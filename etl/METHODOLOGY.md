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

#### Zero Versus Not Reported

A campus reported a year when it is in `campus_year_sources.parquet` for that
year: its release row has at least one count cell that is not blank. A
reported year without any incident is a 0, not missing data:

- its school page shows 0 for that year, and its charts show 0 there;
- it is ranked with 0 for every category it had none of, after the campuses
  with incidents, all sharing the next rank and listed by name, then UNITID
  (the tie rule below); its institution is ranked with rate 0 when the rate
  rules below allow it;
- a campus that reported but never had an incident has a school page too.

A reported zero can reflect how an institution classifies or reports
incidents, not only how safe it is; the rate rankings say so where their
zero rows begin.

A year a campus did not report has no figures at all. Its school page lists
it as not reported, its charts leave a gap there rather than a 0, and it is
in no ranking for that year. A campus-year whose every figure is counted
under another campus (see Figures Reported by More Than One Campus) is not
ranked, with 0 or otherwise.

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

### Rates are per institution
NCES publishes FTE for each institution, not for each campus: every campus
of an institution (all campuses whose UNITID starts with the same six
digits, the base UNITID) carries the institution's FTE. A rate therefore
divides the incidents of all the institution's campuses that year by the
institution's FTE (`04_create_aggregates.py`, `create_institution_tables`):

- A campus counts for its institution in a year when it reported that year
  (`campus_year_sources`) and its figures are not all shadow blocks.
- The incidents are counted as in rankings: the sum of on-campus, non-campus
  and public property (residence halls are part of on-campus), shadow blocks
  left out, campuses in any state.
- Rate rankings list institutions, one row each, under the institution's
  name. The row links to the main campus (UNITID ending in 001) when that
  campus counts that year, otherwise to the institution's campus with the
  most incidents that year (ties: the lowest UNITID), and is listed in that
  campus's state. Rankings by count still list each campus.
- School pages and Compare show the institution's rate and, for an
  institution of more than one campus, label it "all N campuses combined".

### Who rate rankings leave out
Rate rankings list an institution only when that year (both in `config.py`,
`MIN_FTE_FOR_RATE` and `ONLINE_EXCLUSION_PCT`):
- it has at least 1,000 FTE students, so a few incidents do not swing its
  rate; and
- fewer than 50% of its students are enrolled exclusively in distance
  education (NCES's PCTDEEXC, in the same DRVEF/EF tables as the FTE). Clery
  figures cover the campus, which most students of a mostly online
  institution never attend, so its rate is not comparable. An institution
  without that figure is not left out (none of the institutions that
  reported and have an FTE lacks it in 2015-2024).

For 2020 and 2021 the test uses each institution's fall 2019 share
(`ONLINE_SHARE_YEAR` in `config.py`), because temporary remote teaching
during the pandemic does not make a school an online-only school. When NCES
has no 2019 figure for an institution, that year's own share is used (66
institutions in 2020 and 102 in 2021, of which 1 and 2 have 1,000+ FTE).
Judged by their own 2020 shares, 676 of the 2,264 institutions with 1,000+
FTE in 2020 would have been left out, 582 of them under 50% in 2019. Of the
institutions that reported Clery figures and have 1,000+ FTE, the online
test leaves out 103 of 2,320 in 2019, 96 of 2,264 in 2020, 94 of 2,261 in
2021, 204 of 2,237 in 2022, 188 of 2,243 in 2023 and 191 of 2,268 in 2024.
School pages for 2020 and 2021 say which fall's share they used.

School pages still show these institutions' rates, with a note saying why
they are not ranked. Rates with fewer than 10 incidents, or under 1,000 FTE,
are marked with an asterisk (*) to indicate statistical caution.

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

The categories and their definitions are the regulation's: the crimes in
Appendix A to Subpart D of Part 668 (from the FBI's UCR SRS and NIBRS
manuals), and dating violence, domestic violence, stalking and the
locations in 34 CFR 668.46(a). The site shows the plain-language versions
in `frontend/src/data/sources.ts` (Methodology page, "Definitions").

### Criminal Offenses (Clery Act)
- Murder (DOE: murder and nonnegligent manslaughter)
- Negligent Manslaughter (DOE: manslaughter by negligence)
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

### Not shown
DOE also publishes hate crimes (by bias and offense, including larceny-theft,
simple assault, intimidation and vandalism, which are reported only when they
are hate crimes), unfounded crime reports and fire statistics. The pipeline
does not read them, and the site does not show them. Hate crimes are a
breakdown, not a separate total: the criminal offenses above that were hate
crimes (already in those counts, so adding them would count them twice),
plus four crimes counted only when they are hate crimes (668.46(c)(1)(iii)).
The site has not added that breakdown. Unfounded reports are reports
withheld from the counts.

