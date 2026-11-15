"""
Generate JSON files for static frontend.

This script creates all the JSON files needed by the React frontend:
- metadata.json: Available years, offenses, presets, the rate rules
- presets.json: School groupings (Ivy League)
- rankings/ivy-YYYY-all.json: Rankings by year
- schools/UNITID.json: Individual school profiles
- rates/: 3-year rates, comparisons and ordered lists (etl/rates.py)

Usage:
    python 05_generate_json.py
"""

import re
import sys
import json
from fractions import Fraction
import pandas as pd
from pathlib import Path, PurePosixPath
from datetime import datetime

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, JSON_DIR, IVY_LEAGUE,
    OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, DATA_YEARS,
    US_STATES, PROCESS_ALL_SCHOOLS,
    SUMMARY_FAMILIES, MIN_FTE_FOR_RATE, ONLINE_SHARE_YEAR, RATE_CI_LEVEL, ONLINE_UNCERTAIN_RATIO,
    MEDICAL_CAMPUS_SHARE, SHARED_SITE_MAX_SHARE, SHARED_SITE_FIGURE_YEARS, SHARED_NEAR_MIN_NONZERO, SHARED_NEAR_MATCH,
    SHARED_NEAR_MIN_TOTAL,
    COUNT_FLAG_MIN_COUNT, COUNT_FLAG_FACTOR, COUNT_FLAG_PERCENTILE,
    RATE_WINDOW_YEARS, RATE_SKIP_YEARS, RATE_CODES, RATE_DISPERSION, RATE_DISPERSION_OTHER, RATE_RAMP, LIST_CODES,
    LIST_MIN_EXPECTED, LIST_ALPHA, STATE_LIST_MIN_MEMBERS, STATE_LIST_DISPLAY_MIN, PEER_TYPES, SIZE_SETTING_FIELDS,
    FLAG_OFFENSES, FLAG_GEOS, FLAG_MIN_COUNT, FLAG_MIN_OTHER_YEARS, FLAG_P, FLAG_C, FLAG_MIN_MEAN, RATE_CALIBRATION,
    MEDICAL_SCREEN_PATTERN, MEDICAL_SCREEN_SHARE, MEDICAL_SCREEN_MIN_COUNT, rate_windows, dispersion_c
)
import provenance
import rates


class SiteDataError(Exception):
    """A problem that must stop the build before bad site data is published."""


# Files under JSON_DIR that 05 makes. rankings/ and schools/ belong to 05
# entirely; in the top folder only these names do (build_inputs.json is
# written by provenance after the rest).
ROOT_FILES = {"metadata.json", "presets.json", "school-index.json"}
OWNED_DIRS = ("rankings", "schools", "rates")
# rates/institutions/ belongs to 05 as well: one file per institution (write_rates)
RATES_INSTITUTIONS_DIR = "rates/institutions"
# downloads/ belongs to 05 as well: its CSV files (generate_downloads)
DOWNLOADS_DIR = "downloads"

# Paths (relative to JSON_DIR, "/" separated) written by this run
_written: set[str] = set()


def owns(rel: str) -> bool:
    """Whether 05 makes the site file at `rel` (relative to JSON_DIR, "/" separated).

    remove_stale_files deletes such a file when a run does not write it;
    00_check_for_updates.py uses the same rule.
    """
    top = rel.split("/")[0]
    return rel in ROOT_FILES or (
        top in OWNED_DIRS and rel.count("/") == 1 and PurePosixPath(rel).suffix == ".json") or (
        rel.startswith(RATES_INSTITUTIONS_DIR + "/") and rel.count("/") == 2
        and PurePosixPath(rel).suffix == ".json") or (
        top == DOWNLOADS_DIR and rel.count("/") == 1 and PurePosixPath(rel).suffix == ".csv")


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
        CURATED_DIR / "dims" / "campus_id_links.parquet",
        CURATED_DIR / "dims" / "dim_medical_campus.parquet",
        CURATED_DIR / "dims" / "dim_shared_site_enrollment.parquet",
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


def campus_of(row) -> str | None:
    """
    The campus's own DOE name (dim_institution campus_name: BRANCH, when it
    says more than the institution name) for a campus that is not its
    institution's main campus; the site shows it as the title and the
    institution name under it. None for a main campus (titled by the
    institution name) and for a campus DOE gives only a generic label.
    """
    if bool(row.get("is_main_campus", False)):
        return None
    return opt(row.get("campus_name"))


def id_links() -> dict[int, list[dict]]:
    """
    {unitid: [{unitid, relation, years}]} from 03's campus_id_links: the
    other ID DOE reported the same campus under (etl/reference/
    campus_id_changes.csv, decision "link"), "earlier" or "later", and the
    years reported under it. The pages link to each other; no figures move.
    """
    links = pd.read_parquet(CURATED_DIR / "dims" / "campus_id_links.parquet")
    out: dict[int, list[dict]] = {}
    for u, o, years, rel in zip(links["unitid"].tolist(), links["other_unitid"].tolist(),
                                links["other_years"].tolist(), links["relation"].tolist()):
        out.setdefault(int(u), []).append({"unitid": int(o), "relation": rel,
                                           "years": [int(y) for y in str(years).split()]})
    return out


def write_json(path: Path, obj, compact: bool = False) -> None:
    """Write one site file as strict JSON with LF line endings (`compact`: no indentation or spaces).

    NaN and Infinity are not valid JSON and break the site, so they stop the
    build instead of being written.
    """
    try:
        text = (json.dumps(obj, separators=(",", ":"), allow_nan=False) if compact
                else json.dumps(obj, indent=2, allow_nan=False))
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
    (JSON_DIR / RATES_INSTITUTIONS_DIR).mkdir(parents=True, exist_ok=True)


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


