"""
Download Clery Act data release zips from DOE.

The DOE download page (https://ope.ed.gov/campussafety/#/datafile/list) is an
Angular SPA; files are served from its API:

    https://ope.ed.gov/campussafety/api/dataFiles/file?fileName=Crime{RELEASE}{FMT}.zip

IMPORTANT: Release zips are named by RELEASE year, not data year. Each release
contains THREE calendar years of data (e.g. Crime2025SAS.zip covers calendar
years 2022-2024, in files suffixed 222324). The transform step
(02_transform_to_parquet.py) takes each campus-year from the newest release
that has it, so this script downloads every release that covers a year of
DATA_YEARS (for 2015-2024, Crime2016SAS.zip to Crime2025SAS.zip).

Usage:
    python 01_download_raw_data.py                 # releases needed for DATA_YEARS
    python 01_download_raw_data.py --release 2025  # a single release
    python 01_download_raw_data.py --check         # list what's on disk
    python 01_download_raw_data.py --force         # re-download existing zips

A download is saved to a temporary file and replaces the zip on disk only
when it is a complete, readable zip that holds every crime file the transform
reads. If it is not (an error page, a cut-off transfer, a renamed file), the
zip already on disk is kept as it was.

Extracting never damages files already extracted: a zip on disk is first
read in full (every member's CRC-32 is checked) and must hold every crime
file the transform reads, and each file is written to a temporary file that
replaces the extracted file only once it is complete and verified. A release
that fails is reported with the command that fixes it, the other releases
are still processed, and the exit code is 1. A 404 for a release DOE has not
published yet is expected and does not change the exit code: that is a
release newer than the newest release held, once the releases held already
cover the newest year in DATA_YEARS. Any other 404 (for example for the only
release that covers that year) is a failure.

Manual Fallback:
    If script fails, download manually from:
    https://ope.ed.gov/campussafety/#/datafile/list
"""

import os
import sys
import argparse
import importlib
import re
import shutil
import zipfile
import zlib
import requests
from pathlib import Path
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, DATA_YEARS
import ipeds_files
import provenance

# The download page is an Angular SPA; files are served by its API endpoint.
# Release zips are named by RELEASE year and each contains THREE calendar
# years of data (e.g. Crime2025SAS.zip covers calendar years 2022-2024).
# These are here and not in config.py because config.py is part of every
# build stage's code fingerprint (provenance.STAGE_CODE) and this file is
# not, so changing a URL does not make the whole build out of date.
# 00_check_for_updates.py uses DOE_BASE_URL from here.
DOE_BASE_URL = "https://ope.ed.gov/campussafety/api/dataFiles/file"
DOE_DOWNLOAD_PAGE = "https://ope.ed.gov/campussafety/#/datafile/list"


def get_data_url(release_year: int, file_type: str = "sas") -> str:
    """Get the download URL for a release-year zip (sas, excel, or spss)."""
    fmt = file_type.upper()
    if fmt == "CSV":
        fmt = "EXCEL"  # DOE ships spreadsheet data in the EXCEL zip
    if fmt not in ("SAS", "EXCEL", "SPSS"):
        raise ValueError(f"Unknown file type: {file_type}")
    return f"{DOE_BASE_URL}?fileName=Crime{release_year}{fmt}.zip"


# What reading a damaged or unreadable zip can raise
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, OSError)


def expected_members(release_year: int) -> list[str]:
    """The crime files the transform reads from a SAS release, e.g. oncampuscrime222324.sas7bdat."""
    transform = importlib.import_module("02_transform_to_parquet")
    suffix = "".join(f"{(release_year - k) % 100:02d}" for k in (3, 2, 1))
    return [f"{geo}{cat}{suffix}.sas7bdat" for geo in transform.GEOGRAPHY_MAP for cat in transform.CATEGORY_MAP]


def missing_members(names: set[str], release_year: int, fmt: str) -> str | None:
    """
    The crime files the transform reads that a release zip whose (lowercased)
    member names are `names` lacks, listed as text, or None when it lacks
    none. Only SAS releases are checked.
    """
    if fmt != "SAS":
        return None
    missing = [m for m in expected_members(release_year) if m not in names]
    if not missing:
        return None
    more = f" and {len(missing) - 6} more" if len(missing) > 6 else ""
    return f"{', '.join(missing[:6])}{more}"