### How institutions count (34 CFR 668.46)
- A crime is counted when it is reported to a campus security authority or
  local police and occurred on the institution's Clery geography
  (668.46(c)(1)). Reports that sworn or commissioned law enforcement
  personnel determine to be false or baseless are "unfounded" and left out
  (668.46(c)(2)(iii)).
- Counts are by the calendar year in which the crime was reported, not the
  year it occurred (see "Year of report" below).
- Hierarchy Rule: of several criminal offenses in one incident, only the most
  serious is counted (668.46(c)(9)(v)); arson is always counted, and a sex
  offense in the same incident as a murder is counted along with it
  ((c)(9)(vi)-(vii)). VAWA offenses are not subject to the Hierarchy Rule and
  are counted in addition (2016 Handbook, chapter 3).
- Arrests count people arrested (the 2016 Handbook: persons processed by
  arrest, citation or summons). Disciplinary referrals count persons "not
  included" in the arrests who were referred for campus disciplinary action
  (668.46(c)(1)(ii)(B)), so a person both arrested and referred is counted
  once, as an arrest. A violation of institutional policy alone, with no
  violation of law, is not counted (2016 Handbook, chapter 3).
- Stalking that continues across calendar years is counted in each year in
  which it is reported (668.46(c)(6)).
- Residence-hall figures are the on-campus crimes that took place in student
  housing (668.46(c)(5)), so they are part of on-campus and never added to
  totals.

