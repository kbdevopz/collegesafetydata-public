"""
Build provenance: what each stage of the pipeline read and wrote, carried
forward stage by stage up to the published site data. The lock that keeps
two steps from running at the same time is in pipeline_lock.py (its names are
also available here).

  02_transform_to_parquet.py      -> data/curated/facts/crime_inputs.json
  02b_transform_ef_enrollment.py  -> data/curated/dims/enrollment_ef_inputs.json
  02a_transform_enrollment.py     -> data/curated/dims/enrollment_inputs.json  (carries 02b's)
  03_build_dimensions.py          -> data/curated/dims/institution_inputs.json (carries 02's)
  04_create_aggregates.py         -> data/curated/aggs/build_inputs.json       (carries 02's, 02a's, 03's)
  05_generate_json.py             -> frontend/public/data/build_inputs.json    (carries 04's)

Each record holds:
  - the raw DOE and NCES files used (02, 02b, 02a: CRC-32 or SHA-256),
  - "read": the SHA-256 of each curated file the stage read (03, 04, 05, and
    02a for 02b's table), which must be what the stage before it wrote,
  - "outputs": the SHA-256 of each file the stage wrote. For 05 that is every
    site file, by its path under frontend/public/data,
  - "code": the SHA-256 of the pipeline code and config that made it
    (see STAGE_CODE). Comments, docstrings, blank lines, trailing spaces
    and line endings do not count (see code_sha256).

How a stage uses this:
  - Its entry point runs under run_locked(), which holds the pipeline lock
    (data/curated/.pipeline.lock) for the whole run. A second step started
    meanwhile stops with an error.
  - Before it reads anything, it records the identity of its inputs (a
    Snapshot, or the CRCs and hashes 02/02b/02a take before reading each raw
    file). A Snapshot refuses a curated file that is not exactly what the
    stage before it wrote.
  - It deletes its own record, builds, and only then writes a new record. Just
    before that it checks its inputs again: if any changed while it ran, it
    stops with an error and writes no record.

00_check_for_updates.py re-hashes every file the records name and compares
the records with the raw files, the code and each other, so a stage that was
skipped, failed, or ran on other inputs or code shows up as out of date. The
last record is published with the site, so anyone can see which DOE and NCES
files the live numbers come from.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import tokenize
import warnings
from datetime import datetime, timezone
from pathlib import Path

from config import CURATED_DIR, JSON_DIR, PROJECT_ROOT
import ipeds_files
# The pipeline lock is kept out of the code fingerprint; the stages and the
# checker use these names from here.
from pipeline_lock import (  # noqa: F401
    LOCK_PATH, LockError, LockHeld, acquire_lock, lock_report, release_lock, run_locked,
)

ETL_DIR = Path(__file__).resolve().parent
# Reference data committed with the code (01c_extract_ipeds_official.ps1 writes it, 02b reads it)
REFERENCE_DIR = ETL_DIR / "reference"

CRIME_MANIFEST = CURATED_DIR / "facts" / "crime_inputs.json"
EF_MANIFEST = ipeds_files.EF_BUILD_MANIFEST_PATH
ENROLLMENT_MANIFEST = ipeds_files.BUILD_MANIFEST_PATH
INSTITUTION_MANIFEST = CURATED_DIR / "dims" / "institution_inputs.json"
AGGS_MANIFEST = CURATED_DIR / "aggs" / "build_inputs.json"
PUBLISHED_MANIFEST = JSON_DIR / "build_inputs.json"

RECORDS = {
    "02": CRIME_MANIFEST,
    "02b": EF_MANIFEST,
    "02a": ENROLLMENT_MANIFEST,
    "03": INSTITUTION_MANIFEST,
    "04": AGGS_MANIFEST,
    "05": PUBLISHED_MANIFEST,
}

# Pipeline files whose content decides each step's output. 00, 06 and 07 only
# check, so they are not here, nor are pipeline_lock.py and ipeds_listing.py,
# which cannot change what a step writes.
STAGE_CODE = {
    "02": ("02_transform_to_parquet.py", "config.py", "provenance.py"),
    "02b": ("02b_transform_ef_enrollment.py", "config.py", "ipeds_files.py", "provenance.py"),
    "02a": ("02a_transform_enrollment.py", "config.py", "ipeds_files.py", "provenance.py"),
    "03": ("03_build_dimensions.py", "campus_identity.py", "config.py", "ipeds_files.py", "provenance.py"),
    "04": ("04_create_aggregates.py", "config.py", "provenance.py"),
    "05": ("05_generate_json.py", "config.py", "provenance.py"),
}

# The step that writes each curated file (paths relative to data/curated)
CURATED_WRITERS = {
    "facts/incidents.parquet": "02",
    "dims/raw_institutions.parquet": "02",
    "dims/campus_year_sources.parquet": "02",
    "dims/older_release_counts.parquet": "02",
    "dims/campus_names.parquet": "02",
    "dims/dim_enrollment_ef.parquet": "02b",
    "dims/dim_enrollment.parquet": "02a",
    "dims/dim_institution.parquet": "03",
    "dims/dim_offense.parquet": "03",
    "dims/campus_id_links.parquet": "03",
}

# Records each step reads, and where 04's record keeps the ones it used
UPSTREAM = {"02a": ("02b",), "03": ("02",), "04": ("02", "03", "02a"), "05": ("04",)}
AGGS_INPUT_KEYS = {"02": "crime", "03": "institutions", "02a": "enrollment"}


class RecordError(RuntimeError):
    """A build record cannot be written truthfully, so none is written."""


# --------------------------------------------------------------------------
# Hashes and records
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def invalidate(path: Path) -> None:
    """Delete a stage's record before the stage rewrites its output."""
    path.unlink(missing_ok=True)


