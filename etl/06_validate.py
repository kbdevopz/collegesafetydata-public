"""
Validate data quality and generate QA report.

This script runs various data quality checks:
- Row counts per year
- No negative counts
- All Ivy League schools present
- Offense coverage
- JSON file integrity

Usage:
    python 06_validate.py
    python 06_validate.py --verbose
"""

import sys
import json
import argparse
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import CURATED_DIR, QA_DIR, JSON_DIR, IVY_LEAGUE, DATA_YEARS


class ValidationError(Exception):
    """Raised when a validation check fails."""
    pass


def get_facts_pattern() -> str:
    """Get the glob pattern for reading fact files."""
    facts_path = CURATED_DIR / "facts"

    if (facts_path / "incidents").exists():
        return str(facts_path / "incidents" / "**" / "*.parquet")
    else:
        return str(facts_path / "*.parquet")


def validate_facts(verbose: bool = False) -> dict:
    """Run data quality checks on fact table."""
    print("Validating fact table...")

    checks = {
        "fact_table": {
            "status": "PENDING",
            "checks": {}
        }
    }

    con = duckdb.connect()
    facts_pattern = get_facts_pattern()

    try:
        # Check 1: Row counts per year
        print("  Checking row counts by year...")
        year_counts = con.execute(f"""
            SELECT year, COUNT(*) as records, SUM(count) as total_incidents
            FROM read_parquet('{facts_pattern}')
            GROUP BY year
            ORDER BY year
        """).df()

        checks["fact_table"]["checks"]["year_counts"] = year_counts.to_dict('records')

        if verbose:
            print("    Year counts:")
            for _, row in year_counts.iterrows():
                print(f"      {row['year']}: {row['records']:,} records, {row['total_incidents']:,} incidents")

        # Check 2: No negative counts
        print("  Checking for negative counts...")
        negative_counts = con.execute(f"""
            SELECT COUNT(*) as negative_records
            FROM read_parquet('{facts_pattern}')
            WHERE count < 0
        """).fetchone()[0]

        checks["fact_table"]["checks"]["negative_counts"] = int(negative_counts)

        if negative_counts > 0:
            raise ValidationError(f"Found {negative_counts} records with negative counts!")

        print(f"    No negative counts found")

        # Check 3: All Ivy League schools present
        print("  Checking Ivy League coverage...")
        ivy_check = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_pattern}')
            WHERE unitid IN ({', '.join(str(u) for u in IVY_LEAGUE.keys())})
        """).df()

        ivy_found = set(ivy_check["unitid"].tolist())
        ivy_expected = set(IVY_LEAGUE.keys())
        ivy_missing = ivy_expected - ivy_found

        checks["fact_table"]["checks"]["ivy_schools_found"] = len(ivy_found)
        checks["fact_table"]["checks"]["ivy_schools_missing"] = list(ivy_missing)

        if ivy_missing:
            missing_names = [IVY_LEAGUE[u]["name"] for u in ivy_missing]
            print(f"    WARNING: Missing Ivy schools: {missing_names}")
        else:
            print(f"    All {len(ivy_found)} Ivy League schools present")

        # Check 4: Offense coverage
        print("  Checking offense coverage...")
        offenses = con.execute(f"""
            SELECT
                offense,
                offense_family,
                COUNT(DISTINCT year) as years_present,
                SUM(count) as total_count
            FROM read_parquet('{facts_pattern}')
            GROUP BY offense, offense_family
            ORDER BY total_count DESC
        """).df()

        checks["fact_table"]["checks"]["offense_count"] = len(offenses)
        checks["fact_table"]["checks"]["top_offenses"] = offenses.head(10).to_dict('records')

        if verbose:
            print("    Top 5 offenses:")
            for _, row in offenses.head(5).iterrows():
                print(f"      {row['offense']}: {row['total_count']:,} total")

        # Check 5: Geography coverage
        print("  Checking geography coverage...")
        geos = con.execute(f"""
            SELECT
                geo,
                COUNT(*) as records,
                SUM(count) as total_count
            FROM read_parquet('{facts_pattern}')
            GROUP BY geo
            ORDER BY total_count DESC
        """).df()

        checks["fact_table"]["checks"]["geographies"] = geos.to_dict('records')

        if verbose:
            print("    Geographies:")
            for _, row in geos.iterrows():
                print(f"      {row['geo']}: {row['total_count']:,}")

        checks["fact_table"]["status"] = "PASS"
        print("  Fact table validation: PASS")

    except ValidationError as e:
        checks["fact_table"]["status"] = "FAIL"
        checks["fact_table"]["error"] = str(e)
        print(f"  Fact table validation: FAIL - {e}")

    except Exception as e:
        checks["fact_table"]["status"] = "ERROR"
        checks["fact_table"]["error"] = str(e)
        print(f"  Fact table validation: ERROR - {e}")

    return checks


def validate_aggregates(verbose: bool = False) -> dict:
    """Validate aggregate tables."""
    print("\nValidating aggregates...")

    checks = {
        "aggregates": {
            "status": "PENDING",
            "checks": {}
        }
    }

    agg_dir = CURATED_DIR / "aggs"

    # Check school-year-offense aggregate
    agg_path = agg_dir / "agg_school_year_offense.parquet"
    if agg_path.exists():
        agg = pd.read_parquet(agg_path)
        checks["aggregates"]["checks"]["school_year_offense"] = {
            "exists": True,
            "rows": len(agg),
            "years": sorted(agg["year"].unique().tolist()),
            "schools": agg["unitid"].nunique()
        }
        print(f"  school_year_offense: {len(agg):,} rows")
    else:
        checks["aggregates"]["checks"]["school_year_offense"] = {"exists": False}
        print(f"  school_year_offense: MISSING")

    # Check ivy rankings aggregate
    rankings_path = agg_dir / "agg_ivy_rankings.parquet"
    if rankings_path.exists():
        rankings = pd.read_parquet(rankings_path)
        checks["aggregates"]["checks"]["ivy_rankings"] = {
            "exists": True,
            "rows": len(rankings),
            "years": sorted(rankings["year"].unique().tolist()),
            "schools": rankings["unitid"].nunique()
        }
        print(f"  ivy_rankings: {len(rankings):,} rows")
    else:
        checks["aggregates"]["checks"]["ivy_rankings"] = {"exists": False}
        print(f"  ivy_rankings: MISSING")

    checks["aggregates"]["status"] = "PASS"
    return checks


def validate_json_files(verbose: bool = False) -> dict:
    """Validate generated JSON files."""
    print("\nValidating JSON files...")

    checks = {
        "json_files": {
            "status": "PENDING",
            "checks": {}
        }
    }

    errors = []

    # Check metadata.json
    metadata_path = JSON_DIR / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
            checks["json_files"]["checks"]["metadata"] = {
                "exists": True,
                "years": len(metadata.get("years", [])),
                "offenses": len(metadata.get("offenses", []))
            }
            print(f"  metadata.json: {len(metadata.get('years', []))} years, {len(metadata.get('offenses', []))} offenses")
        except json.JSONDecodeError as e:
            errors.append(f"metadata.json: Invalid JSON - {e}")
    else:
        checks["json_files"]["checks"]["metadata"] = {"exists": False}
        errors.append("metadata.json: MISSING")

    # Check presets.json
    presets_path = JSON_DIR / "presets.json"
    if presets_path.exists():
        try:
            with open(presets_path) as f:
                presets = json.load(f)
            ivy_schools = len(presets.get("ivy", {}).get("schools", []))
            checks["json_files"]["checks"]["presets"] = {
                "exists": True,
                "ivy_schools": ivy_schools
            }
            print(f"  presets.json: {ivy_schools} Ivy schools")
        except json.JSONDecodeError as e:
            errors.append(f"presets.json: Invalid JSON - {e}")
    else:
        checks["json_files"]["checks"]["presets"] = {"exists": False}
        errors.append("presets.json: MISSING")

    # Check ranking files
    rankings_dir = JSON_DIR / "rankings"
    if rankings_dir.exists():
        ranking_files = list(rankings_dir.glob("*.json"))
        valid_rankings = 0
        for f in ranking_files:
            try:
                with open(f) as fp:
                    json.load(fp)
                valid_rankings += 1
            except json.JSONDecodeError:
                errors.append(f"rankings/{f.name}: Invalid JSON")

        checks["json_files"]["checks"]["rankings"] = {
            "count": len(ranking_files),
            "valid": valid_rankings
        }
        print(f"  rankings/: {valid_rankings}/{len(ranking_files)} valid files")
    else:
        checks["json_files"]["checks"]["rankings"] = {"exists": False}
        errors.append("rankings/: Directory MISSING")

    # Check school files
    schools_dir = JSON_DIR / "schools"
    if schools_dir.exists():
        school_files = list(schools_dir.glob("*.json"))
        valid_schools = 0
        for f in school_files:
            try:
                with open(f) as fp:
                    json.load(fp)
                valid_schools += 1
            except json.JSONDecodeError:
                errors.append(f"schools/{f.name}: Invalid JSON")

        checks["json_files"]["checks"]["schools"] = {
            "count": len(school_files),
            "valid": valid_schools
        }
        print(f"  schools/: {valid_schools}/{len(school_files)} valid files")
    else:
        checks["json_files"]["checks"]["schools"] = {"exists": False}
        errors.append("schools/: Directory MISSING")

    if errors:
        checks["json_files"]["status"] = "FAIL"
        checks["json_files"]["errors"] = errors
        print(f"  JSON validation: FAIL ({len(errors)} errors)")
    else:
        checks["json_files"]["status"] = "PASS"
        print(f"  JSON validation: PASS")

    return checks


def generate_qa_report(
    fact_checks: dict,
    agg_checks: dict,
    json_checks: dict
) -> dict:
    """Generate QA summary report."""
    QA_DIR.mkdir(parents=True, exist_ok=True)

    # Determine overall status
    statuses = [
        fact_checks.get("fact_table", {}).get("status"),
        agg_checks.get("aggregates", {}).get("status"),
        json_checks.get("json_files", {}).get("status")
    ]

    if all(s == "PASS" for s in statuses):
        overall_status = "PASS"
    elif any(s == "FAIL" for s in statuses):
        overall_status = "FAIL"
    else:
        overall_status = "WARNING"

    report = {
        "generated_at": datetime.now().isoformat(),
        "status": overall_status,
        "checks": {
            **fact_checks,
            **agg_checks,
            **json_checks
        }
    }

    # Save report
    report_path = QA_DIR / "validation_summary.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n  Report saved to: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate data quality and generate QA report"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Data Validation")
    print("=" * 60)

    fact_checks = validate_facts(verbose=args.verbose)
    agg_checks = validate_aggregates(verbose=args.verbose)
    json_checks = validate_json_files(verbose=args.verbose)

    report = generate_qa_report(fact_checks, agg_checks, json_checks)

    print("\n" + "=" * 60)
    print(f"Overall Status: {report['status']}")
    print("=" * 60)

    if report["status"] == "PASS":
        print("\nAll validations passed!")
        print("\nNext steps:")
        print("1. Start frontend: cd ../frontend && npm install && npm run dev")
        print("2. Deploy: npm run build")
    else:
        print("\nSome validations failed. Review the report for details.")
        print(f"Report: {QA_DIR / 'validation_summary.json'}")


if __name__ == "__main__":
    main()
