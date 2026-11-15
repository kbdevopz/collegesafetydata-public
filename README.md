# CollegeSafetyData.org

> Transparent access to campus crime statistics reported under the Jeanne Clery Act.

**Live Site:** [collegesafetydata.org](https://collegesafetydata.org)

This project provides free, public access to the campus crime statistics that U.S. colleges and universities report to the U.S. Department of Education under the Clery Act, for calendar years 2015-2024, with enrollment from NCES IPEDS. The pipeline that builds the site is open source and reproducible.

## Overview

- **Every reporting campus** — each campus that reported to DOE in at least one year has a school page (14,081 campuses of 7,380 institutions in the November 2026 build; the site shows the count from `metadata.json`)
- **10 Years of Data** — calendar years 2015-2024
- **Transparent Methodology** — Full ETL pipeline is open source
- **Rates** — 3-year rates of reported on-campus incidents per 10,000 on-campus students a year (no window includes 2020), each with a 95% interval and a comparison with the national rate; ordered lists of large institutions, with each position given as a range, for violent crimes, criminal offenses except motor vehicle theft, and burglary only (see [etl/METHODOLOGY.md](etl/METHODOLOGY.md), "Rate rules", for which institutions are rated and listed)

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
- Zero versus not reported: a year a campus reported without incidents is a 0 (shown, charted and ranked as 0, and a campus that never had an incident still has a page); a year it did not report has no figures and is shown as not reported
- Known errors in DOE files and how they are handled
- Figures that two campuses report identically (one location, or a whole year), counted once (under one host campus) in totals and rankings
- Enrollment (FTE): NCES's own figures for every year
- Totals: criminal offenses by default; "all categories" mixes crimes, arrests and disciplinary referrals
- Ranking ties: equal counts share a rank (1, 2, 2, 4), listed by name
- Rates are per institution and per 3-year window without 2020 (etl/METHODOLOGY.md, "Rate rules"): the on-campus incidents of all the institution's campuses in the United States over the 3 years, divided by the sum of its on-campus FTE in those years (NCES publishes FTE per institution; on-campus FTE is the larger of two estimates made from NCES's FTE, fall headcounts and share of students enrolled exclusively online); non-campus and public-property incidents are shown beside the rate, not in it. An institution is rated in a window when DOE has figures for it in each of the 3 years, its link campus is in the 50 states, DC, Puerto Rico or the U.S. Virgin Islands, its on-campus FTE (with any FTE pooled under the merger and shared-campus rules) is at least 1,000 in each year, and no rule applies in any of them (a hospital, a special-focus medical or research institution, a reference list, figures or students that cannot be matched after a merger, or a main campus shared with another institution's main campus). Each rate has a 95% interval from a negative binomial (NB-P) model and is compared with the national rate and with the rate of its peer type (from the Carnegie Size & Setting classification). Violent crimes, criminal offenses except motor vehicle theft, and burglary have ordered lists of the institutions whose expected count at the national rate is at least 20, each position given as a 95% rank range from pairwise tests. Where campuses of two or more institutions report the same incidents (identical or near-identical figures, or a reviewed list), the site's incidents are in at most one institution's rate; an institution with a campus at another's site has its comparisons withheld unless published enrollment figures (counts or upper bounds, from its own year or, failing that, up to 3 years away) show that at most 1 in 10 of its student-years are there, because DOE's files give no enrollment per campus. Withheld comparisons, an uncertain on-campus FTE, or a quarter or more of on-campus incidents at listed medical-center campuses keep an institution off the lists; with an uncertain FTE, its comparisons are given only when both FTE estimates lead to the same result
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
python 02b_transform_ef_enrollment.py # NCES's FTE for 2015-2020 (etl/reference) and EF headcounts
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
│   ├── 01c_extract_ipeds_official.ps1 # Copy NCES's 2015-2020 FTE from its Access databases (Windows)
│   ├── 02b_transform_ef_enrollment.py # NCES's FTE for 2015-2020, from etl/reference
│   ├── reference/                # NCES's 2015-2020 FTE and the databases it came from
│   ├── 03_build_dimensions.py    # Build dimension tables
│   ├── 04_create_aggregates.py   # Create aggregate rankings
│   ├── 05_generate_json.py       # Export to JSON
│   ├── rates.py                  # Rate windows, intervals, comparisons, lists (run by 05)
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

## FTE (Enrollment)

Full-Time Equivalent (FTE) enrollment is the basis of the rates' denominator, an estimate of on-campus FTE made from it (etl/METHODOLOGY.md, rate rule 3). Every year uses NCES's own FTE; the pipeline does not calculate it:

- **2021-2024**: the DRVEF file of each year. The pipeline reads NCES's final revised file (`*_rv.csv`) when it has been published and the provisional file otherwise. As of November 2026, 2015-2023 are final and 2024 is provisional. `etl/00_check_for_updates.py` reports which file each year uses, and `enrollmentStatus` in `frontend/public/data/metadata.json` records it for each year of the build (`final`, `provisional`, or `missing` when NCES has not published the year).
- **2015-2020**: NCES publishes FTE for these falls only inside its final IPEDS Access databases. `etl/reference/ipeds_official_fte.csv` holds it (and the percent of students enrolled exclusively online), with each database's URL, size and SHA-256 in `etl/reference/ipeds_official_sources.json`. Both are committed, so the build needs no Access. To check or refresh them, run on Windows (it needs Microsoft's 64-bit Access ODBC driver, from the Microsoft Access Database Engine 2016 Redistributable):
  ```
  powershell -ExecutionPolicy Bypass -File etl\01c_extract_ipeds_official.ps1
  ```
  It downloads the six databases (about 430 MB) into `data/raw/ipeds_official`, stops if one differs from the recorded SHA-256, and rewrites the CSV. `00_check_for_updates.py` checks on every run, without downloading, that each database is still published at the recorded size. The EF fall enrollment files still supply 2015-2020 headcounts and the `final`/`provisional` status of those years.

