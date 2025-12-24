"""
Generate JSON files for static frontend.

This script creates all the JSON files needed by the React frontend:
- metadata.json: Available years, offenses, presets
- presets.json: School groupings (Ivy League)
- rankings/ivy-YYYY-all.json: Rankings by year
- schools/UNITID.json: Individual school profiles

Usage:
    python 05_generate_json.py
"""

import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, JSON_DIR, IVY_LEAGUE,
    OFFENSE_ORDER, OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, DATA_YEARS,
    US_STATES, PROCESS_ALL_SCHOOLS
)


def ensure_json_dir():
    """Create JSON directory structure."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    (JSON_DIR / "rankings").mkdir(exist_ok=True)
    (JSON_DIR / "schools").mkdir(exist_ok=True)


def generate_metadata() -> dict:
    """
    Generate metadata.json with available options.

    Schema:
        years: number[]
        offenses: Offense[]
        geographies: string[]
        presets: Preset[]
        last_updated: string
        data_source: string
        coverage: string
        note: string
    """
    print("Generating metadata.json...")

    # Load offense dimension
    dim_offense_path = CURATED_DIR / "dims" / "dim_offense.parquet"
    if dim_offense_path.exists():
        dim_offense = pd.read_parquet(dim_offense_path)
    else:
        # Create from config
        dim_offense = pd.DataFrame([
            {
                "offense": o,
                "offense_family": "Criminal",
                "display_order": i,
                "description": OFFENSE_DESCRIPTIONS.get(o, "")
            }
            for i, o in enumerate(OFFENSE_ORDER)
        ])

    # Build offense list - start with "all" pseudo-offense
    offenses = [
        {
            "code": "all",
            "display": "All Offenses",
            "family": "Summary",
            "familyDisplay": "Summary",
            "description": "Total incidents across all categories including criminal offenses, VAWA offenses, AND arrests/disciplinary referrals for drugs, alcohol, and weapons. Note: High counts may reflect drug/alcohol enforcement, not violent crime.",
            "displayOrder": 0
        }
    ]

    # Add individual offenses
    for _, row in dim_offense.iterrows():
        offense_code = row["offense"].lower().replace(" ", "_")
        offenses.append({
            "code": offense_code,
            "display": row["offense"],
            "family": row.get("offense_family", "Criminal"),
            "familyDisplay": OFFENSE_FAMILIES.get(row.get("offense_family", "Criminal"), {}).get("display", row.get("offense_family", "Criminal")),
            "description": row.get("description", OFFENSE_DESCRIPTIONS.get(row["offense"], "")),
            "displayOrder": int(row.get("display_order", 999)) + 1  # Shift by 1 since "all" is 0
        })

    # Sort by display order
    offenses.sort(key=lambda x: x["displayOrder"])

    # Get available years from data (filtered to DATA_YEARS config)
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    if agg_path.exists():
        agg = pd.read_parquet(agg_path)
        # Only include years defined in DATA_YEARS config
        years = sorted([y for y in agg["year"].unique().tolist() if y in DATA_YEARS])
    else:
        years = DATA_YEARS

    # Build preset list
    presets = []

    # Add national preset first if processing all schools
    if PROCESS_ALL_SCHOOLS:
        dim_inst_path = CURATED_DIR / "dims" / "dim_institution.parquet"
        if dim_inst_path.exists():
            dim_inst = pd.read_parquet(dim_inst_path)
            total_schools = len(dim_inst)
            presets.append({
                "id": "national",
                "name": "All Schools",
                "description": f"All {total_schools:,} schools nationwide",
                "schoolCount": total_schools
            })

    # Add Ivy League preset
    presets.append({
        "id": "ivy",
        "name": "Ivy League",
        "description": "8 Ivy League schools",
        "schoolCount": 8
    })

    # Add state presets if processing all schools
    if PROCESS_ALL_SCHOOLS:
        # Load institution dimension to count schools per state
        dim_inst_path = CURATED_DIR / "dims" / "dim_institution.parquet"
        if dim_inst_path.exists():
            dim_inst = pd.read_parquet(dim_inst_path)
            state_counts = dim_inst["state"].value_counts().to_dict()

            for state_code in sorted(US_STATES.keys()):
                school_count = state_counts.get(state_code, 0)
                if school_count > 0:
                    presets.append({
                        "id": state_code,
                        "name": US_STATES[state_code],
                        "description": f"Schools in {US_STATES[state_code]}",
                        "schoolCount": school_count
                    })

    metadata = {
        "years": years,
        "offenses": offenses,
        "geographies": ["All", "On-campus", "Non-campus", "Public property", "Residence halls"],
        "presets": presets,
        "lastUpdated": datetime.now().isoformat(),
        "dataSource": "U.S. Department of Education Campus Safety & Security",
        "dataSourceUrl": "https://ope.ed.gov/campussafety/",
        "coverage": f"{min(years)}-{max(years)}" if years else "2015-2024",
        "note": "Data reflects reported Clery Act incidents. Reporting practices may vary by institution. Residence hall incidents are a subset of on-campus incidents."
    }

    # Save
    with open(JSON_DIR / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"  Years: {metadata['coverage']}")
    print(f"  Offenses: {len(offenses)}")
    print(f"  Saved to: {JSON_DIR / 'metadata.json'}")

    return metadata


def generate_presets() -> dict:
    """
    Generate presets.json with school groupings.

    Schema:
        {presetId}: {
            id: string
            name: string
            schools: School[]
        }
    """
    print("\nGenerating presets.json...")

    # Start with Ivy League preset
    presets = {
        "ivy": {
            "id": "ivy",
            "name": "Ivy League",
            "schools": [
                {
                    "unitid": unitid,
                    "name": info["name"],
                    "short": info["short"],
                    "city": info["city"],
                    "state": info["state"]
                }
                for unitid, info in sorted(IVY_LEAGUE.items(), key=lambda x: x[1]["name"])
            ]
        }
    }

    # Add state presets if processing all schools
    if PROCESS_ALL_SCHOOLS:
        dim_inst_path = CURATED_DIR / "dims" / "dim_institution.parquet"
        if dim_inst_path.exists():
            dim_inst = pd.read_parquet(dim_inst_path)

            for state_code, state_name in sorted(US_STATES.items()):
                state_schools = dim_inst[dim_inst["state"] == state_code].copy()
                if len(state_schools) == 0:
                    continue

                # Sort by institution name
                state_schools = state_schools.sort_values("institution_name")

                presets[state_code] = {
                    "id": state_code,
                    "name": state_name,
                    "schools": [
                        {
                            "unitid": int(row["unitid"]),
                            "name": row["institution_name"] or f"School {row['unitid']}",
                            "short": row.get("short_name") or None,
                            "city": row.get("city"),
                            "state": state_code
                        }
                        for _, row in state_schools.iterrows()
                    ]
                }

            print(f"  State presets generated: {len(presets) - 1}")

    # Save
    with open(JSON_DIR / "presets.json", 'w') as f:
        json.dump(presets, f, indent=2)

    print(f"  Total presets: {len(presets)}")
    print(f"  Schools in 'ivy': {len(presets['ivy']['schools'])}")
    print(f"  Saved to: {JSON_DIR / 'presets.json'}")

    return presets


def is_main_campus(unitid: int) -> bool:
    """Determine if a campus is main or branch based on UNITID convention."""
    # Main campuses typically end in 001 (e.g., 166027001)
    # Branch campuses have other suffixes (e.g., 166027002)
    return int(unitid) % 1000 == 1


def compute_all_offense_ranking(rankings_df: pd.DataFrame, pct_column: str) -> pd.DataFrame:
    """
    Compute "all" offense ranking by summing across all offenses per school.

    Returns a dataframe with total incidents per school, ranked.
    """
    # Filter to "All" geography
    all_geo = rankings_df[rankings_df["geo"] == "All"].copy()

    # Build aggregation dict based on available columns
    agg_dict = {
        "count": "sum",
        "short_name": "first",  # Keep short name if exists
    }
    if "state" in all_geo.columns:
        agg_dict["state"] = "first"
    # FTE is the same for all offenses at a school, so take first
    if "fte" in all_geo.columns:
        agg_dict["fte"] = "first"

    # Group by school and sum counts across all offenses
    school_totals = all_geo.groupby(["unitid", "institution_name"]).agg(agg_dict).reset_index()

    # Ensure state column exists (set to None if not present)
    if "state" not in school_totals.columns:
        school_totals["state"] = None

    # Calculate rate per 10k if FTE is available
    if "fte" in school_totals.columns:
        school_totals["rate_per_10k"] = (school_totals["count"] / school_totals["fte"] * 10000).round(2)
        school_totals.loc[school_totals["fte"].isna() | (school_totals["fte"] == 0), "rate_per_10k"] = None
    else:
        school_totals["fte"] = None
        school_totals["rate_per_10k"] = None

    # Sort by count descending
    school_totals = school_totals.sort_values("count", ascending=False).reset_index(drop=True)

    # Calculate total for percentage
    total_count = school_totals["count"].sum()

    # Add rank and percentage
    school_totals["rank"] = range(1, len(school_totals) + 1)
    school_totals["pct"] = school_totals["count"].apply(
        lambda x: round((x / total_count * 100) if total_count > 0 else 0, 2)
    )

    # Add rank by rate for schools that have rate data
    schools_with_rate = school_totals[school_totals["rate_per_10k"].notna()].copy()
    if len(schools_with_rate) > 0:
        schools_with_rate = schools_with_rate.sort_values("rate_per_10k", ascending=False)
        rate_ranks = {row["unitid"]: i + 1 for i, (_, row) in enumerate(schools_with_rate.iterrows())}
        school_totals["rank_by_rate"] = school_totals["unitid"].map(rate_ranks)
    else:
        school_totals["rank_by_rate"] = None

    return school_totals


def generate_rankings_json() -> None:
    """
    Generate rankings JSON files for each year and preset.

    Files:
        rankings/ivy-YYYY-all.json     (Ivy League rankings)
        rankings/CA-YYYY-all.json      (State rankings)
        rankings/national-YYYY-all.json (National rankings)
    Schema:
        preset: string
        year: number
        rankings: { [offense_code]: RankingEntry[] }  # Includes "all" for total
        totals: { [offense_code]: number }
    """
    print("\nGenerating rankings JSON files...")

    rankings_dir = JSON_DIR / "rankings"
    rankings_dir.mkdir(exist_ok=True)

    # Generate Ivy League rankings
    ivy_rankings_path = CURATED_DIR / "aggs" / "agg_ivy_rankings.parquet"
    ivy_files = 0

    if ivy_rankings_path.exists():
        rankings_df = pd.read_parquet(ivy_rankings_path)
        # Filter to only include years in DATA_YEARS
        rankings_df = rankings_df[rankings_df["year"].isin(DATA_YEARS)]

        for year in sorted(rankings_df["year"].unique()):
            year_data = rankings_df[rankings_df["year"] == year].copy()

            output = {
                "preset": "ivy",
                "year": int(year),
                "rankings": {},
                "totals": {}
            }

            all_geo = year_data[year_data["geo"] == "All"]

            # Add "all" offense (sum across all offenses)
            all_offense_ranking = compute_all_offense_ranking(year_data, "pct_of_ivy_total")
            output["rankings"]["all"] = [
                {
                    "rank": int(row["rank"]),
                    "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                    "unitid": int(row["unitid"]),
                    "name": row["institution_name"],
                    "short": row["short_name"],
                    "count": int(row["count"]),
                    "pct": float(row["pct"]),
                    "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                    "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                    "isMainCampus": is_main_campus(row["unitid"])
                }
                for _, row in all_offense_ranking.iterrows()
            ]
            output["totals"]["all"] = int(all_offense_ranking["count"].sum())

            # Add individual offense rankings
            for offense in all_geo["offense"].unique():
                offense_data = all_geo[all_geo["offense"] == offense].sort_values("rank")
                offense_code = offense.lower().replace(" ", "_")

                output["rankings"][offense_code] = [
                    {
                        "rank": int(row["rank"]),
                        "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                        "unitid": int(row["unitid"]),
                        "name": row["institution_name"],
                        "short": row["short_name"],
                        "count": int(row["count"]),
                        "pct": float(row["pct_of_ivy_total"]),
                        "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                        "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                        "isMainCampus": is_main_campus(row["unitid"])
                    }
                    for _, row in offense_data.iterrows()
                ]

                output["totals"][offense_code] = int(offense_data["count"].sum())

            filename = f"ivy-{year}-all.json"
            with open(rankings_dir / filename, 'w') as f:
                json.dump(output, f, indent=2)

            ivy_files += 1

        print(f"  Ivy League: {ivy_files} files")
    else:
        print("  WARNING: Ivy rankings not found")

    # Generate state rankings if processing all schools
    state_files = 0

    if PROCESS_ALL_SCHOOLS:
        state_rankings_path = CURATED_DIR / "aggs" / "agg_state_rankings.parquet"

        if state_rankings_path.exists():
            state_df = pd.read_parquet(state_rankings_path)
            # Filter to only include years in DATA_YEARS
            state_df = state_df[state_df["year"].isin(DATA_YEARS)]
            states = sorted(state_df["state"].unique())
            years = sorted(state_df["year"].unique())

            print(f"  Processing state rankings for {len(states)} states, {len(years)} years...")

            for state in states:
                state_data = state_df[state_df["state"] == state]

                for year in years:
                    year_data = state_data[state_data["year"] == year].copy()
                    if len(year_data) == 0:
                        continue

                    output = {
                        "preset": state,
                        "year": int(year),
                        "rankings": {},
                        "totals": {}
                    }

                    all_geo = year_data[year_data["geo"] == "All"]

                    # Add "all" offense (sum across all offenses)
                    all_offense_ranking = compute_all_offense_ranking(year_data, "pct_of_state_total")
                    output["rankings"]["all"] = [
                        {
                            "rank": int(row["rank"]),
                            "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                            "unitid": int(row["unitid"]),
                            "name": row["institution_name"],
                            "short": row["short_name"] if pd.notna(row.get("short_name")) else None,
                            "count": int(row["count"]),
                            "pct": float(row["pct"]),
                            "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                            "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                            "isMainCampus": is_main_campus(row["unitid"])
                        }
                        for _, row in all_offense_ranking.iterrows()
                    ]
                    output["totals"]["all"] = int(all_offense_ranking["count"].sum())

                    # Add individual offense rankings
                    for offense in all_geo["offense"].unique():
                        offense_data = all_geo[all_geo["offense"] == offense].sort_values("rank")
                        offense_code = offense.lower().replace(" ", "_")

                        output["rankings"][offense_code] = [
                            {
                                "rank": int(row["rank"]),
                                "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                                "unitid": int(row["unitid"]),
                                "name": row["institution_name"],
                                "short": row["short_name"] if pd.notna(row.get("short_name")) else None,
                                "count": int(row["count"]),
                                "pct": float(row["pct_of_state_total"]),
                                "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                                "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                                "isMainCampus": is_main_campus(row["unitid"])
                            }
                            for _, row in offense_data.iterrows()
                        ]

                        output["totals"][offense_code] = int(offense_data["count"].sum())

                    filename = f"{state}-{year}-all.json"
                    with open(rankings_dir / filename, 'w') as f:
                        json.dump(output, f, indent=2)

                    state_files += 1

            print(f"  State rankings: {state_files} files")
        else:
            print("  WARNING: State rankings not found")

    # Generate national rankings if processing all schools
    national_files = 0

    if PROCESS_ALL_SCHOOLS:
        national_rankings_path = CURATED_DIR / "aggs" / "agg_national_rankings.parquet"

        if national_rankings_path.exists():
            national_df = pd.read_parquet(national_rankings_path)
            # Filter to only include years in DATA_YEARS
            national_df = national_df[national_df["year"].isin(DATA_YEARS)]
            years = sorted(national_df["year"].unique())

            print(f"  Processing national rankings for {len(years)} years...")

            for year in years:
                year_data = national_df[national_df["year"] == year].copy()
                if len(year_data) == 0:
                    continue

                output = {
                    "preset": "national",
                    "year": int(year),
                    "rankings": {},
                    "totals": {}
                }

                all_geo = year_data[year_data["geo"] == "All"]

                # Add "all" offense (sum across all offenses)
                all_offense_ranking = compute_all_offense_ranking(year_data, "pct_of_national_total")
                output["rankings"]["all"] = [
                    {
                        "rank": int(row["rank"]),
                        "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                        "unitid": int(row["unitid"]),
                        "name": row["institution_name"],
                        "short": row["short_name"] if pd.notna(row.get("short_name")) else None,
                        "state": row["state"] if pd.notna(row.get("state")) else None,
                        "count": int(row["count"]),
                        "pct": float(row["pct"]),
                        "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                        "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                        "isMainCampus": is_main_campus(row["unitid"])
                    }
                    for _, row in all_offense_ranking.iterrows()
                ]
                output["totals"]["all"] = int(all_offense_ranking["count"].sum())

                # Add individual offense rankings
                for offense in all_geo["offense"].unique():
                    offense_data = all_geo[all_geo["offense"] == offense].sort_values("rank")
                    offense_code = offense.lower().replace(" ", "_")

                    output["rankings"][offense_code] = [
                        {
                            "rank": int(row["rank"]),
                            "rankByRate": int(row["rank_by_rate"]) if pd.notna(row.get("rank_by_rate")) else None,
                            "unitid": int(row["unitid"]),
                            "name": row["institution_name"],
                            "short": row["short_name"] if pd.notna(row.get("short_name")) else None,
                            "state": row["state"] if pd.notna(row.get("state")) else None,
                            "count": int(row["count"]),
                            "pct": float(row["pct_of_national_total"]),
                            "fte": int(row["fte"]) if pd.notna(row.get("fte")) else None,
                            "rate": float(row["rate_per_10k"]) if pd.notna(row.get("rate_per_10k")) else None,
                            "isMainCampus": is_main_campus(row["unitid"])
                        }
                        for _, row in offense_data.iterrows()
                    ]

                    output["totals"][offense_code] = int(offense_data["count"].sum())

                filename = f"national-{year}-all.json"
                with open(rankings_dir / filename, 'w') as f:
                    json.dump(output, f, indent=2)

                national_files += 1

            print(f"  National rankings: {national_files} files")
        else:
            print("  WARNING: National rankings not found. Run 04_create_aggregates.py first.")

    print(f"  Total: {ivy_files + state_files + national_files} ranking files")
    print(f"  Saved to: {rankings_dir}/")


def generate_school_profiles() -> None:
    """
    Generate individual school JSON files.

    Files: schools/UNITID.json
    Schema:
        unitid: number
        name: string
        shortName: string
        city: string
        state: string
        ivyLeague: boolean
        summary: SummaryStats
        trends: TrendPoint[]
        breakdownByOffense: BreakdownEntry[]
        breakdownByGeo: BreakdownEntry[]
    """
    print("\nGenerating school profile JSON files...")

    # Load data
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    if not agg_path.exists():
        print("  ERROR: School aggregate not found. Run 04_create_aggregates.py first.")
        return

    agg = pd.read_parquet(agg_path)
    schools_dir = JSON_DIR / "schools"
    schools_dir.mkdir(exist_ok=True)

    # Load institution dimension for school info
    dim_inst_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if dim_inst_path.exists():
        dim_inst = pd.read_parquet(dim_inst_path)
    else:
        # Fallback to Ivy League only
        dim_inst = pd.DataFrame([
            {
                "unitid": uid,
                "institution_name": info["name"],
                "short_name": info["short"],
                "city": info["city"],
                "state": info["state"],
                "ivy_league": True
            }
            for uid, info in IVY_LEAGUE.items()
        ])

    # Determine which schools to process
    if PROCESS_ALL_SCHOOLS:
        schools_to_process = dim_inst.copy()
        print(f"  Processing all {len(schools_to_process)} schools...")
    else:
        # Ivy League only
        schools_to_process = dim_inst[dim_inst["ivy_league"] == True].copy()
        print(f"  Processing {len(schools_to_process)} Ivy League schools...")

    schools_generated = 0
    ivy_count = 0
    state_count = 0

    for _, inst_row in schools_to_process.iterrows():
        unitid = int(inst_row["unitid"])
        school_data = agg[agg["unitid"] == unitid].copy()

        # Filter to only include years in DATA_YEARS
        school_data = school_data[school_data["year"].isin(DATA_YEARS)]

        if school_data.empty:
            continue

        # Get school info
        is_ivy = unitid in IVY_LEAGUE

        # Get campus type from dimension data
        is_main_campus = bool(inst_row.get("is_main_campus", True))
        campus_type = "Main Campus" if is_main_campus else "Branch Campus"

        if is_ivy:
            ivy_info = IVY_LEAGUE[unitid]
            name = ivy_info["name"]
            short_name = ivy_info["short"]
            city = ivy_info["city"]
            state = ivy_info["state"]
        else:
            name = inst_row.get("institution_name") or f"School {unitid}"
            short_name = inst_row.get("short_name") or None
            city = inst_row.get("city")
            state = inst_row.get("state")

        # Latest year summary
        latest_year = int(school_data["year"].max())
        latest_all = school_data[
            (school_data["year"] == latest_year) &
            (school_data["geo"] == "All")
        ]

        if latest_all.empty:
            total_incidents = 0
            top_offense = None
            top_offense_count = 0
        else:
            total_incidents = int(latest_all["count"].sum())
            top_row = latest_all.nlargest(1, "count")
            if not top_row.empty:
                top_offense = top_row.iloc[0]["offense"]
                top_offense_count = int(top_row.iloc[0]["count"])
            else:
                top_offense = None
                top_offense_count = 0

        # Get FTE (enrollment) - build per-year dict and also store latest
        # FTE is now available for all years (2015-2023)
        fte_value = None
        fte_by_year = {}
        if "fte" in school_data.columns:
            fte_data = school_data[school_data["fte"].notna()].copy()
            if not fte_data.empty:
                # Build fteByYear dictionary
                for _, fte_row in fte_data.drop_duplicates(subset=["year"]).iterrows():
                    fte_by_year[int(fte_row["year"])] = int(fte_row["fte"])
                # Also store latest FTE for backwards compatibility
                latest_fte_year = fte_data["year"].max()
                fte_row = fte_data[fte_data["year"] == latest_fte_year].iloc[0]
                fte_value = int(fte_row["fte"])

        # Trends (all years, geo="All", by offense)
        trends_data = school_data[school_data["geo"] == "All"].copy()
        trends = [
            {
                "year": int(row["year"]),
                "offense": row["offense"],
                "offenseFamily": row["offense_family"],
                "count": int(row["count"])
            }
            for _, row in trends_data.iterrows()
        ]

        # Sort trends by year, then offense
        trends.sort(key=lambda x: (x["year"], x["offense"]))

        # Breakdown by offense (latest year, geo="All")
        offense_breakdown = [
            {"offense": row["offense"], "count": int(row["count"])}
            for _, row in latest_all.nlargest(15, "count").iterrows()
        ] if not latest_all.empty else []

        # Breakdown by geography (latest year, all offenses)
        latest_by_geo = school_data[
            (school_data["year"] == latest_year) &
            (school_data["geo"] != "All")
        ]
        geo_totals = latest_by_geo.groupby("geo")["count"].sum().reset_index()
        geo_breakdown = [
            {"geo": row["geo"], "count": int(row["count"])}
            for _, row in geo_totals.sort_values("count", ascending=False).iterrows()
        ]

        # Year-over-year totals
        yearly_totals = school_data[school_data["geo"] == "All"].groupby("year")["count"].sum()
        yearly_data = [
            {"year": int(year), "total": int(count)}
            for year, count in yearly_totals.items()
        ]

        # Build output
        output = {
            "unitid": unitid,
            "name": name,
            "shortName": short_name,
            "city": city,
            "state": state,
            "ivyLeague": is_ivy,
            "isMainCampus": is_main_campus,
            "campusType": campus_type,
            "fte": fte_value,
            "fteByYear": fte_by_year if fte_by_year else None,
            "summary": {
                "latestYear": latest_year,
                "totalIncidents": total_incidents,
                "topOffense": top_offense,
                "topOffenseCount": top_offense_count
            },
            "yearlyTotals": yearly_data,
            "trends": trends,
            "breakdownByOffense": offense_breakdown,
            "breakdownByGeo": geo_breakdown
        }

        # Save
        filename = f"{unitid}.json"
        with open(schools_dir / filename, 'w') as f:
            json.dump(output, f, indent=2)

        schools_generated += 1
        if is_ivy:
            ivy_count += 1
        else:
            state_count += 1

        # Progress update for large batches
        if schools_generated % 500 == 0:
            print(f"  Generated {schools_generated} profiles...")

    print(f"\n  Generated {schools_generated} school profiles")
    print(f"    Ivy League: {ivy_count}")
    if PROCESS_ALL_SCHOOLS:
        print(f"    Other schools: {state_count}")
    print(f"  Saved to: {schools_dir}/")


def generate_school_index() -> None:
    """
    Generate school-index.json for search functionality.

    Files: school-index.json
    Schema:
        schools: [{unitid, name, short, city, state}]
    """
    print("\nGenerating school search index...")

    dim_inst_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dim_inst_path.exists():
        print("  ERROR: Institution dimension not found.")
        return

    dim_inst = pd.read_parquet(dim_inst_path)

    # Build index - only include schools we have data for
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    if agg_path.exists():
        agg = pd.read_parquet(agg_path)
        unitids_with_data = set(agg["unitid"].unique())
        dim_inst = dim_inst[dim_inst["unitid"].isin(unitids_with_data)]

    # Sort by state, then name for better UX
    dim_inst = dim_inst.sort_values(["state", "institution_name"])

    schools = []
    for _, row in dim_inst.iterrows():
        unitid = int(row["unitid"])
        is_ivy = unitid in IVY_LEAGUE

        # Get campus type from dimension data
        is_main_campus = bool(row.get("is_main_campus", True))
        base_unitid = int(row.get("base_unitid", unitid // 1000))

        if is_ivy:
            ivy_info = IVY_LEAGUE[unitid]
            schools.append({
                "unitid": unitid,
                "name": ivy_info["name"],
                "short": ivy_info["short"],
                "city": ivy_info["city"],
                "state": ivy_info["state"],
                "isMainCampus": is_main_campus,
                "baseUnitid": base_unitid
            })
        else:
            schools.append({
                "unitid": unitid,
                "name": row.get("institution_name") or f"School {unitid}",
                "short": row.get("short_name") if pd.notna(row.get("short_name")) else None,
                "city": row.get("city") if pd.notna(row.get("city")) else None,
                "state": row.get("state") if pd.notna(row.get("state")) else None,
                "isMainCampus": is_main_campus,
                "baseUnitid": base_unitid
            })

    output = {"schools": schools}

    with open(JSON_DIR / "school-index.json", 'w') as f:
        json.dump(output, f, indent=2)

    print(f"  Indexed {len(schools)} schools")
    print(f"  Saved to: {JSON_DIR / 'school-index.json'}")


def main():
    print("=" * 60)
    print("Generating Frontend JSON Files")
    print("=" * 60)
    print(f"Processing mode: {'ALL SCHOOLS (nationwide)' if PROCESS_ALL_SCHOOLS else 'Ivy League only'}")

    ensure_json_dir()

    metadata = generate_metadata()
    presets = generate_presets()
    generate_rankings_json()
    generate_school_profiles()

    # Generate search index for nationwide mode
    if PROCESS_ALL_SCHOOLS:
        generate_school_index()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Output directory: {JSON_DIR}")

    # List generated files
    json_files = list(JSON_DIR.glob("*.json"))
    ranking_files = list((JSON_DIR / "rankings").glob("*.json"))
    school_files = list((JSON_DIR / "schools").glob("*.json"))

    print(f"Root JSON files: {len(json_files)}")
    print(f"Ranking files: {len(ranking_files)}")
    print(f"School files: {len(school_files)}")

    # Total size
    total_size = sum(f.stat().st_size for f in JSON_DIR.rglob("*.json"))
    if total_size > 1024 * 1024:
        print(f"Total size: {total_size / 1024 / 1024:.1f} MB")
    else:
        print(f"Total size: {total_size / 1024:.1f} KB")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 06_validate.py")
    print("2. Start frontend: cd ../frontend && npm run dev")


if __name__ == "__main__":
    main()
