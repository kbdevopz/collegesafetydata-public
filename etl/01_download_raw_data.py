"""
Download Clery Act data release zips from DOE.

The DOE download page (https://ope.ed.gov/campussafety/#/datafile/list) is an
Angular SPA; files are served from its API:

    https://ope.ed.gov/campussafety/api/dataFiles/file?fileName=Crime{RELEASE}{FMT}.zip

IMPORTANT: Release zips are named by RELEASE year, not data year. Each release
contains THREE calendar years of data (e.g. Crime2025SAS.zip covers calendar
years 2022-2024, in files suffixed 222324). The transform step
(02_transform_to_parquet.py) sources each calendar year from the newest
release that covers it, so this script downloads the releases needed to cover
DATA_YEARS at their newest.

Usage:
    python 01_download_raw_data.py                 # releases needed for DATA_YEARS
    python 01_download_raw_data.py --release 2025  # a single release
    python 01_download_raw_data.py --check         # list what's on disk
    python 01_download_raw_data.py --force         # re-download existing zips

Manual Fallback:
    If script fails, download manually from:
    https://ope.ed.gov/campussafety/#/datafile/list
"""

import sys
import argparse
import zipfile
import requests
from pathlib import Path
from tqdm import tqdm

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import RAW_DIR, DATA_YEARS, DOE_DOWNLOAD_PAGE, get_data_url


def download_file(url: str, dest_path: Path, desc: str = "") -> bool:
    """
    Download a file with progress bar.
    Returns True if successful, False otherwise.
    """
    try:
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


def needed_release_years() -> list[int]:
    """
    Release years whose zips are needed to cover DATA_YEARS at their newest.

    Release r contains calendar years r-3..r-1, so the newest release covering
    data year y is release y+3. Trailing releases that DOE has not published
    yet will 404 and can be ignored - the years they would cover are still
    present (unrevised) in the newest published release.
    """
    return sorted({y + 3 for y in DATA_YEARS})


def extract_release(zip_path: Path) -> int:
    """Extract a release zip flat into RAW_DIR. Returns number of files."""
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(RAW_DIR)
        return len(zf.namelist())


def download_release(release_year: int, file_type: str = "sas", force: bool = False) -> bool:
    """
    Download and extract the release zip for a given RELEASE year.
    Returns True if the zip is present and extracted.
    """
    fmt = "SAS" if file_type.lower() == "sas" else file_type.upper()
    zip_path = RAW_DIR / f"Crime{release_year}{fmt}.zip"

    if zip_path.exists() and not force:
        print(f"\n{release_year}: Already downloaded ({zip_path.name})")
    else:
        url = get_data_url(release_year, file_type)
        print(f"\n{release_year}: Downloading {zip_path.name}...")
        if not download_file(url, zip_path, zip_path.name):
            print(f"  Could not download release {release_year}")
            print(f"  (Releases not yet published by DOE will 404 - that is expected)")
            return False
        print(f"  Downloaded: {zip_path.name}")

    try:
        n = extract_release(zip_path)
        print(f"  Extracted {n} files into {RAW_DIR}")
        return True
    except zipfile.BadZipFile:
        print(f"  ERROR: {zip_path.name} is not a valid zip - deleting")
        zip_path.unlink()
        return False


def check_existing_files() -> None:
    """List release zips and extracted SAS files on disk."""
    zips = sorted(RAW_DIR.glob("Crime*.zip"))
    sas = list(RAW_DIR.glob("*.sas7bdat"))
    if zips:
        print("\nRelease zips on disk:")
        for z in zips:
            size_mb = z.stat().st_size / (1024 * 1024)
            print(f"  {z.name} ({size_mb:.1f} MB)")
    else:
        print("\nNo release zips found.")
    print(f"\nExtracted SAS files: {len(sas)}")


def main():
    parser = argparse.ArgumentParser(
        description="Download Clery Act crime data release zips from DOE"
    )
    parser.add_argument(
        "--release",
        type=int,
        help="Download only a specific RELEASE year (e.g. 2025 = calendar years 2022-24)"
    )
    parser.add_argument(
        "--format",
        choices=["sas", "excel", "spss"],
        default="sas",
        help="File format to download (default: sas)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing files without downloading"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if zips exist"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Clery Act Data Downloader")
    print("=" * 60)
    print(f"Target: {RAW_DIR.absolute()}")
    print(f"Format: {args.format.upper()}")

    if args.check:
        check_existing_files()
        return

    # Create raw directory
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Ascending order so the newest release's ReadMe.txt wins on extract
    releases = [args.release] if args.release else needed_release_years()

    successful = []
    failed = []
    for release_year in releases:
        if download_release(release_year, args.format, force=args.force):
            successful.append(release_year)
        else:
            failed.append(release_year)

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Successful: {len(successful)} releases")
    if successful:
        print(f"  Releases: {', '.join(map(str, successful))}")
    if failed:
        print(f"\nUnavailable: {len(failed)} releases")
        print(f"  Releases: {', '.join(map(str, failed))}")
        print(f"  (Trailing releases DOE has not published yet are expected here)")
        print(f"  Manual download: {DOE_DOWNLOAD_PAGE}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Verify downloads in data/raw/")
    print("2. Run: python 02_transform_to_parquet.py")


if __name__ == "__main__":
    main()