def read(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes."""
    return ipeds_files.sha256_file(path)


def text_sha256(path: Path) -> str:
    """SHA-256 of a text file with CRLF line endings read as LF, so a
    checkout that converts line endings does not change it."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


site_file_sha256 = text_sha256  # site files are JSON text


def reference_name(path: Path) -> str:
    """A reference file's name in records: its path relative to etl/ (e.g. reference/x.csv)."""
    return path.relative_to(ETL_DIR).as_posix()


def reference_sha256(path: Path) -> str:
    """Checksum of a reference file, as text (a checkout that converts line endings does not change it)."""
    return text_sha256(path)


# Since Python 3.12 an f-string is several tokens (3.14 adds t-strings); before, one STRING token
_STRING_STARTS = {getattr(tokenize, n, None) for n in ("FSTRING_START", "TSTRING_START")} - {None}
_STRING_ENDS = {getattr(tokenize, n, None) for n in ("FSTRING_END", "TSTRING_END")} - {None}
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

_Span = tuple[tuple[int, int], tuple[int, int]]  # (start, end), each (row, column) as tokenize gives them


def _docstring_spans(text: str, strings: list[_Span]) -> list[_Span]:
    """
    Where each module, class and function docstring in `text` starts and
    ends. A docstring is the first statement of such a body when that
    statement is a plain string. Positions come from the parsed source, whose
    columns count UTF-8 bytes, and are turned into tokenize's character
    columns. `strings` holds every STRING token; a docstring that does not
    start and end on token boundaries is not returned, so it counts as code.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # e.g. SyntaxWarning for an invalid escape sequence
        tree = ast.parse(text)
    lines = text.split("\n")
    starts = {start for start, _ in strings}
    ends = {end for _, end in strings}

    def position(row: int, offset: int) -> tuple[int, int]:
        return row, len(lines[row - 1].encode("utf-8")[:offset].decode("utf-8", "ignore"))

    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, _DOCSTRING_OWNERS) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            doc = first.value
            start, end = position(doc.lineno, doc.col_offset), position(doc.end_lineno, doc.end_col_offset)
            if start in starts and end in ends:
                spans.append((start, end))
    return spans


def code_sha256(path: Path) -> str:
    """
    SHA-256 of a Python file's code. Comments, docstrings (the string that
    opens a module, class or function), blank lines, trailing spaces and CRLF
    line endings do not count; all other code does, every other string
    included. A line that ends inside a string is kept exactly, since that
    text is part of the string. The source is hashed, not its tokens, which
    differ between Python versions; docstrings are found by their position in
    the parsed source. A file that cannot be read as Python is hashed as text.
    """
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    try:
        text = raw.decode("utf-8-sig")
        comments = {}      # row -> column where the row's comment starts
        strings = []       # (start, end) of each STRING token
        in_string = set()  # rows whose line end lies inside a string other than a docstring
        opened = []        # rows where the f-strings still open started
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.start[1]
            elif tok.type == tokenize.STRING:
                strings.append((tok.start, tok.end))
            elif tok.type in _STRING_STARTS:
                opened.append(tok.start[0])
            elif tok.type in _STRING_ENDS:
                in_string.update(range(opened.pop(), tok.end[0]))
        docstrings = _docstring_spans(text, strings)
    except (ValueError, SyntaxError, tokenize.TokenError, IndexError, RecursionError):
        return hashlib.sha256(raw).hexdigest()
    for start, end in strings:
        if not any(a <= start and end <= b for a, b in docstrings):
            in_string.update(range(start[0], end[0]))
    cuts = {}  # row -> (from, to) columns of docstring text on it; to None: up to the line end
    for (row1, col1), (row2, col2) in docstrings:
        for row in range(row1, row2 + 1):
            cuts.setdefault(row, []).append((col1 if row == row1 else 0, col2 if row == row2 else None))
    lines = []
    for row, line in enumerate(text.split("\n"), start=1):
        if row in comments:
            line = line[:comments[row]]
        for col1, col2 in sorted(cuts.get(row, ()), key=lambda cut: cut[0], reverse=True):
            line = line[:col1] + (line[col2:] if col2 is not None else "")
        if row not in in_string:
            line = line.rstrip()
            if not line:
                continue
        lines.append(line)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def code_fingerprint(step: str) -> dict[str, str]:
    """SHA-256 of each pipeline file that decides `step`'s output (see code_sha256)."""
    return {name: code_sha256(ETL_DIR / name) for name in STAGE_CODE[step]}


