"""
Transform DOE Campus Safety files into tidy Parquet fact table.

The DOE data is organized as:
- Separate files by geography (oncampus, noncampus, publicproperty, residencehall)
- Separate files by category (crime, vawa, arrest, discipline)
- Each file covers 3 years with suffixes like 212223 (2021-2022-2023)
- Columns have year suffixes: RAPE21, MURD22, etc.

Which release each number comes from (see choose_sources):
- Consecutive releases overlap, so most campus-years appear in up to three
  releases. Each campus-year (UNITID_P and calendar year) is taken from the
  NEWEST release whose row for that campus and year is not entirely blank in
  its 16 count files (4 geographies x 4 categories, count columns only). All
  16 files' values for that campus-year then come from that one release; a
  blank file or cell is never filled from another release, except for the
  known DOE file defects listed in KNOWN_DEFECTS.
- A campus that is missing from (or blank in) the newest release keeps the
  numbers an older release has for it, as DOE's own data tool shows them.

Output Schema:
    year: int16                  # 2015-2024
    unitid: int32                # Institution ID
    offense: string              # "Rape", "Fondling", "Burglary", etc.
    offense_family: string       # "Criminal", "VAWA", "Arrest", "Disciplinary"
    geo: string                  # "On-campus", "Non-campus", "Public property", "Residence halls"
    count: int16                 # Number of incidents

Also written: data/curated/dims/campus_year_sources.parquet, the release each
campus-year was taken from (unitid, year, release, restored), including
campus-years whose counts are all zero (the facts hold no rows for those);
and data/curated/dims/older_release_counts.parquet: for each year and each
older release that some campus-year of that year is taken from, every
campus's nonzero counts in that release (On-campus, Non-campus and Public
property), so 04_create_aggregates.py can tell whether a campus-year taken
from an older release copied another campus there (release, year, unitid,
offense, geo, count).

Usage:
    python 02_transform_to_parquet.py
    python 02_transform_to_parquet.py --ivy-only
"""

import sys
import argparse
import logging
import numpy as np
import pandas as pd
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, CURATED_DIR, IVY_UNITIDS, PROCESS_ALL_SCHOOLS, DATA_YEARS
import provenance

# =============================================================================
# DOE FILE STRUCTURE MAPPING
# =============================================================================

# Geography prefixes in filenames -> display names
GEOGRAPHY_MAP = {
    "oncampus": "On-campus",
    "residencehall": "Residence halls",
    "noncampus": "Non-campus",
    "publicproperty": "Public property",
}

# Category -> offense family
CATEGORY_MAP = {
    "crime": "Criminal",
    "vawa": "VAWA",
    "arrest": "Arrest",
    "discipline": "Disciplinary",
}

# Offense code mappings (column prefix -> display name)
OFFENSE_MAP = {
    # Criminal offenses
    "MURD": "Murder",
    "NEG_M": "Negligent Manslaughter",
    "RAPE": "Rape",
    "FONDL": "Fondling",
    "INCES": "Incest",
    "STATR": "Statutory Rape",
    "ROBBE": "Robbery",
    "AGG_A": "Aggravated Assault",
    "BURGLA": "Burglary",
    "VEHIC": "Motor Vehicle Theft",
    "ARSON": "Arson",
    # VAWA offenses
    "DOMEST": "Domestic Violence",
    "DATING": "Dating Violence",
    "STALK": "Stalking",
    # Arrests / Discipline
    "WEAPON": "Weapons",
    "DRUG": "Drug",
    "LIQUOR": "Liquor",
}

# Offense columns each category's files must have, one per year (e.g. RAPE22).
# Names match exactly, in upper case, as DOE has always written them.
CATEGORY_OFFENSES = {
    "crime": ["MURD", "NEG_M", "RAPE", "FONDL", "INCES", "STATR",
              "ROBBE", "AGG_A", "BURGLA", "VEHIC", "ARSON"],
    "vawa": ["DOMEST", "DATING", "STALK"],
    "arrest": ["WEAPON", "DRUG", "LIQUOR"],
    "discipline": ["WEAPON", "DRUG", "LIQUOR"],
}

# Year-suffixed DOE columns that are not counts and are not read (FILTERyy)
IGNORED_YEAR_COLUMNS = ["FILTER"]

# The geographies whose figures 04_create_aggregates.py compares between
# campuses (residence halls are a subset of on-campus and are not compared)
COMPARED_GEOS = ["oncampus", "noncampus", "publicproperty"]

# File suffix patterns -> year lists
# Files are named like: oncampuscrime212223.sas7bdat (covers 2021, 2022, 2023)
FILE_YEAR_PATTERNS = {
    "121314": [2012, 2013, 2014],
    "131415": [2013, 2014, 2015],
    "141516": [2014, 2015, 2016],
    "151617": [2015, 2016, 2017],
    "161718": [2016, 2017, 2018],
    "171819": [2017, 2018, 2019],
    "181920": [2018, 2019, 2020],
    "192021": [2019, 2020, 2021],
    "202122": [2020, 2021, 2022],
    "212223": [2021, 2022, 2023],
    "222324": [2022, 2023, 2024],
}


