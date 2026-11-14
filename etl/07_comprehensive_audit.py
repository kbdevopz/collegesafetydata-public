"""
Comprehensive Data Audit - Validates ALL schools in the dataset.

This script performs thorough validation of all schools:
1. School Completeness - All schools in facts have JSON files
2. Incident Totals - JSON yearlyTotals match aggregate data
3. FTE Coverage - Report enrollment data coverage by year
4. Rate Calculations - Verify rate = (count / FTE) * 10,000 in every rate ranking
5. Ranking Order - Ranks are competition ranks (1, 2, 2, 4) of the counts, and of the rates
6. Ranking Totals - Each file's totals and campus/institution tables agree with its rankings
7. Aggregate Consistency - Aggregates equal the fact table, per year and geography
8. Shared Statistics - Figures two campuses report identically (in the data
   used, or in the older release a campus-year is taken from) are counted
   once in rankings and totals, under one host, and school files say so
9. Enrollment Sources - FTE and the share of exclusively online students are
   NCES's own (official FTE for every year, none estimated)
10. Institution Rates - Rates are per institution (all its campuses, its
   FTE), and rate rankings list exactly the institutions config.py allows
   (enough FTE, not mostly online)
11. Campus Identity - etl/reference/campus_id_changes.csv lists exactly the
   campus ID changes found again in the DOE names (with the same evidence),
   every "link" pair meets the rules, both school files link to each other,
   no figures move between the IDs, and every school file is in the search
   index under its DOE campus name

Each check's details say in "what_it_checks" exactly what it verifies. Checks
1-8, 10 and 11 compare the pipeline's own files with each other; check 9 re-reads
NCES's enrollment figures (the DRVEF CSVs and etl/reference). None re-reads
the DOE downloads.

Usage:
    python 07_comprehensive_audit.py
    python 07_comprehensive_audit.py --verbose
    python 07_comprehensive_audit.py --stop-on-fail

Output:
    - Console: Summary with pass/fail per check
    - CSV: data/qa/comprehensive_audit.csv (per-school results)
    - JSON: data/qa/comprehensive_audit.json (machine-readable). Its
      generated_at is UTC, and "audited_build" holds the SHA-256 of the site's
      build record (frontend/public/data/build_inputs.json) and of each curated
      file the checks read, so 00_check_for_updates.py can tell whether
      frontend/public/audit.json is the audit of the site data it ships with.
"""

import os
import sys
import json
import bisect
import itertools
import argparse
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, QA_DIR, JSON_DIR, DATA_YEARS, PROJECT_ROOT, GEO_CODES, GEO_FOR_ALL,
                    OFFENSE_ORDER, SHARED_MIN_NONZERO, US_STATES, IVY_LEAGUE, IVY_BASE_UNITIDS,
                    SUMMARY_FAMILIES, MIN_FTE_FOR_RATE, ONLINE_EXCLUSION_PCT, ONLINE_SHARE_YEAR)
import provenance
import campus_identity

# Curated files the checks read (relative to data/curated)
CURATED_READ = ("facts/incidents.parquet", "aggs/agg_school_year_offense.parquet", "dims/dim_enrollment.parquet",
                "dims/dim_institution.parquet", "dims/campus_year_sources.parquet",
                "dims/older_release_counts.parquet", "aggs/shared_blocks.parquet",
                "dims/campus_names.parquet", "dims/campus_id_links.parquet")
# FTE coverage: share of the schools with crime data in a year that have an FTE for that year
FTE_COVERAGE_FAIL = 95.0  # below this in any year with enrollment, the check fails
FTE_COVERAGE_WARN = 99.0  # below this, a warning (2015-2024 are 99.4-100% today)
# A pct is count / group total x 100 rounded to 2 decimals, so it is off by at most half a hundredth
PCT_TOLERANCE = 0.005 + 1e-6


class AuditResult:
    """Container for audit check results."""
    def __init__(self, name: str):
        self.name = name
        self.status = "PENDING"
        self.details = {}
        self.errors = []
        self.warnings = []

    def passed(self):
        # A check that has already failed or warned keeps that status
        if self.status == "PENDING":
            self.status = "PASS"

    def failed(self, error: str):
        self.status = "FAIL"
        self.errors.append(error)

    def warning(self, msg: str):
        if self.status in ("PENDING", "PASS"):
            self.status = "WARNING"
        self.warnings.append(msg)

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"


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
            f"(move them outside data/curated to keep them), then run 03 to 07 again."
        )
    if not FACTS_PATH.is_file():
        raise RuntimeError(f"{FACTS_PATH} not found. Run 02_transform_to_parquet.py first.")
    return str(FACTS_PATH)


def reported_years() -> dict[int, set[int]]:
    """
    The years of DATA_YEARS each campus reported, from 02's
    campus_year_sources.parquet (a campus-year is reported when its release
    row has at least one count cell that is not blank, zeros included).
    """
    sources = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py", ["unitid", "year"])
    sources = sources[sources["year"].isin(DATA_YEARS)]
    out: dict[int, set[int]] = {}
    for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist()):
        out.setdefault(int(u), set()).add(int(y))
    return out


