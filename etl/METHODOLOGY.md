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
  (the tie rule below);
- a campus that reported but never had an incident has a school page too.

An institution rated in a 3-year window with no on-campus incident of a code
in it has a rate of 0 for that code, with its interval, and is on that
code's list when it meets the list rule (rate rules 4 and 10). A reported
zero can reflect how an institution classifies or reports incidents, not
only how safe it is.

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

FTE is the basis of the per-student rates' denominator, an estimate of on-campus FTE made from it (rate rule 3): full-time students count fully, part-time students in part. The site uses the FTE that NCES (the National Center for Education Statistics) publishes for each institution and fall, for every year. It does not calculate FTE.

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

A rate is a 3-year average: the reported on-campus incidents of one code in
a 3-year window per 10,000 on-campus students a year.

```
Rate = N / F × 10,000
N = on-campus incidents of the code, summed over the window's 3 years
F = on-campus FTE, summed over the same 3 years ("student-years")
```

A rate per 10,000 student-years is a rate per 10,000 on-campus students a
year. Each rate has a 95% interval and is compared with the national rate.
Violent crimes, criminal offenses except motor vehicle theft, and burglary
also have ordered lists of large institutions, on which each position is a
range. The rules below say which institutions and codes have a rate and how
each figure is made; "Published rate files" lists the files that hold them.

### Rates are per institution
NCES publishes FTE for each institution, not for each campus: every campus
of an institution (all campuses whose UNITID starts with the same six
digits, the base UNITID) carries the institution's FTE. A rate is therefore
the institution's: the on-campus incidents of all its campuses in the
United States over its on-campus FTE (`04_create_aggregates.py`,
`create_institution_tables`, for the institution-years; `etl/rates.py` for
the rates):

- A campus counts for its institution in a year when it reported that year
  (`campus_year_sources`) and its figures are not all shadow blocks.
- The institution's counts are its counting campuses' counts per geography
  (residence halls are part of on-campus), shadow blocks left out, campuses
  with a state (territories included). A campus abroad (rule 17) is not in
  its institution's counts or rates, but stays in its own school file. The
  rate uses the on-campus counts only (rule 2).
- Each institution-year has a link campus: the main campus (UNITID ending
  in 001) when that campus counts that year, otherwise the institution's
  campus in the United States with the most incidents that year (ties: the
  lowest UNITID). A rate entry carries the institution's name, link campus
  and state of the window's last year. Rates cover the institutions whose
  link campus is in `US_STATES` (the 50 states, DC, PR and VI); an
  institution elsewhere (Guam, the Federated States of Micronesia, ...) has
  counts but no rate (rule 4). Rankings by count still list each campus.
- Every school file of an institution that has a rates file names it
  (`institution.ratesFile`), so all of an institution's campuses point to
  the same rates.

### Rate rules
These are the rules every rate follows. The constants are in `config.py`
and are published in `metadata.json` `rateRules`. The institution-year
figures (on-campus FTE, pooled FTE, population rules) are made in
`04_create_aggregates.py`; the windows, intervals, comparisons, lists and
flags in `etl/rates.py`, which `05_generate_json.py` runs.
`07_comprehensive_audit.py` checks them again without that code: check 10
the institution-year figures, check 12 every published rate figure, check
13 the calibration of the intervals and check 14 the medical-center campus
list (see Validation). No rule changes a count or the order of a ranking by
count; rule 15 adds a flag to rankings by count. Figures that depend on the
build are named below by the field that holds them, in `metadata.json`
(`rateRules`, `rateStats`) or in the rate files.

1. **3-year windows** (`RATE_WINDOW_YEARS` = 3, `RATE_SKIP_YEARS` = 2020;
   `rateRules.windowYears`, `skipYears`, `windows`). A rate covers 3
   consecutive calendar years, none of them 2020: with data for 2015-2024
   the windows are 2015-2017, 2016-2018, 2017-2019, 2021-2023 and
   2022-2024. In fall 2020 many institutions taught remotely (44% of
   undergraduates took only distance education courses, against 15% in fall
   2019; see Comparing Years), so that year's enrollment does not measure
   who was on campus. 2020 keeps its counts but has no rate, and no window
   contains it. Comparisons and lists are made for windows only; the
   single-year rates of rule 13 serve the trend on school pages.
2. **Numerator: on-campus incidents** (`RATE_CODES`; `rateRules.codes`). N
   is the institution's on-campus incidents of the code (DOE's "On campus",
   which includes residence halls), summed over the window's 3 years (`n`;
   per year `nByYear`). Its non-campus and public-property incidents in the
   same years are published beside the rate as counts (`nNoncampus`,
   `nPublic`) and are not in it: the denominator counts students, and how
   much public property next to campus an institution reports depends on
   where it is and how it maps its Clery geography. The codes with a rate
   are `violent` (murder and nonnegligent manslaughter, rape, robbery,
   aggravated assault), `criminal_xmvt` (the 11 criminal offenses except
   motor vehicle theft), `burglary`, and the single offenses `rape`,
   `fondling`, `robbery`, `aggravated_assault`, `stalking`,
   `dating_violence` and `domestic_violence`. Every other code has counts
   only (rule 14).
