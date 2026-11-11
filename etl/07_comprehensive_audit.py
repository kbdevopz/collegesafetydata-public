"""
Comprehensive Data Audit - Validates ALL schools in the dataset.

This script performs thorough validation of all schools:
1. School Completeness - All schools in facts have JSON files
2. Incident Totals - JSON yearlyTotals match aggregate data
3. FTE Coverage - Report enrollment data coverage by year
4. Rate Calculations - Verify rate = (count / FTE) * 10,000
5. Ranking Order - Verify ranks match sorted counts, and rankByRate sorted rates
6. Percentage Sums - Verify each offense % is count / group total, to 2 decimals
7. Aggregate Consistency - Aggregates equal the fact table, per year and geography
8. Shared Statistics - Figures two campuses report identically are counted
   once in rankings and totals, under one host, and school files say so

Each check's details say in "what_it_checks" exactly what it verifies. All of
them compare the pipeline's own files with each other; none re-reads the DOE
or IPEDS downloads.

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
import argparse
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, QA_DIR, JSON_DIR, DATA_YEARS, PROJECT_ROOT, GEO_CODES, GEO_FOR_ALL,
                    OFFENSE_ORDER, SHARED_MIN_NONZERO, US_STATES)
import provenance

# Curated files the checks read (relative to data/curated)
CURATED_READ = ("facts/incidents.parquet", "aggs/agg_school_year_offense.parquet", "dims/dim_enrollment.parquet",
                "dims/dim_institution.parquet", "dims/campus_year_sources.parquet", "aggs/shared_blocks.parquet")
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


def audit_school_completeness(verbose: bool = False) -> AuditResult:
    """
    CHECK 1: Verify all schools in facts have JSON files generated.
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

        facts_unitids = set(facts_schools["unitid"].tolist())
        print(f"  Schools in facts: {len(facts_unitids):,}")

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
        missing_json = facts_unitids - json_unitids
        extra_json = json_unitids - facts_unitids

        result.details["what_it_checks"] = (
            "Every school (UNITID) in data/curated/facts/incidents.parquet has a site file "
            "schools/<UNITID>.json, and every school file has fact data. It compares file names "
            "only; check 2 and the per-school report compare the files' numbers.")
        result.details["schools_in_facts"] = len(facts_unitids)
        result.details["json_files_generated"] = len(json_unitids)
        result.details["missing_json"] = len(missing_json)
        result.details["extra_json"] = len(extra_json)

        if not facts_unitids:
            result.failed("The fact table has no schools. Run 02_transform_to_parquet.py and 03 to 07 again.")
        if missing_json:
            result.failed(f"Missing JSON files for {len(missing_json)} schools")
            if verbose and len(missing_json) <= 10:
                print(f"    Missing: {sorted(missing_json)[:10]}")
        else:
            result.passed()
            print(f"  Missing JSONs: 0")

        if extra_json:
            result.warning(f"Found {len(extra_json)} JSON files without fact data "
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

        variances = []
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
            "For every site school file schools/<UNITID>.json, the yearlyTotals total of each year "
            "(every year in the file or the aggregates) equals the sum over offenses of that school's "
            "geo \"All\" rows in agg_school_year_offense.parquet. The files' trends and breakdowns are "
            "not compared, and check 7 compares the aggregates with the fact table.")
        result.details["schools_validated"] = schools_validated
        result.details["variances_found"] = len(variances)
        result.details["schools_with_variance"] = schools_with_variance

        print(f"  Schools validated: {schools_validated:,} / {len(json_files):,}")
        print(f"  Variances found: {len(variances)}")

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
        else:
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


