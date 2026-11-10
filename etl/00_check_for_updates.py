"""
Check whether DOE or NCES has published data that is newer than, or different
from, what the pipeline uses, and whether the site data was built from exactly
those files. Nothing under data/ or frontend/ is changed.

What it checks:
  DOE Campus Safety (crime counts)
    - DOE's own file listing, row by row: every row must be a kind of file the
      listing has always had (CrimeYYYY{SAS,SPSS,EXCEL}.zip or CrimeYYYY.zip
      for release YYYY); any other row is reported as NEW. Is there a release
      newer than the newest we hold (in any format), is every release the
      pipeline needs still offered, and does each still cover the calendar
      years we expect?
    - The next release by its exact predicted name (e.g. Crime2026SAS.zip).
    - Every release the pipeline reads that we hold or DOE offers, compared
      byte for byte (SHA-256). DOE's server sends no validators and ignores
      Range, so this downloads each release (about 20 MB each). A download
      that is not a complete release zip cannot be compared and is an ERROR.
      A zip we hold that differs from DOE's and fails its own CRC-32 check is
      reported as damaged on disk (re-download it with --release N --force),
      not as re-issued. Older releases we hold that DATA_YEARS does not need
      are not downloaded.
    - Whether config.DATA_YEARS reaches the newest calendar year available.
    - Whether the transform recognizes every crime file of every release (a
      file it does not recognize would be skipped without an error).
    - Whether the extracted .sas7bdat files are exactly the ones in the zips,
      and every file the transform would read is in a release zip that
      matched DOE's copy in this run. (01_download_raw_data.py checks a zip
      in full before extracting it, never replaces a good file from a damaged
      zip, and exits 1 when a release it needs could not be downloaded or
      extracted.)
  NCES IPEDS (enrollment used for rates)
    - The enrollment file the transforms read (DRVEF, or EF part A before
      2021), for every year in DATA_YEARS, at the location NCES's own Complete
      Data Files listing links to. Compared member by member (CRC-32 and size)
      via the ZIP's central directory, so a same-size correction is still
      detected. EFFY and HD are compared too, but are not read by the
      transforms, so their results are INFO only.
    - Which CSV the transforms read (final *_rv.csv or provisional), that it is
      exactly the copy inside the zip, and that the zip has no other CSV (it
      could be NCES's data under a new name).
    - A ZIP listed next to the pipeline file under a longer name (e.g.
      DRVEF2024_RV.zip next to DRVEF2024.zip) is NEW: it may hold final or
      corrected data, which the pipeline does not read.
    - Whether fall enrollment for the next year has been published. A year in
      DATA_YEARS whose fall enrollment NCES has not published yet is WAITING:
      step 05 marks it "missing" in metadata.json (enrollmentStatus), and the
      site shows its counts without rates until NCES publishes it.
      01b_download_ipeds.py reports such a year as WAITING too, not FAILED.
  Build records (see provenance.py)
    - Whether each stage, 02 through 05, was built from the current raw files
      and pipeline code and from exactly the files the stage before it wrote,
      and whether every file a stage wrote is still on disk unchanged. Two
      records are the same build when they agree on everything but the time a
      step ran (built_at, generated_at): re-running a step that produces the
      same files is not a change.
    - Whether the site data (frontend/public/data) holds exactly the files
      step 05 wrote, built from exactly the current raw files. A file 05 does
      not make (by 05's own rule) is reported on its own line, to delete or
      move: running 05 does not remove it. Files git ignores (.DS_Store,
      desktop.ini) are never committed or published and are not reported.
    - Whether data/curated/facts holds parquet data step 02 did not write
      (steps 03, 04, 06 and 07 refuse to run while it is there).
    - Whether frontend/public/audit.json is 07's audit of exactly this site
      data: 07 records the SHA-256 of the build_inputs.json it audited, and the
      check compares that with the one on disk (times play no part).
    - Whether a pipeline step is running (data/curated/.pipeline.lock).
      Each step holds an operating-system lock on that file while it runs; it
      is released however the step ends, so there is nothing to clean up.
  Release (git and the live sites; the build itself is checked above)
    - Committed: HEAD holds every site file the build record lists, the record
      and audit.json exactly as they are on disk (compared by git blob id, so
      git's line-ending conversion is taken into account), and no other file
      in frontend/public/data. Files git ignores or that the index marks
      assume-unchanged or skip-worktree are named, since git status does not
      show them.
    - Released: origin's main branch (asked with git ls-remote; the commit
      must have been fetched) holds the same frontend/public/data tree and
      audit.json as HEAD. When HEAD does not hold the build on disk, main is
      compared with the build on disk instead, so the line says whether to
      commit first or main already has it. The sites deploy from main; when
      only staging has the build, that is INFO.
    - Served: collegesafetydata.org and collegesafetydata.com each serve this
      build's /data/build_inputs.json, its audit.json and every site file the
      record lists, compared by SHA-256 with the record. Every file is fetched
      on every run (a few at a time, with retries), so a partial or stale
      deploy of any file is found whatever the git history looks like. The
      site's HTML page (its answer for a missing file) counts as missing.
      Removed files: every other path under frontend/public/data that the git
      history of HEAD and origin's main (and every commit this checkout saw
      main at) ever held must be gone from each site (404, 410 or the HTML
      page). In a shallow clone that list may be incomplete, which the RESULT
      says.
    The closing RESULT says committed, released or served only when this run
    showed it.

Anything that cannot be verified is reported as ERROR, never as current.

Exit code: 0 = everything is current, 1 = something is new, changed or not
yet rebuilt, 2 = a check could not be completed, so the answer is unknown.
WAITING and INFO lines do not change the exit code.

Usage:
    python 00_check_for_updates.py
    python 00_check_for_updates.py --local-only   # no network for the release check: origin and the
                                                  # live sites are not asked
"""

import sys
import traceback

try:
    import argparse
    import contextlib
    import hashlib
    import importlib
    import io
    import json
    import re
    import subprocess
    import tempfile
    import threading
    import time
    import zipfile
    import zlib
    from datetime import datetime
    from pathlib import Path

    import requests

    sys.path.insert(0, str(Path(__file__).parent))
    from config import RAW_DIR, DATA_YEARS, PROJECT_ROOT, CURATED_DIR, JSON_DIR, QA_DIR
    import ipeds_files
    import provenance

    downloader = importlib.import_module("01_download_raw_data")
    ipeds = importlib.import_module("01b_download_ipeds")
    transform = importlib.import_module("02_transform_to_parquet")
except Exception:  # an import failure must not look like "no updates"
    traceback.print_exc()
    print("RESULT: the checker could not start, so the answer is UNKNOWN.")
    sys.exit(2)

DOE_FILE_LIST_URL = "https://ope.ed.gov/campussafety/api/dataFiles/fileList"
TIMEOUT = 120
HEADERS = {"Accept-Encoding": "identity", "User-Agent": "collegesafetydata-etl"}
SAS_RELEASE = re.compile(r"Crime(\d{4})SAS\.zip", re.I)
ANY_RELEASE = re.compile(r"Crime(\d{4})", re.I)
# The files DOE's listing has always had for release YYYY: CrimeYYYYSAS.zip,
# CrimeYYYYSPSS.zip, CrimeYYYYEXCEL.zip and CrimeYYYY.zip (aggregated, Excel)
KNOWN_FILE = re.compile(r"Crime(\d{4})(SAS|SPSS|EXCEL)?\.zip", re.I)
KNOWN_FORMAT = {"SAS": "sas", "SPSS": "spss", "EXCEL": "excel", "": "excel"}
CALENDAR_YEARS = re.compile(r"(\d{4})\s*(?:-|\u2013|\u2014|through|to)\s*(\d{2,4})", re.I)
# Failures worth another try: DOE's API intermittently drops or stalls connections
RETRYABLE = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, OSError)
IPEDS_RAW_DIR = ipeds_files.IPEDS_RAW_DIR

findings = []   # (kind, message): NEW, CHANGED, OK, INFO, WAITING or ERROR
WAITING_YEARS: set[int] = set()  # years in DATA_YEARS whose fall enrollment NCES has not published yet
UNRECOGNIZED: list[str] = []  # upstream files the pipeline does not know, reported as NEW


class BadDownload(Exception):
    """DOE answered, but what it sent is not a usable copy of the file."""


def report(kind: str, message: str) -> None:
    findings.append((kind, message))
    print(f"  [{kind:7}] {message}")


def short(items, limit: int = 6) -> str:
    items = list(items)
    more = f" and {len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(str(i) for i in items[:limit]) + more


# --------------------------------------------------------------------------
# DOE crime releases
# --------------------------------------------------------------------------

def release_suffix(release: int) -> str:
    """File suffix of a release, e.g. 2025 -> '222324' (calendar 2022-2024)."""
    return "".join(f"{(release - k) % 100:02d}" for k in (3, 2, 1))


def expected_members(release: int) -> list[str]:
    """The crime files the transform reads from a release, e.g. oncampuscrime222324.sas7bdat."""
    suffix = release_suffix(release)
    return [f"{geo}{cat}{suffix}.sas7bdat" for geo in transform.GEOGRAPHY_MAP for cat in transform.CATEGORY_MAP]


def doe_fetch(url: str, consume, attempts: int = 4):
    """
    GET a DOE URL and return consume(response). Network errors, a body cut
    off mid-transfer and HTTP 5xx are retried with backoff, because DOE's API
    is intermittently flaky; each attempt reads the response from the start.
    Other answers (200, 404, other 4xx) go to consume() as they are.
    """
    delay = 5
    for attempt in range(1, attempts + 1):
        try:
            with requests.get(url, stream=True, timeout=TIMEOUT, headers=HEADERS) as r:
                if r.status_code < 500:
                    return consume(r)
                error = requests.HTTPError(f"HTTP {r.status_code} from {url}", response=r)
        except RETRYABLE as e:
            error = e
        if attempt < attempts:
            print(f"  (attempt {attempt} failed: {error}; retrying in {delay}s)")
            time.sleep(delay)
            delay *= 3
    raise error


def save_body(r, name: str, out) -> str:
    """Write a response's body to the open file `out` and return its SHA-256."""
    r.raise_for_status()
    h, size = hashlib.sha256(), 0
    for chunk in r.iter_content(chunk_size=1 << 20):
        h.update(chunk)
        out.write(chunk)
        size += len(chunk)
    declared = str(r.headers.get("Content-Length") or "")
    encoded = str(r.headers.get("Content-Encoding") or "identity").lower() != "identity"
    if declared.isdigit() and not encoded and int(declared) != size:
        raise BadDownload(f"DOE sent {size:,} of the {int(declared):,} bytes it announced for {name}")
    return h.hexdigest()


def read_zip(f, name: str) -> dict[str, tuple[int, int]]:
    """Member list of a downloaded zip, after reading every member in full. Raises BadDownload."""
    f.seek(0)
    try:
        with zipfile.ZipFile(f) as zf:
            members = {i.filename.lower(): (i.CRC, i.file_size) for i in zf.infolist() if not i.is_dir()}
            bad = zf.testzip()
    except ZIP_ERRORS as e:
        raise BadDownload(f"what DOE sent for {name} is not a readable zip file ({e})") from e
    if bad is not None:
        raise BadDownload(f"DOE's {name} has a damaged member ({bad})")
    return members


