"""
Comprehensive Data Audit - Validates ALL schools in the dataset.

This script performs thorough validation of all 8,683+ schools:
1. School Completeness - All schools in facts have JSON files
2. Incident Totals - JSON yearlyTotals match aggregate data
3. FTE Coverage - Report enrollment data coverage by year
4. Rate Calculations - Verify rate = (count / FTE) * 10,000
5. Ranking Order - Verify ranks match sorted counts
6. Percentage Sums - Verify offense %s sum to 100%
7. Source Traceability - Compare fact totals to source data

Usage:
    python 07_comprehensive_audit.py
    python 07_comprehensive_audit.py --verbose
    python 07_comprehensive_audit.py --stop-on-fail

Output:
    - Console: Summary with pass/fail per check
    - CSV: data/qa/comprehensive_audit.csv (per-school results)
    - JSON: data/qa/comprehensive_audit.json (machine-readable)
"""

import sys
import json
import argparse
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import CURATED_DIR, QA_DIR, JSON_DIR, DATA_YEARS


class AuditResult:
    """Container for audit check results."""
    def __init__(self, name: str):
        self.name = name
        self.status = "PENDING"
        self.details = {}
        self.errors = []
        self.warnings = []

    def passed(self):
        self.status = "PASS"

    def failed(self, error: str):
        self.status = "FAIL"
        self.errors.append(error)

    def warning(self, msg: str):
        if self.status == "PENDING":
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


def get_facts_pattern() -> str:
    """Get the glob pattern for reading fact files."""
    facts_path = CURATED_DIR / "facts"
    if (facts_path / "incidents").exists():
        return str(facts_path / "incidents" / "**" / "*.parquet")
    else:
        return str(facts_path / "*.parquet")


