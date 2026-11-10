"""
Download IPEDS enrollment data files from NCES.

Where files come from:
    Each file is downloaded from the link on NCES's own Complete Data Files
    listing (https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=YYYY).
    Recent files live under /ipeds/complete-data-files/, older ones under
    /ipeds/datacenter/data/. The two paths are never guessed: the legacy path
    can serve an OLDER copy under the same name. If the listing cannot be read,
    nothing is downloaded or replaced.

When a file is refreshed:
    A local ZIP is kept only if every member (CRC-32 and size) matches the
    upstream ZIP. Any difference, including a one-digit correction, triggers a
    re-download. When NCES publishes the final version of a year, the ZIP gains
    a *_rv.csv member; the transforms read that member when it exists.

Safety:
    A replacement that would drop the final {stem}_rv.csv (or any *_rv.csv)
    the local copy has is refused; the local copy is the ZIP's members plus
    the {stem}.csv and {stem}_rv.csv on disk, so this holds even when the ZIP
    itself is missing. A replacement that would leave the transforms no file
    to read is refused too. Member names are checked before anything is
    downloaded, and a download is read in full (every CRC-32) before it
    replaces anything, so a corrupt or unsafe ZIP leaves the previous files as
    they were. Each member is extracted to a temporary file and moved into
    place, so an interrupted run never leaves a half-written CSV. Files only
    the previous version of a ZIP had are removed before the new version
    replaces it, and on every run a {stem}.csv or {stem}_rv.csv the ZIP does
    not contain is removed, so files from an older version never linger, even
    after an interrupted run. Files of other NCES files whose names start with
    the same stem (such as ef2015a_dist.csv from EF2015A_DIST.zip) are never
    touched. A local ZIP that cannot be read, or whose member data is corrupt,
    is treated as different from upstream and replaced. After a refresh, the
    CSV the transforms read must be in its ZIP and match it, and must be
    {stem}_rv.csv when the ZIP has it. A failure in one file or year never
    stops the others.

Waiting for NCES:
    A year whose fall enrollment NCES has not published yet is WAITING (the
    rule the update checker uses, ipeds_files.waiting_years): its enrollment
    file is reported as WAITING, not as a failure. A file on a year's listing
    whose name starts with the enrollment file's stem but that the pipeline
    does not know (e.g. DRVEF2024_RV.zip next to DRVEF2024.zip) is reported
    as a NOTE: it may hold final or corrected data the pipeline does not read.

File Types:
- DRVEF (Derived Fall Enrollment): Pre-calculated FTE, 2021 onward
- EF (Fall Enrollment, part A): Enrollment by FT/PT status, used for 2015-2020
- EFFY (12-month enrollment): Headcount only
- HD (Directory): Institution names and metadata

For FTE calculations:
- 2021 onward: Use DRVEF (has pre-calculated FTE)
- 2015-2020: Use EF part A and calculate FTE from full-time and part-time
  counts (see 02b_transform_ef_enrollment.py)

Exit code: 0 when every file is current or WAITING for NCES, 1 when anything failed.

Usage:
    python 01b_download_ipeds.py
    python 01b_download_ipeds.py --year 2023
    python 01b_download_ipeds.py --ef-only  # Download only EF files for 2015-2020
    python 01b_download_ipeds.py --check    # List CSVs on disk
    python 01b_download_ipeds.py --force    # Re-download selected files even if identical
"""

import os
import sys
import argparse
import contextlib
import zipfile
import zlib
from pathlib import Path

from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import DATA_YEARS  # noqa: E402
import ipeds_files  # noqa: E402
import provenance  # noqa: E402
from ipeds_files import IPEDS_RAW_DIR  # noqa: E402

# Years to download (match our crime data range)
IPEDS_YEARS = list(DATA_YEARS)

# Year ranges for different file types
DRVEF_YEARS = [y for y in IPEDS_YEARS if y >= 2021]  # DRVEF (pre-calculated FTE) exists 2021+
EF_YEARS = [y for y in IPEDS_YEARS if y <= 2020]     # Need EF for FTE calculation


