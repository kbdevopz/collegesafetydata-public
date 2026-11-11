# CollegeSafetyData.org - Data Methodology

This document describes the data sources, calculation methods, and methodological choices used in generating the campus safety statistics for CollegeSafetyData.org.

## Data Sources

### Campus Crime Data
- **Source:** U.S. Department of Education Campus Safety and Security Data
- **URL:** https://ope.ed.gov/campussafety/
- **Coverage:** 2015-2024
- **Legal Basis:** Clery Act (20 U.S.C. § 1092(f))

The Clery Act requires all postsecondary institutions participating in federal student aid programs to disclose campus crime statistics and security information annually.

#### Release File Handling

DOE publishes one data release per collection year, and each release contains
the three most recent calendar years (for example, the 2025 release covers
calendar years 2022-2024). Consecutive releases therefore overlap, and a
campus that reports in one release is sometimes missing from the next (it
closed, merged, or did not submit that year).

Each campus-year (one campus, one calendar year) is taken from the newest
release whose row for that campus and year is not entirely blank across the
16 count files of the release (criminal offenses, VAWA offenses, arrests and
disciplinary actions, each for on-campus, residence halls, non-campus and
public property). A row of zeros counts as reported. Later collections
incorporate corrections that institutions made to previously submitted
figures, so the newest release that has the campus-year wins. All of that
campus-year's figures, in all 16 files, come from that one release:
releases are never mixed within a campus-year, and a blank file or cell is
never filled in from another release. The release used for each campus-year
is recorded in `data/curated/dims/campus_year_sources.parquet` and, per year,
in the crime build record (`build record/crime_inputs.json`,
`campus_year_sources`).

#### Known Errors in DOE Files

Two files of the 2021-2023 release (`Crime2024SAS.zip`, suffix `212223`) are
wrong, and `02_transform_to_parquet.py` handles them by explicit, narrow
rules (`KNOWN_DEFECTS`). They apply only to campus-years taken from that
release, which are campuses missing from the 2022-2024 release:

| File | Error | What we use |
|------|-------|-------------|
| `residencehalldiscipline212223` | Its 2022 and 2023 figures are a copy of `oncampusdiscipline212223` | 2022: residence-hall disciplinary actions from the 2020-2022 release (`202122`). 2023: left blank (no other release has them) |
| `residencehallarrest212223` | It has no `LIQUOR22` column (it has a column named `LIQUOR2` instead, which we do not read) | 2022 residence-hall liquor-law arrests from the 2020-2022 release (`202122`) |

These defective cells are also ignored when deciding whether a campus-year
is blank in that release. If DOE corrects either file, the pipeline stops
and asks for the rule to be updated rather than keep replacing good data.

#### Figures Reported by More Than One Campus

Some campuses report exactly the same figures as another campus: a medical
school's sites repeating their university's main campus figures, several
institutions on one shared campus, or a renumbered campus appearing under
its old and new UNITID. Added up, those numbers would be counted twice.

A block is one campus's figures for one year and one geography (on-campus,
non-campus or public property; residence halls are a subset of on-campus and
are not compared): its 20 counts (11 criminal offenses, 3 VAWA offenses, 3
arrest and 3 disciplinary categories), a blank counting as 0. A campus-year's
whole figures are its three blocks (60 counts). Copies are looked for only
between campuses in the same state (campuses with no state, or outside the
50 states, DC, Puerto Rico and the U.S. Virgin Islands, are not ranked and
are not compared), and every test needs at least 6 counts that are not 0:
fewer match by chance too often to call a copy.

The host of a copy is chosen in this order: its campus-year comes from the
newest release that covers the year (not from an older one), it is a main
campus (UNITID ending in 001), it has more students (the FTE used for rates;
no FTE sorts last), it has the larger total for the campus-year over the
three geographies, it has the lower UNITID. The copies are shadows of the
host. Four rules find them, in this order (a block keeps the first rule's
answer):