@dataclass(frozen=True)
class KnownDefect:
    """
    Cells of one DOE file and year that are known to be wrong. The rule
    applies only to campus-years taken from that release (`suffix`). Those
    cells are not read, do not count when deciding whether the release has a
    campus-year (choose_sources), and are taken from the `replacement`
    release instead, or left blank when it is None.

    `copy_of` names the geography whose file of the same release and
    category the defective cells duplicate; `missing` the columns the file
    lacks and `misnamed` columns it has instead. Each is checked every time
    the file is read (check_defect_still_present, check_columns), so a
    corrected re-issue of the file stops the build rather than being
    patched by a rule that no longer applies.
    """
    suffix: str                     # release file suffix, e.g. "212223"
    geo: str                        # GEOGRAPHY_MAP key
    category: str                   # CATEGORY_MAP key
    year: int                       # calendar year of the defective cells
    offenses: Tuple[str, ...]       # offense codes (CATEGORY_OFFENSES) whose cells are defective
    problem: str                    # what is wrong, for messages and the build record
    replacement: Optional[str]      # release suffix to take the cells from, or None (left blank)
    copy_of: Optional[str] = None   # geography of the same release whose values the cells copy
    missing: Tuple[str, ...] = ()   # columns the file lacks for this year
    misnamed: Tuple[str, ...] = ()  # columns the file has instead, which are not read

    @property
    def filename(self) -> str:
        return f"{self.geo}{self.category}{self.suffix}.sas7bdat"


# Known defects in DOE's files. Each is named by release, file and year, and
# applies only to campus-years whose source is that release.
KNOWN_DEFECTS: Tuple[KnownDefect, ...] = (
    # Crime2024SAS.zip: the residence-hall discipline columns for 2022 and
    # 2023 are an exact copy of on-campus discipline at every campus (blank
    # cells included). In every other release and year about 60% of the
    # nonzero residence-hall discipline cells equal the on-campus cell.
    # DOE's data tool shows the 2022 residence-hall figures of the
    # Crime2023SAS.zip release (202122), so those are used; no other release
    # covers 2023 residence-hall discipline for these campuses, so it is left
    # blank.
    KnownDefect("212223", "residencehall", "discipline", 2022, ("WEAPON", "DRUG", "LIQUOR"),
                "is a copy of oncampusdiscipline212223", "202122", copy_of="oncampus"),
    KnownDefect("212223", "residencehall", "discipline", 2023, ("WEAPON", "DRUG", "LIQUOR"),
                "is a copy of oncampusdiscipline212223", None, copy_of="oncampus"),
    # Crime2024SAS.zip: residence-hall arrests have no LIQUOR22 column; the
    # file has a column LIQUOR2 in its place, which is not read. Residence-hall
    # liquor arrests for 2022 are taken from the Crime2023SAS.zip release
    # (202122), the same way as the discipline columns above.
    KnownDefect("212223", "residencehall", "arrest", 2022, ("LIQUOR",),
                "has no LIQUOR22 column (it has a column named LIQUOR2 instead)", "202122",
                missing=("LIQUOR22",), misnamed=("LIQUOR2",)),
)


def defects_for(suffix: str, geo: str, category: str, year: int) -> List[KnownDefect]:
    """The known defects of one file and year."""
    return [d for d in KNOWN_DEFECTS
            if (d.suffix, d.geo, d.category, d.year) == (suffix, geo, category, year)]


def defective_offenses(suffix: str, geo: str, category: str, year: int) -> set:
    """Offense codes whose cells of one file and year are known to be wrong."""
    return {code for d in defects_for(suffix, geo, category, year) for code in d.offenses}


def release_year(suffix: str) -> int:
    """DOE release that holds a file suffix, e.g. "222324" -> 2025."""
    return 2000 + int(suffix[-2:]) + 1


def release_zip(suffix: str) -> str:
    """DOE zip that holds a file suffix, e.g. "222324" -> "Crime2025SAS.zip"."""
    return f"Crime{release_year(suffix)}SAS.zip"


def reextract_hint(filename: str) -> str:
    """How to restore a damaged or missing extracted file."""
    parsed = parse_filename(filename)
    if not parsed:
        return "Extract it again from its DOE zip."
    suffix = parsed[2]
    return (f"Extract it again from {release_zip(suffix)}: "
            f"python 01_download_raw_data.py --release {release_year(suffix)}")


