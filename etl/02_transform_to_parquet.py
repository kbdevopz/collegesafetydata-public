"""
Transform DOE Campus Safety files into tidy Parquet fact table.

The DOE data is organized as:
- Separate files by geography (oncampus, noncampus, publicproperty, residencehall)
- Separate files by category (crime, vawa, arrest, discipline)
- Each file covers 3 years with suffixes like 212223 (2021-2022-2023)
- Columns have year suffixes: RAPE21, MURD22, etc.

Output Schema:
    year: int16                  # 2015-2024
    unitid: int32                # Institution ID
    offense: string              # "Rape", "Fondling", "Burglary", etc.
    offense_family: string       # "Criminal", "VAWA", "Arrest", "Disciplinary"
    geo: string                  # "On-campus", "Non-campus", "Public property", "Residence halls"
    count: int16                 # Number of incidents

Usage:
    python 02_transform_to_parquet.py
    python 02_transform_to_parquet.py --ivy-only
"""

import sys
import argparse
import logging
import pandas as pd
import re
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
    log = logging.getLogger(str(filepath))  # the logger the sas7bdat library uses for this file
    cap = LogCap(SAS_LOG_LIMIT)
    log.addFilter(cap)
    cut_short = None
    try:
        from sas7bdat import SAS7BDAT
        with SAS7BDAT(str(filepath)) as f:
            props = f.properties
            declared = (props.header_length, props.page_count, props.page_length)
            # A file cut short is rejected without reading its pages, which
            # would only fill the log with the library's errors
            if (all(isinstance(v, int) for v in declared)
                    and size != declared[0] + declared[1] * declared[2]):
                cut_short = (f"{filepath.name} is {size:,} bytes but its header declares "
                             f"{declared[0] + declared[1] * declared[2]:,}. {hint}")
            else:
                df = f.to_data_frame()
                props = f.properties
                layout = (props.row_count, props.header_length,
                          props.page_count, props.page_length)
    except Exception as e:
        # Never skip a file: that would silently drop its years from the site
        raise RuntimeError(f"Could not read {filepath.name} ({e}), so it is damaged or is not "
                           f"a SAS data file. {hint}") from e
    finally:
        log.removeFilter(cap)
    if cut_short:
        raise RuntimeError(cut_short)

    # A file cut short (for example by an interrupted extraction) can still
    # parse, with rows missing. Check it against its own header.
    if any(not isinstance(v, int) for v in layout):
        raise RuntimeError(f"Could not read {filepath.name}: its header has no "
                           f"row count or page layout. {reextract_hint(filepath.name)}")
    row_count, header_length, page_count, page_length = layout
    if len(df) != row_count:
        raise RuntimeError(f"{filepath.name} is incomplete: read {len(df):,} of the "
                           f"{row_count:,} rows its header declares. {reextract_hint(filepath.name)}")
    expected_size = header_length + page_count * page_length
    if size != expected_size:
        raise RuntimeError(f"{filepath.name} is {size:,} bytes but its header declares "
                           f"{expected_size:,}. {reextract_hint(filepath.name)}")
    # Where a file's pages are zeros, the pinned sas7bdat reader repeats the
    # last good row instead of failing, so both checks above can pass.
    repeated = int(df.duplicated().sum())
    if repeated:
        raise RuntimeError(f"{filepath.name} has {repeated:,} rows that exactly repeat another "
                           f"row, so it is damaged (or repeats a record that would be counted "
                           f"twice). {reextract_hint(filepath.name)}")

    # Decode bytes columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: x.decode('latin1') if isinstance(x, bytes) else x)

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
YEAR_SOURCES: dict = {}
READ_BEFORE: dict = {}  # CRC-32 and size of each used file, taken before reading


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
    other column ending in one of those years' two digits, so a renamed or
    new DOE column is not silently ignored. Only the years taken from the
    file are checked; columns for its other years are never read.
    """
    present = set(columns)
    suffixes = [str(year)[-2:] for year in years]
    expected = [f"{code}{yy}" for code in CATEGORY_OFFENSES[category] for yy in suffixes]
    known = set(expected) | {f"{prefix}{yy}" for prefix in IGNORED_YEAR_COLUMNS for yy in suffixes}

    problems = []
    if "UNITID_P" not in present and "UNITID" not in present:
        problems.append("no UNITID_P or UNITID column")
    missing = [c for c in expected if c not in present]
    if missing:
        problems.append(f"missing columns {', '.join(missing)}")
    unknown = [c for c in columns if c.endswith(tuple(suffixes)) and c not in known]
    if unknown:
        problems.append(f"unrecognized columns {', '.join(unknown)}")
    if problems:
        raise RuntimeError(
            f"{filename}: {'; '.join(problems)} (years {', '.join(map(str, years))}). "
            "DOE may have renamed or added columns. Update CATEGORY_OFFENSES or "
            "IGNORED_YEAR_COLUMNS in 02_transform_to_parquet.py so every column is "
            "read or deliberately ignored, then rebuild."
        )


def is_blank(value) -> bool:
    """True for a missing value or an empty string."""
    if isinstance(value, str):
        return not value.strip()
    return value is None or bool(pd.isna(value))


def extract_offense_data(
    df: pd.DataFrame,
    category: str,
    years: List[int],
    filename: str = "file",
) -> List[dict]:
    """
    Extract offense counts from DataFrame columns.

    Columns are named like: RAPE21, MURD22, etc.
    """
    check_columns(list(df.columns), filename, category, years)

    records = []
    family = CATEGORY_MAP[category]
    unitid_col = "UNITID_P" if "UNITID_P" in df.columns else "UNITID"

    # Process each offense type
    for offense_code in CATEGORY_OFFENSES[category]:
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


def select_files(target_years: List[int]) -> Tuple[List[tuple], dict]:
    """
    Choose which extracted SAS files to read, without reading them.

    Each DOE release covers 3 calendar years, so consecutive releases overlap.
    Each year is sourced ONLY from the newest release that covers it (later
    collections include institutions' corrections). Extracting the same year
    from multiple overlapping releases would double/triple-count incidents.

    Returns ([(path, geography, category, years_to_take), ...] newest release
    first, {year: release suffix}). Also used by 00_check_for_updates.py.
    """
    sas_files = sorted(RAW_DIR.glob("*.sas7bdat"))
    print(f"Found {len(sas_files)} SAS files in {RAW_DIR}")

    parsed_files = []
    newest_release = {}  # year -> newest release suffix that covers it
    for f in sas_files:
        parsed = parse_filename(f.name)
        if parsed:
            geo, cat, suffix, years = parsed
            parsed_files.append((f, geo, cat, suffix, years))
            for year in years:
                if year in target_years:
                    newest_release[year] = max(newest_release.get(year, ""), suffix)

    # Newest releases first so institution info reflects current names
    # (stable sort: within a release, files stay in name order)
    parsed_files.sort(key=lambda item: item[3], reverse=True)

    files_to_process = []
    for f, geo, cat, suffix, years in parsed_files:
        relevant_years = [
            y for y in years
            if y in target_years and newest_release[y] == suffix
        ]
        if relevant_years:
            files_to_process.append((f, geo, cat, relevant_years))

    return files_to_process, {y: s for y, s in sorted(newest_release.items())}


def check_coverage(files_to_process: List[tuple], year_sources: dict, target_years: List[int]) -> None:
    """
    Raise unless every target year is read from exactly one file for each
    geography and category, so a missing file or release never silently
    drops part of a year. Also raise unless each year is read from the newest
    DOE release that covers it: Crime{year + 3}SAS.zip, or the newest release
    on disk when that is older, so a missing release in between never leaves
    a year built from a superseded release.
    """
    read = {}
    for f, geo, cat, years in files_to_process:
        for year in years:
            read.setdefault((year, geo, cat), []).append(f.name)

    problems = []
    missing = {}  # (release suffix, geo, cat) -> years left without a source
    newest_on_disk = max((release_year(s) for s in year_sources.values()), default=None)
    for year in sorted(target_years):
        suffix = year_sources.get(year)
        if suffix is None:
            problems.append(f"no DOE release on disk covers {year}; download and extract the releases "
                            "the pipeline needs: python 01_download_raw_data.py")
            continue
        newest = min(year + 3, newest_on_disk)
        if release_year(suffix) < newest:
            problems.append(f"{year} would be read from {release_zip(suffix)}, but Crime{newest}SAS.zip, a "
                            f"newer DOE release that covers {year}, is not extracted in {RAW_DIR}; download "
                            "and extract the releases the pipeline needs: python 01_download_raw_data.py")
            continue
        for geo in GEOGRAPHY_MAP:
            for cat in CATEGORY_MAP:
                names = read.get((year, geo, cat), [])
                if not names:
                    missing.setdefault((suffix, geo, cat), []).append(year)
                elif len(names) > 1:
                    problems.append(f"{year} {geo} {cat} would be read from {len(names)} files: {', '.join(names)}")
    for (suffix, geo, cat), years in missing.items():
        name = f"{geo}{cat}{suffix}.sas7bdat"
        problems.append(f"{release_zip(suffix)} is the source of {', '.join(map(str, years))} but "
                        f"{name} is not in {RAW_DIR}. {reextract_hint(name)}")
    if problems:
        raise RuntimeError("Crime data is incomplete:\n  " + "\n  ".join(problems))


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
    print(f"Year -> release mapping: {year_sources}")
    print(f"Processing {len(files_to_process)} files...")
    USED_FILES[:] = [f for f, _geo, _cat, _years in files_to_process]
    YEAR_SOURCES.clear()
    YEAR_SOURCES.update(year_sources)
    READ_BEFORE.clear()
    READ_BEFORE.update(provenance.file_records(USED_FILES))

    check_coverage(files_to_process, year_sources, target_years)

    for filepath, geo, category, years in tqdm(files_to_process, desc="Processing files"):
        geo_display = GEOGRAPHY_MAP[geo]

        # Read the file
        df = read_sas_file(filepath)
        if df.empty:
            raise RuntimeError(f"{filepath.name} contains no rows")
        check_columns(list(df.columns), filepath.name, category, years)

        # Filter to Ivy League if requested. IVY_UNITIDS are full UNITID_P
        # values (e.g. 166027001), the same ids the facts carry.
        unitid_col = "UNITID_P" if "UNITID_P" in df.columns else "UNITID"
        if ivy_only:
            df = df[df[unitid_col].astype(float).isin(IVY_UNITIDS)].copy()

        if df.empty:
            continue

        # Extract institution info from every file (files are processed newest
        # release first, so the first occurrence of a school has current info;
        # schools only present in older releases are still captured)
        if unitid_col in df.columns:
            inst_cols = [c for c in ["UNITID_P", "INSTNM", "City", "State", "ZIP"] if c in df.columns]
            if inst_cols:
                all_institutions.append(df[inst_cols].drop_duplicates())

        # Extract offense data
        records = extract_offense_data(df, category, years, filepath.name)

        # Add geography to records
        for rec in records:
            rec["geo"] = geo_display

        all_records.extend(records)

    if not all_records:
        raise ValueError("No data extracted from any files!")

    # Create DataFrames
    facts = pd.DataFrame(all_records)

    # Collapse to one row per school/year/offense/geo. Each year is sourced
    # from exactly one release (see newest_release above), so this only merges
    # rows within a single release - it cannot double-count across releases.
    facts = facts.groupby(
        ["year", "unitid", "offense", "offense_family", "geo"],
        as_index=False
    )["count"].sum()

    # Filter to target years
    facts = facts[facts["year"].isin(target_years)]

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


def save_parquet(facts: pd.DataFrame, institutions: pd.DataFrame) -> None:
    """Save DataFrames to Parquet files."""
    facts_dir = CURATED_DIR / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)

    # Save facts as single file (simpler)
    facts_path = facts_dir / "incidents.parquet"
    facts.to_parquet(facts_path, index=False)
    print(f"Facts saved to: {facts_path}")

    # Save institutions dimension
    if not institutions.empty:
        dims_dir = CURATED_DIR / "dims"
        dims_dir.mkdir(parents=True, exist_ok=True)
        inst_path = dims_dir / "raw_institutions.parquet"
        institutions.to_parquet(inst_path, index=False)
        print(f"Institutions saved to: {inst_path}")


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
    save_parquet(facts, institutions)

    # Record which release and which SAS files each year came from, and the
    # files written (raw_institutions.parquet only when this run wrote it)
    written = [CURATED_DIR / "facts" / "incidents.parquet"]
    if not institutions.empty:
        written.append(CURATED_DIR / "dims" / "raw_institutions.parquet")
    provenance.write_crime_manifest(YEAR_SOURCES, USED_FILES, all_schools=not ivy_only,
                                    read_before=READ_BEFORE, outputs=written)
    print(f"Input record: {provenance.CRIME_MANIFEST}")

    # Print summary
    print_summary(facts)

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 03_build_dimensions.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("02", main))