3. **Denominator: on-campus student-years** (`oncampus_estimates`,
   `ONLINE_UNCERTAIN_RATIO`, `ONLINE_SHARE_YEAR`;
   `rateRules.onlineUncertainRatio`, `onlineShareYear`). Clery figures cover
   the campus, so each year's denominator is an estimate of the FTE without
   students enrolled exclusively in distance education. NCES gives their
   share of the fall headcount (PCTDEEXC), not of FTE, so 04 makes two
   estimates: (a) proportional, FTE x (1 - PCTDEEXC / 100); (b) part-time
   first, the on-campus headcount H x (1 - PCTDEEXC / 100) filled first with
   full-time students (FT_on = min(FT, on-campus headcount)), the rest
   part-time, each counting (FTE - FT) / PT as in the institution's FTE; by
   level (PCUDEEXC, PCGDEEXC) when the share is the year's own and DRVEF has
   them (2021 on), else from the totals. Headcounts are NCES's (DRVEF 2021
   on, EF A before). On-campus FTE is the larger estimate, rounded half up.
   When the larger is more than 5/4 of the smaller (more than 25% apart) or
   (b) cannot be computed (headcounts that do not add up), the year's
   on-campus FTE is uncertain (`fteUncertain`; rule 5). For 2020 and 2021
   the share is the institution's fall 2019 share, so those years divide by
   the same kind of enrollment as the others; when NCES has no 2019 figure
   the year's own share is used (`rateStats.institutionYears.onlineOwnYear`).
   2020 has no rate, so the 2019 share enters the 2021 rates and the count
   flag's reference for 2020 and 2021 (rule 15). The number of institutions
   with an uncertain on-campus FTE
   (`rateStats.institutionYears.byYear[y].fteUncertain`) rises in 2022, the
   first year after 2020-2021 that uses each fall's own share. An
   institution without PCTDEEXC would keep its full FTE (none with an FTE
   lacks it in 2015-2024).

   A year's denominator adds another institution's on-campus FTE in two
   cases (`rateStats.institutionYears.pooled` counts them):
   - Merger (`merger_rate_rules`): in a year DOE reports a campus under two
     institutions (its old and new ID), the institution whose FTE holds its
     students is the one with an FTE or, when both have one, the one that
     reported only campuses linked to campuses of the other. When the other
     institution counts the campus and the students' institution counts no
     campus of its own, the other's denominator adds the students'
     institution's on-campus FTE. The other cases are population rules
     (rule 4, `merger`).
   - Shared campus (`shared_rate_rules`): for a shadow block whose host
     campus belongs to another institution (not two IDs of one campus), when
     the shadow's institution counts no campus of its own that year and has
     one host institution, the host's denominator adds its on-campus FTE.

   A denominator that adds another institution's FTE is uncertain too when
   that institution's is (`fteUncertain` reason `pooled`; `own` when the
   institution's own estimates differ). The window's F (`fteYears`) is the
   sum of the 3 years' denominators (`fteByYear` in the institution file).
