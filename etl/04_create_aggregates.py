"""
Create pre-aggregated tables for fast UI queries.

This script creates aggregate tables that power the dashboard:
- agg_school_year_offense: Summary by school, year, offense, geography (every
  school's full DOE figures, as its profile shows them)
- shared_blocks: statistics that DOE reports identically for two or more
  campuses (see find_shared_blocks), and the one campus they are counted under
- agg_ivy_rankings, agg_state_rankings, agg_national_rankings: rankings by
  year/offense/geography, in which shared statistics are counted once

Usage:
    python 04_create_aggregates.py
    python 04_create_aggregates.py --ivy-only
"""

import os
import sys
import argparse
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, IVY_LEAGUE, GEO_FOR_ALL, US_STATES, PROCESS_ALL_SCHOOLS, OFFENSE_ORDER,
                    SHARED_MIN_NONZERO)
import provenance

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"
# The DOE release each campus-year was taken from (02_transform_to_parquet.py)
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"
# Statistics reported identically by two or more campuses (find_shared_blocks)
SHARED_PATH = CURATED_DIR / "aggs" / "shared_blocks.parquet"

# Shared (copied) statistics. Some DOE rows repeat another campus's numbers:
# a medical school's sites report their university's main campus figures, a
# divinity or law school its university's, several institutions on one
# shared campus the same figures, and a renumbered campus appears under its
# old and new UNITID. Added up, those numbers would be counted twice in state
# and national totals and ranked as separate schools.
#
# A block is one campus's figures for one year and one geography of
# GEO_FOR_ALL (residence halls are a subset of on-campus and are not
# compared): its 20 cells, one per offense in OFFENSE_ORDER (11 criminal, 3
# VAWA, 3 arrest, 3 disciplinary), a blank cell counting as 0. Blocks of the
# same year and geography are copies when all 20 cells are equal, at least
# SHARED_MIN_NONZERO (config.py) of them are not 0, and the campuses are in
# the same state. Fewer nonzero cells match by chance too often to call a copy.


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


def load_school_agg() -> pd.DataFrame:
    """The school-year-offense aggregate this step writes first."""
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    if not agg_path.is_file():
        raise RuntimeError(f"{agg_path} not found. Run 04_create_aggregates.py again.")
    return pd.read_parquet(agg_path)


def load_enrollment_data() -> pd.DataFrame:
    """
    Load enrollment data with FTE for rate calculations.
    Returns DataFrame with unitid, year, fte columns.
    """
    enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    if not enrollment_path.is_file():
        raise RuntimeError(
            f"{enrollment_path} not found, so no rates can be calculated. "
            f"Run 01b_download_ipeds.py, 02b_transform_ef_enrollment.py and "
            f"02a_transform_enrollment.py first."
        )

    df = pd.read_parquet(enrollment_path)
    # A repeated school-year would duplicate aggregate rows in the join
    dups = int(df.duplicated(["unitid", "year"]).sum())
    if dups:
        raise RuntimeError(
            f"{enrollment_path} has {dups} repeated school-year rows, which would double counts. "
            f"Run 02a_transform_enrollment.py again."
        )
    # Only need unitid, year, fte for joining
    return df[["unitid", "year", "fte"]]


def load_dim_institution() -> pd.DataFrame:
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")
    return pd.read_parquet(dims_path)


