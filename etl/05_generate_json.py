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
from pathlib import Path, PurePosixPath
from datetime import datetime

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, JSON_DIR, IVY_LEAGUE, IVY_BASE_UNITIDS,
    OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, DATA_YEARS,
    US_STATES, PROCESS_ALL_SCHOOLS,
    SUMMARY_FAMILIES, MIN_FTE_FOR_RATE, ONLINE_EXCLUSION_PCT
)
import provenance


class SiteDataError(Exception):
    """A problem that must stop the build before bad site data is published."""


# Files under JSON_DIR that 05 makes. rankings/ and schools/ belong to 05
# entirely; in the top folder only these names do (build_inputs.json is
# written by provenance after the rest).
ROOT_FILES = {"metadata.json", "presets.json", "school-index.json"}
OWNED_DIRS = ("rankings", "schools")

# Paths (relative to JSON_DIR, "/" separated) written by this run
_written: set[str] = set()


def owns(rel: str) -> bool:
    """Whether 05 makes the site file at `rel` (relative to JSON_DIR, "/" separated).

    remove_stale_files deletes such a file when a run does not write it;
    00_check_for_updates.py uses the same rule.
    """
    top = rel.split("/")[0]
    return rel in ROOT_FILES or (
        top in OWNED_DIRS and rel.count("/") == 1 and PurePosixPath(rel).suffix == ".json")


def required_inputs() -> list[Path]:
    """Curated files 05 reads. All must exist before anything is written."""
    paths = [
        CURATED_DIR / "aggs" / "agg_school_year_offense.parquet",
        CURATED_DIR / "aggs" / "shared_blocks.parquet",
        CURATED_DIR / "aggs" / "agg_ivy_rankings.parquet",
        CURATED_DIR / "aggs" / "agg_campus_year.parquet",
        CURATED_DIR / "aggs" / "agg_institution_year.parquet",
        CURATED_DIR / "aggs" / "agg_institution_year_offense.parquet",
        CURATED_DIR / "dims" / "dim_institution.parquet",
        CURATED_DIR / "dims" / "dim_offense.parquet",
        CURATED_DIR / "dims" / "dim_enrollment.parquet",
        CURATED_DIR / "dims" / "campus_year_sources.parquet",
    ]
    if PROCESS_ALL_SCHOOLS:
        paths += [
            CURATED_DIR / "aggs" / "agg_state_rankings.parquet",
            CURATED_DIR / "aggs" / "agg_national_rankings.parquet",
        ]
    return paths


def opt(value):
    """None for a missing value (None, NaN, NA), otherwise the value."""
    return None if value is None or pd.isna(value) else value


def write_json(path: Path, obj) -> None:
    """Write one site file as strict JSON with LF line endings.

    NaN and Infinity are not valid JSON and break the site, so they stop the
    build instead of being written.
    """
    try:
        text = json.dumps(obj, indent=2, allow_nan=False)
    except ValueError as e:
        raise SiteDataError(
            f"{path.relative_to(JSON_DIR).as_posix()}: a value is NaN or Infinity ({e}). "
            "Fix the curated data (steps 02-04) and re-run 05.") from e
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    _written.add(path.relative_to(JSON_DIR).as_posix())