See [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for complete documentation.

## Data Quality

Every data run ends with an audit of internal consistency: the published files must agree with each other and with the pipeline's tables. It does not check institutions' figures against their records. Its 14 checks (`etl/METHODOLOGY.md`, "Validation"; each check's `details.what_it_checks` in `audit.json` says exactly what it verifies):
1. School Completeness: every campus that reported a year, zeros included, has a JSON file and is in the search index
2. Incident Total Accuracy: each file has exactly the years the campus reported, and its sums match the aggregates
3. FTE Coverage: of the schools with crime data in a year, the share that have FTE that year (a year whose enrollment NCES has not published is expected to have none)
4. Rate Calculation Accuracy: every 3-year and single-year rate in the rate files is its on-campus count over its on-campus FTE (summed over the 3 years for a 3-year rate) x 10,000 and lies inside its interval, and the national rates, peer rates and expected counts agree with the figures they are made of
5. Ranking Order Validation: rankings by count are in order with ranks 1, 2, 2, 4; the rate files are in rate order, and every list position lies inside its rank range
6. Ranking Totals and Tables: each rankings file's totals and campus table agree with its rankings, and the rate files, institution rate files, `rates/flags.json` and school files agree with each other
7. Aggregate Consistency: the aggregates hold exactly the fact table's counts
8. Shared Statistics Counted Once: figures two campuses report identically (in the data used, or in the older release a campus-year is taken from) are found again from the fact table and the older releases' figures, and every ranking entry must count them once, under the host campus
9. Enrollment Matches NCES: every FTE, online share and headcount is NCES's own figure
10. Institution Rates: each institution's campuses (campuses abroad apart), counts per geography, link campus, FTE, online share, both on-campus FTE estimates, pooled FTE, the rules that give it no rate, its peer type and its figures at medical-center and shared campuses are recomputed from the facts, NCES's enrollment, the IPEDS HD files and the reference lists, and must match the published files
11. Campus Identity: the campus ID changes in `etl/reference/campus_id_changes.csv` are found again with their evidence, and the two school files of each change point to each other
12. Rate Rules: every 3-year rate, interval, comparison (national, peer, both FTE estimates), list, position, rank range, state list, unusual-year flag, single-year rate and count flag is recomputed from check 10's figures by the audit's own implementation of the rules, with the rate constants in `metadata.json` and the design's test vectors
13. Interval Calibration: for each code and period, each institution's yearly on-campus counts are predicted from its other years under the published model, and the share inside the 95% predictive interval is compared with the share the model expects, against fixed limits (`rateRules.calibration` in `metadata.json`); in a group of institutions with similar counts the limit below the expected share is tighter than the one above, because intervals that are too narrow overstate certainty
14. Medical-Campus Screen: campuses whose DOE name or address suggests a medical center and that hold a material share of an institution's on-campus incidents must be on the medical-center campus list or recorded as reviewed; any other is named as a warning, never a failure

Download the latest audit: [audit.json](https://collegesafetydata.org/audit.json). It names the site data it audited (`audited_build`: the SHA-256 of that build's `build_inputs.json`) and when it ran, in UTC. Its `summary` counts the checks that passed, failed and gave a warning, and each check lists its errors and warnings.

## Data Limitations

See the Methodology page (Limitations) and [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for the full list. In short:

- **Reports, not victimization**: Clery figures count crimes reported to campus security authorities or police. In the Bureau of Justice Statistics' NCVS analysis (NCJ 248471, 2014), 80% of rape and sexual assault victimizations of female college students aged 18-24 in 1995-2013 were not reported to police.
- **Year reported**: counts are by the calendar year a crime was reported, not when it occurred.
- **Institutional variation**: institutions classify incidents and map their Clery geography themselves.
- **Rates per enrolled student**: on-campus FTE estimates enrolled students of the whole institution who are not exclusively online, not people on campus.
- **Rates**: a rate counts on-campus incidents only, over a 3-year window without 2020. Its interval allows for year-to-year variation in an institution's counts, not for differences in how institutions record and report incidents. A rank range holds for each institution on its own, and only large institutions are on the lists. etl/METHODOLOGY.md ("Limitations of the rates") has the full list.
- **Institution-reported**: the figures are what institutions reported to ED; this project does not audit them.

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

The code in this repository is released under the [MIT License](LICENSE).

The data comes from the U.S. Department of Education (Campus Safety and Security) and the National Center for Education Statistics (IPEDS), which publish it as public information. The MIT License covers this project's code and its own presentation of the data, not the underlying government data.

## Security

To report a security issue, see [SECURITY.md](SECURITY.md). Please do not open a public issue for it.

## Data Citation

The Methodology page (https://collegesafetydata.org/methodology#cite) and every school page give an APA and a BibTeX citation with the build identifier and date. Cite the original sources as well:

1. U.S. Department of Education, Office of Postsecondary Education. Campus Safety and Security Survey. https://ope.ed.gov/campussafety/
2. National Center for Education Statistics. Integrated Postsecondary Education Data System (IPEDS). https://nces.ed.gov/ipeds/

### Build identifier

The build identifier is the SHA-256 of `frontend/public/data/build_inputs.json`, the build record, which lists the checksum of every source file the build read and every data file it published. `audit.json` names it as `audited_build.site_record_sha256`; the site footer shows its first 12 characters. Rebuilding from the same source files gives the same data files, but `metadata.json` (`lastUpdated`) and the build record carry the time of the run, so each run has a new identifier. To check that two builds hold the same figures, compare the `published` checksums in their build records other than `metadata.json`.

## Downloads

`05_generate_json.py` writes flat CSV files (UTF-8, comma-separated, header row) to `frontend/public/data/downloads/`, served at `https://collegesafetydata.org/data/downloads/`:

- `campus-years.csv`: one row per campus and year shown on the site (each year a campus reported to DOE, zeros included). Columns: `year`, `unitid` (DOE campus ID), `base_unitid` (the IPEDS institution, the first six digits), `campus_name` (the campus's own DOE name, or the institution's when DOE gives none), `institution_name`, `city`, `state`, `main_campus`, `doe_release` (the DOE file suffix the year's figures come from, e.g. `222324` for the 2022-2024 release), `counts_in_rankings` (false when every figure the campus reported that year is counted under another campus), `institution_fte` (NCES FTE of the whole institution), `institution_online_pct` (NCES's percent of students enrolled exclusively in distance education), `online_pct_fall` (the fall that share is from), `institution_rate_fte` (the institution's rate denominator that year: its on-campus FTE, the larger of the two estimates below, with any FTE pooled under the merger and shared-campus rules; a 3-year rate divides by the sum over its 3 years), `institution_rate_rule` (the rule that gives the institution no rate that year, and none for any 3-year window that contains the year: `hospital`, `medical`, `listed`, `merger`, `family`, `shared_pooled` or `shared_campus`; empty when none), `institution_oncampus_fte_proportional` (on-campus FTE estimate (a): FTE x (1 - online share)), `institution_oncampus_fte_part_time_first` (estimate (b): the on-campus headcount filled first with full-time students; empty when NCES's headcounts do not allow it), `institution_oncampus_fte_uncertain` (`True` when the estimates differ by more than 25%, estimate (b) cannot be computed, or an institution whose FTE the rate adds has an uncertain estimate, otherwise `False`; empty exactly when the institution has no on-campus FTE that year. In a 3-year window with an uncertain year, the institution's comparisons are given only when both estimates lead to the same result, and it is on no list), `institution_oncampus_fte_uncertain_reason` (`own` when the institution's own estimates make it uncertain, `pooled` when only an institution whose FTE the rate adds does; empty when it is not uncertain) and `medical_center_campus` (`True` when the campus is on the medical-center list, `etl/reference/medical_campuses.csv`, that year). An institution's counts and rates take in its campuses in the United States (territories included) and leave out its campuses abroad: those with an empty `state`, and those in `etl/reference/campuses_abroad.csv`, which DOE lists with a U.S. state. Rates count on-campus incidents only (`On-campus` in `counts-YYYY.csv`).
- `counts-YYYY.csv`, one per year: every nonzero count, by campus, location and offense, as the campus reported it. Columns: `year`, `unitid`, `geo` (`On-campus`, `Residence halls`, `Non-campus`, `Public property`), `offense`, `count`, `counted_under_unitid` (set when the same figures for that location were also reported by another campus, or by the same campus under its new DOE ID; totals and rankings count them under that campus).

To reproduce the site's state and national totals from `counts-YYYY.csv`: leave out `Residence halls` (they are part of on-campus), keep rows where `counted_under_unitid` is empty, and keep campuses whose `state` in `campus-years.csv` is one of the 50 states, DC, PR or VI.