class LogCap(logging.Filter):
    """Pass the first `limit` log records, then one notice, then nothing."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit, self.seen = limit, 0

    def filter(self, record: logging.LogRecord) -> bool:
        self.seen += 1
        if self.seen == self.limit + 1:
            record.msg, record.args = "(further messages from the SAS reader about this file are not shown)", ()
        return self.seen <= self.limit + 1


# Smaller than any SAS data file header, so an empty or cut-off file
SAS_MIN_SIZE = 1024
# The sas7bdat library logs a line per bad page or row of a damaged file
SAS_LOG_LIMIT = 5
# Smallest IPEDS UNITID (six digits); UNITID_P adds three branch digits
MIN_UNITID = 100000


def read_sas_file(filepath: Path) -> pd.DataFrame:
    """Read a SAS7BDAT file and return a DataFrame."""
    hint = reextract_hint(filepath.name)
    try:
        size = filepath.stat().st_size
    except OSError as e:
        raise RuntimeError(f"Could not read {filepath.name} ({e}). {hint}") from e
    # An interrupted extraction can leave a file empty or holding only its start
    if size < SAS_MIN_SIZE:
        raise RuntimeError(f"{filepath.name} is {size:,} bytes, too small to be a SAS data file, "
                           f"so it is damaged. {hint}")
    # The page layout comes from the header, read with the sas7bdat library
    # (it reads no data pages for this). The data itself is read with
    # pyreadstat: sas7bdat misreads the first rows of the files DOE wrote
    # with SAS 9.0000M0 (the 2015 and 2016 releases), turning their UNITIDs
    # into numbers near zero, which dropped those campuses.
    log = logging.getLogger(str(filepath))  # the logger the sas7bdat library uses for this file
    cap = LogCap(SAS_LOG_LIMIT)
    log.addFilter(cap)
    try:
        from sas7bdat import SAS7BDAT
        with SAS7BDAT(str(filepath)) as f:
            props = f.properties
            layout = (props.row_count, props.header_length, props.page_count, props.page_length)
    except Exception as e:
        # Never skip a file: that would silently drop its years from the site
        raise RuntimeError(f"Could not read {filepath.name} ({e}), so it is damaged or is not "
                           f"a SAS data file. {hint}") from e
    finally:
        log.removeFilter(cap)
    if any(not isinstance(v, int) for v in layout):
        raise RuntimeError(f"Could not read {filepath.name}: its header has no "
                           f"row count or page layout. {hint}")
    row_count, header_length, page_count, page_length = layout
    # A file cut short (for example by an interrupted extraction) is rejected
    # before its pages are read
    expected_size = header_length + page_count * page_length
    if size != expected_size:
        raise RuntimeError(f"{filepath.name} is {size:,} bytes but its header declares "
                           f"{expected_size:,}. {hint}")
    try:
        import pyreadstat
        # DOE writes text in Windows-1252 (en dashes are byte 0x96)
        df, meta = pyreadstat.read_sas7bdat(str(filepath), encoding="WINDOWS-1252")
    except Exception as e:
        raise RuntimeError(f"Could not read {filepath.name} ({e}), so it is damaged or is not "
                           f"a SAS data file. {hint}") from e
    for read, source in ((len(df), "rows read"), (meta.number_rows, "rows pyreadstat's header reports")):
        if read != row_count:
            raise RuntimeError(f"{filepath.name} is incomplete: {read:,} {source}, but its header "
                               f"declares {row_count:,}. {hint}")
    # A damaged page can read as a repeat of another row, which both checks
    # above would let through
    repeated = int(df.duplicated().sum())
    if repeated:
        raise RuntimeError(f"{filepath.name} has {repeated:,} rows that exactly repeat another "
                           f"row, so it is damaged (or repeats a record that would be counted "
                           f"twice). {hint}")
    # Some DOE text fields start or end with spaces (" Granada")
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
    return df


def suffix_years(suffix: str) -> Optional[List[int]]:
    """
    Calendar years covered by a release file suffix, e.g. "222324" ->
    [2022, 2023, 2024]. Any six-digit suffix of three consecutive two-digit
    years is accepted, so a new DOE release is picked up without a code
    change (the list above only documents past releases).
    """
    if suffix in FILE_YEAR_PATTERNS:
        return FILE_YEAR_PATTERNS[suffix]
    if re.fullmatch(r"\d{6}", suffix):
        years = [2000 + int(suffix[i:i + 2]) for i in (0, 2, 4)]
        if years[1] == years[0] + 1 and years[2] == years[1] + 1:
            return years
    return None


# Set by process_all_files() for the build record written in main()
USED_FILES: List[Path] = []
YEAR_SOURCES: dict = {}  # year -> the releases on disk that cover it, newest first
READ_BEFORE: dict = {}  # CRC-32 and size of each used file, taken before reading
CAMPUS_YEAR_SOURCES: List[pd.DataFrame] = []  # one table: unitid, year, release, restored
DEFECTS_APPLIED: List[dict] = []  # how many campus-years each KNOWN_DEFECTS rule applied to
OLDER_RELEASE_COUNTS: List[pd.DataFrame] = []  # one table: see older_release_counts.parquet above


def parse_filename(filename: str) -> Optional[Tuple[str, str, List[int]]]:
    """
    Parse a DOE filename to extract geography, category, release suffix, and years.

    Returns: (geography, category, release_suffix, years_list) or None if not recognized

    Example: "oncampuscrime212223.sas7bdat" -> ("oncampus", "crime", "212223", [2021, 2022, 2023])
    """
    name = filename.lower().replace(".sas7bdat", "")

    # Try to match pattern: {geography}{category}{yearpattern}
    for geo in GEOGRAPHY_MAP.keys():
        if name.startswith(geo):
            rest = name[len(geo):]
            for cat in CATEGORY_MAP.keys():
                if rest.startswith(cat):
                    year_suffix = rest[len(cat):]
                    years = suffix_years(year_suffix)
                    if years:
                        return (geo, cat, year_suffix, years)

    return None


def check_columns(columns: List[str], filename: str, category: str, years: List[int]) -> None:
    """
    Raise unless a file has every column the transform reads for the given
    years: a UNITID and one column per offense and year. Also raise on any
    other column ending in one of those years' two digits, and on any column
    named like an offense or FILTER column without a two-digit year (such
    as LIQUOR2), so a renamed or new DOE column is not silently ignored. Only
    the years taken from the file are checked; columns for its other years
    are never read.

    The only exceptions are the columns KNOWN_DEFECTS names for this file and
    year: a column it says is missing may be absent (and must be), and a
    column it says is misnamed is not read (and must be there). Anything else
    about such a file is checked as for every other file.
    """
    present = set(columns)
    suffixes = [str(year)[-2:] for year in years]
    expected = [f"{code}{yy}" for code in CATEGORY_OFFENSES[category] for yy in suffixes]
    known = set(expected) | {f"{prefix}{yy}" for prefix in IGNORED_YEAR_COLUMNS for yy in suffixes}

    parsed = parse_filename(filename)
    file_defects = [d for d in KNOWN_DEFECTS
                    if parsed and (d.suffix, d.geo, d.category) == (parsed[2], parsed[0], category)]
    known_missing = {c for d in file_defects if d.year in years for c in d.missing}
    misnamed = {c for d in file_defects for c in d.misnamed}  # whichever years are checked

    problems = []
    if "UNITID_P" not in present and "UNITID" not in present:
        problems.append("no UNITID_P or UNITID column")
    missing = [c for c in expected if c not in present and c not in known_missing]
    if missing:
        problems.append(f"missing columns {', '.join(missing)}")
    prefixes = "|".join(re.escape(p) for p in CATEGORY_OFFENSES[category] + IGNORED_YEAR_COLUMNS)
    unknown = [c for c in columns if c not in known and c not in misnamed and (
        c.endswith(tuple(suffixes)) or (re.match(prefixes, c) and not re.fullmatch(rf"(?:{prefixes})\d\d", c)))]
    if unknown:
        problems.append(f"unrecognized columns {', '.join(unknown)}")
    if problems:
        raise RuntimeError(
            f"{filename}: {'; '.join(problems)} (years {', '.join(map(str, years))}). "
            "DOE may have renamed or added columns. Update CATEGORY_OFFENSES or "
            "IGNORED_YEAR_COLUMNS in 02_transform_to_parquet.py so every column is "
            "read or deliberately ignored, then rebuild."
        )
    # A known defect that is no longer there means DOE corrected the file
    corrected = [f"it has {c}, which KNOWN_DEFECTS says it lacks" for c in sorted(known_missing & present)]
    corrected += [f"it no longer has {c}, which KNOWN_DEFECTS says it has" for c in sorted(misnamed - present)]
    if corrected:
        raise RuntimeError(
            f"{filename}: {'; '.join(corrected)}, so DOE may have corrected this file. Check the file, "
            "then update or remove its entry in KNOWN_DEFECTS in 02_transform_to_parquet.py and rebuild."
        )


def is_blank(value) -> bool:
    """True for a missing value or an empty string."""
    if isinstance(value, str):
        return not value.strip()
    return value is None or bool(pd.isna(value))


def unitid_column(df: pd.DataFrame) -> str:
    return "UNITID_P" if "UNITID_P" in df.columns else "UNITID"


def campus_ids(df: pd.DataFrame, filename: str) -> pd.Series:
    """
    Each row's institution id as an integer. Every row must carry a
    whole-number id of at least six digits: a misread row (its id read as a
    number near zero) would otherwise be dropped or filed under the wrong
    campus without notice.
    """
    unitid_col = unitid_column(df)
    ids = pd.to_numeric(df[unitid_col], errors="coerce")
    bad = ids.isna() | (ids < MIN_UNITID) | (ids != ids.round())
    if bad.any():
        examples = ", ".join(repr(v) for v in df.loc[bad, unitid_col].head(5))
        raise RuntimeError(
            f"{filename}: {int(bad.sum()):,} rows have a {unitid_col} that is not an institution "
            f"id (for example {examples}), so the file was misread or is damaged. "
            f"{reextract_hint(filename)}"
        )
    return ids.astype("int64")


def extract_offense_data(
    df: pd.DataFrame,
    category: str,
    years: List[int],
    filename: str = "file",
    offenses: Optional[List[str]] = None,
) -> List[dict]:
    """
    Extract offense counts from DataFrame columns.

    Columns are named like: RAPE21, MURD22, etc. `offenses` limits the
    offense codes read (default: all of the category's).
    """
    check_columns(list(df.columns), filename, category, years)

    records = []
    family = CATEGORY_MAP[category]
    unitid_col = unitid_column(df)
    campus_ids(df, filename)

    # Process each offense type
    for offense_code in (CATEGORY_OFFENSES[category] if offenses is None else offenses):
        offense_name = OFFENSE_MAP[offense_code]
        # For arrest/discipline, append category to offense name
        if category in ["arrest", "discipline"]:
            display_name = f"{offense_name} {category.title()}"
        else:
            display_name = offense_name

        for year in years:
            col = f"{offense_code}{str(year)[-2:]}"  # 2021 -> RAPE21

            # Extract values. Blank counts mean nothing reported. Any other
            # value must convert, or the file is not what this code expects.
            for _, row in df.iterrows():
                count = row[col]
                if is_blank(count):
                    continue
                try:
                    count = int(float(count))
                except (ValueError, TypeError, OverflowError):
                    raise RuntimeError(
                        f"{filename}: {col} holds {count!r}, which is not a number"
                    ) from None
                if count <= 0:
                    continue

                unitid = row[unitid_col]
                try:
                    if is_blank(unitid):
                        raise ValueError
                    unitid = int(unitid)
                except (ValueError, TypeError, OverflowError):
                    raise RuntimeError(
                        f"{filename}: a row with {col} = {count} has {unitid_col} "
                        f"{unitid!r}, which is not an institution id"
                    ) from None

                records.append({
                    "year": year,
                    "unitid": unitid,
                    "offense": display_name,
                    "offense_family": family,
                    "count": count,
                })

    return records


def release_counts(df: pd.DataFrame, ids: pd.Series, category: str, year: int, filename: str,
                   skip: set) -> pd.DataFrame:
    """
    Every campus's counts for one year of one file, read as
    extract_offense_data reads them (blank and 0 are left out; a value that is
    not a number stops the build), but column by column rather than row by
    row: (unitid, offense, count). `ids` are the file's campus ids
    (campus_ids), `skip` offense codes not to read (KNOWN_DEFECTS).
    """
    check_columns(list(df.columns), filename, category, [year])
    parts = []
    for code in CATEGORY_OFFENSES[category]:
        if code in skip:
            continue
        col = f"{code}{str(year)[-2:]}"
        values = df[col]
        has = filled(values).to_numpy()
        try:
            numbers = values[has].map(float).to_numpy(dtype="float64")
            counts = np.trunc(numbers)  # int(float(value)), as extract_offense_data
            if not np.isfinite(counts).all():
                raise OverflowError
        except (ValueError, TypeError, OverflowError):
            bad = next(v for v in values[has] if not _is_number(v))
            raise RuntimeError(f"{filename}: {col} holds {bad!r}, which is not a number") from None
        positive = counts > 0
        name = OFFENSE_MAP[code] + (f" {category.title()}" if category in ["arrest", "discipline"] else "")
        parts.append(pd.DataFrame({"unitid": ids.to_numpy()[has][positive], "offense": name,
                                   "count": counts[positive].astype("int64")}))
    return pd.concat(parts, ignore_index=True)


def _is_number(value) -> bool:
    """True when int(float(value)) works, as extract_offense_data needs."""
    try:
        int(float(value))
        return True
    except (ValueError, TypeError, OverflowError):
        return False


def select_files(target_years: List[int]) -> Tuple[List[tuple], dict]:
    """
    Choose which extracted SAS files to read, without reading them.

    Each DOE release covers 3 calendar years, so consecutive releases overlap.
    Every release that covers a target year is read, and each campus-year is
    taken from the newest of them that has it (choose_sources), so a campus
    missing from or blank in the newest release keeps an older release's
    numbers. One campus-year's numbers never come from more than one release
    (apart from KNOWN_DEFECTS, which supply other cells), so overlapping
    releases are never added up.

    Returns ([(path, geography, category, years_to_take), ...] newest release
    first, {year: [suffixes of the releases on disk that cover it, newest
    first]}). Also used by 00_check_for_updates.py.
    """
    sas_files = sorted(RAW_DIR.glob("*.sas7bdat"))
    print(f"Found {len(sas_files)} SAS files in {RAW_DIR}")

    parsed_files = []
    covering = {}  # year -> suffixes of the releases on disk that cover it
    for f in sas_files:
        parsed = parse_filename(f.name)
        if parsed:
            geo, cat, suffix, years = parsed
            taken = [y for y in years if y in target_years]
            if taken:
                parsed_files.append((f, geo, cat, suffix, taken))
                for year in taken:
                    covering.setdefault(year, set()).add(suffix)

    # Newest releases first, so a campus-year is assigned to the newest
    # release that has it and institution info reflects current names
    # (stable sort: within a release, files stay in name order)
    parsed_files.sort(key=lambda item: item[3], reverse=True)

    files_to_process = [(f, geo, cat, taken) for f, geo, cat, _suffix, taken in parsed_files]
    return files_to_process, {y: sorted(s, reverse=True) for y, s in sorted(covering.items())}


def suffix_of_release(release: int) -> str:
    """File suffix of a release, e.g. 2025 -> "222324" (calendar 2022-2024)."""
    return "".join(f"{(release - k) % 100:02d}" for k in (3, 2, 1))


def check_coverage(files_to_process: List[tuple], year_sources: dict, target_years: List[int]) -> None:
    """
    Raise unless every DOE release the transform needs is extracted in full:
    each release that covers a target year (Crime{y+1..y+3}SAS.zip for year
    y), up to the newest release on disk, with all 16 of its count files
    (every geography and category). A campus-year is taken from the newest
    release that has it, so a missing release or file would silently move
    campus-years to an older release, or drop them, instead of failing.
    Also raise when no release on disk covers a target year, or a file would
    be read twice.
    """
    read = {}  # (release suffix, geo, cat) -> file names
    for f, geo, cat, _years in files_to_process:
        read.setdefault((parse_filename(f.name)[2], geo, cat), []).append(f.name)

    problems = []
    newest_on_disk = max((release_year(s) for s, _geo, _cat in read), default=None)
    needed = {}  # release year -> the target years it covers
    for year in sorted(target_years):
        if not year_sources.get(year):
            problems.append(f"no DOE release on disk covers {year}; download and extract the releases "
                            "the pipeline needs: python 01_download_raw_data.py")
            continue
        for release in (year + 1, year + 2, year + 3):
            if release <= newest_on_disk:
                needed.setdefault(release, []).append(year)
    for release, years in sorted(needed.items()):
        suffix = suffix_of_release(release)
        names = {(geo, cat): read.get((suffix, geo, cat), []) for geo in GEOGRAPHY_MAP for cat in CATEGORY_MAP}
        covered = f"it covers {', '.join(map(str, years))}"
        if not any(names.values()):
            problems.append(f"Crime{release}SAS.zip is not extracted in {RAW_DIR} ({covered}); "
                            f"download and extract it: python 01_download_raw_data.py --release {release}")
            continue
        for (geo, cat), found in names.items():
            name = f"{geo}{cat}{suffix}.sas7bdat"
            if not found:
                problems.append(f"{name} is not in {RAW_DIR} ({release_zip(suffix)}; {covered}). "
                                f"{reextract_hint(name)}")
            elif len(found) > 1:
                problems.append(f"{geo}{cat} of {release_zip(suffix)} would be read from {len(found)} files: "
                                f"{', '.join(found)}")
    if problems:
        raise RuntimeError("Crime data is incomplete:\n  " + "\n  ".join(problems))


def filled(values: pd.Series) -> pd.Series:
    """True for each cell that holds a value (a 0 included), False for a blank one (is_blank)."""
    if pd.api.types.is_numeric_dtype(values):
        return values.notna()
    return ~values.map(is_blank).astype(bool)


def campuses_with_data(frames: dict, suffix: str, year: int) -> set:
    """
    The campuses (UNITID_P) whose row for `year` is not entirely blank in
    this release: some count cell of its count files holds a value, a 0
    included. FILTERyy columns are not counts and do not count, nor do the
    cells KNOWN_DEFECTS names for this release and year.
    """
    found = set()
    for (geo, cat), (_path, df, ids, years) in frames.items():
        if year not in years:
            continue
        skip = defective_offenses(suffix, geo, cat, year)
        cols = [f"{code}{str(year)[-2:]}" for code in CATEGORY_OFFENSES[cat] if code not in skip]
        if not cols:
            continue
        has_value = pd.concat([filled(df[c]) for c in cols], axis=1).any(axis=1).to_numpy()
        found.update(ids[has_value].tolist())
    return found


def check_defect_still_present(suffix: str, frames: dict, target_years: List[int]) -> None:
    """
    Raise unless each copy defect in KNOWN_DEFECTS for this release is still
    in its file: every campus's defective cells equal the cells of the file
    they copy (blank where that is blank). If DOE corrects the file, the
    build stops here rather than discarding good numbers.
    """
    for d in KNOWN_DEFECTS:
        if d.suffix != suffix or d.copy_of is None or d.year not in target_years:
            continue
        _path, df, ids, _years = frames[(d.geo, d.category)]
        _src_path, src, src_ids, _src_years = frames[(d.copy_of, d.category)]
        cols = [f"{code}{str(d.year)[-2:]}" for code in d.offenses]
        ours = df[cols].set_axis(ids.to_numpy(), axis=0)
        theirs = src[cols].set_axis(src_ids.to_numpy(), axis=0)
        source_name = f"{d.copy_of}{d.category}{d.suffix}.sas7bdat"
        if set(ours.index) != set(theirs.index):
            differ = len(set(ours.index) ^ set(theirs.index))
        else:
            theirs = theirs.reindex(ours.index)
            same = (ours == theirs) | (ours.isna() & theirs.isna())
            differ = int((~same.all(axis=1)).sum())
        if differ:
            raise RuntimeError(
                f"{d.filename}: its {d.year} columns {', '.join(cols)} are no longer a copy of "
                f"{source_name} ({differ:,} campuses differ), so DOE may have corrected this file. "
                "Check the file, then update or remove its entry in KNOWN_DEFECTS in "
                "02_transform_to_parquet.py and rebuild."
            )


def process_all_files(
    ivy_only: bool = False,
    target_years: Optional[List[int]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Process all SAS files in the raw directory.

    Returns: (facts_df, institutions_df)
    """
    if target_years is None:
        target_years = list(DATA_YEARS)

    all_records = []
    all_institutions = []

    files_to_process, year_sources = select_files(target_years)
    print(f"Releases that cover each year, newest first: {year_sources}")
    print(f"Processing {len(files_to_process)} files...")
    USED_FILES[:] = [f for f, _geo, _cat, _years in files_to_process]
    YEAR_SOURCES.clear()
    YEAR_SOURCES.update(year_sources)
    READ_BEFORE.clear()
    READ_BEFORE.update(provenance.file_records(USED_FILES))

    check_coverage(files_to_process, year_sources, target_years)

    # The files of each release, newest release first (select_files' order)
    releases: List[Tuple[str, List[tuple]]] = []
    for item in files_to_process:
        suffix = parse_filename(item[0].name)[2]
        if not releases or releases[-1][0] != suffix:
            releases.append((suffix, []))
        releases[-1][1].append(item)

    sources = {}  # (unitid, year) -> suffix of the release the campus-year is taken from
    done = set()  # releases processed so far (all newer than the current one)
    older_counts = []  # tables of release_counts for older_release_counts.parquet

    def add(records: List[dict], geo: str, suffix: str) -> None:
        for rec in records:
            rec["geo"] = GEOGRAPHY_MAP[geo]
            rec["release"] = suffix
        all_records.extend(records)

    for suffix, files in tqdm(releases, desc="Processing releases"):
        # Read the release's files
        frames = {}  # (geo, cat) -> (path, df, ids, years)
        for filepath, geo, category, years in files:
            df = read_sas_file(filepath)
            if df.empty:
                raise RuntimeError(f"{filepath.name} contains no rows")
            check_columns(list(df.columns), filepath.name, category, years)
            frames[(geo, category)] = (filepath, df, campus_ids(df, filepath.name), years)
        check_defect_still_present(suffix, frames, target_years)

        # The campus-years this release supplies: those it has, and that no
        # newer release has (choose_sources)
        taken = {}  # year -> campuses taken from this release
        for year in sorted({y for *_rest, years in files for y in years}):
            mine = {u for u in campuses_with_data(frames, suffix, year) if (u, year) not in sources}
            for unitid in mine:
                sources[(unitid, year)] = suffix
            taken[year] = mine

        # The years this release supplies as an older release: every campus's
        # counts there, so 04 can see whether a campus-year taken from it
        # copied another campus in this same release
        for year in sorted(y for y, mine in taken.items() if mine and suffix != year_sources[y][0]):
            for geo in COMPARED_GEOS:
                for category in CATEGORY_MAP:
                    filepath, df, ids, _years = frames[(geo, category)]
                    if ivy_only:
                        keep = ids.isin(IVY_UNITIDS).to_numpy()
                        df, ids = df[keep], ids[keep]
                    counts = release_counts(df, ids, category, year, filepath.name,
                                            defective_offenses(suffix, geo, category, year))
                    counts.insert(0, "release", suffix)
                    counts.insert(1, "year", year)
                    counts["geo"] = GEOGRAPHY_MAP[geo]
                    older_counts.append(counts)

        for filepath, geo, category, years in files:
            _path, df, ids, _years = frames[(geo, category)]

            # Filter to Ivy League if requested. IVY_UNITIDS are full UNITID_P
            # values (e.g. 166027001), the same ids the facts carry.
            if ivy_only:
                keep = ids.isin(IVY_UNITIDS).to_numpy()
                df, ids = df[keep], ids[keep]
            if df.empty:
                continue

            # Extract institution info from every file (files are processed newest
            # release first, so the first occurrence of a school has current info;
            # schools only present in older releases are still captured)
            inst_cols = [c for c in ["UNITID_P", "INSTNM", "City", "State", "ZIP"] if c in df.columns]
            if inst_cols:
                all_institutions.append(df[inst_cols].drop_duplicates())

            # Offense counts of the campus-years taken from this release,
            # except the cells KNOWN_DEFECTS names for this file and year
            for year in years:
                skip = defective_offenses(suffix, geo, category, year)
                codes = [c for c in CATEGORY_OFFENSES[category] if c not in skip]
                rows = df[ids.isin(taken[year]).to_numpy()]
                if codes and not rows.empty:
                    add(extract_offense_data(rows, category, [year], filepath.name, codes), geo, suffix)

            # The cells this release supplies in place of a newer release's defect
            for d in KNOWN_DEFECTS:
                if d.replacement != suffix or (d.geo, d.category) != (geo, category) or d.year not in years:
                    continue
                if d.suffix not in done and any(s == d.suffix for s, _files in releases):
                    raise RuntimeError(f"KNOWN_DEFECTS: {d.filename} takes its {d.year} cells from "
                                       f"{release_zip(suffix)}, which is not older. Fix the entry in "
                                       "02_transform_to_parquet.py.")
                affected = {u for (u, y), s in sources.items() if y == d.year and s == d.suffix}
                rows = df[ids.isin(affected).to_numpy()]
                if not rows.empty:
                    add(extract_offense_data(rows, category, [d.year], filepath.name, list(d.offenses)),
                        geo, suffix)
        done.add(suffix)

    if not all_records:
        raise ValueError("No data extracted from any files!")

    # The release of every campus-year that has one (all-zero rows included)
    table = pd.DataFrame([(u, y, s) for (u, y), s in sources.items()], columns=["unitid", "year", "release"])
    table["restored"] = table["release"] != table["year"].map(lambda y: year_sources[y][0])
    if ivy_only:
        table = table[table["unitid"].isin(IVY_UNITIDS)]
    table = table.sort_values(["year", "unitid"]).reset_index(drop=True)
    CAMPUS_YEAR_SOURCES[:] = [table]
    DEFECTS_APPLIED[:] = [{
        "file": d.filename,
        "year": d.year,
        "columns": [f"{code}{str(d.year)[-2:]}" for code in d.offenses],
        "problem": d.problem,
        "taken_from": f"{d.geo}{d.category}{d.replacement}.sas7bdat" if d.replacement else None,
        "campus_years": int(((table["year"] == d.year) & (table["release"] == d.suffix)).sum()),
    } for d in KNOWN_DEFECTS if d.year in target_years]

    # Create DataFrames
    facts = pd.DataFrame(all_records)

    # Collapse to one row per school/year/offense/geo. Each count comes from
    # the one release its campus-year is taken from (or, for a known defect,
    # from the release that replaces those cells), never from two.
    keys = ["year", "unitid", "offense", "offense_family", "geo"]
    mixed = facts.groupby(keys)["release"].nunique()
    if (mixed > 1).any():
        first = mixed[mixed > 1].index[0]
        raise RuntimeError(f"{int((mixed > 1).sum()):,} counts would add up two DOE releases (first: {first}). "
                           "This is a bug in 02_transform_to_parquet.py; nothing was written.")
    facts = facts.groupby(keys, as_index=False)["count"].sum()

    # Filter to target years
    facts = facts[facts["year"].isin(target_years)]

    # Every campus's counts in each older release a campus-year is taken
    # from. A campus-year taken from that release must have there exactly
    # its fact counts, or the two readings of the files disagree.
    columns = ["release", "year", "unitid", "offense", "geo", "count"]
    older = (pd.concat(older_counts, ignore_index=True) if older_counts else pd.DataFrame(columns=columns))
    older = older[columns].astype({"year": "int64", "unitid": "int64", "count": "int64"})
    older = older.sort_values(["release", "year", "unitid", "geo", "offense"]).reset_index(drop=True)
    if older.duplicated(["release", "year", "unitid", "geo", "offense"]).any():
        raise RuntimeError("older_release_counts would hold a count twice. This is a bug in "
                           "02_transform_to_parquet.py; nothing was written.")
    taken_older = table[table["restored"]][["unitid", "year", "release"]]
    compared = [GEOGRAPHY_MAP[g] for g in COMPARED_GEOS]
    mine = older.merge(taken_older, on=["unitid", "year", "release"])
    theirs = facts[facts["geo"].isin(compared)].merge(taken_older, on=["unitid", "year"])
    key = ["release", "year", "unitid", "geo", "offense", "count"]
    differ = pd.concat([mine[key], theirs[key]]).drop_duplicates(keep=False)
    if len(differ):
        first = differ.iloc[0]
        raise RuntimeError(f"{len(differ):,} counts of campus-years taken from an older release differ between "
                           f"the facts and older_release_counts (first: {first['unitid']} {first['year']} "
                           f"{first['geo']} {first['offense']}). This is a bug in 02_transform_to_parquet.py; "
                           "nothing was written.")
    OLDER_RELEASE_COUNTS[:] = [older]

    # Create institutions DataFrame - keep first occurrence per school
    # (newest release first, so current names/addresses win)
    if all_institutions:
        institutions = pd.concat(all_institutions, ignore_index=True)
        if "UNITID_P" in institutions.columns:
            institutions = institutions.drop_duplicates(subset=["UNITID_P"], keep="first")
        else:
            institutions = institutions.drop_duplicates()
    else:
        institutions = pd.DataFrame()

    return facts, institutions


# The release each campus-year is taken from (see the module docstring).
# Not in data/curated/facts, where steps 03-07 accept only incidents.parquet.
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"
# Every campus's counts in the older releases campus-years are taken from (see the module docstring)
OLDER_PATH = CURATED_DIR / "dims" / "older_release_counts.parquet"


def save_parquet(facts: pd.DataFrame, institutions: pd.DataFrame, sources: pd.DataFrame,
                 older: pd.DataFrame) -> None:
    """Save DataFrames to Parquet files."""
    facts_dir = CURATED_DIR / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)

    # Save facts as single file (simpler)
    facts_path = facts_dir / "incidents.parquet"
    facts.to_parquet(facts_path, index=False)
    print(f"Facts saved to: {facts_path}")

    dims_dir = CURATED_DIR / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)

    # Save institutions dimension
    if not institutions.empty:
        inst_path = dims_dir / "raw_institutions.parquet"
        institutions.to_parquet(inst_path, index=False)
        print(f"Institutions saved to: {inst_path}")

    sources.to_parquet(SOURCES_PATH, index=False)
    print(f"Campus-year sources saved to: {SOURCES_PATH}")
    older.to_parquet(OLDER_PATH, index=False)
    print(f"Older release counts ({len(older):,} rows) saved to: {OLDER_PATH}")


