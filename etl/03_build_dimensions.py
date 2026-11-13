"""
Build dimension tables for institutions and offenses.

This script creates dimension tables that enrich the fact data:
- dim_institution: School metadata with Ivy League flags, for every campus
  that reported at least one year (campus_year_sources.parquet), including
  campuses that never had an incident
- dim_offense: Offense metadata with descriptions and ordering

Usage:
    python 03_build_dimensions.py
"""

import os
import sys
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, IVY_LEAGUE, IVY_BASE_UNITIDS, OFFENSE_ORDER_MAP,
    OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, US_STATES, VALID_STATE_CODES,
    PROCESS_ALL_SCHOOLS
)
import provenance

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"
# The campus-years DOE published (02_transform_to_parquet.py): a campus-year
# is reported when its release row has at least one count cell that is not
# blank, so a campus that reported only zeros is in it but not in the facts
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"


def find_stray_facts() -> list:
    """Parquet data under data/curated/facts other than FACTS_PATH."""
    def fail(err):
        raise err

    stray = []
    for root, dirs, files in os.walk(FACTS_PATH.parent, onerror=fail):
        root = Path(root)
        for name in list(dirs):
            if name.lower() == "incidents" or name.lower().endswith(".parquet"):
                stray.append(root / name)
                dirs.remove(name)
        for name in files:
            if name.lower().endswith(".parquet") and root / name != FACTS_PATH:
                stray.append(root / name)
    return sorted(stray)


def get_facts_path() -> str:
    """FACTS_PATH, after checking that nothing else there could be read as facts."""
    stray = find_stray_facts()
    if stray:
        listing = "\n".join(f"  {p}{' (folder)' if p.is_dir() else ''}" for p in stray)
        raise RuntimeError(
            f"{FACTS_PATH.parent} holds parquet data that 02_transform_to_parquet.py "
            f"did not write:\n{listing}\n"
            f"Only the file {FACTS_PATH.name} belongs there. Delete the items listed above "
            f"(move them outside data/curated to keep them), then run this step again."
        )
    if not FACTS_PATH.is_file():
        raise RuntimeError(f"{FACTS_PATH} not found. Run 02_transform_to_parquet.py first.")
    return str(FACTS_PATH)


def facts_read_error(err: Exception) -> RuntimeError:
    return RuntimeError(
        f"Could not read {FACTS_PATH}: {err}\n"
        f"If another program (sync, backup or antivirus) has the file open, close it and "
        f"run this step again. Otherwise run 02_transform_to_parquet.py again."
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

    # Get unique UNITIDs from facts (a read error stops the build)
    facts_file = get_facts_path()
    try:
        fact_ids = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_file}')
            ORDER BY unitid
        """).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e

    # Every campus that reported a year, incidents or not: a reported year
    # with no incident is a 0, which its school page and the rankings show
    if not SOURCES_PATH.is_file():
        raise RuntimeError(f"{SOURCES_PATH} not found. Run 02_transform_to_parquet.py first.")
    reported_ids = set(pd.read_parquet(SOURCES_PATH, columns=["unitid"])["unitid"].astype(int).tolist())
    fact_set = set(fact_ids["unitid"].astype(int).tolist())
    unreported = sorted(fact_set - reported_ids)
    if unreported:
        raise RuntimeError(f"{len(unreported)} schools have incidents but no reported campus-year in "
                           f"{SOURCES_PATH.name} (UNITIDs {unreported[:10]}). Run 02_transform_to_parquet.py "
                           "again, then this step.")
    unitids_df = pd.DataFrame({"unitid": sorted(reported_ids)})

    print(f"  Found {len(unitids_df)} campuses that reported a year ({len(fact_set)} with incidents, "
          f"{len(reported_ids - fact_set)} that only ever reported zeros)")

    # Names, cities and states come from the institution list that 02 writes
    raw_inst_path = dims_dir / "raw_institutions.parquet"
    if not raw_inst_path.is_file():
        raise RuntimeError(f"{raw_inst_path} not found. Run 02_transform_to_parquet.py first.")
    raw_inst = pd.read_parquet(raw_inst_path)
    raw_inst.columns = raw_inst.columns.str.upper()
    print(f"  Loaded raw institution data: {len(raw_inst)} rows")
    missing_cols = [c for c in ("INSTNM", "CITY") if c not in raw_inst.columns]
    if not {"UNITID", "UNITID_P"} & set(raw_inst.columns):
        missing_cols.append("UNITID_P")
    if not {"STATE", "STABBR"} & set(raw_inst.columns):
        missing_cols.append("STATE")
    if missing_cols:
        raise RuntimeError(
            f"{raw_inst_path} has no {', '.join(missing_cols)} column. "
            f"Run 02_transform_to_parquet.py again and check the DOE file layout."
        )

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

        # Get info from raw institutions
        # Check various possible column names for UNITID
        unitid_col = None
        for col in ["UNITID", "UNITID_P"]:
            if col in raw_inst.columns:
                unitid_col = col
                break

        if unitid_col:
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

    # A school without a name would drop out of the "All" totals in step 04
    missing = dim_institution.loc[dim_institution["institution_name"].isna(), "unitid"].tolist()
    if missing:
        raise RuntimeError(
            f"{len(missing)} reporting schools have no name in {raw_inst_path.name} "
            f"(UNITIDs {missing[:10]}). Run 02_transform_to_parquet.py again, then this step."
        )

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

    print(f"  Total institutions: {len(dim_institution)}")
    print(f"  Main campuses: {main_count}")
    print(f"  Branch campuses: {branch_count}")
    print(f"  Ivy League: {ivy_count}")
    print(f"  States with data: {states_with_data}")

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

    # Get unique offenses from facts (a read error stops the build)
    facts_file = get_facts_path()
    try:
        offenses_df = con.execute(f"""
            SELECT DISTINCT
                offense,
                offense_family
            FROM read_parquet('{facts_file}')
            ORDER BY offense
        """).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e
    offenses_df["definition_version"] = "post_2015"

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

    # The files this step reads, checked against 02's record before reading
    dims = CURATED_DIR / "dims"
    inputs_before = provenance.Snapshot("03", [FACTS_PATH, dims / "raw_institutions.parquet", SOURCES_PATH])
    provenance.invalidate(provenance.INSTITUTION_MANIFEST)
    dim_institution = build_dim_institution()
    dim_offense = build_dim_offense()
    provenance.write_institution_manifest(
        inputs_before, outputs=[dims / "dim_institution.parquet", dims / "dim_offense.parquet"])

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Institutions: {len(dim_institution)}")
    print(f"Offenses: {len(dim_offense)}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 04_create_aggregates.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("03", main))