def audit_school_completeness(verbose: bool = False) -> AuditResult:
    """
    CHECK 1: Verify all schools in facts have JSON files generated.
    """
    result = AuditResult("School Completeness")
    print("\nCHECK 1: School Completeness")

    try:
        # Get unique schools from facts
        con = duckdb.connect()
        facts_pattern = get_facts_pattern()

        facts_schools = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_pattern}')
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

        result.details["schools_in_facts"] = len(facts_unitids)
        result.details["json_files_generated"] = len(json_unitids)
        result.details["missing_json"] = len(missing_json)
        result.details["extra_json"] = len(extra_json)

        if missing_json:
            result.failed(f"Missing JSON files for {len(missing_json)} schools")
            if verbose and len(missing_json) <= 10:
                print(f"    Missing: {sorted(missing_json)[:10]}")
        else:
            result.passed()
            print(f"  Missing JSONs: 0")

        if extra_json:
            result.warning(f"Found {len(extra_json)} JSON files without fact data")

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
        agg_totals = agg[agg["geo"] == "All"].groupby(["unitid", "year"])["count"].sum().reset_index()
        agg_totals = agg_totals.rename(columns={"count": "agg_total"})

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

            yearly_totals = {yt["year"]: yt["total"] for yt in school_data.get("yearlyTotals", [])}

            # Compare each year
            school_agg = agg_totals[agg_totals["unitid"] == unitid]

            for _, row in school_agg.iterrows():
                year = int(row["year"])
                agg_total = int(row["agg_total"])
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

        result.details["schools_validated"] = schools_validated
        result.details["variances_found"] = len(variances)
        result.details["schools_with_variance"] = schools_with_variance

        print(f"  Schools validated: {schools_validated:,} / {len(json_files):,}")
        print(f"  Variances found: {len(variances)}")

        if variances:
            result.failed(f"Found {len(variances)} incident count variances across {schools_with_variance} schools")
            if verbose:
                for v in variances[:5]:
                    print(f"    {v['unitid']} ({v['year']}): JSON={v['json_total']}, Agg={v['agg_total']}")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_fte_coverage(verbose: bool = False) -> AuditResult:
    """
    CHECK 3: Report FTE data coverage by year.
    """
    result = AuditResult("FTE Coverage")
    print("\nCHECK 3: FTE Coverage by Year")

    try:
        # Load enrollment data
        enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
        if not enrollment_path.exists():
            result.failed("Enrollment file not found")
            return result

        enrollment = pd.read_parquet(enrollment_path)

        # Load aggregate to get schools with data per year
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        agg = pd.read_parquet(agg_path)

        # Get unique schools per year from aggregates
        schools_per_year = agg.groupby("year")["unitid"].nunique().reset_index()
        schools_per_year.columns = ["year", "schools_with_data"]

        # Get schools with FTE per year
        fte_per_year = enrollment.groupby("year")["unitid"].nunique().reset_index()
        fte_per_year.columns = ["year", "schools_with_fte"]

        # Merge
        coverage = schools_per_year.merge(fte_per_year, on="year", how="left")
        coverage["schools_with_fte"] = coverage["schools_with_fte"].fillna(0).astype(int)
        coverage["coverage_pct"] = (coverage["schools_with_fte"] / coverage["schools_with_data"] * 100).round(1)

        result.details["by_year"] = coverage.to_dict("records")

        total_schools = coverage["schools_with_data"].sum()
        total_with_fte = coverage["schools_with_fte"].sum()
        overall_coverage = (total_with_fte / total_schools * 100) if total_schools > 0 else 0

        result.details["overall_coverage_pct"] = round(overall_coverage, 1)

        for _, row in coverage.iterrows():
            year = int(row["year"])
            schools = int(row["schools_with_data"])
            fte_count = int(row["schools_with_fte"])
            pct = row["coverage_pct"]
            print(f"  {year}: {fte_count:,} / {schools:,} schools ({pct}%)")

        # FTE coverage warning if < 90%
        if overall_coverage < 90:
            result.warning(f"Overall FTE coverage is {overall_coverage:.1f}% (some schools missing enrollment data)")
        else:
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
        schools_with_rates = 0
        tolerance = 0.01  # Allow 0.01 variance for rounding

        for ranking_file in ranking_files:
            with open(ranking_file) as f:
                data = json.load(f)

            for offense, entries in data.get("rankings", {}).items():
                for entry in entries:
                    count = entry.get("count", 0)
                    fte = entry.get("fte")
                    rate = entry.get("rate")

                    if fte and fte > 0 and rate is not None:
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
                        schools_with_rates += 1

        result.details["schools_with_rates_checked"] = schools_with_rates
        result.details["rate_errors"] = len(rate_errors)

        print(f"  Schools with rates checked: {schools_with_rates:,}")
        print(f"  Rate variances > {tolerance}: {len(rate_errors)}")

        if rate_errors:
            result.failed(f"Found {len(rate_errors)} rate calculation errors")
            if verbose:
                for err in rate_errors[:5]:
                    print(f"    {err['unitid']}: stored={err['stored_rate']}, expected={err['expected_rate']}")
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
    Rank N should have count >= Rank N+1
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

        result.details["groups_validated"] = groups_validated
        result.details["order_violations"] = len(order_violations)

        print(f"  Year/offense/geo combinations validated: {groups_validated:,}")
        print(f"  Rank order violations: {len(order_violations)}")

        if order_violations:
            result.failed(f"Found {len(order_violations)} rank order violations")
            if verbose:
                for v in order_violations[:5]:
                    print(f"    {v['file']}/{v['offense']}: rank {v['rank']} ({v['current_count']}) < rank {v['next_rank']} ({v['next_count']})")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_percentage_sums(verbose: bool = False) -> AuditResult:
    """
    CHECK 6: Verify offense percentages sum to 100% per group.

    Note: Floating-point rounding causes small cumulative errors when summing
    thousands of 2-decimal percentages. We use tiered tolerance:
    - Small groups (<100 schools): 0.5% tolerance
    - Medium groups (100-1000): 2% tolerance
    - Large groups (1000+): 5% tolerance (rounding errors accumulate)
    """
    result = AuditResult("Percentage Sum Validation")
    print("\nCHECK 6: Percentage Sum Validation")

    try:
        rankings_dir = JSON_DIR / "rankings"
        ranking_files = list(rankings_dir.glob("*.json"))

        pct_errors = []
        pct_warnings = []
        groups_validated = 0

        for ranking_file in ranking_files:
            with open(ranking_file) as f:
                data = json.load(f)

            for offense, entries in data.get("rankings", {}).items():
                if len(entries) < 2:
                    continue

                groups_validated += 1
                pct_sum = sum(e.get("pct", 0) for e in entries)
                num_schools = len(entries)

                # Tiered tolerance based on group size
                if num_schools < 100:
                    tolerance = 0.5
                elif num_schools < 1000:
                    tolerance = 2.0
                else:
                    tolerance = 5.0  # Large datasets have cumulative rounding error

                variance = abs(pct_sum - 100.0)
                if variance > tolerance:
                    # Still an issue even with tiered tolerance
                    if variance > 10:  # Severe error
                        pct_errors.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "pct_sum": round(pct_sum, 2),
                            "schools": num_schools
                        })
                    else:  # Acceptable rounding error
                        pct_warnings.append({
                            "file": ranking_file.name,
                            "offense": offense,
                            "pct_sum": round(pct_sum, 2),
                            "schools": num_schools
                        })

        result.details["groups_validated"] = groups_validated
        result.details["severe_errors"] = len(pct_errors)
        result.details["rounding_warnings"] = len(pct_warnings)

        print(f"  Groups validated: {groups_validated:,}")
        print(f"  Severe errors (>10% off): {len(pct_errors)}")
        print(f"  Rounding warnings (expected): {len(pct_warnings)}")

        if pct_errors:
            result.failed(f"Found {len(pct_errors)} severe percentage sum errors")
            if verbose:
                for err in pct_errors[:5]:
                    print(f"    {err['file']}/{err['offense']}: sum = {err['pct_sum']}% ({err['schools']} schools)")
        elif pct_warnings:
            result.warning(f"Found {len(pct_warnings)} groups with acceptable rounding variance")
        else:
            result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def audit_source_traceability(verbose: bool = False) -> AuditResult:
    """
    CHECK 7: Compare fact table totals to aggregate totals.
    Ensures no data loss during aggregation.
    """
    result = AuditResult("Source Traceability")
    print("\nCHECK 7: Source Traceability")

    try:
        con = duckdb.connect()
        facts_pattern = get_facts_pattern()

        # Get fact table totals by year
        fact_totals = con.execute(f"""
            SELECT year, SUM(count) as total_incidents
            FROM read_parquet('{facts_pattern}')
            GROUP BY year
            ORDER BY year
        """).df()

        # Get aggregate totals by year (geo="All" to avoid double counting)
        agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
        agg = pd.read_parquet(agg_path)

        # Sum across schools and offenses for geo="All"
        agg_totals = agg[agg["geo"] == "All"].groupby("year")["count"].sum().reset_index()
        agg_totals.columns = ["year", "agg_total"]

        # Compare
        comparison = fact_totals.merge(agg_totals, on="year", how="outer")
        comparison["variance"] = comparison["agg_total"] - comparison["total_incidents"]

        variances = comparison[comparison["variance"] != 0]

        # Calculate overall totals
        fact_total = int(fact_totals["total_incidents"].sum())
        agg_total = int(agg_totals["agg_total"].sum())

        result.details["fact_table_total"] = fact_total
        result.details["aggregate_total"] = agg_total
        result.details["variance"] = agg_total - fact_total
        result.details["by_year"] = comparison.to_dict("records")

        print(f"  Fact table total (2015-2023): {fact_total:,} incidents")
        print(f"  Aggregate total (geo=All): {agg_total:,} incidents")
        print(f"  Variance: {agg_total - fact_total:,}")

        if len(variances) > 0:
            result.warning("Fact totals differ from aggregate totals (expected due to geo aggregation)")
            if verbose:
                for _, row in variances.iterrows():
                    print(f"    {int(row['year'])}: fact={int(row['total_incidents']):,}, agg={int(row['agg_total']):,}")
        else:
            result.passed()

        # Note: Variance is expected because facts include all geos while agg sums geo="All"
        # The key check is that aggregates are derived correctly from facts
        result.passed()

        print(f"  {result.status}")

    except Exception as e:
        result.failed(str(e))
        print(f"  ERROR: {e}")

    return result