def create_school_year_offense_agg(ivy_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Aggregate: (year, unitid, offense, geo) -> count, every school's full
    DOE figures (the school profiles show these). Saved as
    agg_school_year_offense.parquet.

    Returns (the aggregate, the fact rows it was built from).
    """
    print("Creating school-year-offense aggregate...")
    base = load_fact_rows(ivy_only)
    agg = build_school_agg(base, load_dim_institution(), load_enrollment_data())

    # Save
    agg_dir = CURATED_DIR / "aggs"
    agg_dir.mkdir(parents=True, exist_ok=True)

    output_path = agg_dir / "agg_school_year_offense.parquet"
    agg.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    return agg, base


def load_fact_rows(ivy_only: bool = False) -> pd.DataFrame:
    """(year, unitid, offense, offense_family, geo) -> count, from the fact table."""
    con = duckdb.connect()
    facts_file = get_facts_path()

    # Base aggregation query
    query = f"""
    SELECT
        f.year,
        f.unitid,
        f.offense,
        f.offense_family,
        f.geo,
        SUM(f.count) as count
    FROM read_parquet('{facts_file}') f
    """

    if ivy_only:
        ivy_list = ", ".join(str(u) for u in IVY_LEAGUE.keys())
        query += f" WHERE f.unitid IN ({ivy_list})"

    query += """
    GROUP BY f.year, f.unitid, f.offense, f.offense_family, f.geo
    ORDER BY f.year, f.unitid, f.offense, f.geo
    """

    try:
        agg = con.execute(query).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e
    print(f"  Base aggregation: {len(agg):,} records")
    return agg


def build_school_agg(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame) -> pd.DataFrame:
    """
    The school-year-offense aggregate of the fact rows `base` (load_fact_rows).

    Also creates an "All" geography that sums On-campus + Non-campus + Public property
    (excluding Residence halls to avoid double-counting).

    Schema:
        year: int16
        unitid: int32
        institution_name: string     # Denormalized for convenience
        offense: string
        offense_family: string
        geo: string
        count: int32
        fte: int32                   # FTE enrollment (may be null)
        rate_per_10k: float          # Rate per 10,000 FTE students (may be null)
    """
    agg = base.copy()

    # Add institution names from dimension
    name_map = dim_inst.set_index("unitid")["institution_name"].to_dict()
    agg["institution_name"] = agg["unitid"].map(name_map)

    # Create "All" geography aggregation
    # Sum On-campus + Non-campus + Public property (not Residence halls)
    geo_filter = agg["geo"].isin(GEO_FOR_ALL)
    all_geo = agg[geo_filter].copy()
    all_geo["geo"] = "All"

    # groupby drops rows with an empty key, which would lose their counts
    group_keys = ["year", "unitid", "institution_name", "offense", "offense_family", "geo"]
    no_key = all_geo[all_geo[group_keys].isna().any(axis=1)]
    if len(no_key) > 0:
        cols = [c for c in group_keys if all_geo[c].isna().any()]
        raise RuntimeError(
            f"{len(no_key):,} aggregate rows have no {', '.join(cols)} "
            f"(UNITIDs {sorted(no_key['unitid'].unique().tolist())[:10]}). "
            f"Run 02_transform_to_parquet.py and 03_build_dimensions.py again, then this step."
        )

    all_geo_agg = all_geo.groupby(group_keys, as_index=False)["count"].sum()

    # Combine with original
    agg = pd.concat([agg, all_geo_agg], ignore_index=True)

    # Join enrollment data for FTE and rate calculations
    # Note: Crime data uses extended UNITID format (UNITID * 1000 + branch)
    # IPEDS uses base UNITID, so we need to extract base UNITID for joining
    print(f"  Joining enrollment data ({len(enrollment):,} records)...")
    # Extract base UNITID from extended format
    agg["base_unitid"] = (agg["unitid"] // 1000).astype("int32")
    # Join on base_unitid and year
    agg = agg.merge(enrollment, left_on=["base_unitid", "year"], right_on=["unitid", "year"], how="left", suffixes=("", "_enroll"))
    # Drop the duplicate unitid column from enrollment
    agg = agg.drop(columns=["unitid_enroll"], errors="ignore")
    agg = agg.drop(columns=["base_unitid"])
    # Calculate rate per 10,000 FTE students
    agg["rate_per_10k"] = (agg["count"] / agg["fte"] * 10000).round(2)
    # Handle division by zero or missing FTE
    agg.loc[agg["fte"].isna() | (agg["fte"] == 0), "rate_per_10k"] = None
    matched = agg["fte"].notna().sum()
    print(f"  Matched enrollment: {matched:,} / {len(agg):,} records ({matched/len(agg)*100:.1f}%)")

    # Ensure proper types
    agg["year"] = agg["year"].astype("int16")
    agg["unitid"] = agg["unitid"].astype("int32")
    agg["count"] = agg["count"].astype("int32")
    # FTE may have nulls, so use nullable int
    agg["fte"] = agg["fte"].astype("Int32")

    # Sort
    agg = agg.sort_values(["year", "unitid", "offense", "geo"]).reset_index(drop=True)

    print(f"  With 'All' geography: {len(agg):,} records")

    return agg


def load_campus_year_sources() -> pd.DataFrame:
    if not SOURCES_PATH.is_file():
        raise RuntimeError(f"{SOURCES_PATH} not found. Run 02_transform_to_parquet.py first.")
    return pd.read_parquet(SOURCES_PATH)


def find_shared_blocks(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame,
                       sources: pd.DataFrame) -> pd.DataFrame:
    """
    The blocks that two or more campuses report identically (see
    SHARED_MIN_NONZERO above), one row per campus and block. In each copy
    group one campus is the host, the campus the figures are counted under;
    the others are shadows. The host is the first campus by:
      1. its campus-year is taken from the newest DOE release that covers
         the year, not restored from an older one (campus_year_sources),
      2. it is a main campus (UNITID_P ending in 001),
      3. larger FTE that year (the FTE rates use; no FTE sorts last),
      4. larger total for the campus-year over GEO_FOR_ALL,
      5. lower UNITID_P.

    Schema:
        year: int16, geo: string, state: string   # the block
        group: int32                 # copy group, numbered within the table
        unitid: int32
        role: string                 # "host" or "shadow"
        host_unitid: int32           # the group's host
        group_size: int16            # campuses in the group
        nonzero_cells: int16         # cells of the block that are not 0
        block_count: int32           # sum of the block's 20 cells
    """
    unknown = sorted(set(base["offense"]) - set(OFFENSE_ORDER))
    if unknown:
        raise RuntimeError(f"The facts hold offenses not in OFFENSE_ORDER ({', '.join(unknown)}), so shared "
                           "statistics cannot be compared cell by cell. Add them to OFFENSE_ORDER in config.py.")
    rows = base[base["geo"].isin(GEO_FOR_ALL)]
    cells = rows.pivot_table(index=["year", "geo", "unitid"], columns="offense", values="count",
                             aggfunc="sum", fill_value=0)
    cells = cells.reindex(columns=OFFENSE_ORDER, fill_value=0).astype("int64")
    nonzero = (cells != 0).sum(axis=1)
    blocks = cells[nonzero >= SHARED_MIN_NONZERO].reset_index()
    blocks["nonzero_cells"] = nonzero[nonzero >= SHARED_MIN_NONZERO].to_numpy()
    blocks["block_count"] = blocks[OFFENSE_ORDER].sum(axis=1)

    # Copies are looked for within one state, among the campuses that state and
    # national rankings count (a state in US_STATES). A campus with a blank
    # state or another code is never ranked, so nothing of it is counted twice.
    blocks["state"] = blocks["unitid"].map(dim_inst.set_index("unitid")["state"])
    blocks = blocks[blocks["state"].isin(US_STATES.keys())]
    key = ["year", "geo", "state"] + OFFENSE_ORDER
    blocks["group_size"] = blocks.groupby(key)["unitid"].transform("size")
    blocks = blocks[blocks["group_size"] >= 2].copy()
    blocks["group"] = blocks.groupby(key, sort=True).ngroup()

    # What chooses the host
    restored = sources.set_index(["unitid", "year"])["restored"]
    blocks["restored"] = [restored.get((u, y)) for u, y in zip(blocks["unitid"].tolist(), blocks["year"].tolist())]
    if blocks["restored"].isna().any():
        first = blocks[blocks["restored"].isna()].iloc[0]
        raise RuntimeError(f"{SOURCES_PATH.name} has no release for campus {first['unitid']} in {first['year']}, "
                           "which has fact rows. Run 02_transform_to_parquet.py again, then 03 and this step.")
    fte = enrollment.assign(unitid=enrollment["unitid"].astype("int64")).set_index(["unitid", "year"])["fte"]
    blocks["fte"] = [fte.get((u // 1000, y)) for u, y in zip(blocks["unitid"].tolist(), blocks["year"].tolist())]
    totals = rows.groupby(["unitid", "year"])["count"].sum()
    blocks["campus_total"] = [totals[(u, y)] for u, y in zip(blocks["unitid"].tolist(), blocks["year"].tolist())]
    blocks["by_restored"] = blocks["restored"].astype(bool).astype(int)       # newest release first
    blocks["by_branch"] = (blocks["unitid"] % 1000 != 1).astype(int)          # main campus first
    blocks["by_fte"] = (-pd.to_numeric(blocks["fte"], errors="coerce").astype("float64")).fillna(float("inf"))
    blocks["by_total"] = -blocks["campus_total"].astype("float64")
    blocks = blocks.sort_values(["group", "by_restored", "by_branch", "by_fte", "by_total", "unitid"],
                                kind="mergesort")
    blocks["host_unitid"] = blocks.groupby("group")["unitid"].transform("first")
    blocks["role"] = (blocks["unitid"] == blocks["host_unitid"]).map({True: "host", False: "shadow"})

    shared = blocks[["year", "geo", "state", "group", "unitid", "role", "host_unitid", "group_size",
                     "nonzero_cells", "block_count"]].copy()
    shared = shared.astype({"year": "int16", "group": "int32", "unitid": "int32", "host_unitid": "int32",
                            "group_size": "int16", "nonzero_cells": "int16", "block_count": "int32"})
    return shared.sort_values(["year", "geo", "group", "role", "unitid"]).reset_index(drop=True)


def create_shared_blocks(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame) -> pd.DataFrame:
    """Find the shared blocks (find_shared_blocks), save them and print what they take out of the rankings."""
    print("\nFinding statistics reported identically by two or more campuses...")
    shared = find_shared_blocks(base, dim_inst, enrollment, load_campus_year_sources())
    shared.to_parquet(SHARED_PATH, index=False)
    shadows = shared[shared["role"] == "shadow"]
    print(f"  Copy groups: {shared['group'].nunique():,}; shadow blocks (counted once, under the host): "
          f"{len(shadows):,}; counts not added again: {int(shadows['block_count'].sum()):,}")
    for year, part in shared.groupby("year"):
        s = part[part["role"] == "shadow"]
        print(f"    {year}: {part['group'].nunique():,} groups, {len(s):,} shadow blocks, "
              f"{int(s['block_count'].sum()):,} counts")
    print(f"  Saved to: {SHARED_PATH}")
    return shared


def without_shadows(base: pd.DataFrame, shared: pd.DataFrame) -> pd.DataFrame:
    """The fact rows `base` without the shadow blocks: what totals and rankings count."""
    shadows = shared[shared["role"] == "shadow"]
    drop = set(zip(shadows["year"].astype(int).tolist(), shadows["geo"].tolist(), shadows["unitid"].astype(int).tolist()))
    keep = [(y, g, u) not in drop for y, g, u in zip(base["year"].astype(int).tolist(), base["geo"].tolist(),
                                                       base["unitid"].astype(int).tolist())]
    kept = base[keep].reset_index(drop=True)
    print(f"  Fact rows counted in totals and rankings: {len(kept):,} of {len(base):,}")
    return kept


def create_ivy_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute Ivy League rankings for all year/offense/geo combinations.

    Schema:
        year: int16
        offense: string
        geo: string
        rank: int8                   # 1-8 for Ivy League
        rank_by_rate: int8           # Rank by rate per 10k (may be null)
        unitid: int32
        institution_name: string
        short_name: string
        count: int32
        pct_of_ivy_total: float      # Percent of total Ivy incidents
        fte: int32                   # FTE enrollment (may be null)
        rate_per_10k: float          # Rate per 10,000 FTE students (may be null)
    """
    print("\nCreating Ivy League rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Filter to Ivy League only
    ivy_unitids = set(IVY_LEAGUE.keys())
    ivy_data = school_agg[school_agg["unitid"].isin(ivy_unitids)].copy()

    if len(ivy_data) == 0:
        raise RuntimeError("No Ivy League schools in the aggregate. Check the facts from 02_transform_to_parquet.py.")

    print(f"  Ivy League records: {len(ivy_data):,}")

    # Add short names
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    ivy_data["short_name"] = ivy_data["unitid"].map(short_map)

    # Calculate rankings within each (year, offense, geo) group
    rankings = []

    groups = ivy_data.groupby(["year", "offense", "geo"])

    for (year, offense, geo), group in groups:
        # Sort by count descending, then by name for deterministic tie-breaking
        sorted_group = group.sort_values(
            ["count", "institution_name"],
            ascending=[False, True]
        ).reset_index(drop=True)

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        # Create rank by rate (only for schools with FTE data)
        # Sort by rate descending, then by name for deterministic tie-breaking
        rate_ranks = {}
        schools_with_rate = sorted_group[sorted_group["rate_per_10k"].notna()].copy() if "rate_per_10k" in sorted_group.columns else pd.DataFrame()
        if len(schools_with_rate) > 0:
            schools_with_rate = schools_with_rate.sort_values(
                ["rate_per_10k", "institution_name"],
                ascending=[False, True]
            )
            for rate_rank, (_, rate_row) in enumerate(schools_with_rate.iterrows(), 1):
                rate_ranks[rate_row["unitid"]] = rate_rank

        for rank, (_, row) in enumerate(sorted_group.iterrows(), 1):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "rank_by_rate": rate_ranks.get(row["unitid"]),
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row["short_name"],
                "count": row["count"],
                "pct_of_ivy_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
                "rate_per_10k": row.get("rate_per_10k") if pd.notna(row.get("rate_per_10k")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int8")
    rankings_df["rank_by_rate"] = rankings_df["rank_by_rate"].astype("Int8")  # Nullable
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_ivy_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  Rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    Offenses: {rankings_df['offense'].nunique()}")
    print(f"    Schools: {rankings_df['unitid'].nunique()}")

    # Show sample ranking for most recent year
    latest_year = rankings_df["year"].max()
    sample = rankings_df[
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Rape") &
        (rankings_df["geo"] == "All")
    ].head(8)

    if not sample.empty:
        print(f"\n  Sample: Rape rankings ({latest_year}, All locations):")
        for _, row in sample.iterrows():
            print(f"    {row['rank']}. {row['short_name']}: {row['count']} ({row['pct_of_ivy_total']:.1f}%)")

    return rankings_df


def create_state_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute state-based rankings for all year/offense/geo/state combinations.

    Schema:
        state: string                # State code (CA, NY, etc.)
        year: int16
        offense: string
        geo: string
        rank: int16                  # Rank within state
        rank_by_rate: int16          # Rank by rate per 10k (may be null)
        unitid: int32
        institution_name: string
        short_name: string           # May be null for non-Ivy
        count: int32
        pct_of_state_total: float    # Percent of state's total incidents
        fte: int32                   # FTE enrollment (may be null)
        rate_per_10k: float          # Rate per 10,000 FTE students (may be null)
    """
    print("\nCreating state-based rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only (schools with a blank state or a code not in US_STATES are not ranked)
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        raise RuntimeError(f"No school in the aggregate has a U.S. state code. Check {dims_path.name}.")

    states_in_data = valid_data["state"].nunique()
    print(f"  Records with valid states: {len(valid_data):,}")
    print(f"  States represented: {states_in_data}")

    # Add short names (only for Ivy League schools)
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    valid_data["short_name"] = valid_data["unitid"].map(short_map)

    # Calculate rankings within each (state, year, offense, geo) group
    rankings = []

    groups = valid_data.groupby(["state", "year", "offense", "geo"])
    total_groups = len(groups)

    for i, ((state, year, offense, geo), group) in enumerate(groups):
        if i % 10000 == 0 and i > 0:
            print(f"  Processed {i:,}/{total_groups:,} groups...")

        # Sort by count descending, then by name for deterministic tie-breaking
        sorted_group = group.sort_values(
            ["count", "institution_name"],
            ascending=[False, True]
        ).reset_index(drop=True)

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        # Create rank by rate (only for schools with FTE data)
        # Sort by rate descending, then by name for deterministic tie-breaking
        rate_ranks = {}
        schools_with_rate = sorted_group[sorted_group["rate_per_10k"].notna()].copy() if "rate_per_10k" in sorted_group.columns else pd.DataFrame()
        if len(schools_with_rate) > 0:
            schools_with_rate = schools_with_rate.sort_values(
                ["rate_per_10k", "institution_name"],
                ascending=[False, True]
            )
            for rate_rank, (_, rate_row) in enumerate(schools_with_rate.iterrows(), 1):
                rate_ranks[rate_row["unitid"]] = rate_rank

        for rank, (_, row) in enumerate(sorted_group.iterrows(), 1):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "state": state,
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "rank_by_rate": rate_ranks.get(row["unitid"]),
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row.get("short_name"),
                "count": row["count"],
                "pct_of_state_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
                "rate_per_10k": row.get("rate_per_10k") if pd.notna(row.get("rate_per_10k")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    if len(rankings_df) == 0:
        raise RuntimeError("No rankings were generated from the aggregate.")

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int16")
    rankings_df["rank_by_rate"] = rankings_df["rank_by_rate"].astype("Int16")  # Nullable
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["state", "year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Total ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_state_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  State rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    States: {rankings_df['state'].nunique()}")
    print(f"    Total schools: {rankings_df['unitid'].nunique()}")

    # Show sample for California
    latest_year = rankings_df["year"].max()
    ca_sample = rankings_df[
        (rankings_df["state"] == "CA") &
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Burglary") &
        (rankings_df["geo"] == "All")
    ].head(5)

    if not ca_sample.empty:
        print(f"\n  Sample: CA Burglary rankings ({latest_year}, All locations, top 5):")
        for _, row in ca_sample.iterrows():
            name = row["short_name"] or row["institution_name"][:30]
            print(f"    {row['rank']}. {name}: {row['count']} ({row['pct_of_state_total']:.1f}%)")

    return rankings_df


def create_national_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute national rankings for all schools across all year/offense/geo combinations.

    Schema:
        year: int16
        offense: string
        geo: string
        rank: int16                  # Rank nationally (by count)
        rank_by_rate: int16          # Rank nationally (by rate per 10k)
        unitid: int32
        institution_name: string
        short_name: string           # May be null for non-Ivy
        state: string
        count: int32
        pct_of_national_total: float # Percent of national total incidents
        fte: int32                   # FTE enrollment (may be null)
        rate_per_10k: float          # Rate per 10,000 FTE students (may be null)
    """
    print("\nCreating national rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only (schools with a blank state or a code not in US_STATES are not ranked)
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        raise RuntimeError(f"No school in the aggregate has a U.S. state code. Check {dims_path.name}.")

    print(f"  Records with valid states: {len(valid_data):,}")
    print(f"  Total unique schools: {valid_data['unitid'].nunique()}")

    # Add short names (only for Ivy League schools)
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    valid_data["short_name"] = valid_data["unitid"].map(short_map)

    # Calculate rankings within each (year, offense, geo) group
    rankings = []

    groups = valid_data.groupby(["year", "offense", "geo"])
    total_groups = len(groups)

    for i, ((year, offense, geo), group) in enumerate(groups):
        if i % 1000 == 0 and i > 0:
            print(f"  Processed {i:,}/{total_groups:,} groups...")

        # Sort by count descending, then by name for deterministic tie-breaking
        sorted_group = group.sort_values(
            ["count", "institution_name"],
            ascending=[False, True]
        ).reset_index(drop=True)

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        # Create rank by rate (only for schools with FTE data)
        # Sort by rate descending, then by name for deterministic tie-breaking
        rate_ranks = {}
        schools_with_rate = sorted_group[sorted_group["rate_per_10k"].notna()].copy()
        if len(schools_with_rate) > 0:
            schools_with_rate = schools_with_rate.sort_values(
                ["rate_per_10k", "institution_name"],
                ascending=[False, True]
            )
            for rate_rank, (_, rate_row) in enumerate(schools_with_rate.iterrows(), 1):
                rate_ranks[rate_row["unitid"]] = rate_rank

        for rank, (_, row) in enumerate(sorted_group.iterrows(), 1):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "rank_by_rate": rate_ranks.get(row["unitid"]),
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row.get("short_name"),
                "state": row["state"],
                "count": row["count"],
                "pct_of_national_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
                "rate_per_10k": row.get("rate_per_10k") if pd.notna(row.get("rate_per_10k")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    if len(rankings_df) == 0:
        raise RuntimeError("No rankings were generated from the aggregate.")

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int16")
    rankings_df["rank_by_rate"] = rankings_df["rank_by_rate"].astype("Int16")  # Nullable
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Total ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_national_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  National rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    Total schools: {rankings_df['unitid'].nunique()}")
    schools_with_rate = rankings_df["fte"].notna().sum()
    print(f"    Records with FTE/rate: {schools_with_rate:,} ({schools_with_rate/len(rankings_df)*100:.1f}%)")

    # Show sample for Burglary
    latest_year = rankings_df["year"].max()
    sample = rankings_df[
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Burglary") &
        (rankings_df["geo"] == "All")
    ].head(5)

    if not sample.empty:
        print(f"\n  Sample: National Burglary rankings ({latest_year}, All locations, top 5):")
        for _, row in sample.iterrows():
            name = row["short_name"] or row["institution_name"][:30]
            rate_str = f", rate={row['rate_per_10k']:.1f}/10k" if pd.notna(row['rate_per_10k']) else ""
            print(f"    {row['rank']}. {name} ({row['state']}): {row['count']}{rate_str}")

    return rankings_df


def main():
    parser = argparse.ArgumentParser(
        description="Create aggregate tables for dashboard"
    )
    parser.add_argument(
        "--ivy-only",
        action="store_true",
        help="Only aggregate Ivy League schools (overrides config)"
    )
    parser.add_argument(
        "--all-schools",
        action="store_true",
        help="Aggregate all schools (overrides config)"
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
    print("Creating Aggregate Tables")
    print("=" * 60)
    print(f"Processing mode: {'Ivy League only' if ivy_only else 'ALL SCHOOLS (nationwide)'}")

    # The files this step reads, checked against their steps' records before reading
    dims = CURATED_DIR / "dims"
    inputs_before = provenance.Snapshot(
        "04", [FACTS_PATH, dims / "dim_institution.parquet", dims / "dim_enrollment.parquet", SOURCES_PATH])

    # The old build record no longer describes the files about to be written
    provenance.invalidate(provenance.AGGS_MANIFEST)

    # Create aggregates: every school's full figures, for its profile
    school_agg, base = create_school_year_offense_agg(ivy_only=ivy_only)

    # Rankings and their totals count statistics that several campuses report
    # identically once, under the host campus
    dim_inst, enrollment = load_dim_institution(), load_enrollment_data()
    shared = create_shared_blocks(base, dim_inst, enrollment)
    print("\nCreating the aggregate that rankings count (shadow blocks removed)...")
    ranked_agg = build_school_agg(without_shadows(base, shared), dim_inst, enrollment)
    ivy_rankings = create_ivy_rankings(ranked_agg)

    # Create state and national rankings if processing all schools
    state_rankings = None
    national_rankings = None
    if not ivy_only:
        state_rankings = create_state_rankings(ranked_agg)
        national_rankings = create_national_rankings(ranked_agg)

    aggs = CURATED_DIR / "aggs"
    written = [aggs / "agg_school_year_offense.parquet", SHARED_PATH, aggs / "agg_ivy_rankings.parquet"]
    if not ivy_only:
        written += [aggs / "agg_state_rankings.parquet", aggs / "agg_national_rankings.parquet"]
    provenance.write_aggs_manifest(all_schools=not ivy_only, snapshot=inputs_before, outputs=written)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"School-year-offense records: {len(school_agg):,}")
    if ivy_rankings is not None:
        print(f"Ivy rankings records: {len(ivy_rankings):,}")
    if state_rankings is not None:
        print(f"State rankings records: {len(state_rankings):,}")
    if national_rankings is not None:
        print(f"National rankings records: {len(national_rankings):,}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 05_generate_json.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("04", main))