def doe_release(name: str, release: int, local_sha: str | None):
    """
    DOE's copy of a release as served now: None if DOE answers 404, otherwise
    (SHA-256, members). members is None when the bytes are exactly ours (our
    copy is checked separately); otherwise the download was checked to be a
    complete release zip with every crime file the transform reads, and
    members is its member list. Raises BadDownload when it is not.
    """
    def consume(r):
        if r.status_code == 404:
            return None
        with tempfile.TemporaryFile() as f:
            sha = save_body(r, name, f)
            if sha == local_sha:
                return sha, None
            members = read_zip(f, name)
        missing = [m for m in expected_members(release) if m not in members]
        if missing:
            raise BadDownload(f"DOE's {name} lacks crime files the transform expects ({short(missing)}); "
                              "DOE may have renamed them")
        return sha, members

    return doe_fetch(f"{downloader.DOE_BASE_URL}?fileName={name}", consume)


def probe_release(name: str, release: int):
    """
    Whether DOE serves a release under its predicted name: None for 404,
    otherwise the list of crime files the transform expects that it lacks
    (empty for a complete release). Raises BadDownload when DOE answers with
    something that is not a complete zip.
    """
    def consume(r):
        if r.status_code == 404:
            return None
        with tempfile.TemporaryFile() as f:
            save_body(r, name, f)
            members = read_zip(f, name)
        return [m for m in expected_members(release) if m not in members]

    return doe_fetch(f"{downloader.DOE_BASE_URL}?fileName={name}", consume)


def field(row: dict, key: str):
    """A listing field by DOE's key (e.g. FileName) or its camelCase form (fileName)."""
    value = row.get(key)
    return row.get(key[0].lower() + key[1:]) if value is None else value


def listing_year(value) -> int | None:
    """A listing row's Year as a whole number (2025, '2025', ' 2025 ', 2025.0), or None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return int(number) if number.is_integer() else None


def known_release(row: dict) -> int | None:
    """
    The release year of a listing row of a kind the listing has always had
    (KNOWN_FILE, with Year, when given, equal to that release and Format,
    when given, matching the name), or None for any other row.
    """
    m = KNOWN_FILE.fullmatch(str(field(row, "FileName") or ""))
    if not m:
        return None
    release = int(m.group(1))
    year, fmt = field(row, "Year"), field(row, "Format")
    if year not in (None, "") and listing_year(year) != release:
        return None
    if fmt not in (None, "") and str(fmt).strip().lower() != KNOWN_FORMAT[(m.group(2) or "").upper()]:
        return None
    return release


def describe_row(row: dict) -> str:
    name = str(field(row, "FileName") or "")
    shown = name if name and name == name.strip() else repr(name)
    details = [f"{key} {field(row, key)!r}" for key in ("Year", "Format", "LinkName")
               if field(row, key) not in (None, "")]
    return shown + (f" ({', '.join(details)})" if details else "")


def doe_listing():
    """
    DOE's file listing, every row classified. Returns (listed, known,
    unknown, newest_any): the SAS releases (release year -> row), the rows
    of a kind the listing has always had (release year, row), every other
    row, and the newest release year the listing names in any form.
    """
    rows = doe_fetch(DOE_FILE_LIST_URL, lambda r: (r.raise_for_status(), r.json())[1])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("DOE file listing is not a list of records; its format may have changed")
    listed: dict[int, dict] = {}
    known: list[tuple[int, dict]] = []
    unknown: list[dict] = []
    newest_any = 0
    for row in rows:
        name = str(field(row, "FileName") or "")
        m = SAS_RELEASE.fullmatch(name)
        if m:
            listed[int(m.group(1))] = row
        release = known_release(row)
        if release is None:
            unknown.append(row)
        else:
            known.append((release, row))
        candidates = [int(y) for y in ANY_RELEASE.findall(name)]
        year = listing_year(field(row, "Year"))
        if year is not None:
            candidates.append(year)
        newest_any = max([newest_any, *candidates])
    if not listed:
        raise ValueError("DOE file listing contains no CrimeYYYYSAS.zip releases; its format may have changed")
    return listed, known, unknown, newest_any


def check_calendar_years(release: int, row: dict) -> None:
    """DOE describes each release's calendar years; ours assume R-3 .. R-1."""
    text = str(field(row, "LinkName") or "")
    m = CALENDAR_YEARS.search(text)
    if not m:
        return
    start = int(m.group(1))
    end = int(m.group(2)) if len(m.group(2)) == 4 else start // 100 * 100 + int(m.group(2))
    if (start, end) != (release - 3, release - 1):
        report("ERROR", f"DOE describes {field(row, 'FileName')} as calendar {start}-{end}; "
                        f"the pipeline assumes {release - 3}-{release - 1}")


def release_file_lines(release: int, zip_path: Path) -> tuple[list[tuple[str, str]], str | None]:
    """
    The extracted .sas7bdat files must be exactly the zip's members, and the
    transform must recognize every crime file in the release with the right
    years. Returns the problems as (kind, message), and the OK message when
    there are none.
    """
    name = zip_path.name
    try:
        members = {e.lower(): v for e, v in ipeds_files.local_entries(zip_path).items()}
    except (zipfile.BadZipFile, OSError) as e:
        return [("CHANGED", f"{name} on disk is unreadable ({e}); re-download with "
                            f"01_download_raw_data.py --release {release} --force")], None

    lines = []
    expected_years = [release - 3, release - 2, release - 1]
    missing = [f for f in expected_members(release) if f not in members]
    if missing:
        lines.append(("ERROR", f"{name} lacks crime files the transform expects: {short(missing)}; "
                               "DOE may have renamed them"))
    # Every member that starts like a crime file the transform reads (geography
    # + category). Other members (hate, fire, unfounded, reported*) are not used;
    # the fire files also share names across releases, so they are not compared.
    used = [m for m in members if m.endswith(".sas7bdat")
            and any(m.startswith(g + c) for g in transform.GEOGRAPHY_MAP for c in transform.CATEGORY_MAP)]
    unrecognized = []
    for member in used:
        parsed = transform.parse_filename(member)
        if parsed is None or parsed[3] != expected_years:
            unrecognized.append(member)
    if unrecognized:
        lines.append(("ERROR", f"The transform would skip or misdate {short(unrecognized)} from {name}"))

    on_disk = {p.name.lower(): p for p in RAW_DIR.glob("*.sas7bdat")}
    not_extracted, differs = [], []
    for member in used:
        crc, size = members[member]
        path = on_disk.get(member)
        if path is None:
            not_extracted.append(member)
        elif ipeds_files.crc32_file(path) != (crc, size):
            differs.append(member)
    if not_extracted:
        lines.append(("CHANGED", f"{name}: {short(not_extracted)} not extracted; "
                                 f"run 01_download_raw_data.py --release {release}"))
    if differs:
        lines.append(("CHANGED", f"{name}: extracted {short(differs)} differ from the zip; "
                                 f"run 01_download_raw_data.py --release {release}"))
    if lines:
        return lines, None
    return [], (f"{name}: all files extracted intact and recognized as calendar "
                f"{expected_years[0]}-{expected_years[-1]}")


def reissue_line(name: str, release: int, zip_path: Path, theirs: dict) -> tuple[str, str] | None:
    """
    What a SHA-256 difference with DOE's (complete) copy means: our copy is
    damaged on disk, or DOE re-issued the release. None if our copy is
    unreadable.
    """
    try:
        ours = {e.lower(): v for e, v in ipeds_files.local_entries(zip_path).items()}
    except (zipfile.BadZipFile, OSError):
        return None  # reported as unreadable
    try:  # read every member in full: a damaged copy on disk is not a re-issue
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
        damage = None if bad is None else f"its member {bad} does not match its CRC-32"
    except ZIP_ERRORS as e:
        damage = f"it cannot be read in full: {e}"
    if damage:
        return ("CHANGED", f"{name} on disk is damaged ({damage}), so it no longer matches DOE's copy, which is "
                           f"complete; run 01_download_raw_data.py --release {release} --force")
    diff = ipeds_files.describe_difference(ours, theirs)
    if diff == "no difference":
        diff = "every member is the same; only the zip file itself differs"
    return ("CHANGED", f"{name} was re-issued: DOE's copy differs from ours ({diff}); "
                       f"run 01_download_raw_data.py --release {release} --force")


