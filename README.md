# CollegeSafetyData.org

> Transparent access to campus crime statistics reported under the Jeanne Clery Act.

**Live Site:** [collegesafetydata.org](https://collegesafetydata.org)

This project provides free, public access to campus safety data for over 8,100 U.S. colleges and universities, covering 10 years of crime statistics (2015-2024). Data is sourced from the U.S. Department of Education and processed using an open, reproducible methodology.

## Overview

- **8,100+ Schools** — All U.S. institutions reporting Clery Act data
- **10 Years of Data** — 2015-2024 for consistent comparisons
- **Transparent Methodology** — Full ETL pipeline is open source
- **Rate-Based Rankings** — Per 10,000 FTE students for fair comparisons

## Features

- **Rankings** — Compare schools by offense type, year, and geography
- **School Profiles** — Detailed trends and breakdowns for each institution
- **Compare Tool** — Side-by-side comparisons of multiple schools
- **Data Audit** — Downloadable validation reports for data quality

## Data Sources

| Source | Coverage | URL |
|--------|----------|-----|
| Campus Crime Data | 2015-2024 | [ope.ed.gov/campussafety](https://ope.ed.gov/campussafety) |
| Enrollment (FTE) | 2015-2024 | [nces.ed.gov/ipeds](https://nces.ed.gov/ipeds) |

### Methodology

Our data processing pipeline is fully documented. See [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for:
- Which DOE release each campus-year comes from: the newest release that has that campus for that year, with all of its figures from that one release
- Known errors in DOE files and how they are handled
- Figures that two campuses report identically (one location, or a whole year), counted once (under one host campus) in totals and rankings
- FTE calculation using official IPEDS factors
- Crime rate formulas
- Geographic classifications
- Data limitations

## Quick Start

### Frontend Only (Demo Mode)

The frontend includes sample data for immediate preview:

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173

### Full ETL Pipeline

Requires Python 3.11+:

```bash
cd etl
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Is there newer data, and is the site built from it and released?
# Exit code 0 = current, 1 = new/changed, 2 = unknown (INFO and WAITING lines do not change it)
python 00_check_for_updates.py
python 00_check_for_updates.py --local-only   # release check without network: origin and the live sites are not asked

# Run the full pipeline, in this order
python 01_download_raw_data.py        # DOE crime release zips
python 01b_download_ipeds.py          # IPEDS enrollment files
python 02_transform_to_parquet.py
python 02b_transform_ef_enrollment.py # FTE from enrollment components (EF years)
python 02a_transform_enrollment.py    # official FTE (DRVEF); reads 02b's table, so run it after 02b
python 03_build_dimensions.py
python 04_create_aggregates.py
python 05_generate_json.py
python 06_validate.py
python 07_comprehensive_audit.py
cp ../data/qa/comprehensive_audit.json ../frontend/public/audit.json  # the audit the Methodology page offers
```

Generated JSON files are written to `frontend/public/data/`. Run one step at a time: each step holds an operating-system lock on `data/curated/.pipeline.lock` while it runs. A step started meanwhile waits a few seconds, then stops with an error. The lock is released however a step ends (even if it crashes or is killed), so there is nothing to clean up.

`01_download_raw_data.py` checks each zip in full (every member's CRC-32) before it extracts anything, and never replaces a good extracted file with one from a damaged zip. It exits with code 1, and prints the command that fixes it, when a release the pipeline needs could not be downloaded or extracted. `01b_download_ipeds.py` reports a year as WAITING, not FAILED, while NCES has not published that year's fall enrollment yet; that alone does not make it exit 1.

#### Update checker

`00_check_for_updates.py` prints one line per check. NEW, CHANGED and ERROR lines set the exit code; OK, INFO and WAITING lines do not.

- Every row of DOE's file listing must be a kind of file DOE has always listed (`CrimeYYYYSAS.zip`, `CrimeYYYYSPSS.zip`, `CrimeYYYYEXCEL.zip` or `CrimeYYYY.zip`). Any other row is NEW, since it may be newer or corrected data.
- Each DOE release the pipeline reads is downloaded and compared byte for byte, with retries when DOE fails. A download that is not a complete release zip is an ERROR, not a re-issue. Older releases on disk that `DATA_YEARS` does not need are not downloaded (INFO).
- `01_download_raw_data.py --force` replaces a zip only with a complete, readable download that has all the crime files; otherwise the zip on disk is kept.
- A held DOE zip that differs from DOE's copy and fails its own CRC-32 check is reported as damaged on disk, with the command to download it again (`01_download_raw_data.py --release N --force`). "Re-issued" is kept for an intact zip that differs from DOE's.
- A pipeline enrollment zip from NCES with any CSV other than the final (`*_rv.csv`) and provisional files is NEW: it may be NCES's final data under a new name.
- A ZIP that NCES lists next to a pipeline enrollment file under a longer name (for example `DRVEF2024_RV.zip` next to `DRVEF2024.zip`) is NEW: it may hold final or corrected data as a ZIP of its own, which the pipeline does not read.
- DOE usually publishes a release before NCES publishes fall enrollment for its newest year. After `DATA_YEARS` is extended to that year, the checker reports it as WAITING until NCES publishes the file (it looks on every run). Step 05 marks such a year `missing` in `enrollmentStatus` in `frontend/public/data/metadata.json` (other years are `final` or `provisional`), and the site shows that year's crime counts without a rate.

#### Build records

Each step from 02 to 05 writes a record of what it was built from, and step 05 publishes the last one with the site as `frontend/public/data/build_inputs.json`. The records hold:

- the DOE releases used for each year, how many campus-years each of them supplied (each campus-year comes from the newest release that has it; `data/curated/dims/campus_year_sources.parquet` lists the release of every campus-year), the known DOE file errors the build worked around, and the name and checksum of every DOE and NCES file behind the published numbers,
- the checksum of each file the step read from the step before it, and of each file it wrote; for step 05 that is every file in `frontend/public/data`,
- a checksum of the pipeline code and `config.py` the step ran with.

A step refuses to start if a file it reads is not exactly what the step before it wrote. A step deletes its record before it rebuilds and writes a new one only when it finishes, and only if its inputs did not change while it ran.

`00_check_for_updates.py` compares the records with the raw files, the code and each other, and re-checksums every file they list. A skipped, failed or out-of-order step, a changed or stray file, or code changed since the last build shows up as out of date, with the step to rebuild from. Records are compared by what they describe, not by when a step ran: re-running a step that writes the same files is not a change. It also reports:

- parquet data in `data/curated/facts` that step 02 did not write (steps 03, 04, 06 and 07 refuse to run until it is deleted or moved out of `data/curated`); other files there, such as `.DS_Store`, cannot reach any output and are not reported,
- files in `frontend/public/data` that step 05 does not make. Running 05 removes stale files of the kinds it makes (`metadata.json`, `presets.json`, `school-index.json`, and JSON files directly in `rankings/` and `schools/`) but leaves anything else in place, so the checker names those files on their own line: delete them or move them out of `frontend/public/data`. Files git ignores (`.DS_Store`, `desktop.ini`) are never committed or published and are not reported,
- a `frontend/public/audit.json` that is not 07's audit of exactly this site data. Step 07 records in its report (`audited_build`) the SHA-256 of the `build_inputs.json` it audited and writes `generated_at` in UTC; the checker compares the SHA-256, so the computer's time zone and clock play no part. If 07 has already audited this build, the checker says to copy its report; otherwise to re-run 07 and copy it.

#### Release check

The last section of `00_check_for_updates.py` checks that this build is committed, released and served, in that order:

- **Committed**: `HEAD` holds every site file the build record lists, `build_inputs.json` and `audit.json`, each exactly as on disk (compared by git blob id, so git's line-ending conversion does not matter), and no other file in `frontend/public/data`. Files that `git status` does not show are named with what to do: files git ignores (`git add -f`, or remove the rule) and files the index marks assume-unchanged or skip-worktree.
- **Released**: origin's `main` branch, asked with `git ls-remote` (no fetch, nothing written), has the same `frontend/public/data` tree and `audit.json` as `HEAD`. When `HEAD` does not hold the build on disk, `main` is compared with the build on disk instead, so the line says what to do: commit first, or nothing to merge because `main` already has it. If `main` is at a commit this checkout does not have, the answer is unknown (ERROR): run `git fetch origin` and check again. If only `staging` has the build, that is reported as INFO, since `main` is what both sites deploy.
- **Served**: collegesafetydata.org and collegesafetydata.com each serve this build's `/data/build_inputs.json`, `/audit.json` and every site file the build record lists, compared by SHA-256 with the record. Every file is fetched on every run, six at a time with retries and progress lines, so a partial or stale deploy of any file is found whatever the git history looks like; this takes about 15 minutes per site. Every other file under `frontend/public/data` that the git history of `HEAD` and origin's `main` ever held (including commits this checkout saw `main` at before a rewrite) must be gone from each site. The site's HTML page, which the hosts send for a file they do not have, counts as missing (or, for a removed file, as gone). In a shallow clone the list of earlier files may be incomplete, and the result says so.

The closing RESULT line says the build is committed, on `main` or served only when this run showed it, and lists what it did not verify. `--local-only` checks the commit only and makes no network request.

## Project Structure

```
├── etl/                          # Data processing pipeline
│   ├── 01_download_raw_data.py   # Download DOE data
│   ├── 02_transform_to_parquet.py # Transform to Parquet
│   ├── 02a_transform_enrollment.py # Process DRVEF (2021-2024)
│   ├── 02b_transform_ef_enrollment.py # Calculate FTE from EF (2015-2020)
│   ├── 03_build_dimensions.py    # Build dimension tables
│   ├── 04_create_aggregates.py   # Create aggregate rankings
│   ├── 05_generate_json.py       # Export to JSON
│   ├── 06_validate.py            # Validate outputs
│   ├── 07_comprehensive_audit.py # Run data quality audit
│   ├── METHODOLOGY.md            # Full methodology documentation
│   └── config.py                 # Configuration
│
├── frontend/                     # React dashboard
│   ├── src/
│   │   ├── pages/               # Rankings, Compare, SchoolProfile, Methodology
│   │   ├── components/          # Reusable components
│   │   └── lib/                 # API, types, utilities
│   └── public/data/             # Generated JSON outputs
│
└── data/                        # Raw and processed data (gitignored)
    ├── raw/                     # Downloaded DOE/IPEDS files
    ├── curated/                 # Parquet fact/dimension tables
    └── qa/                      # Audit reports
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| ETL | Python 3.11+, DuckDB, pandas, pyarrow |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Charts | Recharts 2.x |
| Tables | TanStack Table v8 |
| Hosting | Cloudflare Pages (collegesafetydata.org) and Vercel (collegesafetydata.com), both static |

## FTE Calculation

Full-Time Equivalent (FTE) enrollment is used as the denominator for crime rate calculations:

- **Every year**: the pipeline reads NCES's final revised file (`*_rv.csv`) when it has been published and the provisional file otherwise. As of November 2026, 2015-2023 are final and 2024 is provisional. `etl/00_check_for_updates.py` reports which file each year uses, and `enrollmentStatus` in `frontend/public/data/metadata.json` records it for each year of the build (`final`, `provisional`, or `missing` when NCES has not published the year).
- **2021-2024**: Official IPEDS pre-calculated FTE values
- **2015-2020**: Calculated from raw enrollment components using official IPEDS factors:
  ```
  FTE = FT_Undergrad + FT_Graduate
      + (PT_Undergrad × 0.403543)
      + (PT_Graduate × 0.361702)
  ```

See [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for complete documentation.

## Data Quality

Every data run includes a comprehensive audit validating:
- School completeness (all schools have JSON files)
- Incident total accuracy (sums match aggregates)
- FTE coverage by year: of the schools with crime data in a year, the share that have FTE that year (a year whose enrollment NCES has not published is expected to have none)
- Rate calculation verification
- Ranking order validation
- Shared statistics: figures two campuses report identically (in the data used, or in the older release a campus-year is taken from) are found again from the fact table and the older releases' figures, and every ranking entry must count them once, under the host campus

Download the latest audit: [audit.json](https://collegesafetydata.org/audit.json). It names the site data it audited (`audited_build`: the SHA-256 of that build's `build_inputs.json`) and when it ran, in UTC.

## Data Limitations

- **Underreporting**: ~80% of campus crimes are never reported (DOJ NCVS)
- **Reporting Lag**: DOE releases data ~1 year after collection
- **Institutional Variation**: Reporting practices vary by school
- **Higher Numbers ≠ More Crime**: Often indicates better reporting culture

## Development

```bash
# Install dependencies
cd frontend && npm install

# Run dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Releasing changes

`main` is production. A push to `main` deploys to collegesafetydata.org and collegesafetydata.com at the same time, so nothing is pushed to `main` directly.

1. Do the work on a short-lived branch cut from `staging`. Pushing it gives a private preview build on both hosts.
2. Open a pull request into `staging`. Once merged, the staging build is at a stable address:
   - https://staging.collegesafetydata-public.pages.dev
   - the `staging` branch preview in the Vercel project
3. Check the staging build: spot-check numbers against the DOE source and run the audit.
4. Release by opening a pull request from `staging` into `main` and merging it.

After a data rebuild, commit all of the site data and `frontend/public/audit.json` together: `git add -A frontend/public/data frontend/public/audit.json` (new and deleted files included). Before the release, `python etl/00_check_for_updates.py --local-only` should report that `HEAD` holds this build. Once the release is merged and deployed, run `git fetch origin` and then `python etl/00_check_for_updates.py`: it should report that origin's `main` has this build and both live sites serve it (it fetches every site file from each site and checks that files earlier builds held are gone).

Preview and staging builds are marked `noindex` by both hosts, so search engines do not pick them up.

## License

This project displays publicly available data from the U.S. Department of Education. Built for transparency and public education purposes.

## Data Citation

If you use this data in research or reporting, please cite both sources:

1. U.S. Department of Education. Campus Safety and Security Data Analysis Cutting Tool. https://ope.ed.gov/campussafety/
2. National Center for Education Statistics. IPEDS. https://nces.ed.gov/ipeds/