def curated_name(path: Path) -> str:
    return path.relative_to(CURATED_DIR).as_posix()


def site_name(path: Path) -> str:
    return path.relative_to(JSON_DIR).as_posix()


def writer_of(name: str) -> str:
    """Step that writes a curated file (name relative to data/curated)."""
    if name.startswith("aggs/"):
        return "04"
    return CURATED_WRITERS.get(name, "?")


def file_records(files: list[Path]) -> dict[str, dict]:
    """CRC-32 and size of each file, keyed by lower-case name."""
    records = {}
    for p in sorted(files, key=lambda q: q.name.lower()):
        crc, size = ipeds_files.crc32_file(p)
        records[p.name.lower()] = {"crc32": crc, "size": size}
    return records


def _outputs(paths) -> dict[str, str]:
    out = {}
    for p in paths:
        if not p.is_file():
            raise RecordError(f"{p} was not written, so no record was written")
        out[curated_name(p)] = file_sha256(p)
    return out


def _input_sha256(path: Path) -> str:
    """SHA-256 of an input file; a file another program holds open is an error."""
    try:
        return file_sha256(path)
    except OSError as e:
        raise RecordError(f"Could not read {path}: {e}. If another program (sync, backup or "
                          "antivirus) has it open, close it and run this step again.") from None


def current_inputs() -> dict:
    """The crime, institution and enrollment records as they are now on disk."""
    return {
        "crime": read(CRIME_MANIFEST),
        "institutions": read(INSTITUTION_MANIFEST),
        "enrollment": read(ENROLLMENT_MANIFEST),
    }


# --------------------------------------------------------------------------
# Inputs: what a stage is about to read, checked again before its record
# --------------------------------------------------------------------------