1. **Same block:** two or more campuses' blocks of the same year and
   geography have all 20 counts equal. The host is the first by the order
   above; the other blocks are its shadows.
2. **Whole year:** two or more campus-years have all 60 counts equal. Every
   block of the campus-years other than the host's is a shadow, including a
   block with fewer than 6 nonzero counts of its own.
3. **Whole year, in an older release:** a campus-year taken from an older
   release has, in that release, all 60 counts equal to those of another
   campus whose own figures for the year now come from a newer release
   (where that campus may have corrected them). Every block of it is a
   shadow of that campus.
4. **Block, in an older release:** the same for one block of such a
   campus-year (all 20 counts equal).

State and national totals and rankings count a shadow block's figures once,
under the host; a campus-year whose every block with data is a shadow is not
ranked at all. Each school page still shows the
school's full figures as DOE publishes them, and a shadow campus's page names
the host for each year and geography it shares
(`sharedFigures` in its school file). The blocks are listed in
`data/curated/aggs/shared_blocks.parquet`, with the rule that found each
shadow; the older releases' figures the last two rules compare are in
`data/curated/dims/older_release_counts.parquet`.

### Enrollment Data
- **Source:** IPEDS (Integrated Postsecondary Education Data System)
- **URL:** https://nces.ed.gov/ipeds/
- **Files Used:**
  - 2021-2024: DRVEF (Derived Fall Enrollment) files, with NCES's FTE and the percent of students enrolled exclusively in distance education (fall 2024 is provisional release data)
  - 2015-2020: the DRVEF tables of NCES's final IPEDS Access databases, copied into `etl/reference/ipeds_official_fte.csv` (see below); the EF (Fall Enrollment) files only for headcounts

## FTE (Full-Time Equivalent) Enrollment

FTE is the denominator of the per-student rates: full-time students count fully, part-time students in part. The site uses the FTE that NCES (the National Center for Education Statistics) publishes for each institution and fall, for every year. It does not calculate FTE.

| Years | Source of NCES's FTE |
|-------|----------------------|
| 2021-2024 | The year's DRVEF file (`drvef<year>_rv.csv` when NCES has published the final revised file, otherwise `drvef<year>.csv`) |
| 2015-2020 | Table `DRVEF<year>` in NCES's final IPEDS database of the collection year (`IPEDS_2015-16_Final.zip` to `IPEDS_2020-21_Final.zip`, Microsoft Access) |