def audit_school_completeness(verbose: bool = False) -> AuditResult:
    """
    CHECK 1: Every campus that reported a year (zeros included) has a school
    file, and every school file is such a campus; every school in the facts
    reported.
    """
    result = AuditResult("School Completeness")
    print("\nCHECK 1: School Completeness")

    try:
        # Get unique schools from facts
        con = duckdb.connect()
        facts_file = get_facts_path()

        facts_schools = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_file}')
        """).df()

        facts_unitids = set(int(u) for u in facts_schools["unitid"].tolist())
        print(f"  Schools in facts: {len(facts_unitids):,}")
        reported = set(reported_years())
        print(f"  Schools that reported a year: {len(reported):,} "
              f"({len(reported - facts_unitids):,} of them never had an incident)")
        unreported = facts_unitids - reported

        # Get JSON files
        schools_dir = JSON_DIR / "schools"
        json_files = list(schools_dir.glob("*.json"))
        json_unitids = set()

        for f in json_files:
            try:
                unitid = int(f.stem)
                json_unitids.add(unitid)
            except ValueError:
                pass

        print(f"  JSON files generated: {len(json_unitids):,}")

        # Find missing
        missing_json = reported - json_unitids
        extra_json = json_unitids - reported

        # The search index must list exactly the schools with a file (a school
        # missing from it can only be reached by a link)
        index_path = JSON_DIR / "school-index.json"
        if not index_path.is_file():
            raise RuntimeError(f"{index_path} not found. Run 05_generate_json.py.")
        index_entries = json.loads(index_path.read_text(encoding="utf-8")).get("schools", [])
        index_unitids = [int(s["unitid"]) for s in index_entries]
        print(f"  Schools in school-index.json: {len(index_unitids):,}")

        result.details["what_it_checks"] = (
            "Every campus (UNITID) that reported a year of DATA_YEARS in data/curated/dims/campus_year_sources.parquet "
            "(a release row with a count cell that is not blank, zeros included) has a site file "
            "schools/<UNITID>.json, every school file is such a campus, every school in "
            "data/curated/facts/incidents.parquet reported, and school-index.json (the site search) lists every "
            "school file once and nothing else. It compares file names only; check 2 and the per-school report "
            "compare the files' numbers.")
        result.details["schools_in_search_index"] = len(index_unitids)
        result.details["schools_in_facts"] = len(facts_unitids)
        result.details["schools_reported"] = len(reported)
        result.details["schools_reported_never_an_incident"] = len(reported - facts_unitids)
        result.details["json_files_generated"] = len(json_unitids)
        result.details["missing_json"] = len(missing_json)
        result.details["extra_json"] = len(extra_json)

        if not facts_unitids:
            result.failed("The fact table has no schools. Run 02_transform_to_parquet.py and 03 to 07 again.")
        if unreported:
            result.failed(f"{len(unreported)} schools have facts but reported no year in campus_year_sources.parquet "
                          f"(first: {sorted(unreported)[0]}). Run 02_transform_to_parquet.py and 03 to 07 again.")
        if len(index_unitids) != len(set(index_unitids)) or set(index_unitids) != json_unitids:
            diff = sorted(set(index_unitids) ^ json_unitids)
            result.failed(f"school-index.json lists {len(index_unitids):,} schools ({len(set(index_unitids)):,} "
                          f"distinct) but there are {len(json_unitids):,} school files"
                          f"{f' (first difference: {diff[0]})' if diff else ''}. Run 05_generate_json.py, then 07 again.")
        if missing_json:
            result.failed(f"Missing JSON files for {len(missing_json)} schools")
            if verbose and len(missing_json) <= 10:
                print(f"    Missing: {sorted(missing_json)[:10]}")
        else:
            result.passed()
            print(f"  Missing JSONs: 0")

        if extra_json:
            result.warning(f"Found {len(extra_json)} JSON files of campuses that reported no year "
                           f"(first: schools/{sorted(extra_json)[0]}.json). Run 05_generate_json.py "
                           f"again: it removes school files it did not write.")

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_incident_totals(verbose: bool = False) -> AuditResult:
    """
    CHECK 2: Verify JSON yearlyTotals match aggregate data for ALL schools.
    """
    result = AuditResult("Incident Total Accuracy")
    print("\nCHECK 2: Incident Total Accuracy")

    try:
        # Load aggregate data
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        if not agg_path.exists():
            result.failed("Aggregate file not found")
            return result

        agg = pd.read_parquet(agg_path)

        # Sum by school and year (across all offenses, geo="All")
        agg_totals = agg[agg["geo"] == "All"].groupby(["unitid", "year"])["count"].sum()
        agg_by_school = {}  # unitid -> {year: total}
        for (uid, year), total in agg_totals.items():
            agg_by_school.setdefault(int(uid), {})[int(year)] = int(total)

        # Load each school JSON and compare
        schools_dir = JSON_DIR / "schools"
        json_files = list(schools_dir.glob("*.json"))
        years_of = reported_years()

        variances = []
        year_problems = []  # files whose years are not the years the campus reported
        schools_validated = 0
        schools_with_variance = 0

        for json_file in json_files:
            try:
                unitid = int(json_file.stem)
            except ValueError:
                continue

            with open(json_file) as f:
                school_data = json.load(f)

            yearly_totals = {int(yt["year"]): yt["total"] for yt in school_data.get("yearlyTotals", [])}
            want_years = years_of.get(unitid, set())
            not_reported = sorted(set(DATA_YEARS) - want_years)
            if set(yearly_totals) != want_years or school_data.get("notReported", []) != not_reported:
                year_problems.append(f"schools/{unitid}.json: years {sorted(yearly_totals)}, notReported "
                                     f"{school_data.get('notReported', [])}; reported {sorted(want_years)}")

            # Compare every year in either: a year the file shows that the aggregates lack is a variance too
            school_agg = agg_by_school.get(unitid, {})

            for year in sorted(set(school_agg) | set(yearly_totals)):
                agg_total = school_agg.get(year, 0)
                json_total = yearly_totals.get(year, 0)

                if agg_total != json_total:
                    variances.append({
                        "unitid": unitid,
                        "year": year,
                        "agg_total": agg_total,
                        "json_total": json_total,
                        "variance": json_total - agg_total
                    })

            schools_validated += 1

            if schools_validated % 1000 == 0:
                print(f"  Validated {schools_validated:,} schools...")

        schools_with_variance = len(set(v["unitid"] for v in variances))

        result.details["what_it_checks"] = (
            "For every site school file schools/<UNITID>.json, the yearlyTotals years are exactly the years the "
            "campus reported (campus_year_sources.parquet, zeros included) and notReported the other years of "
            "DATA_YEARS, and the total of each year (every year in the file or the aggregates; 0 when the "
            "aggregates have none) equals the sum over offenses of that school's geo \"All\" rows in "
            "agg_school_year_offense.parquet. The files' trends and breakdowns are not compared, and check 7 "
            "compares the aggregates with the fact table.")
        result.details["schools_validated"] = schools_validated
        result.details["variances_found"] = len(variances)
        result.details["files_with_other_years"] = len(year_problems)
        result.details["reported_years_without_an_incident"] = sum(
            1 for u, ys in years_of.items() for y in ys if y not in agg_by_school.get(u, {}))
        result.details["schools_with_variance"] = schools_with_variance

        print(f"  Schools validated: {schools_validated:,} / {len(json_files):,}")
        print(f"  Variances found: {len(variances)}")
        print(f"  Files whose years are not the years the campus reported: {len(year_problems)}")

        if year_problems:
            result.failed(f"{len(year_problems)} school files do not have exactly the years the campus reported "
                          f"(first: {year_problems[0]}). Run 05_generate_json.py, then 07 again.")
        if variances:
            v = variances[0]
            result.failed(f"Found {len(variances)} incident count variances across {schools_with_variance} schools "
                          f"(first: {v['unitid']} {v['year']}: JSON {v['json_total']}, aggregates {v['agg_total']}). "
                          f"Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for v in variances[:5]:
                    print(f"    {v['unitid']} ({v['year']}): JSON={v['json_total']}, Agg={v['agg_total']}")
        elif schools_validated == 0:
            result.failed(f"No school files in {schools_dir} to check. Run 05_generate_json.py.")
        elif not year_problems:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def published_enrollment_status() -> dict:
    """metadata.json's enrollmentStatus (year -> final, provisional or missing); empty if it has none."""
    try:
        metadata = json.loads((JSON_DIR / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    status = metadata.get("enrollmentStatus") if isinstance(metadata, dict) else None
    return status if isinstance(status, dict) else {}


def audit_fte_coverage(verbose: bool = False) -> AuditResult:
    """
    CHECK 3: FTE coverage by year: of the schools with crime data in a year,
    the share that have an FTE (so a rate) for that year. A year whose
    enrollment NCES has not published (enrollmentStatus "missing") is expected
    to have none.
    """
    result = AuditResult("FTE Coverage")
    print("\nCHECK 3: FTE Coverage by Year")

    try:
        # Schools with crime data per year, and those of them with an FTE for that year
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        agg = pd.read_parquet(agg_path, columns=["year", "unitid", "fte"])
        has_fte = agg["fte"].astype("float64").fillna(0) > 0
        schools = agg.groupby("year")["unitid"].nunique()
        with_fte = agg[has_fte].groupby("year")["unitid"].nunique()
        status = published_enrollment_status()

        rows = []
        total_schools = total_with_fte = 0
        for year in sorted(int(y) for y in schools.index):
            count = int(schools[year])
            fte_count = int(with_fte.get(year, 0))
            pct = round(fte_count / count * 100, 1) if count else 0.0
            enrollment = status.get(str(year), "unknown")
            rows.append({"year": year, "schools_with_data": count, "schools_with_fte": fte_count,
                         "coverage_pct": pct, "enrollment": enrollment})
            note = " (no enrollment published yet)" if enrollment == "missing" else ""
            print(f"  {year}: {fte_count:,} / {count:,} schools with crime data have an FTE ({pct}%){note}")
            if fte_count > count:
                result.failed(f"{year}: {fte_count} schools with an FTE but only {count} with crime data")
            elif enrollment == "missing":
                if fte_count:
                    result.failed(f"{year}: metadata.json says there is no enrollment, yet {fte_count} "
                                  "schools have an FTE")
            else:
                total_schools += count
                total_with_fte += fte_count
                if pct < FTE_COVERAGE_FAIL:
                    result.failed(f"{year}: only {pct}% of schools with crime data have an FTE "
                                  f"(below {FTE_COVERAGE_FAIL}%)")
                elif pct < FTE_COVERAGE_WARN:
                    result.warning(f"{year}: {pct}% of schools with crime data have an FTE "
                                   f"(below {FTE_COVERAGE_WARN}%)")

        overall_coverage = (total_with_fte / total_schools * 100) if total_schools > 0 else 0
        result.details["what_it_checks"] = (
            "Of the schools with crime data in each year in agg_school_year_offense.parquet, the share "
            "that have an FTE above 0 for that year in the same file (metadata.json's enrollmentStatus "
            "names the years NCES has not published). It does not compare FTE values with the IPEDS files.")
        result.details["by_year"] = rows
        result.details["overall_coverage_pct"] = round(overall_coverage, 1)
        result.details["years_without_enrollment"] = [r["year"] for r in rows if r["enrollment"] == "missing"]
        result.details["thresholds_pct"] = {"fail_below": FTE_COVERAGE_FAIL, "warn_below": FTE_COVERAGE_WARN}
        print(f"  Overall (years with enrollment): {total_with_fte:,} / {total_schools:,} ({overall_coverage:.1f}%)")

        if not rows:
            result.failed("No schools with crime data in the aggregates")
        if result.status == "PENDING":
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


RATE_TOLERANCE = 0.005 + 1e-9  # rates are rounded to 2 decimals


def ranking_files_data() -> list[tuple[Path, dict]]:
    """Every rankings/*.json file and its content."""
    out = []
    for ranking_file in sorted((JSON_DIR / "rankings").glob("*.json")):
        with open(ranking_file, encoding="utf-8") as f:
            out.append((ranking_file, json.load(f)))
    return out


def audit_rate_calculations(verbose: bool = False) -> AuditResult:
    """
    CHECK 4: Verify rate calculations are mathematically correct.
    rate = (count / FTE) * 10,000, rounded to 2 decimals, for every entry of
    every rate ranking, with the FTE of the entry's institution.
    """
    result = AuditResult("Rate Calculation Accuracy")
    print("\nCHECK 4: Rate Calculation Accuracy")

    try:
        rate_errors = []
        entries_checked = 0
        files = ranking_files_data()

        for ranking_file, data in files:
            table = data.get("institutions") or {}
            for code, entries in (data.get("rateRankings") or {}).items():
                for entry in entries:
                    inst = table.get(str(entry.get("id")))
                    fte = (inst or {}).get("fte")
                    count, rate = entry.get("count"), entry.get("rate")
                    entries_checked += 1
                    if not isinstance(fte, int) or fte <= 0:
                        rate_errors.append(f"{ranking_file.name}/{code}: institution {entry.get('id')} has no "
                                           "FTE above 0 in the file's institutions")
                    elif not isinstance(rate, (int, float)) or not isinstance(count, int) \
                            or abs(rate - count / fte * 10000) > RATE_TOLERANCE:
                        rate_errors.append(f"{ranking_file.name}/{code}: institution {entry.get('id')}: count "
                                           f"{count}, fte {fte}, rate {rate}, expected "
                                           f"{(count or 0) / fte * 10000:.4f}")

        result.details["what_it_checks"] = (
            "For every entry of every rateRankings list of rankings/*.json, rate equals count / fte x 10,000 to "
            "2 decimals (within 0.005), with the FTE of the entry's institution in the file's institutions "
            "table, which must be above 0. Check 10 compares the counts and FTE with the facts and NCES's "
            "enrollment.")
        result.details["rate_entries_checked"] = entries_checked
        result.details["rate_errors"] = len(rate_errors)

        print(f"  Rate entries checked: {entries_checked:,}")
        print(f"  Rates that are not count / FTE x 10,000 (to 2 decimals): {len(rate_errors)}")

        if rate_errors:
            result.failed(f"Found {len(rate_errors)} rate calculation errors (first: {rate_errors[0]}). "
                          "Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for err in rate_errors[:5]:
                    print(f"    {err}")
        elif entries_checked == 0:
            result.failed("No rate ranking entry in rankings/ to check. Run 04_create_aggregates.py "
                          "and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def competition_rank_problems(entries: list, value: str) -> list[str]:
    """
    Problems with the standard competition ranks ("1, 2, 2, 4") of entries
    ranked by `value`: each rank must be 1 + the number of entries with a
    larger value.
    """
    problems = []

    def number(e):
        v = e.get(value)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    negated = sorted(-number(e) for e in entries if number(e) is not None)  # bisect: how many are larger
    for e in entries:
        if number(e) is None:
            problems.append(f"{e.get('unitid', e.get('id'))}: no {value}")
            continue
        want = 1 + bisect.bisect_left(negated, -number(e))
        if e.get("rank") != want:
            problems.append(f"{e.get('unitid', e.get('id'))}: rank {e.get('rank')} for {value} {number(e)}, "
                            f"expected {want} (1 + the entries with a larger {value})")
    return problems


def audit_ranking_order(verbose: bool = False) -> AuditResult:
    """
    CHECK 5: Ranks are standard competition ranks, and the entries are
    listed in ranking order.

    In each count ranking (one code of a file's "rankings") the entries are
    listed by count, largest first, ties by name (from the file's campuses
    table), then UNITID; each rank is 1 + the number of entries with a larger
    count (tied counts share a rank: 1, 2, 2, 4). Each rate ranking
    ("rateRankings") likewise by rate, ties by institution name, then base
    UNITID.
    """
    result = AuditResult("Ranking Order Validation")
    print("\nCHECK 5: Ranking Order Validation")

    try:
        order_violations = []
        groups_validated = 0
        entries_checked = 0

        for ranking_file, data in ranking_files_data():
            campuses = data.get("campuses") or {}
            institutions = data.get("institutions") or {}
            lists = [("rankings", code, entries, "count", "unitid", campuses)
                     for code, entries in (data.get("rankings") or {}).items()]
            lists += [("rateRankings", code, entries, "rate", "id", institutions)
                      for code, entries in (data.get("rateRankings") or {}).items()]
            for kind, code, entries, value, ident, table in lists:
                if not entries:
                    continue
                groups_validated += 1
                entries_checked += len(entries)

                def violation(text):
                    order_violations.append({"file": ranking_file.name, "offense": f"{kind}/{code}", "problem": text})

                def key(e):
                    v = e.get(value)
                    name = (table.get(str(e.get(ident))) or {}).get("name") or ""
                    return (-(v if isinstance(v, (int, float)) else 0), name, e.get(ident) or 0)
                for i, (current, next_entry) in enumerate(zip(entries, entries[1:])):
                    if key(current) > key(next_entry):
                        violation(f"entry {i + 1} ({current.get(ident)}, {value} {current.get(value)}) is "
                                  f"listed before {next_entry.get(ident)} ({value} {next_entry.get(value)})")
                        break
                for text in competition_rank_problems(entries, value)[:1]:
                    violation(text)

        result.details["what_it_checks"] = (
            "In every count ranking (one code of a rankings/*.json file's rankings, the summary codes included), "
            "entries are listed by count, largest first, ties by name (the file's campuses table), then UNITID, "
            "and each rank is 1 + the number of entries with a larger count, so tied counts share a rank "
            "(1, 2, 2, 4). Every rate ranking (rateRankings) likewise by rate, ties by institution name, then base "
            "UNITID. It checks the order of each file's own counts and rates; check 4 checks the rates' arithmetic.")
        result.details["groups_validated"] = groups_validated
        result.details["entries_checked"] = entries_checked
        result.details["order_violations"] = len(order_violations)

        print(f"  Rankings (file x code, counts and rates) validated: {groups_validated:,} "
              f"({entries_checked:,} entries)")
        print(f"  Rank or order violations: {len(order_violations)}")

        if order_violations:
            v = order_violations[0]
            result.failed(f"Found {len(order_violations)} rank order violations (first: {v['file']}/{v['offense']}: "
                          f"{v['problem']}). Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for v in order_violations[:5]:
                    print(f"    {v['file']}/{v['offense']}: {v['problem']}")
        elif groups_validated == 0:
            result.failed("No rankings in rankings/ to check. Run 04_create_aggregates.py and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_ranking_totals(verbose: bool = False) -> AuditResult:
    """
    CHECK 6: Each file's totals and tables agree with its rankings.

    totals[code] equals the sum of the counts of rankings[code]; every
    ranked campus is in the file's campuses table and every campus of the
    table is ranked under some code; every rate-ranked institution is in the
    file's institutions table and every institution of the table has an FTE
    above 0. (The site shows each campus's share of the total as count /
    total.)
    """
    result = AuditResult("Ranking Totals and Tables")
    print("\nCHECK 6: Ranking Totals and Tables")

    try:
        problems = []
        groups_validated = 0

        for ranking_file, data in ranking_files_data():
            totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
            campuses = data.get("campuses") or {}
            institutions = data.get("institutions") or {}
            rankings = data.get("rankings") or {}
            ranked_ids = set()
            for code, entries in rankings.items():
                groups_validated += 1
                group_total = sum(e.get("count", 0) for e in entries)
                if totals.get(code) != group_total:
                    problems.append(f"{ranking_file.name}/{code}: totals says {totals.get(code)}, "
                                    f"the counts sum to {group_total}")
                ranked_ids |= {str(e.get("unitid")) for e in entries}
            if set(totals) != set(rankings):
                problems.append(f"{ranking_file.name}: totals has codes {sorted(set(totals) ^ set(rankings))[:3]} "
                                "without a ranking, or the reverse")
            if ranked_ids - set(campuses):
                diff = sorted(ranked_ids - set(campuses))
                problems.append(f"{ranking_file.name}: {len(diff)} ranked campuses are not in the campuses table "
                                f"(first: {diff[0]})")
            rate_ids = {str(e.get("id")) for entries in (data.get("rateRankings") or {}).values() for e in entries}
            if rate_ids - set(institutions):
                problems.append(f"{ranking_file.name}: rate-ranked institutions missing from the institutions table "
                                f"(first: {sorted(rate_ids - set(institutions))[0]})")
            bad_fte = [k for k, v in institutions.items() if not isinstance(v.get("fte"), int) or v["fte"] <= 0]
            if bad_fte:
                problems.append(f"{ranking_file.name}: institutions without an FTE above 0 (first: {bad_fte[0]})")

        result.details["what_it_checks"] = (
            "In every rankings/*.json file, totals[code] equals the sum of rankings[code]'s counts for every code, "
            "the campuses table holds every ranked campus (and the campuses ranked with 0, which check 10 checks), "
            "and the institutions table every rate-ranked institution, each with an FTE above 0. It checks the "
            "files' own numbers; check 8 compares the counts with the facts.")
        result.details["groups_validated"] = groups_validated
        result.details["problems"] = len(problems)

        print(f"  Rankings validated: {groups_validated:,}")
        print(f"  Problems: {len(problems)}")

        if problems:
            result.failed(f"Found {len(problems)} problems (first: {problems[0]}). Run 04_create_aggregates.py and "
                          "05_generate_json.py, then 07 again.")
            if verbose:
                for p in problems[:5]:
                    print(f"    {p}")
        elif groups_validated == 0:
            result.failed("No rankings in rankings/ to check. Run 04_create_aggregates.py and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def sql_strings(names) -> str:
    """A SQL list of string literals."""
    return ", ".join("'" + str(n).replace("'", "''") + "'" for n in names)


def audit_aggregate_consistency(verbose: bool = False) -> AuditResult:
    """
    CHECK 7: The aggregates hold exactly the fact table's counts.
    Ensures no data loss during aggregation, by the rules of
    04_create_aggregates.py: for every year, school, offense and geography in
    the facts, an aggregate row with the same total (Residence halls
    included), and an "All" row with the sum of the GEO_FOR_ALL geographies
    (On-campus, Non-campus, Public property). Residence halls are a subset of
    On-campus, so "All" leaves them out. Any difference, in any year or
    geography, fails the check, as do fact rows 04 cannot place: no count, no
    year/school/offense/geography, or a geography not in GEO_CODES (04 would
    leave it out of "All").
    """
    result = AuditResult("Aggregate Consistency")
    print("\nCHECK 7: Aggregate Consistency")

    try:
        con = duckdb.connect()
        facts_file = get_facts_path()
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        if not agg_path.is_file():
            result.failed(f"{agg_path} not found. Run 04_create_aggregates.py.")
            print(f"  {result.status}")
            return result

        result.details["what_it_checks"] = (
            "From data/curated/facts/incidents.parquet, with the rules of 04_create_aggregates.py, the count "
            "of every row of agg_school_year_offense.parquet: each year, school, offense and geography "
            "(Residence halls included), and \"All\" = On-campus + Non-campus + Public property (Residence "
            "halls are a subset of On-campus, so \"All\" leaves them out). Every row must match exactly; the "
            "totals per year and geography are shown. This proves that no count was lost, added or changed "
            "between the facts and the aggregates. It does not re-read the DOE files, so it cannot detect a "
            "value that 02_transform_to_parquet.py read wrongly from them.")

        # Fact rows 04 cannot place
        fact_rows, no_count, no_key, first_year, last_year = con.execute(f"""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE count IS NULL),
                   COUNT(*) FILTER (WHERE year IS NULL OR unitid IS NULL OR offense IS NULL OR geo IS NULL),
                   MIN(year), MAX(year)
            FROM read_parquet('{facts_file}')
        """).fetchone()
        other_geos = con.execute(f"""
            SELECT geo, COUNT(*), CAST(COALESCE(SUM(count), 0) AS BIGINT)
            FROM read_parquet('{facts_file}')
            WHERE geo NOT IN ({sql_strings(GEO_CODES.values())})
            GROUP BY geo ORDER BY geo
        """).fetchall()

        # Every aggregate row as 04 makes it from the facts, next to the row 04 wrote
        same_key = " AND ".join(f"e.{k} IS NOT DISTINCT FROM a.{k}" for k in ("year", "unitid", "offense", "geo"))
        joined = f"""
            WITH f AS (
                SELECT year, unitid, offense, geo, count FROM read_parquet('{facts_file}')
            ),
            expected AS (
                SELECT year, unitid, offense, geo, SUM(n) AS n FROM (
                    SELECT year, unitid, offense, geo, count AS n FROM f
                    UNION ALL
                    SELECT year, unitid, offense, 'All' AS geo, count AS n FROM f
                    WHERE geo IN ({sql_strings(GEO_FOR_ALL)})
                ) AS fact_rows
                GROUP BY year, unitid, offense, geo
            ),
            actual AS (
                SELECT year, unitid, offense, geo, SUM(count) AS n
                FROM read_parquet('{agg_path}')
                GROUP BY year, unitid, offense, geo
            ),
            joined AS (
                SELECT COALESCE(e.year, a.year) AS year, COALESCE(e.unitid, a.unitid) AS unitid,
                       COALESCE(e.offense, a.offense) AS offense, COALESCE(e.geo, a.geo) AS geo,
                       e.n AS facts, a.n AS aggregates
                FROM expected e FULL OUTER JOIN actual a ON {same_key}
            )
        """
        by_year_geo = []
        rows_compared = rows_differing = 0
        for year, geo, facts, aggregates, compared, differing in con.execute(joined + """
            SELECT year, geo,
                   CAST(COALESCE(SUM(facts), 0) AS BIGINT), CAST(COALESCE(SUM(aggregates), 0) AS BIGINT),
                   COUNT(*), COUNT(*) FILTER (WHERE facts IS DISTINCT FROM aggregates)
            FROM joined
            GROUP BY year, geo
            ORDER BY year NULLS LAST, geo NULLS LAST
        """).fetchall():
            by_year_geo.append({"year": year, "geo": geo, "facts": facts, "aggregates": aggregates,
                                "variance": aggregates - facts, "rows_differing": differing})
            rows_compared += compared
            rows_differing += differing
        first_differences = con.execute(joined + """
            SELECT year, unitid, offense, geo, CAST(facts AS BIGINT), CAST(aggregates AS BIGINT)
            FROM joined
            WHERE facts IS DISTINCT FROM aggregates
            ORDER BY year NULLS LAST, geo NULLS LAST, unitid NULLS LAST, offense NULLS LAST
            LIMIT 5
        """).fetchall() if rows_differing else []

        def totals(geo):
            facts = sum(r["facts"] for r in by_year_geo if r["geo"] == geo)
            aggregates = sum(r["aggregates"] for r in by_year_geo if r["geo"] == geo)
            return {"facts": facts, "aggregates": aggregates, "variance": aggregates - facts}

        span = f"{first_year}-{last_year}" if fact_rows else "none"
        result.details["years"] = span
        result.details["fact_rows"] = fact_rows
        result.details["all"] = totals("All")
        result.details["residence_halls"] = totals("Residence halls")
        result.details["aggregate_rows_compared"] = rows_compared
        result.details["aggregate_rows_differing"] = rows_differing
        result.details["by_year_geo"] = by_year_geo

        print(f"  Fact table ({span}): {fact_rows:,} rows")
        print(f"  \"All\" = {' + '.join(GEO_FOR_ALL)}; Residence halls (a subset of On-campus) are compared on their own")
        print(f"    {'Year':<6}{'Geography':<18}{'Facts':>12}{'Aggregates':>12}{'Variance':>10}  (aggregates - facts)")
        for r in by_year_geo:
            print(f"    {str(r['year']):<6}{str(r['geo']):<18}{r['facts']:>12,}{r['aggregates']:>12,}{r['variance']:>10,}")
        for label, t in (("All", result.details["all"]), ("Residence halls", result.details["residence_halls"])):
            print(f"  {label} ({span}): facts {t['facts']:,}, aggregates {t['aggregates']:,}, variance {t['variance']:,}")
        print(f"  Aggregate rows compared: {rows_compared:,}; differing from the facts: {rows_differing:,}")

        if not fact_rows:
            result.failed("The fact table has no rows. Run 02_transform_to_parquet.py and 03 to 07 again.")
        if no_count:
            result.failed(f"{no_count:,} fact rows have no count, so the aggregates add nothing for them. "
                          f"Run 02_transform_to_parquet.py and 03 to 07 again.")
        if no_key:
            result.failed(f"{no_key:,} fact rows have no year, UNITID, offense or geography. "
                          f"Run 02_transform_to_parquet.py and 03 to 07 again.")
        for geo, n, count in other_geos:
            result.failed(f"{n:,} fact rows ({count:,} incidents) have geography {geo!r}, which is not one of "
                          f"{', '.join(GEO_CODES.values())}, so 04 leaves them out of \"All\". Check GEO_CODES "
                          f"in config.py and 02_transform_to_parquet.py.")
        for r in by_year_geo:
            if r["variance"] or r["rows_differing"]:
                result.failed(f"{r['year']} {r['geo']}: facts {r['facts']:,}, aggregates {r['aggregates']:,} "
                              f"(variance {r['variance']:+,}; {r['rows_differing']:,} school-offense rows differ)")
        if rows_differing:
            def shown(n):
                return "none" if n is None else f"{n:,}"
            first = "; ".join(f"{y} {u} {o} {g}: facts {shown(f)}, aggregates {shown(a)}"
                              for y, u, o, g, f, a in first_differences[:3])
            result.failed(f"{rows_differing:,} aggregate rows differ from the facts (first: {first}). "
                          f"Run 04_create_aggregates.py, then 05_generate_json.py and 07 again.")
            if verbose:
                for y, u, o, g, f, a in first_differences:
                    print(f"    {y} {u} {o} {g}: facts={shown(f)}, agg={shown(a)}")

        if result.status == "PENDING":
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def read_curated(name: str, step: str, columns=None) -> pd.DataFrame:
    """A curated file, or an error naming the step that writes it."""
    path = CURATED_DIR / name
    if not path.is_file():
        raise RuntimeError(f"{path} not found. Run {step}, then the later steps and 07 again.")
    return pd.read_parquet(path, columns=columns)


def audit_shared_statistics(verbose: bool = False) -> AuditResult:
    """
    CHECK 8: Statistics that two or more campuses report identically are
    counted once, under one host campus.

    Without 04's code, from the fact table and dims/older_release_counts.parquet
    (every campus's counts in each older release a campus-year is taken
    from), it finds the shadow blocks again by the four rules of
    find_shared_blocks, in the same order; copies only between campuses of
    the same ranked state, at least SHARED_MIN_NONZERO cells not 0 (blank = 0):
      1. same_block: equal 20-cell blocks of a year and geography of
         GEO_FOR_ALL; the first campus by 04's host order (not restored, main
         campus, larger FTE, larger campus-year total, lower UNITID) is the
         host, the others shadows. These blocks keep this role.
      2. whole_year: equal 60-cell campus-years; every other block of the
         campus-years after the first by the order is a shadow of it.
      3. whole_year_older_release / 4. block_older_release: a campus-year
         taken from an older release whose whole figures (3) or one block (4)
         equal, in that release, those of a campus whose figures for the year
         now come from a newer release: a shadow of the first such campus.
      5. renumbered: the two DOE IDs of one campus (the link rows of
         etl/reference/campus_id_changes.csv) with equal whole figures in a
         year both report (no nonzero minimum): the campus-year from the
         older release is a shadow of the other.
    A host whose own block is a shadow passes its shadows to its host.
    aggs/shared_blocks.parquet must hold exactly those shadows with those
    hosts and rules, and a host row for each host block in the facts. Then:
      - every entry of every rankings/*.json counts the school's facts
        without its shadow blocks, and the state and national files rank
        exactly the schools of their state(s) with such a count above 0;
      - every school file's sharedFigures lists exactly its shadow blocks,
        with the host's UNITID and the name of the host's school file.
    """
    result = AuditResult("Shared Statistics Counted Once")
    print("\nCHECK 8: Shared Statistics Counted Once")

    try:
        facts = pd.read_parquet(get_facts_path(), columns=["year", "unitid", "offense", "offense_family", "geo",
                                                           "count"])
        family_of = dict(zip(facts["offense"].tolist(), facts["offense_family"].tolist()))
        inst = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py", ["unitid", "state"])
        sources = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py")
        older = read_curated("dims/older_release_counts.parquet", "02_transform_to_parquet.py")
        enrollment = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py",
                                  ["unitid", "year", "fte"])
        shared = read_curated("aggs/shared_blocks.parquet", "04_create_aggregates.py")
        result.details["what_it_checks"] = (
            "Without 04's code, from data/curated/facts/incidents.parquet and "
            "dims/older_release_counts.parquet: the blocks (one campus, year and geography of On-campus, "
            "Non-campus, Public property; one cell per offense, blank = 0) counted under another campus of "
            f"the same ranked state, each test needing at least {SHARED_MIN_NONZERO} cells not 0, by 04's "
            "rules in order: equal blocks (same_block); equal whole campus-years, every block of the copy "
            "(whole_year); and, for a campus-year taken from an older release, whole figures or a block "
            "equal in that release to a campus whose figures now come from a newer release "
            "(whole_year_older_release, block_older_release); and the two DOE IDs of one campus (link rows of "
            "etl/reference/campus_id_changes.csv) with equal whole figures in a year both report, any number of "
            "nonzero cells: the older release's campus-year is a shadow (renumbered). Hosts are chosen by 04's order. "
            "aggs/shared_blocks.parquet must hold exactly those shadows, hosts and rules. Every "
            "rankings/*.json entry must count the school's facts without its shadow blocks (for \"criminal\" "
            "summed over the Criminal family, for \"all\" over every offense), the state and "
            "national files must rank exactly the schools with such a count, and each school file's "
            "sharedFigures must list exactly its shadow blocks and their host.")

        problems = []

        def problem(text):
            problems.append(text)

        state = {int(u): s for u, s in zip(inst["unitid"].tolist(), inst["state"].tolist())}
        cell_of = {o: i for i, o in enumerate(OFFENSE_ORDER)}
        unknown = sorted((set(facts["offense"]) | set(older["offense"])) - set(OFFENSE_ORDER))
        if unknown:
            raise RuntimeError(f"The facts hold offenses not in OFFENSE_ORDER ({', '.join(unknown)}). "
                               "Add them to OFFENSE_ORDER in config.py, then run 04 to 07 again.")

        def tally(frame, release_column):
            out = {}
            frame = frame[frame["geo"].isin(GEO_FOR_ALL)]
            releases = frame[release_column].tolist() if release_column else [None] * len(frame)
            for r, y, u, o, g, c in zip(releases, frame["year"].tolist(), frame["unitid"].tolist(),
                                        frame["offense"].tolist(), frame["geo"].tolist(), frame["count"].tolist()):
                key = (int(y), g, int(u)) if r is None else (r, int(y), g, int(u))
                out.setdefault(key, [0] * len(OFFENSE_ORDER))[cell_of[o]] += int(c)
            return {k: tuple(v) for k, v in out.items()}

        cells = tally(facts, None)  # (year, geo, unitid) -> 20 cells
        then = tally(older, "release")  # (release, year, geo, unitid) -> 20 cells
        blank = (0,) * len(OFFENSE_ORDER)
        campus_total = {}
        for (y, g, u), v in cells.items():
            campus_total[(u, y)] = campus_total.get((u, y), 0) + sum(v)

        def full_year(source, *key):
            return tuple(c for g in GEO_FOR_ALL for c in source.get((*key[:-1], g, key[-1]), blank))

        def enough(v):
            return sum(1 for c in v if c != 0) >= SHARED_MIN_NONZERO

        def in_ranked_state(u):
            return state.get(u) in US_STATES

        # 04's host order
        release = {(int(u), int(y)): str(r) for u, y, r in zip(sources["unitid"].tolist(), sources["year"].tolist(),
                                                               sources["release"].tolist())}
        restored = {(int(u), int(y)): bool(r) for u, y, r in zip(sources["unitid"].tolist(), sources["year"].tolist(),
                                                                  sources["restored"].tolist())}
        fte = {(int(u), int(y)): float(f) for u, y, f in zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(),
                                                             enrollment["fte"].tolist()) if pd.notna(f)}

        def host_order(u, y):
            if (u, y) not in restored:
                raise RuntimeError(f"campus_year_sources.parquet has no release for {u} in {y}, which has data. "
                                   "Run 02_transform_to_parquet.py and 03 to 07 again.")
            f = fte.get((u // 1000, y))
            return (restored[(u, y)], u % 1000 != 1, -f if f is not None else float("inf"),
                    -campus_total.get((u, y), 0), u)

        # A campus-year taken from an older release has the same counts there as in the facts
        restored_years = [(u, y, release[(u, y)]) for (u, y), r in restored.items() if r]
        for u, y, r in restored_years:
            for g in GEO_FOR_ALL:
                if then.get((r, y, g, u), blank) != cells.get((y, g, u), blank):
                    problem(f"older_release_counts.parquet: {u} {y} {g} differs from the facts, which come from "
                            f"the same release {r}")
                    break

        expected = {}  # (year, geo, unitid) -> (host, rule) of each shadow, before passing hosts on
        settled = set()  # blocks of same_block groups

        def shadow_all(y, u, host, rule):
            for g in GEO_FOR_ALL:
                key = (y, g, u)
                if key in cells and key not in settled and key not in expected:
                    expected[key] = (host, rule)

        # 1. same_block
        groups = {}
        for (y, g, u), v in cells.items():
            if enough(v) and in_ranked_state(u):
                groups.setdefault((y, g, state[u], v), []).append(u)
        for (y, g, _s, _v), us in groups.items():
            if len(us) > 1:
                host = min(us, key=lambda u: host_order(u, y))
                for u in us:
                    settled.add((y, g, u))
                    if u != host:
                        expected[(y, g, u)] = (host, "same_block")

        # 2. whole_year
        groups = {}
        for (y, u) in {(y, u) for (y, _g, u) in cells}:
            v = full_year(cells, y, u)
            if enough(v) and in_ranked_state(u):
                groups.setdefault((y, state[u], v), []).append(u)
        for (y, _s, _v), us in groups.items():
            if len(us) > 1:
                host = min(us, key=lambda u: host_order(u, y))
                for u in us:
                    if u != host:
                        shadow_all(y, u, host, "whole_year")

        # 3. and 4.: in the older release a campus-year is taken from, the
        # campuses whose figures for that year now come from a newer release
        newer_whole, newer_block = {}, {}
        for (r, y, g, u) in then:
            if not in_ranked_state(u) or (u, y) not in release or int(release[(u, y)]) <= int(r):
                continue
            newer_whole.setdefault((r, y, state[u], full_year(then, r, y, u)), set()).add(u)
            newer_block.setdefault((r, y, g, state[u], then[(r, y, g, u)]), set()).add(u)
        for u, y, r in restored_years:
            v = full_year(then, r, y, u)
            if in_ranked_state(u) and enough(v):
                copied = newer_whole.get((r, y, state[u], v), set())
                if copied:
                    shadow_all(y, u, min(copied, key=lambda m: host_order(m, y)), "whole_year_older_release")
        for u, y, r in restored_years:
            if not in_ranked_state(u):
                continue
            for g in GEO_FOR_ALL:
                key, v = (y, g, u), then.get((r, y, g, u), blank)
                if key in settled or key in expected or not enough(v):
                    continue
                copied = newer_block.get((r, y, g, state[u], v), set())
                if copied:
                    expected[key] = (min(copied, key=lambda m: host_order(m, y)), "block_older_release")

        # 5. renumbered: the two DOE IDs of one campus ("link" rows of
        # etl/reference/campus_id_changes.csv) with equal whole figures in a
        # year both report (at least one nonzero cell): the campus-year from
        # the older release is a shadow of the other
        id_links = campus_identity.read_id_changes()
        id_links = id_links[id_links["decision"] == "link"]
        years_with_cells = {}
        for (y, _g, u) in cells:
            years_with_cells.setdefault(u, set()).add(y)
        for o, n in zip(id_links["old_unitid"].astype(int), id_links["new_unitid"].astype(int)):
            for y in sorted(years_with_cells.get(o, set()) & years_with_cells.get(n, set())):
                v = full_year(cells, y, o)
                if (not (in_ranked_state(o) and in_ranked_state(n)) or state[o] != state[n]
                        or v != full_year(cells, y, n) or not any(v)):
                    continue
                ro, rn = int(release[(o, y)]), int(release[(n, y)])
                if ro != rn:
                    shadow_all(y, o if ro < rn else n, n if ro < rn else o, "renumbered")

        # Hosts passed on, and the host rows
        want_shadow = {}
        for (y, g, u), (host, rule) in expected.items():
            seen = {u}
            while (y, g, host) in expected and host not in seen:
                seen.add(host)
                host = expected[(y, g, host)][0]
            if (y, g, host) in expected:
                problem(f"campuses {sorted(seen)} are each other's shadows for {y} {g}")
            want_shadow[(y, g, u)] = (host, rule)
        want_host = {(y, g, h) for (y, g, _u), (h, _r) in want_shadow.items()}
        want_host |= {k for k in settled if k not in expected}
        want_host = {k for k in want_host if k in cells}

        # aggs/shared_blocks.parquet, against them
        actual_host = {}
        group_of = {}
        for y, g, grp, u, role, h, rule in zip(shared["year"].tolist(), shared["geo"].tolist(),
                                               shared["group"].tolist(), shared["unitid"].tolist(),
                                               shared["role"].tolist(), shared["host_unitid"].tolist(),
                                               shared["rule"].tolist()):
            key = (int(y), g, int(u))
            if key in actual_host:
                problem(f"shared_blocks.parquet lists {u} {y} {g} twice")
            actual_host[key] = (role, int(h), rule if isinstance(rule, str) else None)
            if group_of.setdefault((int(y), g, int(h)), int(grp)) != int(grp):
                problem(f"shared_blocks.parquet puts host {h}'s {y} {g} blocks in two groups")
        if len(set(group_of.values())) != len(group_of):
            problem("shared_blocks.parquet gives two hosts the same group")
        got_shadow = {k: (h, rule) for k, (role, h, rule) in actual_host.items() if role == "shadow"}
        got_host = {k for k, (role, h, _rule) in actual_host.items() if role == "host" and h == k[2]}
        odd = {k for k, (role, h, _rule) in actual_host.items() if role not in ("host", "shadow")
               or (role == "host" and h != k[2])}
        if odd:
            problem(f"{len(odd)} rows of shared_blocks.parquet are neither a shadow nor a host of itself "
                    f"(first: {sorted(odd)[0]})")
        for name, want, got in (("shadow", set(want_shadow), set(got_shadow)), ("host", want_host, got_host)):
            if want - got:
                problem(f"{len(want - got)} {name} blocks are not in shared_blocks.parquet "
                        f"(first: {sorted(want - got)[0]})")
            if got - want:
                problem(f"{len(got - want)} {name} blocks in shared_blocks.parquet should not be there "
                        f"(first: {sorted(got - want)[0]})")
        wrong = sorted(k for k in set(want_shadow) & set(got_shadow) if want_shadow[k] != got_shadow[k])
        if wrong:
            problem(f"{len(wrong)} shadow blocks have another host or rule than expected (first: {wrong[0]}: "
                    f"{got_shadow[wrong[0]]}, expected {want_shadow[wrong[0]]})")
        shadows = set(got_shadow)
        groups_found = set(group_of)
        by_rule = {}
        for k, (_h, rule) in got_shadow.items():
            rule = rule or "(no rule)"  # such a row is already a problem above
            n, c = by_rule.get(rule, (0, 0))
            by_rule[rule] = (n + 1, c + sum(cells.get(k, blank)))

        # What totals and rankings count: the facts without the shadow blocks,
        # per offense and summed for the summary codes ("criminal": the
        # Criminal family; "all": every offense)
        counted = {}
        for (y, g, u), v in cells.items():
            if (y, g, u) in shadows:
                continue
            for o, c in zip(OFFENSE_ORDER, v):
                if c:
                    summaries = ("all", "criminal") if family_of.get(o) == "Criminal" else ("all",)
                    for key in (o,) + summaries:
                        counted[(y, u, key)] = counted.get((y, u, key), 0) + c
        code_of = {o: o.lower().replace(" ", "_") for o in OFFENSE_ORDER}
        code_of["all"] = "all"
        code_of["criminal"] = "criminal"
        ranked = {}  # (year, code) -> {unitid: count}, the schools a ranking of that offense must hold
        for (y, u, o), c in counted.items():
            ranked.setdefault((y, code_of[o]), {})[u] = c

        entries_checked = 0
        ranking_files = sorted((JSON_DIR / "rankings").glob("*.json"))
        by_year = {}
        for ranking_file in ranking_files:
            data = json.loads(ranking_file.read_text(encoding="utf-8"))
            preset, year = data.get("preset"), data.get("year")
            if preset == "national":
                in_scope = set(US_STATES)
            elif preset in US_STATES:
                in_scope = {preset}
            else:
                in_scope = None  # Ivy League: counts only
            rankings = data.get("rankings", {})
            codes = set(rankings)
            if in_scope is not None:
                codes |= {code for (y, code) in ranked if y == year}
            for code in sorted(codes):
                entries = rankings.get(code, [])
                want = ranked.get((year, code), {})
                for e in entries:
                    entries_checked += 1
                    if e.get("count") != want.get(e.get("unitid"), 0):
                        problem(f"{ranking_file.name}/{code}: {e.get('unitid')} counts {e.get('count')}, "
                                f"the facts without shadow blocks {want.get(e.get('unitid'), 0)}")
                if in_scope is not None:
                    should = {u for u in want if state.get(u) in in_scope}
                    have = {e.get("unitid") for e in entries}
                    if have != should:
                        diff = sorted(should ^ have, key=str)  # an entry without a unitid sorts too
                        problem(f"{ranking_file.name}/{code}: ranks {len(have)} schools, expected {len(should)} "
                                f"(first difference: {diff[0]})")
            if preset == "national":
                by_year[year] = sum(e.get("count", 0) for e in rankings.get("all", []))

        # Per year: DOE figures of the ranked schools, the shadow counts taken out, what the rankings count
        all_cells = {}
        for (y, g, u), v in cells.items():
            if state.get(u) in US_STATES:
                all_cells[y] = all_cells.get(y, 0) + sum(v)
        shadow_counts = {}
        for (y, g, u) in shadows:
            shadow_counts[y] = shadow_counts.get(y, 0) + sum(cells[(y, g, u)])
        rows_by_year = []
        for year in sorted(by_year):
            doe, out = all_cells.get(year, 0), shadow_counts.get(year, 0)
            ranked_total = by_year[year]
            rows_by_year.append({"year": year, "doe_figures": doe, "shadow_counts": out,
                                 "national_total": ranked_total,
                                 "groups": sum(1 for k in groups_found if k[0] == year),
                                 "shadow_blocks": sum(1 for k in shadows if k[0] == year)})
            if doe - out != ranked_total:
                problem(f"national-{year}-all.json totals {ranked_total:,}; the ranked schools' facts are "
                        f"{doe:,}, less {out:,} in shadow blocks = {doe - out:,}")

        # School files' sharedFigures
        geo_rank = {g: i for i, g in enumerate(GEO_FOR_ALL)}
        notes_expected = {}
        for (y, g, u) in sorted(shadows, key=lambda k: (k[2], k[0], geo_rank[k[1]])):
            notes_expected.setdefault(u, []).append((y, g, actual_host[(y, g, u)][1]))
        names = {}
        notes_found = {}
        for school_file in (JSON_DIR / "schools").glob("*.json"):
            try:
                unitid = int(school_file.stem)
            except ValueError:
                continue
            school = json.loads(school_file.read_text(encoding="utf-8"))
            names[unitid] = school.get("name")
            if "sharedFigures" in school:
                notes_found[unitid] = school["sharedFigures"]
        for unitid in sorted(set(notes_expected) | set(notes_found)):
            found = notes_found.get(unitid) or []
            want = notes_expected.get(unitid, [])
            got = [(f.get("year"), f.get("geo"), f.get("hostUnitid")) for f in found]
            if got != want:
                problem(f"schools/{unitid}.json sharedFigures {got[:3]}, expected {want[:3]}")
            for f in found:
                if f.get("hostName") != names.get(f.get("hostUnitid")):
                    problem(f"schools/{unitid}.json names host {f.get('hostUnitid')} {f.get('hostName')!r}, "
                            f"its school file says {names.get(f.get('hostUnitid'))!r}")

        result.details["min_nonzero_cells"] = SHARED_MIN_NONZERO
        result.details["host_groups"] = len(groups_found)
        result.details["shadow_blocks"] = len(shadows)
        result.details["shadow_counts"] = sum(shadow_counts.values())
        result.details["by_rule"] = {rule: {"shadow_blocks": n, "counts": c} for rule, (n, c) in sorted(by_rule.items())}
        result.details["by_year"] = rows_by_year
        result.details["ranking_entries_checked"] = entries_checked
        result.details["schools_with_shared_figures"] = len(notes_found)
        result.details["problems"] = len(problems)

        print(f"  Hosts' groups: {len(groups_found):,}; shadow blocks: {len(shadows):,} "
              f"({sum(shadow_counts.values()):,} counts, each counted once under its host)")
        for rule, (n, c) in sorted(by_rule.items()):
            print(f"    by rule {rule}: {n:,} shadow blocks, {c:,} counts")
        print(f"    {'Year':<6}{'Groups':>8}{'Shadows':>9}{'DOE figures':>13}{'Shadow':>9}{'National':>11}")
        for r in rows_by_year:
            print(f"    {r['year']:<6}{r['groups']:>8,}{r['shadow_blocks']:>9,}{r['doe_figures']:>13,}"
                  f"{r['shadow_counts']:>9,}{r['national_total']:>11,}")
        print(f"  Ranking entries checked: {entries_checked:,}; school files with sharedFigures: "
              f"{len(notes_found):,}")
        print(f"  Problems: {len(problems)}")

        if problems:
            result.failed(f"{len(problems)} problems with shared statistics (first: {problems[0]}). "
                          f"Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for p in problems[:5]:
                    print(f"    {p}")
        elif not ranking_files:
            result.failed(f"No ranking files in {JSON_DIR / 'rankings'} to check. Run 04_create_aggregates.py "
                          f"and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_campus_identity(verbose: bool = False) -> AuditResult:
    """
    CHECK 11: Campus names, search and the campuses DOE renumbered.

    The ID-change candidates are found again from the curated DOE names
    (campus_identity.candidates_from_curated) and must be exactly the rows
    of etl/reference/campus_id_changes.csv, with the same evidence. Every
    row is reviewed (link or reject). A link pair's IDs never appear in the
    same DOE release, one follows the other, and they share an address or a
    campus name. Each linked school file names the other ID with that ID's
    reported years (and no other school file has idChanges); each keeps only
    its own years (no figures move). Every school file is in the search
    index, with the campus name of dim_institution for a campus that is not
    a main campus.
    """
    print("\n" + "=" * 60)
    print("CHECK 11: Campus Identity")
    print("=" * 60)
    result = AuditResult("Campus Identity")
    result.details["what_it_checks"] = (
        "etl/reference/campus_id_changes.csv equals the campus ID-change candidates found again in "
        "data/curated/dims/campus_names.parquet (every DOE release's INSTNM, BRANCH, address and city per "
        "UNITID_P), campus_year_sources and the facts, evidence included; every row is reviewed (link or "
        "reject); each link pair is never listed in the same release, one ID is listed in the release after "
        "the other's, and they share an address or a campus name; both school files link to each other with "
        "the other ID's reported years and keep only their own years (no figures moved, no rankings changed); "
        "no other school file has idChanges; every school file is in school-index.json, titled by its DOE "
        "campus name (dim_institution campus_name) when it is not a main campus.")
    try:
        reviewed = campus_identity.read_id_changes()
    except (OSError, ValueError) as e:
        result.failed(f"Cannot read {campus_identity.ID_CHANGES_PATH.name}: {e}")
        return result
    found = campus_identity.candidates_from_curated(CURATED_DIR, DATA_YEARS, GEO_FOR_ALL)
    diff = campus_identity.compare_with_review(found, campus_identity.evidence_text(reviewed))
    for kind, pairs in diff.items():
        if pairs:
            result.failed(f"{len(pairs)} candidate pairs are {kind} compared with the CSV (first {pairs[:3]}); "
                          "run campus_identity.py and review them")
    unreviewed = reviewed[~reviewed["decision"].isin(["link", "reject"]) | reviewed["reason"].str.startswith("proposed:")]
    if len(unreviewed):
        result.failed(f"{len(unreviewed)} rows are not reviewed")
    links = reviewed[reviewed["decision"] == "link"]
    for r in links.to_dict("records"):
        pair = f"{r['old_unitid']}-{r['new_unitid']}"
        if set(r["old_releases"].split()) & set(r["new_releases"].split()):
            result.failed(f"{pair}: both IDs are listed in one release")
        if not r["transitions"]:
            result.failed(f"{pair}: neither ID is listed in the release after the other's")
        if r["address_match"] != "yes" and r["campus_name_match"] != "yes":
            result.failed(f"{pair}: linked without the same address or campus name")
    for col, rel in (("old_unitid", "later"), ("new_unitid", "earlier")):
        twice = links[col].value_counts()
        if (twice > 1).any():
            result.failed(f"{int((twice > 1).sum())} IDs have more than one {rel} link (first {twice[twice > 1].index[0]})")

    reported = {u: sorted(ys) for u, ys in reported_years().items()}
    expected = {}
    for r in links.to_dict("records"):
        o, n = int(r["old_unitid"]), int(r["new_unitid"])
        expected.setdefault(o, {})[n] = ("later", reported.get(n, []))
        expected.setdefault(n, {})[o] = ("earlier", reported.get(o, []))
    dim = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py",
                       ["unitid", "is_main_campus", "campus_name"])
    campus = {int(u): (None if m else (c if isinstance(c, str) else None))
              for u, m, c in zip(dim["unitid"], dim["is_main_campus"], dim["campus_name"])}
    index_path = JSON_DIR / "school-index.json"
    index = {int(s["unitid"]): s for s in json.loads(index_path.read_text(encoding="utf-8"))["schools"]}
    files = sorted((JSON_DIR / "schools").glob("*.json"))
    linked_pages = titled = missing_from_index = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        u = int(data["unitid"])
        got = {int(c["unitid"]): (c["relation"], c["years"]) for c in data.get("idChanges", [])}
        want = expected.get(u, {})
        if got != want:
            result.failed(f"{path.name}: idChanges {got} differ from the CSV links {want}")
        if got:
            linked_pages += 1
        own = [int(y["year"]) for y in data["yearlyTotals"]]
        if own != reported.get(u, []):
            result.failed(f"{path.name}: its years {own} are not the years DOE reported under {u}")
        if data.get("campus") != campus.get(u):
            result.failed(f"{path.name}: campus {data.get('campus')!r}, dim_institution has {campus.get(u)!r}")
        titled += data.get("campus") is not None
        entry = index.get(u)
        if entry is None:
            missing_from_index += 1
            result.failed(f"{path.name} is not in school-index.json")
        elif entry.get("campus") != data.get("campus") or sorted(entry.get("idChanges", [])) != sorted(got):
            result.failed(f"school-index.json entry {u} has another campus name or idChanges than {path.name}")
    if len(index) != len(files):
        result.failed(f"school-index.json lists {len(index)} schools, the site has {len(files)} school files")

    # Not changed by the links: years both IDs report, when neither is a shadow of the other
    shared = read_curated("aggs/shared_blocks.parquet", "04_create_aggregates.py", ["unitid", "year", "role"])
    shadow = set(zip(shared.loc[shared["role"] == "shadow", "unitid"].astype(int),
                     shared.loc[shared["role"] == "shadow", "year"].astype(int)))
    both_counted = []
    for r in links.to_dict("records"):
        for part in r["overlap_totals"].split():
            y, counts = part.split(":")
            a, b = (int(x) for x in counts.split("/"))
            o, n = int(r["old_unitid"]), int(r["new_unitid"])
            if a and b and (o, int(y)) not in shadow and (n, int(y)) not in shadow:
                both_counted.append(f"{o}/{n} {y} ({a}/{b})")
    # (a) Mergers: link pairs whose IDs belong to different institutions (base
    # UNITIDs). Each year both report must be out of rate rankings (check 10
    # holds the school files to it); a year both count with differing figures
    # is listed, since its incidents are in two institutions' totals.
    cross = links[links["old_unitid"].astype(int) // 1000 != links["new_unitid"].astype(int) // 1000]
    excluded_years = set()
    for r in cross.to_dict("records"):
        o, n = int(r["old_unitid"]), int(r["new_unitid"])
        for y in set(reported.get(o, [])) & set(reported.get(n, [])):
            excluded_years |= {(y, o // 1000), (y, n // 1000)}
    cross_keys = {(int(o), int(n)) for o, n in zip(cross["old_unitid"], cross["new_unitid"])}
    both_counted_cross = [s for s in both_counted if tuple(int(x) for x in s.split()[0].split("/")) in cross_keys]

    # (b) Identical whole-year figures (every geography) of two campuses in
    # one city, from different releases, neither a shadow: those a link
    # explains are counted once (rule "renumbered"); the rest are listed only.
    facts = pd.read_parquet(get_facts_path(), columns=["year", "unitid", "offense", "geo", "count"])
    facts = facts[facts["count"] > 0]
    vec = (facts.sort_values(["offense", "geo"])
           .assign(cell=lambda f: f["offense"] + "|" + f["geo"] + "|" + f["count"].astype(str))
           .groupby(["unitid", "year"])["cell"].agg(";".join))
    src = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py", ["unitid", "year", "release"])
    release = {(int(u), int(y)): r for u, y, r in zip(src["unitid"], src["year"], src["release"])}
    place = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py", ["unitid", "state", "city"])
    city = {int(u): (s, str(c).strip().lower()) for u, s, c in zip(place["unitid"], place["state"], place["city"])}
    linked_any = {frozenset((int(o), int(n))) for o, n in zip(links["old_unitid"], links["new_unitid"])}
    groups = {}
    for (u, y), v in vec.items():
        u, y = int(u), int(y)
        if (u, y) in shadow or u not in city:
            continue
        groups.setdefault((y, city[u], v), []).append(u)
    unlinked_groups = unlinked_incidents = 0
    unlinked_examples = []
    for (y, _c, v), us in groups.items():
        if len(us) < 2 or len({release.get((u, y)) for u in us}) < 2:
            continue
        if any(frozenset(p) in linked_any for p in itertools.combinations(us, 2)):
            result.failed(f"{y}: linked campuses {us} have identical figures but are both counted")
            continue
        unlinked_groups += 1
        dup = sum(int(c.rsplit("|", 1)[1]) for c in v.split(";")) * (len(us) - 1)
        unlinked_incidents += dup
        if len(unlinked_examples) < 20:
            unlinked_examples.append(f"{y} {'/'.join(map(str, sorted(us)))} ({dup})")

    result.details.update({
        "merger_link_pairs": len(cross),
        "merger_institution_years_both_ids_report": len(excluded_years),
        "merger_years_counted_under_both_institutions": len(both_counted_cross),
        "merger_years_counted_under_both_institutions_list": "; ".join(both_counted_cross),
        "identical_city_year_groups_without_link": unlinked_groups,
        "identical_city_year_incidents_without_link": unlinked_incidents,
        "identical_city_year_groups_without_link_note": (
            "Campus-years of one city with identical figures in every geography, from different DOE releases, "
            "where no reviewed link ties the IDs: left counted under each ID (no evidence they are one campus). "
            "First 20: " + "; ".join(unlinked_examples)),
    })
    print(f"  Links between different base UNITIDs (mergers, renumberings): {len(cross)}; institution-years where both IDs report (no rate, check 10): {len(excluded_years)}; "
          f"merger years still counted under both: {len(both_counted_cross)}")
    print(f"  Identical same-city figures without a link (left alone): {unlinked_groups} groups, "
          f"{unlinked_incidents:,} incidents")
    result.details.update({
        "candidate_pairs": len(reviewed),
        "linked_pairs": len(links),
        "rejected_pairs": int((reviewed["decision"] == "reject").sum()),
        "merged_pairs": 0,
        "school_files_with_id_links": linked_pages,
        "school_files_titled_by_campus_name": titled,
        "school_files_missing_from_search_index": missing_from_index,
        "linked_years_counted_under_both_ids": len(both_counted),
        "linked_years_counted_under_both_ids_note": (
            "Years both IDs of a linked pair report with incidents, where neither is counted under the other "
            "(shared_blocks): the links do not change how they count. First 20: " + "; ".join(both_counted[:20])),
    })
    print(f"  Candidate pairs: {len(reviewed)} ({len(links)} linked, {len(reviewed) - len(links)} rejected); "
          f"school files with ID links: {linked_pages}; titled by campus name: {titled:,}")
    print(f"  Linked years counted under both IDs (unchanged by this check): {len(both_counted)}")
    result.passed()
    return result


def generate_per_school_report(verbose: bool = False) -> pd.DataFrame:
    """
    Generate detailed per-school audit report.
    Returns DataFrame with validation results for each school file:
      incident_match: yearlyTotals equal the aggregates' geo "All" totals in
        every year of either (as check 2).
      fte_match: fteByYear, the FTE the school page's rates use, and fte (its
        newest year) equal dim_enrollment's FTE for the school's base UNITID
        in each year it reported (campus_year_sources, zeros included).
      years_with_data / years_with_fte: the years in yearlyTotals, and how
        many of them have an FTE above 0 in dim_enrollment.
      status: FAIL if a match fails; WARNING if fewer than 80% of its years
        have an FTE; otherwise PASS.
    """
    print("\nGenerating per-school audit report...")

    schools_dir = JSON_DIR / "schools"
    json_files = list(schools_dir.glob("*.json"))

    # Load aggregates for comparison: geo "All" totals, and the years each school has data
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    agg = pd.read_parquet(agg_path, columns=["year", "unitid", "geo", "count"])
    agg_totals = {}  # unitid -> {year: total}
    for (uid, year), total in agg[agg["geo"] == "All"].groupby(["unitid", "year"])["count"].sum().items():
        agg_totals.setdefault(int(uid), {})[int(year)] = int(total)
    agg_years = reported_years()  # unitid -> the years it reported (DATA_YEARS only)

    # Load enrollment for FTE check: (base unitid, year) -> FTE
    enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    enrollment = {}
    if enrollment_path.exists():
        dim = pd.read_parquet(enrollment_path, columns=["unitid", "year", "fte"]).dropna(subset=["fte"])
        for uid, year, fte in zip(dim["unitid"].tolist(), dim["year"].tolist(), dim["fte"].tolist()):
            enrollment[(int(uid), int(year))] = float(fte)

    results = []

    for i, json_file in enumerate(json_files):
        if i % 1000 == 0 and i > 0:
            print(f"  Processed {i:,} / {len(json_files):,} schools...")

        try:
            unitid = int(json_file.stem)
        except ValueError:
            continue

        with open(json_file) as f:
            school_data = json.load(f)

        # Get school info
        name = school_data.get("name", "Unknown")
        yearly_totals = {int(yt["year"]): yt["total"] for yt in school_data.get("yearlyTotals", [])}
        years_in_data = len(yearly_totals)

        # Check incident totals, every year in either
        school_agg = agg_totals.get(unitid, {})
        incident_match = all(
            yearly_totals.get(year, 0) == school_agg.get(year, 0)
            for year in set(school_agg) | set(yearly_totals)
        )

        # Check the FTE the page's rates use (base unitid for the enrollment match)
        base_unitid = unitid // 1000
        expected_fte = {year: enrollment[(base_unitid, year)] for year in agg_years.get(unitid, ())
                        if (base_unitid, year) in enrollment}
        stored_fte = {int(year): float(fte) for year, fte in (school_data.get("fteByYear") or {}).items()
                      if fte is not None}
        stored_latest = None if school_data.get("fte") is None else float(school_data["fte"])
        expected_latest = expected_fte[max(expected_fte)] if expected_fte else None
        fte_match = stored_fte == expected_fte and stored_latest == expected_latest
        years_with_fte = sum(1 for year in yearly_totals if enrollment.get((base_unitid, year), 0) > 0)

        # Determine overall status
        if incident_match and fte_match and years_with_fte >= years_in_data * 0.8:
            status = "PASS"
        elif incident_match and fte_match:
            status = "WARNING"
        else:
            status = "FAIL"

        results.append({
            "unitid": unitid,
            "name": name,
            "json_exists": True,
            "years_with_data": years_in_data,
            "years_with_fte": years_with_fte,
            "incident_match": incident_match,
            "fte_match": fte_match,
            "status": status
        })

    df = pd.DataFrame(results, columns=["unitid", "name", "json_exists", "years_with_data", "years_with_fte",
                                        "incident_match", "fte_match", "status"])
    print(f"  Generated report for {len(df):,} schools")
    failed = df[df["status"] == "FAIL"]
    if len(failed):
        print(f"  {len(failed):,} schools FAIL (first: {int(failed['unitid'].iloc[0])}; see the CSV report). "
              f"Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")

    return df


def audit_enrollment_sources(verbose: bool = False) -> AuditResult:
    """
    CHECK 9: The FTE and the share of exclusively online students
    (pctdeexc) in dims/dim_enrollment.parquet are NCES's own: for 2015-2020
    those in etl/reference/ipeds_official_fte.csv (read from NCES's final
    Access databases), from 2021 on those in the DRVEF CSV the pipeline reads
    for the year. Every institution-year there with an FTE must be in the
    table with the same FTE and pctdeexc, and the table must hold nothing
    else. The formula that estimated 2015-2020 FTE before is not used.
    """
    result = AuditResult("Enrollment Matches NCES")
    print("\nCHECK 9: Enrollment Matches NCES")
    try:
        import ipeds_files
        enrollment = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py",
                                  ["unitid", "year", "fte", "pctdeexc"])
        reference = provenance.REFERENCE_DIR / "ipeds_official_fte.csv"
        if not reference.is_file():
            raise RuntimeError(f"{reference} not found. Restore it with git (or run "
                               "01c_extract_ipeds_official.ps1 on Windows), then 02b, 02a and 04 to 07 again.")
        nces = {}  # (unitid, year) -> (fte, pctdeexc); FTE blank = no row
        ref = pd.read_csv(reference, dtype=str, keep_default_na=False)
        for y, u, f, p in zip(ref["year"], ref["unitid"], ref["fte"], ref["pctdeexc"]):
            if f.strip():
                nces[(int(u), int(y))] = (int(f), int(p) if p.strip() else None)
        sources = {"2015-2020": reference.name}
        for year in sorted(set(int(y) for y in enrollment["year"].unique()) | set(DATA_YEARS)):
            if year <= 2020:
                continue
            path = ipeds_files.pipeline_csv(year, f"drvef{year}")
            if path is None:
                if (enrollment["year"] == year).any():
                    result.failed(f"{year}: dim_enrollment.parquet has FTE, but there is no DRVEF{year} CSV. "
                                  "Run 01b_download_ipeds.py, then 02a and 04 to 07 again.")
                continue
            sources[str(year)] = path.name
            csv = pd.read_csv(path, usecols=["UNITID", "FTE", "PCTDEEXC"])
            for u, f, p in zip(csv["UNITID"], csv["FTE"], csv["PCTDEEXC"]):
                if pd.notna(f):
                    nces[(int(u), year)] = (int(f), int(p) if pd.notna(p) else None)
        ours = {(int(u), int(y)): (int(f), int(p) if pd.notna(p) else None)
                for u, y, f, p in zip(enrollment["unitid"], enrollment["year"], enrollment["fte"],
                                      enrollment["pctdeexc"])}
        years = sorted({y for _, y in ours} | {y for _, y in nces if y in {y2 for _, y2 in ours}})
        rows = []
        for year in years:
            want = {k: v for k, v in nces.items() if k[1] == year}
            have = {k: v for k, v in ours.items() if k[1] == year}
            missing, extra = sorted(set(want) - set(have)), sorted(set(have) - set(want))
            differ = sorted(k for k in set(want) & set(have) if want[k] != have[k])
            rows.append({"year": year, "institutions": len(have), "missing": len(missing), "extra": len(extra),
                         "differ": len(differ)})
            print(f"  {year}: {len(have):,} institutions; missing {len(missing)}, extra {len(extra)}, "
                  f"different FTE or pctdeexc {len(differ)}")
            for what, keys in (("are missing from", missing), ("should not be in", extra)):
                if keys:
                    result.failed(f"{year}: {len(keys)} institutions with an FTE {what} dim_enrollment.parquet "
                                  f"(first: {keys[0][0]}). Run 02b and 02a, then 04 to 07 again.")
            if differ:
                k = differ[0]
                result.failed(f"{year}: {len(differ)} institutions have another FTE or pctdeexc than NCES's "
                              f"(first: {k[0]}: {have[k]}, NCES {want[k]}). Run 02b and 02a, then 04 to 07 again.")
        result.details["what_it_checks"] = (
            "dims/dim_enrollment.parquet against NCES's own figures, re-read: 2015-2020 from "
            "etl/reference/ipeds_official_fte.csv (DRVEF tables of NCES's final Access databases), 2021 on "
            "from the DRVEF CSV the pipeline reads. Every institution-year with an FTE must be there with the "
            "same FTE and percent of exclusively online students (pctdeexc), and nothing else.")
        result.details["sources"] = sources
        result.details["by_year"] = rows
        if not rows:
            result.failed("dim_enrollment.parquet has no rows. Run 02b and 02a.")
        result.passed()
        print(f"  {result.status}")
    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")
    return result


def expected_institutions() -> tuple[dict, dict]:
    """
    Without 04's or 05's code, the institution-years rates are calculated for
    (config.py, "SUMMARY CODES AND RATES"), from the fact table, the shadow
    blocks of aggs/shared_blocks.parquet (check 8 finds them again), the
    reported campus-years, dim_institution and dim_enrollment:

    returns ({(year, base): {name, link, state, campuses, fte, online, online_year}},
             {(year, base, code): count above 0},
             {(year, unitid): {name, state}} of every counting campus-year).

    A campus-year counts (in rankings, with 0 when it had no incident, and
    for its institution, the base UNITID) when the campus reported that year
    and its figures are not all shadow blocks; the institution's counts are
    all such campuses' counts in GEO_FOR_ALL without shadow blocks, in any
    state. An institution-year is listed when one of its campuses counts,
    incidents or not. Its link campus is the main campus (UNITID ending in
    001) when that counts that year and has a school file, otherwise the
    counting campus with a school file and the most incidents (ties: lowest
    UNITID).
    """
    facts = pd.read_parquet(get_facts_path(), columns=["year", "unitid", "offense", "offense_family", "geo", "count"])
    facts = facts[facts["geo"].isin(GEO_FOR_ALL)]
    shared = read_curated("aggs/shared_blocks.parquet", "04_create_aggregates.py")
    sources = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py", ["unitid", "year"])
    inst = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py", ["unitid", "institution_name", "state"])
    enrollment = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py",
                              ["unitid", "year", "fte", "pctdeexc"])

    shadows = {(int(y), g, int(u)) for y, g, u, role in zip(shared["year"].tolist(), shared["geo"].tolist(),
                                                            shared["unitid"].tolist(), shared["role"].tolist())
               if role == "shadow"}
    summaries = {code: family for code, family in SUMMARY_FAMILIES.items()}
    counts = {}  # (year, base, code) -> count
    campus_total = {}  # (unitid, year) -> count without shadow blocks
    for y, u, o, fam, g, c in zip(facts["year"].tolist(), facts["unitid"].tolist(), facts["offense"].tolist(),
                                  facts["offense_family"].tolist(), facts["geo"].tolist(), facts["count"].tolist()):
        y, u, c = int(y), int(u), int(c)
        if (y, g, u) in shadows or c == 0:
            continue
        campus_total[(u, y)] = campus_total.get((u, y), 0) + c
        codes = [o.lower().replace(" ", "_")] + [code for code, f in summaries.items() if f is None or f == fam]
        for code in codes:
            key = (y, u // 1000, code)
            counts[key] = counts.get(key, 0) + c

    shadowed = {(u, y) for (y, _g, u) in shadows}
    counting = [(int(u), int(y)) for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist())
                if (int(u), int(y)) not in shadowed or (int(u), int(y)) in campus_total]
    name = dict(zip(inst["unitid"].astype(int).tolist(), inst["institution_name"].tolist()))
    state = dict(zip(inst["unitid"].astype(int).tolist(), inst["state"].tolist()))
    fte = {(int(u), int(y)): (None if pd.isna(f) else int(f), None if pd.isna(p) else int(p))
           for u, y, f, p in zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(),
                                 enrollment["fte"].tolist(), enrollment["pctdeexc"].tolist())}

    # Institution-years left out of rate rankings: a campus DOE reported under
    # this and another institution that year (the link rows of
    # etl/reference/campus_id_changes.csv whose IDs have different base UNITIDs)
    reported_by = {}
    for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist()):
        reported_by.setdefault(int(u), set()).add(int(y))
    id_links = campus_identity.read_id_changes()
    id_links = id_links[id_links["decision"] == "link"]
    rate_excluded = set()
    for o, n in zip(id_links["old_unitid"].astype(int), id_links["new_unitid"].astype(int)):
        if o // 1000 != n // 1000:
            for y in reported_by.get(o, set()) & reported_by.get(n, set()):
                rate_excluded |= {(y, o // 1000), (y, n // 1000)}

    by_inst = {}
    for u, y in counting:
        by_inst.setdefault((y, u // 1000), []).append(u)
    institutions = {}
    for (y, b), campuses in by_inst.items():
        with_file = [u for u in campuses if u in name]
        if not with_file:
            raise RuntimeError(f"Institution {b} has campuses that count in {y} but none in dim_institution")
        main = b * 1000 + 1
        link = main if main in with_file else min(with_file, key=lambda u: (-campus_total.get((u, y), 0), u))
        f, online = fte.get((b, y), (None, None))
        # The online share the rules use: in an ONLINE_SHARE_YEAR year, that
        # other fall's share when NCES has one, else the year's own
        online_year = y if online is not None else None
        if y in ONLINE_SHARE_YEAR:
            src_online = fte.get((b, ONLINE_SHARE_YEAR[y]), (None, None))[1]
            if src_online is not None:
                online, online_year = src_online, ONLINE_SHARE_YEAR[y]
        s = state.get(link)
        institutions[(y, b)] = {"name": name[link], "link": link, "state": None if pd.isna(s) else s,
                                "campuses": len(campuses), "fte": f, "online": online,
                                "online_year": online_year, "rate_excluded": (y, b) in rate_excluded}
    # And every institution of a merger family (bases joined by those links)
    # in a year its campuses count under two or more institutions and one of
    # them has no IPEDS FTE
    family_of = {}
    for o, n in zip(id_links["old_unitid"].astype(int), id_links["new_unitid"].astype(int)):
        if o // 1000 != n // 1000:
            merged = family_of.get(o // 1000, {o // 1000}) | family_of.get(n // 1000, {n // 1000})
            for b in merged:
                family_of[b] = merged
    family_years = {}
    for (y, b), rec in institutions.items():
        if b in family_of:
            family_years.setdefault((y, min(family_of[b])), []).append(b)
    for (y, _f), bases in family_years.items():
        if len(bases) >= 2 and any(institutions[(y, b)]["fte"] is None for b in bases):
            for b in bases:
                institutions[(y, b)]["rate_excluded"] = True
    campus_years = {}
    for u, y in counting:
        if u not in name:
            raise RuntimeError(f"Campus {u} reported {y} but is not in dim_institution")
        s = state.get(u)
        campus_years[(y, u)] = {"name": name[u], "state": None if pd.isna(s) else s}
    return institutions, counts, campus_years


def rate_ranked(rec: dict) -> bool:
    """Whether an institution-year is in rate rankings (config.py)."""
    return (rec["fte"] is not None and rec["fte"] >= MIN_FTE_FOR_RATE
            and (rec["online"] is None or rec["online"] < ONLINE_EXCLUSION_PCT)
            and not rec.get("rate_excluded"))


def audit_institution_rates(verbose: bool = False) -> AuditResult:
    """
    CHECK 10: Rates are institution rates, and rate rankings list exactly
    the institutions config.py allows.

    From expected_institutions (computed without 04's or 05's code), every
    rankings/*.json file must list in "institutions" exactly the
    institution-years of its preset (national: state in US_STATES; a state:
    the link campus's state; Ivy League: the Ivy institutions) that have at
    least MIN_FTE_FOR_RATE FTE and fewer than ONLINE_EXCLUSION_PCT percent
    exclusively online students (or no such figure), with their link campus,
    name, state, FTE and number of campuses; and per code, "rateRankings"
    exactly those with a count above 0, with that count and rate = count /
    FTE x 10,000 to 2 decimals (within 0.005). Every school file's
    "institution" years must hold the same campuses, online share,
    rateRanked and counts (counts left out only when they equal the school's
    own counts).
    """
    result = AuditResult("Institution Rates")
    print("\nCHECK 10: Institution Rates")

    try:
        result.details["what_it_checks"] = (
            "Without 04's or 05's code, from the facts without shadow blocks, the reported campus-years, "
            "dim_institution and dim_enrollment: the campus-years that count (reported, not all shadow blocks; "
            "incidents or not), the institutions (base UNITIDs) each year with such a campus, counts over all "
            "those campuses (residence halls and shadow blocks left out), link campus (the 001 campus, else the "
            "campus with the most incidents), FTE and share of exclusively online students (in "
            f"{', '.join(str(y) for y in sorted(ONLINE_SHARE_YEAR))}, the share of the fall config.py "
            "ONLINE_SHARE_YEAR names when NCES has one, else the year's own). Every "
            "rankings/*.json file must list in campuses exactly its preset's counting campus-years, with their "
            "name, state, institution FTE and number of campuses (the site ranks those without an entry with 0); "
            f"in institutions exactly its preset's institutions with at least {MIN_FTE_FOR_RATE:,} FTE and under "
            f"{ONLINE_EXCLUSION_PCT}% exclusively online students (or no such figure); and in rateRankings per "
            "code exactly those with a count above 0, each with that count and rate = count / FTE x 10,000 "
            "(within 0.005). Every school file's institution years must match too.")
        institutions, counts, campus_years = expected_institutions()
        problems = []

        def problem(text):
            problems.append(text)

        codes = sorted({code for (_y, _b, code) in counts})
        files_checked = entries_checked = zero_campus_rows = 0
        for ranking_file in sorted((JSON_DIR / "rankings").glob("*.json")):
            data = json.loads(ranking_file.read_text(encoding="utf-8"))
            preset, year = data.get("preset"), data.get("year")
            files_checked += 1

            def in_preset(b, rec):
                if preset == "national":
                    return rec["state"] in US_STATES
                if preset == "ivy":
                    return b in IVY_BASE_UNITIDS
                return rec["state"] == preset

            # The campuses table: every campus-year of the preset that counts, incidents or not
            def campus_in_preset(u, rec):
                if preset == "national":
                    return rec["state"] in US_STATES
                if preset == "ivy":
                    return u in IVY_LEAGUE
                return rec["state"] == preset

            want_campuses = {u: rec for (y, u), rec in campus_years.items() if y == year and campus_in_preset(u, rec)}
            got_campuses = {int(k): v for k, v in (data.get("campuses") or {}).items()}
            if set(got_campuses) != set(want_campuses):
                diff = sorted(set(got_campuses) ^ set(want_campuses))
                problem(f"{ranking_file.name}: the campuses table has {len(got_campuses)} campuses, expected "
                        f"{len(want_campuses)} (first difference: {diff[0]})")
            for u in sorted(set(got_campuses) & set(want_campuses)):
                inst_rec = institutions[(year, u // 1000)]
                expect = {"name": want_campuses[u]["name"], "state": want_campuses[u]["state"],
                          "main": u % 1000 == 1, "fte": inst_rec["fte"], "campuses": inst_rec["campuses"]}
                if {k: got_campuses[u].get(k) for k in expect} != expect:
                    problem(f"{ranking_file.name}: campus {u} is {got_campuses[u]}, expected {expect}")
                    break
            zero_campus_rows += len(want_campuses) - len((data.get("rankings") or {}).get("all", []))

            want = {b: rec for (y, b), rec in institutions.items()
                    if y == year and in_preset(b, rec) and rate_ranked(rec)}
            table = data.get("institutions") or {}
            got = {int(k): v for k, v in table.items()}
            if set(got) != set(want):
                diff = sorted(set(got) ^ set(want))
                problem(f"{ranking_file.name}: lists {len(got)} institutions, expected {len(want)} "
                        f"(first difference: {diff[0]})")
            for b in sorted(set(got) & set(want)):
                rec, g = want[b], got[b]
                expect = {"name": rec["name"], "unitid": rec["link"], "state": rec["state"], "fte": rec["fte"],
                          "campuses": rec["campuses"]}
                if {k: g.get(k) for k in expect} != expect:
                    problem(f"{ranking_file.name}: institution {b} is {g}, expected {expect}")
                    break
            rate_rankings = data.get("rateRankings") or {}
            for code in sorted(set(codes) | set(rate_rankings)):
                entries = rate_rankings.get(code, [])
                should = {b for b in want if counts.get((year, b, code), 0) > 0}
                have = {e.get("id") for e in entries}
                if have != should:
                    diff = sorted(should ^ have, key=str)
                    problem(f"{ranking_file.name}/{code}: rate-ranks {len(have)} institutions, expected "
                            f"{len(should)} (first difference: {diff[0]})")
                for e in entries:
                    entries_checked += 1
                    b = e.get("id")
                    if b not in want:
                        continue
                    c = counts.get((year, b, code), 0)
                    rate = e.get("rate")
                    if e.get("count") != c or not isinstance(rate, (int, float)) or \
                            abs(rate - c / want[b]["fte"] * 10000) > RATE_TOLERANCE:
                        problem(f"{ranking_file.name}/{code}: institution {b} count {e.get('count')} rate {rate}, "
                                f"expected {c} and {c / want[b]['fte'] * 10000:.4f}")
                        break

        # School files
        profiles_checked = 0
        for school_file in sorted((JSON_DIR / "schools").glob("*.json")):
            try:
                unitid = int(school_file.stem)
            except ValueError:
                continue
            school = json.loads(school_file.read_text(encoding="utf-8"))
            years = sorted({int(t["year"]) for t in school.get("trends", [])} |
                           {int(t["year"]) for t in school.get("yearlyTotals", [])})
            own = {}
            for t in school.get("trends", []):
                code = t["offense"].lower().replace(" ", "_")
                fam = t.get("offenseFamily")
                for k in [code] + [s for s, f in SUMMARY_FAMILIES.items() if f is None or f == fam]:
                    own.setdefault(int(t["year"]), {})
                    own[int(t["year"])][k] = own[int(t["year"])].get(k, 0) + int(t["count"])
            b = unitid // 1000
            want = {}
            for y in years:
                rec = institutions.get((y, b))
                if rec is None:
                    continue
                c = {code: counts[(y, b, code)] for code in codes if counts.get((y, b, code), 0) > 0}
                want[str(y)] = {"campuses": rec["campuses"], "online": rec["online"], "rateRanked": rate_ranked(rec),
                                "counts": c}
                if y in ONLINE_SHARE_YEAR and rec["online"] is not None:
                    want[str(y)]["onlineYear"] = rec["online_year"]
            got = (school.get("institution") or {}).get("byYear") or {}
            if want and (school.get("institution") or {}).get("id") != b:
                problem(f"schools/{unitid}.json: institution id {(school.get('institution') or {}).get('id')}, "
                        f"expected {b}")
            if set(got) != set(want):
                problem(f"schools/{unitid}.json: institution years {sorted(got)}, expected {sorted(want)}")
                continue
            for y, w in want.items():
                g = dict(got[y])
                if ("rateExcludedReason" in g) != institutions[(int(y), b)]["rate_excluded"]:
                    problem(f"schools/{unitid}.json: institution {y} rateExcludedReason "
                            f"{'present' if 'rateExcludedReason' in g else 'missing'}, expected the opposite")
                    break
                g.pop("rateExcludedReason", None)
                if "counts" not in g:
                    g["counts"] = {k: v for k, v in own.get(int(y), {}).items() if v > 0}
                if g != w:
                    problem(f"schools/{unitid}.json: institution {y} is {got[y]}, expected {w}")
                    break
            profiles_checked += 1

        online_left_out = {}
        small_left_out = {}
        for (y, b), rec in institutions.items():
            if rec["online"] is not None and rec["online"] >= ONLINE_EXCLUSION_PCT:
                online_left_out[y] = online_left_out.get(y, 0) + 1
            elif rec["fte"] is None or rec["fte"] < MIN_FTE_FOR_RATE:
                small_left_out[y] = small_left_out.get(y, 0) + 1
        by_year = []
        for y in sorted({y for (y, _b) in institutions}):
            listed = [rec for (yy, _b), rec in institutions.items() if yy == y]
            by_year.append({
                "year": y,
                "institutions": len(listed),
                "with_more_than_one_campus": sum(1 for r in listed if r["campuses"] > 1),
                "rate_ranked": sum(1 for r in listed if rate_ranked(r)),
                "left_out_online": online_left_out.get(y, 0),
                "left_out_fte": small_left_out.get(y, 0),
                "no_online_figure": sum(1 for r in listed if r["online"] is None and r["fte"] is not None),
                # ONLINE_SHARE_YEAR years without that other fall's share: their own year's was used
                "online_share_own_year_used": (sum(1 for r in listed if r["online_year"] == y)
                                               if y in ONLINE_SHARE_YEAR else None),
                "online_share_own_year_used_1000_fte": (
                    sum(1 for r in listed if r["online_year"] == y and (r["fte"] or 0) >= MIN_FTE_FOR_RATE)
                    if y in ONLINE_SHARE_YEAR else None),
                "left_out_online_1000_fte": sum(1 for r in listed if (r["fte"] or 0) >= MIN_FTE_FOR_RATE
                                                and r["online"] is not None and r["online"] >= ONLINE_EXCLUSION_PCT),
                "with_1000_fte": sum(1 for r in listed if (r["fte"] or 0) >= MIN_FTE_FOR_RATE),
            })
        result.details["by_year"] = by_year
        result.details["ranking_files_checked"] = files_checked
        result.details["campus_rows_with_0_all_files"] = zero_campus_rows
        result.details["rate_entries_checked"] = entries_checked
        result.details["school_files_checked"] = profiles_checked
        result.details["problems"] = len(problems)

        print(f"    {'Year':<6}{'Inst.':>7}{'Multi':>7}{'Ranked':>8}{'Online':>8}{'<FTE':>7}{'NoPct':>7}"
              f"{'1000+':>7}{'Online1000+':>13}{'OwnYearPct':>12}")
        for r in by_year:
            # OwnYearPct: in an ONLINE_SHARE_YEAR year, how many used their own year's share (with 1,000+ FTE)
            own_used = r["online_share_own_year_used"]
            own_text = "" if own_used is None else f"{own_used:,} ({r['online_share_own_year_used_1000_fte']:,})"
            print(f"    {r['year']:<6}{r['institutions']:>7,}{r['with_more_than_one_campus']:>7,}"
                  f"{r['rate_ranked']:>8,}{r['left_out_online']:>8,}{r['left_out_fte']:>7,}"
                  f"{r['no_online_figure']:>7,}{r['with_1000_fte']:>7,}{r['left_out_online_1000_fte']:>13,}"
                  f"{own_text:>12}")
        print(f"  Ranking files: {files_checked:,}; rate entries: {entries_checked:,}; school files: "
              f"{profiles_checked:,}")
        print(f"  Problems: {len(problems)}")

        if problems:
            result.failed(f"{len(problems)} problems with institution rates (first: {problems[0]}). "
                          "Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for p in problems[:5]:
                    print(f"    {p}")
        elif files_checked == 0:
            result.failed(f"No ranking files in {JSON_DIR / 'rankings'} to check. Run 04_create_aggregates.py "
                          "and 05_generate_json.py.")
        else:
            result.passed()
        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audited_build() -> dict:
    """
    What this audit is of: the SHA-256 of the site's build record (it lists
    the SHA-256 of every site file; line endings read as LF, as provenance
    hashes site files) and of each curated file the checks read.
    """
    record = provenance.PUBLISHED_MANIFEST
    return {
        "site_record": record.relative_to(PROJECT_ROOT).as_posix(),
        "site_record_sha256": provenance.site_file_sha256(record) if record.is_file() else None,
        "curated_sha256": {name: provenance.file_sha256(CURATED_DIR / name)
                           for name in CURATED_READ if (CURATED_DIR / name).is_file()},
    }


def save_audit_results(
    results: list[AuditResult],
    per_school_df: pd.DataFrame,
    verbose: bool = False,
    build: Optional[dict] = None,
):
    """Save audit results to files."""
    QA_DIR.mkdir(parents=True, exist_ok=True)

    # Determine overall status (a school whose file does not match the curated data fails it too)
    statuses = [r.status for r in results]
    if any(s == "FAIL" for s in statuses) or (per_school_df["status"] == "FAIL").any():
        overall_status = "FAIL"
    elif all(s == "PASS" for s in statuses):
        overall_status = "PASS"
    else:
        overall_status = "WARNING"

    # Save JSON report
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audited_build": build or {},
        "overall_status": overall_status,
        "summary": {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "warnings": sum(1 for r in results if r.status == "WARNING"),
        },
        "checks": [r.to_dict() for r in results],
        "schools": {
            "what_it_checks": (
                "Per site school file: yearlyTotals equal the aggregates' geo \"All\" totals (as check 2), and "
                "fteByYear and fte equal dim_enrollment's FTE for the school's years (FAIL otherwise); "
                "WARNING when fewer than 80% of its years have an FTE. A school that fails makes the overall "
                "status FAIL."),
            "total": len(per_school_df),
            "passed": len(per_school_df[per_school_df["status"] == "PASS"]),
            "failed": len(per_school_df[per_school_df["status"] == "FAIL"]),
            "warnings": len(per_school_df[per_school_df["status"] == "WARNING"]),
            "failed_unitids_first_20": [int(u) for u in per_school_df[per_school_df["status"] == "FAIL"]["unitid"][:20]],
        }
    }

    json_path = QA_DIR / "comprehensive_audit.json"
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report saved: {json_path}")

    # Save CSV report
    csv_path = QA_DIR / "comprehensive_audit.csv"
    per_school_df.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"CSV report saved: {csv_path}")

    return overall_status


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive data audit - validates ALL schools"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop immediately on first failure"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("COMPREHENSIVE DATA AUDIT - ALL SCHOOLS")
    print("=" * 60)

    results = []
    build = audited_build()  # what is audited, taken before any check reads it

    # Run all checks
    checks = [
        audit_school_completeness,
        audit_incident_totals,
        audit_fte_coverage,
        audit_rate_calculations,
        audit_ranking_order,
        audit_ranking_totals,
        audit_aggregate_consistency,
        audit_shared_statistics,
        audit_enrollment_sources,
        audit_institution_rates,
        audit_campus_identity,
    ]

    for check_fn in checks:
        result = check_fn(verbose=args.verbose)
        if result.status == "PENDING":
            result.failed("The check ended without a result")
        results.append(result)

        if args.stop_on_fail and result.status == "FAIL":
            print(f"\n  Stopping due to --stop-on-fail")
            break

    # Generate per-school report
    per_school_df = generate_per_school_report(verbose=args.verbose)

    # The files must not have changed while they were audited, or the report would describe no one build
    changed = audited_build() != build
    if changed:
        build = {**build, "site_record_sha256": None,
                 "note": "the site data or curated files changed while 07 ran; run 07 again"}

    # Save results
    overall_status = save_audit_results(results, per_school_df, verbose=args.verbose, build=build)
    if changed:
        print("\nERROR: the site data or curated files changed while 07 ran, so this report is not the "
              "audit of one build. Run 07 again when no pipeline step is running.")
        return 1

    # Print summary
    print("\n" + "=" * 60)
    print(f"OVERALL STATUS: {overall_status}")
    print("=" * 60)

    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    warnings = sum(1 for r in results if r.status == "WARNING")

    print(f"\nChecks: {passed} PASS, {failed} FAIL, {warnings} WARNING")

    schools_passed = len(per_school_df[per_school_df["status"] == "PASS"])
    schools_total = len(per_school_df)
    schools_failed = len(per_school_df[per_school_df["status"] == "FAIL"])
    print(f"Schools: {schools_passed:,} / {schools_total:,} passed "
          f"({schools_passed / schools_total * 100 if schools_total else 0:.1f}%), {schools_failed:,} FAIL")

    print(f"\nReports saved to: {QA_DIR}")

    return 0 if overall_status != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