### Year of report
Clery statistics are compiled by the calendar year in which a crime was
reported to campus security authorities or police (the 2016 Handbook,
chapter 2: statistics are disclosed by "the year in which the crimes were
reported"). A year's count can
therefore include incidents that occurred years earlier: when many people
report past abuse at one institution within a short time, that campus's
counts for the years of the reports jump. On this site, for example, the
national number 1 campus by count of all criminal offenses was Ohio State
University in 2018, 2019 and 2021 (mostly fondling) and the University of
Michigan in 2020 (fondling and rape), and Michigan State University's 1,012
rapes in 2018 are about 12% of that year's national total. These are the
figures the institutions reported; this site does not mark or remove them.

### Totals shown on the site
- **All criminal offenses** (the default view of rankings, school pages and comparisons): the 11 criminal offenses above, added up.
- **All categories (crimes, arrests, referrals)**: every category added up, criminal offenses, VAWA offenses, arrests and disciplinary referrals. These are different kinds of counts. Arrests and disciplinary referrals count people (each person arrested or referred), not incidents, and an incident of dating violence, domestic violence or stalking can also be counted as a criminal offense such as aggravated assault. So this total is not a number of incidents, and high totals often reflect drug and alcohol enforcement rather than violent crime. It is still available (`?offense=all` on the rankings page).

## Comparing Years (2015-2024)

Sourced changes that affect comparisons over time. The notes the site shows
next to charts and rankings are in `frontend/src/data/seriesNotes.ts`
(`SERIES_NOTES`, by year; `SERIES_CONTEXT`, every year); add a note there.

- **2020-2021, COVID-19 pandemic.** Many campuses closed or taught remotely.
  NCES (Fast Facts: Distance learning, https://nces.ed.gov/fastfacts/display.asp?id=80):
  15% of undergraduates took only distance education courses in fall 2019,
  44% in fall 2020 and 28% in fall 2021. ED changed only deadlines (Electronic
  Announcement of July 10, 2020: Annual Security Reports by December 31, 2020;
  survey open November 18, 2020 to January 14, 2021), not what is counted.
  School pages and Compare shade 2020-2021 on trend charts and add a note;
  rankings for 2020 or 2021 show the note too.
- **2022-2023, residence-hall figures from DOE's 2021-2023 release.** See
  Known Errors in DOE Files. `metadata.json` (`knownDefects`) lists, for each
  error, the campuses whose figures for that year come from that release, and
  their school pages say which residence-hall figures are replaced or left
  out.
- **Every year: counts are by the year reported** (see Year of report).
- **VAWA final rule** (79 FR 62752, October 20, 2014; effective July 1, 2015):
  added dating violence, domestic violence and stalking, and replaced forcible
  and nonforcible sex offenses with rape, fondling, incest and statutory rape.
  ED did not require institutions to revise 2013 or 2014 statistics. The site
  starts at 2015; do not join its series with earlier figures.
- **October 2020: the 2016 Handbook was rescinded** and replaced by the Clery
  Act Appendix for the FSA Handbook, "effective for the reporting year
  following publication". ED said no statutory or regulatory requirement
  changed. The Appendix applies no measurable distance to "reasonably
  contiguous" and accepts an institution's reasonable interpretation of terms.
  No effect on the figures has been shown; listed as context only.
- **January 2021: the FBI retired the SRS.** The Clery regulation still
  defines the crimes by the SRS manual (668.46(c)(9), Appendix A), so the
  definitions did not change.

Checked and not listed as breaks: hate-crime categories (not shown); the 2024
Title IX rule (it amends 34 CFR part 106, not the Clery statistics); the Stop
Campus Hazing Act of December 23, 2024 (its statistics start after 2024); a
change to motor vehicle theft or any other definition (none found: eCFR's
version history of 668.46 and Appendix A, which begins in December 2016, has
no substantive amendment); an item the survey stopped collecting (none found
for the categories shown).

## Rankings

Each ranking lists schools by their count, largest first. Schools with the same count share a rank (standard competition ranking: 1, 2, 2, 4, so the rank after a tie skips the places the tie takes) and are listed by name, then by UNITID. Rate rankings rank institutions' rates the same way, ties by institution name, then base UNITID. Every campus that reported the year is in its rankings: those with none of a category are the last tie, with 0 (see Zero Versus Not Reported).

## Data Limitations

The site's Limitations section (Methodology page) has the same points.

### Reports, not victimization
Clery data counts crimes reported to campus security authorities or local
police. Many are never reported: in the Bureau of Justice Statistics'
analysis of the National Crime Victimization Survey (Sinozich and Langton,
NCJ 248471, 2014, https://bjs.ojp.gov/content/pub/pdf/rsavcaf9513.pdf), 80%
of rape and sexual assault victimizations of female college students aged
18-24 in 1995-2013 were not reported to police. The NCVS does not measure
reports to campus officials, which Clery counts include, so this is not a
Clery figure. A higher count can mean more crime, more reporting, or both.

### Year of report
Counts are by the calendar year a crime was reported, not the year it
occurred (see Year of report above).

### Institutional variation
Institutions classify incidents, designate campus security authorities and
map their own Clery geography; ED's 2020 Appendix accepts an institution's
reasonable interpretation of terms and applies no measurable distance to
"reasonably contiguous". The same incidents can be reported differently.

### Rates are per enrolled student
FTE is NCES's fall full-time-equivalent enrollment of the whole institution.
It does not count residents who are not students, employees, visitors or
patients. Where Clery geography includes places used mostly by others (a
hospital, for example), a rate per student says little about risk to a
student.

### Small numbers, zeros and unweighted totals
Rates with fewer than 10 incidents or under 1,000 FTE are marked *; a few
incidents move such an institution many places. A rate of 0 is a reported
zero, which can reflect classification or chance. "All criminal offenses"
adds unlike crimes with equal weight; motor vehicle theft was about 15% of
the national criminal total in 2015 and about 37% in 2024.

### Institution-reported, not audited
The figures are what institutions submitted to ED's survey. This project
does not check them against institutions' records; its audit checks that the
published files agree with the pipeline's tables built from DOE's and NCES's
files.

### Reporting lag
DOE's release for collection year R holds calendar years R-3 to R-1, so the
newest year is about a year old when it is published.

### Definition changes
See Comparing Years: the categories in use since the VAWA final rule took
effect on July 1, 2015 apply to every year shown.

## Validation

These checks test internal consistency: that the published files agree with
each other and with the pipeline's tables built from DOE's and NCES's files.
They do not test institutions' figures against institutions' records.
1. `06_validate.py` checks row counts per year, that no count is negative, that every Ivy League campus is present, offense coverage and that the JSON files parse
2. The audit (`07_comprehensive_audit.py`, check 7) verifies that the aggregates hold exactly the fact table's counts
3. The same audit (check 9) verifies that every FTE and online share is NCES's own published figure
4. The same audit (check 4) recomputes every published rate from its count and FTE
5. The same audit (`07_comprehensive_audit.py`, check 8) that finds the shared blocks again from the fact table and the older releases' figures, and verifies that every ranking entry counts the school's figures without its shadow blocks
6. The same audit (check 5) verifies that every ranking is listed in ranking order and that every rank is 1 + the number of schools with a larger count (or rate)
7. The same audit (check 10) recomputes every institution's campuses, counts, link campus, FTE and online share from the fact table and NCES's enrollment, without the pipeline's code, and verifies that every rate ranking lists exactly the institutions the rules above allow, with rate = count / FTE × 10,000, and that every rankings file lists exactly the campuses that reported its year (those with 0 included)
8. The same audit (checks 1 and 2) verifies that every campus that reported a year has a school page and is in the site search, and that each page has exactly the years the campus reported, 0 included, and lists the others as not reported

## Downloads and build identifier

`05_generate_json.py` also writes `downloads/campus-years.csv` and one
`downloads/counts-YYYY.csv` per year under `frontend/public/data/`, from the
same tables as the site's JSON. The README ("Downloads") describes their
columns and how to reproduce the site's totals from them. The build
identifier is the SHA-256 of `build_inputs.json`, which `audit.json` names
as `audited_build.site_record_sha256`; it changes with every run, because the
build record and `metadata.json` carry the time of the run.

## Source Code

The complete ETL (Extract, Transform, Load) pipeline is open source. Run the
steps in this order (README, "Full ETL Pipeline"):
- `00_check_for_updates.py`: check DOE and NCES for newer files and the local build against its records
- `01_download_raw_data.py`: download and extract the DOE crime releases
- `01b_download_ipeds.py`: download the IPEDS enrollment files
- `01c_extract_ipeds_official.ps1` (Windows, optional): re-extract NCES's 2015-2020 FTE from its Access databases into `etl/reference`
- `02_transform_to_parquet.py`: DOE files to the fact table, one release per campus-year
- `02b_transform_ef_enrollment.py`: NCES's 2015-2020 FTE (from `etl/reference`) and EF headcounts
- `02a_transform_enrollment.py`: DRVEF FTE for 2021 onward
- `03_build_dimensions.py`: campus and offense tables
- `04_create_aggregates.py`: shared figures, institution tables, rankings tables
- `05_generate_json.py`: site JSON and the CSV downloads
- `06_validate.py`: checks of the generated files
- `07_comprehensive_audit.py`: the audit published as `audit.json`

## Contact

For questions about methodology or to report data issues, please open an issue on the GitHub repository.

## References

1. U.S. Department of Education. Campus Safety and Security. https://ope.ed.gov/campussafety/
2. U.S. Department of Education. Campus Security. https://www.ed.gov/teaching-and-administration/safe-learning-environments/school-safety-and-security/campus-security
3. 34 CFR 668.46, Institutional security policies and crime statistics. https://www.ecfr.gov/current/title-34/subtitle-B/chapter-VI/part-668/subpart-D/section-668.46
4. Appendix A to Subpart D of Part 668, Crime Definitions. https://www.ecfr.gov/current/title-34/subtitle-B/chapter-VI/part-668/appendix-Appendix%20A%20to%20Subpart%20D%20of%20Part%20668
5. U.S. Department of Education. The Handbook for Campus Safety and Security Reporting, 2016 Edition (rescinded 2020; kept for historical purposes). https://www.ed.gov/sites/ed/files/admins/lead/safety/handbookfsa.pdf
6. U.S. Department of Education. Clery Act Appendix for FSA Handbook (October 2020). https://www.ed.gov/sites/ed/files/admins/lead/safety/cleryappendixfinal.pdf
7. Federal Student Aid. Rescission of and Replacement for the 2016 Handbook (October 9, 2020; updated January 19, 2021). https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2020-10-09/rescission-and-replacement-2016-handbook-campus-safety-and-security-reporting-updated-jan-19-2021
8. Violence Against Women Act final rule, 79 FR 62752 (October 20, 2014). https://www.govinfo.gov/content/pkg/FR-2014-10-20/pdf/2014-24284.pdf
9. Federal Student Aid. Additional regulatory flexibilities related to Coronavirus (COVID-19) (July 10, 2020). https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2020-07-10/additional-regulatory-flexibilities-related-coronavirus-covid-19
10. National Center for Education Statistics. IPEDS. https://nces.ed.gov/ipeds/ ; DRVEF 2023 data dictionary (FTE, PCTDEEXC). https://nces.ed.gov/ipeds/datacenter/data/DRVEF2023_Dict.zip
11. National Center for Education Statistics. Fast Facts: Distance learning. https://nces.ed.gov/fastfacts/display.asp?id=80
12. Bureau of Justice Statistics. Rape and Sexual Assault Victimization Among College-Age Females, 1995-2013 (NCJ 248471, 2014). https://bjs.ojp.gov/content/pub/pdf/rsavcaf9513.pdf