def check_doe() -> None:
    print("\nDOE Campus Safety crime releases")
    first = len(findings)
    local = {}
    for p in RAW_DIR.glob("*.zip"):
        m = SAS_RELEASE.fullmatch(p.name)
        if m:
            local[int(m.group(1))] = p

    listed: dict[int, dict] = {}
    known, unknown, newest_any = [], [], None
    try:
        listed, known, unknown, newest_any = doe_listing()
    except (requests.RequestException, ValueError) as e:
        report("ERROR", f"Could not read DOE's file listing: {e}")
    for row in unknown:
        UNRECOGNIZED.append(describe_row(row))
        report("NEW", f"DOE lists a file this checker does not recognize: {describe_row(row)}. "
                      "Check whether it is newer or corrected data")
    for release, row in known:
        check_calendar_years(release, row)

    newest_local = max(local) if local else None
    newest_listed = max(listed) if listed else None
    if newest_local:
        report("INFO", f"Newest release held: Crime{newest_local}SAS.zip "
                       f"(calendar {newest_local - 3}-{newest_local - 1})")
    else:
        report("NEW", "No DOE crime releases are held locally")

    if newest_listed and newest_local:
        if newest_listed > newest_local:
            report("NEW", f"DOE lists Crime{newest_listed}SAS.zip "
                          f"(calendar {newest_listed - 3}-{newest_listed - 1}), newer than what we hold")
        elif newest_listed < newest_local:
            report("INFO", f"DOE's listing shows SAS releases up to Crime{newest_listed}SAS.zip; "
                           f"Crime{newest_local}SAS.zip, which we hold, is checked against DOE's file server below")
    if newest_any and newest_any > max(newest_listed or 0, newest_local or 0):
        report("NEW", f"DOE's listing mentions a {newest_any} release that is not listed as "
                      f"Crime{newest_any}SAS.zip; check https://ope.ed.gov/campussafety/")

    known_years = [y for y in (newest_listed, newest_local, newest_any) if y]
    if known_years:
        probe_year = max(known_years) + 1
        probe = f"Crime{probe_year}SAS.zip"
        try:
            lacks = probe_release(probe, probe_year)
            if lacks is None:
                report("OK", f"{probe} does not exist yet (404)")
            elif lacks:
                report("NEW", f"{probe} exists upstream, but lacks crime files the transform expects "
                              f"({short(lacks)}); DOE may have renamed them, so the pipeline may need an update")
            else:
                report("NEW", f"{probe} exists upstream")
        except BadDownload as e:
            report("NEW", f"{probe} may exist upstream: DOE answers for it, but {e}; "
                          "check https://ope.ed.gov/campussafety/")
        except requests.RequestException as e:
            report("ERROR", f"Could not probe {probe}: {e}")

    # Does DATA_YEARS reach the newest calendar year we have or DOE offers?
    newest_release = max(y for y in (newest_listed, newest_local) if y) if (newest_listed or newest_local) else None
    if newest_release and newest_release - 1 > max(DATA_YEARS):
        report("NEW", f"Crime{newest_release}SAS.zip covers calendar {newest_release - 1}, but "
                      f"config.DATA_YEARS ends at {max(DATA_YEARS)}; extend DATA_YEARS and rebuild. Rates also "
                      "need NCES's fall enrollment for each year added: until NCES publishes it, the site "
                      "shows that year's counts without rates, and this check reports the year as WAITING "
                      f"(the NCES section below says whether fall {max(DATA_YEARS) + 1} enrollment is out)")

    if newest_listed and newest_listed == newest_local:
        newer = any(kind in ("NEW", "ERROR") for kind, _ in findings[first:])
        report("INFO" if newer else "OK", f"DOE's newest listed release is Crime{newest_listed}SAS.zip, same as ours")

    # Releases the pipeline reads, held or already published by DOE. Older
    # releases we hold cannot reach the site, so they are not downloaded.
    pipeline_releases = set(downloader.needed_release_years())
    first_used = min(pipeline_releases)
    unused = sorted(r for r in local if r < first_used)
    if unused:
        # Their extracted files can be deleted with them, except those that
        # the zips of the releases the pipeline uses also hold and those the
        # transform reads (reported below)
        with contextlib.redirect_stdout(io.StringIO()):
            keep = {path.name.lower() for path, *_ in transform.select_files(list(DATA_YEARS))[0]}
        for r in local:
            if r >= first_used:
                with contextlib.suppress(zipfile.BadZipFile, OSError):
                    keep |= set(ipeds_files.local_entries(local[r]))
        on_disk = {p.name.lower(): p.name for p in RAW_DIR.glob("*.sas7bdat")}
        extracted = set()
        for r in unused:
            with contextlib.suppress(zipfile.BadZipFile, OSError):  # unreadable: reported below
                extracted |= {on_disk[m] for m in ipeds_files.local_entries(local[r])
                              if m in on_disk and m not in keep}
        # Named by pattern only when every file on disk that matches it is listed
        matching = {s: {n for n in on_disk.values() if n.lower().endswith(f"{s}.sas7bdat")}
                    for s in sorted(release_suffix(r) for r in unused)}
        ends = [s for s, names in matching.items() if names and names <= extracted]
        by_suffix = sorted(n for n in extracted if n.lower().endswith(tuple(f"{s}.sas7bdat" for s in ends)))
        others = sorted(extracted - set(by_suffix))
        with_files = ""
        if extracted:
            named = []
            if by_suffix:
                named.append(f"the {len(by_suffix)} named {', '.join(f'*{s}.sas7bdat' for s in ends)}")
            if others:
                named.append(", ".join(others))
            with_files = (f", together with the {len(extracted)} .sas7bdat files extracted from them in "
                          f"{RAW_DIR}: {' and '.join(named)}")
        report("INFO", f"{short(local[r].name for r in unused)} held but not used by the pipeline (DATA_YEARS "
                       f"{min(DATA_YEARS)}-{max(DATA_YEARS)} reads releases {first_used} and later); "
                       f"not checked against DOE, and can be deleted{with_files}")
    needed = {r for r in pipeline_releases if newest_listed and r <= newest_listed}
    verified: dict[int, set[str]] = {}  # releases byte-identical to DOE's copy in this run -> members
    flagged: set[int] = set()  # releases already reported as NEW, CHANGED or ERROR
    for year in sorted(needed | {r for r in local if r >= first_used}):
        name = f"Crime{year}SAS.zip"
        held, is_needed = year in local, year in needed
        # Newer than anything DOE's listing names: DOE may serve it before listing it
        lags = bool(listed) and held and year not in listed and year > max(newest_listed or 0, newest_any or 0)
        lines = []
        if listed and year not in listed and not lags:
            lines.append(("ERROR", f"{name} is not on DOE's listing"))
        local_sha = ipeds_files.sha256_file(local[year]) if held else None
        try:
            upstream = doe_release(name, year, local_sha)
        except (requests.RequestException, BadDownload) as e:
            lines.append(("ERROR", f"Could not verify {name} against DOE: {e}"))
            upstream = "unknown"
        if upstream is None:
            if is_needed:
                lines.append(("ERROR", f"{name} returns 404 at DOE"))
            else:
                lines.append(("ERROR", f"We hold {name}, but DOE neither lists it nor serves it (404); "
                                       "find out where it came from before using it"))
        elif upstream != "unknown":
            sha, theirs = upstream
            if not held:
                lines.append(("NEW", f"{name} is offered by DOE but not held locally"))
            elif sha == local_sha:
                if lags:
                    lines.append(("INFO", f"{name} is not on DOE's listing yet, but DOE serves it "
                                          "byte-identical to ours (the listing lags)"))
                lines.append(("OK", f"{name} is byte-identical to DOE's (SHA-256)"))
                try:
                    verified[year] = set(ipeds_files.local_entries(local[year]))
                except (zipfile.BadZipFile, OSError):
                    pass  # reported as unreadable below
            else:
                if lags:
                    lines.append(("INFO", f"{name} is not on DOE's listing yet, but DOE serves it"))
                reissue = reissue_line(name, year, local[year], theirs)
                if reissue:
                    lines.append(reissue)
                elif year not in pipeline_releases:
                    lines.append(("CHANGED", f"{name} on disk is unreadable; re-download with "
                                             f"01_download_raw_data.py --release {year} --force"))
        file_ok = None
        if held and year in pipeline_releases:
            problems, file_ok = release_file_lines(year, local[year])
            lines += problems
        bad = any(kind in ("NEW", "CHANGED", "ERROR") for kind, _ in lines)
        if bad:
            flagged.add(year)
        for kind, message in lines:
            report("INFO" if kind == "OK" and bad else kind, message)
        if file_ok and not bad:
            report("OK", file_ok)

    # Extracted files that do not belong to any release we hold may still be read
    belongs = set()
    for year, p in sorted(local.items()):
        try:
            belongs |= set(ipeds_files.local_entries(p))
        except (zipfile.BadZipFile, OSError) as e:
            if year < first_used:
                report("INFO", f"{p.name} (not used by the pipeline) cannot be read ({e}); delete it")
    with contextlib.redirect_stdout(io.StringIO()):
        selected, _ = transform.select_files(list(DATA_YEARS))
    read = {path.name.lower() for path, *_ in selected}
    strays, old = [], []
    for p in sorted(RAW_DIR.glob("*.sas7bdat")):
        if p.name.lower() in belongs:
            continue
        parsed = transform.parse_filename(p.name)
        # Only a file the transform reads, or a crime file of a release the
        # pipeline uses (it could become a year's source), matters. Any other
        # file (an old release's, or one the transform does not recognize,
        # such as the hate and fire files) is never read.
        if p.name.lower() in read or (parsed and transform.release_year(parsed[2]) >= first_used):
            strays.append(p.name)
        else:
            old.append(p.name)
    if strays:
        report("CHANGED", f"{len(strays)} .sas7bdat file(s) in {RAW_DIR} are not from any release zip "
                          f"held: {short(strays)}; delete them or restore their release")
    if old:
        report("INFO", f"{len(old)} .sas7bdat file(s) in {RAW_DIR} are not from any release zip held "
                       f"({short(old)}); they are not used by the pipeline (the transform does not read "
                       "them), so they can be deleted")

    # Every file the transform reads must come from a release zip that matched DOE's copy in this run
    stray_names = {s.lower() for s in strays}
    unverified = []
    for path, *_ in selected:
        if path.name.lower() in stray_names:
            continue
        release = transform.release_year(transform.parse_filename(path.name)[2])
        if release not in flagged and path.name.lower() not in verified.get(release, ()):
            unverified.append(path.name)
    if unverified:
        one = len(unverified) == 1
        report("CHANGED", f"The transform would read {short(unverified)}, which {'is' if one else 'are'} "
                          "not in a release zip that matched DOE's copy in this run; "
                          f"delete {'it' if one else 'them'} or restore its release")


# --------------------------------------------------------------------------
# NCES IPEDS enrollment
# --------------------------------------------------------------------------

# Years that would be checked for WAITING (never held here) but whose NCES
# listing could not be read on this run: the answer for them is unknown and
# already reported as ERROR, and nothing can be rebuilt for them
UNCONFIRMED_YEARS: set[int] = set()


def read_listing(year: int):
    """
    NCES's listing for `year` as (links, conflicts, problem). links maps each
    file stem to its URL, or is None when NCES provably has no page for the
    year or the page could not be read; conflicts maps each stem linked at
    more than one address to its URLs; problem says why the page could not
    be read.
    """
    return ipeds_files.read_listing(year)


def waiting_years(listings: dict) -> set[int]:
    """
    The last years of DATA_YEARS whose fall enrollment file NCES has not
    published yet: NCES's listing for the year was read and neither links
    nor mentions the file (or NCES has no page for the year at all), and we
    have never had the file. Years are taken newest first and stop at the
    first one that does not qualify, so a file NCES removes from an older
    year is still an error. The rule is ipeds_files.waiting_years, which
    01b_download_ipeds.py uses too. Years that are not held but whose listing
    could not be read are put in UNCONFIRMED_YEARS.
    """
    waiting, unconfirmed = ipeds_files.waiting_years(DATA_YEARS, ipeds.pipeline_stem, listings.__getitem__)
    UNCONFIRMED_YEARS.clear()
    UNCONFIRMED_YEARS.update(unconfirmed)
    return waiting


def compare_ipeds_file(year: int, name: str, links: dict, conflicts: dict, used: bool) -> tuple[str, str]:
    """One NCES file compared with our copy, as (kind, message). Files the transforms do not read are INFO."""
    local = IPEDS_RAW_DIR / str(year) / f"{name}.zip"

    def problem(kind: str, message: str) -> tuple[str, str]:
        return (kind, message) if used else ("INFO", message + " (not read by the transforms)")

    key = name.upper()
    if key in conflicts:
        return compare_linked_copies(year, name, conflicts[key], problem)
    url = links.get(key)
    if url is None:
        if ipeds_files.listing_mentions(year, key):
            return problem("ERROR", f"{name}.zip appears on NCES's {year} listing, but its link could not be "
                                    "read; the page format may have changed")
        return problem("ERROR", f"{name}.zip is not on NCES's {year} listing")
    try:
        remote = ipeds_files.remote_entries(url)
    except (requests.RequestException, ValueError) as e:
        return problem("ERROR", f"Could not read {name}.zip at {url}: {e}")
    if remote is None:
        return problem("ERROR", f"NCES lists {name}.zip but {url} returns 404")
    if not local.exists():
        return problem("NEW", f"{name}.zip is published ({remote[1]:,} bytes) and not held locally: {url}")
    try:
        local_members = ipeds_files.local_entries(local)
    except (zipfile.BadZipFile, OSError) as e:
        return problem("CHANGED", f"{name}.zip on disk is unreadable ({e}); run 01b_download_ipeds.py --force")
    if local_members != remote[0]:
        return problem("CHANGED", f"{name}.zip differs upstream "
                                  f"({ipeds_files.describe_difference(local_members, remote[0])}): {url}")
    return "OK", f"{name}.zip identical to NCES's (every member's CRC-32 and size)"