NOTICES: list[str] = []  # listing notes, printed again in the summary (not failures)


def get_files_for_year(year: int) -> list[str]:
    """
    Get the list of files to download for a given year.

    - DRVEF (pre-calculated FTE) only exists for 2021+
    - For 2015-2020, we use EF files to calculate FTE
    """
    files = [
        f"EFFY{year}",      # 12-month unduplicated headcount
        f"HD{year}",        # Directory info
    ]

    if year in DRVEF_YEARS:
        files.append(f"DRVEF{year}")  # Derived Fall Enrollment (has pre-calculated FTE)

    if year in EF_YEARS:
        files.append(f"EF{year}A")    # Fall Enrollment Part A (has FT/PT breakdown for FTE calc)

    return files


def pipeline_stem(year: int) -> str:
    """Stem of the CSV the enrollment transforms read for `year`."""
    return f"drvef{year}" if year in DRVEF_YEARS else f"ef{year}a"


def files_for_run(year: int, ef_only: bool = False) -> list[str]:
    files = get_files_for_year(year)
    if ef_only:
        files = [f for f in files if f.startswith("EF") and not f.startswith("EFFY")]
    return files


def _download(url: str, dest: Path, desc: str) -> None:
    with ipeds_files.session().get(url, stream=True, timeout=ipeds_files.TIMEOUT) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True,
                                         unit_divisor=1024, desc=desc, leave=False) as pbar:
            for chunk in response.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))


def _describe(e: Exception) -> str:
    if isinstance(e, ValueError):
        return str(e)
    kind = type(e).__name__ if type(e).__module__ == "builtins" else f"{type(e).__module__}.{type(e).__name__}"
    return f"{kind}: {e}"


# Errors raised while reading a ZIP's member data: CRC mismatch, broken
# compressed data, unsupported compression or ZIP version, encryption.
ZIP_DATA_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError)


def _readable_entries(zip_path: Path) -> ipeds_files.ZipEntries | None:
    """Member list of a local ZIP, or None if it is missing or unreadable."""
    if not zip_path.exists():
        return None
    try:
        return ipeds_files.local_entries(zip_path)
    except Exception as e:  # whatever the cause, a ZIP that cannot be read is not trusted
        print(f"  Local {zip_path.name} is unreadable ({_describe(e)}); it will be replaced")
        return None


def _named_after(zip_path: Path, p: Path) -> bool:
    """
    Whether p is a version of one of the ZIP's own files: {stem}.csv or
    {stem}_rv.csv (any case). Files of other NCES files whose names only
    start with the stem (ef2015a_dist.csv from EF2015A_DIST.zip,
    effy2023_hs.csv from EFFY2023_HS.zip) never are.
    """
    stem = zip_path.stem.lower()
    n = p.name.lower()
    own = n in (f"{stem}.csv", f"{stem}_rv.csv")
    return own and p.is_file() and p != zip_path


def _local_names(zip_path: Path, entries: ipeds_files.ZipEntries | None) -> set[str]:
    """
    Lower-case names of the files the local copy provides: the ZIP's members
    when it can be read, plus the {stem}.csv and {stem}_rv.csv on disk (e.g.
    drvef2023.csv, drvef2023_rv.csv), so a missing or unreadable ZIP still
    counts what the transforms read now.
    """
    names = {ipeds_files.member_file_name(m).lower() for m in entries or ()}
    names |= {p.name.lower() for p in zip_path.parent.iterdir()
              if _named_after(zip_path, p) and p.name.lower().endswith(".csv")}
    return names