def zip_problem(path: Path, release_year: int, fmt: str) -> str | None:
    """Why a downloaded file is not a complete release zip, or None if it is."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = {i.filename.lower() for i in zf.infolist() if not i.is_dir()}
            bad = zf.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, OSError) as e:
        return f"not a readable zip file ({e})"
    if bad is not None:
        return f"a zip whose member {bad} is damaged"
    missing = missing_members(names, release_year, fmt)
    if missing:
        return (f"a zip without the crime files the transform expects ({missing}); "
                "DOE may have renamed them, so the pipeline may need an update")
    return None


def download_file(url: str, dest_path: Path, desc: str = "", check=None) -> bool | None:
    """
    Download a file with progress bar.

    The download goes to a temporary file next to dest_path and replaces
    dest_path only when it is complete and check(temp_path), if given, finds
    no problem. On any failure dest_path is left as it was.
    Returns True if successful, None if the server answered 404 (not found),
    False on any other failure.
    """
    part = dest_path.with_name(dest_path.name + ".part")
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0) or 0)
            encoded = (response.headers.get('content-encoding') or 'identity').lower() != 'identity'
            received = 0
            with open(part, 'wb') as f, tqdm(
                total=total_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc=desc or dest_path.name,
                leave=False
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        received += len(chunk)
                        pbar.update(len(chunk))
        if total_size and not encoded and received != total_size:
            print(f"  Failed: received {received:,} of {total_size:,} bytes")
            return False
        problem = check(part) if check else None
        if problem:
            print(f"  Failed: what DOE sent for {dest_path.name} is {problem}")
            return False
        os.replace(part, dest_path)
        return True

    except requests.exceptions.RequestException as e:
        print(f"  Failed: {e}")
        response = getattr(e, "response", None)
        return None if response is not None and response.status_code == 404 else False
    except OSError as e:
        # For example the zip on disk is open in another program, so it cannot
        # be replaced, or the disk is full
        print(f"  Failed: could not save {dest_path.name} ({e}). If another program has it open, "
              "close that program and try again")
        return False
    finally:
        # Only the partial download is removed, never the file already in place
        part.unlink(missing_ok=True)


def needed_release_years() -> list[int]:
    """
    Release years whose zips the transform reads: every release that covers
    a year of DATA_YEARS.

    Release r contains calendar years r-3..r-1, so data year y is in releases
    y+1, y+2 and y+3. The transform takes each campus-year from the newest of
    them that has it, so a campus missing from a newer release keeps an older
    release's numbers. Trailing releases that DOE has not published yet will
    404 and can be ignored - the years they would cover are still present
    (unrevised) in the newest published release.
    """
    return sorted({y + k for y in DATA_YEARS for k in (1, 2, 3)})


class ExtractError(Exception):
    """A release could not be extracted. The message says why; fix is the command that fixes it."""

    def __init__(self, message: str, fix: str):
        super().__init__(f"{message} {fix}")
        self.fix = fix


def release_command(release_year: int, fmt: str = "SAS") -> str:
    """The command that downloads and extracts one release, e.g. ... --release 2025."""
    return (f"python 01_download_raw_data.py --release {release_year}"
            + ("" if fmt == "SAS" else f" --format {fmt.lower()}"))


def held_releases(fmt: str = "SAS") -> list[int]:
    """The release years whose zip is in RAW_DIR."""
    return [int(m.group(1)) for p in RAW_DIR.glob("Crime*.zip")
            if (m := re.fullmatch(rf"Crime(\d{{4}}){fmt}\.zip", p.name, re.I))]


def not_published_yet(release_year: int, newest_held: int | None) -> bool:
    """
    Whether a 404 for release_year only means DOE has not published it yet:
    the newest release held (on disk, downloaded now or before) already covers
    the newest year in DATA_YEARS (release r covers r-3..r-1), and
    release_year is newer than it. Any other 404 is a failure, for example one
    for the only release that covers that year.
    """
    return (newest_held is not None and newest_held >= max(DATA_YEARS) + 1
            and release_year > newest_held)


def extract_release(zip_path: Path, release_year: int, verified: bool = False,
                    fmt: str = "SAS") -> tuple[int, int]:
    """
    Extract a release zip flat into RAW_DIR without ever damaging a file that
    is already there. Unless verified (just downloaded and checked), the zip is
    first read in full, which checks every member's CRC-32, and must hold
    every crime file the transform reads, so a damaged or incomplete zip
    changes nothing. Each member is then written to <name>.part, which
    replaces the extracted file only once it is complete and its CRC-32
    matched; a file already identical to its member is left as it is.
    Returns (files in the zip, files written). Raises ExtractError.
    """
    command = release_command(release_year, fmt)
    redownload = f"Download it again: {command} --force"
    kept = "Nothing was extracted from it, and the files already extracted were kept as they were."
    try:
        zf = zipfile.ZipFile(zip_path)
    except ZIP_ERRORS as e:
        raise ExtractError(f"{zip_path.name} on disk is not a readable zip file ({e}). {kept}", redownload) from e
    with zf:
        try:
            bad = None if verified else zf.testzip()
        except ZIP_ERRORS as e:
            raise ExtractError(f"{zip_path.name} on disk is damaged and cannot be read in full ({e}). {kept}",
                               redownload) from e
        if bad is not None:
            raise ExtractError(f"{zip_path.name} on disk is damaged: its member {bad} does not match "
                               f"its CRC-32. {kept}", redownload)
        if not verified:
            names = {i.filename.lower() for i in zf.infolist() if not i.is_dir()}
            missing = missing_members(names, release_year, fmt)
            if missing:
                raise ExtractError(f"{zip_path.name} on disk lacks crime files the transform reads "
                                   f"({missing}). {kept}", redownload)
        written = 0
        members = [i for i in zf.infolist() if not i.is_dir()]
        for info in members:
            target = RAW_DIR / Path(info.filename).name
            if target.name in ("", ".", ".."):
                continue
            part = target.with_name(target.name + ".part")
            try:
                if target.is_file() and ipeds_files.crc32_file(target) == (info.CRC, info.file_size):
                    continue  # already extracted intact
                # Reading the member to its end checks its CRC-32
                with zf.open(info) as src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                os.replace(part, target)
                written += 1
            except OSError as e:
                raise ExtractError(f"Could not write {target.name} into {RAW_DIR} ({e}). Every file on disk "
                                   "was kept as it was or replaced by a complete, verified copy.",
                                   "If another program has the file open, close it; if the disk is full, "
                                   f"free space. Then run: {command}") from e
            except ZIP_ERRORS as e:
                raise ExtractError(f"Could not extract {info.filename} from {zip_path.name} ({e}). Every file "
                                   "on disk was kept as it was or replaced by a complete, verified copy.",
                                   redownload) from e
            finally:
                part.unlink(missing_ok=True)
    return len(members), written


def download_release(release_year: int, file_type: str = "sas", force: bool = False) -> tuple[str, str | None]:
    """
    Download and extract the release zip for a given RELEASE year.
    Returns (status, fix): status is "ok" when the zip is present and
    extracted, "not_found" when DOE answered 404 for it, "failed" for any
    other problem; fix says what fixes a problem (None when "ok").
    """
    fmt = "SAS" if file_type.lower() == "sas" else file_type.upper()
    zip_path = RAW_DIR / f"Crime{release_year}{fmt}.zip"
    verified = False

    if zip_path.exists() and not force:
        print(f"\n{release_year}: Already downloaded ({zip_path.name})")
    else:
        url = get_data_url(release_year, file_type)
        print(f"\n{release_year}: Downloading {zip_path.name}...")
        downloaded = download_file(url, zip_path, zip_path.name,
                                   check=lambda part: zip_problem(part, release_year, fmt))
        if not downloaded:
            if zip_path.exists():
                print(f"  Kept the {zip_path.name} already on disk; nothing was changed")
            else:
                print(f"  Could not download release {release_year}")
                if downloaded is None and not_published_yet(release_year, max(held_releases(fmt), default=None)):
                    print(f"  (DOE answers 404 for a release it has not published yet)")
            if downloaded is None:
                return "not_found", (f"DOE answered 404 for {zip_path.name}. Check whether DOE still offers "
                                     f"it at {DOE_DOWNLOAD_PAGE}")
            return "failed", f"Try again: {release_command(release_year, fmt)}" + (" --force" if force else "")
        print(f"  Downloaded: {zip_path.name}")
        verified = True

    try:
        n, written = extract_release(zip_path, release_year, verified, fmt)
    except ExtractError as e:
        print(f"  ERROR: {e}")
        return "failed", e.fix
    print(f"  Extracted {n} files into {RAW_DIR} ({written} written, {n - written} already up to date)")
    return "ok", None


def check_existing_files() -> None:
    """List release zips and extracted SAS files on disk."""
    zips = sorted(RAW_DIR.glob("Crime*.zip"))
    sas = list(RAW_DIR.glob("*.sas7bdat"))
    if zips:
        print("\nRelease zips on disk:")
        for z in zips:
            size_mb = z.stat().st_size / (1024 * 1024)
            print(f"  {z.name} ({size_mb:.1f} MB)")
    else:
        print("\nNo release zips found.")
    print(f"\nExtracted SAS files: {len(sas)}")


def main():
    parser = argparse.ArgumentParser(
        description="Download Clery Act crime data release zips from DOE"
    )
    parser.add_argument(
        "--release",
        type=int,
        help="Download only a specific RELEASE year (e.g. 2025 = calendar years 2022-24)"
    )
    parser.add_argument(
        "--format",
        choices=["sas", "excel", "spss"],
        default="sas",
        help="File format to download (default: sas)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing files without downloading"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if zips exist"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Clery Act Data Downloader")
    print("=" * 60)
    print(f"Target: {RAW_DIR.absolute()}")
    print(f"Format: {args.format.upper()}")

    if args.check:
        check_existing_files()
        return

    # Create raw directory
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Ascending order so the newest release's ReadMe.txt wins on extract
    releases = [args.release] if args.release else needed_release_years()

    results = {release_year: download_release(release_year, args.format, force=args.force)
               for release_year in releases}
    successful = [r for r, (status, _) in results.items() if status == "ok"]
    # A 404 is expected only for a release DOE has not published yet (see
    # not_published_yet). Any other problem is a failure.
    fmt = "SAS" if args.format == "sas" else args.format.upper()
    newest_held = max(held_releases(fmt), default=None)
    unpublished = [r for r, (status, _) in results.items()
                   if status == "not_found" and not_published_yet(r, newest_held)]
    failed = [(r, fix) for r, (status, fix) in results.items() if status != "ok" and r not in unpublished]
    # 404s that are failures only because no release held covers the newest year
    uncovered = [r for r, _ in failed
                 if results[r][0] == "not_found" and (newest_held is None or r > newest_held)]

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Successful: {len(successful)} releases")
    if successful:
        print(f"  Releases: {', '.join(map(str, successful))}")
    if unpublished:
        print(f"\nNot published by DOE yet: {len(unpublished)} releases")
        print(f"  Releases: {', '.join(map(str, unpublished))}")
        print(f"  (DOE answers 404 for releases newer than Crime{newest_held}{fmt}.zip, the newest held, "
              f"which already covers {max(DATA_YEARS)}; that is expected)")
    if failed:
        print(f"\nFAILED: {len(failed)} releases")
        for r, fix in failed:
            print(f"  {r}: {fix}")
        if uncovered:
            year = max(DATA_YEARS)
            print(f"  No release held covers {year}, the newest year in DATA_YEARS (config.py), so the 404s "
                  f"above are failures, not releases DOE has yet to publish. Crime{year + 1}{fmt}.zip is the "
                  f"first release that covers {year}; if DOE has not published it yet, take {year} out of "
                  "DATA_YEARS until it does.")
        print(f"  Manual download: {DOE_DOWNLOAD_PAGE}")
        print("\nThe files already on disk were kept as they were. Fix the releases above, "
              "then run: python 02_transform_to_parquet.py")
        return 1

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Verify downloads in data/raw/")
    print("2. Run: python 02_transform_to_parquet.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("01", main))
