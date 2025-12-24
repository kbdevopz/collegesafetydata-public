"""
Transform IPEDS enrollment data into parquet format.

Data Sources:
- DRVEF (Derived Fall Enrollment) for 2021-2023: Pre-calculated FTE
- EF (Fall Enrollment) for 2015-2020: Calculate FTE from FT/PT breakdown

Output columns:
- unitid: Institution ID
- year: Academic year
- fte: Full-time equivalent enrollment
- enrollment_total: Total headcount
- enrollment_ft: Full-time enrollment
- enrollment_pt: Part-time enrollment

Usage:
    python 02a_transform_enrollment.py

Prerequisite:
    python 02b_transform_ef_enrollment.py (generates dim_enrollment_ef.parquet)
"""

import sys
import pandas as pd
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT

# Directories
IPEDS_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ipeds"
CURATED_DIR = PROJECT_ROOT / "data" / "curated" / "dims"

# Years with DRVEF files available
DRVEF_YEARS = [2021, 2022, 2023]


def load_drvef_file(year: int) -> pd.DataFrame:
    """Load and parse a DRVEF file for a given year."""
    file_path = IPEDS_RAW_DIR / str(year) / f"drvef{year}.csv"

    if not file_path.exists():
        print(f"  Warning: {file_path.name} not found")
        return pd.DataFrame()

    # Read only the columns we need
    cols = ['UNITID', 'ENRTOT', 'FTE', 'ENRFT', 'ENRPT']
    df = pd.read_csv(file_path, usecols=cols)

    # Add year column
    df['year'] = year

    # Clean up: remove rows with missing FTE
    df = df.dropna(subset=['FTE'])

    # Convert to appropriate types
    df['UNITID'] = df['UNITID'].astype('int32')
    df['year'] = df['year'].astype('int16')
    df['FTE'] = df['FTE'].astype('int32')
    df['ENRTOT'] = df['ENRTOT'].fillna(0).astype('int32')
    df['ENRFT'] = df['ENRFT'].fillna(0).astype('int32')
    df['ENRPT'] = df['ENRPT'].fillna(0).astype('int32')

    return df


def load_ef_data() -> pd.DataFrame:
    """Load EF-derived enrollment data for 2015-2020 from parquet file."""
    ef_path = CURATED_DIR / "dim_enrollment_ef.parquet"

    if not ef_path.exists():
        print(f"  Warning: {ef_path.name} not found")
        print("  Run: python 02b_transform_ef_enrollment.py first")
        return pd.DataFrame()

    df = pd.read_parquet(ef_path)
    return df


def main():
    print("=" * 60)
    print("IPEDS Enrollment Transform (Combined)")
    print("=" * 60)
    print("Sources:")
    print("  - DRVEF files (2021-2023): Pre-calculated FTE")
    print("  - EF files (2015-2020): Calculated FTE")

    all_data = []

    # Load DRVEF files (2021-2023)
    print("\n--- DRVEF Data (2021-2023) ---")
    for year in DRVEF_YEARS:
        print(f"\n{year}:")
        df = load_drvef_file(year)
        if len(df) > 0:
            # Rename columns to match schema
            df = df.rename(columns={
                'UNITID': 'unitid',
                'FTE': 'fte',
                'ENRTOT': 'enrollment_total',
                'ENRFT': 'enrollment_ft',
                'ENRPT': 'enrollment_pt'
            })
            print(f"  Loaded {len(df):,} institutions")
            all_data.append(df)
        else:
            print(f"  No data")

    # Load EF-derived data (2015-2020)
    print("\n--- EF Data (2015-2020) ---")
    ef_data = load_ef_data()
    if len(ef_data) > 0:
        print(f"  Loaded {len(ef_data):,} records from {ef_data['year'].nunique()} years")
        all_data.append(ef_data)
    else:
        print("  Warning: No EF data loaded - historical FTE will be missing")

    if not all_data:
        print("\nError: No enrollment data found!")
        return 1

    # Combine all years
    combined = pd.concat(all_data, ignore_index=True)

    # Ensure correct column order
    combined = combined[['unitid', 'year', 'fte', 'enrollment_total', 'enrollment_ft', 'enrollment_pt']]

    # Sort by unitid and year
    combined = combined.sort_values(['unitid', 'year']).reset_index(drop=True)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total records: {len(combined):,}")
    print(f"Unique institutions: {combined['unitid'].nunique():,}")
    print(f"Years covered: {sorted(combined['year'].unique())}")
    print(f"FTE range: {combined['fte'].min():,} - {combined['fte'].max():,}")

    # Spot check Harvard (166027) - should have all 9 years
    harvard = combined[combined['unitid'] == 166027]
    if len(harvard) > 0:
        print("\nSpot check - Harvard (166027):")
        print(harvard.to_string(index=False))

    # Spot check Yale (130794)
    yale = combined[combined['unitid'] == 130794]
    if len(yale) > 0:
        print("\nSpot check - Yale (130794):")
        print(yale.to_string(index=False))

    # Save to parquet
    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CURATED_DIR / "dim_enrollment.parquet"
    combined.to_parquet(output_path, index=False)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 04_create_aggregates.py (to join enrollment)")
    print("2. Run: python 05_generate_json.py (to add rates to JSON)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
