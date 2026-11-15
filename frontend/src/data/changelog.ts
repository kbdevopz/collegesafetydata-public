/**
 * Changes and corrections, newest first. This is the only file to edit:
 * add a new entry at the top of CHANGES. The /changes page lists them.
 *
 * kind: 'correction' changes figures the site showed (say by how much);
 * 'method' changes how figures are counted, ranked or rated;
 * 'site' changes text or pages, not figures.
 */

export type ChangeKind = 'correction' | 'method' | 'site'

export interface ChangeEntry {
  /** ISO date the change was made (YYYY-MM-DD) */
  date: string
  kind: ChangeKind
  title: string
  /** Plain sentences for readers: what changed and what it affects */
  body: string[]
  /** Methodology anchor that explains it, e.g. "rates" */
  methodology?: string
}

export const CHANGES: ChangeEntry[] = [
  {
    date: '2026-11-15',
    kind: 'method',
    title: 'Three-year rates of on-campus incidents, compared with the national rate',
    body: [
      'A rate now counts the incidents reported on campus over three years, per 10,000 on-campus students a year. No rate includes 2020. Incidents at non-campus locations and on public property are shown beside the rate as counts, not in it.',
      'Rankings by rate for single years are replaced by comparisons. Each rate is compared with the national rate and with the rate of institutions of its type, from its 95% interval: above, below or not distinguishable. For violent crimes, criminal offenses except motor-vehicle theft, and burglary, the institutions large enough to expect at least 20 incidents at the national rate are placed on an ordered list, each with the range of positions its rate allows. School pages still chart each year\'s rate, without comparisons.',
      'Motor-vehicle theft, "All criminal offenses", "Property crimes", "All categories", arrests and disciplinary referrals are shown as counts only, with the reason, as the rare offenses already were.',
      'Intervals use a new model of how much institutions\' counts vary. Its constant is fitted to institutions\' 2015-2019 counts for each of violent crimes, criminal offenses except motor-vehicle theft, burglary, rape and aggravated assault; the other single offenses share one constant fitted to those offenses together. The audit now tests the model against the data on every build. Rank ranges come from comparing each listed institution with every other, not from simulation.',
      'Shared campuses are now handled site by site, not by the share of an institution\'s figures. Where campuses of two or more institutions report the same incidents (identical figures, near-identical figures, or a reviewed list), the site\'s incidents are in one institution\'s rate at most. An institution with a campus at another institution\'s site is shown without comparisons and is not on a list, unless published enrollment figures show that few of its students are there (a year without a figure of its own may use one from up to three years away, and the school page says so). Where the main campuses of several institutions share one site, the others are counted with the one with the most on-campus students when they are much smaller or have no campus elsewhere; otherwise none of them has a rate in those years. No count changed.',
      'Years that are unusually high for an institution are flagged at each location and never removed; when a flagged year changes a comparison, the school page says so. Counts flagged as very high for an institution\'s size are now measured against the 99th percentile of institution rates, not the highest ranked rate.',
      'More medical-center campuses are counted apart, from a list reviewed campus by campus, and AdventHealth University has no rate because its main campus includes a hospital. No count changed.',
    ],
    methodology: 'rates',
  },
  {
    date: '2026-11-14',
    kind: 'method',
    title: 'Rate rules revised: on-campus estimate, medical-center campuses, campuses abroad, wider intervals',
    body: [
      'On-campus FTE is now the larger of two estimates made from NCES\'s FTE, fall headcounts and share of students enrolled exclusively online. When the two differ by more than 25%, or NCES\'s headcounts do not add up, the rate is shown but not ranked: 221 institutions in the 2024 national rate rankings, among them Grand Canyon University (estimates of 12,503 and 23,110), which the previous change ranked.',
      'Incidents at 13 listed medical-center campuses, such as Johns Hopkins University\'s East Baltimore campus, are counted apart: when they are 25% or more of an institution\'s count of an offense, its rate is shown but not ranked. The University of Tennessee Health Science Center (2015-2017) and Albert Einstein College of Medicine (2019-2020) are left out of rate rankings in the years IPEDS gives them no Carnegie classification.',
      'Shared campuses no longer leave institutions out of rate rankings. For each offense, a rate is not ranked when the figures shared with another institution\'s campus are more than 5% of its count, and is ranked with a note below that.',
      'Rates leave out incidents at campuses abroad, because NCES\'s fall enrollment leaves out their students (95 institutions in 2024). Those incidents stay on each campus\'s own page.',
      'Intervals now allow for how much institutions\' counts vary from year to year beyond chance (a negative binomial interval), so they are wider, most of all for large counts, and rank ranges are simulated. Unusually high years are marked under a stricter test, and rankings by count flag counts that are very high for an institution\'s size.',
      'In the 2024 national rate rankings 2,076 institutions are listed, 94 of them left out by a rule; 293 are ranked for all criminal offenses and 79 for violent crimes. Of the previous top 25 by all criminal offenses, 20 are still in it: Grand Canyon University, Metropolitan State University and the CUNY Graduate Center are not ranked because of an uncertain on-campus FTE, Johns Hopkins University because of that and its medical-center campuses, and Harvard University is 26th. No count changed.',
      'The figures in this entry are those of this change. The change above replaced rankings by rate for single years with three-year rates and comparisons, so they no longer hold; Methodology has the current rules.',
    ],
    methodology: 'rate-rules',
  },
  {
    date: '2026-11-14',
    kind: 'method',
    title: 'Rates per on-campus student, with intervals; violent and property crimes',
    body: [
      'Rates now divide by on-campus FTE: the FTE without NCES\'s share of students enrolled only in distance education. The 50% online cut-off is gone, and rate rankings list institutions with at least 1,000 on-campus FTE. Grand Canyon University (79% exclusively online in fall 2024), for example, is now listed.',
      'Rate rankings leave out institutions with a hospital (IPEDS), special-focus medical schools and research institutions (Carnegie), and Gallaudet University, whose campus also holds two schools for deaf children: 1,227 institution-years, among them Ohio State, Michigan and UCLA in 2024. They also leave out 243 institution-years in which DOE reports a campus\'s figures under two institutions and their students cannot be matched exactly, such as Purdue and Texas A&M in 2024; 44 more are rated with both institutions\' FTE.',
      'Only rates built on at least 20 incidents get a rank; the others are listed as too few to rank by rate, with their rate. Every rate shows a 95% interval and every rank the range of ranks the intervals allow. Murder, negligent manslaughter, incest, statutory rape and arson are ranked by count only.',
      'New categories: "Violent crimes" and "Property crimes", the offenses of the FBI\'s violent and property crime (without larceny-theft, which Clery does not collect). Rankings open on violent crimes. A year more than 3 times an institution\'s usual count is marked as unusually high and stays ranked.',
      'In 2024 rate rankings list 1,874 institutions (2,077 before). Of the previous top 25 by all criminal offenses, 13 are still in it and 11 are now left out, most of them medical institutions or institutions with a hospital. No count changed.',
      'The figures in this entry are those of this change. The revision above changed the denominator, the shared-campus rule, the intervals and the unusually-high test, so several of them no longer hold; Methodology has the current ones.',
    ],
    methodology: 'rate-rules',
  },
  {
    date: '2026-11-14',
    kind: 'method',
    title: 'Fewer merger years left out of rate rankings',
    body: [
      'Rate rankings left out 295 institution-years (97 with at least 1,000 FTE) in which a merger or renumbering might have put a campus\'s incidents and its students under different institutions. They now leave out only the years where a campus with at least one incident has its incidents under one institution and its students under another, or where it cannot be told which institution\'s FTE holds them: 91 institution-years (29 with at least 1,000 FTE). Tufts 2015, the University of Arizona 2020 and Northeastern 2023, for example, have rates again.',
      '31 institution-years are now rated with the FTE of an institution whose campus figures DOE reported under them, such as Tufts 2015 with the School of the Museum of Fine Arts. No count changed.',
    ],
    methodology: 'rates',
  },
  {
    date: '2026-11-14',
    kind: 'correction',
    title: 'Campus names, renumbered campuses and mergers',
    body: [
      'Branch campuses are now titled with their own DOE campus name, with the institution under it (6,705 school pages). Search also finds campuses by city and by names DOE and IPEDS used for them before.',
      'When DOE moved a campus to a new ID (a renumbering or a merger), its years were split across two pages. 313 such pairs, each reviewed, now link to each other; each page keeps the years DOE reported under its own ID.',
      'Where both IDs reported the same full year from different DOE releases, those figures were counted twice in state and national totals. They now count once, under the newer ID: 86 campus-years, 661 incidents across 2015-2023. No campus\'s own figures changed.',
      'In a year a campus was reported under two institutions, or a merged institution\'s enrollment covered campuses counted elsewhere, incidents and enrollment may not cover the same campuses. Those institution-years have no rate and are left out of rate rankings; 78 of them were in the rate rankings before (for example Vermont State 2022, the Connecticut State colleges 2022, and Penn State 2019 and 2021).',
    ],
    methodology: 'rates',
  },
  {
    date: '2026-11-14',
    kind: 'site',
    title: 'Definitions, limitations, citation and downloads',
    body: [
      'The Methodology page defines every category and location from the regulation (34 CFR 668.46 and its Appendix A), with sources, and lists the limitations of the data.',
      'Charts shade 2020 and 2021, when most instruction was remote, and link to the note. School pages say when a residence-hall figure comes from another DOE release because of a known error in DOE\'s file.',
      'The pages now say that counts are by the year a crime was reported, not the year it happened. The figure that 80% of crimes go unreported was replaced by what the Bureau of Justice Statistics measured: 80% of rape and sexual assault victimizations of female college students aged 18-24 in 1995-2013 were not reported to police.',
      'School pages call the top category the most common criminal offense, show year-over-year change in neutral colors, and label enrollment as the whole institution\'s FTE.',
      'New: an APA and BibTeX citation with the build identifier, CSV downloads of every figure, and this page. No figure changed.',
    ],
    methodology: 'limitations',
  },
  {
    date: '2026-11-12',
    kind: 'method',
    title: 'Pandemic years judged by the 2019 online share',
    body: [
      'Rate rankings leave out institutions where at least half of students study exclusively online. For 2020 and 2021 the test now uses each institution\'s fall 2019 share, because temporary remote teaching did not make schools online schools. The 2020 rate ranking now lists 2,168 institutions (was 1,588) and 2021 lists 2,167 (was 1,936).',
    ],
    methodology: 'rates',
  },
  {
    date: '2026-11-12',
    kind: 'correction',
    title: 'Years reported with no incidents shown as 0',
    body: [
      'A year a campus reported with no incidents used to look the same as a year it did not report, and campuses that never had an incident had no page. Such years now show 0, every campus that reported has a page, and rankings list campuses with 0 after the others, sharing one rank.',
    ],
  },
  {
    date: '2026-11-12',
    kind: 'method',
    title: 'Rates per institution; mostly online institutions left out',
    body: [
      'NCES publishes enrollment per institution, not per campus, so a branch campus\'s rate divided its own incidents by the whole institution\'s enrollment. Rates are now per institution: the incidents of all its campuses over its FTE. Rankings by count still list each campus.',
      'Rate rankings list institutions with at least 1,000 FTE students and under 50% of students exclusively online. School pages still show other institutions\' rates, with a note.',
    ],
    methodology: 'rates',
  },
  {
    date: '2026-11-12',
    kind: 'method',
    title: 'Ties share a rank; criminal offenses by default',
    body: [
      'Tied schools now share a rank and the next rank skips (1, 2, 2, 4). Rankings, school pages and Compare open on all criminal offenses; "All categories" (which adds arrests and disciplinary referrals, counts of people) stays selectable.',
    ],
    methodology: 'totals',
  },
  {
    date: '2026-11-10',
    kind: 'correction',
    title: 'NCES\'s own enrollment for 2015-2020',
    body: [
      'For 2015-2020 the site estimated FTE with one formula for every school. That matched NCES\'s published FTE exactly for only 58% of institution-years and was off by more than 5% for about 830 a year. Every year now uses NCES\'s own FTE, which changes rates for those years.',
    ],
    methodology: 'fte',
  },
  {
    date: '2026-11-10',
    kind: 'correction',
    title: 'Campus-years missing from the newest DOE release restored',
    body: [
      'Each year used to come only from the newest DOE release covering it, so a campus missing from that release lost the year. Each campus-year now comes from the newest release that has figures for it. This restores 1,551 campus-years at 1,126 campuses (28,695 incidents, 2015-2023).',
      'Two known errors in DOE\'s 2021-2023 release (residence-hall disciplinary referrals and arrests) are worked around; school pages name the campuses affected.',
    ],
    methodology: 'known-defects',
  },
  {
    date: '2026-11-10',
    kind: 'correction',
    title: 'Figures two campuses report identically counted once',
    body: [
      'Some campuses report exactly the same figures for a year and location as another campus in the same state. State and national totals and rankings now count them once, under one campus (242 location-year blocks), and also when a whole year is copied or the copy is in an older DOE release (141 more blocks). School pages still show the figures as reported and name the other campus.',
    ],
    methodology: 'totals',
  },
  {
    date: '2026-11-10',
    kind: 'correction',
    title: 'Alabama 2015 and 2016 restored',
    body: [
      'A file reader misread the first rows of DOE\'s 2015 and 2016 files, so 13 Alabama campuses, including the University of Alabama, Auburn and UAB, had no 2015 or 2016 data. Alabama\'s 2015 total was shown as 1,540; it is 4,646.',
    ],
  },
  {
    date: '2026-11-10',
    kind: 'site',
    title: 'Analytics disclosed; sorting covers the whole list',
    body: [
      'The Privacy page said the site had no analytics; collegesafetydata.org uses Cloudflare Web Analytics (cookieless, aggregate), and the page now says so. Sorting a rankings column used to sort only the rows loaded so far; it now sorts the full list.',
    ],
  },
]