class Snapshot:
    """
    The curated files a step is about to read (SHA-256) and the records of the
    steps that wrote them, taken before the step reads anything. It refuses a
    file that is not exactly what its writer's record says it wrote.
    `optional` files may be missing (02a without 02b's table); a missing file
    is then not read and not recorded.
    """

    def __init__(self, step: str, files: list[Path], optional: tuple[Path, ...] = ()):
        self.step = step
        self.paths = list(files)
        self.records = {s: read(RECORDS[s]) for s in UPSTREAM[step]}
        self.files = {}
        problems = []
        for p in self.paths:
            name = curated_name(p)
            if not p.is_file():
                if p in optional:
                    continue
                writer = writer_of(name)
                problems.append(f"{p} is missing. Run {writer}, then this step.")
                continue
            self.files[name] = _input_sha256(p)
            problems += self._vouch(name)
        if problems:
            raise RecordError(f"Step {step} cannot start:\n  " + "\n  ".join(problems))

    def _writer_record(self, writer: str) -> dict | None:
        if writer in self.records:
            return self.records[writer]
        # 05 reads 03's tables: they must be the ones 04 was built from
        aggs = self.records.get("04")
        if aggs is None:
            return None
        return (aggs.get("inputs") or {}).get(AGGS_INPUT_KEYS.get(writer, ""))

    def _vouch(self, name: str) -> list[str]:
        writer = writer_of(name)
        record = self._writer_record(writer)
        what = f"data/curated/{name}"
        if record is None:
            if writer not in self.records:
                return [f"step 04 has no record of the step {writer} files it used, so {what} "
                        f"cannot be checked. Run {writer} and 04 again, then this step."]
            return [f"step {writer} has no record (it has not run, or did not finish), so {what} "
                    f"cannot be checked. Run {writer}, then this step."]
        wrote = (record.get("outputs") or {}).get(name)
        if wrote is None:
            return [f"step {writer}'s record does not list {what} (it was made by an older "
                    f"pipeline, or that run did not write it). Run {writer} again, then this step."]
        if wrote != self.files[name]:
            if writer in self.records:
                return [f"{what} is not the file step {writer} last wrote. Run {writer} again, "
                        "then this step."]
            return [f"{what} changed after step 04 used it. Run 04 again, then this step."]
        return []

    def verify(self) -> None:
        """Raise RecordError if an input or upstream record changed since the snapshot."""
        changed = []
        for s, rec in self.records.items():
            if read(RECORDS[s]) != rec:
                changed.append(f"the step {s} record ({RECORDS[s].name})")
        for p in self.paths:
            name = curated_name(p)
            now = _input_sha256(p) if p.is_file() else None
            if now != self.files.get(name):
                changed.append(f"data/curated/{name}")
        if changed:
            raise RecordError(
                f"These inputs changed while step {self.step} ran: {', '.join(changed)}. "
                f"Its output may mix old and new data, so no record was written. "
                f"Run {self.step} again.")


def _check_csv_inputs(step: str, inputs: dict[int, dict]) -> None:
    """The IPEDS CSVs recorded before reading must still be the ones the transform reads."""
    changed = []
    for year, rec in sorted(inputs.items()):
        name = str(rec["file"])
        stem = name.lower().removesuffix(".csv").removesuffix("_rv")
        chosen = ipeds_files.pipeline_csv(year, stem)
        if chosen is None or chosen.name.lower() != name.lower():
            changed.append(f"{year} ({name} is no longer the file to read)")
        elif ipeds_files.sha256_file(chosen) != rec["sha256"]:
            changed.append(f"{year} ({name} changed)")
    if changed:
        raise RecordError(f"These enrollment files changed while step {step} ran: {', '.join(changed)}. "
                          f"No record was written. Run {step} again.")


# --------------------------------------------------------------------------
# Writing each stage's record
# --------------------------------------------------------------------------

def write_crime_manifest(year_sources: dict[int, list[str]], files: list[Path], all_schools: bool,
                         read_before: dict[str, dict], outputs: list[Path],
                         campus_years: dict[str, dict[str, int]], defects: list[dict]) -> None:
    """
    Called by 02 after saving its output. `read_before` is file_records(files)
    taken before any SAS file was read. `year_sources` lists, for each year,
    the releases that cover it (newest first); `campus_years` how many
    campus-years of each year were taken from each release (the release of
    each one is in dims/campus_year_sources.parquet); `defects` the known
    DOE file defects 02 corrected and for how many campus-years.
    """
    if file_records(files) != read_before:
        now = file_records(files)
        changed = sorted(n for n in set(now) | set(read_before) if now.get(n) != read_before.get(n))
        raise RecordError(f"These SAS files changed while step 02 ran: {', '.join(changed)}. "
                          "No record was written. Run 02 again.")
    _write(CRIME_MANIFEST, {
        "built_at": _now(),
        "all_schools": all_schools,
        "year_sources": {str(y): list(s) for y, s in sorted(year_sources.items())},
        "campus_year_sources": campus_years,
        "known_defects": defects,
        "files": read_before,
        "outputs": _outputs(outputs),
        "code": code_fingerprint("02"),
    })