def _replacement_problem(zip_path: Path, local: set[str], new: set[str], pipeline: bool) -> str | None:
    """Why the local files must not be replaced by a ZIP whose file names are `new`."""
    stem = zip_path.stem.lower()
    final, provisional = f"{stem}_rv.csv", f"{stem}.csv"
    if final in local and final not in new:
        return (f"NCES's copy has no {final} but the local copy does (NCES may be serving an older copy). "
                f"Kept the local files; retry later, or delete {final} by hand if NCES withdrew it")
    if any(n.endswith("_rv.csv") for n in local) and not any(n.endswith("_rv.csv") for n in new):
        return ("NCES's copy has no final *_rv.csv file but the local copy does (NCES may be serving an "
                "older copy). Kept the local files; retry later")
    if pipeline and local & {final, provisional} and not new & {final, provisional}:
        return (f"NCES's copy has neither {provisional} nor {final}, the files the transforms read. "
                "Kept the local files; NCES may have renamed its files, so the pipeline needs an update")
    return None


def _unsafe_names(zip_path: Path, names: list[str]) -> str | None:
    """Why the member names cannot be extracted next to zip_path, or None."""
    problem = ipeds_files.member_name_problem(names)
    if problem:
        return problem
    for member in names:
        name = ipeds_files.member_file_name(member).lower()
        if name == zip_path.name.lower() or name.endswith(".part"):
            return f"member {member!r} would overwrite a file the downloader itself uses"
    return None


def refresh_file(url: str, zip_path: Path, force: bool = False, pipeline: bool = False) -> str:
    """
    Make zip_path match the ZIP at url and extract it. `pipeline` marks the
    ZIP whose CSV the enrollment transforms read.

    Returns "up_to_date", "downloaded", "not_found" or "failed". Any error is
    reported and returned as "failed", so one bad file never stops the rest.
    """
    name = zip_path.stem
    tmp_path = zip_path.with_name(zip_path.name + ".part")
    try:
        remote = ipeds_files.remote_entries(url)
        if remote is None:
            print(f"  FAILED: NCES lists {name} but {url} returns 404")
            return "not_found"
        remote_members, remote_size = remote
        unsafe = _unsafe_names(zip_path, list(remote_members))
        if unsafe:
            print(f"  FAILED: NCES's {zip_path.name} cannot be extracted safely: {unsafe}. "
                  "Nothing was downloaded or changed; this file needs a manual look")
            return "failed"

        old_members = _readable_entries(zip_path)
        if old_members is not None and not force:
            if old_members == remote_members:
                try:
                    _extract(zip_path)
                except ZIP_DATA_ERRORS as e:
                    print(f"  Local {zip_path.name} matches NCES's member list but its data is corrupt "
                          f"({_describe(e)}); downloading a fresh copy")
                else:
                    _remove_orphans(zip_path, pipeline)
                    print(f"  Up to date: {zip_path.name} (every member identical)")
                    return "up_to_date"
            else:
                print(f"  Upstream differs: {ipeds_files.describe_difference(old_members, remote_members)}")

        _download(url, tmp_path, name)
        if not zipfile.is_zipfile(tmp_path):
            print(f"  FAILED: {url} did not return a ZIP file")
            return "failed"
        new_members = ipeds_files.local_entries(tmp_path)
        if new_members != remote_members:
            print(f"  FAILED: download of {name} does not match its own listing; retry later")
            return "failed"

        new_names = {ipeds_files.member_file_name(m) for m in new_members}
        problem = _replacement_problem(zip_path, _local_names(zip_path, old_members), new_names, pipeline)
        if problem:
            print(f"  FAILED: refusing to replace {zip_path.name}: {problem}")
            return "failed"
        try:
            _verify(tmp_path, zip_path)
        except (ValueError, *ZIP_DATA_ERRORS) as e:
            print(f"  FAILED: the download of {zip_path.name} is corrupt or unsafe ({_describe(e)}). "
                  "Kept the previous files; retry later")
            return "failed"

        _remove_former(zip_path, old_members, new_names)
        if zip_path.exists():
            print(f"  UPDATED: {zip_path.name} {zip_path.stat().st_size:,} -> {remote_size:,} bytes")
        else:
            print(f"  Downloaded: {zip_path.name} ({remote_size:,} bytes)")
        tmp_path.replace(zip_path)
        _extract(zip_path)
        _remove_orphans(zip_path, pipeline)
        return "downloaded"

    except Exception as e:  # one file's failure must not stop the other files and years
        print(f"  FAILED: {name}: {_describe(e)}")
        return "failed"
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)


