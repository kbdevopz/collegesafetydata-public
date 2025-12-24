"""
Download IPEDS Fall Enrollment data files from NCES.

URL Pattern: https://nces.ed.gov/ipeds/datacenter/data/{FILE}.zip
Each ZIP contains CSV with enrollment data by UNITID.

File Types:
- DRVEF (Derived Fall Enrollment): Pre-calculated FTE, only 2021-2023
- EF (Fall Enrollment): Raw enrollment by FT/PT status, all years
- EFFY (12-month enrollment): Headcount only
- HD (Directory): Institution names and metadata

For FTE calculations:
- 2021-2023: Use DRVEF (has pre-calculated FTE)
- 2015-2020: Use EF and calculate FTE = FT + (0.5 * PT)

Usage:
    python 01b_download_ipeds.py
    python 01b_download_ipeds.py --year 2023
    python 01b_download_ipeds.py --ef-only  # Download only EF files for 2015-2020
"""

import os
import sys
import argparse
import requests
import zipfile
from pathlib import Path
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT

# IPEDS configuration
IPEDS_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ipeds"
IPEDS_BASE_URL = "https://nces.ed.gov/ipeds/datacenter/data"

# Years to download (match our crime data range)
IPEDS_YEARS = list(range(2015, 2024))  # 2015-2023

# Year ranges for different file types
DRVEF_YEARS = [2021, 2022, 2023]  # DRVEF only available for these years
EF_YEARS = [2015, 2016, 2017, 2018, 2019, 2020]  # Need EF for FTE calculation


def get_files_for_year(year: int) -> list[str]:
    """
    Get the list of files to download for a given year.

    - DRVEF (pre-calculated FTE) only exists for 2021+
    - For 2015-2020, we use EF files to calculate FTE
    """
    files = [
        f"EFFY{year}",      # 12-month unduplicated headcount
        f"HD{year}",        # Directory info
    ]

    if year in DRVEF_YEARS:
        files.append(f"DRVEF{year}")  # Derived Fall Enrollment (has pre-calculated FTE)

    if year in EF_YEARS:
        files.append(f"EF{year}A")    # Fall Enrollment Part A (has FT/PT breakdown for FTE calc)

    return files


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
        response = requests.get(url, stream=True, timeout=120)
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


def extract_zip(zip_path: Path, extract_dir: Path) -> bool:
    """Extract a ZIP file to the specified directory."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        return True
    except zipfile.BadZipFile as e:
        print(f"  Bad ZIP file: {e}")
        return False


def download_year(year: int, ef_only: bool = False) -> dict:
    """
    Download IPEDS files for a given year.
    Returns dict with file status.

    Args:
        year: The year to download
        ef_only: If True, only download EF files (for adding historical FTE)
    """
    year_dir = IPEDS_RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Get files appropriate for this year
    files_to_download = get_files_for_year(year)

    # If ef_only mode, only download EF files
    if ef_only:
        files_to_download = [f for f in files_to_download if f.startswith("EF") and not f.startswith("EFFY")]

    for filename in files_to_download:
        zip_url = f"{IPEDS_BASE_URL}/{filename}.zip"
        zip_path = year_dir / f"{filename}.zip"

        print(f"  Downloading {filename}.zip...")

        if download_file(zip_url, zip_path, filename):
            # Extract the ZIP
            print(f"    Extracting...")
            if extract_zip(zip_path, year_dir):
                results[filename] = "success"
                print(f"    Done: {filename}")
            else:
                results[filename] = "extract_failed"
        else:
            results[filename] = "download_failed"

    return results


def check_existing_files() -> dict:
    """Check which files already exist."""
    existing = {}
    for year in IPEDS_YEARS:
        year_dir = IPEDS_RAW_DIR / str(year)
        if year_dir.exists():
            csvs = list(year_dir.glob("*.csv"))
            if csvs:
                existing[year] = [f.name for f in csvs]
    return existing


def main():
    parser = argparse.ArgumentParser(
        description="Download IPEDS Fall Enrollment data from NCES"
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Download only a specific year"
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
    parser.add_argument(
        "--ef-only",
        action="store_true",
        help="Download only EF files for 2015-2020 (for historical FTE calculation)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("IPEDS Enrollment Data Downloader")
    print("=" * 60)
    print(f"Source: {IPEDS_BASE_URL}")
    print(f"Target: {IPEDS_RAW_DIR.absolute()}")

    if args.ef_only:
        print(f"Mode: EF files only (for historical FTE)")
        print(f"Years: {min(EF_YEARS)}-{max(EF_YEARS)}")
    else:
        print(f"Years: {min(IPEDS_YEARS)}-{max(IPEDS_YEARS)}")

    # Check existing files
    if args.check:
        existing = check_existing_files()
        if existing:
            print("\nExisting files:")
            for year, files in sorted(existing.items()):
                print(f"  {year}: {', '.join(files)}")
        else:
            print("\nNo existing files found.")
        return

    # Handle force re-download
    if args.force:
        print("\nForce mode: Will re-download all files")
        import shutil
        if IPEDS_RAW_DIR.exists():
            shutil.rmtree(IPEDS_RAW_DIR)

    # Create raw directory
    IPEDS_RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Determine years to download
    if args.ef_only:
        years_to_download = EF_YEARS
    elif args.year:
        years_to_download = [args.year]
    else:
        years_to_download = IPEDS_YEARS

    all_results = {}

    for year in years_to_download:
        print(f"\n{year}:")
        results = download_year(year, ef_only=args.ef_only)
        all_results[year] = results

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)

    success_count = sum(
        1 for year_results in all_results.values()
        for status in year_results.values()
        if status == "success"
    )
    total_count = sum(len(r) for r in all_results.values())

    print(f"Successful: {success_count}/{total_count} files")

    # Show any failures
    failures = [
        (year, fname, status)
        for year, results in all_results.items()
        for fname, status in results.items()
        if status != "success"
    ]
    if failures:
        print("\nFailed downloads:")
        for year, fname, status in failures:
            print(f"  {year}/{fname}: {status}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Verify downloads in data/raw/ipeds/")
    print("2. Run: python 02a_transform_enrollment.py")


if __name__ == "__main__":
    main()
