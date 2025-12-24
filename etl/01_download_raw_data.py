"""
Download Clery Act data files from DOE for 2015-2024.

URL Pattern: https://ope.ed.gov/campussafety/datafiles/[YEAR]/Crime[YEAR].sas7bdat
Alternative: CSV files available at same path with .csv extension

Usage:
    python 01_download_raw_data.py
    python 01_download_raw_data.py --year 2023
    python 01_download_raw_data.py --csv  # Download CSV instead of SAS

Manual Fallback:
    If script fails, download manually from:
    https://ope.ed.gov/campussafety/#/datafile/list
"""

import os
import sys
import argparse
import requests
from pathlib import Path
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, DATA_YEARS, DOE_BASE_URL, DOE_DOWNLOAD_PAGE


def download_file(url: str, dest_path: Path, desc: str = "") -> bool:
    """
    Download a file with progress bar.
    Returns True if successful, False otherwise.
    """
    try:
        # First check if file exists and skip
        if dest_path.exists():
            print(f"  Already exists: {dest_path.name}")
            return True

        # Stream download with progress
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(dest_path, 'wb') as f, tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            desc=desc or dest_path.name,
            leave=False
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

        return True

    except requests.exceptions.RequestException as e:
        print(f"  Failed: {e}")
        # Clean up partial download
        if dest_path.exists():
            dest_path.unlink()
        return False


def download_year(year: int, file_type: str = "csv") -> bool:
    """
    Download crime data file for a given year.
    Tries SAS format first, falls back to CSV.
    Returns True if successful.
    """
    year_dir = RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    # Try primary format
    if file_type == "sas":
        sas_url = f"{DOE_BASE_URL}/{year}/Crime{year}.sas7bdat"
        sas_path = year_dir / f"Crime{year}.sas7bdat"

        print(f"\n{year}: Downloading SAS format...")
        if download_file(sas_url, sas_path, f"Crime{year}.sas7bdat"):
            print(f"  Downloaded: {sas_path.name}")
            return True

    # Try CSV format (more reliable)
    csv_url = f"{DOE_BASE_URL}/{year}/Crime{year}.csv"
    csv_path = year_dir / f"Crime{year}.csv"

    print(f"\n{year}: Downloading CSV format...")
    if download_file(csv_url, csv_path, f"Crime{year}.csv"):
        print(f"  Downloaded: {csv_path.name}")
        return True

    # Try alternative CSV naming
    csv_url_alt = f"{DOE_BASE_URL}/{year}/crime{year}.csv"
    if download_file(csv_url_alt, csv_path, f"crime{year}.csv"):
        print(f"  Downloaded: {csv_path.name}")
        return True

    print(f"  Could not download {year} data")
    print(f"  Try manual download from: {DOE_DOWNLOAD_PAGE}")
    return False


def check_existing_files() -> dict:
    """Check which files already exist and their sizes."""
    existing = {}
    for year in DATA_YEARS:
        year_dir = RAW_DIR / str(year)
        if year_dir.exists():
            files = list(year_dir.glob("*"))
            if files:
                existing[year] = [(f.name, f.stat().st_size) for f in files]
    return existing


def main():
    parser = argparse.ArgumentParser(
        description="Download Clery Act crime data from DOE"
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Download only a specific year"
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        default=True,
        help="Download CSV format (default)"
    )
    parser.add_argument(
        "--sas",
        action="store_true",
        help="Download SAS format instead of CSV"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing files without downloading"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files exist"
    )

    args = parser.parse_args()
    file_type = "sas" if args.sas else "csv"

    print("=" * 60)
    print("Clery Act Data Downloader")
    print("=" * 60)
    print(f"Source: {DOE_BASE_URL}")
    print(f"Target: {RAW_DIR.absolute()}")
    print(f"Format: {file_type.upper()}")

    # Check existing files
    if args.check:
        existing = check_existing_files()
        if existing:
            print("\nExisting files:")
            for year, files in sorted(existing.items()):
                for name, size in files:
                    size_mb = size / (1024 * 1024)
                    print(f"  {year}: {name} ({size_mb:.1f} MB)")
        else:
            print("\nNo existing files found.")
        return

    # Handle force re-download
    if args.force:
        print("\nForce mode: Will re-download all files")
        import shutil
        for year in DATA_YEARS:
            year_dir = RAW_DIR / str(year)
            if year_dir.exists():
                shutil.rmtree(year_dir)

    # Create raw directory
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Download
    years_to_download = [args.year] if args.year else DATA_YEARS
    successful = []
    failed = []

    for year in years_to_download:
        if download_year(year, file_type):
            successful.append(year)
        else:
            failed.append(year)

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Successful: {len(successful)} years")
    if successful:
        print(f"  Years: {', '.join(map(str, successful))}")
    if failed:
        print(f"\nFailed: {len(failed)} years")
        print(f"  Years: {', '.join(map(str, failed))}")
        print(f"\nManual download: {DOE_DOWNLOAD_PAGE}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Verify downloads in data/raw/")
    print("2. Run: python 02_transform_to_parquet.py")


if __name__ == "__main__":
    main()