def _verify(path: Path, zip_path: Path) -> None:
    """
    Read every member of the ZIP at `path`, which is to become zip_path,
    without writing anything: checks the member names, the compression method
    and each member's CRC-32. Raises on any problem.
    """
    with zipfile.ZipFile(path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        _check_names(zip_path, members)
        for info in members:
            with zf.open(info) as src:  # zf.open checks the CRC when the member is read to the end
                while src.read(1 << 20):
                    pass


def _check_names(zip_path: Path, members: list[zipfile.ZipInfo]) -> None:
    for names in ([i.orig_filename for i in members], [i.filename for i in members]):
        unsafe = _unsafe_names(zip_path, names)
        if unsafe:
            raise ValueError(f"{zip_path.name}: {unsafe}")


def _extract(zip_path: Path) -> None:
    """
    Extract every member into the ZIP's folder (flat, by file name). A file
    already identical to its member (CRC-32 and size) is left alone; any other
    is written to a temporary file first and then moved into place.
    """
    year_dir = zip_path.parent
    with zipfile.ZipFile(zip_path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        _check_names(zip_path, members)
        on_disk = {p.name.lower(): p for p in year_dir.iterdir() if p.is_file()}
        for info in members:
            name = ipeds_files.member_file_name(info.filename)
            target = on_disk.get(name.lower(), year_dir / name)
            if target.exists() and ipeds_files.crc32_file(target) == (info.CRC, info.file_size):
                continue
            part = year_dir / (name + ".part")
            try:
                with zf.open(info) as src, open(part, "wb") as dst:  # zf.open checks the CRC on read
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                os.replace(part, target)
            finally:
                part.unlink(missing_ok=True)


def _remove_former(zip_path: Path, old: ipeds_files.ZipEntries | None, new_names: set[str]) -> None:
    """
    Delete the files only the previous local copy of the ZIP had (e.g. a
    drvef2023_notes.csv that the new version drops), and the {name}.part an
    interrupted extraction may have left for one of them. This runs before
    the new ZIP replaces the old one: afterwards nothing on disk would tell
    that they came from this ZIP, so an interrupted run would leave them for
    good. {stem}.csv and {stem}_rv.csv are left to _remove_orphans, which
    guards the files the transforms read, and a name that another ZIP in the
    folder also has is kept.
    """
    stem = zip_path.stem.lower()
    gone = ({ipeds_files.member_file_name(m).lower() for m in old or ()}
            - {n.lower() for n in new_names} - {f"{stem}.csv", f"{stem}_rv.csv", zip_path.name.lower()})
    gone = {n for n in gone if not n.endswith(".part")}
    if not gone:
        return
    for other in zip_path.parent.glob("*.zip"):
        if other.name.lower() != zip_path.name.lower():
            with contextlib.suppress(Exception):
                gone -= {ipeds_files.member_file_name(m) for m in ipeds_files.local_entries(other)}
    gone |= {f"{n}.part" for n in gone}  # the temporary file _extract writes for each
    for p in sorted(zip_path.parent.iterdir()):
        if p.name.lower() in gone and p.is_file():
            p.unlink()
            print(f"  Removed {p.name} (not in the new {zip_path.name})")


def _remove_orphans(zip_path: Path, pipeline: bool) -> None:
    """
    Delete the {stem}.csv or {stem}_rv.csv that the ZIP does not contain, and
    the temporary files an interrupted run left for this ZIP. Those are only
    the names refresh_file and _extract write: {ZIP}.zip.part, and
    {name}.part for each member and for {stem}.csv and {stem}_rv.csv. Any
    other .part file, such as another program's partial download, is left
    alone. This runs on every refresh, so a cleanup an earlier run missed is
    still done. Files only an older version of the ZIP had are removed by
    _remove_former. For the ZIP the transforms read, a {stem}_rv.csv, or a
    {stem}.csv the ZIP has nothing to replace, is never deleted: it raises
    instead.
    """
    stem = zip_path.stem.lower()
    final, provisional = f"{stem}_rv.csv", f"{stem}.csv"
    keep = {ipeds_files.member_file_name(m) for m in ipeds_files.local_entries(zip_path)}
    parts = {f"{n.lower()}.part" for n in (zip_path.name, final, provisional, *keep)}
    for p in sorted(zip_path.parent.iterdir()):
        n = p.name.lower()
        if n in parts and p.is_file():
            p.unlink()
            continue
        if not _named_after(zip_path, p) or n in keep:
            continue
        if n.endswith(".csv"):
            if pipeline and (n == final or (n == provisional and final not in keep)):
                raise ValueError(f"{p.name} is on disk but not in {zip_path.name}, and the transforms read it. "
                                 f"Kept it; check NCES's {zip_path.name}, and delete {p.name} by hand "
                                 "if it should no longer be used")
            p.unlink()
            print(f"  Removed {p.name} (not in {zip_path.name})")


def download_year(year: int, ef_only: bool = False, force: bool = False, waiting: bool = False) -> dict:
    """
    Download IPEDS files for a given year.
    Returns dict mapping file name to status.

    Args:
        year: The year to download
        ef_only: If True, only download EF files (for adding historical FTE)
        force: Re-download even when the local copy is identical
        waiting: The year is WAITING for NCES (ipeds_files.waiting_years): an
            enrollment file NCES does not list yet is "waiting", not a failure
    """
    year_dir = IPEDS_RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    files_to_download = files_for_run(year, ef_only)

    ambiguous: dict[str, list[str]] = {}
    try:
        listing = ipeds_files.listed_files(year)
    except ipeds_files.AmbiguousListing as e:
        listing, ambiguous = e.links, e.conflicts  # only the files linked twice are refused
    except ipeds_files.ListingUnavailable as e:
        print(f"  FAILED: {e}. Nothing downloaded for {year}.")
        return {f: "listing_unavailable" for f in files_to_download}
    if listing is None:
        if waiting:
            print(f"  WAITING: NCES has no {year} listing page yet, so fall {year} enrollment is not "
                  f"published; the site shows {year} counts without rates. Not a failure")
            return {f: "waiting" for f in files_to_download}
        print(f"  FAILED: NCES has no Complete Data Files page for {year}.")
        return {f: "not_listed" for f in files_to_download}

    stem = pipeline_stem(year)
    if stem.upper() in (f.upper() for f in files_to_download):
        for other in ipeds_files.other_versions(stem, [*listing, *ambiguous]):
            url = listing.get(other) or " and ".join(ambiguous[other])
            note = (f"{other}.zip is listed next to {stem.upper()}.zip; check whether it holds final or "
                    f"corrected data (the pipeline does not read it): {url}")
            print(f"  NOTE: {note}")
            NOTICES.append(note)
    results = {}
    for filename in files_to_download:
        url = listing.get(filename.upper())
        print(f"  Checking {filename}.zip...")
        if filename.upper() in ambiguous:
            print(f"  FAILED: NCES's {year} listing links {filename}.zip at more than one address "
                  f"({' and '.join(ambiguous[filename.upper()])}); cannot tell which copy is current, "
                  "so nothing was downloaded or changed for it")
            results[filename] = "ambiguous_listing"
            continue
        if url is None and waiting and filename.lower() == stem:
            print(f"  WAITING: {filename} (fall {year} enrollment) is not on NCES's {year} listing yet; "
                  f"the site shows {year} counts without rates. Not a failure")
            results[filename] = "waiting"
            continue
        if url is None:
            print(f"  FAILED: {filename} is not on NCES's {year} listing")
            results[filename] = "not_listed"
            continue
        status = refresh_file(url, year_dir / f"{filename}.zip", force=force,
                              pipeline=filename.lower() == stem)
        results[filename] = "success" if status in ("up_to_date", "downloaded") else status

    # The enrollment CSV the transforms will read must be the right copy from its ZIP
    for filename in files_to_download:
        if filename.lower() != stem:
            continue
        chosen = ipeds_files.pipeline_csv(year, stem)
        if chosen is not None:
            kind = "final" if chosen.name.lower().endswith("_rv.csv") else "provisional"
            print(f"  Transforms will read {chosen.name} ({kind})")
        if results[filename] != "success":
            continue
        try:
            problem = ipeds_files.pipeline_csv_problem(year, stem, year_dir / f"{filename}.zip")
        except Exception as e:
            problem = f"could not check the CSV the transforms read ({_describe(e)})"
        if problem:
            print(f"  FAILED: {year}: {problem}")
            results[filename] = "wrong_csv"

    return results


def check_existing_files() -> dict:
    """Check which files already exist."""
    existing = {}
    for year in IPEDS_YEARS:
        year_dir = IPEDS_RAW_DIR / str(year)
        if year_dir.exists():
            csvs = list(year_dir.glob("*.csv"))
            if csvs:
                existing[year] = [f.name for f in csvs]
    return existing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download IPEDS Fall Enrollment data from NCES"
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Download only a specific year"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing files without downloading"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download the selected files even if the local copy is identical"
    )
    parser.add_argument(
        "--ef-only",
        action="store_true",
        help="Download only EF files for 2015-2020 (for historical FTE calculation)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("IPEDS Enrollment Data Downloader")
    print("=" * 60)
    print("Source: links on https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx")
    print(f"Target: {IPEDS_RAW_DIR.absolute()}")

    if args.ef_only:
        print("Mode: EF files only (for historical FTE)")
        print(f"Years: {min(EF_YEARS)}-{max(EF_YEARS)}")
    else:
        print(f"Years: {min(IPEDS_YEARS)}-{max(IPEDS_YEARS)}")

    if args.check:
        existing = check_existing_files()
        if existing:
            print("\nExisting files:")
            for year, files in sorted(existing.items()):
                print(f"  {year}: {', '.join(files)}")
        else:
            print("\nNo existing files found.")
        return 0

    IPEDS_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.ef_only:
        years_to_download = EF_YEARS
    elif args.year:
        years_to_download = [args.year]
    else:
        years_to_download = IPEDS_YEARS

    NOTICES.clear()
    try:  # the rule looks at the years of DATA_YEARS newest first, also with --year
        waiting, _ = ipeds_files.waiting_years(IPEDS_YEARS, pipeline_stem)
    except Exception as e:
        print(f"Could not tell which years wait for NCES ({_describe(e)}); none is treated as waiting")
        waiting = set()

    all_results = {}
    for year in years_to_download:
        print(f"\n{year}:")
        try:
            all_results[year] = download_year(year, ef_only=args.ef_only, force=args.force,
                                              waiting=year in waiting)
        except Exception as e:  # one year's failure must not stop the other years
            print(f"  FAILED: {year}: {_describe(e)}")
            all_results[year] = {f: "failed" for f in files_for_run(year, args.ef_only)} or {str(year): "failed"}

    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)

    success_count = sum(
        1 for year_results in all_results.values()
        for status in year_results.values()
        if status == "success"
    )
    total_count = sum(1 for r in all_results.values() for status in r.values() if status != "waiting")
    print(f"Successful: {success_count}/{total_count} files")

    waiting_files = [
        (year, fname)
        for year, results in all_results.items()
        for fname, status in results.items()
        if status == "waiting"
    ]
    if waiting_files:
        print("\nWaiting for NCES (not a failure):")
        for year, fname in waiting_files:
            print(f"  {year}/{fname}: not published yet; the site shows {year} counts without rates")

    if NOTICES:
        print("\nNotes (not failures):")
        for note in NOTICES:
            print(f"  {note}")

    failures = [
        (year, fname, status)
        for year, results in all_results.items()
        for fname, status in results.items()
        if status not in ("success", "waiting")
    ]
    if failures:
        print("\nFailed downloads:")
        for year, fname, status in failures:
            print(f"  {year}/{fname}: {status}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 02b_transform_ef_enrollment.py")
    print("2. Run: python 02a_transform_enrollment.py")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(provenance.run_locked("01b", main))