def audit_rate_calculations(verbose: bool = False) -> AuditResult:
    """
    CHECK 4: Verify rate calculations are mathematically correct.
    rate = (count / FTE) * 10,000
    """
    result = AuditResult("Rate Calculation Accuracy")
    print("\nCHECK 4: Rate Calculation Accuracy")

    try:
        # Check rankings files for rate accuracy
        rankings_dir = JSON_DIR / "rankings"
        ranking_files = list(rankings_dir.glob("*.json"))

        rate_errors = []
        entries_checked = 0
        tolerance = 0.01  # Allow 0.01 variance for rounding

        for ranking_file in ranking_files:
            with open(ranking_file) as f:
                data = json.load(f)

            for offense, entries in data.get("rankings", {}).items():
                for entry in entries:
                    count = entry.get("count", 0)
                    fte = entry.get("fte")
                    rate = entry.get("rate")
                    has_fte = bool(fte) and fte > 0

                    # A rate needs an FTE, and an FTE above 0 gives a rate
                    if has_fte != (rate is not None):
                        rate_errors.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "unitid": entry.get("unitid"),
                            "count": count,
                            "fte": fte,
                            "stored_rate": rate,
                            "expected_rate": None,
                            "variance": None,
                            "problem": "a rate without an FTE above 0" if rate is not None else "an FTE but no rate",
                        })
                    elif has_fte:
                        expected_rate = (count / fte) * 10000
                        if abs(rate - expected_rate) > tolerance:
                            rate_errors.append({
                                "file": ranking_file.name,
                                "offense": offense,
                                "unitid": entry.get("unitid"),
                                "count": count,
                                "fte": fte,
                                "stored_rate": rate,
                                "expected_rate": round(expected_rate, 2),
                                "variance": round(rate - expected_rate, 4)
                            })
                        entries_checked += 1

        result.details["what_it_checks"] = (
            "For every entry of rankings/*.json, rate equals count / fte x 10,000 to within 0.01, using "
            "the entry's own count and fte; an entry with a rate but no FTE above 0, or with an FTE "
            "but no rate, is an error. It does not compare the count or FTE with the aggregates or IPEDS.")
        result.details["ranking_entries_checked"] = entries_checked
        result.details["rate_errors"] = len(rate_errors)

        print(f"  Ranking entries with a rate checked: {entries_checked:,}")
        print(f"  Rate variances > {tolerance}, or a rate without an FTE (or the reverse): {len(rate_errors)}")

        if rate_errors:
            err = rate_errors[0]
            what = err.get("problem") or f"expected {err['expected_rate']}"
            result.failed(f"Found {len(rate_errors)} rate calculation errors (first: {err['file']} {err['offense']} "
                          f"{err['unitid']}: count {err['count']}, fte {err['fte']}, rate {err['stored_rate']}, "
                          f"{what}). Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for err in rate_errors[:5]:
                    print(f"    {err['unitid']}: stored={err['stored_rate']}, "
                          f"{err.get('problem') or 'expected=' + str(err['expected_rate'])}")
        elif entries_checked == 0:
            result.failed(f"No ranking entry with a rate in {rankings_dir} to check. Run 04_create_aggregates.py "
                          f"and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_ranking_order(verbose: bool = False) -> AuditResult:
    """
    CHECK 5: Verify ranks match sorted incident counts.
    Rank N should have count >= Rank N+1, and the ranks run 1..N. Likewise
    rankByRate runs 1..M over the entries with a rate, with rates non-increasing.
    """
    result = AuditResult("Ranking Order Validation")
    print("\nCHECK 5: Ranking Order Validation")

    try:
        rankings_dir = JSON_DIR / "rankings"
        ranking_files = list(rankings_dir.glob("*.json"))

        order_violations = []
        groups_validated = 0

        for ranking_file in ranking_files:
            with open(ranking_file) as f:
                data = json.load(f)

            for offense, entries in data.get("rankings", {}).items():
                if len(entries) < 2:
                    continue

                groups_validated += 1

                # Sort by rank
                sorted_entries = sorted(entries, key=lambda x: x.get("rank", 999))

                # Check order (higher rank = lower count)
                for i in range(len(sorted_entries) - 1):
                    current = sorted_entries[i]
                    next_entry = sorted_entries[i + 1]

                    if current.get("count", 0) < next_entry.get("count", 0):
                        order_violations.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "rank": current.get("rank"),
                            "current_count": current.get("count"),
                            "next_rank": next_entry.get("rank"),
                            "next_count": next_entry.get("count")
                        })

                # Ranks are 1..N (a missing or repeated rank cannot be in order)
                ranks = sorted(e.get("rank") for e in entries if isinstance(e.get("rank"), int))
                if ranks != list(range(1, len(entries) + 1)):
                    order_violations.append({"file": ranking_file.name, "offense": offense,
                                             "problem": "rank does not run 1..N"})

                # rankByRate: 1..M over exactly the entries with a rate, rates non-increasing
                rated = [e for e in entries if e.get("rate") is not None]
                by_rate = sorted((e for e in rated if isinstance(e.get("rankByRate"), int)),
                                 key=lambda x: x["rankByRate"])
                if (any(e.get("rankByRate") is not None for e in entries if e.get("rate") is None)
                        or [e["rankByRate"] for e in by_rate] != list(range(1, len(rated) + 1))):
                    order_violations.append({"file": ranking_file.name, "offense": offense,
                                             "problem": "rankByRate does not run 1..M over the entries with a rate"})
                for current, next_entry in zip(by_rate, by_rate[1:]):
                    if current["rate"] < next_entry["rate"]:
                        order_violations.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "problem": (f"rankByRate {current['rankByRate']} (rate {current['rate']}) < "
                                        f"rankByRate {next_entry['rankByRate']} (rate {next_entry['rate']})"),
                        })

        result.details["what_it_checks"] = (
            "In every ranking group (one offense of one rankings/*.json file) of 2 or more entries, rank "
            "runs 1..N with counts non-increasing, and rankByRate runs 1..M over exactly the entries with "
            "a rate, with rates non-increasing. It checks the order of each file's own counts and rates; "
            "check 4 checks the rates' arithmetic.")
        result.details["groups_validated"] = groups_validated
        result.details["order_violations"] = len(order_violations)

        print(f"  Ranking groups (file x offense) validated: {groups_validated:,}")
        print(f"  Rank order violations: {len(order_violations)}")

        def describe(v):
            return v.get("problem") or (f"rank {v['rank']} ({v['current_count']}) < "
                                        f"rank {v['next_rank']} ({v['next_count']})")

        if order_violations:
            v = order_violations[0]
            result.failed(f"Found {len(order_violations)} rank order violations (first: {v['file']}/{v['offense']}: "
                          f"{describe(v)}). Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for v in order_violations[:5]:
                    print(f"    {v['file']}/{v['offense']}: {describe(v)}")
        elif groups_validated == 0:
            result.failed(f"No ranking groups in {rankings_dir} to check. Run 04_create_aggregates.py "
                          f"and 05_generate_json.py.")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_percentage_sums(verbose: bool = False) -> AuditResult:
    """
    CHECK 6: Verify each offense percentage is the entry's share of its group.

    04/05 write pct = count / group total x 100 rounded to 2 decimals, so each
    pct must be within half a hundredth (PCT_TOLERANCE) of that share. A
    group's pcts then sum to 100% give or take only that rounding, which can
    add up to several percent in a group of thousands of schools; the largest
    such deviation is reported for information only, since the per-entry test
    is what tells rounding apart from an error. The file's "totals" entry for
    the offense, when there is one, must equal the group's count sum.
    """
    result = AuditResult("Percentage Sum Validation")
    print("\nCHECK 6: Percentage Sum Validation")

    try:
        rankings_dir = JSON_DIR / "rankings"
        ranking_files = list(rankings_dir.glob("*.json"))

        pct_errors = []
        groups_validated = 0
        entries_checked = 0
        max_sum_deviation = 0.0

        for ranking_file in ranking_files:
            with open(ranking_file) as f:
                data = json.load(f)
            totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}

            for offense, entries in data.get("rankings", {}).items():
                if not entries:
                    continue

                groups_validated += 1
                group_total = sum(e.get("count", 0) for e in entries)
                if offense in totals and totals[offense] != group_total:
                    pct_errors.append({
                        "file": ranking_file.name,
                        "offense": offense,
                        "problem": f"totals says {totals[offense]}, the counts sum to {group_total}",
                    })
                for e in entries:
                    entries_checked += 1
                    pct = e.get("pct")
                    share = e.get("count", 0) / group_total * 100 if group_total else 0.0
                    if not isinstance(pct, (int, float)) or abs(pct - share) > PCT_TOLERANCE:
                        pct_errors.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "problem": (f"{e.get('unitid')}: pct {pct}, but count {e.get('count')} of "
                                        f"{group_total} is {share:.4f}%"),
                        })
                if group_total:
                    pct_sum = sum(e.get("pct", 0) for e in entries if isinstance(e.get("pct"), (int, float)))
                    max_sum_deviation = max(max_sum_deviation, abs(pct_sum - 100.0))

        result.details["what_it_checks"] = (
            "In every ranking group (one offense of one rankings/*.json file), each entry's pct equals its "
            "count / the group's count sum x 100 to 2 decimals (within 0.005), and the file's totals entry "
            "equals that sum. Group pct sums differ from 100% only by that rounding; the largest difference "
            "is shown. It checks the files' own counts, not the counts against the aggregates.")
        result.details["groups_validated"] = groups_validated
        result.details["entries_checked"] = entries_checked
        result.details["pct_errors"] = len(pct_errors)
        result.details["max_sum_deviation_pct"] = round(max_sum_deviation, 2)

        print(f"  Groups validated: {groups_validated:,} ({entries_checked:,} entries)")
        print(f"  Entries whose pct is not count / group total (to 2 decimals), or wrong totals: {len(pct_errors)}")
        print(f"  Largest difference of a group's pct sum from 100% (rounding only): {max_sum_deviation:.2f}")

        if pct_errors:
            err = pct_errors[0]
            result.failed(f"Found {len(pct_errors)} percentage errors (first: {err['file']}/{err['offense']}: "
                          f"{err['problem']}). Run 04_create_aggregates.py and 05_generate_json.py, then 07 again.")
            if verbose:
                for err in pct_errors[:5]:
                    print(f"    {err['file']}/{err['offense']}: {err['problem']}")
        elif groups_validated == 0:
            result.failed(f"No ranking groups in {rankings_dir} to check. Run 04_create_aggregates.py "
                          f"and 05_generate_json.py.")
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

    From the fact table, by the rule in config.py (SHARED_MIN_NONZERO), it
    finds the copy blocks again, without 04's code: per year and geography
    of GEO_FOR_ALL, campuses in the same ranked state whose cells for all
    offenses in OFFENSE_ORDER are equal (blank = 0), at least
    SHARED_MIN_NONZERO of them not 0. aggs/shared_blocks.parquet must hold
    exactly those blocks in exactly those groups, with one host per group,
    the first campus by 04's order (find_shared_blocks: not restored from an
    older release, main campus, larger FTE, larger campus-year total, lower
    UNITID), and every other member a shadow pointing to it. Then:
      - every entry of every rankings/*.json counts the school's facts
        without its shadow blocks, and the state and national files rank
        exactly the schools of their state(s) with such a count above 0;
      - every school file's sharedFigures lists exactly its shadow blocks,
        with the host's UNITID and the name of the host's school file.
    """
    result = AuditResult("Shared Statistics Counted Once")
    print("\nCHECK 8: Shared Statistics Counted Once")

    try:
        facts = pd.read_parquet(get_facts_path(), columns=["year", "unitid", "offense", "geo", "count"])
        inst = read_curated("dims/dim_institution.parquet", "03_build_dimensions.py", ["unitid", "state"])
        sources = read_curated("dims/campus_year_sources.parquet", "02_transform_to_parquet.py")
        enrollment = read_curated("dims/dim_enrollment.parquet", "02a_transform_enrollment.py",
                                  ["unitid", "year", "fte"])
        shared = read_curated("aggs/shared_blocks.parquet", "04_create_aggregates.py")
        result.details["what_it_checks"] = (
            "From data/curated/facts/incidents.parquet, without 04's code: the blocks (one campus, year "
            "and geography of On-campus, Non-campus, Public property; one cell per offense, blank = 0) "
            f"that campuses of the same ranked state report identically, at least {SHARED_MIN_NONZERO} "
            "cells not 0. aggs/shared_blocks.parquet must hold exactly those blocks and groups, with one "
            "host per group chosen by 04's order and every other member a shadow of it. Every "
            "rankings/*.json entry must count the school's facts without its shadow blocks, the state and "
            "national files must rank exactly the schools with such a count, and each school file's "
            "sharedFigures must list exactly its shadow blocks and their host.")

        problems = []

        def problem(text):
            problems.append(text)

        state = {int(u): s for u, s in zip(inst["unitid"].tolist(), inst["state"].tolist())}
        rows = facts[facts["geo"].isin(GEO_FOR_ALL)]
        unknown = sorted(set(rows["offense"]) - set(OFFENSE_ORDER))
        if unknown:
            raise RuntimeError(f"The facts hold offenses not in OFFENSE_ORDER ({', '.join(unknown)}). "
                               "Add them to OFFENSE_ORDER in config.py, then run 04 to 07 again.")
        cell_of = {o: i for i, o in enumerate(OFFENSE_ORDER)}

        # Every block's cells, and each campus-year's total over GEO_FOR_ALL
        cells = {}
        campus_total = {}
        for y, u, o, g, c in zip(rows["year"].tolist(), rows["unitid"].tolist(), rows["offense"].tolist(),
                                 rows["geo"].tolist(), rows["count"].tolist()):
            key = (int(y), g, int(u))
            cells.setdefault(key, [0] * len(OFFENSE_ORDER))[cell_of[o]] += int(c)
            campus_total[(int(u), int(y))] = campus_total.get((int(u), int(y)), 0) + int(c)

        # The copy groups, found again
        by_cells = {}
        for (y, g, u), v in cells.items():
            if sum(1 for c in v if c != 0) >= SHARED_MIN_NONZERO and state.get(u) in US_STATES:
                by_cells.setdefault((y, g, state[u], tuple(v)), []).append(u)
        expected =[(y, g, sorted(us)) for (y, g, _st, _v), us in by_cells.items() if len(us) >= 2]

        # 04's host order
        restored = {(int(u), int(y)): bool(r) for u, y, r in zip(sources["unitid"].tolist(), sources["year"].tolist(),
                                                                  sources["restored"].tolist())}
        fte = {(int(u), int(y)): float(f) for u, y, f in zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(),
                                                             enrollment["fte"].tolist()) if pd.notna(f)}

        def host_order(u, y):
            if (u, y) not in restored:
                raise RuntimeError(f"campus_year_sources.parquet has no release for {u} in {y}, which has fact "
                                   "rows. Run 02_transform_to_parquet.py and 03 to 07 again.")
            f = fte.get((u // 1000, y))
            return (restored[(u, y)], u % 1000 != 1, -f if f is not None else float("inf"),
                    -campus_total[(u, y)], u)

        expected_role = {}  # (year, geo, unitid) -> host UNITID
        expected_members = {}  # frozenset of (year, geo, unitid) of one group
        for y, g, us in expected:
            host = min(us, key=lambda u: host_order(u, y))
            members = frozenset((y, g, u) for u in us)
            expected_members[members] = host
            for u in us:
                expected_role[(y, g, u)] = host

        # aggs/shared_blocks.parquet, against them
        actual_groups = {}
        actual_host = {}
        for y, g, grp, u, role, h in zip(shared["year"].tolist(), shared["geo"].tolist(), shared["group"].tolist(),
                                         shared["unitid"].tolist(), shared["role"].tolist(),
                                         shared["host_unitid"].tolist()):
            key = (int(y), g, int(u))
            if key in actual_host:
                problem(f"shared_blocks.parquet lists {u} {y} {g} twice")
            actual_host[key] = (role, int(h))
            actual_groups.setdefault(int(grp), set()).add(key)
        missing = sorted(set(expected_role) - set(actual_host))
        extra = sorted(set(actual_host) - set(expected_role))
        if missing:
            problem(f"{len(missing)} copied blocks are not in shared_blocks.parquet (first: {missing[0]})")
        if extra:
            problem(f"{len(extra)} blocks in shared_blocks.parquet are not copies (first: {extra[0]})")
        groups_found = {frozenset(m) for m in actual_groups.values()}
        if groups_found != set(expected_members):
            problem("shared_blocks.parquet groups the blocks differently from the facts")
        for members in groups_found & set(expected_members):
            host = expected_members[members]
            hosts = [k for k in members if actual_host[k][0] == "host"]
            if [k[2] for k in hosts] != [host]:
                problem(f"group of {min(members)}: host {[k[2] for k in hosts]}, expected {host}")
            for k in members:
                role, h = actual_host[k]
                if h != host or role != ("host" if k[2] == host else "shadow"):
                    problem(f"{k}: role {role} with host {h}, expected host {host}")
        shadows = {k for k, (role, _h) in actual_host.items() if role == "shadow"}

        # What totals and rankings count: the facts without the shadow blocks
        counted = {}
        for (y, g, u), v in cells.items():
            if (y, g, u) in shadows:
                continue
            for o, c in zip(OFFENSE_ORDER, v):
                if c:
                    counted[(y, u, o)] = counted.get((y, u, o), 0) + c
                    counted[(y, u, "all")] = counted.get((y, u, "all"), 0) + c
        code_of = {o: o.lower().replace(" ", "_") for o in OFFENSE_ORDER}
        code_of["all"] = "all"
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
                        diff = sorted(should ^ have)
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
                                 "groups": len({frozenset(m) for m in groups_found if min(m)[0] == year}),
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
        result.details["copy_groups"] = len(groups_found)
        result.details["shadow_blocks"] = len(shadows)
        result.details["shadow_counts"] = sum(shadow_counts.values())
        result.details["by_year"] = rows_by_year
        result.details["ranking_entries_checked"] = entries_checked
        result.details["schools_with_shared_figures"] = len(notes_found)
        result.details["problems"] = len(problems)

        print(f"  Copy groups: {len(groups_found):,}; shadow blocks: {len(shadows):,} "
              f"({sum(shadow_counts.values()):,} counts, each counted once under its host)")
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


def generate_per_school_report(verbose: bool = False) -> pd.DataFrame:
    """
    Generate detailed per-school audit report.
    Returns DataFrame with validation results for each school file:
      incident_match: yearlyTotals equal the aggregates' geo "All" totals in
        every year of either (as check 2).
      fte_match: fteByYear, the FTE the school page's rates use, and fte (its
        newest year) equal dim_enrollment's FTE for the school's base UNITID
        in each year it has aggregate data (the FTE 04 joins).
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
    agg_years = {}  # unitid -> years with any aggregate row, as 05 reads them (DATA_YEARS only)
    in_years = agg[agg["year"].isin(DATA_YEARS)]
    for uid, year in zip(in_years["unitid"].tolist(), in_years["year"].tolist()):
        agg_years.setdefault(int(uid), set()).add(int(year))

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
        audit_percentage_sums,
        audit_aggregate_consistency,
        audit_shared_statistics,
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