def known_defects(aggs_record: dict, years) -> list[dict]:
    """
    The known DOE file errors the build worked around (KNOWN_DEFECTS in 02,
    as recorded in the crime record inside 04's record), each with the
    campuses whose figures for that year come from the defective release
    (campus_year_sources.parquet), so their school pages can say so.

    Only describes the data; no figure is changed here.
    """
    crime = ((aggs_record or {}).get("inputs") or {}).get("crime") or {}
    sources = pd.read_parquet(CURATED_DIR / "dims" / "campus_year_sources.parquet",
                              columns=["unitid", "year", "release"])
    out = []
    for rec in crime.get("known_defects") or []:
        name = str(rec.get("file") or "")
        m = re.fullmatch(r"(oncampus|residencehall|noncampus|publicproperty)"
                         r"(crime|vawa|arrest|discipline)(\d{6})\.sas7bdat", name)
        year = rec.get("year")
        if not m or year not in years:
            raise SiteDataError(f"known defect {name!r} ({year}) in 04's record is not a DOE count file "
                                "of a data year. Fix known_defects in 05.")
        geo, category, release = m.groups()
        taken = str(rec.get("taken_from") or "")
        t = re.fullmatch(r"[a-z]+(\d{6})\.sas7bdat", taken) if taken else None
        if taken and not t:
            raise SiteDataError(f"known defect {name!r}: replacement {taken!r} is not a DOE count file.")
        unitids = sorted(int(u) for u in sources.loc[(sources["year"] == year)
                                                     & (sources["release"] == release), "unitid"])
        if len(unitids) != int(rec.get("campus_years") or 0):
            raise SiteDataError(f"known defect {name!r} ({year}): 02 recorded {rec.get('campus_years')} "
                                f"campus-years, campus_year_sources.parquet has {len(unitids)}.")
        out.append({
            "year": int(year),
            "release": release,            # DOE file suffix, e.g. "212223" (2021-2023)
            "file": name,
            "geo": geo,                    # "residencehall", ...
            "category": category,          # "discipline", "arrest", ...
            "columns": list(rec.get("columns") or []),
            "problem": str(rec.get("problem") or ""),
            "takenFrom": t.group(1) if t else None,   # release the cells come from, or None (left blank)
            "unitids": unitids,
        })
    return out