def compare_linked_copies(year: int, name: str, urls, problem) -> tuple[str, str]:
    """
    NCES links one file name at several addresses. Our copy is current only
    if it equals every copy; if any differs, NCES may have corrected it.
    01b will not pick one, so the owner has to.
    """
    both = " and ".join(urls)
    unsure = (f"NCES's {year} listing links {name}.zip at more than one address ({both}) "
              "and cannot be checked")
    local = IPEDS_RAW_DIR / str(year) / f"{name}.zip"
    try:
        local_members = ipeds_files.local_entries(local) if local.exists() else None
    except (zipfile.BadZipFile, OSError):
        local_members = None
    differs = []
    for url in urls:
        try:
            remote = ipeds_files.remote_entries(url)
        except (requests.RequestException, ValueError) as e:
            return problem("ERROR", f"{unsure}: could not read {url} ({e})")
        if remote is None:
            return problem("ERROR", f"{unsure}: {url} returns 404")
        if local_members is None or local_members != remote[0]:
            differs.append(url)
    if not differs:
        return "OK", (f"{name}.zip identical to NCES's at every address its {year} listing links "
                      "(every member's CRC-32 and size)")
    if not local.exists():
        return problem("NEW", f"{name}.zip is published at more than one address ({both}) and not held "
                              "locally. Find out which copy is current and download it by hand; 01b will not choose")
    return problem("CHANGED", f"NCES's {year} listing links {name}.zip at more than one address ({both}), and "
                              f"{' and '.join(differs)} {'is' if len(differs) == 1 else 'are'} not our copy. "
                              "Find out which copy is current and download it by hand; 01b will not choose")


def check_ipeds() -> None:
    print("\nNCES IPEDS enrollment files")
    listings = {year: read_listing(year) for year in DATA_YEARS}
    WAITING_YEARS.clear()
    WAITING_YEARS.update(waiting_years(listings))
    for year in DATA_YEARS:
        links, conflicts, problem = listings[year]
        stem = ipeds.pipeline_stem(year)
        if year in WAITING_YEARS:
            why = (f"NCES has no {year} listing page yet" if links is None
                   else f"{stem.upper()}.zip is not on NCES's {year} listing yet")
            report("WAITING", f"Rates for {year} cannot be computed until NCES publishes fall {year} "
                              f"enrollment ({why}); the site shows counts without rates. Checked again on every run")
        elif problem:
            report("ERROR", problem)
        elif links is None:
            report("ERROR", f"NCES has no Complete Data Files page for {year}")

        lines, pipeline_line, version_lines = [], None, []
        if links is not None:  # otherwise the listing problem is already reported
            for name in ipeds.get_files_for_year(year):
                used = name.lower() == stem
                if used and year in WAITING_YEARS:
                    continue
                lines.append(compare_ipeds_file(year, name, links, conflicts, used))
                if used:
                    pipeline_line = len(lines) - 1
            # A final or corrected version could also come as a ZIP of its own (e.g. DRVEF2024_RV.zip)
            for other in ipeds_files.other_versions(stem, [*links, *conflicts]):
                UNRECOGNIZED.append(f"{other}.zip")
                url = links.get(other) or " and ".join(conflicts[other])
                version_lines.append(("NEW", f"{other}.zip is listed next to {stem.upper()}.zip; check whether it "
                                             "holds final or corrected data (the pipeline does not read it): "
                                             f"{url}"))
        if year in WAITING_YEARS or year in UNCONFIRMED_YEARS:
            csv_lines = []  # nothing to read yet, or unknown: the listing ERROR above covers it
        else:
            published_not_held = pipeline_line is not None and lines[pipeline_line][0] == "NEW"
            csv_lines = check_chosen_csv(year, published_not_held)
        csv_bad = any(kind in ("NEW", "CHANGED", "ERROR") for kind, _ in csv_lines)
        for i, (kind, message) in enumerate(lines):
            report("INFO" if kind == "OK" and i == pipeline_line and csv_bad else kind, message)
        for kind, message in csv_lines + version_lines:
            report(kind, message)

    next_year = max(DATA_YEARS) + 1
    links, conflicts, problem = read_listing(next_year)
    if problem:
        report("ERROR", problem)
        return
    for name in (f"DRVEF{next_year}", f"EF{next_year}A"):
        if name in conflicts:
            report("NEW", f"{name}.zip (fall {next_year} enrollment) is published: {' and '.join(conflicts[name])}")
        elif links and name in links:
            report("NEW", f"{name}.zip (fall {next_year} enrollment) is published: {links[name]}")
        elif links is not None and ipeds_files.listing_mentions(next_year, name):
            report("ERROR", f"{name}.zip appears on NCES's {next_year} listing, but its link could not be read; "
                            "the page format may have changed")
        else:
            report("OK", f"{name}.zip (fall {next_year} enrollment) is not on NCES's listing yet")


def check_chosen_csv(year: int, published_not_held: bool = False) -> list[tuple[str, str]]:
    """
    The CSV the transforms read must be the best one in the zip, extracted
    intact, and the zip must hold no other CSV, which could be NCES's data
    under a name the transforms do not know. Members are matched by file
    name, as 01b extracts them flat. Returns (kind, message) lines.
    """
    stem = ipeds.pipeline_stem(year)
    zip_name = f"{stem.upper()}.zip"
    zip_path = IPEDS_RAW_DIR / str(year) / zip_name
    chosen = ipeds_files.pipeline_csv(year, stem)
    try:
        members = ipeds_files.local_entries(zip_path) if zip_path.exists() else None
    except (zipfile.BadZipFile, OSError):
        members = None  # reported by the zip comparison above
    if chosen is None:
        if published_not_held:
            return []  # reported as NEW above; 01b_download_ipeds.py downloads it
        return [("CHANGED" if members else "ERROR", f"{year}: no {stem}.csv on disk for the transforms to read; "
                                                    "run 01b_download_ipeds.py")]
    final = chosen.name.lower().endswith("_rv.csv")
    lines = [("INFO", f"{year}: transforms read {chosen.name} ({'final' if final else 'provisional'})")]
    if members is None:
        return lines
    flat: dict[str, tuple[int, int]] = {}
    for member, entry in members.items():
        base = ipeds_files.member_file_name(member)
        if base in flat:
            return lines + [("ERROR", f"{year}: {zip_name} has two members named {base}; "
                                      "cannot tell which one the transforms read")]
        flat[base] = entry
    final_name = f"{stem}_rv.csv"
    other = sorted(n for n in flat if n.endswith(".csv") and n not in (f"{stem}.csv", final_name))
    if other:
        UNRECOGNIZED.extend(other)
        lines.append(("NEW", f"{year}: {zip_name} has {short(other)}, which the transforms do not read (they "
                             f"read {final_name}, or {stem}.csv until NCES publishes the final file). It may be "
                             "NCES's final or corrected data under a new name: check it, and update the pipeline "
                             "if it is"))
    if not final and final_name in flat:
        lines.append(("CHANGED", f"{year}: {zip_name} has the final {final_name} but it is not extracted; "
                                 "run 01b_download_ipeds.py"))
    expected = flat.get(chosen.name.lower())
    if expected is None:
        if final or final_name not in flat:  # otherwise 01b extracts the final file and then removes this one
            lines.append(("CHANGED", f"{year}: {chosen.name} is on disk but not in {zip_name}, and the transforms "
                                     f"read it. 01b keeps such a file: check NCES's {zip_name}, and delete "
                                     f"{chosen.name} by hand if it should no longer be used"))
    elif ipeds_files.crc32_file(chosen) != expected:
        lines.append(("CHANGED", f"{year}: {chosen.name} on disk differs from the copy in {zip_name}; "
                                 "run 01b_download_ipeds.py"))
    return lines


# --------------------------------------------------------------------------
# Build records: was each stage, and the published site, built from these files?
# --------------------------------------------------------------------------

STEPS = ("02", "02b", "02a", "03", "04", "05")  # run order
FEEDS = {"02": ("03", "04"), "02b": ("02a",), "02a": ("04",), "03": ("04",), "04": ("05",), "05": ()}
EF_TABLE = "dims/dim_enrollment_ef.parquet"
TIMESTAMPS = ("built_at", "generated_at")  # when a step ran; never part of what it built
SITE_DIR = JSON_DIR.relative_to(PROJECT_ROOT).as_posix()
SITE_RECORD = provenance.PUBLISHED_MANIFEST.relative_to(PROJECT_ROOT).as_posix()
AUDIT_COPY = JSON_DIR.parent / "audit.json"
AUDIT_REL = AUDIT_COPY.relative_to(PROJECT_ROOT).as_posix()
AUDIT_REPORT = QA_DIR / "comprehensive_audit.json"
LIVE_SITES = ("https://collegesafetydata.org", "https://collegesafetydata.com")
GIT_TIMEOUT = 60  # seconds for a git command that asks origin
LOCAL_ONLY = False  # --local-only: origin and the live sites are not asked
COMMITTED = False  # set when HEAD holds this build (site data, its record, audit.json) exactly as on disk
ON_MAIN = False  # set when origin's main branch has this build (as HEAD has it, or as on disk when HEAD lags)
LIVE_OK = False  # set when both live sites were fetched and serve this build


def rerun(steps) -> str:
    """Advice: re-run these steps and every step that uses their output, in run order."""
    need, todo = set(), list(steps)
    while todo:
        step = todo.pop()
        if step not in need:
            need.add(step)
            todo.extend(FEEDS[step])
    order = [s for s in STEPS if s in need]
    listed = order[0] if len(order) == 1 else ", ".join(order[:-1]) + " and " + order[-1]
    return f"Rebuild from step {order[0]}: run {listed}"


def steps_of(problems) -> set:
    return {step for step, _ in problems}


def texts(problems) -> str:
    return "; ".join(dict.fromkeys(text for _, text in problems))


def same_build(a, b) -> bool:
    """
    Whether two records of a step describe the same build: the same files
    read and written (by SHA-256), from the same raw files, by the same code.
    When the step ran (built_at, generated_at) does not count, so re-running
    a step that writes byte-identical files changes nothing.
    """
    def content(record):
        if isinstance(record, dict):
            return {k: content(v) for k, v in record.items() if k not in TIMESTAMPS}
        return record
    return content(a) == content(b)


def current_crime() -> dict:
    files, year_sources = transform.select_files(list(DATA_YEARS))
    return {
        "year_sources": {str(y): s for y, s in year_sources.items()},
        "files": provenance.file_records([f for f, *_ in files]),
    }


