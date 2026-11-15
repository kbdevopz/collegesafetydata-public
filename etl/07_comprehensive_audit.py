"""
Comprehensive Data Audit - Validates ALL schools in the dataset.

This script performs thorough validation of all schools:
1. School Completeness - All schools in facts have JSON files
2. Incident Totals - JSON yearlyTotals match aggregate data
3. FTE Coverage - Report enrollment data coverage by year
4. Rate Calculations - Every published rate is n / FTE x 10,000 to 2
   decimals (3-year window rates and single-year rates) inside its interval
5. Ranking Order - Ranks are competition ranks (1, 2, 2, 4) of the counts;
   rate files are in rate order, and list positions and ranges agree with it
6. Ranking Totals - Each file's totals and campus tables agree with its
   rankings; the rate files agree with each other and with the school files
7. Aggregate Consistency - Aggregates equal the fact table, per year and geography
8. Shared Statistics - Figures two campuses report identically (in the data
   used, or in the older release a campus-year is taken from) are counted
   once in rankings and totals, under one host, and school files say so
9. Enrollment Sources - FTE, the share of exclusively online students and
   the headcounts the on-campus FTE uses are NCES's own (official FTE for
   every year, none estimated)
10. Institution Rates - The institution figures rates are made of: its
   campuses in the United States (campuses abroad apart), its on-campus FTE
   (the larger and the smaller of two estimates), the rules that give it no
   rate, pooled institutions, per geography and offense its counts and those
   at medical-center and shared campuses, the peer type; in 04's tables, the
   school files, campus-years.csv and metadata.json
11. Campus Identity - etl/reference/campus_id_changes.csv lists exactly the
   campus ID changes found again in the DOE names (with the same evidence),
   every "link" pair meets the rules, both school files link to each other,
   no figures move between the IDs, and every school file is in the search
   index under its DOE campus name
12. Rate Rules - Every 3-year rate, interval, verdict (national, peer, both
   student-count estimates), list, position, rank range, state list,
   unusual-year flag, single-year rate and count flag recomputed from check
   10's figures, metadata.json's rateRules equal to the design's values,
   the design's test vectors, flagged excess inside rank ranges, intervals
   monotone in the count
13. Interval Calibration - The intervals' coverage of single years left out
   (observed against simulated, per code and period, with pass thresholds)
14. Medical-Campus Screen - Campuses whose DOE name or address suggests a
   medical center and that hold a material share of an institution's on-campus
   count are on the medical-campus list or reviewed (a warning otherwise)

Each check's details say in "what_it_checks" exactly what it verifies. Checks
1-8, 10 and 11 compare the pipeline's own files with each other; check 9 re-reads
NCES's enrollment figures (the DRVEF CSVs, the EF A files and etl/reference),
check 10 the IPEDS HD files (hospital, Carnegie and Size & Setting fields),
NCES's headcounts and the reference lists of medical-center campuses and
campuses abroad, and checks 12 to 14 recompute the rates from check 10's
figures with their own implementation of the rules (nothing of etl/rates.py,
04 or 05 is imported or called; the rule constants are written out in SPEC
and compared with config.py and metadata.json). None re-reads the DOE
downloads.

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
import io
import csv
import sys
import json
import math
import bisect
import itertools
import argparse
import statistics
import re
import time
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, QA_DIR, JSON_DIR, DATA_YEARS, PROJECT_ROOT, GEO_CODES, GEO_FOR_ALL,
                    OFFENSE_ORDER, SHARED_MIN_NONZERO, US_STATES, IVY_LEAGUE, SUMMARY_FAMILIES, MIN_FTE_FOR_RATE,
                    ONLINE_SHARE_YEAR, HOSPITAL_CODE, MEDICAL_CARNEGIE, ONLINE_UNCERTAIN_RATIO,
                    STATE_LIST_MIN_MEMBERS)
import config
import provenance
import campus_identity

# Curated files the checks read (relative to data/curated)
CURATED_READ = ("facts/incidents.parquet", "aggs/agg_school_year_offense.parquet", "dims/dim_enrollment.parquet",
                "dims/dim_institution.parquet", "dims/campus_year_sources.parquet",
                "dims/older_release_counts.parquet", "aggs/shared_blocks.parquet",
                "dims/campus_names.parquet", "dims/campus_id_links.parquet",
                "aggs/agg_institution_year.parquet", "aggs/agg_institution_year_offense.parquet")
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


def ranking_files_data() -> list[tuple[Path, dict]]:
    """Every rankings/*.json file and its content."""
    out = []
    for ranking_file in sorted((JSON_DIR / "rankings").glob("*.json")):
        with open(ranking_file, encoding="utf-8") as f:
            out.append((ranking_file, json.load(f)))
    return out


def rate_window_files() -> list[tuple[Path, dict]]:
    """Every rates/{first year}-{last year}-{code}.json file (one window and code) and its content."""
    out = []
    for path in sorted((JSON_DIR / "rates").glob("*.json")):
        if path.name == "flags.json":
            continue
        with open(path, encoding="utf-8") as f:
            out.append((path, json.load(f)))
    return out


def rate_institution_files() -> dict[int, dict]:
    """{base UNITID: content} of every rates/institutions/{base}.json file."""
    out = {}
    for path in sorted((JSON_DIR / "rates" / "institutions").glob("*.json")):
        with open(path, encoding="utf-8") as f:
            out[int(path.stem)] = json.load(f)
    return out


def cents(value) -> Optional[int]:
    """A published 2-decimal figure as a whole number of hundredths (None when it is not a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(Decimal(str(value)).scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))


def rate_cents(n: int, fte: int) -> int:
    """n / fte x 10,000 in hundredths, rounded half up, in integers."""
    return (2 * n * 1_000_000 + fte) // (2 * fte)


def audit_rate_calculations(verbose: bool = False) -> AuditResult:
    """
    CHECK 4: The rates' arithmetic, from each file's own numbers.

    In every rates/{window}-{code}.json file: natl = natlN / natlF x 10,000
    rounded half up to 2 decimals; each entry's rate = n / fteYears x
    10,000 the same way (integer arithmetic), 0 <= lo <= rate <= hi, E =
    natlN x fteYears / natlF rounded half up to 1 decimal, fteYearsSmaller
    (an online institution's smaller estimate) between 1 and fteYears; each
    peer group's rate = its n / fteYears x 10,000. Every single-year rate of
    rates/institutions/*.json ([n, rate, lo, hi] per code) likewise with the
    year's fte. Check 12 recomputes every figure from the incidents and NCES's
    enrollment; this check needs only the files.
    """
    result = AuditResult("Rate Calculation Accuracy")
    print("\nCHECK 4: Rate Calculation Accuracy")

    try:
        rate_errors = []
        entries_checked = single_checked = 0

        def bad(text):
            rate_errors.append(text)

        windows = rate_window_files()
        for path, data in windows:
            natl_n, natl_f = data.get("natlN"), data.get("natlF")
            if not (isinstance(natl_n, int) and isinstance(natl_f, int) and natl_f > 0):
                bad(f"rates/{path.name}: natlN {natl_n}, natlF {natl_f}")
                continue
            if cents(data.get("natl")) != rate_cents(natl_n, natl_f):
                bad(f"rates/{path.name}: natl {data.get('natl')}, expected {rate_cents(natl_n, natl_f) / 100}")
            for key, peer in (data.get("peer") or {}).items():
                if not (isinstance(peer.get("n"), int) and isinstance(peer.get("fteYears"), int)
                        and peer["fteYears"] > 0 and cents(peer.get("rate")) == rate_cents(peer["n"], peer["fteYears"])):
                    bad(f"rates/{path.name}: peer {key} is {peer}")
            for e in data.get("entries") or []:
                entries_checked += 1
                n, f = e.get("n"), e.get("fteYears")
                if not (isinstance(n, int) and n >= 0 and isinstance(f, int) and f > 0):
                    bad(f"rates/{path.name}: institution {e.get('id')} has n {n}, fteYears {f}")
                    continue
                lo, rate, hi = cents(e.get("lo")), cents(e.get("rate")), cents(e.get("hi"))
                e_tenths = int(Decimal(str(e.get("E"))).scaleb(1).to_integral_value(rounding=ROUND_HALF_UP)) \
                    if isinstance(e.get("E"), (int, float)) else None
                small = e.get("fteYearsSmaller")
                if rate != rate_cents(n, f):
                    bad(f"rates/{path.name}: institution {e.get('id')} rate {e.get('rate')}, expected "
                        f"{rate_cents(n, f) / 100} ({n} / {f})")
                elif None in (lo, hi) or not 0 <= lo <= rate <= hi:
                    bad(f"rates/{path.name}: institution {e.get('id')} interval [{e.get('lo')}, {e.get('hi')}] "
                        f"does not hold its rate {e.get('rate')}")
                elif e_tenths != half_up(natl_n * f * 10, natl_f):
                    bad(f"rates/{path.name}: institution {e.get('id')} E {e.get('E')}, expected "
                        f"{half_up(natl_n * f * 10, natl_f) / 10}")
                elif small is not None and not (isinstance(small, int) and 0 < small <= f):
                    bad(f"rates/{path.name}: institution {e.get('id')} fteYearsSmaller {small}, fteYears {f}")
        institutions = rate_institution_files()
        for b, inst in institutions.items():
            for y, entry in (inst.get("years") or {}).items():
                if "rates" not in entry:
                    continue
                fte = entry.get("fte")
                if not isinstance(fte, int) or fte <= 0:
                    bad(f"rates/institutions/{b}.json: {y} has rates but fte {fte}")
                    continue
                for code, (n, rate, lo, hi) in entry["rates"].items():
                    single_checked += 1
                    r, l, h = cents(rate), cents(lo), cents(hi)
                    if not isinstance(n, int) or n < 0 or r != rate_cents(n, fte):
                        bad(f"rates/institutions/{b}.json: {y} {code} is {[n, rate, lo, hi]} with fte {fte}")
                    elif None in (l, h) or not 0 <= l <= r <= h:
                        bad(f"rates/institutions/{b}.json: {y} {code} interval [{lo}, {hi}] does not hold {rate}")

        result.details["what_it_checks"] = (
            "From each file's own numbers: in every rates/{window}-{code}.json file natl = natlN / natlF x 10,000 "
            "rounded half up to 2 decimals, each peer group's rate and each entry's rate = n / fteYears x 10,000 "
            "the same way (integer arithmetic), 0 <= lo <= rate <= hi, E = natlN x fteYears / natlF rounded half "
            "up to 1 decimal, and fteYearsSmaller between 1 and fteYears; every single-year rate in "
            "rates/institutions/*.json ([n, rate, lo, hi]) with its year's fte likewise. Check 12 recomputes "
            "every figure from the incidents and NCES's enrollment.")
        result.details["window_files"] = len(windows)
        result.details["window_entries_checked"] = entries_checked
        result.details["single_year_rates_checked"] = single_checked
        result.details["rate_errors"] = len(rate_errors)
        print(f"  Window files: {len(windows):,}; entries: {entries_checked:,}; single-year rates: {single_checked:,}")
        print(f"  Rates that are not n / FTE x 10,000 (to 2 decimals) or outside their interval: {len(rate_errors)}")

        if rate_errors:
            result.failed(f"Found {len(rate_errors)} rate calculation errors (first: {rate_errors[0]}). "
                          "Run 05_generate_json.py, then 07 again.")
            if verbose:
                for err in rate_errors[:5]:
                    print(f"    {err}")
        elif entries_checked == 0 or single_checked == 0:
            result.failed("No rates in rates/ to check. Run 04_create_aggregates.py and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")

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


def window_order_problems(name: str, entries: list, list_n: Optional[int]) -> list[str]:
    """
    Problems with one rates/{window}-{code}.json file's order and positions:
    entries by n / fteYears, highest first (exact), then name, then id; a
    listed entry's position = 1 + the listed entries with a strictly higher
    rate, rankLo <= position <= rankHi within 1..list.n; a listed entry in a
    state list (stateN >= 2) the same within its state (statePosition,
    stateRankLo, stateRankHi, stateN = the state's listed entries); no
    position fields on an entry that is not listed.
    """
    problems = []

    def key(e):
        return (Fraction(-e["n"], e["fteYears"]), e.get("name") or "", e.get("id") or 0)
    try:
        keys = [key(e) for e in entries]
    except (KeyError, TypeError, ZeroDivisionError):
        return [f"{name}: an entry without n or fteYears"]
    for i, (a, b) in enumerate(zip(keys, keys[1:])):
        if a > b:
            problems.append(f"{name}: entry {i + 1} ({entries[i].get('id')}) is listed before "
                            f"{entries[i + 1].get('id')}, which has a higher rate or comes first by name")
            break
    listed = [e for e in entries if e.get("listed")]
    if list_n is not None and len(listed) != list_n:
        problems.append(f"{name}: list.n is {list_n}, {len(listed)} entries are listed")
    rates = sorted(-Fraction(e["n"], e["fteYears"]) for e in listed)
    by_state = {}
    for e in listed:
        by_state.setdefault(e.get("state"), []).append(-Fraction(e["n"], e["fteYears"]))
    for v in by_state.values():
        v.sort()
    for e in entries:
        fields = ("position", "rankLo", "rankHi", "statePosition", "stateRankLo", "stateRankHi", "stateN")
        if not e.get("listed"):
            if any(k in e for k in fields):
                problems.append(f"{name}: institution {e.get('id')} is not listed but has a position")
            continue
        r = -Fraction(e["n"], e["fteYears"])
        pos = 1 + bisect.bisect_left(rates, r)
        lo, hi = e.get("rankLo"), e.get("rankHi")
        if e.get("position") != pos or not (isinstance(lo, int) and isinstance(hi, int)
                                             and 1 <= lo <= pos <= hi <= len(listed)):
            problems.append(f"{name}: institution {e.get('id')} position {e.get('position')} range {lo}-{hi}, "
                            f"expected position {pos} inside a range within 1-{len(listed)}")
        members = by_state[e.get("state")]
        if len(members) >= STATE_LIST_MIN_MEMBERS:
            spos = 1 + bisect.bisect_left(members, r)
            slo, shi = e.get("stateRankLo"), e.get("stateRankHi")
            if e.get("statePosition") != spos or e.get("stateN") != len(members) or not (
                    isinstance(slo, int) and isinstance(shi, int) and 1 <= slo <= spos <= shi <= len(members)):
                problems.append(f"{name}: institution {e.get('id')} state position {e.get('statePosition')} range "
                                f"{slo}-{shi} of {e.get('stateN')}, expected position {spos} of {len(members)}")
        elif any(k in e for k in fields[3:]):
            problems.append(f"{name}: institution {e.get('id')} has a state position in a state list of "
                            f"{len(members)}")
    return problems


def audit_ranking_order(verbose: bool = False) -> AuditResult:
    """
    CHECK 5: Ranks are standard competition ranks, and the entries are
    listed in ranking order.

    In each count ranking (one code of a file's "rankings") the entries are
    listed by count, largest first, ties by name (from the file's campuses
    table), then UNITID; each rank is 1 + the number of entries with a larger
    count (tied counts share a rank: 1, 2, 2, 4). In each rates/{window}-
    {code}.json file the entries are listed by rate (exact n / fteYears),
    highest first, ties by name, then base UNITID, and positions and ranges
    agree with that order (window_order_problems).
    """
    result = AuditResult("Ranking Order Validation")
    print("\nCHECK 5: Ranking Order Validation")

    try:
        order_violations = []
        groups_validated = 0
        entries_checked = 0

        for ranking_file, data in ranking_files_data():
            campuses = data.get("campuses") or {}
            for code, entries in (data.get("rankings") or {}).items():
                if not entries:
                    continue
                groups_validated += 1
                entries_checked += len(entries)

                def violation(text):
                    order_violations.append({"file": ranking_file.name, "offense": code, "problem": text})

                def key(e):
                    name = (campuses.get(str(e.get("unitid"))) or {}).get("name") or ""
                    v = e.get("count")
                    return (-(v if isinstance(v, (int, float)) else -1), name, e.get("unitid") or 0)
                for i, (current, next_entry) in enumerate(zip(entries, entries[1:])):
                    if key(current) > key(next_entry):
                        violation(f"entry {i + 1} ({current.get('unitid')}, count {current.get('count')}) is "
                                  f"listed before {next_entry.get('unitid')} (count {next_entry.get('count')})")
                        break
                for text in competition_rank_problems(entries, "count")[:1]:
                    violation(text)
        windows_validated = 0
        for path, data in rate_window_files():
            windows_validated += 1
            entries = data.get("entries") or []
            entries_checked += len(entries)
            list_n = (data.get("list") or {}).get("n") if "list" in data else None
            if data.get("code") not in LIST_CODES_SPEC and any("listed" in e for e in entries):
                order_violations.append({"file": f"rates/{path.name}", "offense": data.get("code"),
                                         "problem": "a code without lists has listed entries"})
            for text in window_order_problems(f"rates/{path.name}", entries, list_n)[:1]:
                order_violations.append({"file": f"rates/{path.name}", "offense": data.get("code"), "problem": text})

        result.details["what_it_checks"] = (
            "In every count ranking (one code of a rankings/*.json file's rankings, the summary codes included), "
            "entries are listed by count, largest first, ties by name (the file's campuses table), then UNITID, "
            "and each rank is 1 + the number of entries with a larger count, so tied counts share a rank "
            "(1, 2, 2, 4). In every rates/{window}-{code}.json file the entries are listed by rate (exact "
            "n / fteYears), highest first, ties by name, then base UNITID; list.n is the number of listed "
            "entries; each listed entry's position is 1 + the listed entries with a strictly higher rate and "
            "lies inside its range (rankLo-rankHi within 1-n); a state list (2+ members) the same within the "
            "state with stateN its members; entries not listed have no position. Check 12 recomputes the lists "
            "and ranges.")
        result.details["groups_validated"] = groups_validated
        result.details["rate_files_validated"] = windows_validated
        result.details["entries_checked"] = entries_checked
        result.details["order_violations"] = len(order_violations)

        print(f"  Count rankings (file x code) validated: {groups_validated:,}; rate files: {windows_validated:,} "
              f"({entries_checked:,} entries)")
        print(f"  Rank or order violations: {len(order_violations)}")

        if order_violations:
            v = order_violations[0]
            result.failed(f"Found {len(order_violations)} rank order violations (first: {v['file']}/{v['offense']}: "
                          f"{v['problem']}). Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for v in order_violations[:5]:
                    print(f"    {v['file']}/{v['offense']}: {v['problem']}")
        elif groups_validated == 0 or windows_validated == 0:
            result.failed("No rankings or rate files to check. Run 04_create_aggregates.py and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")

    return result


# The keys a window file's entry shares with the institution file's copy of it (rates/institutions/{base}.json)
WINDOW_ENTRY_ONLY = ("id", "unitid", "name", "state", "peerType")
INSTITUTION_CODE_ONLY = ("nByYear", "natl", "peerRate")


def audit_ranking_totals(verbose: bool = False) -> AuditResult:
    """
    CHECK 6: Each file's totals and tables agree with its rankings, and the
    rate files agree with each other.

    totals[code] equals the sum of the counts of rankings[code]; every
    ranked campus is in the file's campuses table; the rate keys v4 removed
    (institutions, rateRankings, rateUnranked, rateNotRanked) are gone. Each
    rates/{window}-{code}.json file lists each institution once, its
    summary.rated is the number of entries and its stateLists the listed
    entries per state; every entry is in rates/institutions/{id}.json, whose
    window status is "rated" and whose copy of the entry has the same
    values, with natl and peerRate as in the window file; every rated window
    of an institution file is in the window files. rates/flags.json holds
    exactly the institution files' flags. Every school file's ratesFile
    names its institution's file exactly when that file exists, and every
    institution file is named by a school file.
    """
    result = AuditResult("Ranking Totals and Tables")
    print("\nCHECK 6: Ranking Totals and Tables")

    try:
        problems = []
        groups_validated = 0

        for ranking_file, data in ranking_files_data():
            totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
            campuses = data.get("campuses") or {}
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
            old = sorted(k for k in ("institutions", "rateRankings", "rateUnranked", "rateNotRanked") if k in data)
            if old:
                problems.append(f"{ranking_file.name}: has the removed rate keys {old}")

        institutions = rate_institution_files()
        windows = rate_window_files()
        rated_pairs = set()
        for path, data in windows:
            window = "{}-{}".format(*data.get("window", ["?", "?"]))
            code = data.get("code")
            entries = data.get("entries") or []
            ids = [e.get("id") for e in entries]
            if len(ids) != len(set(ids)):
                problems.append(f"rates/{path.name}: an institution is listed twice")
            if (data.get("summary") or {}).get("rated") != len(entries):
                problems.append(f"rates/{path.name}: summary.rated {(data.get('summary') or {}).get('rated')}, "
                                f"{len(entries)} entries")
            if "list" in data:
                per_state = {}
                for e in entries:
                    if e.get("listed"):
                        per_state[e.get("state")] = per_state.get(e.get("state"), 0) + 1
                if (data.get("stateLists") or {}) != per_state:
                    problems.append(f"rates/{path.name}: stateLists {data.get('stateLists')}, the listed entries "
                                    f"per state are {per_state}")
            peers = data.get("peer") or {}
            for e in entries:
                b = e.get("id")
                rated_pairs.add((b, window))
                inst = institutions.get(b)
                status = ((inst or {}).get("windows") or {}).get(window) or {}
                copy = (status.get("codes") or {}).get(code)
                if inst is None or status.get("status") != "rated" or copy is None:
                    problems.append(f"rates/{path.name}: institution {b} has no rated {window} {code} in "
                                    f"rates/institutions/{b}.json")
                    continue
                want = {k: v for k, v in e.items() if k not in WINDOW_ENTRY_ONLY}
                # The institution file's copy also has the composition of an entry that is not listed
                got = {k: v for k, v in copy.items() if k not in INSTITUTION_CODE_ONLY
                       and (k != "composition" or "composition" in want)}
                peer_rate = (peers.get(e.get("peerType")) or {}).get("rate")
                if got != want or copy.get("natl") != data.get("natl") or copy.get("peerRate") != peer_rate:
                    problems.append(f"rates/institutions/{b}.json: {window} {code} differs from rates/{path.name}")
        for b, inst in institutions.items():
            if inst.get("id") != b:
                problems.append(f"rates/institutions/{b}.json: id {inst.get('id')}")
            for window, status in (inst.get("windows") or {}).items():
                if status.get("status") == "rated" and (b, window) not in rated_pairs:
                    problems.append(f"rates/institutions/{b}.json: rated in {window}, but in no window file")
        flags_path = JSON_DIR / "rates" / "flags.json"
        flags = json.loads(flags_path.read_text(encoding="utf-8")).get("flags") if flags_path.is_file() else None
        want_flags = sorted((b, f["year"], f["offense"], f["geo"], f["count"], f["usual"])
                            for b, inst in institutions.items() for f in inst.get("flags") or [])
        got_flags = sorted((f.get("id"), f.get("year"), f.get("offense"), f.get("geo"), f.get("count"), f.get("usual"))
                           for f in flags or [])
        if flags is None or got_flags != want_flags:
            problems.append(f"rates/flags.json holds {len(got_flags)} flags, the institution files {len(want_flags)}")
        named = set()
        for school_file in sorted((JSON_DIR / "schools").glob("*.json")):
            school = json.loads(school_file.read_text(encoding="utf-8"))
            inst = school.get("institution")
            if not inst:
                continue
            b = inst.get("id")
            want = f"rates/institutions/{b}.json" if b in institutions else None
            if inst.get("ratesFile") != want:
                problems.append(f"schools/{school_file.name}: ratesFile {inst.get('ratesFile')}, expected {want}")
            if want:
                named.add(b)
        if set(institutions) - named:
            problems.append(f"{len(set(institutions) - named)} rates/institutions files are named by no school file "
                            f"(first: {sorted(set(institutions) - named)[0]})")

        result.details["what_it_checks"] = (
            "In every rankings/*.json file, totals[code] equals the sum of rankings[code]'s counts for every code, "
            "the campuses table holds every ranked campus (and the campuses ranked with 0, which check 10 checks), "
            "and the v3 rate keys (institutions, rateRankings, rateUnranked, rateNotRanked) are gone. Each "
            "rates/{window}-{code}.json file lists an institution once, summary.rated is its number of entries and "
            "stateLists the listed entries per state; each entry is in rates/institutions/{id}.json, rated in that "
            "window, with the same values (natl and peerRate as in the window file); every rated window of an "
            "institution file is in the window files; rates/flags.json holds exactly the institution files' "
            "flags; every school file names its institution's rates file (ratesFile) exactly when it exists, and "
            "every institution file is named.")
        result.details["groups_validated"] = groups_validated
        result.details["rate_files"] = len(windows)
        result.details["institution_files"] = len(institutions)
        result.details["flags"] = len(got_flags)
        result.details["problems"] = len(problems)

        print(f"  Rankings validated: {groups_validated:,}; rate files {len(windows):,}; institution rate files "
              f"{len(institutions):,}; flags {len(got_flags):,}")
        print(f"  Problems: {len(problems)}")

        if problems:
            result.failed(f"Found {len(problems)} problems (first: {problems[0]}). Run 04_create_aggregates.py and "
                          "05_generate_json.py, then 07 again.")
            if verbose:
                for p in problems[:5]:
                    print(f"    {p}")
        elif groups_validated == 0 or not windows:
            result.failed("No rankings or rate files to check. Run 04_create_aggregates.py and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")

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
            "summed over the Criminal family, for \"violent\" and \"property\" over their offenses, for \"all\" "
            "over every offense), the state and "
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
        # per offense and summed for the summary codes (config.py
        # SUMMARY_FAMILIES: "criminal" the Criminal family, "violent" and
        # "property" their offenses, "all" every offense)
        counted = {}
        for (y, g, u), v in cells.items():
            if (y, g, u) in shadows:
                continue
            for o, c in zip(OFFENSE_ORDER, v):
                if c:
                    for key in [o] + summary_of(o, family_of.get(o), SUMMARY_FAMILIES):
                        counted[(y, u, key)] = counted.get((y, u, key), 0) + c
        code_of = {o: o.lower().replace(" ", "_") for o in OFFENSE_ORDER}
        for code in SUMMARY_FAMILIES:
            code_of[code] = code
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
    # UNITIDs). The years both report are held to the merger rate rule by
    # check 10; a year both count with differing figures is listed, since its
    # incidents are in two institutions' totals.
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
    print(f"  Links between different base UNITIDs (mergers, renumberings): {len(cross)}; institution-years where both IDs report (merger rate rule, check 10): {len(excluded_years)}; "
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
        # The headcounts the on-campus FTE uses (config.py, ONLINE_UNCERTAIN_RATIO), re-read from NCES's raw files
        heads = raw_headcounts()
        head_cols = ["enrollment_total", "enrollment_ft", "enrollment_pt", "enrollment_ug", "enrollment_ug_ft",
                     "enrollment_grad", "enrollment_grad_ft", "pcudeexc", "pcgdeexc"]
        table = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py", ["unitid", "year"] + head_cols)
        head_differ = []
        for rec in table.itertuples(index=False):
            have = tuple(None if pd.isna(v) else int(v) for v in rec[2:])
            want = heads.get((int(rec[0]), int(rec[1])), (0, 0, 0) + (None,) * 6)
            if have != want:
                head_differ.append((int(rec[1]), int(rec[0]), have, want))
        result.details["headcounts_differ"] = len(head_differ)
        print(f"  Headcounts (total, full-time, part-time; by level from 2021): {len(table):,} institution-years, "
              f"different from NCES's {len(head_differ)}")
        if head_differ:
            y, u, have, want = sorted(head_differ)[0]
            result.failed(f"{len(head_differ)} institution-years have other headcounts than NCES's raw files "
                          f"(first: {u} {y}: {have}, NCES {want}). Run 02b and 02a, then 04 to 07 again.")
        result.details["what_it_checks"] = (
            "dims/dim_enrollment.parquet against NCES's own figures, re-read: 2015-2020 from "
            "etl/reference/ipeds_official_fte.csv (DRVEF tables of NCES's final Access databases), 2021 on "
            "from the DRVEF CSV the pipeline reads. Every institution-year with an FTE must be there with the "
            "same FTE and percent of exclusively online students (pctdeexc), and nothing else; and its "
            "headcounts the same as NCES's raw files: total, full-time and part-time (2015-2020 the EF A file, "
            "EFALEVEL 22 + 32 and 42 + 52; 2021 on DRVEF ENRTOT, ENRFT, ENRPT) and from 2021 by level (EFUG, "
            "EFUGFT, EFGRAD, EFGRADFT, PCUDEEXC, PCGDEEXC).")
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


def summary_of(offense: str, family: str, summaries: dict) -> list[str]:
    """The summary codes of config.py SUMMARY_FAMILIES (a family, a tuple of offenses, or every offense) an offense is in."""
    out = []
    for code, group in summaries.items():
        if group is None or (isinstance(group, str) and group == family) or \
                (isinstance(group, tuple) and offense in group):
            out.append(code)
    return out


def half_up(numerator: int, denominator: int) -> int:
    """numerator / denominator rounded half up, with Decimal arithmetic."""
    return int((Decimal(numerator) / Decimal(denominator)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def hd_classes() -> dict:
    """
    From the raw IPEDS HD files (not 03's table): {(year, UNITID): (rule, reason
    text start)} for the institution-years the population rule leaves out:
    HOSPITAL = HOSPITAL_CODE; else the newest Carnegie basic field the file
    has (C21BASIC, C18BASIC, C15BASIC) in MEDICAL_CARNEGIE; else listed in
    etl/reference/rate_population_exclusions.csv.
    """
    out = {}
    for y in DATA_YEARS:
        path = PROJECT_ROOT / "data" / "raw" / "ipeds" / str(y) / f"hd{y}.csv"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        rows = csv.DictReader(io.StringIO(text))
        rows.fieldnames = [f.strip().upper() for f in rows.fieldnames]
        field = next(f for f in ("C21BASIC", "C18BASIC", "C15BASIC") if f in rows.fieldnames)
        for r in rows:
            try:
                u = int(r["UNITID"])
            except ValueError:
                continue
            hosp, basic = r["HOSPITAL"].strip(), r[field].strip()
            if hosp.lstrip("-").isdigit() and int(hosp) == HOSPITAL_CODE:
                out[(y, u)] = "hospital"
            elif basic.lstrip("-").isdigit() and int(basic) in MEDICAL_CARNEGIE[field]:
                out[(y, u)] = "medical"
    listed = PROJECT_ROOT / "etl" / "reference" / "rate_population_exclusions.csv"
    with open(listed, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for y in range(int(r["first_year"]), int(r["last_year"]) + 1):
                if y in DATA_YEARS:
                    out.setdefault((y, int(r["unitid"])), "listed")
    return out


def whole(text: str) -> Optional[int]:
    """A raw NCES cell as a whole number: None when blank or "." (not applicable)."""
    text = str(text).strip()
    if text in ("", ".", "nan"):
        return None
    value = float(text)
    if value != int(value):
        raise RuntimeError(f"Expected a whole number in an NCES file, found {text!r}")
    return int(value)


_RAW_HEADCOUNTS = None


def raw_headcounts() -> dict:
    """
    From NCES's raw files, not 02a's or 02b's tables: {(UNITID, year):
    (total, full-time, part-time, UG, UG full-time, graduate, graduate
    full-time, UG % exclusively online, graduate %)}. 2021 on from the
    DRVEF CSV the pipeline reads (ENRTOT, ENRFT, ENRPT, a blank counting 0;
    EFUG, EFUGFT, EFGRAD, EFGRADFT, PCUDEEXC, PCGDEEXC, a blank or "." none);
    2015-2020 from the EF A file (full-time = EFALEVEL 22 + 32, part-time =
    42 + 52, of EFTOTLT, a missing level 0; no level figures). Read once per
    run (checks 9 and 10 use it).
    """
    global _RAW_HEADCOUNTS
    if _RAW_HEADCOUNTS is not None:
        return _RAW_HEADCOUNTS
    import ipeds_files
    out = {}
    for year in DATA_YEARS:
        if year >= 2021:
            path = ipeds_files.pipeline_csv(year, f"drvef{year}")
            if path is None:
                continue
            cols = ["UNITID", "ENRTOT", "ENRFT", "ENRPT", "EFUG", "EFUGFT", "EFGRAD", "EFGRADFT", "PCUDEEXC",
                    "PCGDEEXC"]
            raw = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)
            for rec in raw.itertuples(index=False):
                vals = [whole(v) for v in rec[1:]]
                out[(int(rec[0]), year)] = tuple(v or 0 for v in vals[:3]) + tuple(vals[3:])
        else:
            path = ipeds_files.pipeline_csv(year, f"ef{year}a")
            if path is None:
                continue
            raw = pd.read_csv(path, usecols=["UNITID", "EFALEVEL", "EFTOTLT"], dtype=str, keep_default_na=False)
            sums = {}
            for u, level, n in zip(raw["UNITID"].tolist(), raw["EFALEVEL"].tolist(), raw["EFTOTLT"].tolist()):
                level = whole(level)
                if level in (22, 32, 42, 52):
                    side = 0 if level in (22, 32) else 1
                    acc = sums.setdefault(int(u), [0, 0])
                    acc[side] += whole(n) or 0
            for u, (ft, pt) in sums.items():
                out[(u, year)] = (ft + pt, ft, pt, None, None, None, None, None, None)
    _RAW_HEADCOUNTS = out
    return out


def medical_campus_years() -> set:
    """{(campus UNITID, year)} of etl/reference/medical_campuses.csv, read here (not 03's table)."""
    out = set()
    with open(PROJECT_ROOT / "etl" / "reference" / "medical_campuses.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for y in range(int(r["first_year"]), int(r["last_year"]) + 1):
                if y in DATA_YEARS:
                    out.add((int(r["unitid"]), y))
    return out


def shared_campus_overrides() -> dict:
    """
    {(campus UNITID, year): host campus UNITID} of
    etl/reference/shared_campus_overrides.csv (campuses whose reported
    figures are another institution's campus figures), read here (not 03's
    table).
    """
    out = {}
    with open(PROJECT_ROOT / "etl" / "reference" / "shared_campus_overrides.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            u, h = int(r["unitid"]), int(r["host_unitid"])
            if u // 1000 == h // 1000:
                raise RuntimeError(f"etl/reference/shared_campus_overrides.csv: {u} and its host {h} are campuses "
                                   "of one institution")
            for y in range(int(r["first_year"]), int(r["last_year"]) + 1):
                if y in DATA_YEARS:
                    if (u, y) in out:
                        raise RuntimeError(f"etl/reference/shared_campus_overrides.csv lists {u} twice for {y}")
                    out[(u, y)] = h
    return out


def oncampus_estimates(fte: int, share: Optional[int], heads: Optional[tuple], by_level: bool) -> dict:
    """
    config.py's two on-campus FTE estimates in whole-number arithmetic (no
    Fraction): a = fte x (100 - share) / 100 as (A, 100); b, part time first,
    as (B, 100 x max(PT, 1)): on-campus headcount H x (100 - share) (by
    level when `by_level` and the levels add up to the totals), full-time
    on campus min(FT x 100, that), the rest at (FTE - FT) / PT. b is None
    when the headcounts do not add up (total 0, FT + PT not the total, FTE
    outside [FT, total]). uncertain: a share above 0 and b None or
    larger x 4 > smaller x 5 (ONLINE_UNCERTAIN_RATIO). oncampus: the larger,
    rounded half up (FTE without a share or with 0).
    """
    if not share:
        return {"a": (fte, 1), "b": (fte, 1), "uncertain": False, "oncampus": fte, "level": False}
    A = fte * (100 - share)
    total, ft, pt = (heads or (0, 0, 0))[:3]
    if not (total > 0 and ft + pt == total and ft <= fte <= total):
        return {"a": (A, 100), "b": None, "uncertain": True, "oncampus": half_up(A, 100), "level": False}
    level = None
    if by_level and heads is not None and None not in heads[3:7]:
        ug, ug_ft, grad, grad_ft, pcu, pcg = heads[3:9]
        if pcu is None and ug == 0:
            pcu = 0
        if pcg is None and grad == 0:
            pcg = 0
        if (pcu is not None and pcg is not None and ug + grad == total and ug_ft + grad_ft == ft
                and ug_ft <= ug and grad_ft <= grad):
            level = (ug, ug_ft, grad, grad_ft, pcu, pcg)
    if level:
        ug, ug_ft, grad, grad_ft, pcu, pcg = level
        on_ug, on_grad = ug * (100 - pcu), grad * (100 - pcg)
        on = on_ug + on_grad
        ft_on = min(ug_ft * 100, on_ug) + min(grad_ft * 100, on_grad)
    else:
        on = total * (100 - share)
        ft_on = min(ft * 100, on)
    d = max(pt, 1)
    B = ft_on * d + (on - ft_on) * (fte - ft)
    num, den = ONLINE_UNCERTAIN_RATIO
    big, small = max(A * d, B), min(A * d, B)
    return {"a": (A, 100), "b": (B, 100 * d), "uncertain": big * den > small * num,
            "oncampus": half_up(big, 100 * d), "level": level is not None}


def hd_size_settings() -> dict:
    """
    From the raw IPEDS HD files (not 03's table): {UNITID: Carnegie Size &
    Setting value} for the institutions an HD file classifies: the first of
    C21SZSET, C18SZSET, C15SZSET that any year's file gives the institution
    with a value above 0, and of that field the newest year's value.
    """
    fields = ("C21SZSET", "C18SZSET", "C15SZSET")
    found = {}  # (field, UNITID) -> (year, value)
    for y in DATA_YEARS:
        path = PROJECT_ROOT / "data" / "raw" / "ipeds" / str(y) / f"hd{y}.csv"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        rows = csv.DictReader(io.StringIO(text))
        rows.fieldnames = [f.strip().upper() for f in rows.fieldnames]
        present = [f for f in fields if f in rows.fieldnames]
        for r in rows:
            try:
                u = int(r["UNITID"])
            except ValueError:
                continue
            for f in present:
                v = r[f].strip()
                if v.lstrip("-").isdigit() and int(v) > 0:
                    found[(f, u)] = (y, int(v))  # DATA_YEARS ascend: the newest year's value stays
    out = {}
    for u in sorted({u for (_f, u) in found}):
        f = next(f for f in fields if (f, u) in found)
        out[u] = found[(f, u)][1]
    return out


# The spec's peer types: Carnegie Size & Setting values per type (anything else, or no value: "other")
SPEC_PEER_TYPES = {"two_year": (1, 2, 3, 4, 5), "nonresidential": (6, 9, 12, 15), "residential": (7, 10, 13, 16),
                   "highly_residential": (8, 11, 14, 17)}
# The codes with ordered lists
LIST_CODES_SPEC = ("violent", "criminal_xmvt", "burglary")


def spec_peer_type(size_setting: Optional[int]) -> str:
    """The peer type of a Size & Setting value (SPEC_PEER_TYPES; "other" otherwise)."""
    return next((k for k, values in SPEC_PEER_TYPES.items() if size_setting in values), "other")


def reference_abroad() -> set:
    """The campus UNITIDs of etl/reference/campuses_abroad.csv (abroad, though DOE gives them a U.S. state)."""
    with open(PROJECT_ROOT / "etl" / "reference" / "campuses_abroad.csv", encoding="utf-8", newline="") as f:
        return {int(r["unitid"]) for r in csv.DictReader(f)}


class Expected:
    """
    What 04 and 05 must publish about institutions and rates, found again
    by expected_institutions without their code:
      institutions {(year, base): rec}, counts {(year, base, code): count at
      its counting campuses in the United States}, abroad, shared_in,
      shared_out (the same keys), geo {(year, base, DOE offense): [on campus,
      residence halls, non-campus, public property]} (for the rates: without
      the campuses of etl/reference/shared_campus_overrides.csv), medical_on,
      shared_in_on, shared_out_on, override_count {(year, base, DOE offense):
      count}, campus_geo {(year,
      campus, DOE offense): [on campus, residence halls]} (counting campuses
      in the United States), campus_years {(year, unitid): {name, state}},
      campus_codes {(year, unitid): {code: count}} (shadow blocks left out),
      family_of {offense code: family}, medical_years, abroad_campuses.
    """


_EXPECTED_INSTITUTIONS = None


def expected_institutions() -> Expected:
    """
    Without 04's or 05's code, the institution-years rates are calculated for
    (config.py, "SUMMARY CODES AND RATES" and "Rates"), from the fact table,
    the shadow blocks of aggs/shared_blocks.parquet (check 8 finds them
    again), the reported campus-years, dim_institution, dim_enrollment's FTE
    and online share (check 9 compares them with NCES), NCES's raw
    headcounts (raw_headcounts), etl/reference/medical_campuses.csv,
    etl/reference/campuses_abroad.csv and the raw IPEDS HD files
    (hd_classes, hd_size_settings). Computed once per run (checks 10 and 12
    to 14 use it).

    A campus-year counts (in rankings, with 0 when it had no incident, and
    for its institution, the base UNITID) when the campus reported that year
    and its figures are not all shadow blocks. A campus DOE lists without a
    state, or in etl/reference/campuses_abroad.csv, is abroad: its incidents
    are not in its institution's counts (IPEDS fall enrollment leaves out
    students at branch campuses abroad) but are kept apart (abroad). The
    institution's counts are its other counting campuses' counts in
    GEO_FOR_ALL without shadow blocks; per geography the same, with the
    residence-hall rows of its counting campuses (DOE's subset of on campus;
    shadow blocks are never residence-hall rows). An institution-year is
    listed when one of its campuses counts, incidents or not; campuses is the
    number in the United States. Its link campus is the main campus (UNITID
    ending in 001) when that counts, otherwise the counting campus with the
    most incidents (ties: lowest UNITID), of those in the United States when
    it has one.

    The rate rules, each independently of 04: on-campus FTE
    (oncampus_estimates; the online share of the fall ONLINE_SHARE_YEAR
    names when NCES has one, by level only with the year's own share), the
    larger estimate rounded half up, and the smaller one (none when the
    part-time-first estimate cannot be calculated); no rate: the population
    rule (hd_classes), the merger rules (a campus under two IDs, a merger
    family); the first rule in the order hospital, medical, listed, merger,
    family is the one published. The rate's denominator adds the on-campus
    FTE of the institutions pooled with it (merger, or a shared campus whose
    other institution counts no campus of its own and has one host
    institution); the smaller denominator adds their smaller estimates (none
    when one has none); uncertain when its own or a pooled institution's
    on-campus FTE is. Other shared campuses (a shadow block whose host has
    another base UNITID and is not a linked ID of the same campus): the host
    block's figures are the host institution's shared_in (each host block
    once), and the shadow institution's shared_out when it counts a campus
    of its own that year (each shadow block); neither for a campus abroad;
    shared_in_on and shared_out_on the same of on-campus blocks. A campus of
    etl/reference/shared_campus_overrides.csv (its figures are another
    institution's campus figures): in its institution's counts (counts, and
    override_count per DOE offense), in no geography of the rates and no
    medical_on; each of its blocks that is not a shadow block adds its own
    figures to its institution's shared_out (shared_out_on for on campus)
    and the host campus's block, once, to the host institution's shared_in
    (shared_in_on). medical_on:
    per DOE offense, at campuses of the reference list in its years, the
    campus's on-campus count less its residence-hall count, not below 0.
    peer_type: the institution's Carnegie Size & Setting type
    (hd_size_settings, SPEC_PEER_TYPES).
    """
    global _EXPECTED_INSTITUTIONS
    if _EXPECTED_INSTITUTIONS is not None:
        return _EXPECTED_INSTITUTIONS
    facts = pd.read_parquet(get_facts_path(), columns=["year", "unitid", "offense", "offense_family", "geo", "count"])
    residence = facts[facts["geo"] == "Residence halls"]
    facts = facts[facts["geo"].isin(GEO_FOR_ALL)]
    shared = read_curated("aggs/shared_blocks.parquet", "04_create_aggregates.py")
    sources = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py", ["unitid", "year"])
    inst = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py", ["unitid", "institution_name", "state"])
    enrollment = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py",
                              ["unitid", "year", "fte", "pctdeexc"])
    heads = raw_headcounts()
    medical_years = medical_campus_years()
    override_host = shared_campus_overrides()
    size_settings = hd_size_settings()

    name = dict(zip(inst["unitid"].astype(int).tolist(), inst["institution_name"].tolist()))
    state = {}
    for u, s in zip(inst["unitid"].astype(int).tolist(), inst["state"].tolist()):
        state[u] = None if s is None or pd.isna(s) or not str(s).strip() else s
    listed_abroad = reference_abroad()
    unknown = sorted(u for u in listed_abroad if u not in name)
    if unknown:
        raise RuntimeError(f"etl/reference/campuses_abroad.csv lists {unknown[0]}, which is not a campus in "
                           "dim_institution")
    abroad_campus = {u for u, s in state.items() if s is None} | listed_abroad
    unknown = sorted(u for u, _y in medical_years if u not in name)
    if unknown:
        raise RuntimeError(f"etl/reference/medical_campuses.csv lists {unknown[0]}, which is not a campus in "
                           "dim_institution")

    shadows = {(int(y), g, int(u)) for y, g, u, role in zip(shared["year"].tolist(), shared["geo"].tolist(),
                                                            shared["unitid"].tolist(), shared["role"].tolist())
               if role == "shadow"}
    summaries = {code: family for code, family in SUMMARY_FAMILIES.items()}
    counts, abroad_counts = {}, {}
    campus_codes = {}  # (year, unitid) -> {code: count} without shadow blocks
    block_codes = {}  # (year, unitid, geo) -> {code: count} without shadow blocks
    block_offenses = {}  # (year, unitid, geo) -> {DOE offense: count} without shadow blocks
    campus_geo = {}  # (year, unitid, DOE offense) -> [on campus, residence halls]
    geo_slot = {"On-campus": 0, "Non-campus": 2, "Public property": 3}
    campus_geo_all = {}  # (year, unitid, DOE offense) -> [on, res, non, pub], every campus
    campus_total = {}  # (unitid, year) -> count without shadow blocks
    published = set()  # (unitid, year) with an incident in DOE's figures, shadow blocks included
    family_of = {}
    for y, u, o, fam, g, c in zip(facts["year"].tolist(), facts["unitid"].tolist(), facts["offense"].tolist(),
                                  facts["offense_family"].tolist(), facts["geo"].tolist(), facts["count"].tolist()):
        y, u, c = int(y), int(u), int(c)
        family_of[o.lower().replace(" ", "_")] = fam
        if c > 0:
            published.add((u, y))
        if (y, g, u) in shadows or c == 0:
            continue
        campus_total[(u, y)] = campus_total.get((u, y), 0) + c
        offenses = block_offenses.setdefault((y, u, g), {})
        offenses[o] = offenses.get(o, 0) + c
        campus_geo_all.setdefault((y, u, o), [0, 0, 0, 0])[geo_slot[g]] += c
        block = block_codes.setdefault((y, u, g), {})
        here = campus_codes.setdefault((y, u), {})
        for code in [o.lower().replace(" ", "_")] + summary_of(o, fam, summaries):
            block[code] = block.get(code, 0) + c
            here[code] = here.get(code, 0) + c
            key = (y, u // 1000, code)
            if u in abroad_campus:
                abroad_counts[key] = abroad_counts.get(key, 0) + c
                continue
            counts[key] = counts.get(key, 0) + c

    shadowed = {(u, y) for (y, _g, u) in shadows}
    counting = [(int(u), int(y)) for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist())
                if (int(u), int(y)) not in shadowed or (int(u), int(y)) in campus_total]
    counting_set = set(counting)
    # Residence halls: DOE's subset of on campus, of the campus-years that count
    for y, u, o, c in zip(residence["year"].tolist(), residence["unitid"].tolist(), residence["offense"].tolist(),
                          residence["count"].tolist()):
        y, u, c = int(y), int(u), int(c)
        if c > 0 and (u, y) in counting_set:
            campus_geo_all.setdefault((y, u, o), [0, 0, 0, 0])[1] += c
    geo, medical_on, override_count = {}, {}, {}
    for (y, u, o), v in campus_geo_all.items():
        if u in abroad_campus or (u, y) not in counting_set:
            continue
        if (u, y) in override_host:
            override_count[(y, u // 1000, o)] = override_count.get((y, u // 1000, o), 0) + v[0] + v[2] + v[3]
            continue
        campus_geo[(y, u, o)] = [v[0], v[1]]
        g = geo.setdefault((y, u // 1000, o), [0, 0, 0, 0])
        for i in range(4):
            g[i] += v[i]
        if (u, y) in medical_years and v[0] > v[1]:
            medical_on[(y, u // 1000, o)] = medical_on.get((y, u // 1000, o), 0) + v[0] - v[1]
    fte = {(int(u), int(y)): (None if pd.isna(f) else int(f), None if pd.isna(p) else int(p))
           for u, y, f, p in zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(),
                                 enrollment["fte"].tolist(), enrollment["pctdeexc"].tolist())}

    by_inst = {}
    for u, y in counting:
        by_inst.setdefault((y, u // 1000), []).append(u)

    # A campus DOE reported under two institutions in one year (the link rows
    # of etl/reference/campus_id_changes.csv whose IDs have different base
    # UNITIDs, both reporting the year): the institution whose IPEDS FTE holds
    # its students is the only one of the two with an FTE, or, with both, the
    # one whose every reported campus that year is linked to a campus of the
    # other (exactly one). Unknown: both left out. The other counts the
    # campus: its rate adds the students' institution's FTE when that one
    # counts no campus that year and is added to no other institution,
    # otherwise it is left out. The students' institution does not count the
    # campus but counts others: left out. None of these exclusions for a
    # campus without an incident under either ID that year.
    reported_by = {}
    campuses_of = {}
    for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist()):
        reported_by.setdefault(int(u), set()).add(int(y))
        campuses_of.setdefault((int(y), int(u) // 1000), set()).add(int(u))
    id_links = campus_identity.read_id_changes()
    id_links = id_links[id_links["decision"] == "link"]
    cross = [(o, n) for o, n in zip(id_links["old_unitid"].astype(int), id_links["new_unitid"].astype(int))
             if o // 1000 != n // 1000]
    with_fte = {k for k, (f, _p) in fte.items() if f is not None}
    rate_excluded = set()
    rules_of = {}  # (year, base) -> the rules that leave it out
    add_to = {}  # (year, students' base) -> bases whose rate would add its FTE
    for y in sorted({yy for ys in reported_by.values() for yy in ys}):
        active = [(o, n) for o, n in cross if y in reported_by.get(o, ()) and y in reported_by.get(n, ())]
        partner = {}
        for o, n in active:
            partner.setdefault((o // 1000, n // 1000), set()).add(o)
            partner.setdefault((n // 1000, o // 1000), set()).add(n)
        for o, n in active:
            a, b = o // 1000, n // 1000
            fa, fb = (a, y) in with_fte, (b, y) in with_fte
            if not (fa or fb):
                continue
            silent = not ({(o, y), (n, y)} & published)
            if fa and fb:
                full = [x for x, z in ((a, b), (b, a)) if campuses_of[(y, x)] == partner[(x, z)]]
                students = full[0] if len(full) == 1 else None
            else:
                students = a if fa else b
            if students is None:
                if not silent:
                    rate_excluded |= {(y, a), (y, b)}
                continue
            other = b if students == a else a
            own_copy, other_copy = (o, n) if students == a else (n, o)
            if (other_copy, y) in counting_set:
                if (own_copy, y) not in counting_set and (y, students) not in by_inst and (other, y) in with_fte:
                    add_to.setdefault((y, students), set()).add(other)
                elif (other, y) in with_fte and not silent:
                    rate_excluded.add((y, other))
            if (own_copy, y) not in counting_set and (y, students) in by_inst and not silent:
                rate_excluded.add((y, students))
    pooled, pooled_rules = {}, {}
    for (y, s), targets in add_to.items():
        if len(targets) > 1:
            rate_excluded |= {(y, t) for t in targets}
        else:
            pooled.setdefault((y, min(targets)), set()).add(s)
            pooled_rules.setdefault((y, min(targets)), set()).add("merger")
    for key in rate_excluded:
        rules_of.setdefault(key, set()).add("merger")
    institutions = {}
    for (y, b), campuses in by_inst.items():
        with_file = [u for u in campuses if u in name]
        if not with_file:
            raise RuntimeError(f"Institution {b} has campuses that count in {y} but none in dim_institution")
        home = [u for u in with_file if u not in abroad_campus] or with_file
        main = b * 1000 + 1
        link = main if main in home else min(home, key=lambda u: (-campus_total.get((u, y), 0), u))
        f, online = fte.get((b, y), (None, None))
        # The online share the rules use: in an ONLINE_SHARE_YEAR year, that
        # other fall's share when NCES has one, else the year's own
        online_year = y if online is not None else None
        if y in ONLINE_SHARE_YEAR:
            src_online = fte.get((b, ONLINE_SHARE_YEAR[y]), (None, None))[1]
            if src_online is not None:
                online, online_year = src_online, ONLINE_SHARE_YEAR[y]
        n_abroad = sum(1 for u in campuses if u in abroad_campus)
        institutions[(y, b)] = {"name": name[link], "link": link, "state": state.get(link),
                                "campuses": len(campuses) - n_abroad, "abroad": n_abroad, "fte": f,
                                "online": online, "online_year": online_year,
                                "peer_type": spec_peer_type(size_settings.get(b))}
    # And every institution of a merger family (bases joined by those links)
    # in a year its campuses count under two or more institutions and one of
    # them has no IPEDS FTE
    family_members = {}
    for o, n in zip(id_links["old_unitid"].astype(int), id_links["new_unitid"].astype(int)):
        if o // 1000 != n // 1000:
            merged = family_members.get(o // 1000, {o // 1000}) | family_members.get(n // 1000, {n // 1000})
            for b in merged:
                family_members[b] = merged
    family_years = {}
    for (y, b), rec in institutions.items():
        if b in family_members:
            family_years.setdefault((y, min(family_members[b])), []).append(b)
    # ... when a member without an FTE counts a campus with an incident that
    # year whose figures no member with an FTE also counts under a linked ID
    linked_to = {}
    for o, n in cross:
        for y in reported_by.get(o, set()) & reported_by.get(n, set()):
            linked_to.setdefault((o, y), set()).add(n)
            linked_to.setdefault((n, y), set()).add(o)
    for (y, _f), bases in family_years.items():
        if len(bases) < 2 or not any(institutions[(y, b)]["fte"] is None for b in bases):
            continue
        fte_bases = {b for b in bases if institutions[(y, b)]["fte"] is not None}
        unmatched = [c for b in bases if institutions[(y, b)]["fte"] is None for c in by_inst[(y, b)]
                     if (c, y) in published
                     and not any(p // 1000 in fte_bases and (p, y) in counting_set for p in linked_to.get((c, y), ()))]
        if unmatched:
            for b in bases:
                rules_of.setdefault((y, b), set()).add("family")
    # Shared campuses
    link_pairs = {frozenset((int(o), int(n))) for o, n in zip(id_links["old_unitid"], id_links["new_unitid"])}
    host_bases, shadow_blocks = {}, {}
    for y, g, u, h, role in zip(shared["year"].tolist(), shared["geo"].tolist(), shared["unitid"].tolist(),
                                shared["host_unitid"].tolist(), shared["role"].tolist()):
        y, u, h = int(y), int(u), int(h)
        if role == "shadow" and u // 1000 != h // 1000 and frozenset((u, h)) not in link_pairs:
            host_bases.setdefault((y, u // 1000), set()).add(h // 1000)
            shadow_blocks.setdefault((y, u // 1000), []).append((g, u, h))
    partial = []  # (year, geo, shadow campus, host campus, whether the shadow's institution is listed)
    for (y, a), hosts in host_bases.items():
        if (y, a) not in institutions and len(hosts) == 1:
            if (a, y) in with_fte:
                pooled.setdefault((y, min(hosts)), set()).add(a)
                pooled_rules.setdefault((y, min(hosts)), set()).add("shared")
            continue
        partial += [(y, g, u, h, (y, a) in institutions) for g, u, h in shadow_blocks[(y, a)]]
    # The blocks with counts (not shadow blocks) of the campuses of
    # shared_campus_overrides.csv, in the United States, that count that year
    override_blocks = [(y, g, u, h) for (u, y), h in sorted(override_host.items())
                       if (u, y) in counting_set and u not in abroad_campus
                       for g in GEO_FOR_ALL if block_offenses.get((y, u, g))]
    host_set = ({(y, h, g) for (y, g, _u, h, _l) in partial if h not in abroad_campus}
                | {(y, h, g) for (y, g, _u, h) in override_blocks if h not in abroad_campus})
    shared_in, shared_out, shared_in_on, shared_out_on = {}, {}, {}, {}
    for y, h, g in host_set:
        for code, c in block_codes.get((y, h, g), {}).items():
            shared_in[(y, h // 1000, code)] = shared_in.get((y, h // 1000, code), 0) + c
        if g == "On-campus":
            for o, c in block_offenses.get((y, h, g), {}).items():
                shared_in_on[(y, h // 1000, o)] = shared_in_on.get((y, h // 1000, o), 0) + c
    for y, g, u, h, listed in partial:
        if listed and u not in abroad_campus:
            for code, c in block_codes.get((y, h, g), {}).items():
                shared_out[(y, u // 1000, code)] = shared_out.get((y, u // 1000, code), 0) + c
            if g == "On-campus":
                for o, c in block_offenses.get((y, h, g), {}).items():
                    shared_out_on[(y, u // 1000, o)] = shared_out_on.get((y, u // 1000, o), 0) + c
    for y, g, u, _h in override_blocks:
        for code, c in block_codes.get((y, u, g), {}).items():
            shared_out[(y, u // 1000, code)] = shared_out.get((y, u // 1000, code), 0) + c
        if g == "On-campus":
            for o, c in block_offenses[(y, u, g)].items():
                shared_out_on[(y, u // 1000, o)] = shared_out_on.get((y, u // 1000, o), 0) + c
    # The population rule: a hospital, a special-focus medical school, or listed
    for key, rule in hd_classes().items():
        if key in institutions:
            rules_of.setdefault(key, set()).add(rule)

    # On-campus FTE (oncampus_estimates), of every institution-year with an FTE
    estimates = {}
    for (b, y), (f, own_share) in fte.items():
        if f is None:
            continue
        src = ONLINE_SHARE_YEAR.get(y, y)
        src_share = fte.get((b, src), (None, None))[1]
        own = not (src != y and src_share is not None)
        share = own_share if own else src_share
        est = oncampus_estimates(f, share, heads.get((b, y)), own)
        est["smaller"] = None if est["b"] is None else half_up(*min(est["a"], est["b"],
                                                                    key=lambda q: Fraction(q[0], q[1])))
        estimates[(b, y)] = est

    order = ("hospital", "medical", "listed", "merger", "family")
    for (y, b), rec in institutions.items():
        rec["rules"] = sorted(rules_of.get((y, b), ()))
        rec["rule"] = next((r for r in order if r in rules_of.get((y, b), ())), None)
        est = estimates.get((b, y))
        rec["oncampus"] = None if est is None else est["oncampus"]
        rec["est_a"] = None if est is None else half_up(*est["a"])
        rec["est_b"] = None if est is None or est["b"] is None else half_up(*est["b"])
        rec["oncampus_smaller"] = None if est is None else est["smaller"]
        adds = sorted(pooled.get((y, b), ())) if rec["rule"] is None and rec["fte"] is not None else []
        rec["pooled"] = adds
        rec["pooled_rules"] = sorted(pooled_rules.get((y, b), ())) if adds else []
        rec["pooled_fte"] = {s: estimates[(s, y)]["oncampus"] for s in adds}
        rec["rate_fte"] = None if rec["oncampus"] is None else rec["oncampus"] + sum(rec["pooled_fte"].values())
        smaller = [rec["oncampus_smaller"]] + [estimates[(s, y)]["smaller"] for s in adds]
        rec["rate_fte_smaller"] = None if est is None or None in smaller else sum(smaller)
        rec["uncertain_own"] = est is not None and est["uncertain"]
        rec["uncertain"] = est is not None and (est["uncertain"] or any(estimates[(s, y)]["uncertain"] for s in adds))
    campus_years = {}
    for u, y in counting:
        if u not in name:
            raise RuntimeError(f"Campus {u} reported {y} but is not in dim_institution")
        campus_years[(y, u)] = {"name": name[u], "state": state.get(u)}
    e = Expected()
    e.institutions, e.counts, e.campus_years = institutions, counts, campus_years
    e.abroad, e.shared_in, e.shared_out = abroad_counts, shared_in, shared_out
    e.geo, e.medical_on, e.shared_in_on, e.shared_out_on = geo, medical_on, shared_in_on, shared_out_on
    e.override_count = override_count
    e.campus_geo, e.campus_codes, e.family_of = campus_geo, campus_codes, family_of
    e.medical_years, e.abroad_campuses = medical_years, abroad_campus
    _EXPECTED_INSTITUTIONS = e
    return e


def rate_inputs(E: Optional[Expected] = None) -> dict:
    """
    The institution figures checks 12 to 14 recompute the rates from, from
    expected_institutions (not 04's tables): inst {(year, base): {name, link,
    state, fte, rate_fte, rate_fte_smaller, rule, uncertain, uncertain_own,
    peer_type}}; off {(year, base, DOE offense): (on campus, residence halls,
    non-campus, public property)}; medical_on, shared_in_on, shared_out_on
    {(year, base, DOE offense): count}; count_all {(year, base, count code):
    count over all geographies}; campus_on_res {(year, campus, DOE offense):
    (on campus, residence halls)}. Zeros are left out.
    """
    E = E or expected_institutions()
    keys = ("name", "link", "state", "fte", "rate_fte", "rate_fte_smaller", "rule", "uncertain", "uncertain_own",
            "peer_type")
    return {
        "inst": {k: {f: rec[f] for f in keys} for k, rec in E.institutions.items()},
        "off": {k: tuple(v) for k, v in E.geo.items() if any(v)},
        "medical_on": {k: v for k, v in E.medical_on.items() if v},
        "shared_in_on": {k: v for k, v in E.shared_in_on.items() if v},
        "shared_out_on": {k: v for k, v in E.shared_out_on.items() if v},
        "count_all": {k: v for k, v in E.counts.items() if v},
        "campus_on_res": {k: tuple(v) for k, v in E.campus_geo.items() if any(v)},
    }


def rate_listed(rec: dict) -> bool:
    """Whether an institution-year's rate's denominator (on-campus FTE, pooled included) is at least MIN_FTE_FOR_RATE."""
    return rec["rate_fte"] is not None and rec["rate_fte"] >= MIN_FTE_FOR_RATE


def single_year_status(rec: dict, y: int) -> str:
    """
    Why an institution-year has no single-year rate, first that applies:
    "scope" (link campus not in US_STATES), "size" (denominator under
    MIN_FTE_FOR_RATE or none), "excluded" (a rule), "skippedYear" (2020);
    "" when it has one.
    """
    if rec["state"] not in US_STATES:
        return "scope"
    if not rate_listed(rec):
        return "size"
    if rec["rule"] is not None:
        return "excluded"
    if y == 2020:
        return "skippedYear"
    return ""


def audit_institution_rates(verbose: bool = False) -> AuditResult:
    """
    CHECK 10: The institution figures rates are made of.

    From expected_institutions (computed without 04's or 05's code), every
    rankings/*.json file must list in "campuses" exactly its preset's
    counting campus-years (name, state, institution FTE, number of campuses
    in the United States); 04's institution tables (aggs/
    agg_institution_year.parquet and agg_institution_year_offense.parquet)
    must hold exactly the expected institution-years and figures (link
    campus, name, state, campuses, campuses abroad, FTE, online share, the
    on-campus FTE estimates, the larger and the smaller, the rule, the
    denominators, uncertain and why, the peer type; per DOE offense the
    counts per geography, at listed medical-center campuses, shared and
    abroad); every school file's "institution" years the same campuses,
    online share, rateFte, fteUncertain (with reason), pooledWith, abroad
    and counts, with a rateExcludedReason exactly when a rule leaves the
    institution out; downloads/campus-years.csv the same denominator, rule,
    estimates, uncertain flag (empty exactly when there is no on-campus FTE)
    and reason, and medical-center campuses; and metadata.json's
    rateStats.institutionYears the numbers counted here. Check 12 checks the
    rates themselves and the school files' rated, notRated and flags.
    """
    result = AuditResult("Institution Rates")
    print("\nCHECK 10: Institution Rates")

    try:
        result.details["what_it_checks"] = (
            "Without 04's or 05's code, from the facts without shadow blocks, the reported campus-years, "
            "dim_institution, dim_enrollment's FTE and online share, NCES's raw headcounts (DRVEF 2021 on, EF A "
            "before), etl/reference/medical_campuses.csv, etl/reference/campuses_abroad.csv, "
            "etl/reference/shared_campus_overrides.csv and the raw IPEDS HD files: the campus-years that count, the institutions (base UNITIDs) each year, counts over their "
            "counting campuses in the United States (a campus DOE lists without a state, or on the reference list "
            "of campuses abroad, is counted apart), per geography (residence halls included), link campus, FTE, "
            f"online share (in {', '.join(str(y) for y in sorted(ONLINE_SHARE_YEAR))} that of the fall "
            "ONLINE_SHARE_YEAR names when NCES has one), the two on-campus FTE estimates (proportional, and part "
            "time first, by level with the year's own share) in whole-number arithmetic, on-campus FTE = the "
            "larger rounded half up, the smaller one, uncertain when they differ by more than "
            f"{ONLINE_UNCERTAIN_RATIO[0]}:{ONLINE_UNCERTAIN_RATIO[1]} or the headcounts do not add up (own, or "
            f"only through a pooled institution); the rules that leave an institution-year out (HD HOSPITAL = "
            f"{HOSPITAL_CODE}, a Carnegie special-focus medical code, the reference list, a campus under two IDs, "
            "a merger family; the first one published), pooled institutions and both denominators, the Carnegie "
            "Size & Setting peer type, and the on-campus figures at listed medical-center campuses (less "
            "residence halls) and at shared campuses (copies identical to another institution's campus, and the "
            "campuses of the reviewed override list, whose figures are in the counts and in none of the rates). "
            "Every rankings/*.json file must list exactly its preset's "
            "counting campuses; 04's institution tables, every school file's institution years, "
            "downloads/campus-years.csv and metadata.json's rateStats.institutionYears must match.")
        E = expected_institutions()
        institutions, counts = E.institutions, E.counts
        problems = []

        def problem(text):
            problems.append(text)

        codes = sorted({code for (_y, _b, code) in counts} | {code for (_y, _b, code) in E.abroad})
        files_checked = zero_campus_rows = 0
        for ranking_file in sorted((JSON_DIR / "rankings").glob("*.json")):
            data = json.loads(ranking_file.read_text(encoding="utf-8"))
            preset, year = data.get("preset"), data.get("year")
            files_checked += 1

            # The campuses table: every campus-year of the preset that counts, incidents or not
            def campus_in_preset(u, rec):
                if preset == "national":
                    return rec["state"] in US_STATES
                if preset == "ivy":
                    return u in IVY_LEAGUE
                return rec["state"] == preset

            want_campuses = {u: rec for (y, u), rec in E.campus_years.items() if y == year and campus_in_preset(u, rec)}
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

        # 04's institution tables
        table = read_curated("aggs/agg_institution_year.parquet", "04_create_aggregates.py")
        table_rows = 0
        got_keys = set()
        for r in table.to_dict("records"):
            key = (int(r["year"]), int(r["base_unitid"]))
            got_keys.add(key)
            rec = institutions.get(key)
            table_rows += 1
            if rec is None:
                problem(f"agg_institution_year: {key} is not an expected institution-year")
                break

            def opt(v):
                return None if v is None or pd.isna(v) else v
            got = {"name": r["institution_name"], "link": int(r["link_unitid"]), "state": opt(r["state"]),
                   "campuses": int(r["campuses"]), "abroad": int(r["abroad_campuses"]),
                   "fte": opt(r["fte"]), "online": opt(r["online_pct"]), "online_year": opt(r["online_year"]),
                   "est_a": opt(r["fte_share"]), "est_b": opt(r["fte_part_time_first"]),
                   "oncampus": opt(r["oncampus_fte"]), "oncampus_smaller": opt(r["oncampus_fte_smaller"]),
                   "rule": opt(r["rate_rule"]), "rate_fte": opt(r["rate_fte"]),
                   "rate_fte_smaller": opt(r["rate_fte_smaller"]), "uncertain": bool(r["online_uncertain"]),
                   "uncertain_own": bool(r["online_uncertain_own"]), "peer_type": r["peer_type"]}
            got = {k: (int(v) if isinstance(v, (int, np.integer)) and not isinstance(v, bool) else v)
                   for k, v in got.items()}
            want = {k: rec[k] for k in got}
            if got != want:
                diff = {k: (got[k], want[k]) for k in got if got[k] != want[k]}
                problem(f"agg_institution_year: {key} differs (found, expected): {diff}")
                break
        if got_keys != set(institutions):
            problem(f"agg_institution_year has {len(got_keys):,} institution-years, expected {len(institutions):,}")
        offense = read_curated("aggs/agg_institution_year_offense.parquet", "04_create_aggregates.py")
        want_off = {}
        for (y, b, o), v in E.geo.items():
            want_off.setdefault((y, b, o), {})["geo"] = tuple(v)
        for name_, source in (("medical_on", E.medical_on), ("shared_in_on", E.shared_in_on),
                              ("shared_out_on", E.shared_out_on), ("override_count", E.override_count)):
            for k, v in source.items():
                want_off.setdefault(k, {})[name_] = v
        offense_rows = 0
        seen = set()
        for r in offense.to_dict("records"):
            offense_rows += 1
            y, b, o = int(r["year"]), int(r["base_unitid"]), r["offense"]
            code = o.lower().replace(" ", "_")
            seen.add((y, b, o))
            w = want_off.get((y, b, o), {})
            want = {"geo": w.get("geo", (0, 0, 0, 0)), "count": counts.get((y, b, code), 0),
                    "medical_on": w.get("medical_on", 0), "shared_in_on": w.get("shared_in_on", 0),
                    "shared_out_on": w.get("shared_out_on", 0), "override_count": w.get("override_count", 0),
                    "shared_in": E.shared_in.get((y, b, code), 0),
                    "shared_out": E.shared_out.get((y, b, code), 0), "abroad_count": E.abroad.get((y, b, code), 0)}
            got = {"geo": (int(r["count_on"]), int(r["count_res"]), int(r["count_non"]), int(r["count_pub"])),
                   **{k: int(r[k]) for k in want if k != "geo"}}
            if got != want:
                diff = {k: (got[k], want[k]) for k in got if got[k] != want[k]}
                problem(f"agg_institution_year_offense: {y} {b} {o} differs (found, expected): {diff}")
                break
        # Every institution-year-offense with a figure above 0 has its row
        name_of = {o.lower().replace(" ", "_"): o for o in offense["offense"].unique()}
        name_of.update({o.lower().replace(" ", "_"): o for (_y, _b, o) in E.geo})
        expected_rows = {k for k, w in want_off.items() if any(w.get("geo", ())) or any(
            v for n, v in w.items() if n != "geo")}
        for source in (E.abroad, E.shared_in, E.shared_out):
            expected_rows |= {(y, b, name_of[code]) for (y, b, code), v in source.items() if v and code in name_of}
        if expected_rows != seen:
            diff = sorted(expected_rows ^ seen, key=str)
            problem(f"agg_institution_year_offense has {len(seen):,} rows, expected {len(expected_rows):,} "
                    f"(first difference: {diff[0]})")

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
                for k in [code] + summary_of(t["offense"], fam, SUMMARY_FAMILIES):
                    own.setdefault(int(t["year"]), {})
                    own[int(t["year"])][k] = own[int(t["year"])].get(k, 0) + int(t["count"])
            b = unitid // 1000
            want = {}
            for y in years:
                rec = institutions.get((y, b))
                if rec is None:
                    continue
                c = {code: counts[(y, b, code)] for code in codes if counts.get((y, b, code), 0) > 0}
                w = {"campuses": rec["campuses"], "online": rec["online"], "counts": c}
                if y in ONLINE_SHARE_YEAR and rec["online"] is not None:
                    w["onlineYear"] = rec["online_year"]
                if rec["rate_fte"] is not None:
                    w["rateFte"] = rec["rate_fte"]
                if rec["uncertain"]:
                    w["fteUncertain"] = {"share": rec["est_a"], "partTimeFirst": rec["est_b"],
                                         "reason": "own" if rec["uncertain_own"] else "pooled"}
                if rec["pooled"]:
                    w["pooledWith"] = [[s, rec["pooled_fte"][s]] for s in rec["pooled"]]
                if rec["abroad"]:
                    w["abroad"] = {"campuses": rec["abroad"],
                                   "counts": {code: E.abroad[(y, b, code)] for code in codes
                                              if E.abroad.get((y, b, code), 0) > 0}}
                want[str(y)] = w
            got = (school.get("institution") or {}).get("byYear") or {}
            if want and (school.get("institution") or {}).get("id") != b:
                problem(f"schools/{unitid}.json: institution id {(school.get('institution') or {}).get('id')}, "
                        f"expected {b}")
            if set(got) != set(want):
                problem(f"schools/{unitid}.json: institution years {sorted(got)}, expected {sorted(want)}")
                continue
            for y, w in want.items():
                g = dict(got[y])
                if ("rateExcludedReason" in g) != (institutions[(int(y), b)]["rule"] is not None):
                    problem(f"schools/{unitid}.json: institution {y} rateExcludedReason "
                            f"{'present' if 'rateExcludedReason' in g else 'missing'}, expected the opposite")
                    break
                for k in ("rateExcludedReason", "rated", "notRated", "flags"):  # check 12: rated, notRated, flags
                    g.pop(k, None)
                if "pooledWith" in g:
                    g["pooledWith"] = sorted([p.get("id"), p.get("fte")] for p in g["pooledWith"])
                if "counts" not in g:
                    g["counts"] = {k: v for k, v in own.get(int(y), {}).items() if v > 0}
                if g != w:
                    problem(f"schools/{unitid}.json: institution {y} is {got[y]}, expected {w}")
                    break
            profiles_checked += 1

        # downloads/campus-years.csv: the institution's denominator, rule, estimates and flags, and medical campuses
        csv_path = JSON_DIR / "downloads" / "campus-years.csv"
        csv_rows = 0
        if not csv_path.is_file():
            problem("downloads/campus-years.csv is missing")
        else:
            cy = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            cols = ["year", "unitid", "institution_rate_fte", "institution_rate_rule",
                    "institution_oncampus_fte_proportional", "institution_oncampus_fte_part_time_first",
                    "institution_oncampus_fte_uncertain", "institution_oncampus_fte_uncertain_reason",
                    "medical_center_campus"]
            missing_cols = [c for c in cols if c not in cy.columns]
            if missing_cols:
                problem(f"downloads/campus-years.csv has no column {missing_cols[0]}")
            else:
                for row in cy[cols].itertuples(index=False):
                    y, u = int(row[0]), int(row[1])
                    rec = institutions.get((y, u // 1000))
                    if rec is None or rec["est_a"] is None:
                        want_row = ("" if rec is None or rec["rate_fte"] is None else str(rec["rate_fte"]),
                                    "" if rec is None else rec["rule"] or "", "", "", "", "")
                    else:
                        want_row = ("" if rec["rate_fte"] is None else str(rec["rate_fte"]), rec["rule"] or "",
                                    str(rec["est_a"]), "" if rec["est_b"] is None else str(rec["est_b"]),
                                    str(rec["uncertain"]),
                                    ("own" if rec["uncertain_own"] else "pooled") if rec["uncertain"] else "")
                    got_row = tuple(row[2:8])
                    medical_flag = str((u, y) in E.medical_years)
                    csv_rows += 1
                    if got_row != want_row or row[8] != medical_flag:
                        problem(f"downloads/campus-years.csv: {y} {u} has {tuple(row[2:])}, expected "
                                f"{want_row + (medical_flag,)}")
                        break

        # metadata.json rateStats.institutionYears
        order = ("hospital", "medical", "listed", "merger", "family")
        stats = {"rules": {r: {"institutionYears": 0, "withFte": 0} for r in order},
                 "pooled": {"merger": 0, "shared": 0}, "byYear": {},
                 "onlineOwnYear": {str(y): {"all": 0, "withFte": 0} for y in sorted(ONLINE_SHARE_YEAR)}}
        for (y, b), rec in sorted(institutions.items()):
            if y not in DATA_YEARS:
                continue
            big = rate_listed(rec)
            with_fte = big and rec["state"] in US_STATES
            if rec["rule"] is not None:
                stats["rules"][rec["rule"]]["institutionYears"] += 1
                stats["rules"][rec["rule"]]["withFte"] += int(with_fte)
            for p in rec["pooled_rules"]:
                stats["pooled"][p] += 1
            row = stats["byYear"].setdefault(str(y), {"withFte": 0, "excluded": 0, "rated": 0, "fteUncertain": 0,
                                                      "fteUncertainPooledOnly": 0, "abroad": 0,
                                                      "outsideScopeWithFte": 0})
            row["outsideScopeWithFte"] += int(big and not with_fte)
            if with_fte:
                row["withFte"] += 1
                row["excluded"] += int(rec["rule"] is not None)
                row["rated"] += int(single_year_status(rec, y) == "")
                row["fteUncertain"] += int(rec["rule"] is None and rec["uncertain"])
                row["fteUncertainPooledOnly"] += int(rec["rule"] is None and rec["uncertain"]
                                                     and not rec["uncertain_own"])
                row["abroad"] += int(rec["abroad"] > 0)
            if y in ONLINE_SHARE_YEAR and rec["online_year"] == y:
                stats["onlineOwnYear"][str(y)]["all"] += 1
                stats["onlineOwnYear"][str(y)]["withFte"] += int(with_fte)
        metadata = json.loads((JSON_DIR / "metadata.json").read_text(encoding="utf-8"))
        published_stats = (metadata.get("rateStats") or {}).get("institutionYears")
        if published_stats != stats:
            problem(f"metadata.json rateStats.institutionYears is {json.dumps(published_stats)[:300]}, expected "
                    f"{json.dumps(stats)[:300]}")

        by_year = []
        for y in sorted({y for (y, _b) in institutions}):
            listed = [(b, rec) for (yy, b), rec in institutions.items() if yy == y]
            in_rates = [(b, r) for b, r in listed if rate_listed(r)]
            row = {
                "year": y,
                "institutions": len(listed),
                "with_more_than_one_campus": sum(1 for _b, r in listed if r["campuses"] > 1),
                "rate_listed": len(in_rates),
                "single_year_rate": sum(1 for _b, r in listed if single_year_status(r, y) == ""),
                "left_out_fte": sum(1 for _b, r in listed if r["rule"] is None
                                    and (r["rate_fte"] is None or r["rate_fte"] < MIN_FTE_FOR_RATE)),
                "no_online_figure": sum(1 for _b, r in listed if r["online"] is None and r["fte"] is not None),
                "online_share_own_year_used": (sum(1 for _b, r in listed if r["online_year"] == y)
                                               if y in ONLINE_SHARE_YEAR else None),
                "fte_uncertain_no_rule": sum(1 for _b, r in in_rates if r["uncertain"] and r["rule"] is None),
                "fte_uncertain_pooled_only": sum(1 for _b, r in in_rates if r["uncertain"] and not r["uncertain_own"]
                                                 and r["rule"] is None),
                "no_second_estimate": sum(1 for _b, r in in_rates if r["uncertain"] and r["rule"] is None
                                          and r["rate_fte_smaller"] is None),
                "with_campus_abroad": sum(1 for _b, r in in_rates if r["abroad"]),
                "abroad_criminal_removed": sum(E.abroad.get((y, b, "criminal"), 0) for b, r in in_rates),
                "pooled_merger": sum(1 for _b, r in listed if "merger" in r["pooled_rules"]),
                "pooled_shared": sum(1 for _b, r in listed if "shared" in r["pooled_rules"]),
                "medical_on_campus": sum(v for (yy, _b, _o), v in E.medical_on.items() if yy == y),
            }
            for rule in order:
                hit = [r for _b, r in listed if rule in r["rules"]]
                row[f"rule_{rule}"] = len(hit)
                row[f"rule_{rule}_1000"] = sum(1 for r in hit if (r["oncampus"] or 0) >= MIN_FTE_FOR_RATE)
                row[f"rule_{rule}_first"] = sum(1 for _b, r in listed if r["rule"] == rule)
            by_year.append(row)
        result.details["by_year"] = by_year
        result.details["ranking_files_checked"] = files_checked
        result.details["campus_rows_with_0_all_files"] = zero_campus_rows
        result.details["institution_table_rows_checked"] = table_rows
        result.details["institution_offense_rows_checked"] = offense_rows
        result.details["school_files_checked"] = profiles_checked
        result.details["campus_years_csv_rows_checked"] = csv_rows
        result.details["problems"] = len(problems)

        print(f"    {'Year':<6}{'Inst.':>7}{'Listed':>8}{'Single':>8}{'Uncert':>8}{'Abroad':>8}{'PoolM':>7}"
              f"{'PoolS':>7}" + "".join(f"{n[:8]:>13}" for n in order))
        for r in by_year:
            print(f"    {r['year']:<6}{r['institutions']:>7,}{r['rate_listed']:>8,}{r['single_year_rate']:>8,}"
                  f"{r['fte_uncertain_no_rule']:>8,}{r['with_campus_abroad']:>8,}{r['pooled_merger']:>7,}"
                  f"{r['pooled_shared']:>7,}"
                  + "".join("{:>13}".format(f"{r['rule_' + n + '_first']:,} ({r['rule_' + n]:,})") for n in order))
        print(f"  Ranking files: {files_checked:,}; institution table rows: {table_rows:,} and {offense_rows:,}; "
              f"school files: {profiles_checked:,}; campus-years.csv rows: {csv_rows:,}")
        print(f"  Problems: {len(problems)}")

        if problems:
            result.failed(f"{len(problems)} problems with institution figures (first: {problems[0]}). "
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
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")

    return result


# =============================================================================
# The rule constants, written out from the design (v4 spec sections 1-3, as
# amended: state lists from 2 members, single-year rates kept for the school
# page). Changing one here, in config.py or in metadata.json makes check 12 fail.
# =============================================================================

VIOLENT = ("Murder", "Rape", "Robbery", "Aggravated Assault")
SPEC = {
    "min_fte": 1000,
    "window_years": 3,
    "skip_years": (2020,),
    "first_year": 2015,
    "windows_through_2024": ((2015, 2017), (2016, 2018), (2017, 2019), (2021, 2023), (2022, 2024)),
    "codes": {
        "violent": VIOLENT,
        "criminal_xmvt": ("Murder", "Negligent Manslaughter", "Rape", "Fondling", "Incest", "Statutory Rape",
                          "Robbery", "Aggravated Assault", "Burglary", "Arson"),
        "burglary": ("Burglary",),
        "rape": ("Rape",),
        "fondling": ("Fondling",),
        "robbery": ("Robbery",),
        "aggravated_assault": ("Aggravated Assault",),
        "stalking": ("Stalking",),
        "dating_violence": ("Dating Violence",),
        "domestic_violence": ("Domestic Violence",),
    },
    "c": {"violent": 0.354, "criminal_xmvt": 0.497, "burglary": 0.665, "rape": 0.295, "aggravated_assault": 0.585},
    "c_other": 0.522,
    "power": 1.5,
    "ramp_start": 10, "ramp_end": 20, "ramp_cap": 2,
    "ci_level": 0.95,
    "medical_share": (1, 4),
    "shared_share": (1, 20),
    "list_codes": ("violent", "criminal_xmvt", "burglary"),
    "list_min_expected": 20,
    "list_alpha": 0.05,
    "state_min_members": 2,
    "state_display_min": 5,
    "composition": {"violent": VIOLENT, "criminal_xmvt": ("Motor Vehicle Theft",)},
    "flag_offenses": ("Aggravated Assault", "Burglary", "Dating Violence", "Domestic Violence", "Fondling",
                      "Motor Vehicle Theft", "Rape", "Robbery", "Stalking"),
    "flag_geos": ("On-campus", "Non-campus", "Public property"),
    "flag_min_count": 10, "flag_min_other_years": 3, "flag_p": 0.001, "flag_c": 0.52, "flag_min_mean": 0.5,
    "count_flag_min_count": 20, "count_flag_factor": 3, "count_flag_percentile": 99,
    "medical_screen_share": (1, 10), "medical_screen_min_count": 5,
    "calibration": {"codes": ("violent", "criminal_xmvt", "burglary", "rape", "aggravated_assault", "robbery",
                              "fondling", "stalking"),
                    "periods": ((2015, 2019), "latest"), "latestYears": 3, "simulations": 600, "seed": 11,
                    "bands": (2, 5, 10, 20), "tolerance": 0.02, "bandToleranceBelow": 0.03,
                    "bandToleranceAbove": 0.05, "bandMinUnits": 100},
    "size_setting_fields": ("C21SZSET", "C18SZSET", "C15SZSET"),
    "peer_size_setting": {"two_year": (1, 2, 3, 4, 5), "nonresidential": (6, 9, 12, 15),
                          "residential": (7, 10, 13, 16), "highly_residential": (8, 11, 14, 17), "other": ()},
    # Section 3.3 test vectors: (c, N, phi to 6 decimals, count interval to 4 decimals), T = 3
    "test_counts": ((0.354, 0, 1.000000, 0.0000, 3.6889), (0.354, 1, 1.204382, 0.0132, 6.3521),
                    (0.354, 5, 1.457012, 1.1843, 13.7113), (0.354, 20, 1.914024, 9.7732, 36.3132),
                    (0.354, 45, 3.056554, 25.0292, 74.5614), (0.354, 60, 4.166272, 33.1237, 99.9595),
                    (0.354, 139, 5.819256, 88.9550, 207.0136), (0.354, 1000, 13.926252, 782.1644, 1259.7230),
                    (0.497, 20, 2.283248, 9.0290, 38.2865), (0.497, 139, 7.766018, 82.2421, 219.9591),
                    (0.665, 20, 2.717023, 8.2662, 40.5081), (0.665, 266, 13.523676, 161.7265, 412.2858),
                    (0.522, 5, 1.673899, 1.0263, 14.6429), (0.522, 60, 5.668910, 29.4782, 108.5388)),
    # (N, F, c, rate, lo, hi)
    "test_rates": ((20, 30000, 0.354, 6.67, 3.26, 12.10), (139, 44830, 0.354, 31.01, 19.84, 46.18),
                   (82, 30483, 0.354, 26.90, 15.79, 42.82), (0, 6751, 0.665, 0.00, 0.00, 5.46),
                   (188, 20282, 0.497, 92.69, 57.52, 141.41)),
    # list example: c 0.354, T 3, members (N, F, position, rankLo, rankHi)
    "test_list": {"c": 0.354, "years": 3, "zc": 2.497705,
                  "members": ((139, 44830, 1, 1, 2), (82, 30483, 2, 1, 2), (20, 30000, 3, 3, 5),
                              (60, 90000, 3, 3, 5), (30, 100000, 5, 3, 5)),
                  "z": (("A", "B", 0.4478), ("A", "C", 3.3169), ("B", "C", 3.2472), ("C", "D", 0.0),
                        ("C", "E", 2.0556), ("D", "E", 2.0995))},
    "critical_z": {5: 2.4977, 146: 3.5791, 208: 3.6711, 531: 3.9047},
}

GEO_IDX = {"On-campus": 0, "Residence halls": 1, "Non-campus": 2, "Public property": 3}


def ocode(offense: str) -> str:
    """DOE offense name as a code: lowercase with underscores."""
    return offense.lower().replace(" ", "_")


def c_of(code, spec):
    return spec["c"].get(code, spec["c_other"])


def all_windows(years, spec):
    """Every run of window_years consecutive years of `years` without a skipped year."""
    have = set(years)
    out = []
    for y in sorted(have):
        span = range(y, y + spec["window_years"])
        if all(z in have and z not in spec["skip_years"] for z in span):
            out.append((y, y + spec["window_years"] - 1))
    return out


# =============================================================================
# Numerics: regularized incomplete gamma, its inverse, normal quantile
# =============================================================================

_LGAMMA = np.frompyfunc(math.lgamma, 1, 1)


def lgamma_v(a):
    return np.asarray(_LGAMMA(np.asarray(a, float)), float)


def gamma_p(a, x, lga=None):
    """Regularized lower incomplete gamma P(a, x), elementwise: the power series for x < a + 1, else
    1 - Q(a, x) from the continued fraction (modified Lentz). lga: lgamma(a), when already known."""
    a = np.asarray(a, float)
    x = np.asarray(x, float)
    a, x = np.broadcast_arrays(a, x)
    if lga is None:
        lga = lgamma_v(a)
    lga = np.broadcast_to(np.asarray(lga, float), a.shape)
    out = np.zeros(a.shape)
    pos = x > 0
    ser = pos & (x < a + 1.0)
    if ser.any():
        aa, xx = a[ser], x[ser]
        term = 1.0 / aa
        tot = term.copy()
        ap = aa.copy()
        for _ in range(200000):
            ap = ap + 1.0
            term = term * (xx / ap)
            tot = tot + term
            if np.all(term <= tot * 1e-17):
                break
        out[ser] = np.exp(aa * np.log(xx) - xx - lga[ser]) * tot
    cf = pos & ~ser
    if cf.any():
        aa, xx = a[cf], x[cf]
        tiny = 1e-300
        b = xx + 1.0 - aa
        c = np.full_like(b, 1.0 / tiny)
        d = 1.0 / b
        h = d.copy()
        for i in range(1, 200000):
            an = -i * (i - aa)
            b = b + 2.0
            d = an * d + b
            d = np.where(np.abs(d) < tiny, tiny, d)
            c = b + an / c
            c = np.where(np.abs(c) < tiny, tiny, c)
            d = 1.0 / d
            delta = d * c
            h = h * delta
            if np.all(np.abs(delta - 1.0) <= 4e-16):
                break
        out[cf] = 1.0 - np.exp(aa * np.log(xx) - xx - lga[cf]) * h
    return out


def gamma_inv(a, q):
    """Quantile of the gamma distribution (shape a, scale 1) at probability q, elementwise: the smallest
    double x with P(a, x) >= q, by bisection until the bracket is two adjacent doubles."""
    a = np.asarray(a, float)
    lga = lgamma_v(a)
    lo = np.zeros_like(a)
    hi = a + 10.0 * np.sqrt(a) + 10.0
    for _ in range(200):
        low = gamma_p(a, hi, lga) < q
        if not low.any():
            break
        hi = np.where(low, hi * 2.0, hi)
    for _ in range(5000):
        mid = 0.5 * (lo + hi)
        active = (mid > lo) & (mid < hi)
        if not active.any():
            break
        up = gamma_p(a, mid, lga) >= q
        hi = np.where(active & up, mid, hi)
        lo = np.where(active & ~up, mid, lo)
    return hi


def normal_upper_quantile(p: float) -> float:
    """z with P(Z > z) = p for a standard normal Z, by bisection on 0.5 erfc(z / sqrt 2)."""
    lo, hi = -40.0, 40.0
    for _ in range(3000):
        mid = 0.5 * (lo + hi)
        if mid <= lo or mid >= hi:
            break
        if 0.5 * math.erfc(mid / math.sqrt(2.0)) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ci_quantiles(spec):
    al = (Fraction(1) - Fraction(str(spec["ci_level"]))) / 2
    return float(al), float(1 - al)


def critical_z(n, spec):
    """Bonferroni critical value of a list of n: Phi^-1(1 - alpha / (2 (n - 1)))."""
    return normal_upper_quantile(float(Fraction(str(spec["list_alpha"])) / (2 * (n - 1))))


def ramp(m, spec):
    return np.minimum(spec["ramp_cap"], np.maximum(1.0, np.asarray(m, float) / spec["ramp_start"]))


def count_intervals(N, c, T, spec):
    """R5/R6 for window totals N (array) over T years: phi(N) = 1 + c g(N/T) sqrt(N/T), m = N / phi,
    lower = phi GammaInv(alpha/2; m) (0 for N = 0), upper = phi GammaInv(1 - alpha/2; m + 1)."""
    N = np.asarray(N, float)
    m = N / T
    phi = 1.0 + c * ramp(m, spec) * np.sqrt(m)
    shape = N / phi
    q_lo, q_hi = ci_quantiles(spec)
    lower = np.zeros_like(N)
    pos = N > 0
    if pos.any():
        lower[pos] = phi[pos] * gamma_inv(shape[pos], q_lo)
    upper = phi * gamma_inv(shape + 1.0, q_hi)
    return phi, lower, upper


class IntervalBank:
    """Count intervals asked for by (N, c, T), computed together (count_intervals) and kept."""
    def __init__(self, spec):
        self.spec = spec
        self.want = defaultdict(set)
        self.val = {}

    def need(self, N, c, T):
        key = (float(N), c, T)
        if key not in self.val:
            self.want[(c, T)].add(float(N))

    def compute(self):
        for (c, T), ns in self.want.items():
            arr = np.array(sorted(ns))
            phi, lo, hi = count_intervals(arr, c, T, self.spec)
            for n, p, l, h in zip(arr.tolist(), phi.tolist(), lo.tolist(), hi.tolist()):
                self.val[(n, c, T)] = (p, l, h)
        self.want = defaultdict(set)

    def get(self, N, c, T):
        key = (float(N), c, T)
        if key not in self.val:
            self.need(N, c, T)
            self.compute()
        return self.val[key]


def rate2(N: int, F: int) -> float:
    """R12: floor((2 N 10^6 + F) / (2 F)) / 100."""
    return ((2 * N * 10 ** 6 + F) // (2 * F)) / 100


def bound2(x: float) -> float:
    """R12: floor(x 100 + 0.5) / 100 from a double."""
    return math.floor(x * 100 + 0.5) / 100


def half_up_dp(x: Fraction, dp: int) -> float:
    s = 10 ** dp
    return math.floor(x * s + Fraction(1, 2)) / s


def verdict_of(lower: float, upper: float, F, ref: Fraction) -> str:
    """R7a with unrounded bounds: above when lower / F > ref, below when upper / F < ref (exact)."""
    t = ref * F
    if Fraction(lower) > t:
        return "above"
    if Fraction(upper) < t:
        return "below"
    return "nd"


def nb_upper_tail(x: int, mu: float, c: float) -> float:
    """P(Y >= x) for a negative binomial Y with mean mu and variance mu + c mu^1.5 (size k = mu^0.5 / c),
    summed upward from x."""
    k = math.sqrt(mu) / c
    r = mu / (k + mu)
    logp = (math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1) + k * math.log(k / (k + mu))
            + x * math.log(r))
    t = math.exp(logp)
    s = t
    y = x
    for _ in range(10 ** 7):
        ratio = (y + k) / (y + 1) * r
        t *= ratio
        y += 1
        s += t
        if ratio < 1 and t <= s * 1e-18:
            break
    return s


def percentile_linear(values_sorted, pct) -> Fraction:
    """numpy's default (linear) percentile, exactly, of sorted Fractions."""
    n = len(values_sorted)
    h = (n - 1) * Fraction(pct, 100)
    i = math.floor(h)
    g = h - i
    if i + 1 >= n:
        return values_sorted[i]
    return values_sorted[i] + g * (values_sorted[i + 1] - values_sorted[i])


def z_matrix(N, F, c, T, spec):
    """R9 pairwise z_ij (0 where the variance is 0)."""
    N = np.asarray(N, float)
    F = np.asarray(F, float)
    r = N / F
    rbar = (N[:, None] + N[None, :]) / (F[:, None] + F[None, :])

    def V0(mu):
        m = mu / T
        return T * (m + c * ramp(m, spec) * m ** 1.5)
    var = V0(rbar * F[:, None]) / F[:, None] ** 2 + V0(rbar * F[None, :]) / F[None, :] ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(var > 0, (r[:, None] - r[None, :]) / np.sqrt(np.where(var > 0, var, 1.0)), 0.0)
    return z


def rank_list(members, c, T, spec):
    """members: list of (N, F) in list order (rate descending). Returns positions, rankLo, rankHi, zc, z."""
    n = len(members)
    pos = []
    for i, (Ni, Fi) in enumerate(members):
        if i > 0 and Fraction(Ni, Fi) == Fraction(*members[i - 1]):
            pos.append(pos[-1])
        else:
            pos.append(i + 1)
    if n < 2:
        return pos, [1] * n, [1] * n, None, None
    zc = critical_z(n, spec)
    z = z_matrix([m[0] for m in members], [m[1] for m in members], c, T, spec)
    sig = z > zc
    lo = 1 + sig.sum(axis=0)
    hi = n - sig.sum(axis=1)
    rlo = [int(min(lo[i], pos[i])) for i in range(n)]
    rhi = [int(max(hi[i], pos[i])) for i in range(n)]
    return pos, rlo, rhi, zc, z


# =============================================================================
# Inputs and published data
# =============================================================================

_CACHE = {}


def default_inputs():
    if "inputs" not in _CACHE:
        _CACHE["inputs"] = rate_inputs()
    return _CACHE["inputs"]


def default_data():
    if "data" not in _CACHE:
        _CACHE["data"] = load_published(JSON_DIR)
    return _CACHE["data"]


def load_published(json_dir):
    """The published files the checks read: rates/*.json, rates/institutions/*.json, rates/flags.json,
    metadata.json, rankings/*.json (rankings only) and schools/*.json (institution only)."""
    from concurrent.futures import ThreadPoolExecutor
    d = Path(json_dir)

    def read_all(paths):
        # file reads in threads (they wait on the disk), parsing in this thread
        with ThreadPoolExecutor(16) as ex:
            blobs = list(ex.map(lambda p: p.read_bytes(), paths))
        return [(p, json.loads(b)) for p, b in zip(paths, blobs)]
    out = {"json_dir": str(d), "metadata": json.loads((d / "metadata.json").read_bytes()), "windows": {},
           "institutions": {}, "flags": None, "rankings": {}, "schools": {}}
    for p, obj in read_all(sorted((d / "rates").glob("*.json"))):
        if p.name == "flags.json":
            out["flags"] = obj
        else:
            out["windows"][p.stem] = obj
    for p, obj in read_all(list((d / "rates" / "institutions").glob("*.json"))):
        out["institutions"][p.stem] = obj
    for p, r in read_all(list((d / "rankings").glob("*.json"))):
        out["rankings"][p.stem] = {"preset": r.get("preset"), "year": r.get("year"), "rankings": r.get("rankings")}
    for p, obj in read_all(list((d / "schools").glob("*.json"))):
        out["schools"][p.stem] = obj.get("institution")
    return out


def single_year_reason(rec, y, spec, us_states):
    """Why an institution-year has no single-year rate (None: it has one)."""
    if rec["state"] not in us_states:
        return "scope"
    if rec["rate_fte"] is None or rec["rate_fte"] < spec["min_fte"]:
        return "size"
    if rec["rule"] is not None:
        return "excluded"
    if y in spec["skip_years"]:
        return "skippedYear"
    return None


# =============================================================================
# Re-derivation of everything published
# =============================================================================

def derive(inputs, spec, cfg, bank):
    """Everything the rules publish, from the inputs alone."""
    us = set(cfg.US_STATES)
    inst = inputs["inst"]
    off = inputs["off"]
    codes = spec["codes"]
    code_of = defaultdict(list)
    for k, offs in codes.items():
        for o in offs:
            code_of[o].append(k)
    comp_off = set(o for v in spec["composition"].values() for o in v)

    years_by_base = defaultdict(list)
    for (y, b) in inst:
        years_by_base[b].append(y)
    for b in years_by_base:
        years_by_base[b].sort()
    data_years = sorted({y for (y, b) in inst})
    windows = all_windows(data_years, spec)

    # code sums per institution-year: on, non, pub, medical, sharedIn, sharedOut
    S = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    oncount = {}  # (y, b, offense) -> on
    for (y, b, o), (on, res, non, pub) in off.items():
        oncount[(y, b, o)] = on
        for k in code_of.get(o, ()):
            s = S[(y, b, k)]
            s[0] += on
            s[1] += non
            s[2] += pub
    for src, idx in (("medical_on", 3), ("shared_in_on", 4), ("shared_out_on", 5)):
        for (y, b, o), v in inputs[src].items():
            for k in code_of.get(o, ()):
                S[(y, b, k)][idx] += v
    ZERO = (0, 0, 0, 0, 0, 0)

    # ---------------------------------------------------------- unusual-year flags (R8)
    cells = defaultdict(dict)
    fo = set(spec["flag_offenses"])
    gi = [(g, GEO_IDX[g]) for g in spec["flag_geos"]]
    for (y, b, o), vals in off.items():
        if o in fo:
            for g, i in gi:
                if vals[i]:
                    cells[(b, o, g)][y] = vals[i]
    flags = defaultdict(list)
    for (b, o, g), byy in cells.items():
        if max(byy.values()) < spec["flag_min_count"]:
            continue
        yrs = [y for y in years_by_base[b] if spec["first_year"] <= y <= data_years[-1]]
        for y in yrs:
            cnt = byy.get(y, 0)
            if cnt < spec["flag_min_count"]:
                continue
            others = [byy.get(z, 0) for z in yrs if z != y]
            if len(others) < spec["flag_min_other_years"]:
                continue
            med = statistics.median(others)
            mu = max(spec["flag_min_mean"], med)
            if nb_upper_tail(cnt, float(mu), spec["flag_c"]) < spec["flag_p"]:
                usual = int(med) if med == int(med) else float(med)
                flags[b].append({"year": y, "offense": ocode(o), "geo": g, "count": cnt, "usual": usual})
    for b in flags:
        flags[b].sort(key=lambda f: (f["year"], f["offense"], f["geo"]))

    # ---------------------------------------------------------- window statuses
    status = {}
    rated = defaultdict(list)
    for b, ys in years_by_base.items():
        for (y0, y1) in windows:
            wy = list(range(y0, y1 + 1))
            have = [y for y in wy if (y, b) in inst]
            if not have:
                continue
            w = f"{y0}-{y1}"
            if len(have) < len(wy):
                status[(b, w)] = {"status": "missingYears", "years": have}
                continue
            recs = [inst[(y, b)] for y in wy]
            if recs[-1]["state"] not in us:
                status[(b, w)] = {"status": "scope"}
            elif any(r["rate_fte"] is None or r["rate_fte"] < spec["min_fte"] for r in recs):
                status[(b, w)] = {"status": "size", "fteByYear": {str(y): r["rate_fte"] for y, r in zip(wy, recs)}}
            elif any(r["rule"] is not None for r in recs):
                status[(b, w)] = {"status": "excluded",
                                  "rules": {str(y): r["rule"] for y, r in zip(wy, recs) if r["rule"] is not None}}
            else:
                st = {"status": "rated"}
                if any(r["uncertain"] for r in recs):
                    st["why"] = "online"
                st["fteByYear"] = {str(y): r["rate_fte"] for y, r in zip(wy, recs)}
                if "why" in st:
                    st["fteSmallerByYear"] = {str(y): r["rate_fte_smaller"] for y, r in zip(wy, recs)}
                status[(b, w)] = st
                rated[(y0, y1)].append(b)

    # ---------------------------------------------------------- window x code raw figures
    raw = {}
    for (y0, y1) in windows:
        wy = list(range(y0, y1 + 1))
        for k in codes:
            c = c_of(k, spec)
            for b in rated[(y0, y1)]:
                recs = [inst[(y, b)] for y in wy]
                sums = [S.get((y, b, k), ZERO) for y in wy]
                N = sum(s[0] for s in sums)
                F = sum(r["rate_fte"] for r in recs)
                Fs = None if any(r["rate_fte_smaller"] is None for r in recs) else sum(r["rate_fte_smaller"] for r in recs)
                med = sum(s[3] for s in sums)
                sI = sum(s[4] for s in sums)
                sO = sum(s[5] for s in sums)
                if any(r["uncertain"] for r in recs):
                    why = "online"
                elif N > 0 and spec["medical_share"][1] * med >= spec["medical_share"][0] * N:
                    why = "medical_campus"
                elif spec["shared_share"][1] * (sI + sO) > spec["shared_share"][0] * (N + sO):
                    why = "shared"
                else:
                    why = ""
                att = [f for f in flags.get(b, ()) if f["geo"] == "On-campus" and y0 <= f["year"] <= y1
                       and f["offense"] in {ocode(o) for o in codes[k]}]
                Nw = None
                if att:
                    Nw = max(Fraction(0), Fraction(N) - sum(Fraction(f["count"]) - Fraction(f["usual"]) for f in att))
                    bank.need(float(Nw), c, spec["window_years"])
                bank.need(N, c, spec["window_years"])
                comp = {}
                if k in spec["composition"]:
                    for o in spec["composition"][k]:
                        comp[ocode(o)] = sum(oncount.get((y, b, o), 0) for y in wy)
                raw[((y0, y1), k, b)] = {
                    "N": N, "non": sum(s[1] for s in sums), "pub": sum(s[2] for s in sums), "F": F, "Fs": Fs,
                    "med": med, "sI": sI, "sO": sO, "why": why, "flags": att, "Nw": Nw, "comp": comp,
                    "nByYear": {str(y): s[0] for y, s in zip(wy, sums)}, "rec": recs[-1], "recs": recs, "wy": wy}

    # ---------------------------------------------------------- single years (T = 1)
    single = {}
    for (y, b), rec in inst.items():
        reason = single_year_reason(rec, y, spec, us)
        if reason is None:
            for k in codes:
                bank.need(S.get((y, b, k), ZERO)[0], c_of(k, spec), 1)
        single[(y, b)] = reason
    bank.compute()

    # ---------------------------------------------------------- window files
    T = spec["window_years"]
    wfiles = {}
    natl_info = {}
    for (y0, y1) in windows:
        w = f"{y0}-{y1}"
        for k in codes:
            c = c_of(k, spec)
            rs = [(b, raw[((y0, y1), k, b)]) for b in rated[(y0, y1)]]
            pop = [(b, r) for b, r in rs if r["why"] in ("", "medical_campus", "shared")]
            natlN = sum(r["N"] for b, r in pop)
            natlF = sum(r["F"] for b, r in pop)
            r0 = Fraction(natlN, natlF) if natlF else Fraction(0)
            peerN, peerF, peerM = Counter(), Counter(), Counter()
            for b, r in pop:
                pt = r["rec"]["peer_type"]
                peerN[pt] += r["N"]
                peerF[pt] += r["F"]
                peerM[pt] += 1
            peer_ref = {pt: Fraction(peerN[pt], peerF[pt]) for pt in peerF if peerF[pt] > 0}
            peer = {pt: {"rate": half_up_dp(peer_ref[pt] * 10000, 2), "n": peerN[pt], "fteYears": peerF[pt],
                         "members": peerM[pt]} for pt in peer_ref}
            natl = half_up_dp(r0 * 10000, 2)
            entries = {}
            for b, r in rs:
                N, F, Fs = r["N"], r["F"], r["Fs"]
                phi, lower, upper = bank.get(N, c, T)
                rec = r["rec"]
                e = {"id": b, "unitid": rec["link"], "name": rec["name"], "state": rec["state"],
                     "peerType": rec["peer_type"], "n": N, "nNoncampus": r["non"], "nPublic": r["pub"],
                     "fteYears": F, "rate": rate2(N, F), "lo": bound2(lower / F * 10000.0),
                     "hi": bound2(upper / F * 10000.0), "E": half_up_dp(r0 * F, 1)}
                v, vL, vS, reason = dual_verdict(lower, upper, F, Fs, r0, r["why"] == "online")
                e["verdict"] = v
                if r["why"]:
                    e["why"] = r["why"]
                if r["why"] == "online":
                    e["verdictLargerFte"] = vL
                    if vS is not None:
                        e["verdictSmallerFte"] = vS
                    if reason:
                        e["undeterminedReason"] = reason
                    if Fs is not None:
                        e["fteYearsSmaller"] = Fs
                    e["fteUncertain"] = {str(y): ("own" if rr["uncertain_own"] else "pooled")
                                         for y, rr in zip(r["wy"], r["recs"]) if rr["uncertain"]}
                pref = peer_ref.get(rec["peer_type"])
                if pref is None:
                    e["peerVerdict"] = None
                else:
                    pv, pvL, pvS, _ = dual_verdict(lower, upper, F, Fs, pref, r["why"] == "online")
                    e["peerVerdict"] = pv
                    if r["why"] == "online":
                        e["peerVerdictLargerFte"] = pvL
                        if pvS is not None:
                            e["peerVerdictSmallerFte"] = pvS
                if r["med"] > 0:
                    e["medical"] = r["med"]
                if r["sI"] > 0:
                    e["sharedIn"] = r["sI"]
                if r["sO"] > 0:
                    e["sharedOut"] = r["sO"]
                if r["flags"]:
                    e["flags"] = [{"year": f["year"], "offense": f["offense"], "count": f["count"],
                                   "usual": f["usual"]} for f in r["flags"]]
                    _, lw, uw = bank.get(float(r["Nw"]), c, T)
                    vw, _, _, _ = dual_verdict(lw, uw, F, Fs, r0, r["why"] == "online")
                    if vw != v:
                        e["verdictWithoutFlagged"] = vw
                if k in spec["list_codes"]:
                    e["listed"] = False
                entries[b] = e
            order = sorted(entries, key=lambda b: (Fraction(-raw[((y0, y1), k, b)]["N"], raw[((y0, y1), k, b)]["F"]),
                                                   entries[b]["name"], b))
            header = {"window": [y0, y1], "code": k, "years": list(range(y0, y1 + 1)), "c": c, "natl": natl,
                      "natlN": natlN, "natlF": natlF, "peer": peer}
            if k in spec["composition"]:
                header["composition"] = {ocode(o): sum(r["comp"][ocode(o)] for b, r in pop)
                                         for o in spec["composition"][k]}
            lists = None
            if k in spec["list_codes"]:
                E_min = spec["list_min_expected"]
                members = [b for b in order if raw[((y0, y1), k, b)]["why"] == ""
                           and natlN * raw[((y0, y1), k, b)]["F"] >= E_min * natlF]
                mem = [(raw[((y0, y1), k, b)]["N"], raw[((y0, y1), k, b)]["F"]) for b in members]
                pos, rlo, rhi, zc, _z = rank_list(mem, c, T, spec)
                for i, b in enumerate(members):
                    e = entries[b]
                    e["listed"] = True
                    e["position"], e["rankLo"], e["rankHi"] = pos[i], rlo[i], rhi[i]
                by_state = defaultdict(list)
                for b in members:
                    by_state[entries[b]["state"]].append(b)
                for st, bs in by_state.items():
                    if len(bs) >= spec["state_min_members"]:
                        sm = [(raw[((y0, y1), k, b)]["N"], raw[((y0, y1), k, b)]["F"]) for b in bs]
                        sp, slo, shi, _, _ = rank_list(sm, c, T, spec)
                        for i, b in enumerate(bs):
                            entries[b].update({"statePosition": sp[i], "stateRankLo": slo[i],
                                               "stateRankHi": shi[i], "stateN": len(bs)})
                if k in spec["composition"]:
                    for b in members:
                        entries[b]["composition"] = dict(raw[((y0, y1), k, b)]["comp"])
                header["list"] = {"n": len(members), "minExpected": E_min,
                                  "minFteYears": math.ceil(Fraction(E_min * natlF, natlN)) if natlN else None,
                                  "zc": None if zc is None else zc}
                header["stateLists"] = {st: len(bs) for st, bs in by_state.items()}
                lists = {"members": members, "by_state": dict(by_state), "zc": zc}
            ents = [entries[b] for b in order]
            summ = window_summary_of(ents)
            header["summary"] = summ
            wfiles[f"{w}-{k}"] = {"header": header, "entries": ents, "by_base": entries, "lists": lists,
                                  "r0": r0, "natl": natl, "peer_ref": peer_ref, "peer": peer}
            natl_info[(w, k)] = (natl, header.get("peer"))

    # ---------------------------------------------------------- single-year entries
    single_entries = {}
    for (y, b), reason in single.items():
        if reason is not None:
            single_entries[(y, b)] = {"notRated": reason}
            continue
        rec = inst[(y, b)]
        F = rec["rate_fte"]
        ent = {"fte": F, "rates": {}}
        mdict, idict, odict = {}, {}, {}
        for k in codes:
            s = S.get((y, b, k), ZERO)
            _, lower, upper = bank.get(s[0], c_of(k, spec), 1)
            ent["rates"][k] = [s[0], rate2(s[0], F), bound2(lower / F * 10000.0), bound2(upper / F * 10000.0)]
            if s[3] > 0:
                mdict[k] = s[3]
            if s[4] > 0:
                idict[k] = s[4]
            if s[5] > 0:
                odict[k] = s[5]
        if rec["uncertain"]:
            ent["fteUncertain"] = "own" if rec["uncertain_own"] else "pooled"
        if mdict:
            ent["medical"] = mdict
        if idict:
            ent["sharedIn"] = idict
        if odict:
            ent["sharedOut"] = odict
        single_entries[(y, b)] = ent

    # ---------------------------------------------------------- institution files
    inst_files = {}
    for b, ys in years_by_base.items():
        has_rated = any(status.get((b, f"{y0}-{y1}"), {}).get("status") == "rated" for (y0, y1) in windows)
        has_single = any(single[(y, b)] is None for y in ys)
        if not (has_rated or has_single or flags.get(b)):
            continue
        last = inst[(ys[-1], b)]
        f = {"id": b, "name": last["name"], "unitid": last["link"], "state": last["state"],
             "peerType": last["peer_type"], "years": {str(y): single_entries[(y, b)] for y in ys}, "windows": {},
             "flags": flags.get(b, [])}
        for (y0, y1) in windows:
            w = f"{y0}-{y1}"
            st = status.get((b, w))
            if st is None:
                continue
            st = dict(st)
            if st["status"] == "rated":
                cds = {}
                for k in codes:
                    wf = wfiles[f"{w}-{k}"]
                    e = {kk: vv for kk, vv in wf["by_base"][b].items()
                         if kk not in ("id", "unitid", "name", "state", "peerType")}
                    e["nByYear"] = raw[((y0, y1), k, b)]["nByYear"]
                    if k in spec["composition"]:
                        # institution files carry the composition for every rated entry
                        e["composition"] = dict(raw[((y0, y1), k, b)]["comp"])
                    e["natl"] = wf["natl"]
                    pt = raw[((y0, y1), k, b)]["rec"]["peer_type"]
                    e["peerRate"] = wf["peer"][pt]["rate"] if pt in wf["peer"] else None
                    cds[k] = e
                st["codes"] = cds
            f["windows"][w] = st
        inst_files[b] = f

    return {"windows": windows, "data_years": data_years, "status": status, "rated": rated, "raw": raw,
            "wfiles": wfiles, "flags": flags, "single": single, "single_entries": single_entries,
            "inst_files": inst_files, "years_by_base": years_by_base}


def dual_verdict(lower, upper, F, Fs, ref, online):
    """R7a, or R7b for an online institution: (verdict, larger-FTE verdict, smaller-FTE verdict, reason)."""
    vL = verdict_of(lower, upper, F, ref)
    if not online:
        return vL, None, None, None
    if Fs is None:
        return "undetermined", vL, None, "noSecondEstimate"
    vS = verdict_of(lower, upper, Fs, ref)
    if vS == vL:
        return vL, vL, vS, None
    return "undetermined", vL, vS, "estimates"


def window_summary_of(ents):
    s = {"rated": len(ents), "byWhy": Counter(), "verdicts": Counter(), "verdictsNoReason": Counter(),
         "peerVerdicts": Counter(), "withFlags": 0, "verdictWithoutFlaggedDiffers": 0}
    for e in ents:
        s["byWhy"][e.get("why") or "none"] += 1
        s["verdicts"][e["verdict"]] += 1
        if not e.get("why"):
            s["verdictsNoReason"][e["verdict"]] += 1
        if e["peerVerdict"] is not None:
            s["peerVerdicts"][e["peerVerdict"]] += 1
        if e.get("flags"):
            s["withFlags"] += 1
        if "verdictWithoutFlagged" in e:
            s["verdictWithoutFlaggedDiffers"] += 1
    for k in ("byWhy", "verdicts", "verdictsNoReason", "peerVerdicts"):
        s[k] = dict(s[k])
    return s


def nz(d):
    """A count dict without its zero entries."""
    return {k: v for k, v in (d or {}).items() if v != 0}


# =============================================================================
# Comparison helpers
# =============================================================================

class Problems:
    def __init__(self, subs):
        self.subs = list(subs)
        self.counts = Counter({s: 0 for s in subs})
        self.examples = defaultdict(list)

    def add(self, sub, msg):
        self.counts[sub] += 1
        if len(self.examples[sub]) < 6:
            self.examples[sub].append(msg)

    def total(self):
        return sum(self.counts.values())


KEY_SUB = {}
for _k in ("id", "unitid", "name", "state", "peerType", "n", "nNoncampus", "nPublic", "fteYears",
           "fteYearsSmaller", "fteUncertain", "medical", "sharedIn", "sharedOut", "why"):
    KEY_SUB[_k] = "entry_fields"
for _k in ("rate", "lo", "hi", "E"):
    KEY_SUB[_k] = "rate_interval"
for _k in ("verdict", "verdictLargerFte", "verdictSmallerFte", "undeterminedReason", "peerVerdict",
           "peerVerdictLargerFte", "peerVerdictSmallerFte"):
    KEY_SUB[_k] = "verdicts"
for _k in ("flags", "verdictWithoutFlagged"):
    KEY_SUB[_k] = "flag_attachment"
for _k in ("listed", "position", "rankLo", "rankHi", "statePosition", "stateRankLo", "stateRankHi", "stateN",
           "composition"):
    KEY_SUB[_k] = "lists"
for _k in ("nByYear", "natl", "peerRate"):
    KEY_SUB[_k] = "institution_files"


def norm_flags(lst):
    return sorted((lst or []), key=lambda f: (f.get("year", 0), f.get("offense", ""), f.get("geo", "")))


def cmp_entry(exp, pub, where, P, default_sub="entry_fields"):
    """Key by key; flag lists compared as sets (sorted)."""
    for key in sorted(set(exp) | set(pub)):
        sub = KEY_SUB.get(key, default_sub)
        if key not in pub:
            P.add(sub, f"{where}: {key} missing (expected {exp[key]!r})")
        elif key not in exp:
            P.add(sub, f"{where}: {key} not expected (published {pub[key]!r})")
        else:
            a, b = exp[key], pub[key]
            if key == "flags":
                a, b = norm_flags(a), norm_flags(b)
            if not same(a, b):
                P.add(sub, f"{where}: {key} published {b!r}, expected {a!r}")


def same(a, b):
    """Equality with ints and floats compared by value, bools kept apart from numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return a == b


def diff_paths(exp, pub, path=""):
    """Paths where two JSON-like values differ."""
    out = []
    if isinstance(exp, dict) and isinstance(pub, dict):
        for k in sorted(set(exp) | set(pub), key=str):
            if k not in pub:
                out.append(f"{path}/{k} missing")
            elif k not in exp:
                out.append(f"{path}/{k} not expected")
            else:
                out += diff_paths(exp[k], pub[k], f"{path}/{k}")
    elif isinstance(exp, (list, tuple)) and isinstance(pub, (list, tuple)) and len(exp) == len(pub):
        for i, (a, b) in enumerate(zip(exp, pub)):
            out += diff_paths(a, b, f"{path}[{i}]")
    elif not same(exp, pub):
        out.append(f"{path}: published {pub!r}, expected {exp!r}")
    return out


# =============================================================================
# CHECK 12: Rate Rules
# =============================================================================

SUBS_12 = ("constants_config", "constants_metadata", "test_vectors", "window_files", "national_rate", "statuses",
           "entry_fields", "entry_order", "rate_interval", "verdicts", "unusual_year_flags", "flag_attachment",
           "lists", "summary", "single_year", "institution_files", "count_flags", "school_files", "A4", "A5")


def expected_rate_rules_meta(spec, cfg, windows):
    rate_codes = list(spec["codes"])
    count_codes = list(cfg.SUMMARY_FAMILIES) + [ocode(o) for o in cfg.OFFENSE_ORDER]
    tl = spec["test_list"]
    return {
        "minFte": spec["min_fte"],
        "onlineUncertainRatio": list(cfg.ONLINE_UNCERTAIN_RATIO),
        "onlineShareYear": {str(k): v for k, v in cfg.ONLINE_SHARE_YEAR.items()},
        "windowYears": spec["window_years"],
        "skipYears": list(spec["skip_years"]),
        "windows": [list(w) for w in windows],
        "codes": {k: [ocode(o) for o in v] for k, v in spec["codes"].items()},
        "countsOnly": sorted(c for c in count_codes if c not in rate_codes),
        "ciLevel": spec["ci_level"],
        "dispersion": {"power": spec["power"], "c": {k: c_of(k, spec) for k in rate_codes},
                       "fitted": dict(spec["c"]), "other": spec["c_other"],
                       "ramp": {"start": spec["ramp_start"], "end": spec["ramp_end"], "cap": spec["ramp_cap"]}},
        "medicalShare": list(spec["medical_share"]),
        "sharedShare": list(spec["shared_share"]),
        "lists": {"codes": list(spec["list_codes"]), "minExpected": spec["list_min_expected"],
                  "alpha": spec["list_alpha"], "stateMinMembers": spec["state_min_members"],
                  "stateDisplayMin": spec["state_display_min"]},
        "peerTypes": {k: {"label": cfg.PEER_TYPES[k][0] if k in cfg.PEER_TYPES else None, "sizeSetting": list(v)}
                      for k, v in spec["peer_size_setting"].items()},
        "sizeSettingFields": list(spec["size_setting_fields"]),
        "flags": {"offenses": [ocode(o) for o in spec["flag_offenses"]], "geos": list(spec["flag_geos"]),
                  "minCount": spec["flag_min_count"], "minOtherYears": spec["flag_min_other_years"],
                  "p": spec["flag_p"], "c": spec["flag_c"], "minMean": spec["flag_min_mean"]},
        "countFlag": {"minCount": spec["count_flag_min_count"], "factor": spec["count_flag_factor"],
                      "percentile": spec["count_flag_percentile"]},
        "medicalScreen": {"pattern": cfg.MEDICAL_SCREEN_PATTERN, "share": list(spec["medical_screen_share"]),
                          "minCount": spec["medical_screen_min_count"]},
        "calibration": {"codes": list(spec["calibration"]["codes"]),
                        "periods": [list(p) if isinstance(p, tuple) else p for p in spec["calibration"]["periods"]],
                        **{k: (list(v) if isinstance(v, tuple) else v) for k, v in spec["calibration"].items()
                           if k not in ("codes", "periods")}},
        "testVectors": {
            "counts": [{"c": c, "years": 3, "n": n, "phi": p, "interval": [lo, hi]}
                       for c, n, p, lo, hi in spec["test_counts"]],
            "rates": [{"n": n, "fteYears": f, "c": c, "rate": r, "lo": lo, "hi": hi}
                      for n, f, c, r, lo, hi in spec["test_rates"]],
            "list": {"c": tl["c"], "years": tl["years"], "zc": tl["zc"],
                     "members": [{"n": n, "fteYears": f, "position": p, "rankLo": a, "rankHi": b}
                                 for n, f, p, a, b in tl["members"]]},
            "criticalZ": {str(k): v for k, v in spec["critical_z"].items()}},
    }


def check_config(spec, cfg, P):
    c = cfg
    pairs = [
        ("MIN_FTE_FOR_RATE", c.MIN_FTE_FOR_RATE, spec["min_fte"]),
        ("RATE_WINDOW_YEARS", c.RATE_WINDOW_YEARS, spec["window_years"]),
        ("RATE_SKIP_YEARS", tuple(c.RATE_SKIP_YEARS), tuple(spec["skip_years"])),
        ("RATE_CODES", {k: tuple(v) for k, v in c.RATE_CODES.items()}, spec["codes"]),
        ("RATE_DISPERSION", dict(c.RATE_DISPERSION), dict(spec["c"])),
        ("RATE_DISPERSION_OTHER", c.RATE_DISPERSION_OTHER, spec["c_other"]),
        ("RATE_RAMP", tuple(c.RATE_RAMP), (spec["ramp_start"], spec["ramp_cap"])),
        ("RATE_CI_LEVEL", c.RATE_CI_LEVEL, spec["ci_level"]),
        ("LIST_CODES", tuple(c.LIST_CODES), tuple(spec["list_codes"])),
        ("LIST_MIN_EXPECTED", c.LIST_MIN_EXPECTED, spec["list_min_expected"]),
        ("LIST_ALPHA", c.LIST_ALPHA, spec["list_alpha"]),
        ("STATE_LIST_MIN_MEMBERS", c.STATE_LIST_MIN_MEMBERS, spec["state_min_members"]),
        ("STATE_LIST_DISPLAY_MIN", c.STATE_LIST_DISPLAY_MIN, spec["state_display_min"]),
        ("MEDICAL_CAMPUS_SHARE", tuple(c.MEDICAL_CAMPUS_SHARE), tuple(spec["medical_share"])),
        ("SHARED_MAX_SHARE", tuple(c.SHARED_MAX_SHARE), tuple(spec["shared_share"])),
        ("MEDICAL_SCREEN_SHARE", tuple(c.MEDICAL_SCREEN_SHARE), tuple(spec["medical_screen_share"])),
        ("MEDICAL_SCREEN_MIN_COUNT", c.MEDICAL_SCREEN_MIN_COUNT, spec["medical_screen_min_count"]),
        ("FLAG_OFFENSES", tuple(c.FLAG_OFFENSES), tuple(spec["flag_offenses"])),
        ("FLAG_GEOS", tuple(c.FLAG_GEOS), tuple(spec["flag_geos"])),
        ("FLAG_MIN_COUNT", c.FLAG_MIN_COUNT, spec["flag_min_count"]),
        ("FLAG_MIN_OTHER_YEARS", c.FLAG_MIN_OTHER_YEARS, spec["flag_min_other_years"]),
        ("FLAG_P", c.FLAG_P, spec["flag_p"]),
        ("FLAG_C", c.FLAG_C, spec["flag_c"]),
        ("FLAG_MIN_MEAN", c.FLAG_MIN_MEAN, spec["flag_min_mean"]),
        ("COUNT_FLAG_MIN_COUNT", c.COUNT_FLAG_MIN_COUNT, spec["count_flag_min_count"]),
        ("COUNT_FLAG_FACTOR", c.COUNT_FLAG_FACTOR, spec["count_flag_factor"]),
        ("COUNT_FLAG_PERCENTILE", c.COUNT_FLAG_PERCENTILE, spec["count_flag_percentile"]),
        ("RATE_CALIBRATION", dict(c.RATE_CALIBRATION), dict(spec["calibration"])),
        ("SIZE_SETTING_FIELDS", tuple(c.SIZE_SETTING_FIELDS), tuple(spec["size_setting_fields"])),
        ("PEER_TYPES sizeSetting", {k: tuple(v[1]) for k, v in c.PEER_TYPES.items()},
         {k: tuple(v) for k, v in spec["peer_size_setting"].items()}),
    ]
    for name, got, want in pairs:
        if got != want:
            P.add("constants_config", f"config.{name} = {got!r}, the rules say {want!r}")
    if spec["ramp_end"] != spec["ramp_start"] * spec["ramp_cap"]:
        P.add("constants_config", "ramp end is not start x cap")
    if spec["power"] != 1.5:
        P.add("constants_config", f"power {spec['power']} (the intervals use exponent 1.5)")
    yrs = list(cfg.DATA_YEARS)
    mine = all_windows(yrs, spec)
    if [w for w in mine if w[1] <= 2024] != list(spec["windows_through_2024"]):
        P.add("constants_config", f"windows from DATA_YEARS {mine} do not start with {spec['windows_through_2024']}")


def check_test_vectors(spec, P):
    for c, n, phi, lo, hi in spec["test_counts"]:
        p, l, h = count_intervals(np.array([float(n)]), c, 3, spec)
        p, l, h = float(p[0]), float(l[0]), float(h[0])
        if abs(p - phi) > 0.5e-6 + 1e-12 or abs(l - lo) > 0.5e-4 + 1e-12 or abs(h - hi) > 0.5e-4 + 1e-12:
            P.add("test_vectors", f"c {c} N {n}: phi {p:.6f} [{l:.4f}, {h:.4f}], the design gives {phi} [{lo}, {hi}]")
    for n, f, c, rate, lo, hi in spec["test_rates"]:
        _, l, h = count_intervals(np.array([float(n)]), c, 3, spec)
        got = (rate2(n, f), bound2(float(l[0]) / f * 10000.0), bound2(float(h[0]) / f * 10000.0))
        if got != (rate, lo, hi):
            P.add("test_vectors", f"N {n} F {f} c {c}: {got}, the design gives {(rate, lo, hi)}")
    tl = spec["test_list"]
    mem = [(n, f) for n, f, _, _, _ in tl["members"]]
    pos, rlo, rhi, zc, z = rank_list(mem, tl["c"], tl["years"], spec)
    if abs(zc - tl["zc"]) > 0.5e-6 + 1e-12:
        P.add("test_vectors", f"zc(5) {zc:.6f}, the design gives {tl['zc']}")
    for i, (_, _, p, a, b) in enumerate(tl["members"]):
        if (pos[i], rlo[i], rhi[i]) != (p, a, b):
            P.add("test_vectors", f"list member {'ABCDE'[i]}: {pos[i]} {rlo[i]}-{rhi[i]}, the design gives {p} {a}-{b}")
    for x, y, want in tl["z"]:
        got = float(z["ABCDE".index(x), "ABCDE".index(y)])
        if abs(got - want) > 0.5e-4 + 1e-12:
            P.add("test_vectors", f"z_{x}{y} {got:.4f}, the design gives {want}")
    for n, want in spec["critical_z"].items():
        got = critical_z(n, spec)
        if abs(got - want) > 0.5e-4 + 1e-12:
            P.add("test_vectors", f"zc({n}) {got:.6f}, the design gives {want}")


def audit_rate_rules(verbose: bool = False, inputs=None, data=None, spec=None, cfg=None) -> AuditResult:
    """
    CHECK 12: every rate field the site publishes is what the v4 rules give.

    From the institution data alone (rate_inputs) and the rules written out in
    SPEC: the windows and each institution's window status, the 3-year counts,
    FTE-years, reason (why), national and peer rates, intervals (own gamma
    function), rates, bounds and E rounded half up, verdicts (exact, the online
    rule with both FTE estimates, peer verdicts), unusual-year flags and their
    effect on the verdict, the ordered lists (members by E, exact order,
    positions, Bonferroni rank ranges, state lists, composition), the summary
    counts, single-year entries, institution files, flags.json, count flags in
    every rankings file and the rate fields of every school file. Also
    config.py's and metadata.json's constants against SPEC, the design's test
    vectors, A4 (removing flagged excess keeps a listed institution's position
    inside its published range) and A5 (bounds non-decreasing in N).
    """
    result = AuditResult("Rate Rules")
    print("\nCHECK 12: Rate Rules")
    t0 = time.time()
    spec = spec or SPEC
    cfg = cfg or config
    P = Problems(SUBS_12)
    try:
        result.details["what_it_checks"] = (
            "Without 04's, 05's or rates.py's code, from the institution-year data (institution-years with a "
            "counting campus, their on-campus/residence-hall/non-campus/public-property counts per offense, "
            "medical-center and shared on-campus figures, NCES FTE, the rate denominator and its smaller estimate, "
            "rules, online uncertainty, peer type) and the rule constants written out in this check: each "
            "institution's status in every 3-year window without 2020 (missingYears, scope, size, excluded, rated), "
            "the window counts, FTE-years, reason (online, medical_campus: medical share at least 1/4, shared: "
            "20 x shared > count + sharedOut), the national and peer rates as exact fractions, phi with the ramp, "
            "the gamma interval (own incomplete gamma, bisection), rate/lo/hi/E rounded half up, the verdicts "
            "against the exact reference (online: both FTE estimates must agree), the unusual-year flags "
            "(negative binomial tail < 0.001) and the verdict without the flagged excess, the ordered lists "
            "(E >= 20 exactly, exact order, positions, pairwise z with Bonferroni critical values from an own "
            "normal quantile, ranges widened to the position, state lists from 2 members, composition), every "
            "window file's header and summary, rates/institutions (single-year T = 1 entries and notRated "
            "reasons, window statuses), rates/flags.json, the count flag (3 x P99, numpy linear percentile, "
            "count >= 20) in every rankings file, school files' ratesFile/rated/notRated/flags, metadata.json "
            "rateRules and rateStats, config.py's constants, the design's test vectors, A4 and A5.")
        inputs = inputs if inputs is not None else default_inputs()
        data = data if data is not None else default_data()
        md = data["metadata"]

        check_config(spec, cfg, P)
        check_test_vectors(spec, P)

        bank = IntervalBank(spec)
        X = derive(inputs, spec, cfg, bank)
        windows = X["windows"]
        result.details["windows"] = [f"{a}-{b}" for a, b in windows]

        # ---- metadata.rateRules
        rr = md.get("rateRules", {})
        exp_rr = expected_rate_rules_meta(spec, cfg, windows)
        rr_cmp = {k: v for k, v in rr.items()}
        if isinstance(rr_cmp.get("countFlag"), dict):
            rr_cmp["countFlag"] = {k: v for k, v in rr_cmp["countFlag"].items() if k != "reference"}
        for d in diff_paths(exp_rr, rr_cmp, "rateRules"):
            P.add("constants_metadata", d)

        # ---- window files
        exp_names = set(X["wfiles"])
        pub_names = set(data["windows"])
        for n in sorted(exp_names - pub_names):
            P.add("window_files", f"rates/{n}.json missing")
        for n in sorted(pub_names - exp_names):
            P.add("window_files", f"rates/{n}.json not expected")
        per_window = {}
        for name in sorted(exp_names & pub_names):
            W = X["wfiles"][name]
            pub = data["windows"][name]
            h = W["header"]
            for key in ("window", "code", "years", "c"):
                if not same(h[key], pub.get(key)):
                    P.add("window_files", f"{name}: {key} published {pub.get(key)!r}, expected {h[key]!r}")
            for key in ("natl", "natlN", "natlF", "peer"):
                if not same(h[key], pub.get(key)):
                    P.add("national_rate", f"{name}: {key} published {pub.get(key)!r}, expected {h[key]!r}")
            for key in ("composition", "list", "stateLists"):
                if key in h or key in pub:
                    a, b = h.get(key), pub.get(key)
                    if key == "list" and isinstance(a, dict) and isinstance(b, dict):
                        a = dict(a)
                        b = dict(b)
                        za, zb = a.pop("zc"), b.pop("zc", "missing")
                        if not ((za is None and zb is None) or
                                (za is not None and isinstance(zb, (int, float)) and abs(za - zb) <= 0.5e-6 + 1e-12)):
                            P.add("lists", f"{name}: list.zc published {zb!r}, expected {za!r}")
                    if not same(a, b):
                        P.add("lists" if key != "composition" or name.split("-")[-1] in spec["list_codes"]
                              else "national_rate", f"{name}: {key} published {b!r}, expected {a!r}")
            pub_sum = pub.get("summary", {})
            for key, val in h["summary"].items():
                pv = pub_sum.get(key)
                ok = same(nz(val), nz(pv)) if isinstance(val, dict) else same(val, pv)
                if not ok:
                    P.add("summary", f"{name}: summary.{key} published {pv!r}, expected {val!r}")
            for key in set(pub_sum) - set(h["summary"]):
                P.add("summary", f"{name}: summary.{key} not expected")
            pents = pub.get("entries", [])
            pby = {}
            for e in pents:
                if e.get("id") in pby:
                    P.add("statuses", f"{name}: institution {e.get('id')} listed twice")
                pby[e.get("id")] = e
            eby = W["by_base"]
            for b in sorted(set(eby) - set(pby)):
                P.add("statuses", f"{name}: rated institution {b} ({eby[b]['name']}) has no entry")
            for b in sorted(set(pby) - set(eby)):
                st = X["status"].get((b, "-".join(name.split("-")[:2])))
                P.add("statuses", f"{name}: entry {b} ({pby[b].get('name')}) not expected (status {st})")
            for b in sorted(set(eby) & set(pby)):
                cmp_entry(eby[b], pby[b], f"{name} {b} {eby[b]['name']}", P)
            exp_order = [e["id"] for e in W["entries"]]
            pub_order = [e.get("id") for e in pents]
            if set(exp_order) == set(pub_order) and exp_order != pub_order:
                i = next(i for i, (a, b) in enumerate(zip(exp_order, pub_order)) if a != b)
                P.add("entry_order", f"{name}: order differs first at index {i}: published {pub_order[i]}, "
                                     f"expected {exp_order[i]}")
            k = name.split("-", 2)[2]
            pw = {"rated": len(eby), "verdicts": h["summary"]["verdicts"], "natl": h["natl"]}
            if W["lists"] is not None:
                bs = W["lists"]["by_state"]
                pw.update({"listed": len(W["lists"]["members"]), "zc": W["lists"]["zc"],
                           "stateLists": sum(1 for v in bs.values() if len(v) >= spec["state_min_members"]),
                           "stateListsDisplayMin": sum(1 for v in bs.values() if len(v) >= spec["state_display_min"])})
            per_window[name] = pw

        # ---- rateStats.windows
        rs = md.get("rateStats", {})
        for name, W in X["wfiles"].items():
            w = "-".join(name.split("-")[:2])
            k = name.split("-", 2)[2]
            h = W["header"]
            exp = dict(h["summary"])
            exp["natl"] = h["natl"]
            if W["lists"] is not None:
                exp["listed"] = h["list"]["n"]
                exp["minFteYears"] = h["list"]["minFteYears"]
                exp["stateLists"] = per_window[name]["stateLists"] if name in per_window else None
                exp["stateListsDisplayMin"] = per_window[name]["stateListsDisplayMin"] if name in per_window else None
            pub = rs.get("windows", {}).get(w, {}).get(k)
            if pub is None:
                P.add("summary", f"rateStats.windows.{w}.{k} missing")
                continue
            for key in set(exp) | set(pub):
                a, b = exp.get(key, "missing"), pub.get(key, "missing")
                ok = same(nz(a), nz(b)) if isinstance(a, dict) and isinstance(b, dict) else same(a, b)
                if not ok:
                    P.add("summary", f"rateStats.windows.{w}.{k}.{key} published {b!r}, expected {a!r}")
        exp_w = {"-".join(n.split("-")[:2]) for n in X["wfiles"]}
        for w in set(rs.get("windows", {})) - exp_w:
            P.add("summary", f"rateStats.windows.{w} not expected")

        # ---- unusual-year flags: flags.json, rateStats.flags
        inst = inputs["inst"]
        all_flags = []
        for b, fl in X["flags"].items():
            last = inst[(X["years_by_base"][b][-1], b)]
            for f in fl:
                all_flags.append({"id": b, "name": last["name"], "state": last["state"], **f})
        key5 = lambda f: (f.get("id"), f.get("year"), f.get("offense"), f.get("geo"))
        exp_f = {key5(f): f for f in all_flags}
        pub_fl = (data.get("flags") or {}).get("flags", [])
        pub_f = {}
        for f in pub_fl:
            if key5(f) in pub_f:
                P.add("unusual_year_flags", f"flags.json: {key5(f)} twice")
            pub_f[key5(f)] = f
        for kk in sorted(set(exp_f) - set(pub_f), key=str):
            f = exp_f[kk]
            P.add("unusual_year_flags", f"flags.json: missing flag {kk} count {f['count']} usual {f['usual']}")
        for kk in sorted(set(pub_f) - set(exp_f), key=str):
            P.add("unusual_year_flags", f"flags.json: flag {kk} not expected ({pub_f[kk]})")
        for kk in sorted(set(pub_f) & set(exp_f), key=str):
            if not same(exp_f[kk], pub_f[kk]):
                P.add("unusual_year_flags", f"flags.json: {kk} published {pub_f[kk]}, expected {exp_f[kk]}")
        fstats = {"total": len(all_flags), "byGeo": dict(Counter(f["geo"] for f in all_flags)),
                  "byYear": dict(Counter(str(f["year"]) for f in all_flags)),
                  "byOffense": dict(Counter(f["offense"] for f in all_flags))}
        for d in diff_paths({k: (nz(v) if isinstance(v, dict) else v) for k, v in fstats.items()},
                            {k: (nz(v) if isinstance(v, dict) else v) for k, v in rs.get("flags", {}).items()},
                            "rateStats.flags"):
            P.add("unusual_year_flags", d)

        # ---- institution files
        exp_files = X["inst_files"]
        pub_files = data["institutions"]
        for b in sorted(set(map(str, exp_files)) - set(pub_files), key=int):
            P.add("institution_files", f"rates/institutions/{b}.json missing")
        for b in sorted(set(pub_files) - set(map(str, exp_files)), key=lambda s: int(s) if s.isdigit() else 0):
            P.add("institution_files", f"rates/institutions/{b}.json not expected")
        n_single = 0
        for b, ef in exp_files.items():
            pf = pub_files.get(str(b))
            if pf is None:
                continue
            for key in ("id", "name", "unitid", "state", "peerType"):
                if not same(ef[key], pf.get(key)):
                    P.add("institution_files", f"{b}.json: {key} published {pf.get(key)!r}, expected {ef[key]!r}")
            if not same(norm_flags(ef["flags"]), norm_flags(pf.get("flags"))):
                P.add("unusual_year_flags", f"{b}.json: flags published {pf.get('flags')}, expected {ef['flags']}")
            py = pf.get("years", {})
            for y in sorted(set(ef["years"]) | set(py)):
                a, bb = ef["years"].get(y, "missing"), py.get(y, "missing")
                if not same(a, bb):
                    P.add("single_year", f"{b}.json years.{y}: " + "; ".join(diff_paths(a, bb)[:3])
                          if isinstance(a, dict) and isinstance(bb, dict) else
                          f"{b}.json years.{y}: published {bb!r}, expected {a!r}")
                n_single += 1
            pw = pf.get("windows", {})
            for w in sorted(set(ef["windows"]) | set(pw)):
                if w not in pw:
                    P.add("statuses", f"{b}.json windows.{w} missing (expected {ef['windows'][w]['status']})")
                    continue
                if w not in ef["windows"]:
                    P.add("statuses", f"{b}.json windows.{w} not expected ({pw[w].get('status')})")
                    continue
                es, ps = ef["windows"][w], dict(pw[w])
                if ps.get("why") == "":
                    ps.pop("why")
                a = {kk: vv for kk, vv in es.items() if kk != "codes"}
                bb = {kk: vv for kk, vv in ps.items() if kk != "codes"}
                if not same(a, bb):
                    P.add("statuses", f"{b}.json windows.{w}: published {bb}, expected {a}")
                if "codes" in es:
                    pc = ps.get("codes", {})
                    for k in set(es["codes"]) | set(pc):
                        if k not in pc or k not in es["codes"]:
                            P.add("institution_files", f"{b}.json windows.{w}.codes.{k} "
                                                       f"{'missing' if k not in pc else 'not expected'}")
                            continue
                        cmp_entry(es["codes"][k], pc[k], f"{b}.json {w} {k}", P, "institution_files")
                elif "codes" in ps:
                    P.add("statuses", f"{b}.json windows.{w}: codes on a {ps.get('status')} window")

        # ---- rateStats.singleYear, institutionFiles
        sy = Counter()
        for (y, b), reason in X["single"].items():
            if reason is None:
                sy[str(y)] += 1
        exp_sy = {str(y): sy.get(str(y), 0) for y in X["data_years"]}
        if not same(nz(exp_sy), nz(rs.get("singleYear"))):
            P.add("single_year", f"rateStats.singleYear published {rs.get('singleYear')}, expected {exp_sy}")
        if rs.get("institutionFiles") != len(exp_files):
            P.add("institution_files", f"rateStats.institutionFiles published {rs.get('institutionFiles')}, "
                                       f"expected {len(exp_files)}")

        # ---- count flags (R13)
        cf_details = check_count_flags(inputs, data, spec, cfg, X, P)

        # ---- school files
        sch_details = check_school_files(inputs, data, X, P)

        # ---- A4: removing flagged excess keeps listed positions inside the published range
        a4 = {"checked": 0, "outside": 0, "verdict_changes": {}}
        for name, W in X["wfiles"].items():
            k = name.split("-", 2)[2]
            w = "-".join(name.split("-")[:2])
            a4["verdict_changes"].setdefault(w, {})[k] = W["header"]["summary"]["verdictWithoutFlaggedDiffers"]
            if W["lists"] is None:
                continue
            pby = {e.get("id"): e for e in data["windows"].get(name, {}).get("entries", [])}
            mem = W["lists"]["members"]
            yy = tuple(W["header"]["window"])
            rates = {b: Fraction(X["raw"][(yy, k, b)]["N"], X["raw"][(yy, k, b)]["F"]) for b in mem}
            for b in mem:
                r = X["raw"][(yy, k, b)]
                if not r["flags"]:
                    continue
                a4["checked"] += 1
                rw = r["Nw"] / r["F"]
                pos = 1 + sum(1 for j in mem if j != b and rates[j] > rw)
                pe = pby.get(b, {})
                lo_, hi_ = pe.get("rankLo", W["by_base"][b]["rankLo"]), pe.get("rankHi", W["by_base"][b]["rankHi"])
                if not (isinstance(lo_, int) and isinstance(hi_, int) and lo_ <= pos <= hi_):
                    a4["outside"] += 1
                    P.add("A4", f"{name} {b} {W['by_base'][b]['name']}: position without the flagged excess {pos}, "
                                f"published range {lo_}-{hi_}")

        # ---- A5: bounds non-decreasing in N
        a5 = {}
        cs = sorted(set(spec["c"].values()) | {spec["c_other"]})
        for T in (spec["window_years"], 1):
            for c in cs:
                Ns = np.arange(0, 3001, dtype=float)
                _, lo_, hi_ = count_intervals(Ns, c, T, spec)
                dlo, dhi = np.diff(lo_), np.diff(hi_)
                bad_lo = np.nonzero(dlo < 0)[0]
                bad_hi = np.nonzero(dhi < 0)[0]
                a5[f"T{T} c{c}"] = {"lo_monotone": bool(len(bad_lo) == 0), "hi_monotone": bool(len(bad_hi) == 0),
                                    "min_step_lo": round(float(dlo.min()), 6), "min_step_hi": round(float(dhi.min()), 6)}
                if len(bad_lo):
                    P.add("A5", f"T {T} c {c}: lower bound falls from N = {int(bad_lo[0])} to {int(bad_lo[0]) + 1}")
                if len(bad_hi):
                    P.add("A5", f"T {T} c {c}: upper bound falls from N = {int(bad_hi[0])} to {int(bad_hi[0]) + 1}")

        # ---- details
        result.details["per_window_code"] = per_window
        result.details["institution_files"] = len(exp_files)
        result.details["single_year_entries_checked"] = n_single
        result.details["flags"] = fstats
        result.details["count_flags"] = cf_details
        result.details["school_files"] = sch_details
        result.details["A4"] = a4
        result.details["A5"] = a5
        result.details["subchecks"] = dict(P.counts)
        result.details["examples"] = {k: v for k, v in P.examples.items()}
        result.details["problems"] = P.total()
        result.details["seconds"] = round(time.time() - t0, 1)

        print(f"  Windows {len(windows)}, window files {len(exp_names)}, institution files {len(exp_files):,}, "
              f"flags {len(all_flags):,}; A4 listed entries with flags {a4['checked']}, outside range "
              f"{a4['outside']}; A5 {'monotone' if not P.counts['A5'] else 'NOT monotone'}")
        bad = {k: v for k, v in P.counts.items() if v}
        print(f"  Problems: {P.total()}" + (f" {bad}" if bad else ""))
        if verbose:
            for k, ex in P.examples.items():
                for m in ex[:3]:
                    print(f"    [{k}] {m}")
        if P.total():
            first = next(k for k in SUBS_12 if P.counts[k])
            result.failed(f"{P.total()} problems with the rate rules ({', '.join(f'{k} {v}' for k, v in bad.items())}; "
                          f"first: {P.examples[first][0]})")
        else:
            result.passed()
        print(f"  {result.status} ({result.details['seconds']} s)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")
    return result


def count_codes_of(cfg):
    return list(cfg.SUMMARY_FAMILIES) + [ocode(o) for o in cfg.OFFENSE_ORDER]


def p99_reference(inputs, spec, cfg, years):
    """R13 reference: P99 (numpy linear) per year and count code of count_all x 10,000 / rate_fte over
    institutions with a link state in US_STATES, rate_fte >= min, no rule and a certain FTE (0 included)."""
    us = set(cfg.US_STATES)
    inst = inputs["inst"]
    ca = inputs["count_all"]
    codes = count_codes_of(cfg)
    ref = {}
    for y in years:
        pop = [b for (yy, b), r in inst.items() if yy == y and r["state"] in us and r["rate_fte"] is not None
               and r["rate_fte"] >= spec["min_fte"] and r["rule"] is None and not r["uncertain"]]
        ref[y] = {}
        for code in codes:
            vals = sorted(Fraction(ca.get((y, b, code), 0) * 10000, inst[(y, b)]["rate_fte"]) for b in pop)
            ref[y][code] = percentile_linear(vals, spec["count_flag_percentile"]) if vals else None
    return ref


def check_count_flags(inputs, data, spec, cfg, X, P):
    inst = inputs["inst"]
    years = X["data_years"]
    ref = p99_reference(inputs, spec, cfg, years)
    md = data["metadata"]
    pref = md.get("rateRules", {}).get("countFlag", {}).get("reference", {})
    for y in years:
        py = pref.get(str(y), {})
        for code, v in ref[y].items():
            pv = py.get(code)
            if v is None or not isinstance(pv, (int, float)) or abs(float(v) - pv) > 0.5e-4 + 1e-9:
                P.add("count_flags", f"countFlag.reference.{y}.{code} published {pv!r}, expected "
                                     f"{None if v is None else round(float(v), 4)}")
        for code in set(py) - set(ref[y]):
            P.add("count_flags", f"countFlag.reference.{y}.{code} not expected")
    for y in set(pref) - {str(y) for y in years}:
        P.add("count_flags", f"countFlag.reference.{y} not expected")
    mn, fac = spec["count_flag_min_count"], spec["count_flag_factor"]
    files = 0
    flagged_nat = defaultdict(Counter)
    total_flagged = 0
    for name, r in data["rankings"].items():
        files += 1
        y = r.get("year")
        if y not in ref:
            P.add("count_flags", f"rankings/{name}.json: year {y!r} has no reference")
            continue
        for code, ents in (r.get("rankings") or {}).items():
            p99 = ref[y].get(code)
            if p99 is None:
                P.add("count_flags", f"rankings/{name}.json: code {code} has no reference")
                continue
            for e in ents:
                u = e.get("unitid")
                rec = inst.get((y, u // 1000)) if isinstance(u, int) else None
                fte = rec["fte"] if rec else None
                cnt = e.get("count")
                exp = bool(cnt >= mn and p99 > 0 and fte is not None and fte > 0
                           and cnt * 10000 > fac * p99 * fte)
                got = e.get("highForSize", False)
                if got not in (True, False) or ("highForSize" in e and got is not True):
                    P.add("count_flags", f"rankings/{name}.json {code} {u}: highForSize {got!r}")
                if exp != bool(got):
                    P.add("count_flags", f"rankings/{name}.json {code} {u}: count {cnt}, FTE {fte}, P99 "
                                         f"{float(p99):.4f}: highForSize {bool(got)}, expected {exp}")
                if exp:
                    total_flagged += 1
                    if r.get("preset") == "national" or name.startswith("national-"):
                        flagged_nat[str(y)][code] += 1
    rs = md.get("rateStats", {}).get("countFlags", {})
    for y in sorted(set(flagged_nat) | set(rs)):
        if not same(nz(dict(flagged_nat.get(y, {}))), nz(rs.get(y, {}))):
            P.add("count_flags", f"rateStats.countFlags.{y} published {nz(rs.get(y, {}))}, expected "
                                 f"{nz(dict(flagged_nat.get(y, {})))}")
    return {"rankings_files": files, "flagged_entries_all_files": total_flagged,
            "flagged_national": {y: sum(v.values()) for y, v in sorted(flagged_nat.items())},
            "p99_violent": {str(y): round(float(ref[y]["violent"]), 4) for y in years if ref[y].get("violent") is not None}}


def check_school_files(inputs, data, X, P):
    inst = inputs["inst"]
    files = set(X["inst_files"])
    flags_by_year = defaultdict(list)
    for b, fl in X["flags"].items():
        for f in fl:
            flags_by_year[(f["year"], b)].append({"offense": f["offense"], "geo": f["geo"], "count": f["count"],
                                                  "usual": f["usual"]})
    n = 0
    years_checked = 0
    no_inst = 0
    bases = set(X["years_by_base"])
    for u, ins in data["schools"].items():
        n += 1
        if not isinstance(ins, dict):
            # a campus whose institution has no institution-year (all its figures count under another campus)
            if str(u).isdigit() and int(u) // 1000 in bases:
                P.add("school_files", f"schools/{u}.json: no institution, but institution {int(u) // 1000} "
                                      "has institution-years")
            no_inst += 1
            continue
        b = ins.get("id")
        if not str(u).isdigit() or b != int(u) // 1000:
            P.add("school_files", f"schools/{u}.json: institution id {b}, campus base {int(u) // 1000 if str(u).isdigit() else u}")
        exp_rf = f"rates/institutions/{b}.json" if b in files else None
        if ins.get("ratesFile") != exp_rf:
            P.add("school_files", f"schools/{u}.json: ratesFile {ins.get('ratesFile')!r}, expected {exp_rf!r}")
        for ys, by in (ins.get("byYear") or {}).items():
            y = int(ys)
            years_checked += 1
            if (y, b) not in inst:
                P.add("school_files", f"schools/{u}.json {y}: no institution-year in the data")
                continue
            reason = X["single"][(y, b)]
            if by.get("rated") is not (reason is None):
                P.add("school_files", f"schools/{u}.json {y}: rated {by.get('rated')!r}, expected {reason is None}")
            if by.get("notRated") != reason:
                P.add("school_files", f"schools/{u}.json {y}: notRated {by.get('notRated')!r}, expected {reason!r}")
            ef = flags_by_year.get((y, b))
            pf = by.get("flags")
            if not same(norm_flags(ef), norm_flags(pf)) or (pf is not None and not pf):
                P.add("school_files", f"schools/{u}.json {y}: flags {pf}, expected {ef}")
    return {"school_files": n, "school_years_checked": years_checked, "without_institution": no_inst}


# =============================================================================
# CHECK 13: Interval Calibration (A1)
# =============================================================================

def nb_central(mu, var, level):
    """Central predictive interval [lo, hi] of a negative binomial with mean mu and variance var:
    lo the smallest y with P(Y <= y) > (1 - level) / 2, hi the smallest y with P(Y <= y) >= 1 - that."""
    mu = np.asarray(mu, float)
    var = np.maximum(np.asarray(var, float), mu * (1 + 1e-9))
    k = np.minimum(mu * mu / (var - mu), 1e7)
    q_lo, q_hi = level
    r = mu / (k + mu)
    p = np.exp(k * np.log(k / (k + mu)))
    cdf = p.copy()
    lo = np.where(cdf > q_lo, 0, -1)
    hi = np.where(cdf >= q_hi, 0, -1)
    ymax = int(np.max(mu + 14 * np.sqrt(var) + 30))
    for y in range(ymax):
        if (lo >= 0).all() and (hi >= 0).all():
            break
        p = p * (y + k) / (y + 1) * r
        cdf = cdf + p
        lo = np.where((lo < 0) & (cdf > q_lo), y + 1, lo)
        hi = np.where((hi < 0) & (cdf >= q_hi), y + 1, hi)
    return lo, hi


def calib_V(mu, c, spec):
    return mu + c * ramp(mu, spec) * mu ** 1.5


def calib_indicators(Y, W, c, spec, q):
    """Leave-one-out: each year's count against the 95% predictive interval from the institution's other
    years (rate from the other years times the year's exposure; variance of the count plus the estimate's)."""
    U, T = Y.shape
    N = Y.sum(1)
    Ws = W.sum(1)
    out = np.zeros((U, T))
    for t in range(T):
        Nm = N - Y[:, t]
        Wm = Ws - W[:, t]
        rate = Nm / Wm
        mut = rate * W[:, t]
        vp = calib_V(mut, c, spec) + (W[:, t] / Wm) ** 2 * sum(calib_V(rate * W[:, s], c, spec)
                                                             for s in range(T) if s != t)
        ok = mut > 0
        lo, hi = nb_central(np.where(ok, mut, 1.0), np.where(ok, vp, 1.0), q)
        out[:, t] = np.where(ok, (Y[:, t] >= lo) & (Y[:, t] <= hi), Y[:, t] == 0)
    return out


def calib_panel(inputs, code, years, spec, cfg):
    """Institutions with a single-year rate and a certain FTE in every year of the period and at least one
    incident; exposure = rate_fte x the panel's national rate of the year."""
    us = set(cfg.US_STATES)
    inst = inputs["inst"]
    offs = spec["codes"][code]
    bases = None
    for y in years:
        ok = {b for (yy, b), r in inst.items() if yy == y and single_year_reason(r, y, spec, us) is None
              and not r["uncertain"]}
        bases = ok if bases is None else bases & ok
    bases = sorted(bases or [])
    off = inputs["off"]
    Y = np.array([[sum(off.get((y, b, o), (0, 0, 0, 0))[0] for o in offs) for y in years] for b in bases], float)
    F = np.array([[inst[(y, b)]["rate_fte"] for y in years] for b in bases], float)
    if not len(bases):
        return Y.reshape(0, len(years)), F.reshape(0, len(years)), []
    tau = Y.sum(0) / F.sum(0)
    W = F * tau[None, :]
    keep = Y.sum(1) > 0
    return Y[keep], W[keep], [b for b, k in zip(bases, keep) if k]


def audit_rate_calibration(verbose: bool = False, inputs=None, data=None, spec=None, cfg=None) -> AuditResult:
    """
    CHECK 13 (A1): the dispersion model's intervals cover as often as the model says they should.

    For each code and period of the calibration settings, every institution
    with a single-year rate and a certain on-campus FTE in all the period's
    years and at least one on-campus incident: each year's on-campus count is
    predicted from the institution's other years (year effects from the
    panel's national rates) with variance m + c g(m) m^1.5, and the share of
    counts inside the central 95% predictive interval is compared with the
    share expected under the model (mean of 600 simulated panels, NumPy PCG64
    seeded 11 for each code and period). Fails when they differ, either way,
    by more than 0.02 over institutions with a mean of at least 2 a year; in a
    band of yearly means with at least 100 institutions, when the observed
    share is below the expected one by more than 0.03 (intervals too narrow:
    verdicts claim more certainty than the data give) or above it by more
    than 0.05 (intervals too wide: only fewer verdicts). Every band is
    published in details["rows"], with tested false when it has fewer than
    100 institutions (or none).
    """
    result = AuditResult("Interval Calibration")
    print("\nCHECK 13: Interval Calibration")
    t0 = time.time()
    spec = spec or SPEC
    cfg = cfg or config
    try:
        cal = spec["calibration"]
        result.details["what_it_checks"] = (
            "A1: single-year leave-one-out predictive coverage of on-campus counts under the published "
            "dispersion (c per code, ramp), observed against expected from "
            f"{cal['simulations']} simulations (PCG64 seed {cal['seed']}, fresh per code and period); "
            f"tolerance {cal['tolerance']} either way over units with a mean >= {cal['bands'][0]}/year; "
            f"in bands with >= {cal['bandMinUnits']} units, fails when observed is below expected by more than "
            f"{cal['bandToleranceBelow']} (intervals too narrow: verdicts overstate certainty) or above it by "
            f"more than {cal['bandToleranceAbove']} (intervals too wide: fewer verdicts, the safer error). "
            "Every band is listed in rows; tested is false below the unit minimum.")
        inputs = inputs if inputs is not None else default_inputs()
        problems = []
        if dict(cfg.RATE_CALIBRATION) != dict(cal):
            problems.append(f"config.RATE_CALIBRATION {cfg.RATE_CALIBRATION} differs from the rules {cal}")
        data_years = sorted({y for (y, b) in inputs["inst"]})
        periods = []
        for p in cal["periods"]:
            if p == "latest":
                periods.append(tuple(data_years[-cal["latestYears"]:]))
            else:
                periods.append(tuple(range(p[0], p[1] + 1)))
        q = ci_quantiles(spec)
        bands = list(cal["bands"])
        labels = [f"{a}-{b}" for a, b in zip(bands[:-1], bands[1:])] + [f"{bands[-1]}+"]
        edges = bands + [float("inf")]
        rows = []
        for code in cal["codes"]:
            c = c_of(code, spec)
            for years in periods:
                Y, W, units = calib_panel(inputs, code, list(years), spec, cfg)
                if not len(units):
                    problems.append(f"{code} {years[0]}-{years[-1]}: no institutions")
                    continue
                obs = calib_indicators(Y, W, c, spec, q)
                rng = np.random.default_rng(cal["seed"])
                N = Y.sum(1)
                mu = (N / W.sum(1))[:, None] * W
                v = calib_V(mu, c, spec)
                kk = mu ** 2 / np.maximum(v - mu, 1e-12)
                e = np.zeros_like(obs)
                for _ in range(cal["simulations"]):
                    Ys = rng.poisson(rng.gamma(kk, mu / kk)).astype(float)
                    e = e + calib_indicators(Ys, W, c, spec, q)
                e = e / cal["simulations"]
                mb = N / Y.shape[1]
                period = f"{years[0]}-{years[-1]}"
                for lab, a, b in [(f"all>={bands[0]}", bands[0], float("inf"))] + list(zip(labels, edges[:-1], edges[1:])):
                    mm = (mb >= a) & (mb < b)
                    units_n = int(mm.sum())
                    overall = lab.startswith("all")
                    below = cal["tolerance"] if overall else cal["bandToleranceBelow"]
                    above = cal["tolerance"] if overall else cal["bandToleranceAbove"]
                    if units_n == 0:
                        rows.append({"code": code, "c": c, "period": period, "band": lab, "units": 0,
                                     "observed": None, "expected": None, "diff": None, "toleranceBelow": below,
                                     "toleranceAbove": above, "tested": False, "ok": None})
                        continue
                    o, x = float(obs[mm].mean()), float(e[mm].mean())
                    tested = overall or units_n >= cal["bandMinUnits"]
                    ok = (-below <= o - x <= above) if tested else None
                    rows.append({"code": code, "c": c, "period": period, "band": lab, "units": units_n,
                                 "observed": round(o, 4), "expected": round(x, 4), "diff": round(o - x, 4),
                                 "toleranceBelow": below, "toleranceAbove": above, "tested": tested, "ok": ok})
                    if tested and not ok:
                        side = f"below by more than {below}" if o < x else f"above by more than {above}"
                        problems.append(f"{code} {period} {lab}: observed {o:.3f}, expected {x:.3f} "
                                        f"(diff {o - x:+.3f}, {side}, {units_n} institutions)")
                if verbose:
                    print(f"    {code} {period}: {len(units)} institutions", flush=True)
        result.details["rows"] = rows
        result.details["problems"] = problems
        result.details["seconds"] = round(time.time() - t0, 1)
        for r in rows:
            if r["band"].startswith("all") and r["units"]:
                print(f"    {r['code']:<20}{r['period']:<11}units {r['units']:>5}  obs {r['observed']:.3f}  "
                      f"exp {r['expected']:.3f}  diff {r['diff']:+.3f}")
        print(f"  Problems: {len(problems)}")
        if problems:
            result.failed(f"{len(problems)} calibration problems (first: {problems[0]})")
        else:
            result.passed()
        print(f"  {result.status} ({result.details['seconds']} s)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")
    return result


# =============================================================================
# CHECK 14: Medical-Campus Screen (A3)
# =============================================================================

def audit_medical_screen(verbose: bool = False, inputs=None, data=None, spec=None, cfg=None,
                         names=None, listed=None, reviews=None) -> AuditResult:
    """
    CHECK 14 (A3): campuses that look like medical centers and are not reviewed.

    A campus-year is a candidate when the campus is not a main campus (UNITID
    not ending in 001), its DOE branch name and address (any release of
    dims/campus_names.parquet) match config.MEDICAL_SCREEN_PATTERN (ignoring
    case), its institution-year has a single-year rate, and its criminal
    (without motor-vehicle theft) on-campus figure outside residence halls is
    at least MEDICAL_SCREEN_MIN_COUNT and at least MEDICAL_SCREEN_SHARE of the
    institution's on-campus criminal_xmvt count that year. It is reviewed when
    etl/reference/medical_campuses.csv or medical_campus_reviews.csv covers
    that campus and year. Unreviewed candidates give a warning, listed here.
    """
    result = AuditResult("Medical-Campus Screen")
    print("\nCHECK 14: Medical-Campus Screen")
    t0 = time.time()
    spec = spec or SPEC
    cfg = cfg or config
    try:
        result.details["what_it_checks"] = (
            "A3: non-main campuses whose DOE branch name + address match MEDICAL_SCREEN_PATTERN, in an "
            "institution-year with a single-year rate, with sum over criminal_xmvt offenses of max(0, on campus - "
            f"residence halls) >= {spec['medical_screen_min_count']} and >= "
            f"{spec['medical_screen_share'][0]}/{spec['medical_screen_share'][1]} of the institution's on-campus "
            "criminal_xmvt count, not covered for that year by medical_campuses.csv or medical_campus_reviews.csv.")
        inputs = inputs if inputs is not None else default_inputs()
        us = set(cfg.US_STATES)
        if names is None:
            names = pd.read_parquet(CURATED_DIR / "dims" / "campus_names.parquet", columns=["unitid", "branch", "address"])
        if listed is None:
            listed = pd.read_csv(provenance.REFERENCE_DIR / "medical_campuses.csv")
        if reviews is None:
            reviews = pd.read_csv(provenance.REFERENCE_DIR / "medical_campus_reviews.csv")
        pat = re.compile(cfg.MEDICAL_SCREEN_PATTERN, re.IGNORECASE)
        texts = defaultdict(set)
        for u, br, ad in names[["unitid", "branch", "address"]].itertuples(index=False):
            texts[int(u)].add(f"{'' if br is None or pd.isna(br) else br} {'' if ad is None or pd.isna(ad) else ad}")
        match = {u for u, ts in texts.items() if u % 1000 != 1 and any(pat.search(t) for t in ts)}
        cov = defaultdict(set)
        for df, src in ((listed, "listed"), (reviews, "reviewed")):
            for r in df.itertuples(index=False):
                for y in range(int(r.first_year), int(r.last_year) + 1):
                    cov[(int(r.unitid), y)].add(src if src == "listed" else f"reviewed:{getattr(r, 'decision', '')}")
        offs = set(spec["codes"]["criminal_xmvt"])
        fig = Counter()
        for (y, u, o), (on, res) in inputs["campus_on_res"].items():
            if o in offs and u in match:
                fig[(y, u)] += max(0, on - res)
        instN = Counter()
        for (y, b, o), vals in inputs["off"].items():
            if o in offs:
                instN[(y, b)] += vals[0]
        a, bden = spec["medical_screen_share"]
        cands = []
        for (y, u), f in sorted(fig.items()):
            b = u // 1000
            rec = inputs["inst"].get((y, b))
            if rec is None or single_year_reason(rec, y, spec, us) is not None:
                continue
            n = instN[(y, b)]
            if f >= spec["medical_screen_min_count"] and bden * f >= a * n:
                cands.append({"unitid": u, "year": y, "figure": f, "institutionN": n,
                              "share": round(f / n, 3) if n else None, "reviewed": sorted(cov.get((u, y), []))})
        unrev = [c for c in cands if not c["reviewed"]]
        by_campus = defaultdict(list)
        for c in unrev:
            by_campus[c["unitid"]].append(c)
        listing = []
        for u, cs in sorted(by_campus.items()):
            t = sorted(texts.get(u, []))
            listing.append({"unitid": u, "institution": inputs["inst"][(cs[-1]["year"], u // 1000)]["name"],
                            "names": t[:3], "years": [c["year"] for c in cs],
                            "figures": [c["figure"] for c in cs], "shares": [c["share"] for c in cs]})
        result.details["matching_campuses"] = len(match)
        result.details["candidate_campus_years"] = len(cands)
        result.details["reviewed_candidate_campus_years"] = len(cands) - len(unrev)
        result.details["unreviewed_campus_years"] = len(unrev)
        result.details["unreviewed"] = listing
        result.details["seconds"] = round(time.time() - t0, 1)
        print(f"  Name/address matches {len(match):,}; candidate campus-years {len(cands)} "
              f"(reviewed {len(cands) - len(unrev)}); unreviewed {len(unrev)} at {len(listing)} campuses")
        for x in listing[: (len(listing) if verbose else 5)]:
            print(f"    {x['unitid']} {x['institution']}: {x['names'][0] if x['names'] else ''} years {x['years']} "
                  f"shares {x['shares']}")
        if unrev:
            result.warning(f"{len(unrev)} unreviewed candidate campus-years at {len(listing)} campuses (first: "
                           f"{listing[0]['unitid']} {listing[0]['institution']} {listing[0]['years']}); review them "
                           "and add each to etl/reference/medical_campuses.csv or medical_campus_reviews.csv.")
        else:
            result.passed()
        print(f"  {result.status} ({result.details['seconds']} s)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        result.failed(f"{type(e).__name__}: {e}")
        print(f"  ERROR: {type(e).__name__}: {e}")
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
        audit_rate_rules,
        audit_rate_calibration,
        audit_medical_screen,
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