def remove_stale_files() -> None:
    """Delete site files 05 owns that this run did not write.

    Files that 05 does not make are reported and left in place.
    """
    written_lower = {p.lower(): p for p in _written}
    stale, foreign = [], []
    for p in sorted(JSON_DIR.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(JSON_DIR).as_posix()
        if rel in _written or rel == provenance.PUBLISHED_MANIFEST.name:
            continue
        if not owns(rel):
            foreign.append(rel)
        elif rel.lower() in written_lower:
            raise SiteDataError(
                f"{rel} differs only in letter case from {written_lower[rel.lower()]}, "
                "which this run wrote. Delete it and re-run 05.")
        else:
            stale.append(p)
    for p in stale:
        p.unlink()
    if stale:
        by_dir: dict[str, int] = {}
        for p in stale:
            d = p.parent.name if p.parent != JSON_DIR else "top folder"
            by_dir[d] = by_dir.get(d, 0) + 1
        print(f"\nRemoved {len(stale)} files left from earlier runs: {by_dir}")
    if foreign:
        print(f"\nNOTE: {len(foreign)} file(s) in {JSON_DIR} are not made by 05, so 05 left them "
              f"in place: {foreign[:10]}. Delete them or move them out of {JSON_DIR}. Until then "
              "00_check_for_updates.py reports them, except files git ignores (such as .DS_Store), "
              "which are never committed or published.")


def ensure_json_dir():
    """Create JSON directory structure."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    (JSON_DIR / "rankings").mkdir(exist_ok=True)
    (JSON_DIR / "schools").mkdir(exist_ok=True)


def enrollment_status(years, aggs_record: dict) -> dict[str, str]:
    """
    For each year, where its FTE comes from: "final" (NCES's final *_rv.csv),
    "provisional" (NCES's provisional file) or "missing" (no enrollment, for
    example because NCES has not published it yet; the site shows counts
    without rates). Taken from the enrollment record (step 02a) inside 04's
    record, which 05's snapshot checked against the files it reads.
    """
    inputs = (aggs_record or {}).get("inputs") or {}
    used = (inputs.get("enrollment") or {}).get("inputs") or {}
    status = {}
    for year in years:
        rec = used.get(str(year))
        name = str(rec.get("file") or "").lower() if isinstance(rec, dict) else ""
        status[str(year)] = "missing" if not name else ("final" if name.endswith("_rv.csv") else "provisional")
    return status


def generate_metadata(aggs_record: dict) -> dict:
    """
    Generate metadata.json with available options.

    Schema:
        years: number[]
        enrollmentStatus: {year: "final" | "provisional" | "missing"}
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
    dim_offense = pd.read_parquet(CURATED_DIR / "dims" / "dim_offense.parquet")

    # Build offense list - start with the summary codes (SUMMARY_FAMILIES):
    # criminal offenses (the default view), then every category
    offenses = [
        {
            "code": "criminal",
            "display": "All criminal offenses",
            "family": "Summary",
            "familyDisplay": "Totals",
            "description": "The 11 criminal offenses added up: murder, negligent manslaughter, rape, fondling, "
                           "incest, statutory rape, robbery, aggravated assault, burglary, motor vehicle theft "
                           "and arson. VAWA offenses, arrests and disciplinary referrals are not included.",
            "displayOrder": 0
        },
        {
            "code": "all",
            "display": "All categories (crimes, arrests, referrals)",
            "family": "Summary",
            "familyDisplay": "Totals",
            "description": "Every category added up: criminal offenses, VAWA offenses (domestic violence, dating "
                           "violence, stalking), arrests and disciplinary referrals for drug, liquor and weapons "
                           "law violations. These are different kinds of counts: arrests and referrals count "
                           "people, not incidents, and an incident of dating violence, domestic violence or "
                           "stalking can also be counted as a criminal offense. High totals often reflect drug "
                           "and alcohol enforcement, not violent crime.",
            "displayOrder": 1
        }
    ]
    if [o["code"] for o in offenses] != list(SUMMARY_FAMILIES):
        raise SiteDataError("metadata.json would list other summary codes than SUMMARY_FAMILIES "
                            "(config.py). Fix generate_metadata in 05.")

    # Add individual offenses
    for _, row in dim_offense.iterrows():
        offense_code = row["offense"].lower().replace(" ", "_")
        offenses.append({
            "code": offense_code,
            "display": row["offense"],
            "family": row.get("offense_family", "Criminal"),
            "familyDisplay": OFFENSE_FAMILIES.get(row.get("offense_family", "Criminal"), {}).get("display", row.get("offense_family", "Criminal")),
            "description": row.get("description", OFFENSE_DESCRIPTIONS.get(row["offense"], "")),
            "displayOrder": int(row.get("display_order", 999)) + len(SUMMARY_FAMILIES)  # after the summary codes
        })

    # Sort by display order
    offenses.sort(key=lambda x: x["displayOrder"])

    # Get available years from data (filtered to DATA_YEARS config)
    agg = pd.read_parquet(CURATED_DIR / "aggs" / "agg_school_year_offense.parquet")
    # Only include years defined in DATA_YEARS config
    years = sorted([y for y in agg["year"].unique().tolist() if y in DATA_YEARS])
    if not years:
        raise SiteDataError(
            f"agg_school_year_offense.parquet has no rows for DATA_YEARS {DATA_YEARS[0]}-{DATA_YEARS[-1]}. "
            "Re-run 02-04, then 05.")

    # Build preset list
    presets = []

    # Add national preset first if processing all schools
    if PROCESS_ALL_SCHOOLS:
        dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
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
        "enrollmentStatus": enrollment_status(years, aggs_record),
        # Who rate rankings list (config.py): institutions with at least
        # minFte FTE and fewer than onlineExclusionPct % exclusively online
        "rateRules": {"minFte": MIN_FTE_FOR_RATE, "onlineExclusionPct": ONLINE_EXCLUSION_PCT},
        "offenses": offenses,
        "geographies": ["All", "On-campus", "Non-campus", "Public property", "Residence halls"],
        "presets": presets,
        "lastUpdated": datetime.now().isoformat(),
        "dataSource": "U.S. Department of Education Campus Safety & Security",
        "dataSourceUrl": "https://ope.ed.gov/campussafety/",
        "coverage": f"{min(years)}-{max(years)}",
        "note": "Data reflects reported Clery Act incidents. Reporting practices may vary by institution. Residence hall incidents are a subset of on-campus incidents."
    }

    # Save
    write_json(JSON_DIR / "metadata.json", metadata)

    print(f"  Years: {metadata['coverage']}")
    print(f"  Enrollment (FTE): {metadata['enrollmentStatus']}")
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

                # Sort by institution name; unitid fixes the order of same-name campuses
                state_schools = state_schools.sort_values(["institution_name", "unitid"])

                presets[state_code] = {
                    "id": state_code,
                    "name": state_name,
                    "schools": [
                        {
                            "unitid": int(row["unitid"]),
                            "name": opt(row["institution_name"]) or f"School {row['unitid']}",
                            "short": opt(row.get("short_name")) or None,
                            "city": opt(row.get("city")),
                            "state": state_code
                        }
                        for _, row in state_schools.iterrows()
                    ]
                }

            print(f"  State presets generated: {len(presets) - 1}")

    # Save
    write_json(JSON_DIR / "presets.json", presets)

    print(f"  Total presets: {len(presets)}")
    print(f"  Schools in 'ivy': {len(presets['ivy']['schools'])}")
    print(f"  Saved to: {JSON_DIR / 'presets.json'}")

    return presets


def is_main_campus(unitid: int) -> bool:
    """Determine if a campus is main or branch based on UNITID convention."""
    # Main campuses typically end in 001 (e.g., 166027001)
    # Branch campuses have other suffixes (e.g., 166027002)
    return int(unitid) % 1000 == 1


def ranked(rows: pd.DataFrame, column: str) -> tuple[pd.DataFrame, list[int]]:
    """
    The rows that have a value in `column`, largest first, and their ranks,
    exactly as 04_create_aggregates.py ranks (its ranked): ties listed by
    institution name, then UNITID, and given standard competition ranks
    1, 2, 2, 4.
    """
    rows = rows[rows[column].notna()].sort_values(
        [column, "institution_name", "unitid"], ascending=[False, True, True], kind="mergesort"
    ).reset_index(drop=True)
    values = rows[column].tolist()
    ranks: list[int] = []
    for i, value in enumerate(values):
        ranks.append(ranks[-1] if i and value == values[i - 1] else i + 1)
    return rows, ranks


def offense_code(offense: str) -> str:
    """The code of an offense in the site files ("Motor Vehicle Theft" -> "motor_vehicle_theft")."""
    code = offense.lower().replace(" ", "_")
    if code in SUMMARY_FAMILIES:
        raise SiteDataError(f"Offense {offense!r} has the code {code!r} of a summary code. "
                            "Rename it in config.py (OFFENSE_ORDER) or SUMMARY_FAMILIES.")
    return code


def code_counts(rows: pd.DataFrame, keys: list[str]) -> dict[str, pd.DataFrame]:
    """
    {code: rows of `keys` + count} for every summary code (SUMMARY_FAMILIES:
    the sum over its family, or over every offense) and every offense in
    `rows` (which have offense, offense_family and count), counts above 0.
    """
    out = {}
    for code, family in SUMMARY_FAMILIES.items():
        part = rows if family is None else rows[rows["offense_family"] == family]
        out[code] = part.groupby(keys, as_index=False, dropna=False)["count"].sum()
    for offense, part in rows.groupby("offense"):
        out[offense_code(offense)] = part[keys + ["count"]]
    return {code: df[df["count"] > 0] for code, df in out.items()}


class Institutions:
    """
    The institutions rates are calculated for (04's agg_institution_year and
    agg_institution_year_offense): per institution-year its link campus,
    name, state, campuses, FTE and share of exclusively online students, and
    its counts per code (code_counts).
    """

    def __init__(self):
        aggs = CURATED_DIR / "aggs"
        self.years = pd.read_parquet(aggs / "agg_institution_year.parquet")
        offense_rows = pd.read_parquet(aggs / "agg_institution_year_offense.parquet")
        self.counts = code_counts(offense_rows, ["year", "base_unitid"])
        self.by_key = {(int(r["year"]), int(r["base_unitid"])): r for r in self.years.to_dict("records")}
        self._count_of = {code: {(int(y), int(b)): int(c) for y, b, c in
                                 zip(df["year"].tolist(), df["base_unitid"].tolist(), df["count"].tolist())}
                          for code, df in self.counts.items()}

    @staticmethod
    def rate_ranked(rec: dict) -> bool:
        """Whether an institution-year is in rate rankings (config.py, MIN_FTE_FOR_RATE, ONLINE_EXCLUSION_PCT)."""
        fte, online = rec.get("fte"), rec.get("pctdeexc")
        return (pd.notna(fte) and int(fte) >= MIN_FTE_FOR_RATE
                and (pd.isna(online) or int(online) < ONLINE_EXCLUSION_PCT))

    def count(self, code: str, year: int, base_unitid: int) -> int:
        return self._count_of.get(code, {}).get((int(year), int(base_unitid)), 0)

    def codes(self) -> list[str]:
        return list(self.counts)

    def profile_years(self, base_unitid: int, own: dict[int, dict[str, int]]) -> dict[str, dict]:
        """
        A school file's "institution" years: {year: {campuses, online,
        rateRanked, counts}} for each year of `own` (the school's own counts
        per year and code, above 0) in which its institution is listed.

        counts (per code, above 0) is left out when it equals the school's
        own counts that year (one campus and no shadow blocks), which keeps
        the files small: the page then uses the school's own counts.
        """
        out = {}
        for year in sorted(own):
            rec = self.by_key.get((int(year), int(base_unitid)))
            if rec is None:
                continue
            counts = {code: self.count(code, year, base_unitid) for code in self.counts}
            counts = {code: n for code, n in counts.items() if n > 0}
            entry = {
                "campuses": int(rec["campuses"]),
                "online": int(rec["pctdeexc"]) if pd.notna(rec.get("pctdeexc")) else None,
                "rateRanked": self.rate_ranked(rec),
            }
            if counts != own[year]:
                entry["counts"] = counts
            out[str(year)] = entry
        return out


def rate_rankings(institutions: Institutions, year: int, in_preset) -> tuple[dict, dict]:
    """
    One file's rate rankings: ({base UNITID: institution}, {code: entries}).

    The institutions are those of the year that `in_preset(rec)` accepts and
    that are rate ranked (Institutions.rate_ranked). Per code, those with a
    count above 0 are ranked by rate = count / FTE x 10,000 rounded to 2
    decimals, largest first, ties by name, then base UNITID, ranks 1, 2, 2, 4.
    """
    recs = [r for r in institutions.years[institutions.years["year"] == year].to_dict("records")
            if in_preset(r) and Institutions.rate_ranked(r)]
    table = {}
    for r in sorted(recs, key=lambda r: int(r["base_unitid"])):
        table[str(int(r["base_unitid"]))] = {
            "name": r["institution_name"],
            "unitid": int(r["link_unitid"]),
            "state": opt(r["state"]),
            "fte": int(r["fte"]),
            "campuses": int(r["campuses"]),
        }
    frame = pd.DataFrame({
        "unitid": [int(r["base_unitid"]) for r in recs],
        "institution_name": [r["institution_name"] for r in recs],
        "fte": [int(r["fte"]) for r in recs],
    })
    entries = {}
    for code in institutions.codes():
        rows = frame.assign(count=[institutions.count(code, year, u) for u in frame["unitid"].tolist()])
        rows = rows[rows["count"] > 0].copy()
        rows["rate"] = (rows["count"] / rows["fte"] * 10000).round(2)
        rows, ranks = ranked(rows, "rate")
        entries[code] = [{"rank": rank, "id": int(row["unitid"]), "count": int(row["count"]),
                          "rate": float(row["rate"])}
                         for rank, (_, row) in zip(ranks, rows.iterrows())]
    return table, entries


def rankings_output(year_data: pd.DataFrame, preset: str, year: int, institutions: Institutions,
                    in_preset, campus_rows: pd.DataFrame) -> dict:
    """
    One rankings file.

    Schema:
        preset, year
        campuses: {UNITID: {name, short, state, main, fte, campuses}}
            every campus of this file's scope that counts this year
            (`campus_rows`: 04's agg_campus_year, reported and not entirely
            figures counted under another campus), incidents or not; fte is
            its institution's (NCES publishes FTE per institution) and
            campuses its institution's number of campuses that year
        rankings: {code: [{rank, unitid, count}]}
            per summary code (SUMMARY_FAMILIES) and offense, the campuses
            with a count above 0 (04's geo "All", shadow blocks left out),
            largest first, ties by name, then UNITID, ranks 1, 2, 2, 4. Every
            other campus of `campuses` has 0 for that code: the site lists
            those after them, all with rank (number of entries + 1), by name,
            then UNITID (the same tie rule)
        totals: {code: sum of the counts}
        institutions: {base UNITID: {name, unitid (link campus), state, fte, campuses}}
            every institution of the scope that rate rankings may list this
            year, incidents or not
        rateRankings: {code: [{rank, id (base UNITID), count, rate}]} (rate_rankings)
            those with a count above 0; every other institution of
            `institutions` has rate 0 for that code, listed after them the
            same way
    """
    all_geo = year_data[year_data["geo"] == "All"]
    output = {"preset": preset, "year": int(year), "campuses": {}, "rankings": {}, "totals": {}}

    for row in campus_rows.sort_values("unitid").to_dict("records"):
        unitid = int(row["unitid"])
        inst = institutions.by_key.get((int(year), unitid // 1000))
        if inst is None:
            raise SiteDataError(f"{preset}-{year}: campus {unitid} counts this year but its institution is "
                                "not in agg_institution_year.parquet. Re-run 04_create_aggregates.py, then 05.")
        output["campuses"][str(unitid)] = {
            "name": row["institution_name"],
            "short": opt(row.get("short_name")),
            "state": opt(row.get("state")),
            "main": is_main_campus(unitid),
            "fte": int(inst["fte"]) if pd.notna(inst.get("fte")) else None,
            "campuses": int(inst["campuses"]),
        }
    ranked_ids = {str(int(u)) for u in all_geo["unitid"].unique()}
    if ranked_ids - set(output["campuses"]):
        raise SiteDataError(f"{preset}-{year}: {len(ranked_ids - set(output['campuses']))} ranked campuses are not "
                            f"campus-years that count (first: {sorted(ranked_ids - set(output['campuses']))[0]}). "
                            "Re-run 04_create_aggregates.py, then 05.")

    names = all_geo.drop_duplicates("unitid")[["unitid", "institution_name"]]
    for code, rows in code_counts(all_geo, ["unitid"]).items():
        rows = rows.merge(names, on="unitid", how="left")
        rows, ranks = ranked(rows, "count")
        output["rankings"][code] = [{"rank": rank, "unitid": int(u), "count": int(c)}
                                    for rank, u, c in zip(ranks, rows["unitid"].tolist(), rows["count"].tolist())]
        output["totals"][code] = int(rows["count"].sum())

    # 04's ranks of each offense must be the ones written (one ranking rule)
    for offense, part in all_geo.groupby("offense"):
        theirs = dict(zip(part["unitid"].astype(int).tolist(), part["rank"].astype(int).tolist()))
        ours = {e["unitid"]: e["rank"] for e in output["rankings"][offense_code(offense)]}
        if theirs != ours:
            raise SiteDataError(f"{preset}-{year}: the ranks of {offense} differ from 04's. "
                                "Re-run 04_create_aggregates.py, then 05.")

    output["institutions"], output["rateRankings"] = rate_rankings(institutions, int(year), in_preset)
    return output


def campus_year_rows() -> pd.DataFrame:
    """
    04's agg_campus_year (the campus-years that count in rankings, 0
    included) with each campus's name and short name from dim_institution.
    """
    rows = pd.read_parquet(CURATED_DIR / "aggs" / "agg_campus_year.parquet")
    rows = rows[rows["year"].isin(DATA_YEARS)]
    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
    names = dim_inst[["unitid", "institution_name", "short_name"]]
    out = rows.merge(names, on="unitid", how="left", validate="many_to_one")
    if out["institution_name"].isna().any():
        first = out[out["institution_name"].isna()].iloc[0]
        raise SiteDataError(f"Campus {int(first['unitid'])} counts in {int(first['year'])} but has no name in "
                            "dim_institution.parquet. Re-run 03_build_dimensions.py and 04, then 05.")
    return out


def generate_rankings_json() -> None:
    """
    Generate rankings JSON files for each year and preset (schema: rankings_output).

    Files:
        rankings/ivy-YYYY-all.json     (Ivy League rankings)
        rankings/CA-YYYY-all.json      (State rankings)
        rankings/national-YYYY-all.json (National rankings)
    """
    print("\nGenerating rankings JSON files...")

    rankings_dir = JSON_DIR / "rankings"
    rankings_dir.mkdir(exist_ok=True)
    institutions = Institutions()
    campus_years = campus_year_rows()
    zero_rows = 0

    # Generate Ivy League rankings
    ivy_rankings_path = CURATED_DIR / "aggs" / "agg_ivy_rankings.parquet"
    ivy_files = 0

    if ivy_rankings_path.exists():
        rankings_df = pd.read_parquet(ivy_rankings_path)
        # Filter to only include years in DATA_YEARS
        rankings_df = rankings_df[rankings_df["year"].isin(DATA_YEARS)]

        for year in sorted(rankings_df["year"].unique()):
            year_data = rankings_df[rankings_df["year"] == year].copy()
            scope = campus_years[(campus_years["year"] == year) & campus_years["unitid"].isin(IVY_LEAGUE.keys())]
            output = rankings_output(year_data, "ivy", year, institutions,
                                     lambda r: int(r["base_unitid"]) in IVY_BASE_UNITIDS, scope)
            write_json(rankings_dir / f"ivy-{year}-all.json", output)
            ivy_files += 1

        print(f"  Ivy League: {ivy_files} files")
    else:
        raise SiteDataError(f"{ivy_rankings_path} not found. Run 04_create_aggregates.py first.")

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
                    scope = campus_years[(campus_years["year"] == year) & (campus_years["state"] == state)]
                    # A state-year is published when a campus there reported it
                    if len(year_data) == 0 and len(scope) == 0:
                        continue
                    output = rankings_output(year_data, state, year, institutions,
                                             lambda r, s=state: r["state"] == s, scope)
                    zero_rows += len(scope) - len(output["rankings"]["all"])
                    write_json(rankings_dir / f"{state}-{year}-all.json", output)
                    state_files += 1

            print(f"  State rankings: {state_files} files ({zero_rows:,} campus-years ranked with 0)")
        else:
            raise SiteDataError(f"{state_rankings_path} not found. Run 04_create_aggregates.py first.")

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
                scope = campus_years[(campus_years["year"] == year) & campus_years["state"].isin(US_STATES)]
                output = rankings_output(year_data, "national", year, institutions,
                                         lambda r: r["state"] in US_STATES, scope)
                print(f"    {year}: {len(scope):,} campuses ranked, "
                      f"{len(scope) - len(output['rankings']['all']):,} of them with no incident (0)")
                write_json(rankings_dir / f"national-{year}-all.json", output)
                national_files += 1

            print(f"  National rankings: {national_files} files")
        else:
            raise SiteDataError(f"{national_rankings_path} not found. Run 04_create_aggregates.py first.")

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
        sharedFigures: SharedFigure[]  # only for a school with shadow blocks (see shared_figures)
        institution: {id, byYear: {year: {campuses, online, rateRanked, counts?}}}
            the school's institution (base UNITID) in the school's years, as
            rates count it (Institutions.profile_years): all its campuses'
            counts per code without shadow blocks (left out when equal to
            the school's own); fteByYear is its FTE

    Every campus that reported a year has a file (dim_institution). Its
    years are the years it reported (campus_year_sources: a release row
    with at least one count cell not blank): yearlyTotals has each of them,
    0 for a year with no incident, and notReported lists the other years
    of DATA_YEARS (left out when there are none), so a page can tell 0 from
    not reported.
    """
    print("\nGenerating school profile JSON files...")

    # Load data
    agg = pd.read_parquet(CURATED_DIR / "aggs" / "agg_school_year_offense.parquet")
    by_unitid = {int(u): rows for u, rows in agg.groupby("unitid", sort=False)}
    institutions = Institutions()

    # The years each campus reported, and each institution's FTE by year
    sources = pd.read_parquet(CURATED_DIR / "dims" / "campus_year_sources.parquet", columns=["unitid", "year"])
    sources = sources[sources["year"].isin(DATA_YEARS)]
    reported_years = {int(u): sorted(int(y) for y in g["year"].tolist()) for u, g in sources.groupby("unitid")}
    enrollment = pd.read_parquet(CURATED_DIR / "dims" / "dim_enrollment.parquet", columns=["unitid", "year", "fte"])
    enrollment = enrollment[enrollment["fte"].notna() & enrollment["year"].isin(DATA_YEARS)]
    fte_of = {(int(u), int(y)): int(f) for u, y, f in
              zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(), enrollment["fte"].tolist())}
    zero_profiles = 0
    zero_years = 0
    schools_dir = JSON_DIR / "schools"
    schools_dir.mkdir(exist_ok=True)

    # Load institution dimension for school info
    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
    shared = shared_figures(dim_inst)
    shared_written = 0

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
        school_data = by_unitid.get(unitid, agg.iloc[0:0]).copy()

        # Filter to only include years in DATA_YEARS
        school_data = school_data[school_data["year"].isin(DATA_YEARS)]

        # The years it reported; a year with figures must be one of them
        years = reported_years.get(unitid, [])
        unreported = sorted(set(int(y) for y in school_data["year"].unique()) - set(years))
        if unreported:
            raise SiteDataError(f"School {unitid} has figures for {unreported} but no reported campus-year then in "
                                "campus_year_sources.parquet. Re-run 02_transform_to_parquet.py to 04, then 05.")
        if not years:
            raise SiteDataError(f"School {unitid} is in dim_institution.parquet but reported no year of DATA_YEARS. "
                                "Re-run 03_build_dimensions.py to 04, then 05.")
        if school_data.empty:
            zero_profiles += 1

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
            name = opt(inst_row.get("institution_name")) or f"School {unitid}"
            short_name = opt(inst_row.get("short_name")) or None
            city = opt(inst_row.get("city"))
            state = opt(inst_row.get("state"))

        # Latest year summary (the newest year it reported)
        latest_year = max(years)
        latest_all = school_data[
            (school_data["year"] == latest_year) &
            (school_data["geo"] == "All")
        ]

        # Offenses by count, largest first; ties in offense order
        latest_all = latest_all.sort_values(["count", "offense"], ascending=[False, True])

        if latest_all.empty:
            total_incidents = 0
            top_offense = None
            top_offense_count = 0
        else:
            total_incidents = int(latest_all["count"].sum())
            top_row = latest_all.head(1)
            if not top_row.empty:
                top_offense = top_row.iloc[0]["offense"]
                top_offense_count = int(top_row.iloc[0]["count"])
            else:
                top_offense = None
                top_offense_count = 0

        # FTE (enrollment) of its institution in each year it reported (NCES
        # publishes FTE per institution); fte is the newest one
        fte_by_year = {y: fte_of[(unitid // 1000, y)] for y in years if (unitid // 1000, y) in fte_of}
        fte_value = fte_by_year[max(fte_by_year)] if fte_by_year else None

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
            for _, row in latest_all.head(15).iterrows()
        ] if not latest_all.empty else []

        # Breakdown by geography (latest year, all offenses)
        latest_by_geo = school_data[
            (school_data["year"] == latest_year) &
            (school_data["geo"] != "All")
        ]
        geo_totals = latest_by_geo.groupby("geo")["count"].sum().reset_index()
        geo_breakdown = [
            {"geo": row["geo"], "count": int(row["count"])}
            for _, row in geo_totals.sort_values(["count", "geo"], ascending=[False, True]).iterrows()
        ]

        # Totals of every year it reported, 0 for a year without an incident
        yearly_totals = school_data[school_data["geo"] == "All"].groupby("year")["count"].sum()
        yearly_data = [{"year": year, "total": int(yearly_totals.get(year, 0))} for year in years]
        zero_years += sum(1 for row in yearly_data if row["total"] == 0)
        not_reported = [year for year in DATA_YEARS if year not in set(years)]

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
        if not_reported:
            output["notReported"] = not_reported
        # The school's figures stay as DOE reports them; these blocks are
        # counted under another campus in totals and rankings
        if unitid in shared:
            output["sharedFigures"] = shared[unitid]
            shared_written += 1
        # The institution's counts, campuses and online share, for its rates
        own = {year: {} for year in years}
        for code, rows in code_counts(school_data[school_data["geo"] == "All"], ["year"]).items():
            for y, c in zip(rows["year"].tolist(), rows["count"].tolist()):
                own[int(y)][code] = int(c)
        inst_years = institutions.profile_years(unitid // 1000, own)
        if inst_years:
            output["institution"] = {"id": unitid // 1000, "byYear": inst_years}

        # Save
        filename = f"{unitid}.json"
        write_json(schools_dir / filename, output)

        schools_generated += 1
        if is_ivy:
            ivy_count += 1
        else:
            state_count += 1

        # Progress update for large batches
        if schools_generated % 500 == 0:
            print(f"  Generated {schools_generated} profiles...")

    # Every campus named in a note (the campus itself and its host, which the
    # note links to) must have a school file.
    named = set(shared) | {f["hostUnitid"] for figures in shared.values() for f in figures}
    missing = sorted(named - {int(u) for u in schools_to_process["unitid"]})
    if missing:
        raise SiteDataError(f"shared_blocks.parquet names campuses with no school file ({missing[:5]}). "
                            "Re-run 03 and 04, then 05.")

    print(f"\n  Generated {schools_generated} school profiles")
    print(f"    Ivy League: {ivy_count}")
    if PROCESS_ALL_SCHOOLS:
        print(f"    Other schools: {state_count}")
    print(f"    With figures counted under another campus (sharedFigures): {shared_written}")
    print(f"    That reported but never had an incident: {zero_profiles}")
    print(f"    Reported years without an incident (shown as 0): {zero_years:,}")
    print(f"  Saved to: {schools_dir}/")


def shared_figures(dim_inst: pd.DataFrame) -> dict[int, list[dict]]:
    """
    For each campus with shadow blocks (04_create_aggregates.py,
    find_shared_blocks), the blocks that are counted under another campus:
    [{year, geo, hostUnitid, hostName}], by year and geography. The school's
    own figures include them as DOE reports them; state and national totals
    and rankings count them once, under the host.
    """
    shared = pd.read_parquet(CURATED_DIR / "aggs" / "shared_blocks.parquet")
    shadows = shared[shared["role"] == "shadow"]
    rows = dim_inst.set_index("unitid")
    geo_order = {g: i for i, g in enumerate(["On-campus", "Non-campus", "Public property"])}
    out: dict[int, list[dict]] = {}
    for rec in sorted(shadows.to_dict("records"), key=lambda r: (int(r["unitid"]), int(r["year"]),
                                                                  geo_order.get(r["geo"], 99))):
        host = int(rec["host_unitid"])
        if host not in rows.index:
            raise SiteDataError(f"shared_blocks.parquet names host {host}, which is not in "
                                "dim_institution.parquet. Re-run 03 and 04, then 05.")
        name = IVY_LEAGUE[host]["name"] if host in IVY_LEAGUE else (
            opt(rows.loc[host, "institution_name"]) or f"School {host}")
        out.setdefault(int(rec["unitid"]), []).append({
            "year": int(rec["year"]),
            "geo": rec["geo"],
            "hostUnitid": host,
            "hostName": name,
        })
    return out


def generate_school_index() -> None:
    """
    Generate school-index.json for search functionality.

    Files: school-index.json
    Schema:
        schools: [{unitid, name, short, city, state}]

    It lists every school that has a school file: every campus in
    dim_institution (every campus that reported a year, including those that
    never had an incident).
    """
    print("\nGenerating school search index...")

    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")

    # Sort by state, then name for better UX; unitid fixes the order of same-name campuses
    dim_inst = dim_inst.sort_values(["state", "institution_name", "unitid"])

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
                "name": opt(row.get("institution_name")) or f"School {unitid}",
                "short": row.get("short_name") if pd.notna(row.get("short_name")) else None,
                "city": row.get("city") if pd.notna(row.get("city")) else None,
                "state": row.get("state") if pd.notna(row.get("state")) else None,
                "isMainCampus": is_main_campus,
                "baseUnitid": base_unitid
            })

    output = {"schools": schools}

    write_json(JSON_DIR / "school-index.json", output)

    print(f"  Indexed {len(schools)} schools")
    print(f"  Saved to: {JSON_DIR / 'school-index.json'}")


def main() -> int:
    print("=" * 60)
    print("Generating Frontend JSON Files")
    print("=" * 60)
    print(f"Processing mode: {'ALL SCHOOLS (nationwide)' if PROCESS_ALL_SCHOOLS else 'Ivy League only'}")

    # Check inputs before touching the site data
    missing = [p for p in required_inputs() if not p.exists()]
    if missing:
        print("\nERROR: input files are missing:")
        for p in missing:
            print(f"  {p}")
        print("Run 02, 02b, 02a, 03 and 04 in order, then 05. Nothing was written.")
        return 1
    # The same files, checked against 04's record before anything is read
    inputs_before = provenance.Snapshot("05", required_inputs())

    ensure_json_dir()
    provenance.invalidate(provenance.PUBLISHED_MANIFEST)

    try:
        metadata = generate_metadata(inputs_before.records["04"])
        presets = generate_presets()
        generate_rankings_json()
        generate_school_profiles()

        # Generate search index for nationwide mode
        if PROCESS_ALL_SCHOOLS:
            generate_school_index()

        remove_stale_files()
    except SiteDataError as e:
        print(f"\nERROR: {e}")
        print(f"{JSON_DIR} is now partly rewritten and has no build record. "
              "Do not commit it; fix the problem and re-run 05.")
        return 1

    # Publish the record of which DOE and NCES files these numbers come from
    provenance.write_published_manifest(all_schools=PROCESS_ALL_SCHOOLS, snapshot=inputs_before,
                                        written=_written)

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
    return 0


if __name__ == "__main__":
    sys.exit(provenance.run_locked("05", main))