def current_enrollment() -> dict[str, dict]:
    out = {}
    for year in DATA_YEARS:
        chosen = ipeds_files.pipeline_csv(year, ipeds.pipeline_stem(year))
        if chosen is not None:
            out[str(year)] = {"file": chosen.name.lower(), "sha256": ipeds_files.sha256_file(chosen)}
    return out


def is_ef_year(year: int) -> bool:
    """Years whose FTE 02b computes from the EF file (the others come from DRVEF in 02a)."""
    return ipeds.pipeline_stem(year).startswith("ef")


def enrollment_differences(used, enrollment_now: dict, years) -> list[str]:
    """Years whose recorded enrollment file is not the one the transforms read now."""
    used = used if isinstance(used, dict) else {}
    stale = []
    for year in years:
        rec, now = used.get(str(year)), enrollment_now.get(str(year))
        if rec is None and now is None and (year in WAITING_YEARS or year in UNCONFIRMED_YEARS):
            continue  # not published yet (WAITING), or unknown (the listing ERROR): nothing to rebuild
        if not isinstance(rec, dict) or now is None:
            stale.append(f"{year} (missing)")
        elif str(rec.get("file", "")).lower() != now["file"]:
            stale.append(f"{year} ({rec.get('file')} -> {now['file']})")
        elif rec.get("sha256") != now["sha256"]:
            stale.append(f"{year} ({now['file']} content changed)")
    return stale


def input_problems(inputs, crime_now: dict, enrollment_now: dict) -> list[tuple[str, str]]:
    """Ways a build's input record differs from the raw files on disk now, by the step to re-run."""
    if not isinstance(inputs, dict):
        return [("02", "no record of its inputs")]
    problems = []

    crime = inputs.get("crime")
    if not crime:
        problems.append(("02", "no record of the crime files used (step 02)"))
    else:
        if crime.get("all_schools") is not True:
            problems.append(("02", "crime data was built for a subset of schools"))
        if crime.get("year_sources") != crime_now["year_sources"]:
            was, now = crime.get("year_sources") or {}, crime_now["year_sources"]
            diff = [f"{y}: {was.get(y)} -> {now.get(y)}" for y in sorted(set(was) | set(now)) if was.get(y) != now.get(y)]
            problems.append(("02", f"crime years come from different releases now ({short(diff)})"))
        files_was, files_now = crime.get("files") or {}, crime_now["files"]
        changed = sorted(f for f in set(files_was) | set(files_now) if files_was.get(f) != files_now.get(f))
        if changed:
            problems.append(("02", f"crime files differ from those used ({short(changed)})"))

    institutions = inputs.get("institutions")
    if not institutions:
        problems.append(("03", "no record of the institution table (step 03)"))
    elif crime and not same_build(institutions.get("crime"), crime):
        problems.append(("03", "the institution table (step 03) was built from a different crime build"))

    enrollment = inputs.get("enrollment")
    if not enrollment:
        problems.append(("02a", "no record of the enrollment files used (step 02a)"))
    else:
        stale = enrollment_differences(enrollment.get("inputs"), enrollment_now, DATA_YEARS)
        if stale:
            problems.append(("02a", f"enrollment differs for {short(stale)}"))
    return problems


def new_format(record) -> bool:
    return isinstance(record, dict) and isinstance(record.get("code"), dict)


def code_problems(step: str, record: dict) -> list[tuple[str, str]]:
    """The pipeline code and config a step's record was made with must be today's."""
    if not new_format(record):
        return [(step, f"step {step}'s record was made by an older pipeline that kept no code fingerprint")]
    was, now = record["code"], provenance.code_fingerprint(step)
    changed = sorted(n for n in set(was) | set(now) if was.get(n) != now.get(n))
    if changed:
        return [(step, f"step {step} was built by different pipeline code ({short(changed)} changed since)")]
    return []


def output_problems(step: str, record: dict) -> list[tuple[str, str]]:
    """Every curated file a step's record lists must be on disk, unchanged."""
    if not new_format(record):
        return []  # reported by code_problems
    outputs = record.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        return [(step, f"step {step}'s record lists no output files")]
    missing, changed = [], []
    for name, sha in sorted(outputs.items()):
        path = CURATED_DIR / name
        if not path.is_file():
            missing.append(name)
        elif provenance.file_sha256(path) != sha:
            changed.append(name)
    problems = []
    if changed:
        problems.append((step, f"{short(changed)} changed after step {step} wrote it"))
    if missing:
        problems.append((step, f"{short(missing)} that step {step} wrote is missing"))
    return problems


def read_problems(step: str, record: dict, writers: dict) -> list[tuple[str, str]]:
    """The curated files a step read must be exactly what the steps before it wrote."""
    if not new_format(record):
        return []  # reported by code_problems
    reads = record.get("read")
    if not isinstance(reads, dict):
        return [(step, f"step {step}'s record lists no files read")]
    bad = []
    for name, sha in sorted(reads.items()):
        writer = writers.get(provenance.writer_of(name))
        if isinstance(writer, dict) and (writer.get("outputs") or {}).get(name) != sha:
            bad.append(name)
    if bad:
        return [(step, f"step {step} read {short(bad)}, which is not what the step before it last wrote")]
    return []


def local_problems(rec: dict, crime_now: dict, enrollment_now: dict) -> list[tuple[str, str]]:
    """Problems in data/curated up to step 03, by the step to re-run."""
    crime, ef, enrollment, institutions = rec["02"], rec["02b"], rec["02a"], rec["03"]
    problems = input_problems({"crime": crime, "institutions": institutions, "enrollment": enrollment},
                              crime_now, enrollment_now)
    if crime:
        problems += code_problems("02", crime) + output_problems("02", crime)
    ef_years = [y for y in DATA_YEARS if is_ef_year(y)]
    if ef is None:
        if ef_years or EF_TABLE in ((enrollment or {}).get("read") or {}):
            problems.append(("02b", "no record of the fall enrollment files used (step 02b)"))
    else:
        problems += code_problems("02b", ef) + output_problems("02b", ef)
        stale = enrollment_differences(ef.get("inputs"), enrollment_now, ef_years)
        if stale:
            problems.append(("02b", f"fall enrollment (step 02b) differs for {short(stale)}"))
    if enrollment:
        problems += (code_problems("02a", enrollment) + output_problems("02a", enrollment)
                     + read_problems("02a", enrollment, {"02b": ef}))
    if institutions:
        problems += (code_problems("03", institutions) + output_problems("03", institutions)
                     + read_problems("03", institutions, {"02": crime}))
    return problems


def aggs_problems(rec: dict) -> list[tuple[str, str]]:
    """Problems with the aggregates (step 04) in data/curated."""
    aggs = rec["04"]
    if aggs is None:
        return [("04", "no record of the aggregates (step 04)")]
    problems = []
    if aggs.get("all_schools") is not True:
        problems.append(("04", "the aggregates were built for a subset of schools"))
    inputs_now = {"crime": rec["02"], "institutions": rec["03"], "enrollment": rec["02a"]}
    if not same_build(aggs.get("inputs"), inputs_now):
        problems.append(("04", "the aggregates were built before the latest 02, 02b, 02a or 03 run"))
    problems += (code_problems("04", aggs) + output_problems("04", aggs)
                 + read_problems("04", aggs, {"02": rec["02"], "03": rec["03"], "02a": rec["02a"]}))
    return problems