def write_ef_manifest(inputs: dict[int, dict], outputs: list[Path], reference: dict[str, str]) -> None:
    """
    Called by 02b. `inputs` holds each CSV's hash, `reference` each reference
    file's (reference_sha256, by reference_name), both taken before reading.
    """
    _check_csv_inputs("02b", inputs)
    changed = sorted(name for name, sha in reference.items()
                     if not (ETL_DIR / name).is_file() or reference_sha256(ETL_DIR / name) != sha)
    if changed:
        raise RecordError(f"{', '.join(changed)} changed while step 02b ran. No record was written. "
                          "Run 02b again.")
    _write(EF_MANIFEST, {
        "built_at": _now(),
        "inputs": {str(year): rec for year, rec in sorted(inputs.items())},
        "reference": dict(sorted(reference.items())),
        "outputs": _outputs(outputs),
        "code": code_fingerprint("02b"),
    })


def write_enrollment_manifest(drvef_inputs: dict[int, dict], built_years: set[int],
                              snapshot: Snapshot, outputs: list[Path]) -> None:
    """
    Called by 02a. The years taken from 02b's table carry 02b's record of
    their CSVs; `snapshot` holds that table and record as they were before
    02a read them.
    """
    snapshot.verify()
    _check_csv_inputs("02a", drvef_inputs)
    ef_record = snapshot.records["02b"] if snapshot.files else None
    ef_inputs = {int(y): rec for y, rec in ((ef_record or {}).get("inputs") or {}).items()}
    inputs = {y: rec for y, rec in {**ef_inputs, **drvef_inputs}.items() if y in built_years}
    _write(ENROLLMENT_MANIFEST, {
        "built_at": _now(),
        "inputs": {str(year): rec for year, rec in sorted(inputs.items())},
        "read": snapshot.files,
        "ef": ef_record,
        "outputs": _outputs(outputs),
        "code": code_fingerprint("02a"),
    })


def other_input_records(paths: list[Path]) -> dict[str, str]:
    """SHA-256 of input files outside data/curated (raw downloads, etl/reference), by project-relative path."""
    return {p.resolve().relative_to(PROJECT_ROOT).as_posix(): _input_sha256(p) for p in sorted(paths)}


def write_institution_manifest(snapshot: Snapshot, outputs: list[Path],
                               other_inputs: dict[str, str] | None = None) -> None:
    """
    Called by 03 after building its tables from the files in `snapshot` and
    `other_inputs` (other_input_records, taken before reading them).
    """
    snapshot.verify()
    other_inputs = other_inputs or {}
    changed = sorted(name for name, sha in other_inputs.items()
                     if not (PROJECT_ROOT / name).is_file() or _input_sha256(PROJECT_ROOT / name) != sha)
    if changed:
        raise RecordError(f"{', '.join(changed)} changed while step 03 ran. No record was written. "
                          "Run 03 again.")
    _write(INSTITUTION_MANIFEST, {
        "built_at": _now(),
        "crime": snapshot.records["02"],
        "read": snapshot.files,
        "other_inputs": dict(sorted(other_inputs.items())),
        "outputs": _outputs(outputs),
        "code": code_fingerprint("03"),
    })


def write_aggs_manifest(all_schools: bool, snapshot: Snapshot, outputs: list[Path]) -> None:
    """Called by 04 after building aggregates from the files in `snapshot`."""
    snapshot.verify()
    _write(AGGS_MANIFEST, {
        "built_at": _now(),
        "all_schools": all_schools,
        "inputs": {AGGS_INPUT_KEYS[s]: snapshot.records[s] for s in ("02", "03", "02a")},
        "read": snapshot.files,
        "outputs": _outputs(outputs),
        "code": code_fingerprint("04"),
    })


def write_published_manifest(all_schools: bool, snapshot: Snapshot, written: set[str]) -> None:
    """
    Called by 05 after generating the site JSON. `written` holds the paths
    (relative to frontend/public/data) of every file this run wrote; each is
    recorded with its SHA-256.
    """
    snapshot.verify()
    site = {}
    for name in sorted(written):
        p = JSON_DIR / name
        if not p.is_file():
            raise RecordError(f"{p} was written by this run but is gone. No record was written. Run 05 again.")
        site[name] = site_file_sha256(p)
    _write(PUBLISHED_MANIFEST, {
        "generated_at": _now(),
        "all_schools": all_schools,
        "aggregates": snapshot.records["04"],
        "read": snapshot.files,
        "outputs": site,
        "code": code_fingerprint("05"),
    })