def sources_by_year(sources: pd.DataFrame) -> dict:
    """For the build record: {year: {release suffix: campus-years taken from it}}."""
    out = {}
    for (year, release), n in sources.groupby(["year", "release"]).size().items():
        out.setdefault(str(int(year)), {})[str(release)] = int(n)
    return out


def print_sources(sources: pd.DataFrame, facts: pd.DataFrame) -> None:
    """Campus-years per year and release, and those taken from an older release."""
    print("\nCampus-years by release (newest release first; zeros included):")
    with_counts = set(zip(facts["unitid"].tolist(), facts["year"].tolist()))
    for year, part in sources.groupby("year"):
        counts = part.groupby("release").size().sort_index(ascending=False)
        older = part[part["restored"]]
        positive = sum((u, year) in with_counts for u in older["unitid"].tolist())
        print(f"  {year}: " + ", ".join(f"{s}: {n:,}" for s, n in counts.items())
              + f"  (from an older release: {len(older):,}, {positive:,} with counts)")
    for rec in DEFECTS_APPLIED:
        taken = f"taken from {rec['taken_from']}" if rec["taken_from"] else "left blank"
        print(f"  Known DOE defect: {rec['file']} {rec['year']} ({', '.join(rec['columns'])}) {rec['problem']}; "
              f"{taken} for the {rec['campus_years']:,} campus-years from that release")


