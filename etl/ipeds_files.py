"""
Shared helpers for IPEDS enrollment files: the part that decides which file
the enrollment transforms read and how. It is part of the 02b and 02a code
fingerprints (provenance.STAGE_CODE).

- Which CSV the pipeline reads: the final revised file ({stem}_rv.csv) when it
  exists, otherwise the provisional one (pipeline_csv), and whether that CSV
  is the right copy from its ZIP (pipeline_csv_problem).
- Which ZIP member names can be extracted (member_name_problem), and the file
  each member is extracted to.
- CRC-32 and SHA-256 of files, and a record of which input files the
  enrollment build used, so a stale build can be detected.
- The HTTP session and settings for every NCES request, and the listing
  page's address. 01b's downloads and ipeds_listing both use them from here,
  so replacing the session (as a test does) covers every request.

NCES's listing (where each file is published, the WAITING rule, other
versions of a file) and remote ZIP reads are in ipeds_listing.py, which is not
part of any code fingerprint because it cannot change what the transforms
read. Its names are available here too (see __getattr__), so callers can use
ipeds_files.listed_files and the like.

Used by 00_check_for_updates.py, 01b_download_ipeds.py, ipeds_listing.py,
provenance.py and the 02a/02b enrollment transforms.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
import zlib
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import PROJECT_ROOT

IPEDS_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ipeds"
DATAFILES_PAGE = "https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year={year}"
BUILD_MANIFEST_PATH = PROJECT_ROOT / "data" / "curated" / "dims" / "enrollment_inputs.json"
EF_BUILD_MANIFEST_PATH = PROJECT_ROOT / "data" / "curated" / "dims" / "enrollment_ef_inputs.json"

# Uncompressed transfer: with gzip, both government servers drop Content-Length.
HEADERS = {"Accept-Encoding": "identity", "User-Agent": "collegesafetydata-etl"}
TIMEOUT = 120
TAIL_BYTES = 65536

ZipEntries = dict[str, tuple[int, int]]  # lower-case member name -> (CRC-32, uncompressed size)


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def __getattr__(name: str):
    """
    A name of ipeds_listing.py (listed_files, read_listing, waiting_years,
    remote_entries, ...), which 00 and 01b use as ipeds_files.<name>. That
    module is imported on first use, so the transforms never load it.
    """
    if not name.startswith("__"):
        import ipeds_listing
        if name in vars(ipeds_listing):
            return vars(ipeds_listing)[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def local_entries(zip_path: Path) -> ZipEntries:
    with zipfile.ZipFile(zip_path) as zf:
        return {i.filename.lower(): (i.CRC, i.file_size) for i in zf.infolist() if not i.is_dir()}


def has_final_member(entries: ZipEntries) -> bool:
    return any(name.endswith("_rv.csv") for name in entries)


_WINDOWS_BAD_CHARS = frozenset('<>:"/\\|?*') | frozenset(chr(c) for c in range(32))
_WINDOWS_RESERVED = frozenset(["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
                              + [f"{dev}{n}" for dev in ("COM", "LPT")
                                 for n in [*"0123456789", chr(0xB9), chr(0xB2), chr(0xB3)]])


def member_file_name(member: str) -> str:
    """The file name a ZIP member is extracted to: members are extracted flat, by file name."""
    return member.rsplit("/", 1)[-1]


def member_name_problem(members: Iterable[str]) -> str | None:
    """
    Why a ZIP's members cannot all be extracted flat into one folder on
    Windows, or None if they can. Pass the raw member names (directory entries
    are ignored). Refused: a file name that is empty, '.' or '..', contains a
    character Windows does not allow (such as ':' or a backslash), ends with a
    dot or space, or is a reserved device name (CON, NUL, COM1 ...); and two
    members that Windows would store as the same file.
    """
    seen: dict[str, str] = {}
    for member in members:
        if member.endswith("/"):
            continue
        name = member_file_name(member)
        why = None
        if name in ("", ".", ".."):
            why = "has no usable file name"
        elif any(c in _WINDOWS_BAD_CHARS for c in name):
            why = "has a character Windows does not allow in file names"
        elif name[-1] in ". ":
            why = "ends with a dot or a space"
        elif name.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_RESERVED:
            why = "is a reserved device name on Windows"
        if why:
            return f"member {member!r} {why}"
        key = name.rstrip(". ").lower()  # Windows ignores case and trailing dots and spaces
        if key in seen:
            return f"members {seen[key]!r} and {member!r} would be extracted to the same file"
        seen[key] = member
    return None


def pipeline_csv_problem(year: int, stem: str, zip_path: Path) -> str | None:
    """
    Why the CSV the transforms read for `stem` (see pipeline_csv) is not the
    right copy from zip_path, or None when it is. It must exist, be a member
    of the ZIP (matched by file name, as members are extracted flat), match
    that member's CRC-32 and size, and be {stem}_rv.csv whenever the ZIP has
    that final file. Raises zipfile.BadZipFile or OSError when the ZIP cannot
    be read.
    """
    members = {member_file_name(m): v for m, v in local_entries(zip_path).items()}
    chosen = pipeline_csv(year, stem)
    renamed = "NCES may have renamed its files, so the pipeline needs an update"
    if chosen is None:
        return (f"no {stem}.csv or {stem}_rv.csv on disk for the transforms to read "
                f"({zip_path.name} has {', '.join(sorted(members)) or 'no files'}); {renamed}")
    name = chosen.name.lower()
    if name not in members:
        return f"the transforms read {chosen.name}, which is not in {zip_path.name}; {renamed}"
    if crc32_file(chosen) != members[name]:
        return f"{chosen.name} on disk differs from the copy in {zip_path.name}; run 01b_download_ipeds.py"
    final = f"{stem}_rv.csv".lower()
    if name != final and final in members:
        return (f"{zip_path.name} has the final {final} but the transforms read the provisional "
                f"{chosen.name}; run 01b_download_ipeds.py")
    return None


def pipeline_csv(year: int, stem: str) -> Path | None:
    """
    The CSV the transforms read for `stem` (e.g. 'drvef2023', 'ef2015a'): the
    final revised file ({stem}_rv.csv) when present, otherwise the provisional
    {stem}.csv. Case-insensitive, because NCES ships both _rv and _RV.
    """
    year_dir = IPEDS_RAW_DIR / str(year)
    if not year_dir.is_dir():
        return None
    by_name = {p.name.lower(): p for p in year_dir.glob("*.csv")}
    return by_name.get(f"{stem}_rv.csv".lower()) or by_name.get(f"{stem}.csv".lower())


def crc32_file(path: Path) -> tuple[int, int]:
    """(CRC-32, size) of a file, comparable with a ZIP member's CRC and size."""
    crc = 0
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
    return crc & 0xFFFFFFFF, size


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_record(path: Path) -> dict:
    return {"file": path.name, "final": path.name.lower().endswith("_rv.csv"), "sha256": sha256_file(path)}


def write_build_manifest(path: Path, inputs: dict[int, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {str(year): rec for year, rec in sorted(inputs.items())},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_build_manifest(path: Path) -> dict[int, dict] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(year): rec for year, rec in payload.get("inputs", {}).items()}
