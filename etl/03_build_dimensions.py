"""
Build dimension tables for institutions and offenses.

This script creates dimension tables that enrich the fact data:
- dim_institution: School metadata with Ivy League flags
- dim_offense: Offense metadata with descriptions and ordering

Usage:
    python 03_build_dimensions.py
"""

import sys
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, IVY_LEAGUE, IVY_BASE_UNITIDS, OFFENSE_ORDER, OFFENSE_ORDER_MAP,
    OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, US_STATES, VALID_STATE_CODES,
    PROCESS_ALL_SCHOOLS
)


def build_dim_institution() -> pd.DataFrame:
    """
    Create institution dimension with Ivy League flags.

    Schema:
        unitid: int32                # Primary key
        institution_name: string     # Full name
        short_name: string           # Short name (Ivy only)
        city: string
        state: string (2-char)
        ivy_league: boolean
        sector: string               # Optional, from raw data
    """
    print("Building institution dimension...")

    dims_dir = CURATED_DIR / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()

    # Get unique UNITIDs from facts
    facts_path = CURATED_DIR / "facts"

    # Check for partitioned or single file
    if (facts_path / "incidents").exists():
        facts_pattern = str(facts_path / "incidents" / "**" / "*.parquet")
    else:
        facts_pattern = str(facts_path / "*.parquet")

    try:
        unitids_df = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_pattern}')
            ORDER BY unitid
        """).df()
    except Exception as e:
        print(f"Error reading facts: {e}")
        # Create from Ivy League config only
        unitids_df = pd.DataFrame({"unitid": list(IVY_LEAGUE.keys())})

    print(f"  Found {len(unitids_df)} unique institutions in facts")

    # Try to get additional info from raw institutions if available
    raw_inst_path = dims_dir / "raw_institutions.parquet"
    raw_inst = None
    if raw_inst_path.exists():
        raw_inst = pd.read_parquet(raw_inst_path)
        raw_inst.columns = raw_inst.columns.str.upper()
        print(f"  Loaded raw institution data: {len(raw_inst)} rows")

    # Build dimension
    records = []

    for unitid in unitids_df["unitid"]:
        # Check if this is an Ivy League school (by base unitid)
        base_unitid = int(unitid) // 1000
        is_ivy = base_unitid in IVY_BASE_UNITIDS

        # Determine campus type based on UNITID suffix
        # Main campuses typically end in 001, branches have other suffixes
        branch_suffix = int(unitid) % 1000
        is_main_campus = (branch_suffix == 1)

        record = {
            "unitid": int(unitid),
            "base_unitid": base_unitid,
            "is_main_campus": is_main_campus,
            "institution_name": None,
            "short_name": None,
            "city": None,
            "state": None,
            "ivy_league": is_ivy,
            "sector": None,
        }

        # Add Ivy League info (use main campus info for all branches)
        if is_ivy:
            # Find the main campus unitid (base * 1000 + 1)
            main_campus_uid = base_unitid * 1000 + 1
            if main_campus_uid in IVY_LEAGUE:
                ivy_info = IVY_LEAGUE[main_campus_uid]
                record["institution_name"] = ivy_info["name"]
                record["short_name"] = ivy_info["short"]
                record["city"] = ivy_info["city"]
                record["state"] = ivy_info["state"]

        # Try to get info from raw institutions
        # Check various possible column names for UNITID
        unitid_col = None
        for col in ["UNITID", "UNITID_P"]:
            if raw_inst is not None and col in raw_inst.columns:
                unitid_col = col
                break

        if raw_inst is not None and unitid_col:
            # Match unitid directly (UNITID_P is same format, just float)
            row = raw_inst[raw_inst[unitid_col].astype(int) == unitid]

            if len(row) > 0:
                row = row.iloc[0]
                if record["institution_name"] is None and "INSTNM" in row.index:
                    record["institution_name"] = row.get("INSTNM")
                if record["city"] is None and "CITY" in row.index:
                    record["city"] = row.get("CITY")
                # Check for STATE or STABBR column
                if record["state"] is None:
                    if "STATE" in row.index:
                        record["state"] = row.get("STATE")
                    elif "STABBR" in row.index:
                        record["state"] = row.get("STABBR")
                if "SECTOR_DESC" in row.index:
                    record["sector"] = row.get("SECTOR_DESC")

        records.append(record)

    dim_institution = pd.DataFrame(records)

    # Add state_name column from config
    dim_institution["state_name"] = dim_institution["state"].map(
        lambda x: US_STATES.get(x, x) if pd.notna(x) else None
    )

    # Ensure proper types
    dim_institution["unitid"] = dim_institution["unitid"].astype("int32")
    dim_institution["base_unitid"] = dim_institution["base_unitid"].astype("int32")
    dim_institution["is_main_campus"] = dim_institution["is_main_campus"].astype(bool)
    dim_institution["ivy_league"] = dim_institution["ivy_league"].astype(bool)

    # Save
    output_path = dims_dir / "dim_institution.parquet"
    dim_institution.to_parquet(output_path, index=False)

    # Summary
    ivy_count = dim_institution["ivy_league"].sum()
    main_count = dim_institution["is_main_campus"].sum()
    branch_count = len(dim_institution) - main_count
    states_with_data = dim_institution["state"].dropna().nunique()
    missing_names = dim_institution["institution_name"].isna().sum()

    print(f"  Total institutions: {len(dim_institution)}")
    print(f"  Main campuses: {main_count}")
    print(f"  Branch campuses: {branch_count}")
    print(f"  Ivy League: {ivy_count}")
    print(f"  States with data: {states_with_data}")
    if missing_names > 0:
        print(f"  WARNING: {missing_names} institutions missing names")

    # Show top states by school count
    if PROCESS_ALL_SCHOOLS and len(dim_institution) > 100:
        state_counts = dim_institution["state"].value_counts().head(10)
        print("\n  Top 10 states by school count:")
        for state, count in state_counts.items():
            state_name = US_STATES.get(state, state)
            print(f"    {state} ({state_name}): {count}")

    print(f"\n  Saved to: {output_path}")

    return dim_institution


def build_dim_offense() -> pd.DataFrame:
    """
    Create offense dimension with metadata.

    Schema:
        offense: string              # Primary key
        offense_family: string       # "Criminal", "VAWA", etc.
        family_display: string       # "Criminal Offenses"
        description: string          # Full description
        display_order: int16         # For consistent UI ordering
        definition_version: string   # "post_2015"
        comparable_from_year: int16  # 2015
    """
    print("\nBuilding offense dimension...")

    dims_dir = CURATED_DIR / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()

    # Get unique offenses from facts
    facts_path = CURATED_DIR / "facts"

    if (facts_path / "incidents").exists():
        facts_pattern = str(facts_path / "incidents" / "**" / "*.parquet")
    else:
        facts_pattern = str(facts_path / "*.parquet")

    try:
        offenses_df = con.execute(f"""
            SELECT DISTINCT
                offense,
                offense_family
            FROM read_parquet('{facts_pattern}')
            ORDER BY offense
        """).df()
        offenses_df["definition_version"] = "post_2015"
    except Exception as e:
        print(f"Error reading facts: {e}")
        # Create from config
        offenses_df = pd.DataFrame([
            {"offense": o, "offense_family": "Criminal", "definition_version": "post_2015"}
            for o in OFFENSE_ORDER
        ])

    print(f"  Found {len(offenses_df)} unique offenses")

    # Enrich with metadata
    records = []

    for _, row in offenses_df.iterrows():
        offense = row["offense"]
        family = row["offense_family"]

        record = {
            "offense": offense,
            "offense_family": family,
            "family_display": OFFENSE_FAMILIES.get(family, {}).get("display", family),
            "description": OFFENSE_DESCRIPTIONS.get(offense, ""),
            "display_order": OFFENSE_ORDER_MAP.get(offense, 999),
            "definition_version": row["definition_version"],
            "comparable_from_year": 2015,
        }

        records.append(record)

    dim_offense = pd.DataFrame(records)

    # Sort by display order
    dim_offense = dim_offense.sort_values("display_order").reset_index(drop=True)

    # Ensure proper types
    dim_offense["display_order"] = dim_offense["display_order"].astype("int16")
    dim_offense["comparable_from_year"] = dim_offense["comparable_from_year"].astype("int16")

    # Save
    output_path = dims_dir / "dim_offense.parquet"
    dim_offense.to_parquet(output_path, index=False)

    # Summary
    print(f"  Total offenses: {len(dim_offense)}")
    print(f"  Families: {dim_offense['offense_family'].nunique()}")
    print(f"  Saved to: {output_path}")

    # Show offense list
    print("\n  Offense order:")
    for _, row in dim_offense.iterrows():
        print(f"    {row['display_order']:2d}. {row['offense']} ({row['offense_family']})")

    return dim_offense


def main():
    print("=" * 60)
    print("Building Dimension Tables")
    print("=" * 60)

    dim_institution = build_dim_institution()
    dim_offense = build_dim_offense()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Institutions: {len(dim_institution)}")
    print(f"Offenses: {len(dim_offense)}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 04_create_aggregates.py")


if __name__ == "__main__":
    main()