def git_ignored(paths: list[str]) -> set[str]:
    """
    The paths (relative to the project, "/" separated) that git ignores and
    does not track, so they are never committed or published. Empty when git
    cannot tell (no git, or not a checkout): then nothing is left out.
    """
    if not paths:
        return set()
    try:
        r = subprocess.run(["git", "-C", str(PROJECT_ROOT), "check-ignore", "-z", "--stdin"],
                           input="\0".join(paths), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return set()
    if r.returncode not in (0, 1):  # 1: none of them is ignored
        return set()
    return {p for p in r.stdout.split("\0") if p}


def site_extras(outputs: dict) -> tuple[list[str], list[str]]:
    """
    Files in frontend/public/data that step 05 did not write, leaving out
    those git ignores (.DS_Store, Thumbs.db: never committed or published),
    split by 05's own rule (05_generate_json.owns) into the files 05 removes
    when it runs again and the files it leaves in place.
    """
    on_disk = sorted(p.relative_to(JSON_DIR).as_posix() for p in JSON_DIR.rglob("*") if p.is_file())
    extra = [n for n in on_disk if n not in outputs and n != provenance.PUBLISHED_MANIFEST.name]
    ignored = git_ignored([f"{SITE_DIR}/{n}" for n in extra])
    extra = [n for n in extra if f"{SITE_DIR}/{n}" not in ignored]
    owns = importlib.import_module("05_generate_json").owns
    return [n for n in extra if owns(n)], [n for n in extra if not owns(n)]


def foreign_site_files(published) -> list[str]:
    """Files in frontend/public/data that step 05 neither wrote nor removes (and git does not ignore)."""
    outputs = published.get("outputs") if new_format(published) else None
    if not isinstance(outputs, dict) or not outputs:
        return []  # the site line reports the record
    return site_extras(outputs)[1]


def site_file_problems(published: dict) -> list[tuple[str, str]]:
    """
    frontend/public/data must hold exactly the files step 05 wrote, unchanged.
    Files 05 does not make are reported on their own (foreign_site_files),
    since running 05 again does not remove them.
    """
    if not new_format(published):
        return []  # reported by code_problems
    outputs = published.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        return [("05", "the site's record lists no site files")]
    on_disk = {p.relative_to(JSON_DIR).as_posix(): p for p in JSON_DIR.rglob("*") if p.is_file()}
    on_disk.pop(provenance.PUBLISHED_MANIFEST.name, None)
    missing = sorted(set(outputs) - set(on_disk))
    extra = site_extras(outputs)[0]
    changed = sorted(n for n in set(outputs) & set(on_disk)
                     if provenance.site_file_sha256(on_disk[n]) != outputs[n])
    parts = []
    if changed:
        parts.append(f"{len(changed)} changed since step 05 wrote them ({short(changed, 3)})")
    if missing:
        parts.append(f"{len(missing)} missing ({short(missing, 3)})")
    if extra:
        parts.append(f"{len(extra)} not written by step 05 ({short(extra, 3)}; running 05 removes them)")
    return [("05", "site files differ from what step 05 wrote: " + ", ".join(parts))] if parts else []


def site_problems(published: dict, crime_now: dict, enrollment_now: dict) -> list[tuple[str, str]]:
    """Whether the site data and its record hold up on their own: files, code and raw inputs."""
    problems = []
    if published.get("all_schools") is not True:
        problems.append(("05", "the site data was generated for a subset of schools"))
    problems += code_problems("05", published) + site_file_problems(published)
    aggs = published.get("aggregates")
    if not isinstance(aggs, dict):
        return problems + [("04", "its record has no record of the aggregates (step 04)")]
    if aggs.get("all_schools") is not True:
        problems.append(("04", "the aggregates it was generated from cover a subset of schools"))
    inputs = aggs.get("inputs") if isinstance(aggs.get("inputs"), dict) else {}
    problems += input_problems(inputs, crime_now, enrollment_now)
    chain = {"04": aggs, "02": inputs.get("crime"), "03": inputs.get("institutions"),
             "02a": inputs.get("enrollment")}
    enrollment = chain["02a"]
    if isinstance(enrollment, dict) and EF_TABLE in (enrollment.get("read") or {}):
        chain["02b"] = enrollment.get("ef")
        if not isinstance(chain["02b"], dict):
            problems.append(("02b", "its record has no record of step 02b"))
    for step, record in chain.items():
        if isinstance(record, dict):
            problems += code_problems(step, record)
    problems += read_problems("05", published, chain) + read_problems("04", aggs, chain)
    for step in ("03", "02a"):
        if isinstance(chain[step], dict):
            problems += read_problems(step, chain[step], chain)
    return problems


def stray_facts() -> list[str]:
    """
    Parquet data in data/curated/facts besides step 02's incidents.parquet,
    by the rule steps 03, 04, 06 and 07 use (find_stray_facts): a .parquet
    file, or a folder named incidents or *.parquet, which DuckDB could read
    as facts. Other files (.DS_Store, notes) cannot reach any output.
    """
    facts = CURATED_DIR / "facts"
    if not facts.is_dir():
        return []
    stray, folders = [], [facts]
    while folders:
        folder = folders.pop()
        for p in folder.iterdir():
            name = p.name.lower()
            if p.is_dir():
                if name == "incidents" or name.endswith(".parquet"):
                    stray.append(p.relative_to(facts).as_posix() + "/")
                else:
                    folders.append(p)
            elif name.endswith(".parquet") and p != facts / "incidents.parquet":
                stray.append(p.relative_to(facts).as_posix())
    return sorted(stray)


def no_local_build(rec: dict) -> bool:
    if any(rec[s] is not None for s in ("02", "02b", "02a", "03", "04")):
        return False
    return not (CURATED_DIR.is_dir() and any(CURATED_DIR.rglob("*.parquet")))


def read_audit(path: Path) -> dict | None:
    """07's report at `path`, or None if it is missing or not a JSON object."""
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return audit if isinstance(audit, dict) else None


def audited_build(audit) -> dict:
    """What a 07 report says it audited (empty for a report made by an older 07)."""
    build = audit.get("audited_build") if isinstance(audit, dict) else None
    return build if isinstance(build, dict) else {}


def utc_time(value) -> datetime | None:
    """A generated_at that names its time zone (07 writes UTC, e.g. 2026-11-09T16:20:01Z), else None."""
    try:
        made = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return made if made.tzinfo is not None else None


def curated_outputs(published: dict) -> dict:
    """The curated files the site data was built from, by SHA-256, as its record lists them."""
    aggs = published.get("aggregates")
    if not isinstance(aggs, dict):
        return {}
    inputs = aggs.get("inputs") if isinstance(aggs.get("inputs"), dict) else {}
    out = {}
    for record in (*inputs.values(), aggs):
        if isinstance(record, dict) and isinstance(record.get("outputs"), dict):
            out.update(record["outputs"])
    return out


def check_audit(published) -> None:
    """
    frontend/public/audit.json is copied by hand from 07's report. It must be
    07's audit of exactly this site data: 07 records the SHA-256 of the
    build_inputs.json it audited and of the curated files it read.
    """
    if published is None:
        return  # the site data itself is reported
    where = AUDIT_REL
    source = AUDIT_REPORT.relative_to(PROJECT_ROOT).as_posix()
    site = provenance.site_file_sha256(provenance.PUBLISHED_MANIFEST)
    latest = read_audit(AUDIT_REPORT)
    latest_is_this_build = audited_build(latest).get("site_record_sha256") == site
    if latest_is_this_build:
        advice = f"07 has already audited this build: copy {source} to {where}"
    else:
        advice = f"Re-run 07_comprehensive_audit.py and copy its report ({source}) to {where}"
    if not AUDIT_COPY.is_file():
        report("CHANGED", f"{where}, the audit the Methodology page offers, is missing. {advice}")
        return
    copy = read_audit(AUDIT_COPY)
    build = audited_build(copy)
    if copy is None:
        report("CHANGED", f"{where} is not a readable 07 report. {advice}")
        return
    if "site_record_sha256" not in build:
        report("CHANGED", f"{where} does not say which build it audited (an older 07 made it). {advice}")
        return
    if build["site_record_sha256"] != site:
        report("CHANGED", f"{where} is the audit of another build, not of the site data in {SITE_DIR} "
                          f"(the SHA-256 of {SITE_RECORD} it audited differs). {advice}")
        return
    built_from = curated_outputs(published)
    read = build.get("curated_sha256") if isinstance(build.get("curated_sha256"), dict) else {}
    other = sorted(name for name, sha in read.items() if built_from.get(name) != sha)
    if other:
        report("CHANGED", f"{where} audited curated files that the site data was not built from "
                          f"({short(other)}). {advice}")
        return
    if latest_is_this_build and provenance.text_sha256(AUDIT_REPORT) != provenance.text_sha256(AUDIT_COPY):
        made, newer = utc_time(copy.get("generated_at")), utc_time(latest.get("generated_at"))
        if made is None or newer is None or newer > made:
            report("CHANGED", f"07 has a newer report than {where}. Copy {source} to {where}")
            return
    report("OK", f"{where} is 07's audit of exactly this site data")


def check_build() -> None:
    print("\nBuild records")
    lock = provenance.lock_report()
    if lock:
        report("ERROR", lock)
        return
    crime_now = current_crime()
    enrollment_now = current_enrollment()
    rec = {step: provenance.read(path) for step, path in provenance.RECORDS.items()}
    published = rec["05"]
    site = None if published is None else site_problems(published, crime_now, enrollment_now)

    strays = stray_facts()
    if strays:
        report("CHANGED", f"data/curated/facts holds parquet data that step 02 did not write: {short(strays)}. "
                          "Steps 03, 04, 06 and 07 stop while it is there: delete it (move it outside "
                          "data/curated to keep it)")
    foreign = foreign_site_files(published)
    if foreign:
        report("CHANGED", f"{SITE_DIR} holds {len(foreign)} file(s) that step 05 does not make: {short(foreign)}. "
                          "Running 05 does not remove them, and git add -A would publish them with the "
                          f"site: delete them or move them out of {SITE_DIR}")

    if no_local_build(rec):
        everything = rerun(["02", "02b"])
        if published is None:
            report("CHANGED", f"No local build in data/curated, and the site data has no build record "
                              f"({SITE_RECORD} is missing). {everything}")
        elif site:
            report("CHANGED", f"No local build in data/curated, and the site data is out of date: "
                              f"{texts(site)}. {everything}")
        else:
            report("INFO", "No local build in data/curated (a fresh clone or a new machine); the site data "
                           "matches the current DOE and NCES files and pipeline code. To change the site "
                           f"data, build locally first. {everything}")
    else:
        local = local_problems(rec, crime_now, enrollment_now)
        if local:
            report("CHANGED", f"Local build in data/curated is out of date: {texts(local)}. "
                              f"{rerun(steps_of(local))}")
        else:
            report("OK", "Local build in data/curated (steps 02 to 03) was made from exactly the current "
                         "raw files and pipeline code, and each file in it is the one its step wrote")
        aggs = aggs_problems(rec)
        if aggs:
            report("CHANGED", f"The aggregates (step 04) are out of date: {texts(aggs)}. "
                              f"{rerun(steps_of(local + aggs))}")
        elif local:
            report("INFO", "The aggregates (step 04) match the files they were built from, but those are "
                           "out of date: rebuild them with the local build as the line above says")
        else:
            report("OK", "The aggregates (step 04) were built from the current local build by the current code")

        upstream = steps_of(local + aggs) | {"05"}
        if published is None:
            report("CHANGED", f"The site data has no build record ({SITE_RECORD} is missing): it was "
                              "generated before build records existed, or step 05 did not finish. "
                              f"{rerun(upstream)}")
        elif site:
            report("CHANGED", f"The site data in frontend/public/data is out of date: {texts(site)}. "
                              f"{rerun(upstream)}")
        elif not local and not aggs and not same_build(published.get("aggregates"), rec["04"]):
            report("CHANGED", "The site data was generated from different aggregates than the current "
                              f"ones (step 04 ran again after step 05). {rerun(['05'])}")
        else:
            report("OK", "The site data in frontend/public/data was built from exactly the current DOE and "
                         "NCES files and pipeline code, and every site file is the one step 05 wrote"
                         + (" (apart from the files named above)" if foreign else ""))

    check_audit(published)
    if provenance.lock_report():
        report("ERROR", "A pipeline step started while the build records were being checked; "
                        "run this check again when it has finished")


# --------------------------------------------------------------------------
# Release: is this build committed, on origin's main, and served by the live sites?
# --------------------------------------------------------------------------

DISK_BLOBS: dict[str, str] | None = None  # set by check_commit: git blob id of each file of this build on disk
MAIN_SHA: str | None = None  # set by check_main: the commit origin's main branch is at, when this checkout has it
REMOVED_UNSURE = False  # set when the list of removed site files may be incomplete (shallow clone)
PROGRESS_EVERY = 500  # files fetched from a live site between progress lines
FETCH_WORKERS = 6  # files fetched from a live site at the same time
RETRY_AFTER_MAX = 30  # longest wait (seconds) for a host's Retry-After before fetching again
PRINT_LOCK = threading.Lock()  # the threads that fetch host files print whole lines, one at a time


def git(*args: str, stdin: str | None = None, timeout: float | None = None, codes=(0,)) -> str:
    """Run git in the project and return its output; RuntimeError when it fails."""
    import os
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")  # never wait for a password
    try:
        r = subprocess.run(["git", "-C", str(PROJECT_ROOT), *args], input=stdin, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {args[0]} did not answer within {timeout} seconds") from None
    if r.returncode not in codes:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {args[0]} failed")
    return r.stdout


def say(line: str) -> None:
    """Print one whole line, also from the threads that fetch host files."""
    with PRINT_LOCK:
        print(line, flush=True)


def fetch_live(url: str, attempts: int = 3) -> requests.Response:
    """
    GET with backoff on network errors, HTTP 429 and HTTP 5xx, waiting at least
    as long as a numeric Retry-After asks (up to RETRY_AFTER_MAX seconds).
    Safe to call from several threads.
    """
    delay = 3
    for attempt in range(1, attempts + 1):
        wait = delay
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "collegesafetydata-etl",
                                                       "Cache-Control": "no-cache"})
            if r.status_code < 500 and r.status_code != 429:
                return r
            error = requests.HTTPError(f"HTTP {r.status_code} from {url}")
            after = str(r.headers.get("Retry-After") or "").strip()
            if after.isdigit():
                wait = max(delay, min(int(after), RETRY_AFTER_MAX))
        except (requests.ConnectionError, requests.Timeout) as e:
            error = e
        if attempt < attempts:
            say(f"  (attempt {attempt} failed: {error}; retrying in {wait}s)")
            time.sleep(wait)
            delay *= 3
    raise error