def print_summary(facts: pd.DataFrame) -> None:
    """Print summary statistics."""
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total records: {len(facts):,}")
    print(f"Years: {facts['year'].min()}-{facts['year'].max()}")
    print(f"Schools: {facts['unitid'].nunique():,}")
    print(f"Offenses: {facts['offense'].nunique()}")
    print(f"Total incidents: {facts['count'].sum():,}")

    print("\nRecords by year:")
    for year in sorted(facts["year"].unique()):
        year_data = facts[facts["year"] == year]
        print(f"  {year}: {len(year_data):,} records, {year_data['count'].sum():,} incidents")

    print("\nTop 10 offenses by total count:")
    top_offenses = facts.groupby("offense")["count"].sum().nlargest(10)
    for offense, count in top_offenses.items():
        print(f"  {offense}: {count:,}")

    print("\nBy offense family:")
    for family in ["Criminal", "VAWA", "Arrest", "Disciplinary"]:
        family_data = facts[facts["offense_family"] == family]
        if len(family_data) > 0:
            print(f"  {family}: {family_data['count'].sum():,} incidents")


def main():
    parser = argparse.ArgumentParser(
        description="Transform DOE crime data to tidy Parquet format"
    )
    parser.add_argument(
        "--ivy-only",
        action="store_true",
        help="Filter to Ivy League schools only (overrides config)"
    )
    parser.add_argument(
        "--all-schools",
        action="store_true",
        help="Process all schools (overrides config)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )

    args = parser.parse_args()

    # Determine processing mode: CLI args override config
    if args.all_schools:
        ivy_only = False
    elif args.ivy_only:
        ivy_only = True
    else:
        # Use config setting (PROCESS_ALL_SCHOOLS=True means ivy_only=False)
        ivy_only = not PROCESS_ALL_SCHOOLS

    print("=" * 60)
    print("DOE Campus Safety Data Transformation")
    print("=" * 60)
    print(f"Target years: {min(DATA_YEARS)}-{max(DATA_YEARS)}")
    print(f"Processing mode: {'Ivy League only' if ivy_only else 'ALL SCHOOLS (nationwide)'}")
    print(f"Source: {RAW_DIR}")

    # The old build record no longer describes the files about to be written
    provenance.invalidate(provenance.CRIME_MANIFEST)

    # Process all files
    facts, institutions = process_all_files(
        ivy_only=ivy_only,
        target_years=list(DATA_YEARS)
    )

    # Save to parquet
    sources = CAMPUS_YEAR_SOURCES[0]
    save_parquet(facts, institutions, sources, OLDER_RELEASE_COUNTS[0])

    # Record which releases and which SAS files each year came from, how many
    # campus-years each release supplied, the known defects applied, and the
    # files written (raw_institutions.parquet only when this run wrote it)
    written = [CURATED_DIR / "facts" / "incidents.parquet"]
    if not institutions.empty:
        written.append(CURATED_DIR / "dims" / "raw_institutions.parquet")
    written += [SOURCES_PATH, OLDER_PATH]
    provenance.write_crime_manifest(YEAR_SOURCES, USED_FILES, all_schools=not ivy_only,
                                    read_before=READ_BEFORE, outputs=written,
                                    campus_years=sources_by_year(sources), defects=DEFECTS_APPLIED)
    print(f"Input record: {provenance.CRIME_MANIFEST}")

    # Print summary
    print_summary(facts)
    print_sources(sources, facts)

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 03_build_dimensions.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("02", main))
