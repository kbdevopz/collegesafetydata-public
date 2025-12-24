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
import pandas as pd
import re
from pathlib import Path
from typing import Optional, List, Tuple
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, CURATED_DIR, IVY_UNITIDS, PROCESS_ALL_SCHOOLS

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
}


def read_sas_file(filepath: Path) -> pd.DataFrame:
    """Read a SAS7BDAT file and return a DataFrame."""
    try:
        from sas7bdat import SAS7BDAT
        with SAS7BDAT(str(filepath)) as f:
            df = f.to_data_frame()
    except Exception as e:
        print(f"  Error reading {filepath.name}: {e}")
        return pd.DataFrame()

    # Decode bytes columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: x.decode('latin1') if isinstance(x, bytes) else x)

    return df


def parse_filename(filename: str) -> Optional[Tuple[str, str, List[int]]]:
    """
    Parse a DOE filename to extract geography, category, and years.

    Returns: (geography, category, years_list) or None if not recognized

    Example: "oncampuscrime212223.sas7bdat" -> ("oncampus", "crime", [2021, 2022, 2023])
    """
    name = filename.lower().replace(".sas7bdat", "")

    # Try to match pattern: {geography}{category}{yearpattern}
    for geo in GEOGRAPHY_MAP.keys():
        if name.startswith(geo):
            rest = name[len(geo):]
            for cat in CATEGORY_MAP.keys():
                if rest.startswith(cat):
                    year_suffix = rest[len(cat):]
                    if year_suffix in FILE_YEAR_PATTERNS:
                        return (geo, cat, FILE_YEAR_PATTERNS[year_suffix])

    return None


def extract_offense_data(
    df: pd.DataFrame,
    category: str,
    years: List[int]
) -> List[dict]:
    """
    Extract offense counts from DataFrame columns.

    Columns are named like: RAPE21, MURD22, etc.
    """
    records = []
    family = CATEGORY_MAP[category]

    # Get the UNITID column - prefer _base_unitid if available (for Ivy filtering)
    unitid_col = None
    for col in ["_base_unitid", "UNITID_P", "UNITID"]:
        if col in df.columns:
            unitid_col = col
            break

    if unitid_col is None:
        print("  WARNING: No UNITID column found")
        return records

    # Process each offense type
    for offense_code, offense_name in OFFENSE_MAP.items():
        # For arrest/discipline, append category to offense name
        if category in ["arrest", "discipline"]:
            display_name = f"{offense_name} {category.title()}"
        else:
            display_name = offense_name

        # Look for columns matching this offense for each year
        for year in years:
            year_suffix = str(year)[-2:]  # 2021 -> "21"

            # Try different column name patterns
            possible_cols = [
                f"{offense_code}{year_suffix}",
                f"{offense_code.upper()}{year_suffix}",
            ]

            col_found = None
            for col in possible_cols:
                if col in df.columns or col.upper() in df.columns:
                    col_found = col if col in df.columns else col.upper()
                    break

            if col_found is None:
                continue

            # Extract values
            for _, row in df.iterrows():
                try:
                    unitid = int(row[unitid_col])
                    count = row[col_found]

                    # Convert to numeric, skip nulls and zeros
                    if pd.isna(count):
                        continue
                    count = int(float(count))
                    if count <= 0:
                        continue

                    records.append({
                        "year": year,
                        "unitid": unitid,
                        "offense": display_name,
                        "offense_family": family,
                        "count": count,
                    })
                except (ValueError, TypeError):
                    continue

    return records


def process_all_files(
    ivy_only: bool = False,
    target_years: Optional[List[int]] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Process all SAS files in the raw directory.

    Returns: (facts_df, institutions_df)
    """
    if target_years is None:
        target_years = list(range(2015, 2025))  # 2015-2024

    all_records = []
    all_institutions = []

    # Find all SAS files
    sas_files = list(RAW_DIR.glob("*.sas7bdat"))
    print(f"Found {len(sas_files)} SAS files in {RAW_DIR}")

    # Collect all files to process (not just one per geo+cat)
    files_to_process = []
    for f in sas_files:
        parsed = parse_filename(f.name)
        if parsed:
            geo, cat, years = parsed
            # Filter to target years
            relevant_years = [y for y in years if y in target_years]
            if relevant_years:
                files_to_process.append((f, geo, cat, relevant_years))

    print(f"Processing {len(files_to_process)} files...")

    for filepath, geo, category, years in tqdm(files_to_process, desc="Processing files"):
        geo_display = GEOGRAPHY_MAP[geo]

        # Read the file
        df = read_sas_file(filepath)
        if df.empty:
            continue

        # Filter to Ivy League if requested
        unitid_col = "UNITID_P" if "UNITID_P" in df.columns else "UNITID"
        if ivy_only and unitid_col in df.columns:
            # UNITID_P has format like 166027001 (base + 3-digit suffix)
            # Extract base UNITID by dividing by 1000
            df["_base_unitid"] = (df[unitid_col].astype(float) / 1000).astype(int)
            df = df[df["_base_unitid"].isin(IVY_UNITIDS)].copy()

        if df.empty:
            continue

        # Extract institution info (from first file that has it)
        if not all_institutions and unitid_col in df.columns:
            inst_cols = [c for c in ["UNITID_P", "INSTNM", "City", "State", "ZIP"] if c in df.columns]
            if inst_cols:
                all_institutions.append(df[inst_cols].drop_duplicates())

        # Extract offense data
        records = extract_offense_data(df, category, years)

        # Add geography to records
        for rec in records:
            rec["geo"] = geo_display

        all_records.extend(records)

    if not all_records:
        raise ValueError("No data extracted from any files!")

    # Create DataFrames
    facts = pd.DataFrame(all_records)

    # Dedupe - same offense at same school/year/geo should be summed
    facts = facts.groupby(
        ["year", "unitid", "offense", "offense_family", "geo"],
        as_index=False
    )["count"].sum()

    # Filter to target years
    facts = facts[facts["year"].isin(target_years)]

    # Create institutions DataFrame
    if all_institutions:
        institutions = pd.concat(all_institutions, ignore_index=True)
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
    print(f"Target years: 2015-2024")
    print(f"Processing mode: {'Ivy League only' if ivy_only else 'ALL SCHOOLS (nationwide)'}")
    print(f"Source: {RAW_DIR}")

    # Process all files
    facts, institutions = process_all_files(
        ivy_only=ivy_only,
        target_years=list(range(2015, 2025))
    )

    # Save to parquet
    save_parquet(facts, institutions)

    # Print summary
    print_summary(facts)

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 03_build_dimensions.py")


if __name__ == "__main__":
    main()