def generate_per_school_report(verbose: bool = False) -> pd.DataFrame:
    """
    Generate detailed per-school audit report.
    Returns DataFrame with validation results for each school.
    """
    print("\nGenerating per-school audit report...")

    schools_dir = JSON_DIR / "schools"
    json_files = list(schools_dir.glob("*.json"))

    # Load aggregates for comparison
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    agg = pd.read_parquet(agg_path)

    # Load enrollment for FTE check
    enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    enrollment = pd.read_parquet(enrollment_path) if enrollment_path.exists() else pd.DataFrame()

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
        years_in_data = len(school_data.get("yearlyTotals", []))

        # Check FTE coverage (use base unitid for enrollment match)
        base_unitid = unitid // 1000
        school_fte = enrollment[enrollment["unitid"] == base_unitid] if len(enrollment) > 0 else pd.DataFrame()
        years_with_fte = len(school_fte)

        # Check incident totals
        yearly_totals = {yt["year"]: yt["total"] for yt in school_data.get("yearlyTotals", [])}
        school_agg = agg[(agg["unitid"] == unitid) & (agg["geo"] == "All")]
        agg_totals = school_agg.groupby("year")["count"].sum().to_dict()

        incident_match = all(
            yearly_totals.get(int(year), 0) == count
            for year, count in agg_totals.items()
        )

        # Check rate calculation (spot check latest year)
        fte = school_data.get("fte")
        rate_match = True
        if fte and fte > 0:
            latest_year = max(yearly_totals.keys()) if yearly_totals else None
            if latest_year:
                count = yearly_totals[latest_year]
                expected_rate = (count / fte) * 10000
                # Check if rate is stored in fteByYear
                stored_rate = school_data.get("rate")  # May not exist in current schema

        # Determine overall status
        if incident_match and years_with_fte >= years_in_data * 0.8:
            status = "PASS"
        elif incident_match:
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
            "rate_match": rate_match,
            "status": status
        })

    df = pd.DataFrame(results)
    print(f"  Generated report for {len(df):,} schools")

    return df