def head_blobs(ref: str = "HEAD") -> dict[str, str]:
    """Every file a commit (HEAD unless named) holds in frontend/public/data, and audit.json: path -> blob id."""
    blobs = {}
    for entry in git("ls-tree", "-r", "-z", ref, "--", SITE_DIR, AUDIT_REL).split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            if meta.split()[1] == "blob":
                blobs[path] = meta.split()[2]
    return blobs


def worktree_blobs(paths: list[str]) -> dict[str, str]:
    """The blob id `git add` would store for each file on disk (.gitattributes and autocrlf applied)."""
    if not paths:
        return {}
    ids = git("hash-object", "--stdin-paths", stdin="".join(p + "\n" for p in paths)).split()
    if len(ids) != len(paths):
        raise RuntimeError(f"git hash-object returned {len(ids)} ids for {len(paths)} files")
    return dict(zip(paths, ids))


def hidden_from_git(absent: list[str], differs: list[str]) -> str:
    """Advice for files whose state git status does not show: ignored, or flagged in the index."""
    notes = []
    ignored = sorted(git_ignored(absent))
    if ignored:
        it = "it" if len(ignored) == 1 else "them"
        notes.append(f"Git ignores {short(ignored, 3)}, so git add -A leaves {it} out: add {it} with git add -f, "
                     "or remove the ignore rule (git check-ignore -v <file> names it)")
    tags = {e[2:]: e[0] for e in git("ls-files", "-v", "-z", "--", SITE_DIR, AUDIT_REL).split("\0") if len(e) > 2}
    flagged = [p for p in differs if tags.get(p, "H") == "S" or tags.get(p, "H").islower()]
    if flagged:
        notes.append(f"The index marks {short(flagged, 3)} assume-unchanged or skip-worktree, so git status "
                     "does not show the change: clear that with git update-index --no-assume-unchanged "
                     "--no-skip-worktree <file>, then commit")
    return "".join(f". {n}" for n in notes)


def check_commit(published: dict) -> None:
    """HEAD must hold the site files the record lists, the record and audit.json as on disk, and no other site file."""
    global COMMITTED, DISK_BLOBS
    outputs = published.get("outputs") if isinstance(published.get("outputs"), dict) else {}
    expected = [f"{SITE_DIR}/{n}" for n in sorted(outputs)] + [SITE_RECORD, AUDIT_REL]
    head = head_blobs()
    disk = worktree_blobs([p for p in expected if (PROJECT_ROOT / p).is_file()])
    gone = [p for p in expected if p not in disk]
    DISK_BLOBS = None if gone else disk  # an incomplete build on disk is compared with nothing
    absent = [p for p in disk if p not in head]
    differs = [p for p in disk if p in head and head[p] != disk[p]]
    wanted = set(expected)
    stale = sorted(p for p in head if p not in wanted)
    if gone or absent or differs:
        parts = []
        if differs:
            parts.append(f"{len(differs)} {'differs' if len(differs) == 1 else 'differ'} from HEAD "
                         f"({short(differs, 3)})")
        if absent:
            parts.append(f"{len(absent)} {'is' if len(absent) == 1 else 'are'} not in HEAD ({short(absent, 3)})")
        if gone:
            parts.append(f"{len(gone)} {'is' if len(gone) == 1 else 'are'} not on disk "
                         f"({short(gone, 3)}; see Build records)")
        # origin's main is checked next (see check_main), except with --local-only
        report("CHANGED", f"This build is not committed as it is on disk: {', '.join(parts)}. Commit all of it "
                          f"(git add -A {SITE_DIR} {AUDIT_REL})" + (" and release it to main" if LOCAL_ONLY else "")
                          + hidden_from_git(absent, differs))
    if stale:
        report("CHANGED", f"HEAD holds {len(stale)} file(s) in {SITE_DIR} that are not part of this build "
                          f"({short(stale, 3)}), so the live sites would still publish them: remove them with "
                          "git rm (git rm --cached keeps the file on disk) and commit")
    if not (gone or absent or differs or stale):
        COMMITTED = True
        report("OK", f"HEAD ({git('rev-parse', '--short', 'HEAD').strip()}) holds this build exactly as it is on "
                     f"disk: the {len(outputs)} site files its record lists, {SITE_RECORD} and {AUDIT_REL}, and "
                     f"nothing else in {SITE_DIR}")


