"""
Transform IPEDS EF (Fall Enrollment) files to calculate FTE for 2015-2020.

FTE Calculation uses official IPEDS methodology:
    FTE = FT_Undergrad + FT_Graduate +
          (PT_Undergrad x 0.403543) +
          (PT_Graduate x 0.361702)

These factors are derived from NCES IPEDS survey methodology for calculating
FTE from headcount enrollment by student level. The factors represent the
average course load of part-time students relative to full-time students.

EFALEVEL codes used:
    22 = Full-time undergraduate
    32 = Full-time graduate (including professional)
    42 = Part-time undergraduate
    52 = Part-time graduate (including professional)

For 2021-2023, we use DRVEF files which contain pre-calculated FTE values
directly from IPEDS. This script processes EF files for years where DRVEF
is not available (2015-2020).

Sources:
    - IPEDS Survey Components: https://nces.ed.gov/ipeds/survey-components/8
    - FTE Methodology: https://nces.ed.gov/ipeds/report-your-data/

Usage:
    python 02b_transform_ef_enrollment.py
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

# Years to process (years without DRVEF files)
EF_YEARS = [2015, 2016, 2017, 2018, 2019, 2020]

# =============================================================================
# OFFICIAL IPEDS FTE CONVERSION FACTORS
# =============================================================================
# These factors convert part-time enrollment to full-time equivalent.
# They represent the average course load of part-time students relative
# to full-time students, derived from IPEDS survey methodology.
#
# Source: NCES IPEDS methodology for calculating FTE from headcount.
# The factors are based on the ratio of credit hours taken by part-time
# students compared to full-time students.

PT_FACTOR_UNDERGRAD = 0.403543  # Part-time undergrad converts at ~40%
PT_FACTOR_GRADUATE = 0.361702   # Part-time grad converts at ~36%

# =============================================================================
# EFALEVEL CODES
# =============================================================================
# EFALEVEL is the primary classification variable in EF files.
# It combines attendance status (full-time/part-time) with student level.

EFALEVEL_FT_UNDERGRAD = 22  # Full-time undergraduate
EFALEVEL_FT_GRADUATE = 32   # Full-time graduate (including professional)
EFALEVEL_PT_UNDERGRAD = 42  # Part-time undergraduate
EFALEVEL_PT_GRADUATE = 52   # Part-time graduate (including professional)


def load_ef_file(year: int) -> pd.DataFrame:
    """
    Load EF file and calculate FTE using official IPEDS factors.

    The calculation follows official IPEDS methodology:
        FTE = FT_Undergrad + FT_Graduate +
              (PT_Undergrad x 0.403543) +
              (PT_Graduate x 0.361702)

    Args:
        year: Academic year to process

    Returns:
        DataFrame with columns: unitid, year, fte, enrollment_total,
        enrollment_ft, enrollment_pt
    """
    file_path = IPEDS_RAW_DIR / str(year) / f"ef{year}a.csv"

    if not file_path.exists():
        print(f"  Warning: {file_path.name} not found")
        return pd.DataFrame()

    # Read the EF file
    df = pd.read_csv(file_path)

    # Extract enrollment by level using EFALEVEL codes
    ft_ug = df[df['EFALEVEL'] == EFALEVEL_FT_UNDERGRAD][['UNITID', 'EFTOTLT']].copy()
    ft_ug = ft_ug.rename(columns={'EFTOTLT': 'ft_undergrad'})

    ft_gr = df[df['EFALEVEL'] == EFALEVEL_FT_GRADUATE][['UNITID', 'EFTOTLT']].copy()
    ft_gr = ft_gr.rename(columns={'EFTOTLT': 'ft_graduate'})

    pt_ug = df[df['EFALEVEL'] == EFALEVEL_PT_UNDERGRAD][['UNITID', 'EFTOTLT']].copy()
    pt_ug = pt_ug.rename(columns={'EFTOTLT': 'pt_undergrad'})

    pt_gr = df[df['EFALEVEL'] == EFALEVEL_PT_GRADUATE][['UNITID', 'EFTOTLT']].copy()
    pt_gr = pt_gr.rename(columns={'EFTOTLT': 'pt_graduate'})

    # Merge all components (outer join to include all institutions)
    merged = ft_ug.merge(ft_gr, on='UNITID', how='outer')
    merged = merged.merge(pt_ug, on='UNITID', how='outer')
    merged = merged.merge(pt_gr, on='UNITID', how='outer')

    # Fill missing values with 0 (some schools may not have all student types)
    for col in ['ft_undergrad', 'ft_graduate', 'pt_undergrad', 'pt_graduate']:
        merged[col] = merged[col].fillna(0)

    # Calculate FTE using official IPEDS factors
    merged['fte'] = (
        merged['ft_undergrad'] +
        merged['ft_graduate'] +
        (merged['pt_undergrad'] * PT_FACTOR_UNDERGRAD) +
        (merged['pt_graduate'] * PT_FACTOR_GRADUATE)
    )

    # Calculate totals for reporting and backwards compatibility
    merged['enrollment_ft'] = merged['ft_undergrad'] + merged['ft_graduate']
    merged['enrollment_pt'] = merged['pt_undergrad'] + merged['pt_graduate']
    merged['enrollment_total'] = merged['enrollment_ft'] + merged['enrollment_pt']

    # Add year column
    merged['year'] = year

    # Rename and reorder columns to match DRVEF output schema
    merged = merged.rename(columns={'UNITID': 'unitid'})

    # Convert to appropriate types
    merged['unitid'] = merged['unitid'].astype('int32')
    merged['year'] = merged['year'].astype('int16')
    merged['fte'] = merged['fte'].round().astype('int32')
    merged['enrollment_total'] = merged['enrollment_total'].astype('int32')
    merged['enrollment_ft'] = merged['enrollment_ft'].astype('int32')
    merged['enrollment_pt'] = merged['enrollment_pt'].astype('int32')

    # Return only the columns needed for the enrollment dimension
    return merged[['unitid', 'year', 'fte', 'enrollment_total', 'enrollment_ft', 'enrollment_pt']]


def main():
    print("=" * 60)
    print("IPEDS EF Enrollment Transform (Historical FTE)")
    print("=" * 60)
    print(f"Years: {min(EF_YEARS)}-{max(EF_YEARS)}")
    print()
    print("FTE Calculation (Official IPEDS Methodology):")
    print(f"  FTE = FT_Undergrad + FT_Graduate +")
    print(f"        (PT_Undergrad x {PT_FACTOR_UNDERGRAD}) +")
    print(f"        (PT_Graduate x {PT_FACTOR_GRADUATE})")

    # Load all EF files
    all_data = []

    for year in EF_YEARS:
        print(f"\n{year}:")
        df = load_ef_file(year)
        if len(df) > 0:
            print(f"  Loaded {len(df):,} institutions")
            print(f"  FTE range: {df['fte'].min():,} - {df['fte'].max():,}")
            all_data.append(df)
        else:
            print(f"  No data")

    if not all_data:
        print("\nError: No EF enrollment data found!")
        return 1

    # Combine all years
    combined = pd.concat(all_data, ignore_index=True)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total records: {len(combined):,}")
    print(f"Unique institutions: {combined['unitid'].nunique():,}")
    print(f"Years covered: {sorted(combined['year'].unique())}")
    print(f"FTE range: {combined['fte'].min():,} - {combined['fte'].max():,}")

    # Spot check Yale (130794) - should match expected values
    yale = combined[combined['unitid'] == 130794]
    if len(yale) > 0:
        print("\nSpot check - Yale (130794):")
        print(yale.to_string(index=False))

    # Spot check Harvard (166027)
    harvard = combined[combined['unitid'] == 166027]
    if len(harvard) > 0:
        print("\nSpot check - Harvard (166027):")
        print(harvard.to_string(index=False))

    # Spot check UPenn (215293)
    upenn = combined[combined['unitid'] == 215293]
    if len(upenn) > 0:
        print("\nSpot check - UPenn (215293):")
        print(upenn.to_string(index=False))

    # Save to parquet
    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CURATED_DIR / "dim_enrollment_ef.parquet"
    combined.to_parquet(output_path, index=False)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 02a_transform_enrollment.py (to combine with DRVEF)")
    print("2. Run: python 04_create_aggregates.py")
    print("3. Run: python 05_generate_json.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