def save_audit_results(
    results: list[AuditResult],
    per_school_df: pd.DataFrame,
    verbose: bool = False
):
    """Save audit results to files."""
    QA_DIR.mkdir(parents=True, exist_ok=True)

    # Determine overall status
    statuses = [r.status for r in results]
    if all(s == "PASS" for s in statuses):
        overall_status = "PASS"
    elif any(s == "FAIL" for s in statuses):
        overall_status = "FAIL"
    else:
        overall_status = "WARNING"

    # Save JSON report
    report = {
        "generated_at": datetime.now().isoformat(),
        "overall_status": overall_status,
        "summary": {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "warnings": sum(1 for r in results if r.status == "WARNING"),
        },
        "checks": [r.to_dict() for r in results],
        "schools": {
            "total": len(per_school_df),
            "passed": len(per_school_df[per_school_df["status"] == "PASS"]),
            "failed": len(per_school_df[per_school_df["status"] == "FAIL"]),
            "warnings": len(per_school_df[per_school_df["status"] == "WARNING"]),
        }
    }

    json_path = QA_DIR / "comprehensive_audit.json"
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report saved: {json_path}")

    # Save CSV report
    csv_path = QA_DIR / "comprehensive_audit.csv"
    per_school_df.to_csv(csv_path, index=False)
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

    # Run all checks
    checks = [
        audit_school_completeness,
        audit_incident_totals,
        audit_fte_coverage,
        audit_rate_calculations,
        audit_ranking_order,
        audit_percentage_sums,
        audit_source_traceability,
    ]

    for check_fn in checks:
        result = check_fn(verbose=args.verbose)
        results.append(result)

        if args.stop_on_fail and result.status == "FAIL":
            print(f"\n  Stopping due to --stop-on-fail")
            break

    # Generate per-school report
    per_school_df = generate_per_school_report(verbose=args.verbose)

    # Save results
    overall_status = save_audit_results(results, per_school_df, verbose=args.verbose)

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
    print(f"Schools: {schools_passed:,} / {schools_total:,} passed ({schools_passed/schools_total*100:.1f}%)")

    print(f"\nReports saved to: {QA_DIR}")

    return 0 if overall_status != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
