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

import os
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

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"


class ValidationError(Exception):
    """Raised when a validation check fails."""
    pass


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
        raise ValidationError(
            f"{FACTS_PATH.parent} holds parquet data that 02_transform_to_parquet.py "
            f"did not write:\n{listing}\n"
            f"Only the file {FACTS_PATH.name} belongs there. Delete the items listed above "
            f"(move them outside data/curated to keep them), then run 03 to 06 again."
        )
    if not FACTS_PATH.is_file():
        raise ValidationError(f"{FACTS_PATH} not found. Run 02_transform_to_parquet.py first.")
    return str(FACTS_PATH)


def _reject_constant(token: str):
    raise ValueError(f"{token} is not valid JSON")


def load_json_strict(path: Path):
    """Parse a JSON file the way a browser does: UTF-8, and NaN or Infinity is an error."""
    text = path.read_bytes().decode("utf-8-sig")
    return json.loads(text, parse_constant=_reject_constant)


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

    try:
        facts_file = get_facts_path()

        # Check 1: Row counts per year
        print("  Checking row counts by year...")
        year_counts = con.execute(f"""
            SELECT year, COUNT(*) as records, SUM(count) as total_incidents
            FROM read_parquet('{facts_file}')
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
            FROM read_parquet('{facts_file}')
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
            FROM read_parquet('{facts_file}')
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
            FROM read_parquet('{facts_file}')
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
            FROM read_parquet('{facts_file}')
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

    missing = [k for k, v in checks["aggregates"]["checks"].items() if not v["exists"]]
    if missing:
        checks["aggregates"]["status"] = "FAIL"
        checks["aggregates"]["error"] = f"Missing: {', '.join(missing)}. Run 04_create_aggregates.py."
    else:
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

    # Parse every JSON file the site serves, as strictly as a browser does
    json_files = sorted(JSON_DIR.rglob("*.json")) if JSON_DIR.is_dir() else []
    invalid = set()
    parsed = {}
    for f in json_files:
        try:
            data = load_json_strict(f)
        except (OSError, ValueError) as e:
            invalid.add(f)
            errors.append(f"{f.relative_to(JSON_DIR).as_posix()}: invalid JSON ({e})")
            continue
        if f.parent == JSON_DIR and f.name in ("metadata.json", "presets.json"):
            parsed[f.name] = data
    checks["json_files"]["checks"]["all_files"] = {
        "count": len(json_files),
        "valid": len(json_files) - len(invalid)
    }
    print(f"  all files: {len(json_files) - len(invalid)}/{len(json_files)} valid JSON")

    # Check metadata.json
    metadata_path = JSON_DIR / "metadata.json"
    if "metadata.json" in parsed:
        metadata = parsed["metadata.json"]
        checks["json_files"]["checks"]["metadata"] = {
            "exists": True,
            "years": len(metadata.get("years", [])),
            "offenses": len(metadata.get("offenses", []))
        }
        print(f"  metadata.json: {len(metadata.get('years', []))} years, {len(metadata.get('offenses', []))} offenses")
    elif not metadata_path.exists():
        checks["json_files"]["checks"]["metadata"] = {"exists": False}
        errors.append("metadata.json: MISSING")

    # Check presets.json
    presets_path = JSON_DIR / "presets.json"
    if "presets.json" in parsed:
        presets = parsed["presets.json"]
        ivy_schools = len(presets.get("ivy", {}).get("schools", []))
        checks["json_files"]["checks"]["presets"] = {
            "exists": True,
            "ivy_schools": ivy_schools
        }
        print(f"  presets.json: {ivy_schools} Ivy schools")
    elif not presets_path.exists():
        checks["json_files"]["checks"]["presets"] = {"exists": False}
        errors.append("presets.json: MISSING")

    # Check ranking files
    rankings_dir = JSON_DIR / "rankings"
    if rankings_dir.exists():
        ranking_files = list(rankings_dir.glob("*.json"))
        valid_rankings = sum(1 for f in ranking_files if f not in invalid)

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
        valid_schools = sum(1 for f in school_files if f not in invalid)

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
        for err in errors[:20]:
            print(f"    {err}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20:,} more, all listed in {QA_DIR / 'validation_summary.json'}")
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
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