4. **Who is rated** (`MIN_FTE_FOR_RATE` = 1,000, `HOSPITAL_CODE`,
   `MEDICAL_CARNEGIE`, `reference/rate_population_exclusions.csv`,
   `merger_rate_rules`, `split_family_exclusions`; `rateRules.minFte`,
   `rateStats.definitions.rated`). An institution is rated in a window when
   DOE has figures for it (a counting campus) in each of the 3 years, its
   link campus in the window's last year is in the 50 states, DC, Puerto
   Rico or the U.S. Virgin Islands, its denominator (rule 3) is at least
   1,000 in each year, and no population rule applies to it in any of the 3
   years. The population rules apply to one institution-year each (the
   first that applies is recorded, `rate_rule`):
   - `hospital`: the IPEDS HD file says the institution has a hospital
     (HOSPITAL = 1).
   - `medical`: its Carnegie basic classification is "Special Focus
     Four-Year: Medical Schools & Centers" (25 in C15BASIC, C18BASIC and
     C21BASIC) or the 2021 "Special Focus Research Institution" category
     (C21BASIC 27; 20 of its 22 institutions in HD2024 were 25 in C18BASIC).
   - `listed`: `etl/reference/rate_population_exclusions.csv` names it with
     a sourced reason: Gallaudet University 2015-2024 (its campus also holds
     the Clerc Center's Kendall Demonstration Elementary School and Model
     Secondary School for the Deaf, whose pupils are not in its FTE),
     AdventHealth University 2015-2024 (its main campus's Clery geography
     includes a hospital that IPEDS does not flag), The University of
     Tennessee Health Science Center 2015-2017 and Albert Einstein College
     of Medicine 2019-2020 (the years IPEDS gives them no Carnegie basic
     classification).
   - `merger`: in the merger case of rule 3, both institutions when the
     students' institution cannot be told; the other institution when it
     counts the campus but cannot add the students' FTE; the students'
     institution when its copy of the campus is the shadow but it counts
     other campuses of its own; and, when one institution's FTE would be
     added to two or more others, those others. A campus with no incident
     that year (under either ID, any category) needs none of this.
   - `family`: every institution of a merged group, in a year when a member
     without an FTE counts a campus with incidents that no member with an
     FTE also counts.

   The campuses of hospitals and medical schools hold many people who are
   not in FTE (patients, visitors, clinical and research staff, pupils), so
   a rate per student would not describe them. Rule 16 covers medical
   centers these rules do not catch. `rateStats.institutionYears.rules[rule]`
   gives, per rule, the institution-years it is the first rule for
   (`institutionYears`) and those of them in the national scope with a
   denominator of 1,000 or more (`withFte`).

   An institution that is not rated in a window has no rate for it. Its
   institution file (`rates/institutions/{base}.json`, when it has one)
   gives the first status that applies, in this order: `missingYears` (not
   in DOE's data in each of the 3 years; `years` lists those it is in),
   `scope` (link campus outside the 50 states, DC, PR and VI), `size`
   (denominator under 1,000, or none, in at least one year; `fteByYear`),
   `excluded` (a population rule in at least one year; `rules` gives each
   such year's rule). A rated window has the status `rated`. The window
   files list exactly the rated institutions (`summary.rated`;
   `rateStats.windows[w][code].rated`).
5. **Reasons** (`why`; `MEDICAL_CAMPUS_SHARE` = 1/4, `SHARED_MAX_SHARE` =
   1/20; `rateRules.medicalShare`, `sharedShare`). Per window and code, a
   rated institution has the first of these reasons that applies, or none:
   - `online`: its on-campus FTE (rule 3) is uncertain in at least one of
     the 3 years (`fteUncertain`, `own` or `pooled` per year). The rate and
     interval use the larger estimate. Each comparison (rules 8 and 9) is
     made twice, with F from the larger and from the smaller estimates
     (`fteYearsSmaller`; `verdictLargerFte`, `verdictSmallerFte`): when the
     two agree, that is the verdict; when they differ, the verdict is
     `undetermined` (`undeterminedReason` `estimates`, or
     `noSecondEstimate` when the smaller estimate is missing for a year).
     Its incidents and student-years are not in the national and peer rates
     (rule 7).
   - `medical_campus`: N is above 0 and its incidents at listed
     medical-center campuses (rule 16) are at least 1/4 of N. Those
     incidents (`medical`) are the on-campus incidents at a listed campus
     less those in its residence halls: a medical center's patients,
     visitors and staff are not students.
   - `shared`: (sharedIn + sharedOut) × 20 > N + sharedOut, all on campus
     and summed over the window. These figures come from the shared
     campuses rule 3 does not pool (the shadow's institution counts campuses
     of its own, or its figures count under two or more host institutions):
     `sharedIn` is the institution's on-campus figures that a campus of
     another institution also reports, and `sharedOut` its on-campus
     figures for its own campus that count under another institution's
     campus (not in its N). Above that share, the institution's count is
     not exactly its own.

   A reason never takes away the rate, interval or verdict, and an
   institution with a reason is on no list (rule 10). Each window file's
   `summary.byWhy` counts the rated institutions per reason.
6. **Interval** (`RATE_CI_LEVEL` = 0.95, `RATE_DISPERSION`,
   `RATE_DISPERSION_OTHER`, `RATE_RAMP`, `count_interval`;
   `rateRules.ciLevel`, `dispersion`). Institutions' yearly counts vary more
   than Poisson counts. For a yearly mean m the model's variance is

   ```
   Var(m) = m + c × g(m) × m^1.5,   g(m) = min(2, max(1, m / 10))
   ```

   the NB-P variance function with exponent 1.5 (Greene 2008), with a ramp
   g on its second term that rises from 1 at 10 a year to 2 at 20 a year,
   where counts vary more than the exponent alone allows
   (`dispersion.power`, `dispersion.ramp`). The constant c is per code
   (`dispersion.c`): the codes in `dispersion.fitted` have their own,
   fitted on on-campus counts of institutions with a rate (`config.py`
   describes the fit), and the others share `dispersion.other`. Each window
   file gives its code's c (`c`). For a window total N over its 3 years the
   variance-to-mean ratio is

   ```
   phi(N) = 1 + c × g(N/3) × sqrt(N/3)
   ```

   and the interval is phi times the gamma interval of the effective count
   m = N / phi: lower phi × G(0.025; m) (0 when N = 0), upper
   phi × G(0.975; m + 1), G the gamma quantile (Fay and Feuer 1997;
   Garwood's exact Poisson interval when phi = 1), divided by F and
   multiplied by 10,000 (`lo`, `hi`). Audit check 12 checks that neither
   bound falls as N rises (`details.A5`). Rates are rounded half up to 2 decimals exactly,
   in integer arithmetic; interval bounds half up to 2 decimals; E (rule 7)
   half up to 1 decimal. Verdicts, list membership and ranges use the
   unrounded figures, so they cannot always be recomputed from the rounded
   ones. The interval reflects how much an institution's counts vary from
   year to year; differences between institutions in how they record and
   report incidents are outside it. `rateRules.testVectors` holds worked
   examples (count intervals, rates, a small list with its critical value)
   that check 12 recomputes.
7. **National rate** (`natl`, `natlN`, `natlF` in each window file;
   `rateStats.windows[w][code].natl`). Per window and code: the sum of N
   over the sum of F of the rated institutions, except those with `why`
   `online`, whose denominators are uncertain; institutions with
   `medical_campus` or `shared` are in it. An institution's expected count
   (`E`) is the national rate times its F.
8. **Comparison with the national rate** (`verdict`). `above` when the
   whole 95% interval is above the national rate, `below` when it is wholly
   below it, otherwise `nd` (not distinguishable); `undetermined` only for
   `online` (rule 5). If the intervals had exactly 95% coverage, an
   institution whose underlying rate equals the national rate would be
   shown above about 1 time in 40 and below about 1 time in 40 (see
   Limitations of the rates, item 4). Each window file's `summary.verdicts`
   counts the verdicts (`verdictsNoReason`: those of institutions without a
   reason).
9. **Comparison with the peer type** (`SIZE_SETTING_FIELDS`, `PEER_TYPES`;
   `rateRules.peerTypes`, `sizeSettingFields`; `peerType`, `peerVerdict`,
   and `peer` in each window file). On-campus rates are generally much
   higher where many students live on campus (compare the types' rates in a
   window file's `peer`), so each rated institution is also compared, by the same
   test, with the rate of its type. The type comes from the Carnegie Size &
   Setting classification: the value of the first of C21SZSET, C18SZSET and
   C15SZSET that an IPEDS HD file classifies the institution in, from the
   newest such file, so an institution has one type in every window. The
   types are two-year (1-5); four-year, primarily nonresidential (6, 9, 12,
   15); four-year, primarily residential (7, 10, 13, 16); four-year, highly
   residential (8, 11, 14, 17); and other (exclusively graduate, or not
   classified). A type's rate is computed like the national rate within the
   type (`peer[type]`: `rate`, `n`, `fteYears`, `members`). An `online`
   institution's peer comparison follows rule 5 (`peerVerdictLargerFte`,
   `peerVerdictSmallerFte`). `peerVerdict` is null when the type has no
   rate.
10. **Lists** (`LIST_CODES`, `LIST_MIN_EXPECTED` = 20, `LIST_ALPHA` = 0.05,
    `rank_ranges`; `rateRules.lists`; `listed`, `position`, `rankLo`,
    `rankHi`, and `list` in the window file). Only violent, criminal_xmvt
    and burglary have ordered lists. A window's list holds the rated
    institutions without a reason (rule 5) whose expected count E is at
    least 20, compared exactly. E depends on the institution's size, not on
    its count, so the list does not pick institutions by their outcome. 20
    is the floor CDC WONDER uses for reliable rates: it marks rates based on
    fewer than 20 deaths as unreliable (relative standard error 23% or
    more; https://wonder.cdc.gov/wonder/help/ucd.html). `list.minFteYears`
    is the smallest F that gives E = 20; divided by 3, it is the number of
    on-campus students a year an institution needs to be on the list. `list.n` (`rateStats.windows[w][code].listed`) is the
    number of members.
    - Order (`entries`): rate, highest first, compared exactly (N_i × F_j
      against N_j × F_i), then institution name, then base UNITID. The point
      position (`position`) is 1 + the number of members with a strictly
      higher rate, so equal rates share a position.
    - Rank range (`rankLo`-`rankHi`): for members i and j, with the common
      rate r = (N_i + N_j) / (F_i + F_j) and the variance of rule 6 for a
      window total with mean mu, V(mu) = 3 × (m + c × g(m) × m^1.5) with
      m = mu / 3,

      ```
      z_ij = (N_i/F_i - N_j/F_j) / sqrt( V(r F_i) / F_i^2 + V(r F_j) / F_j^2 )
      zc   = Phi^-1( 1 - 0.05 / (2 (n - 1)) )        (n = list.n; list.zc)
      ```

      rankLo is 1 + the number of members j with z_ji > zc (significantly
      above i), and rankHi is n minus the number with z_ij > zc
      (significantly below i), widened to include i's point position.
      Testing i against the other n - 1 members at the Bonferroni level
      makes the range a 95% confidence set for i's rank (Mogstad, Romano,
      Shaikh and Wilhelm 2024). The set is marginal: it holds for each
      institution on its own, not for all of a list's ranges at once.
      Overlapping ranges do not show that two institutions' rates are equal,
      and positions closer together than the ranges are wide cannot be
      ordered with confidence. No simulation is used.

    Ranks estimated from counts are uncertain, which is why a position is
    given with its range (Goldstein and Spiegelhalter 1996 set out the
    limits of such league tables). A rated institution that is not on a list
    keeps its rate and verdict (`listed` false).
11. **State lists** (`STATE_LIST_MIN_MEMBERS` = 2, `STATE_LIST_DISPLAY_MIN`
    = 5; `rateRules.lists.stateMinMembers`, `stateDisplayMin`;
    `statePosition`, `stateRankLo`, `stateRankHi`, `stateN`, and
    `stateLists` in the window file). A state list is the national list's
    members in one state (the state of the window's last year), ordered as
    in rule 10, with positions and ranges recomputed among them (n = the
    state's members). The data hold every state list with at least
    `lists.stateMinMembers` members, and `stateLists` gives every state's
    number of members (`rateStats.windows[w][code].stateLists` and
    `stateListsDisplayMin` count the states with at least `stateMinMembers`
    and at least `stateDisplayMin` members). The site shows a state list
    only when it has at least `lists.stateDisplayMin` (5) members; for a
    state with fewer, it names the state's institutions on the national list
    with their national positions.
12. **Unusual years** (`FLAG_*`, `unusual_years`; `rateRules.flags`;
    `rates/flags.json`, and `flags` in rate entries, institution files and
    school files). DOE counts incidents in the year they are reported (see
    Year of report), so one investigation or series of reports can add many
    incidents to one year. A cell is one institution's count of one offense
    of `rateRules.flags.offenses` (aggravated assault, burglary, dating
    violence, domestic violence, fondling, motor vehicle theft, rape,
    robbery, stalking) at one geography (on campus, non-campus, public
    property). A cell's year is flagged when its count is at least 10, the
    institution has at least 3 other years in DOE's data (a year without an
    incident counts as 0), and P(Y >= count) < 0.001 for a negative binomial
    Y with mean mu, the larger of `rateRules.flags.minMean` and the median
    of the other years, and variance mu + c × mu^1.5 (c =
    `rateRules.flags.c`). Every institution is tested, whatever its size,
    in every year, 2020 included. A flag gives the year, offense,
    geography, count and `usual` (that median). Flags never change a count
    or a rate. A rate entry carries the on-campus flags of its code's
    offenses in its window's years; for an entry with flags the verdict is
    computed again with N less the flagged excess (the sum of count - usual,
    not below 0), and published as `verdictWithoutFlagged` only when it
    differs from `verdict`. Audit check 12 also checks that removing a
    listed institution's flagged excess would leave its point position
    inside its rank range (`details.A4`). Each window file's `summary`
    counts the entries with flags (`withFlags`) and those whose verdict
    differs without them (`verdictWithoutFlaggedDiffers`); `rateStats.flags`
    counts the flags by year, geography and offense.
13. **Single-year rates** (`single_year`; `rates/institutions/{base}.json`
    `years`). For the trend on each school page, each institution-year has
    the same rate for that year alone: N and F of the year, with T = 1 in
    rule 6 (phi(N) = 1 + c × g(N) × sqrt(N)) and its 1-year interval
    (`years[y].rates[code]` = [N, rate, lo, hi]; also `fte`, `fteUncertain`
    and, per code, `medical`, `sharedIn`, `sharedOut`). Single years vary
    more than 3-year averages, and their intervals are wider. A year has a
    single-year rate when its link campus is in the 50 states, DC, PR or VI,
    its denominator is at least 1,000, no population rule applies and it is
    not 2020; otherwise `years[y].notRated` gives the first reason that
    applies: `scope`, `size`, `excluded` or `skippedYear` (2020). No
    verdict, list or position is computed for a single year.
    `rateStats.singleYear[y]` counts the institutions with a single-year
    rate.
14. **Codes without rates** (`rateRules.countsOnly`). These codes have
    counts and rankings by count but no rate:
    - weapons, drug and liquor law arrests and disciplinary referrals: they
      count people arrested or referred and measure enforcement activity,
      not incidents;
    - "all": it adds criminal offenses, VAWA offenses, arrests and
      referrals, which are different kinds of counts (see Totals shown on
      the site);
    - motor vehicle theft: on-campus vehicle thefts in national totals more
      than tripled from 2021 to 2024, and the 100 institutions with the
      largest increases account for most of the rise
      (`downloads/counts-2021.csv`, `counts-2024.csv`);
    - "criminal" (all criminal offenses) and "property" (burglary, motor
      vehicle theft, arson): both include motor vehicle theft, so
      `criminal_xmvt` and `burglary` carry the rates instead;
    - murder, negligent manslaughter, incest, statutory rape and arson: they
      are rare; each averaged fewer than 1,000 incidents a year in national
      totals in 2015-2024 (the national rankings files' `totals`).

    "violent" is the FBI's violent crime (murder and nonnegligent
    manslaughter, rape, robbery, aggravated assault); "property" is the
    FBI's property crime without larceny-theft, which Clery does not
    collect (burglary, motor vehicle theft, arson). Source: FBI, Crime in
    the United States 2019, Violent Crime and Property Crime,
    https://ucr.fbi.gov/crime-in-the-u.s/2019/crime-in-the-u.s.-2019/topic-pages/violent-crime
    and .../property-crime. Rankings by count open on "violent": motor
    vehicle theft was 37% of all criminal offenses in 2024 (15% in 2015).
    "criminal" and "all" are still offered.
15. **Count flag** (`COUNT_FLAG_MIN_COUNT` = 20, `COUNT_FLAG_FACTOR` = 3,
    `COUNT_FLAG_PERCENTILE` = 99; `rateRules.countFlag`). In rankings by
    count, an entry is flagged `highForSize` when its count is at least 20
    and the count per 10,000 of its institution's FTE (NCES's FTE of the
    whole institution) is more than 3 times the 99th percentile of that
    year's institution rates of the code. Those rates are all-geography
    counts per 10,000 of the denominator (rule 3) of the institutions in the
    national scope with a denominator of at least 1,000, no population rule
    and a certain on-campus FTE, 0 included; the percentile is by linear
    interpolation (NumPy's default), and there is no flag where it is 0.
    The reference is `rateRules.countFlag.reference[year][code]` (per
    10,000), and `rateStats.countFlags[year][code]` counts the flagged
    entries of each year's national rankings file. The count is shown as
    reported.
16. **Medical-center campuses** (`reference/medical_campuses.csv`,
    `reference/medical_campus_reviews.csv`, `MEDICAL_SCREEN_*`;
    `rateRules.medicalShare`, `medicalScreen`). A university's Clery
    geography can include a medical center or hospital, whose patients,
    visitors and staff are not students. The `hospital` rule (rule 4)
    depends on what the institution reports to IPEDS: it catches an
    institution that reports a hospital of its own (HOSPITAL = 1). A
    university next to a medical center owned by a separate organization,
    such as a health system, can report no hospital and is then not caught
    by it; its incidents at that medical center count toward a reason (rule
    5) only when its medical campus is on the reviewed list.
    `medical_campuses.csv` lists such campuses by DOE campus ID and years,
    each with its reason and source (DOE's campus name and address and,
    where they do not settle it, the institution's annual security report
    or another source). Each was reviewed by hand;
    `medical_campus_reviews.csv` records the campuses reviewed and not
    listed, with the decision and its source. The listed campuses'
    incidents stay in the institution's counts and rates; `medical` (rule
    5) counts their on-campus incidents outside residence halls, and
    `campus-years.csv` marks the campuses (`medical_center_campus`). Audit
    check 14 re-runs a screen: every campus other than a main campus whose
    DOE name and address match `rateRules.medicalScreen.pattern`, in an
    institution-year with a single-year rate, and that has at least
    `medicalScreen.minCount` on-campus criminal offenses except motor
    vehicle theft outside residence halls and at least `medicalScreen.share`
    of the institution's on-campus count of them, must be in one of the two
    files. Each campus-year in neither is named as a warning; nothing is
    added to the list automatically.
17. **Campuses abroad** (`abroad_campuses`, `reference/campuses_abroad.csv`).
    A campus DOE lists without a state is abroad, and so are the campuses of
    `etl/reference/campuses_abroad.csv`: sites in other countries that DOE
    lists with a U.S. state, each with its country, reason and source.
    NCES's fall enrollment excludes "students enrolled in any branch campus
    located in a foreign country" (IPEDS 2024-25 Fall Enrollment
    instructions, Who to Exclude), so a campus abroad's incidents are not in
    its institution's counts or rates; they stay in the campus's own school
    file, and the institution's school-file entry gives them under `abroad`
    (`campuses`, `counts`). Territories (PR, VI, GU, ...) are not abroad.
    `rateStats.institutionYears.byYear[y].abroad` counts the institutions
    in the national scope with a denominator of at least 1,000 that have a
    counting campus abroad that year; audit check 10 recomputes the counts
    with those campuses apart (`details.by_year`).

### Published rate files
`05_generate_json.py` writes, under `frontend/public/data/`:

- `rates/{y0}-{y1}-{code}.json`, one per window and rate code: `window`,
  `years`, `c` (rule 6), `natl`, `natlN`, `natlF` (rule 7), `peer` (rule
  9), `summary` (the rated institutions by reason and by verdict, national
  and peer, and the counts of rule 12), `composition` (violent: the
  national on-campus counts of its four offenses; criminal_xmvt: the
  national on-campus motor vehicle thefts it leaves out; both over the
  institutions in the national rate), for the list codes `list` (`n`,
  `minExpected`, `minFteYears`, `zc`) and `stateLists` (members per state),
  and `entries`: every rated institution, by rate (highest first, exact),
  then name, then base UNITID. An entry has `id` (base UNITID), `unitid`
  (link campus), `name`, `state` and `peerType`, `n`, `nNoncampus`,
  `nPublic`, `fteYears`, `rate`, `lo`, `hi`, `E`, `verdict` and
  `peerVerdict`; where they apply `why`, the fields of rule 5 (`medical`,
  `sharedIn` and `sharedOut` only when above 0), `flags` and
  `verdictWithoutFlagged`; and for the list codes `listed` and, when
  listed, `position`, `rankLo`, `rankHi`, the state fields of rule 11 and,
  for violent and criminal_xmvt, the entry's own `composition`.
- `rates/institutions/{base}.json`, one per institution with a rated
  window, a single-year rate or a flag: `id`, `unitid`, `name`, `state`,
  `peerType`; `years` (rule 13); `windows`, for each window in which DOE has
  the institution in at least one year: its status (rule 4) and, when
  rated, `fteByYear`, `why` and `fteSmallerByYear` for `online`, and
  `codes` (each code's window-file entry with `nByYear`, `natl`, `peerRate`
  and, for violent and criminal_xmvt, `composition`); and `flags` (all its
  unusual-year flags, every geography).
- `rates/flags.json`: every unusual-year flag (`id`, `name`, `state`,
  `year`, `offense`, `geo`, `count`, `usual`).
- `rankings/{preset}-{year}-all.json`: rankings by count only; an entry
  flagged by rule 15 has `highForSize`. Rates are not in these files.
- `schools/{unitid}.json`, `institution`: `ratesFile` (the institution's
  rates file, when it has one) and, per year, `rated` (the year has a
  single-year rate), `notRated` (rule 13's reason), `rateExcludedReason`,
  `rateFte` (the year's denominator), `fteUncertain` (`share`,
  `partTimeFirst`, `reason`), `pooledWith`, `abroad`, `flags` (that year's
  unusual-year flags) and `counts`.
- `metadata.json`: `rateRules` (the constants of the rules above, with
  `testVectors`, `calibration` and `medicalScreen`) and `rateStats`
  (`definitions` of each set it counts, `windows[w][code]`, `flags`,
  `singleYear`, `institutionFiles`, `countFlags`, `institutionYears`).

### Institution-years
`rateStats.institutionYears` counts institution-years ("institution-years":
one institution in one year, 2015-2024): `rules[rule]` (rule 4:
`institutionYears`, those the rule is the first for, and `withFte`, those of
them in the national scope with a denominator of at least 1,000), `pooled`
(institution-years whose denominator adds another institution's FTE, per
case of rule 3), `onlineOwnYear` (rule 3), and per year `byYear[y]`:
`withFte` (institutions in the national scope with a denominator of at least
1,000, population rules included), and of those `excluded` (a population
rule), `rated` (a single-year rate), `fteUncertain` (no rule, an uncertain
on-campus FTE), `fteUncertainPooledOnly` (of those, uncertain only through a
pooled institution) and `abroad` (a counting campus abroad); and
`outsideScopeWithFte` (outside the national scope with such a denominator,
no rate). `rateStats.definitions` defines the sets in words.

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
figures the institutions reported; this site does not remove them. The
unusual-year flags (rate rule 12) mark Ohio State's on-campus fondling
counts of those three years, Michigan's 2020 on-campus rape and fondling
counts and Michigan State's 2018 non-campus rapes; a flag changes no count
or rate.

### Totals shown on the site
- **All criminal offenses** (what school pages and comparisons open on; rankings open on violent crimes, rate rule 14): the 11 criminal offenses above, added up. It has no rate; rates use criminal offenses except motor vehicle theft (rate rules 2 and 14).
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
  rankings for 2020 or 2021 show the note too. No rate covers 2020 (rate
  rule 1).
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

Each ranking lists schools by their count, largest first. Schools with the same count share a rank (standard competition ranking: 1, 2, 2, 4, so the rank after a tie skips the places the tie takes) and are listed by name, then by UNITID. The rate lists (rate rule 10) order institutions by rate the same way, ties by institution name, then base UNITID, and give equal rates the same point position; each position comes with its rank range. Every campus that reported the year is in its rankings: those with none of a category are the last tie, with 0 (see Zero Versus Not Reported).

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
On-campus FTE is estimated from NCES's FTE of the whole institution, its
fall headcounts and its share of students enrolled exclusively online (rate
rule 3); when the two estimates differ by more than 25% in a year of a
window, the institution's verdict is given only when both estimates lead to
the same one, and it is on no list (rate rule 5). On-campus FTE does not
count residents who are not students, employees, visitors or patients.
Institutions with a hospital and special-focus medical and research
institutions have no rate (rate rule 4), and an institution with a quarter
or more of a window's on-campus incidents at a listed medical-center campus
is on no list for that code (rate rules 5 and 16), but other Clery geography
can include places used mostly by others (a clinic, or a medical center not
on the list), where a rate per student says little about risk to a student.
Rates leave out campuses abroad, whose students NCES's fall enrollment
leaves out (rate rule 17).

### Small numbers, zeros and unweighted totals
Every rate has a 95% interval (rate rule 6), and an institution is on a list
only when its expected count at the national rate is at least 20 (rate rule
10). Because counts vary from year to year beyond chance, intervals stay
wide even for large counts (`rateRules.testVectors.counts` gives examples).
A rate of 0 means that no on-campus incident of the code was reported in
the window's 3 years; it can reflect classification or chance, and incidents
at the institution's other locations are published beside it (`nNoncampus`,
`nPublic`). "All criminal offenses" adds unlike crimes with equal weight;
motor vehicle theft was about 15% of the national criminal total in 2015 and
about 37% in 2024, which is why rankings by count open on violent crimes and
why the rates use criminal offenses except motor vehicle theft.

### Limitations of the rates
Comparisons of institutions by a rate have general limits, set out by
Goldstein and Spiegelhalter (1996). These are the ones that apply to the
rates here (rate rules above):

1. A rate counts reported incidents, not all incidents. How completely
   institutions record and report incidents differs between institutions
   and over time, and nothing in these methods can correct for that: a high
   rate can mean more complete reporting as well as more crime. Yung (2015)
   found that the sexual assaults universities reported rose by about 44%
   while the Department of Education was auditing their Clery compliance,
   and fell back after the audits; the other crimes studied showed no such
   change.
2. Only on-campus incidents are in a rate. Non-campus and public-property
   incidents are published beside it as counts (`nNoncampus`, `nPublic`);
   at some institutions most of the reported incidents are on public
   property in or next to campus. The order of each list depends on counting
   only on-campus incidents.
3. The denominator is students, but on-campus incidents also involve
   staff, visitors and patients. Rates are generally much higher where many
   students live on campus, so an institution's residential character
   drives its rate; the peer comparison (rate rule 9) compares it with
   institutions of its own type, and each window file's `peer` gives the
   types' rates.
4. The intervals come from a model whose calibration is checked in
   aggregate, over groups of institutions, not institution by institution
   (audit check 13). `audit.json`, check "Interval Calibration", gives the
   measured and expected coverage for each code, period and band of yearly
   means (`details.rows`): where the measured share is below the expected
   one, the intervals of that band are too narrow, and where it is above,
   too wide. A band with fewer institutions than
   `rateRules.calibration.bandMinUnits` is reported but not tested, and the
   check's errors name every tested row outside its tolerance.
5. A rank range is a 95% statement about one institution on its own. It is
   not a statement about all of a list's ranges at once.
6. The lists hold only large institutions: those with at least
   `list.minFteYears` / 3 on-campus students a year in the window file (an
   expected count of 20 at the national rate). Smaller rated institutions
   have a rate and a verdict but no position.
7. Positions in windows five years apart differ substantially (compare a
   list in `rates/2017-2019-{code}.json` with the same institutions in
   `rates/2022-2024-{code}.json`). Adjacent windows share two of their three
   years, so their close agreement says little about stability.
8. The order of a list depends on two judgment calls: counting only
   on-campus incidents (rate rule 2) and the size threshold, an expected
   count of 20 (rate rule 10). Other choices give other members and another
   order.
9. The medical-center campus list (rate rule 16) was reviewed by hand and
   may be incomplete: audit check 14 names, as a warning, every campus its
   screen finds that has not been reviewed.
10. DOE counts incidents in the year they are reported, so one
    investigation can add many incidents to one year; the unusual-year
    flags (rate rule 12) mark such years.
11. 2020 has no rate (rate rule 1).
12. Motor vehicle theft, arrests and disciplinary referrals are counts only
    (rate rule 14).
13. Incidents at campuses abroad are not in the rates (rate rule 17).

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

`06_validate.py` checks row counts per year, that no count is negative, that
every Ivy League campus is present, offense coverage and that the JSON files
parse.

`07_comprehensive_audit.py` runs 14 checks; its report is published as
`audit.json`. Each check's `details.what_it_checks` says exactly what it
verifies, and `summary` counts the checks that passed, failed and gave a
warning. Checks 1-8, 10 and 11 compare the pipeline's own files with each
other; check 9 re-reads NCES's enrollment files, check 10 also the IPEDS HD
files, NCES's headcounts and the reference lists of medical-center campuses
and campuses abroad, and checks 12 to 14 recompute the rates from check 10's
figures with their own implementation of the rules (nothing of
`etl/rates.py`, 04 or 05 is used). None re-reads the DOE downloads.

1. **School Completeness**: every campus that reported a year has a school
   page and is in the site search.
2. **Incident Total Accuracy**: each school page has exactly the years the
   campus reported, 0 included, lists the others as not reported, and each
   year's total equals the aggregates'.
3. **FTE Coverage**: of the schools with crime data in each year, the share
   with an FTE.
4. **Rate Calculation Accuracy**: from each rate file's own numbers, every
   3-year and single-year rate is N / F × 10,000 rounded half up, lies
   inside its interval, and the national rate, peer rates and E agree with
   the figures they are made of.
5. **Ranking Order Validation**: every ranking by count is in count order
   with competition ranks (1, 2, 2, 4); every rate file is in rate order,
   and each list position is 1 + the members with a strictly higher rate
   and lies inside its rank range, state lists included.
6. **Ranking Totals and Tables**: each rankings file's totals and campus
   table agree with its rankings and it holds no rates; the window files,
   institution files, `rates/flags.json` and the school files' `ratesFile`
   agree with each other.
7. **Aggregate Consistency**: the aggregates hold exactly the fact table's
   counts.
8. **Shared Statistics Counted Once**: the shared blocks are found again
   from the fact table and the older releases' figures, and every ranking
   entry counts the school's figures without its shadow blocks.
9. **Enrollment Matches NCES**: every FTE, online share and headcount is
   NCES's own published figure.
10. **Institution Rates**: without 04's or 05's code, each institution-year's
    counting campuses in the United States (campuses abroad apart, rate rule
    17), counts per geography, link campus, FTE, online share, both
    on-campus FTE estimates and whether they make it uncertain, population
    rules, pooled institutions and both denominators, peer type, and
    on-campus figures at listed medical-center campuses and at shared
    campuses; these must match 04's tables, the school files,
    `campus-years.csv` and `rateStats.institutionYears`, and every rankings
    file must list exactly its preset's campuses that count in its year
    (those with 0 included).
11. **Campus Identity**: `etl/reference/campus_id_changes.csv` lists exactly
    the campus ID changes found again in DOE's names, with the same
    evidence, and the two school files of each link point to each other
    without moving figures.
12. **Rate Rules**: every window status, N, F, reason, national and peer
    rate, interval, E, verdict (national, peer, both FTE estimates),
    unusual-year flag, verdict without the flagged excess, list, position,
    rank range and state list; the window files' headers and summaries, the
    institution files (single-year rates and statuses), `rates/flags.json`,
    the count flag in every rankings file, the school files' `ratesFile`,
    `rated`, `notRated` and `flags`, and `metadata.json`'s `rateRules` and
    `rateStats` against `config.py` and the design's values. It also
    recomputes the test vectors (`rateRules.testVectors`), checks that
    removing a listed institution's flagged excess would leave its position
    inside its rank range (`details.A4`) and that no interval bound falls as
    the count rises (`details.A5`). `details.subchecks` counts the problems
    per part.
13. **Interval Calibration** (added with the 3-year rates): for each code
    and period of `rateRules.calibration`, every institution with a
    single-year rate in all the period's years and an incident in at least
    one has each year's on-campus count predicted from its other years
    under the published dispersion model (rate rule 6). The share of counts
    inside the central 95% predictive interval is compared with the share
    the model expects (the mean of `simulations` simulated panels, NumPy
    PCG64 seeded with `seed`). The check fails when they differ by more than
    `tolerance` over the institutions with a mean of at least 2 a year, or
    by more than `bandTolerance` in a band of yearly means (`bands`) with at
    least `bandMinUnits` institutions. `details.rows` gives the observed and
    expected coverage per code, period and band, tested or not.
14. **Medical-Campus Screen** (added with the 3-year rates): the screen of
    rate rule 16. Campus-years it finds in neither reference file are a
    warning, never a failure (`details.unreviewed`).

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
- `05_generate_json.py`: site JSON and the CSV downloads; it runs `rates.py`, which makes the rate windows, intervals, comparisons, lists, unusual-year flags and single-year rates
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
13. National Center for Education Statistics. IPEDS HD data dictionary, 2024 (HOSPITAL, C21BASIC). https://nces.ed.gov/ipeds/datacenter/data/HD2024_Dict.zip
14. Carnegie Classification of Institutions of Higher Education. 2021 Basic Classification. https://carnegieclassifications.acenet.edu/2021-basic-classification
15. Gallaudet University. Laurent Clerc National Deaf Education Center. https://clerccenter.gallaudet.edu/
16. Centers for Disease Control and Prevention. CDC WONDER, Underlying Cause of Death help (unreliable rates). https://wonder.cdc.gov/wonder/help/ucd.html
17. Garwood, F. (1936). Fiducial limits for the Poisson distribution. Biometrika 28(3/4), 437-442. https://doi.org/10.1093/biomet/28.3-4.437
18. Federal Bureau of Investigation. Crime in the United States, 2019: Violent Crime and Property Crime. https://ucr.fbi.gov/crime-in-the-u.s/2019/crime-in-the-u.s.-2019/topic-pages/violent-crime ; https://ucr.fbi.gov/crime-in-the-u.s/2019/crime-in-the-u.s.-2019/topic-pages/property-crime
19. Fay, M. P. and Feuer, E. J. (1997). Confidence intervals for directly standardized rates: a method based on the gamma distribution. Statistics in Medicine 16(7), 791-801. https://doi.org/10.1002/(SICI)1097-0258(19970415)16:7%3C791::AID-SIM500%3E3.0.CO;2-%23
20. National Center for Education Statistics. IPEDS 2024-25 Survey Materials: Fall Enrollment for 4-year degree-granting institutions (full instructions, "Who to Exclude"). https://nces.ed.gov/ipeds/use-the-data/download-survey-material/2024/fall%20enrollment/package_6_74.pdf
21. Greene, W. (2008). Functional forms for the negative binomial model for count data. Economics Letters 99(3), 585-590. https://doi.org/10.1016/j.econlet.2007.10.015
22. Mogstad, M., Romano, J. P., Shaikh, A. M. and Wilhelm, D. (2024). Inference for ranks with applications to mobility across neighbourhoods and academic achievement across countries. Review of Economic Studies 91(1), 476-518. https://doi.org/10.1093/restud/rdad006
23. Yung, C. R. (2015). Concealing campus sexual assault: An empirical examination. Psychology, Public Policy, and Law 21(1), 1-9. https://doi.org/10.1037/law0000037
24. Goldstein, H. and Spiegelhalter, D. J. (1996). League tables and their limitations: statistical issues in comparisons of institutional performance. Journal of the Royal Statistical Society, Series A 159(3), 385-443. https://doi.org/10.2307/2983325