def has_commit(sha: str) -> bool:
    return bool(git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", codes=(0, 1)).strip())


def release_ids(ref: str) -> tuple[str, ...]:
    """The tree id of frontend/public/data and the blob id of audit.json in a commit ('' when absent)."""
    return tuple(git("rev-parse", "--verify", "--quiet", f"{ref}:{path}", codes=(0, 1)).strip()
                 for path in (SITE_DIR, AUDIT_REL))


def build_differences(ref: str) -> list[str]:
    """
    The files in frontend/public/data and audit.json in which commit `ref`
    differs from this build: from HEAD when HEAD holds it (or there is no
    build on disk to compare with), otherwise from the build on disk.
    """
    if COMMITTED or DISK_BLOBS is None:
        return [p for p in git("diff", "--name-only", "-z", ref, "HEAD", "--", SITE_DIR,
                               AUDIT_REL).split("\0") if p]
    theirs = head_blobs(ref)
    return sorted(p for p in set(DISK_BLOBS) | set(theirs) if DISK_BLOBS.get(p) != theirs.get(p))


def check_main() -> None:
    """
    origin's main branch, which both live sites deploy, must have this build:
    HEAD's site data and audit.json, or the build on disk when HEAD does not
    hold it (then merging HEAD into main would not release it).
    """
    global ON_MAIN, MAIN_SHA
    try:
        heads = {}
        for line in git("ls-remote", "origin", "refs/heads/main", "refs/heads/staging",
                        timeout=GIT_TIMEOUT).splitlines():
            sha, _, ref = line.partition("\t")
            heads[ref.strip().removeprefix("refs/heads/")] = sha.strip()
    except (OSError, RuntimeError) as e:
        report("ERROR", f"Could not ask origin which commit its main branch is at ({e}). Check the network and "
                        "that the git remote 'origin' is set, then run this check again")
        return
    main_sha = heads.get("main")
    if not main_sha:
        report("ERROR", "origin has no main branch, so what the live sites deploy is unknown")
        return
    # When HEAD does not hold the build on disk, main is compared with the build on disk
    on_disk = not COMMITTED and DISK_BLOBS is not None
    main = f"origin's main branch (commit {main_sha[:7]})"
    try:
        if not has_commit(main_sha):
            report("ERROR", f"Cannot verify what origin's main branch holds: it is at commit {main_sha[:7]}, "
                            "which this checkout does not have. Run git fetch origin, then run this check again")
            return
        MAIN_SHA = main_sha
        here = release_ids("HEAD")
        like_head = release_ids(main_sha) == here
        if like_head and not on_disk:
            ON_MAIN = COMMITTED
            report("OK", f"{main} has " + ("this build" if COMMITTED else "the same site data and audit.json as HEAD"))
            return
        changed = [] if like_head else build_differences(main_sha)
        if on_disk and not like_head and not changed:  # main has the build on disk; HEAD lags it
            ON_MAIN = True
            report("OK", f"{main} already has this build exactly as it is on disk, so nothing needs merging into "
                         "main for it: it is HEAD that lags (see the line above). Do not merge HEAD into main as "
                         "it is, which could bring back older files; commit the build here, or update this "
                         "checkout from origin/main")
            return
        staging = heads.get("staging")
        on_staging = bool(staging) and has_commit(staging) and (
            not build_differences(staging) if on_disk else release_ids(staging) == here)
    except (OSError, RuntimeError) as e:
        report("ERROR", f"Could not compare origin's main branch with {'the build on disk' if on_disk else 'HEAD'}: "
                        f"{e}")
        return
    if like_head:  # HEAD, and so main, does not hold the build on disk
        report("CHANGED", f"{main} has the same site data and audit.json as HEAD, so it does not have this build "
                          "either: commit the build first (see the line above), then release it to main (via "
                          "staging)")
    elif on_disk:
        report("CHANGED", f"{main} does not have this build: {len(changed)} file(s) differ from the build on disk "
                          f"({short(changed, 3)}). HEAD does not hold it either, so commit the build first (see the "
                          "line above), then release it to main (via staging)")
    elif COMMITTED:
        report("CHANGED", f"{main} does not have this build yet: {len(changed)} file(s) differ from HEAD "
                          f"({short(changed, 3)}). Merge it into main (via staging) and push")
    else:
        report("CHANGED", f"{main} does not have the site data and audit.json HEAD has: {len(changed)} file(s) "
                          f"differ from HEAD ({short(changed, 3)}). The build on disk could not be compared with "
                          "it (see above)")
    if on_staging:
        report("INFO", f"origin's staging branch (commit {staging[:7]}) has it: check the staging build "
                       "(https://staging.collegesafetydata-public.pages.dev), then merge staging into main")


def text_sha(data: bytes) -> str:
    """SHA-256 of text with CRLF read as LF: the hashing provenance.site_file_sha256 uses."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def release_removed(outputs: dict) -> list[str]:
    """
    The files under frontend/public/data that are not part of this build but
    that the git history ever held: every path a commit reachable from HEAD,
    origin's main (MAIN_SHA) or any commit this checkout saw main at (its
    origin/main reflog, which keeps rewritten or rolled-back tips) added,
    changed or deleted, plus the files those tips hold. Named as in a build
    record; the record itself is left out. A live site must serve none of them.
    """
    tips = {git("rev-parse", "HEAD").strip()}
    if MAIN_SHA:
        tips.add(MAIN_SHA)
    seen = git("reflog", "show", "--format=%H", "refs/remotes/origin/main", "--", codes=(0, 128)).split()
    tips |= {sha for sha in seen if has_commit(sha)}
    tips = sorted(tips)
    paths = set(git("log", "-m", "--full-history", "--no-renames", "--format=", "--name-only", "-z",
                    *tips, "--", SITE_DIR).split("\0"))
    for tip in tips:
        paths |= set(git("ls-tree", "-r", "--name-only", "-z", tip, "--", SITE_DIR).split("\0"))
    prefix = SITE_DIR + "/"
    record = SITE_RECORD[len(prefix):]
    names = {p.strip()[len(prefix):] for p in paths if p.strip().startswith(prefix)}
    return sorted(n for n in names if n not in outputs and n != record)


def host_advice() -> str:
    """What to do about a live site that does not serve this build, given what the git checks showed."""
    if ON_MAIN:
        return ("origin's main branch already has this build, so the site has not deployed it: check that "
                "host's deploy of main (it may still be running, or have failed)")
    if COMMITTED:
        return "Release HEAD to main (via staging)"
    return "Commit this build (site data and audit.json together) and release it to main"


def fetch_files(host: str, paths: list[str]) -> tuple[list[tuple[int, str, str, bool]], str | None]:
    """
    Fetch {host}/{path} for each of `paths`, FETCH_WORKERS at a time. Returns
    (HTTP status, content type, text_sha of the body, whether the body is an
    HTML page) for each, in the order of `paths`, and None; or, at the first
    of them (in that order) that could not be fetched or answered other than
    HTTP 200, 404 or 410, the results before it and what went wrong, and the
    files not fetched yet are not asked for. The threads only fetch: results
    are read, and progress printed, here and in order, so every run prints
    the same lines.
    """
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    def fetch(path: str) -> tuple[int, str, str, bool]:
        r = fetch_live(f"{host}/{path}")
        start = r.content[:64].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        return (r.status_code, r.headers.get("Content-Type", ""), text_sha(r.content),
                start.startswith((b"<!doctype html", b"<html")))

    states = []
    todo, queued = iter(paths), deque()
    pool = ThreadPoolExecutor(max_workers=FETCH_WORKERS)

    def queue_next() -> None:
        path = next(todo, None)
        if path is not None:
            queued.append((path, pool.submit(fetch, path)))
    try:
        for _ in range(2 * FETCH_WORKERS):
            queue_next()
        while queued:
            path, job = queued.popleft()
            queue_next()
            try:
                state = job.result()
            except requests.RequestException as e:
                return states, f"Could not reach {host}/{path}: {e}"
            if state[0] not in (200, 404, 410):
                return states, f"{host}/{path} returned HTTP {state[0]}, so what the live site serves is unknown"
            states.append(state)
            if len(states) % PROGRESS_EVERY == 0 and len(states) < len(paths):
                say(f"  ({len(states):,} of {len(paths):,} files fetched from {host})")
        return states, None
    finally:
        pool.shutdown(wait=True, cancel_futures=True)  # what is still queued is never fetched


def check_host(host: str, published: dict, audit_sha: str | None, sample: list[str], what: str = "",
               removed: list[str] | None = None, gone: str = "") -> bool:
    """
    Whether the live site at `host` serves this build: its record, audit.json
    and the site files `sample` (described as `what` in messages), and none
    of the files `removed` (named as in a build record and described as
    `gone`), which are not part of this build.
    """
    what = what or f"{len(sample)} sampled site files"
    name = provenance.PUBLISHED_MANIFEST.name
    url = f"{host}/data/{name}"
    try:
        r = fetch_live(url)
    except requests.RequestException as e:
        report("ERROR", f"Could not reach {url}: {e}")
        return False
    if r.status_code not in (200, 404):
        report("ERROR", f"{url} returned HTTP {r.status_code}, so what the live site serves is unknown")
        return False
    live = None
    content_type = r.headers.get("Content-Type", "")
    if r.status_code == 200 and "json" in content_type.lower():
        try:
            live = r.json()
        except ValueError:
            live = None
    if not isinstance(live, dict):
        report("CHANGED", f"The live site at {host} is not serving this build: it has no /data/{name} "
                          f"(HTTP {r.status_code}, {content_type or 'no content type'}). {host_advice()}")
        return False
    if live != published:
        report("CHANGED", f"The live site at {host} is not serving this build: its /data/{name} is "
                          f"from another build (generated {live.get('generated_at')}). {host_advice()}")
        return False
    wanted = [("audit.json", audit_sha)] + [(f"data/{n}", published["outputs"][n]) for n in sample]
    dropped = [f"data/{n}" for n in removed or ()]
    states, failure = fetch_files(host, [path for path, _ in wanted] + dropped)
    if failure:
        report("ERROR", failure)
        return False
    missing, differs, served = [], [], []
    for (path, sha), (status, content_type, body_sha, _) in zip(wanted, states):
        if status in (404, 410) or (status == 200 and "html" in content_type.lower()):
            missing.append(path)
        elif sha is None or body_sha != sha:
            differs.append(path)
    for path, (status, content_type, _, page) in zip(dropped, states[len(wanted):]):
        if status == 200 and not ("html" in content_type.lower() and page):  # 404, 410 or the HTML page: gone
            served.append(path)
    still = f"still serves {len(served)} file(s) that are not part of this build ({short(served, 3)})"
    if missing or differs:
        parts = []
        if differs:
            parts.append(f"{len(differs)} {'differs' if len(differs) == 1 else 'differ'} from this build "
                         f"({short(differs, 3)})")
        if missing:
            parts.append(f"{len(missing)} {'is' if len(missing) == 1 else 'are'} missing, answered with the "
                         f"site's HTML page, 404 or 410 ({short(missing, 3)})")
        if audit_sha is None:
            parts.append(f"there is no local {AUDIT_REL} to compare its audit.json with")
        report("CHANGED", f"The live site at {host} serves this build's record, but not all of its files: of "
                          f"audit.json and {what}, {'; '.join(parts)}" + (f"; and it {still}" if served else "")
                          + f". {host_advice()}")
        return False
    if served:
        report("CHANGED", f"The live site at {host} serves this build's record, and its audit.json and {what} are "
                          f"this build's, but it {still}. {host_advice()}")
        return False
    gone = gone or f"the {len(dropped):,} file(s) that are not part of this build"
    report("OK", f"The live site at {host} serves this build: its /data/{name}, audit.json and {what} "
                 f"are this build's" + (f", and {gone} are gone from it" if dropped else ""))
    return True


def check_release() -> None:
    global COMMITTED, ON_MAIN, LIVE_OK, DISK_BLOBS, MAIN_SHA, REMOVED_UNSURE
    COMMITTED = ON_MAIN = LIVE_OK = REMOVED_UNSURE = False
    DISK_BLOBS = MAIN_SHA = None
    print("\nRelease")
    published = provenance.read(provenance.PUBLISHED_MANIFEST)
    git_ok = False
    try:
        top = git("rev-parse", "--show-toplevel").strip()
        if not Path(top).samefile(PROJECT_ROOT):
            raise RuntimeError(f"{PROJECT_ROOT} is inside the git checkout {top}, not at its top")
        git_ok = True
        if published is None:
            report("INFO", f"Whether this build is committed was not checked: there is no {SITE_RECORD}")
        else:
            check_commit(published)
    except (OSError, RuntimeError) as e:
        report("ERROR", f"Could not run git to see whether the site data is committed: {e}")

    if LOCAL_ONLY:
        report("INFO", "origin's main branch and the live sites were not checked (--local-only)")
        return
    if git_ok:
        check_main()
    if published is None:
        report("INFO", f"The live sites were not checked: there is no local {SITE_RECORD} to compare them with")
        return
    outputs = published.get("outputs") if isinstance(published.get("outputs"), dict) else {}
    files = sorted(outputs)  # every file, every run: a partial deploy could miss any of them
    what = f"all {len(files):,} site files"
    removed = None
    if git_ok:
        try:
            removed = release_removed(outputs)
            if git("rev-parse", "--is-shallow-repository").strip() != "false":
                REMOVED_UNSURE = True
                report("INFO", "This checkout is a shallow clone, so the list of site files earlier builds held "
                               "(which must be gone from the live sites) may be incomplete. Run "
                               "git fetch --unshallow origin to check all of them")
        except (OSError, RuntimeError) as e:
            report("ERROR", f"Could not list the site files earlier builds held: {e}")
    if removed is None:
        REMOVED_UNSURE = True
    report("INFO", f"Each live site that serves this build's record is asked for all {len(files):,} site files "
                   "it lists" + (f" and the {len(removed):,} file(s) earlier builds held that are not part of it"
                                 if removed else "") + ", which takes a few minutes")
    gone = f"the {len(removed):,} file(s) earlier builds held that are not part of this one" if removed else ""
    audit_sha = provenance.text_sha256(AUDIT_COPY) if AUDIT_COPY.is_file() else None
    serving = sum(check_host(host, published, audit_sha, files, what, removed, gone) for host in LIVE_SITES)
    LIVE_OK = serving == len(LIVE_SITES)


def main(argv: list[str] | None = None) -> int:
    global LOCAL_ONLY
    parser = argparse.ArgumentParser(description="Check for newer DOE and NCES data, and whether the "
                                                 "site data was built from it and released.")
    parser.add_argument("--local-only", action="store_true",
                        help="do not ask origin or the live sites (the release check uses no network)")
    LOCAL_ONLY = parser.parse_args([] if argv is None else argv).local_only

    print("=" * 60)
    print("Checking upstream sources for newer data")
    print("=" * 60)
    for check in (check_doe, check_ipeds, check_build, check_release):
        try:
            check()
        except Exception as e:  # never let an unexpected failure read as "current"
            report("ERROR", f"{check.__name__} stopped unexpectedly: {e!r}")
            traceback.print_exc()

    kinds = [k for k, _ in findings]
    print("\n" + "=" * 60)
    if "ERROR" in kinds:
        print(f"RESULT: {kinds.count('ERROR')} check(s) could not be completed, so the answer is UNKNOWN.")
        print_waiting()
        return 2
    if "NEW" in kinds or "CHANGED" in kinds:
        print(f"RESULT: {kinds.count('NEW')} new and {kinds.count('CHANGED')} changed or stale item(s).")
        print("Next: 01b_download_ipeds.py refreshes IPEDS files on its own. For a new or re-issued")
        print("      DOE release, run 01_download_raw_data.py --release <year> --force. Then rebuild")
        print("      as the lines above say, commit the site data together with audit.json, and")
        print("      release them to main.")
        if UNRECOGNIZED:
            print("      First look at the file(s) this checker does not recognize: the pipeline may")
            print("      need a change to read them.")
        print_waiting()
        return 1
    print("RESULT: everything the pipeline uses matches the newest upstream data,")
    print("        and the site data was built from exactly those files.")
    if COMMITTED:
        print("        This build (site data, its record and audit.json) is committed in HEAD.")
    if ON_MAIN:
        print("        origin's main branch has it.")
    if LIVE_OK:
        print("        Both live sites serve it (record, audit.json and every site file checked).")
    if LOCAL_ONLY:
        print("        origin's main branch and the live sites were not checked (--local-only).")
    unchecked = [what for what, done in (("whether it is committed", COMMITTED),
                                         ("origin's main branch", ON_MAIN or LOCAL_ONLY),
                                         ("the live sites", LIVE_OK or LOCAL_ONLY),
                                         ("that files earlier builds held are gone from the live sites "
                                          "(the git history is incomplete)",
                                          not REMOVED_UNSURE or LOCAL_ONLY or not LIVE_OK)) if not done]
    if unchecked:
        print(f"        Not verified: {', '.join(unchecked)}.")
    print_waiting()
    return 0


def print_waiting() -> None:
    """The WAITING note that goes with every result: data that does not exist upstream yet."""
    if WAITING_YEARS:
        years = ", ".join(str(y) for y in sorted(WAITING_YEARS))
        those = "that year" if len(WAITING_YEARS) == 1 else "those years"
        print(f"        WAITING: NCES has not published fall enrollment for {years} yet, so the site")
        print(f"        shows counts without rates for {those}. Nothing can be rebuilt for it now.")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        traceback.print_exc()
        sys.exit(2)