def generate_metadata(aggs_record: dict, rate_stats: dict, rate_rules: dict) -> dict:
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
    # criminal offenses, violent crimes (the default view), property crimes,
    # then every category
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
            "code": "violent",
            "display": "Violent crimes",
            "family": "Summary",
            "familyDisplay": "Totals",
            "description": "Murder and non-negligent manslaughter, rape, robbery and aggravated assault: the "
                           "offenses the FBI counts as violent crime (Crime in the United States). Fondling, "
                           "incest and statutory rape are not included.",
            "displayOrder": 0
        },
        {
            "code": "property",
            "display": "Property crimes",
            "family": "Summary",
            "familyDisplay": "Totals",
            "description": "Burglary, motor vehicle theft and arson: the offenses the FBI counts as property "
                           "crime (Crime in the United States), without larceny-theft, which Clery does not "
                           "collect.",
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
        code = row["offense"].lower().replace(" ", "_")
        offenses.append({
            "code": code,
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
            # Every campus that reported a year (each has a school page),
            # including the few outside the states that national rankings cover
            "description": f"All {total_schools:,} campuses with a school page",
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
        # The rate rules (config.py; rate_rules)
        "rateRules": rate_rules,
        # The numbers of the rates the Methodology page shows (rate_stats)
        "rateStats": rate_stats,
        "offenses": offenses,
        # Known DOE file errors and the campuses whose figures they touch
        # (residence-hall figures of campus-years from DOE's 2021-2023 release)
        "knownDefects": known_defects(aggs_record, years),
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


INSTITUTION_VALUES = ["count", "abroad_count"]


def code_counts(rows: pd.DataFrame, keys: list[str], values: tuple[str, ...] = ("count",)) -> dict[str, pd.DataFrame]:
    """
    {code: rows of `keys` + `values`} for every summary code (SUMMARY_FAMILIES:
    the sum over its family, or over every offense) and every offense in
    `rows` (which have offense, offense_family and `values`), the rows with
    a value above 0.
    """
    values = list(values)
    out = {}
    for code, family in SUMMARY_FAMILIES.items():
        if family is None:
            part = rows
        elif isinstance(family, tuple):
            part = rows[rows["offense"].isin(family)]
        else:
            part = rows[rows["offense_family"] == family]
        out[code] = part.groupby(keys, as_index=False, dropna=False)[values].sum()
    for offense, part in rows.groupby("offense"):
        out[offense_code(offense)] = part[keys + values]
    return {code: df[(df[values] > 0).any(axis=1)] for code, df in out.items()}


# The rules of 04 that give an institution-year no rate
EXCLUDING_RULES = ("hospital", "medical", "listed", "merger", "family", "shared_pooled", "shared_campus")


class Institutions:
    """
    The institutions rates are calculated for (04's agg_institution_year and
    agg_institution_year_offense): per institution-year its link campus,
    name, state, campuses, FTE estimates and share of exclusively online
    students, and its counts per code (code_counts): count (campuses in the
    United States) and abroad_count.
    """

    def __init__(self):
        aggs = CURATED_DIR / "aggs"
        self.years = pd.read_parquet(aggs / "agg_institution_year.parquet")
        offense_rows = pd.read_parquet(aggs / "agg_institution_year_offense.parquet")
        self.counts = code_counts(offense_rows, ["year", "base_unitid"], tuple(INSTITUTION_VALUES))
        self.by_key = {(int(r["year"]), int(r["base_unitid"])): r for r in self.years.to_dict("records")}
        self._values = {code: {(int(r[0]), int(r[1])): tuple(int(v) for v in r[2:]) for r in
                               df[["year", "base_unitid"] + INSTITUTION_VALUES].itertuples(index=False)}
                        for code, df in self.counts.items()}
        # The name of an institution whose FTE another's rate adds (04's
        # pooled_with): its 001 campus's, else its lowest campus's
        dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet",
                                   columns=["unitid", "institution_name"])
        self._base_name = {}
        for u, name in sorted(zip(dim_inst["unitid"].astype(int).tolist(), dim_inst["institution_name"].tolist())):
            if u % 1000 == 1 or u // 1000 not in self._base_name:
                self._base_name[u // 1000] = name

    @staticmethod
    def rate_listed(rec: dict) -> bool:
        """Whether an institution-year's rate's denominator (rate_fte, pooled FTE included) is at least MIN_FTE_FOR_RATE."""
        fte = rec.get("rate_fte")
        return pd.notna(fte) and int(fte) >= MIN_FTE_FOR_RATE

    def pooled(self, rec: dict) -> list[dict] | None:
        """[{id, name, fte (on-campus)}] of the institutions whose FTE the rate adds (04's pooled_with), or None."""
        text = opt(rec.get("pooled_with"))
        if text is None:
            return None
        out = []
        for part in str(text).split():
            base, fte = part.split(":")
            out.append({"id": int(base), "name": self._base_name.get(int(base)), "fte": int(fte)})
        return out

    def count(self, code: str, year: int, base_unitid: int) -> int:
        return self.values(code, year, base_unitid)[0]

    def values(self, code: str, year: int, base_unitid: int) -> tuple[int, int]:
        """(count, abroad_count) of a code."""
        return self._values.get(code, {}).get((int(year), int(base_unitid)), (0, 0))

    def codes(self) -> list[str]:
        return list(self.counts)

    def profile_years(self, base_unitid: int, own: dict[int, dict[str, int]],
                      flags: list[dict]) -> dict[str, dict]:
        """
        A school file's "institution" years: {year: {campuses, online,
        onlineYear (ONLINE_SHARE_YEAR years only), rated, notRated,
        rateExcludedReason, rateFte, fteUncertain, pooledWith, abroad, flags,
        counts}} for each year of `own` (the school's own counts per year and
        code, above 0) in which its institution is listed.

        rated is true when the institution-year has a single-year rate
        (etl/rates.py, rated_year: a denominator of at least
        MIN_FTE_FOR_RATE, no rule, a state in US_STATES, not a year of
        RATE_SKIP_YEARS); notRated otherwise says why: "scope" (not in
        US_STATES: no rates, as in no rankings file), "size" (denominator
        under MIN_FTE_FOR_RATE or none), "excluded" (a rule of 04:
        rateExcludedReason is its text) or "skippedYear" (RATE_SKIP_YEARS).
        rateFte is the rate's denominator (on-campus FTE, with any pooled
        institutions' added), absent without an FTE; fteUncertain ({share,
        partTimeFirst, reason}: the two estimates, partTimeFirst null when it
        cannot be calculated; reason "own", or "pooled" when only an
        institution pooled with it has an uncertain on-campus FTE) when the
        on-campus FTE is uncertain; pooledWith lists the pooled institutions;
        abroad ({campuses, counts}) the counting campuses abroad and their
        counts per code (not in the institution's counts); flags the
        institution's unusual counts that year (etl/rates.py,
        unusual_years: {offense, geo, count, usual}). counts (per code,
        above 0) is left out when it equals the school's own counts that
        year (one campus, in the United States, and no shadow blocks), which
        keeps the files small: the page then uses the school's own counts.
        """
        out = {}
        for year in sorted(own):
            rec = self.by_key.get((int(year), int(base_unitid)))
            if rec is None:
                continue
            vals = {code: self.values(code, year, base_unitid) for code in self.counts}
            counts = {code: v[0] for code, v in vals.items() if v[0] > 0}
            why = rates.year_status(rec, int(year))
            entry = {
                "campuses": int(rec["campuses"]),
                "online": int(rec["online_pct"]) if pd.notna(rec.get("online_pct")) else None,
                "rated": why == "",
            }
            if why:
                entry["notRated"] = why
            # In the years of ONLINE_SHARE_YEAR, the fall the share is from
            # (that other year, or the year itself when NCES has none for it)
            if int(year) in ONLINE_SHARE_YEAR and entry["online"] is not None:
                entry["onlineYear"] = int(rec["online_year"])
            # No rate by a rule of 04 (population, merger): why
            if opt(rec.get("rate_excluded")) is not None:
                entry["rateExcludedReason"] = rec["rate_excluded"]
            if pd.notna(rec.get("rate_fte")):
                entry["rateFte"] = int(rec["rate_fte"])
            reason = rates.uncertain_reason(rec)
            if reason:
                entry["fteUncertain"] = {"share": opt_int(rec.get("fte_share")),
                                         "partTimeFirst": opt_int(rec.get("fte_part_time_first")),
                                         "reason": reason}
            # Rated with other institutions' on-campus FTE added (04's pooled_with)
            pooled = self.pooled(rec)
            if pooled:
                entry["pooledWith"] = pooled
            if int(rec.get("abroad_campuses") or 0) > 0:
                entry["abroad"] = {"campuses": int(rec["abroad_campuses"]),
                                   "counts": {code: v[1] for code, v in vals.items() if v[1] > 0}}
            year_flags = [{k: f[k] for k in ("offense", "geo", "count", "usual")} for f in flags
                          if f["year"] == int(year)]
            if year_flags:
                entry["flags"] = year_flags
            if counts != own[year]:
                entry["counts"] = counts
            out[str(year)] = entry
        return out


def opt_int(value) -> int | None:
    v = opt(value)
    return None if v is None else int(v)


def high_for_size(count: int, fte, reference: Fraction | None) -> bool:
    """
    config.py COUNT_FLAG_*: count >= COUNT_FLAG_MIN_COUNT and count per
    10,000 FTE above COUNT_FLAG_FACTOR x the year's reference percentile of
    the code (etl/rates.py, count_flag_reference), exactly: count x 10,000 >
    factor x reference x FTE. No flag where the reference is 0 or missing.
    """
    return (reference is not None and reference > 0 and fte is not None and count >= COUNT_FLAG_MIN_COUNT
            and count * 10000 > COUNT_FLAG_FACTOR * reference * int(fte))


def rankings_output(year_data: pd.DataFrame, preset: str, year: int, institutions: Institutions,
                    campus_rows: pd.DataFrame, references: dict[str, Fraction]) -> dict:
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
        rankings: {code: [{rank, unitid, count, highForSize?}]}
            per summary code (SUMMARY_FAMILIES) and offense, the campuses
            with a count above 0 (04's geo "All", shadow blocks left out),
            largest first, ties by name, then UNITID, ranks 1, 2, 2, 4. Every
            other campus of `campuses` has 0 for that code: the site lists
            those after them, all with rank (number of entries + 1), by name,
            then UNITID (the same tie rule). highForSize: true marks a count
            very high for the institution's FTE (high_for_size, `references`:
            the year's count_flag_reference)
        totals: {code: sum of the counts}

    Rates are not in rankings files: rates/ has them (write_rates).
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
        campus = campus_of({"is_main_campus": is_main_campus(unitid), "campus_name": row.get("campus_name")})
        if campus:
            output["campuses"][str(unitid)]["campus"] = campus
    ranked_ids = {str(int(u)) for u in all_geo["unitid"].unique()}
    if ranked_ids - set(output["campuses"]):
        raise SiteDataError(f"{preset}-{year}: {len(ranked_ids - set(output['campuses']))} ranked campuses are not "
                            f"campus-years that count (first: {sorted(ranked_ids - set(output['campuses']))[0]}). "
                            "Re-run 04_create_aggregates.py, then 05.")

    names = all_geo.drop_duplicates("unitid")[["unitid", "institution_name"]]
    for code, rows in code_counts(all_geo, ["unitid"]).items():
        rows = rows.merge(names, on="unitid", how="left")
        rows, ranks = ranked(rows, "count")
        entries = []
        for rank, u, c in zip(ranks, rows["unitid"].tolist(), rows["count"].tolist()):
            e = {"rank": rank, "unitid": int(u), "count": int(c)}
            if high_for_size(int(c), output["campuses"][str(int(u))]["fte"], references.get(code)):
                e["highForSize"] = True
            entries.append(e)
        output["rankings"][code] = entries
        output["totals"][code] = int(rows["count"].sum())

    # 04's ranks of each offense must be the ones written (one ranking rule)
    for offense, part in all_geo.groupby("offense"):
        theirs = dict(zip(part["unitid"].astype(int).tolist(), part["rank"].astype(int).tolist()))
        ours = {e["unitid"]: e["rank"] for e in output["rankings"][offense_code(offense)]}
        if theirs != ours:
            raise SiteDataError(f"{preset}-{year}: the ranks of {offense} differ from 04's. "
                                "Re-run 04_create_aggregates.py, then 05.")

    return output


def campus_year_rows() -> pd.DataFrame:
    """
    04's agg_campus_year (the campus-years that count in rankings, 0
    included) with each campus's name and short name from dim_institution.
    """
    rows = pd.read_parquet(CURATED_DIR / "aggs" / "agg_campus_year.parquet")
    rows = rows[rows["year"].isin(DATA_YEARS)]
    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
    names = dim_inst[["unitid", "institution_name", "short_name", "campus_name"]]
    out = rows.merge(names, on="unitid", how="left", validate="many_to_one")
    if out["institution_name"].isna().any():
        first = out[out["institution_name"].isna()].iloc[0]
        raise SiteDataError(f"Campus {int(first['unitid'])} counts in {int(first['year'])} but has no name in "
                            "dim_institution.parquet. Re-run 03_build_dimensions.py and 04, then 05.")
    return out


STATS_CODES = ("all", "violent", "criminal", "property")


def institution_year_stats(institutions: Institutions) -> dict:
    """
    metadata rateStats numbers over every institution-year of DATA_YEARS: per
    rule of 04 the institution-years it is the first rule for
    (EXCLUDING_RULES order), and of those the ones in the national scope
    (US_STATES) with a denominator of at least MIN_FTE_FOR_RATE; the
    institution-years rated with another institution's FTE added, per rule
    (merger, shared: one with both counts under each); per year, of the
    institutions in the national scope with a denominator of at least
    MIN_FTE_FOR_RATE ("withFte"): those a rule leaves out, those with a
    single-year rate (etl/rates.py rated_year, not in RATE_SKIP_YEARS),
    those of them with an uncertain on-campus FTE (and of those, uncertain
    only through a pooled institution) and those with a counting campus
    abroad; per year the institutions outside the national scope with such
    a denominator (no rates); per ONLINE_SHARE_YEAR year the institutions
    whose own year's online share was used (no share for that other fall),
    all and in the national scope with such a denominator.
    """
    recs = [r for r in institutions.by_key.values() if int(r["year"]) in DATA_YEARS]
    rules = {rule: {"institutionYears": 0, "withFte": 0} for rule in EXCLUDING_RULES}
    pooled = {"merger": 0, "shared": 0}
    by_year = {}
    own_year = {str(y): {"all": 0, "withFte": 0} for y in sorted(ONLINE_SHARE_YEAR)}
    for r in sorted(recs, key=lambda r: (int(r["year"]), int(r["base_unitid"]))):
        y = int(r["year"])
        big = Institutions.rate_listed(r)
        with_fte = big and opt(r.get("state")) in US_STATES
        rule = opt(r.get("rate_rule"))
        if rule is not None:
            rules[rule]["institutionYears"] += 1
            rules[rule]["withFte"] += int(with_fte)
        for p in str(opt(r.get("pooled_rule")) or "").split():
            pooled[p] += 1
        row = by_year.setdefault(str(y), {"withFte": 0, "excluded": 0, "rated": 0, "fteUncertain": 0,
                                          "fteUncertainPooledOnly": 0, "abroad": 0, "outsideScopeWithFte": 0})
        row["outsideScopeWithFte"] += int(big and not with_fte)
        if with_fte:
            row["withFte"] += 1
            row["excluded"] += int(rule is not None)
            rated = rates.year_status(r, y) == ""
            row["rated"] += int(rated)
            reason = rates.uncertain_reason(r)
            row["fteUncertain"] += int(rule is None and reason is not None)
            row["fteUncertainPooledOnly"] += int(rule is None and reason == "pooled")
            row["abroad"] += int(int(r.get("abroad_campuses") or 0) > 0)
        if y in ONLINE_SHARE_YEAR and pd.notna(r.get("online_year")) and int(r["online_year"]) == y:
            own_year[str(y)]["all"] += 1
            own_year[str(y)]["withFte"] += int(with_fte)
    return {"rules": rules, "pooled": pooled, "byYear": by_year, "onlineOwnYear": own_year}


def generate_rankings_json(references: dict[int, dict[str, Fraction]]) -> dict:
    """
    Generate rankings JSON files for each year and preset (schema: rankings_output).
    `references`: etl/rates.py count_flag_reference, for highForSize. Returns
    the national files' flagged counts per year and code.

    Files:
        rankings/ivy-YYYY-all.json     (Ivy League rankings)
        rankings/CA-YYYY-all.json      (State rankings)
        rankings/national-YYYY-all.json (National rankings)
    """
    print("\nGenerating rankings JSON files...")

    rankings_dir = JSON_DIR / "rankings"
    rankings_dir.mkdir(exist_ok=True)
    institutions = Institutions()
    flagged = {}
    flag_rows = []
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
            output = rankings_output(year_data, "ivy", year, institutions, scope, references.get(int(year), {}))
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
                    output = rankings_output(year_data, state, year, institutions, scope,
                                             references.get(int(year), {}))
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
                output = rankings_output(year_data, "national", year, institutions, scope,
                                         references.get(int(year), {}))
                flagged[str(int(year))] = {code: sum(1 for e in entries if e.get("highForSize"))
                                           for code, entries in output["rankings"].items()}
                for code, entries in output["rankings"].items():
                    for e in entries:
                        if e.get("highForSize"):
                            flag_rows.append((int(year), code, e["unitid"], e["count"],
                                              output["campuses"][str(e["unitid"])]["fte"]))
                print(f"    {year}: {len(scope):,} campuses ranked, "
                      f"{len(scope) - len(output['rankings']['all']):,} of them with no incident (0)")
                write_json(rankings_dir / f"national-{year}-all.json", output)
                national_files += 1

            print(f"  National rankings: {national_files} files")
        else:
            raise SiteDataError(f"{national_rankings_path} not found. Run 04_create_aggregates.py first.")

    print(f"  Total: {ivy_files + state_files + national_files} ranking files")
    print(f"  Saved to: {rankings_dir}/")
    # The national count flags, for review (config.py, COUNT_FLAG_*)
    print(f"  Counts flagged as very high for the institution's size (national files): {len(flag_rows):,}")
    for y, code, u, c, fte in sorted(flag_rows):
        print(f"    {y} {code}: {u} count {c}, FTE {fte}")
    return {"countFlags": flagged, "institutionYears": institution_year_stats(institutions)}


# --------------------------------------------------------------------------
# Rates (etl/rates.py builds them; config.py, "Rates", has the rules)
# --------------------------------------------------------------------------

# Test vectors published in metadata rateRules.testVectors: count intervals
# (c, window totals), rates and the rank ranges of a five-member list
TEST_VECTOR_COUNTS = ((0.354, (0, 1, 5, 20, 45, 60, 139, 1000)), (0.497, (20, 139)), (0.665, (20, 266)),
                      (0.522, (5, 60)))
TEST_VECTOR_RATES = ((20, 30000, 0.354), (139, 44830, 0.354), (82, 30483, 0.354), (0, 6751, 0.665),
                     (188, 20282, 0.497))
TEST_VECTOR_LIST = (0.354, ((139, 44830), (82, 30483), (20, 30000), (60, 90000), (30, 100000)))
TEST_VECTOR_CRITICAL = (5, 146, 208, 531)

# What each count of rated institutions counts (metadata rateStats.definitions)
RATE_DEFINITIONS = {
    "rated": "Institutions with a 3-year rate in the window: a campus listed by DOE in each of its years, a link "
             "campus in a U.S. state, the District of Columbia, Puerto Rico or the U.S. Virgin Islands (config.py "
             "US_STATES), a rate denominator (on-campus FTE, pooled FTE added) of at least minFte in each year, and "
             "no rule (hospital, medical, listed, merger, family, shared_pooled, shared_campus) in any year. The "
             "window files list exactly these.",
    "listed": "Rated institutions without a reason (why) whose expected count at the national rate is at least "
              "lists.minExpected: the members of the national ordered list.",
    "stateLists": "Per state, the national list's members in that state; a state list is published (positions and "
                  "ranges within the state) when it has at least lists.stateMinMembers members.",
    "withFte": "Institution-years whose link campus is in US_STATES with a rate denominator of at least minFte, "
               "rules included (single years).",
    "ratedYears": "Of withFte, those with a single-year rate: no rule, and not a year of skipYears.",
}


def write_rates(result: dict) -> tuple[set[int], dict]:
    """
    The rate files (compact JSON) and the numbers metadata rateStats gives.

    rates/{first}-{last}-{code}.json, per rate window and rate code:
        window, code, years, c (overdispersion constant), natl (national rate
        per 10,000 FTE-years, 2 decimals; natlN / natlF exactly), peer {type:
        {rate, n, fteYears, members}}, summary (rated institutions by reason
        and verdict), composition (national on-campus counts of the parts of
        violent, or the motor vehicle thefts beside criminal_xmvt), list
        (LIST_CODES: n, minExpected, minFteYears, zc), stateLists {state:
        members}, entries: every rated institution (rates.WindowCode.entry,
        with the window's shared-site notes: rates.window_status), by rate
        (highest first), then name, then base UNITID.
    rates/institutions/{base UNITID}.json, per institution with a rated
        window, a single-year rate or an unusual-year flag: id, name, unitid
        (link campus), state, peerType, years {year: single-year entry
        (rates.single_year)}, windows {window: status (rates.window_status,
        with the shared-site notes of a rated one), and for a rated one
        fteByYear, fteSmallerByYear (an uncertain on-campus FTE), codes
        {code: entry with nByYear, natl, peerRate}}, flags (every unusual
        year: rates.unusual_years).
    rates/flags.json: every unusual-year flag {id, name, state, year, offense, geo, count, usual}.
    """
    print("\nGenerating rate files...")
    inp, windows, statuses = result["inputs"], result["windows"], result["statuses"]
    out_dir = JSON_DIR / "rates"
    stats = {"definitions": RATE_DEFINITIONS, "windows": {}}
    for window, codes in windows.items():
        label = f"{window[0]}-{window[1]}"
        stats["windows"][label] = {}
        for code, wc in codes.items():
            obj = {"window": list(window), "code": code, "years": wc.years, "c": wc.c,
                   "natl": wc.natl_rate(), "natlN": wc.natl_n, "natlF": wc.natl_f,
                   "peer": {key: {"rate": wc.peer_rate(key), "n": n, "fteYears": f, "members": m}
                            for key, (n, f, m) in wc.peer.items()},
                   "summary": wc.summary()}
            if wc.composition is not None:
                obj["composition"] = wc.composition
            if code in LIST_CODES:
                threshold = -(-LIST_MIN_EXPECTED * wc.natl_f // wc.natl_n)
                obj["list"] = {"n": len(wc.list_members), "minExpected": LIST_MIN_EXPECTED,
                               "minFteYears": threshold, "zc": None if wc.zc is None else round(wc.zc, 6)}
                obj["stateLists"] = wc.state_lists
            obj["entries"] = [wc.entry(r, False) for r in wc.ordered_rows()]
            write_json(out_dir / f"{label}-{code}.json", obj, compact=True)
            s = {"natl": obj["natl"], **obj["summary"]}
            if code in LIST_CODES:
                s |= {"listed": len(wc.list_members), "minFteYears": obj["list"]["minFteYears"],
                      "stateLists": sum(1 for m in wc.state_lists.values() if m >= STATE_LIST_MIN_MEMBERS),
                      "stateListsDisplayMin": sum(1 for m in wc.state_lists.values() if m >= STATE_LIST_DISPLAY_MIN)}
            stats["windows"][label][code] = s
            print(f"  {label} {code}: national {obj['natl']}, rated {s['rated']}, verdicts {s['verdicts']}"
                  + (f", listed {s['listed']}, state lists {s['stateLists']}" if code in LIST_CODES else ""))

    flags, single = result["flags"], result["singleYear"]
    rate_files = set()
    bases = sorted(set(single) | set(flags) | {b for st in statuses.values() for b in st})
    for base in bases:
        rated_windows = [w for w, st in statuses.items() if st.get(base, {}).get("status") == "rated"]
        rated_years = [y for y, e in single.get(base, {}).items() if "rates" in e]
        if not (rated_windows or rated_years or base in flags):
            continue
        latest = inp.rec[(max(inp.years_of[base]), base)]
        obj = {"id": base, "name": str(latest["institution_name"]), "unitid": int(latest["link_unitid"]),
               "state": opt(latest.get("state")), "peerType": str(latest["peer_type"]),
               "years": single.get(base, {}), "windows": {}}
        for window, st in statuses.items():
            if base not in st:
                continue
            entry = dict(st[base])
            if entry["status"] == "rated":
                years = range(window[0], window[1] + 1)
                recs = [inp.rec[(y, base)] for y in years]
                entry["fteByYear"] = {str(y): int(r["rate_fte"]) for y, r in zip(years, recs)}
                if entry["why"] == "online":
                    entry["fteSmallerByYear"] = {str(y): opt_int(r.get("rate_fte_smaller")) for y, r in zip(years, recs)}
                if not entry["why"]:
                    del entry["why"]
                entry["codes"] = {code: wc.entry(wc.rows[base], True) for code, wc in windows[window].items()}
            obj["windows"][f"{window[0]}-{window[1]}"] = entry
        obj["flags"] = flags.get(base, [])
        write_json(JSON_DIR / RATES_INSTITUTIONS_DIR / f"{base}.json", obj, compact=True)
        rate_files.add(base)
    names = {b: inp.rec[(max(inp.years_of[b]), b)] for b in flags}
    all_flags = [{"id": b, "name": str(names[b]["institution_name"]), "state": opt(names[b].get("state")), **f}
                 for b in sorted(flags) for f in flags[b]]
    write_json(out_dir / "flags.json", {"flags": all_flags}, compact=True)
    stats["flags"] = {"total": len(all_flags),
                      "byGeo": {g: sum(1 for f in all_flags if f["geo"] == g) for g in FLAG_GEOS},
                      "byYear": {str(y): sum(1 for f in all_flags if f["year"] == y) for y in inp.data_years},
                      "byOffense": {rates.code_of(o): sum(1 for f in all_flags if f["offense"] == rates.code_of(o))
                                    for o in FLAG_OFFENSES}}
    stats["singleYear"] = {y: sum(1 for b in single if "rates" in single[b].get(y, {}))
                           for y in map(str, inp.data_years)}
    stats["institutionFiles"] = len(rate_files)
    print(f"  Institution rate files: {len(rate_files):,}; unusual-year flags: {len(all_flags):,} "
          f"({stats['flags']['byGeo']})")
    return rate_files, stats


def rate_rules(years: list[int], references: dict[int, dict[str, Fraction]]) -> dict:
    """metadata rateRules: the rate rules of config.py, with the count flag's references and the test vectors."""
    codes = sorted({code for ref in references.values() for code in ref})
    start, cap = RATE_RAMP
    c, members = TEST_VECTOR_LIST
    order = sorted(range(len(members)), key=lambda i: -Fraction(*members[i]))
    position = {}
    for k, i in enumerate(order):
        prev = order[k - 1] if k else None
        position[i] = position[prev] if k and Fraction(*members[i]) == Fraction(*members[prev]) else k + 1
    ranges = rates.rank_ranges([(n, f, position[i]) for i, (n, f) in enumerate(members)], 3, c)
    return {
        "minFte": MIN_FTE_FOR_RATE,
        "onlineUncertainRatio": list(ONLINE_UNCERTAIN_RATIO),
        "onlineShareYear": {str(y): src for y, src in sorted(ONLINE_SHARE_YEAR.items())},
        "windowYears": RATE_WINDOW_YEARS,
        "skipYears": list(RATE_SKIP_YEARS),
        "windows": [list(w) for w in rate_windows(years)],
        "codes": {code: [rates.code_of(o) for o in offenses] for code, offenses in RATE_CODES.items()},
        "countsOnly": [code for code in codes if code not in RATE_CODES],
        "ciLevel": RATE_CI_LEVEL,
        "dispersion": {"power": 1.5, "c": {code: dispersion_c(code) for code in RATE_CODES},
                       "fitted": RATE_DISPERSION, "other": RATE_DISPERSION_OTHER,
                       "ramp": {"start": start, "end": start * cap, "cap": cap}},
        "medicalShare": list(MEDICAL_CAMPUS_SHARE),
        "sharedSiteShare": list(SHARED_SITE_MAX_SHARE),
        "sharedSiteFigureYears": SHARED_SITE_FIGURE_YEARS,
        "sharedNear": {"minNonzero": SHARED_NEAR_MIN_NONZERO, "match": list(SHARED_NEAR_MATCH),
                       "minTotal": SHARED_NEAR_MIN_TOTAL},
        "lists": {"codes": list(LIST_CODES), "minExpected": LIST_MIN_EXPECTED, "alpha": LIST_ALPHA,
                  "stateMinMembers": STATE_LIST_MIN_MEMBERS, "stateDisplayMin": STATE_LIST_DISPLAY_MIN},
        "peerTypes": {key: {"label": label, "sizeSetting": list(values)} for key, (label, values) in PEER_TYPES.items()},
        "sizeSettingFields": list(SIZE_SETTING_FIELDS),
        "flags": {"offenses": [rates.code_of(o) for o in FLAG_OFFENSES], "geos": list(FLAG_GEOS),
                  "minCount": FLAG_MIN_COUNT, "minOtherYears": FLAG_MIN_OTHER_YEARS, "p": FLAG_P, "c": FLAG_C,
                  "minMean": FLAG_MIN_MEAN},
        "countFlag": {"minCount": COUNT_FLAG_MIN_COUNT, "factor": COUNT_FLAG_FACTOR,
                      "percentile": COUNT_FLAG_PERCENTILE,
                      "reference": {str(y): {code: round(float(v), 4) for code, v in sorted(ref.items())}
                                    for y, ref in sorted(references.items())}},
        "medicalScreen": {"pattern": MEDICAL_SCREEN_PATTERN, "share": list(MEDICAL_SCREEN_SHARE),
                          "minCount": MEDICAL_SCREEN_MIN_COUNT},
        "calibration": {k: (list(v) if isinstance(v, tuple) else v) for k, v in RATE_CALIBRATION.items()},
        "testVectors": {
            "counts": [{"c": cc, "years": 3, "n": n, "phi": round(rates.phi(n, 3, cc), 6),
                        "interval": [round(x, 4) for x in rates.count_interval(n, 3, cc)]}
                       for cc, ns in TEST_VECTOR_COUNTS for n in ns],
            "rates": [{"n": n, "fteYears": f, "c": cc, "rate": rates.rate_value(n, f),
                       "lo": rates.round2(rates.count_interval(n, 3, cc)[0] / f * 10000),
                       "hi": rates.round2(rates.count_interval(n, 3, cc)[1] / f * 10000)}
                      for n, f, cc in TEST_VECTOR_RATES],
            "list": {"c": c, "years": 3, "zc": round(rates.critical_z(len(members)), 6),
                     "members": [{"n": n, "fteYears": f, "position": position[i], "rankLo": ranges[i][0],
                                  "rankHi": ranges[i][1]} for i, (n, f) in enumerate(members)]},
            "criticalZ": {str(n): round(rates.critical_z(n), 4) for n in TEST_VECTOR_CRITICAL},
        },
    }


def generate_school_profiles(flags: dict[int, list[dict]], rate_files: set[int]) -> None:
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
        institution: {id, ratesFile?, byYear: {year: {campuses, online, onlineYear?, rated, notRated?,
                      counts?, ...}}}
            the school's institution (base UNITID) in the school's years, as
            rates count it (Institutions.profile_years): all its campuses'
            counts per code without shadow blocks (left out when equal to
            the school's own); fteByYear is its FTE. online is the share of
            exclusively online students the rate rules use, and onlineYear
            (in the years of ONLINE_SHARE_YEAR only) the fall it is from.
            ratesFile is the institution's rates file (write_rates:
            rates/institutions/{id}.json, its 3-year rates, single-year rates
            and flags), when it has one; one file per institution, not a
            copy in each campus's file

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
    links = id_links()
    titles = {int(r["unitid"]): (IVY_LEAGUE[int(r["unitid"])]["name"] if int(r["unitid"]) in IVY_LEAGUE
                                 else opt(r["institution_name"]), campus_of(r))
              for r in dim_inst.to_dict("records")}
    linked_written = 0
    campus_titles = 0

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
            "campus": campus_of(inst_row),
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
        if output["campus"] is None:
            del output["campus"]
        else:
            campus_titles += 1
        # The same campus under another DOE ID (campus_id_links): both pages link to each other
        if unitid in links:
            output["idChanges"] = [{**link, "name": titles[link["unitid"]][0], "campus": titles[link["unitid"]][1]}
                                   for link in links[unitid]]
            for link in output["idChanges"]:
                if link["campus"] is None:
                    del link["campus"]
            linked_written += 1
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
        inst_years = institutions.profile_years(unitid // 1000, own, flags.get(unitid // 1000, []))
        if inst_years:
            output["institution"] = {"id": unitid // 1000}
            if unitid // 1000 in rate_files:
                output["institution"]["ratesFile"] = f"{RATES_INSTITUTIONS_DIR}/{unitid // 1000}.json"
            output["institution"]["byYear"] = inst_years

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
    print(f"    Titled by their own DOE campus name (campus): {campus_titles:,}")
    print(f"    Linked to the same campus under another DOE ID (idChanges): {linked_written:,}")
    print(f"    Reported years without an incident (shown as 0): {zero_years:,}")
    print(f"  Saved to: {schools_dir}/")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    """Write one site download as UTF-8 CSV with LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    _written.add(path.relative_to(JSON_DIR).as_posix())


def generate_downloads() -> None:
    """
    Flat downloads of the published figures (downloads/ in the site data):

    - campus-years.csv: every campus-year the site shows (each year a campus
      reported to DOE, zeros included), with the campus's own DOE name and
      its institution's name, the DOE release its figures come
      from, whether it counts in rankings, its institution's NCES FTE and
      online share as the rate rules use them, its rate's denominator
      (on-campus FTE, pooled FTE added), the rule that gives it no rate, if
      any, the two on-campus FTE estimates (config.py: proportional and
      part-time first, rounded half up), whether they make the on-campus
      FTE uncertain (empty exactly when the institution has no on-campus
      FTE that year: no NCES FTE, or a campus-year that does not count) and
      why ("own", or "pooled" when only an institution pooled with it is
      uncertain), and whether the campus is a listed medical-center campus
      that year (etl/reference/medical_campuses.csv).
    - counts-YYYY.csv: every nonzero count of that year, by campus, location
      and offense, as DOE publishes it (school pages show the same figures),
      and for a location also reported identically by another campus, the
      campus it is counted under in totals and rankings.

    Read from the same tables as the rest of the site; no figure is changed.
    """
    print("Generating downloads...")
    out_dir = JSON_DIR / "downloads"
    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
    sources = pd.read_parquet(CURATED_DIR / "dims" / "campus_year_sources.parquet",
                              columns=["unitid", "year", "release"])
    sources = sources[sources["year"].isin(DATA_YEARS)]
    counted = pd.read_parquet(CURATED_DIR / "aggs" / "agg_campus_year.parquet", columns=["year", "unitid"])
    inst = pd.read_parquet(CURATED_DIR / "aggs" / "agg_institution_year.parquet",
                           columns=["year", "base_unitid", "fte", "online_pct", "online_year", "rate_fte",
                                    "rate_rule", "fte_share", "fte_part_time_first", "online_uncertain",
                                    "online_uncertain_own"])
    inst["uncertain_reason"] = [("own" if o else "pooled") if u else None
                                for u, o in zip(inst["online_uncertain"], inst["online_uncertain_own"])]
    inst = inst.drop(columns=["online_uncertain_own"])
    medical = pd.read_parquet(CURATED_DIR / "dims" / "dim_medical_campus.parquet", columns=["unitid", "year"])
    agg = pd.read_parquet(CURATED_DIR / "aggs" / "agg_school_year_offense.parquet",
                          columns=["year", "unitid", "offense", "geo", "count"])
    shared = pd.read_parquet(CURATED_DIR / "aggs" / "shared_blocks.parquet",
                             columns=["year", "unitid", "geo", "role", "host_unitid"])

    cy = sources.merge(dim_inst[["unitid", "base_unitid", "institution_name", "campus_name", "city", "state"]],
                       on="unitid", how="left", validate="many_to_one")
    if cy["base_unitid"].isna().any():
        raise SiteDataError("campus_year_sources.parquet has campuses that are not in dim_institution.parquet. "
                            "Re-run 03 and 04, then 05.")
    key = counted.assign(counts_in_rankings=True)
    cy = cy.merge(key, on=["year", "unitid"], how="left", validate="one_to_one")
    cy["counts_in_rankings"] = cy["counts_in_rankings"].eq(True)
    cy = cy.merge(inst.rename(columns={"fte": "institution_fte", "online_pct": "institution_online_pct",
                                       "online_year": "online_pct_fall", "rate_fte": "institution_rate_fte",
                                       "rate_rule": "institution_rate_rule",
                                       "fte_share": "institution_oncampus_fte_proportional",
                                       "fte_part_time_first": "institution_oncampus_fte_part_time_first",
                                       "online_uncertain": "institution_oncampus_fte_uncertain",
                                       "uncertain_reason": "institution_oncampus_fte_uncertain_reason"}),
                  on=["year", "base_unitid"], how="left", validate="many_to_one")
    # A campus of etl/reference/medical_campuses.csv that year (config.py, MEDICAL_CAMPUS_SHARE)
    medical_keys = set(zip(medical["unitid"].astype(int).tolist(), medical["year"].astype(int).tolist()))
    cy["medical_center_campus"] = [(int(u), int(y)) in medical_keys for u, y in zip(cy["unitid"], cy["year"])]
    # Without an on-campus FTE (no NCES FTE, or a campus-year that does not count) there is
    # nothing to be uncertain about: empty, not False
    cy["institution_oncampus_fte_uncertain"] = cy["institution_oncampus_fte_uncertain"].astype("boolean").where(
        cy["institution_oncampus_fte_proportional"].notna(), pd.NA)
    # The campus's own DOE name (the institution's name when DOE gives none)
    cy["campus_name"] = cy["campus_name"].where(cy["campus_name"].notna(), cy["institution_name"])
    cy = cy.rename(columns={"release": "doe_release"})
    cy["main_campus"] = cy["unitid"].astype("int64") % 1000 == 1
    cy = cy[["year", "unitid", "base_unitid", "campus_name", "institution_name", "city", "state", "main_campus", "doe_release",
             "counts_in_rankings", "institution_fte", "institution_online_pct", "online_pct_fall",
             "institution_rate_fte", "institution_rate_rule", "institution_oncampus_fte_proportional",
             "institution_oncampus_fte_part_time_first", "institution_oncampus_fte_uncertain",
             "institution_oncampus_fte_uncertain_reason", "medical_center_campus"]]
    cy = cy.sort_values(["year", "unitid"]).reset_index(drop=True)
    for col in ("institution_fte", "online_pct_fall", "institution_rate_fte", "institution_oncampus_fte_proportional",
                "institution_oncampus_fte_part_time_first"):
        cy[col] = cy[col].astype("Int64")
    write_csv(out_dir / "campus-years.csv", cy)

    facts = agg[(agg["geo"] != "All") & agg["year"].isin(DATA_YEARS)].copy()
    shadows = shared[shared["role"] == "shadow"][["year", "unitid", "geo", "host_unitid"]]
    facts = facts.merge(shadows.rename(columns={"host_unitid": "counted_under_unitid"}),
                        on=["year", "unitid", "geo"], how="left", validate="many_to_one")
    facts["counted_under_unitid"] = facts["counted_under_unitid"].astype("Int64")
    missing = facts.merge(sources, on=["year", "unitid"], how="left", indicator=True)
    if (missing["_merge"] != "both").any():
        raise SiteDataError("agg_school_year_offense.parquet has campus-years that are not in "
                            "campus_year_sources.parquet. Re-run 02 to 04, then 05.")
    rows = 0
    for year, part in facts.groupby("year"):
        part = part[["year", "unitid", "geo", "offense", "count", "counted_under_unitid"]]
        part = part.sort_values(["unitid", "geo", "offense"]).reset_index(drop=True)
        write_csv(out_dir / f"counts-{int(year)}.csv", part)
        back = pd.read_csv(out_dir / f"counts-{int(year)}.csv")
        if len(back) != len(part) or int(back["count"].sum()) != int(part["count"].sum()):
            raise SiteDataError(f"downloads/counts-{int(year)}.csv does not read back as written.")
        rows += len(part)
    print(f"  campus-years.csv: {len(cy):,} campus-years; counts-YYYY.csv: {rows:,} rows "
          f"in {facts['year'].nunique()} files")


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
        schools: [{unitid, name, campus?, short, city, state, isMainCampus, baseUnitid,
                   years: [first, last], aliases?, idChanges?: [unitid]}]
            name is the institution name; campus the campus's own DOE name
            (campus_of), which the site shows as the title; years the first and
            last year the campus reported; aliases other names to search by
            (dim_institution aliases: former DOE names and the IPEDS IALIAS
            values); idChanges the other DOE IDs of the same campus
            (campus_id_links)

    It lists every school that has a school file: every campus in
    dim_institution (every campus that reported a year, including those that
    never had an incident).
    """
    print("\nGenerating school search index...")

    dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet")
    sources = pd.read_parquet(CURATED_DIR / "dims" / "campus_year_sources.parquet", columns=["unitid", "year"])
    sources = sources[sources["year"].isin(DATA_YEARS)]
    span = {int(u): [int(g["year"].min()), int(g["year"].max())] for u, g in sources.groupby("unitid")}
    links = id_links()

    # Sort by state, then name for better UX; unitid fixes the order of same-name campuses
    dim_inst = dim_inst.sort_values(["state", "institution_name", "unitid"])

    schools = []
    aliases_written = 0
    for _, row in dim_inst.iterrows():
        unitid = int(row["unitid"])
        is_ivy = unitid in IVY_LEAGUE

        # Get campus type from dimension data
        is_main_campus = bool(row.get("is_main_campus", True))
        base_unitid = int(row.get("base_unitid", unitid // 1000))

        if is_ivy:
            ivy_info = IVY_LEAGUE[unitid]
            entry = {
                "unitid": unitid,
                "name": ivy_info["name"],
                "short": ivy_info["short"],
                "city": ivy_info["city"],
                "state": ivy_info["state"],
                "isMainCampus": is_main_campus,
                "baseUnitid": base_unitid
            }
        else:
            entry = {
                "unitid": unitid,
                "name": opt(row.get("institution_name")) or f"School {unitid}",
                "short": row.get("short_name") if pd.notna(row.get("short_name")) else None,
                "city": row.get("city") if pd.notna(row.get("city")) else None,
                "state": row.get("state") if pd.notna(row.get("state")) else None,
                "isMainCampus": is_main_campus,
                "baseUnitid": base_unitid
            }
        campus = campus_of(row)
        if campus:
            entry["campus"] = campus
        entry["years"] = span[unitid]
        shown = {str(entry["name"]).lower(), str(campus or "").lower()}
        aliases = [a for a in (row.get("aliases") if row.get("aliases") is not None else [])
                   if str(a).lower() not in shown]
        if aliases:
            entry["aliases"] = [str(a) for a in aliases]
            aliases_written += len(aliases)
        if unitid in links:
            entry["idChanges"] = [link["unitid"] for link in links[unitid]]
        schools.append(entry)

    output = {"schools": schools}

    write_json(JSON_DIR / "school-index.json", output)

    print(f"  Indexed {len(schools)} schools ({sum('campus' in s for s in schools):,} with a campus name, "
          f"{aliases_written:,} aliases, {sum('idChanges' in s for s in schools):,} with another DOE ID)")
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
        presets = generate_presets()
        result = rates.build()
        rate_files, rate_stats = write_rates(result)
        count_stats = generate_rankings_json(result["countFlagReference"])
        rate_stats["countFlags"] = count_stats["countFlags"]
        rate_stats["institutionYears"] = count_stats["institutionYears"]
        metadata = generate_metadata(inputs_before.records["04"], rate_stats,
                                     rate_rules(result["inputs"].data_years, result["countFlagReference"]))
        generate_school_profiles(result["flags"], rate_files)
        generate_downloads()

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
    rate_files = list((JSON_DIR / "rates").rglob("*.json"))

    print(f"Root JSON files: {len(json_files)}")
    print(f"Ranking files: {len(ranking_files)}")
    print(f"School files: {len(school_files)}")
    print(f"Rate files: {len(rate_files)}")

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