NCES publishes FTE for falls before 2021 only inside those databases (60 to 77 MB each). `etl/01c_extract_ipeds_official.ps1` (Windows only: it needs Microsoft's 64-bit Access ODBC driver) downloads them, checks each zip's size and SHA-256 against `etl/reference/ipeds_official_sources.json`, and writes FTE and PCTDEEXC (percent of students enrolled exclusively in distance education) of every institution to `etl/reference/ipeds_official_fte.csv`. Both files are committed, so the build (`02b_transform_ef_enrollment.py`) does not need Access or the downloads. `00_check_for_updates.py` checks on every run that NCES still publishes each database at the recorded size; a different size means it may have been re-issued, and the script compares its SHA-256.

An institution-year whose FTE NCES left blank has no rate that year (23 institutions in 2019).

### Earlier estimate for 2015-2020 (no longer used)

Earlier builds estimated 2015-2020 FTE from the EF headcounts with one formula for every institution:

```
FTE = FT_Undergrad + FT_Graduate + (PT_Undergrad × 0.403543) + (PT_Graduate × 0.361702)
```

That matched NCES's FTE exactly for only 58% of institution-years (46% of those with crime data) and was off by more than 5% for about 830 institutions a year (4,978 institution-years in 2015-2020), so it was replaced by NCES's own figures.

## Crime Rate Calculation

Crime rates are expressed as incidents per 10,000 FTE students:

```
Rate = (Incident Count / FTE) × 10,000
```

### Rate Display Thresholds
- Rates are only displayed for institutions with FTE ≥ 1,000 to avoid misleading statistics from small sample sizes
- Institutions with FTE < 1,000 or fewer than 10 incidents are marked with an asterisk (*) to indicate statistical caution

## Geographic Classifications

Crime data is reported across multiple geographic categories:

| Geography | Description |
|-----------|-------------|
| On-campus | All property owned or controlled by the institution |
| Residence halls | A subset of on-campus (student housing only) |
| Non-campus | Property owned but not contiguous to campus |
| Public property | Public property adjacent to campus |
| All | Sum of On-campus + Non-campus + Public property |

**Important:** Residence hall incidents are a subset of on-campus incidents and should not be added to on-campus counts.

State and national totals and rankings leave out shadow blocks (see
"Figures Reported by More Than One Campus" above), so figures that two
campuses report identically count once, under the host campus.

## Offense Categories

### Criminal Offenses (Clery Act)
- Murder
- Negligent Manslaughter
- Rape
- Fondling
- Incest
- Statutory Rape
- Robbery
- Aggravated Assault
- Burglary
- Motor Vehicle Theft
- Arson

### VAWA Offenses (Violence Against Women Act)
- Domestic Violence
- Dating Violence
- Stalking

### Arrests and Disciplinary Referrals
- Weapons (Arrests and Disciplinary Actions)
- Drug Law (Arrests and Disciplinary Actions)
- Liquor Law (Arrests and Disciplinary Actions)

**Note:** The "All Offenses" category sums criminal offenses, VAWA offenses, AND arrests/disciplinary referrals. High counts in this category may reflect drug/alcohol enforcement rather than violent crime.

## Data Limitations

### Underreporting
Clery data represents only reported incidents. Research indicates significant underreporting:
- ~80% of campus crimes are never reported to authorities (DOJ NCVS)
- Only ~20% of college sexual assaults are reported (RAINN)
- Higher reported numbers may indicate better reporting culture, not more crime

### Institutional Variation
Reporting practices, police staffing, and definitions may vary by institution. Cross-institution comparisons should be made with caution.

### Temporal Lag
There is approximately a 1-year lag between when incidents occur and when data is published by the Department of Education.

### Definition Changes
- 2013: FBI updated rape definition to be gender-neutral
- 2014: VAWA offenses (domestic violence, dating violence, stalking) added to Clery requirements

## Validation

Our data pipeline includes validation steps to ensure accuracy:
1. Cross-reference of UNITID (institution ID) with IPEDS directory
2. Verification that offense counts sum correctly
3. Comparison of calculated FTE against official DRVEF values where available
4. Spot checks against known institutions (Ivy League, major state universities)
5. An audit (`07_comprehensive_audit.py`, check 8) that finds the shared blocks again from the fact table and the older releases' figures, and verifies that every ranking entry counts the school's figures without its shadow blocks

## Source Code

The complete ETL (Extract, Transform, Load) pipeline is open source and available for inspection:
- Data download: `01a_download_doe.py`, `01b_download_ipeds.py`
- Enrollment processing: `02a_transform_enrollment.py`, `02b_transform_ef_enrollment.py`
- Crime data processing: `03_transform_crimes.py`
- Aggregation: `04_create_aggregates.py`
- JSON generation: `05_generate_json.py`

## Contact

For questions about methodology or to report data issues, please open an issue on the GitHub repository.

## References

1. U.S. Department of Education. Campus Safety and Security Data Analysis Cutting Tool. https://ope.ed.gov/campussafety/
2. National Center for Education Statistics. IPEDS Survey Components. https://nces.ed.gov/ipeds/survey-components/
3. Clery Center. Summary of the Jeanne Clery Act. https://clerycenter.org/policy/the-clery-act/
4. RAINN. Campus Sexual Violence: Statistics. https://www.rainn.org/statistics/campus-sexual-violence
