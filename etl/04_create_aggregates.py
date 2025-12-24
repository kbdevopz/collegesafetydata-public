"""
Create pre-aggregated tables for fast UI queries.

This script creates aggregate tables that power the dashboard:
- agg_school_year_offense: Summary by school, year, offense, geography
- agg_ivy_rankings: Pre-computed Ivy League rankings by year/offense

Usage:
    python 04_create_aggregates.py
    python 04_create_aggregates.py --ivy-only
"""

import sys
import argparse
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import CURATED_DIR, IVY_LEAGUE, GEO_FOR_ALL, US_STATES, PROCESS_ALL_SCHOOLS


def get_facts_pattern() -> str:
    """Get the glob pattern for reading fact files."""
    facts_path = CURATED_DIR / "facts"

    if (facts_path / "incidents").exists():
        return str(facts_path / "incidents" / "**" / "*.parquet")
    else:
        return str(facts_path / "*.parquet")


def load_enrollment_data() -> pd.DataFrame:
    """
    Load enrollment data with FTE for rate calculations.
    Returns DataFrame with unitid, year, fte columns.
    """
    enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    if not enrollment_path.exists():
        print("  WARNING: Enrollment data not found. Rates will not be calculated.")
        return None

    df = pd.read_parquet(enrollment_path)
    # Only need unitid, year, fte for joining
    return df[["unitid", "year", "fte"]]


def create_school_year_offense_agg(ivy_only: bool = False) -> pd.DataFrame:
    """
    Aggregate: (year, unitid, offense, geo) -> count

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
    print("Creating school-year-offense aggregate...")

    con = duckdb.connect()
    facts_pattern = get_facts_pattern()

    # Base aggregation query
    query = f"""
    SELECT
        f.year,
        f.unitid,
        f.offense,
        f.offense_family,
        f.geo,
        SUM(f.count) as count
    FROM read_parquet('{facts_pattern}') f
    """

    if ivy_only:
        ivy_list = ", ".join(str(u) for u in IVY_LEAGUE.keys())
        query += f" WHERE f.unitid IN ({ivy_list})"

    query += """
    GROUP BY f.year, f.unitid, f.offense, f.offense_family, f.geo
    ORDER BY f.year, f.unitid, f.offense, f.geo
    """

    agg = con.execute(query).df()
    print(f"  Base aggregation: {len(agg):,} records")

    # Add institution names from dimension
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if dims_path.exists():
        dim_inst = pd.read_parquet(dims_path)
        name_map = dim_inst.set_index("unitid")["institution_name"].to_dict()
        agg["institution_name"] = agg["unitid"].map(name_map)
    else:
        # Use Ivy League names from config
        name_map = {uid: info["name"] for uid, info in IVY_LEAGUE.items()}
        agg["institution_name"] = agg["unitid"].map(name_map)

    # Create "All" geography aggregation
    # Sum On-campus + Non-campus + Public property (not Residence halls)
    geo_filter = agg["geo"].isin(GEO_FOR_ALL)
    all_geo = agg[geo_filter].copy()
    all_geo["geo"] = "All"

    all_geo_agg = all_geo.groupby(
        ["year", "unitid", "institution_name", "offense", "offense_family", "geo"],
        as_index=False
    )["count"].sum()

    # Combine with original
    agg = pd.concat([agg, all_geo_agg], ignore_index=True)

    # Join enrollment data for FTE and rate calculations
    # Note: Crime data uses extended UNITID format (UNITID * 1000 + branch)
    # IPEDS uses base UNITID, so we need to extract base UNITID for joining
    enrollment = load_enrollment_data()
    if enrollment is not None:
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
    else:
        agg["fte"] = None
        agg["rate_per_10k"] = None

    # Ensure proper types
    agg["year"] = agg["year"].astype("int16")
    agg["unitid"] = agg["unitid"].astype("int32")
    agg["count"] = agg["count"].astype("int32")
    # FTE may have nulls, so use nullable int
    agg["fte"] = agg["fte"].astype("Int32")

    # Sort
    agg = agg.sort_values(["year", "unitid", "offense", "geo"]).reset_index(drop=True)

    print(f"  With 'All' geography: {len(agg):,} records")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    agg_dir.mkdir(parents=True, exist_ok=True)

    output_path = agg_dir / "agg_school_year_offense.parquet"
    agg.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    return agg


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
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        if agg_path.exists():
            school_agg = pd.read_parquet(agg_path)
        else:
            print("  ERROR: School aggregate not found. Run school_year_offense first.")
            return None

    # Filter to Ivy League only
    ivy_unitids = set(IVY_LEAGUE.keys())
    ivy_data = school_agg[school_agg["unitid"].isin(ivy_unitids)].copy()

    if len(ivy_data) == 0:
        print("  WARNING: No Ivy League data found in aggregate")
        return None

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
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        if agg_path.exists():
            school_agg = pd.read_parquet(agg_path)
        else:
            print("  ERROR: School aggregate not found. Run school_year_offense first.")
            return None

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.exists():
        print("  ERROR: Institution dimension not found. Run 03_build_dimensions.py first.")
        return None

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        print("  WARNING: No data with valid state codes found")
        return None

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
        print("  WARNING: No rankings generated")
        return None

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
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        if agg_path.exists():
            school_agg = pd.read_parquet(agg_path)
        else:
            print("  ERROR: School aggregate not found. Run school_year_offense first.")
            return None

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.exists():
        print("  ERROR: Institution dimension not found. Run 03_build_dimensions.py first.")
        return None

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        print("  WARNING: No data with valid state codes found")
        return None

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
        print("  WARNING: No rankings generated")
        return None

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

    # Create aggregates
    school_agg = create_school_year_offense_agg(ivy_only=ivy_only)
    ivy_rankings = create_ivy_rankings(school_agg)

    # Create state and national rankings if processing all schools
    state_rankings = None
    national_rankings = None
    if not ivy_only:
        state_rankings = create_state_rankings(school_agg)
        national_rankings = create_national_rankings(school_agg)

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
    main()
