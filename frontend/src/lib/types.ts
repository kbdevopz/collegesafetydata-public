/**
 * TypeScript interfaces for the Clery Dashboard
 */

// =============================================================================
// Metadata Types
// =============================================================================

export interface Metadata {
  years: number[]
  offenses: Offense[]
  geographies: string[]
  presets: Preset[]
  lastUpdated: string
  dataSource: string
  dataSourceUrl: string
  coverage: string
  note: string
  // NCES fall enrollment (FTE) status per year in `years`, e.g.
  // {"2023": "final", "2024": "provisional"}. Absent in data built before
  // 05 wrote it.
  enrollmentStatus?: Record<string, EnrollmentStatus>
  // The rate rules (etl/config.py): who rate rankings list and rank, the
  // interval and the spike flag
  rateRules: RateRules
  // What the rate rules did, counted by the build (05): the figures the
  // Methodology page quotes. Absent in data built before 05 wrote it.
  rateStats?: RateStats
  // Known errors in DOE's files that the build worked around, with the
  // campuses whose figures for that year come from the defective release.
  // Absent in data built before 05 wrote it.
  knownDefects?: KnownDefect[]
}

export interface KnownDefect {
  year: number
  release: string // DOE file suffix, e.g. "212223" (2021-2023 release)
  file: string
  geo: string // "residencehall", ...
  category: string // "discipline", "arrest", ...
  columns: string[]
  problem: string
  takenFrom: string | null // release the cells come from, or null (left blank)
  unitids: number[]
}

// A ratio [a, b], read as the fraction a / b (or a threshold a : b)
export type Ratio = [number, number]

export interface RateRules {
  // Rate rankings list institutions with at least this on-campus FTE
  minFte: number
  // ... and rank by rate those with at least this many incidents (and no
  // other reason not to rank them)
  minCount: number
  // Offense codes too rare nationally for a rate ranking (counts only)
  countsOnly: string[]
  // The level of each rate's interval (0.95)
  ciLevel: number
  // On-campus FTE is uncertain when the larger of its two estimates times
  // [1] is more than the smaller times [0] ([5, 4]: more than 25% apart)
  onlineUncertainRatio: Ratio
  // A code is not ranked when incidents at listed medical-center campuses
  // are at least this share of the count ([1, 4]: 25% or more)
  medicalShare: Ratio
  // ... or when shared figures are more than this share ([1, 20]: 5%)
  sharedShare: Ratio
  // The negative binomial overdispersion k of each code (kByCode), fitted
  // per group of codes on the years `years`
  dispersion: Dispersion
  // Rank ranges: `draws` simulated rankings with a fixed seed
  rankRanges: { draws: number; seed: number }
  // An unusually high count: at least minCount, with at least minOtherYears
  // other years with figures, more than factor times their median and maxFactor
  // times their largest, and below probability p for a negative binomial
  // count with that median as its mean
  spike: { minCount: number; factor: number; maxFactor: number; p: number; minOtherYears: number }
  // Count rankings flag a count of at least minCount whose count per 10,000
  // institution FTE is more than factor times the year's highest national
  // ranked rate of the code (RateStats.countFlagLimits)
  countFlag: { minCount: number; factor: number }
  // Years whose online share is another fall's, e.g. {"2020": 2019}: the
  // pandemic's remote teaching did not take students off campus for good
  onlineShareYear?: Record<string, number>
}

export interface Dispersion {
  years: [number, number]
  // Institutions with a mean count of at least this many in those years
  minMean: number
  // k (rounded, as used), its estimate, the median variance-to-mean ratio
  // (phi) and the number of institutions (or institution-offenses) fitted
  groups: Record<string, { k: number; estimate: number; phi: number; units: number }>
  kByCode: Record<string, number>
}

// The rules that leave an institution out of rate rankings altogether
export type RateRule = 'hospital' | 'medical' | 'listed' | 'merger' | 'family'

// Why an institution's rate is shown but not ranked for a code
export type NotRankedReason = 'online' | 'medical_campus' | 'shared' | 'few'

export interface RateCodeStats {
  ranked: number
  // Entries of rateUnranked (1 to minCount - 1 incidents, no other reason)
  few: number
  // Entries of rateNotRanked with each reason or rule
  notRanked: Record<NotRankedReason | RateRule, number>
  // Ranked entries with a medical-center campus or shared-figures note
  medicalNote: number
  sharedNote: number
  spikes: number
  // The median ranked institution's rank range, in ranks
  medianRange: number
}

export interface RateYearStats {
  // Institutions with a denominator of at least minFte (the national file)
  listed: number
  // ... of them left out by a rule (first rule)
  excluded: number
  excludedBy: Record<RateRule, number>
  fteUncertain: number
  // Institutions with a campus abroad
  abroad: number
  rankedEntries: number
  spikes: number
  // Count-ranking entries flagged highForSize, per code
  countFlags: Record<string, number>
  violent?: RateCodeStats
  criminal?: RateCodeStats
  property?: RateCodeStats
}

export interface RateStats {
  // The national file of each year
  byYear: Record<string, RateYearStats>
  // All institution-years, 2015 on (byYear: those with a state code,
  // including places no rankings file covers, such as Guam)
  institutionYears: {
    // Institution-years each rule leaves out (as the first rule), and how
    // many of them have a denominator of at least minFte
    rules: Record<RateRule, { institutionYears: number; listed: number }>
    // Institution-years rated with another institution's FTE added
    pooled: { merger: number; shared: number }
    byYear: Record<string, { listed: number; excluded: number; fteUncertain: number; abroad: number }>
    // Pandemic years whose own online share was used (no fall 2019 share)
    onlineOwnYear: Record<string, { all: number; listed: number }>
  }
  countsOnly: {
    // National incidents per year, 2015 on, per code
    averagePerYear: Record<string, number>
    // Institution-years in rate rankings with at least minCount of a counts-only code
    reachingMinCount: Record<string, number>
  }
  // The 95% interval of a count, as examples: code -> count -> [lo, hi]
  intervalExamples: Record<string, Record<string, [number, number]>>
  // The highest national ranked rate per year and code
  countFlagLimits: Record<string, Record<string, number>>
}

// "final": NCES final revised file; "provisional": NCES provisional release;
// "missing": NCES has not published that fall's enrollment yet (no rates).
export type EnrollmentStatus = 'final' | 'provisional' | 'missing'

export interface Offense {
  code: string
  display: string
  family: string
  familyDisplay: string
  description: string
  displayOrder: number
}

export interface Preset {
  id: string
  name: string
  description: string
  schoolCount: number
}

// =============================================================================
// School Types
// =============================================================================

export interface School {
  unitid: number
  name: string
  short: string | null
  city: string | null
  state: string | null
  isMainCampus?: boolean
  baseUnitid?: number
  // The campus's own DOE name (BRANCH), shown as its title; absent for a
  // main campus and for a campus DOE gives only a generic label
  campus?: string
  // First and last year the campus reported
  years?: [number, number]
  // Other names to search by: former DOE names, IPEDS aliases
  aliases?: string[]
  // Other DOE IDs of the same campus (each has its own page)
  idChanges?: number[]
}

export interface SchoolIndex {
  schools: School[]
}

export interface PresetDetail {
  id: string
  name: string
  schools: School[]
}

export interface Presets {
  [key: string]: PresetDetail
}

// =============================================================================
// Rankings Types
// =============================================================================

// A campus of a rankings file (its "campuses" table): every campus of the
// file's scope that reported the year. A campus without an entry in a count
// ranking had 0 of that category.
export interface RankedCampus {
  name: string
  short: string | null
  state: string | null
  main: boolean
  // The campus's own DOE name, for a campus that is not a main campus
  campus?: string
  // Its institution's FTE (NCES publishes FTE per institution, not campus)
  fte: number | null
  // Its institution's number of campuses in the United States that year
  campuses: number
}

// One campus of a count ranking (by count, ties by name, then UNITID)
export interface CountEntry {
  rank: number
  unitid: number
  count: number
  // The count per 10,000 of its institution's FTE is more than
  // RateRules.countFlag.factor times the year's highest national ranked rate
  // of the code (and the count is at least countFlag.minCount)
  highForSize?: boolean
}

// An institution of a rankings file's rate rankings: all campuses with the
// same first six UNITID digits, shown as `name` and linked to the school
// page of campus `unitid`. Every institution of the file's scope with a
// denominator of at least RateRules.minFte, those a rule leaves out included.
export interface RateInstitution {
  name: string
  unitid: number
  state: string | null
  // The rate's denominator: the larger on-campus FTE estimate, plus the
  // on-campus FTE of `pooled`
  fte: number
  // Its campuses in the United States that count that year
  campuses: number
  // Institutions whose FTE the rate adds (their campus figures count here)
  pooled?: PooledInstitution[]
  // The first rule that leaves it out of rate rankings: no rate at all
  excluded?: RateRule
  // Its on-campus FTE is uncertain: no code is ranked (see FteUncertain)
  fteUncertain?: FteUncertain
  // Its campuses abroad that year (their incidents are not in its rates)
  abroad?: number
}

// The two estimates of an institution's on-campus FTE (rounded), when its
// on-campus FTE is uncertain: proportional, FTE x (1 - online share); and
// part-time first, null when NCES's headcounts do not allow it. The
// institution's own estimates: the flag is also set when an institution
// whose FTE is pooled into the rate has an uncertain on-campus FTE.
export interface FteUncertain {
  share: number
  partTimeFirst: number | null
}

// An institution whose FTE another's rate adds: `id` its base UNITID
export interface PooledInstitution {
  id: number
  name: string | null
  fte: number
}

// Incidents of an institution-year and code that need a note: at listed
// medical-center campuses (medical); shared figures of its host campus that
// another institution also reports (sharedIn, in the count); and figures it
// reports that count under another institution's campus (sharedOut, not in
// the count). Present only when above 0.
export interface RateNoteCounts {
  medical?: number
  sharedIn?: number
  sharedOut?: number
}

// One institution of a rate ranking: `id` is its base UNITID (a key of
// RankingsData.institutions), `count` the incidents of all its campuses in
// the United States, lo-hi the rate's 95% interval, rankLo-rankHi the
// middle 95% of its simulated ranks, spike an unusually high count for it
export interface RateEntry extends RateNoteCounts {
  rank: number
  id: number
  count: number
  rate: number
  lo: number
  hi: number
  rankLo: number
  rankHi: number
  spike?: boolean
}

// An institution with too few incidents to rank by rate (1 to minCount - 1)
// and no other reason not to rank it
export interface RateUnrankedEntry {
  id: number
  count: number
  rate: number
  lo: number
  hi: number
  medical?: number
}

// An institution shown but not ranked by rate for a code: `why` is [rule]
// for an institution a rule leaves out (no rate), else its reasons in the
// order online, medical_campus, shared, few (few only with another)
export interface RateNotRankedEntry extends RateNoteCounts {
  id: number
  count: number
  why: (NotRankedReason | RateRule)[]
  rate?: number
  lo?: number
  hi?: number
  spike?: boolean
}

export interface RankingsData {
  preset: string
  year: number
  campuses: Record<string, RankedCampus>
  // Count rankings per code, by campus: the campuses with a count above 0
  // (every other campus of `campuses` had 0)
  rankings: Record<string, CountEntry[]>
  totals: Record<string, number>
  // Rate rankings per code, by institution (rate per 10,000 on-campus FTE):
  // the ranked ones (rateRankings), those with too few incidents and no
  // other reason (rateUnranked), and those shown but not ranked for another
  // reason or left out by a rule (rateNotRanked). An institution is in at
  // most one of the three per code; one of `institutions` in none of them
  // had 0 of the code. A code of RateRules.countsOnly has none of them.
  institutions: Record<string, RateInstitution>
  rateRankings: Record<string, RateEntry[]>
  rateUnranked: Record<string, RateUnrankedEntry[]>
  // Absent in data built before 05 wrote it
  rateNotRanked?: Record<string, RateNotRankedEntry[]>
}

// =============================================================================
// School Profile Types
// =============================================================================

// The same campus reported by DOE under another ID, which has its own page
export interface IdChange {
  unitid: number
  relation: 'earlier' | 'later'
  years: number[]
  name: string
  campus?: string
}

export interface SchoolProfile {
  unitid: number
  name: string
  // The campus's own DOE name, shown as the title (name is its institution)
  campus?: string
  // The same campus under other DOE IDs (absent when there are none)
  idChanges?: IdChange[]
  shortName: string
  city: string
  state: string
  ivyLeague: boolean
  isMainCampus?: boolean
  campusType?: string
  fte: number | null // Full-time equivalent enrollment (latest year available)
  fteByYear: Record<string, number> | null // FTE by year for historical rate calculations
  summary: SummaryStats
  // Every year the campus reported (DOE published a row for it with at
  // least one count), 0 included for a year with no incident
  yearlyTotals: YearlyTotal[]
  // The years of the data it did not report (absent when there are none):
  // no figures at all, which is not the same as 0
  notReported?: number[]
  trends: TrendPoint[]
  breakdownByOffense: OffenseBreakdown[]
  breakdownByGeo: GeoBreakdown[]
  // Present only when some of this school's figures are an exact copy of
  // another campus's report for the same year and location. The school's own
  // figures above include them as DOE publishes them; totals and rankings
  // count them once, under the host campus.
  sharedFigures?: SharedFigure[]
  // The school's institution (all campuses with the same first six UNITID
  // digits), whose rate the pages show: fteByYear is the institution's FTE.
  // Absent when the institution is listed in none of the school's years.
  institution?: InstitutionInfo
}

export interface InstitutionInfo {
  id: number // base UNITID
  byYear: Record<string, InstitutionYear>
}

export interface InstitutionYear {
  // Its campuses in the United States that count that year
  campuses: number
  // Percent of its students enrolled exclusively online (NCES) that the rate
  // rules use, or null
  online: number | null
  // In the years of RateRules.onlineShareYear only: the fall `online` is
  // from (that other fall, or the year itself when NCES has no figure then)
  onlineYear?: number
  // Whether rate rankings list it that year: a denominator of at least
  // RateRules.minFte and no rule leaving it out. It does not mean ranked: a
  // code is ranked only when this is true, fteUncertain is absent,
  // notRanked[code] is absent, the count is at least RateRules.minCount and
  // the code is not counts-only (rateStanding in lib/rates.ts).
  rateRanked: boolean
  // Why the rate is left out that year, when the pipeline says so
  rateExcludedReason?: string
  // The rate's denominator: the larger on-campus FTE estimate, with the
  // on-campus FTE of pooledWith added (institutions whose campus figures
  // count here that year: a merger, renumbering or shared campus); absent
  // without an FTE
  rateFte?: number
  pooledWith?: PooledInstitution[]
  // Its on-campus FTE is uncertain that year: no code is ranked
  fteUncertain?: FteUncertain
  // Its campuses abroad and their incidents per code (not in counts or rates)
  abroad?: { campuses: number; counts: Record<string, number> }
  // Per code, above 0 only (RateNoteCounts)
  medical?: Record<string, number>
  sharedIn?: Record<string, number>
  sharedOut?: Record<string, number>
  // In a listed year, the codes not ranked because of medical-center
  // campuses and/or shared figures (online and few are left out: they
  // follow from fteUncertain and the count)
  notRanked?: Record<string, ('medical_campus' | 'shared')[]>
  // Codes whose count is unusually high for the institution that year
  spikes?: string[]
  // Counts of all its campuses per code (campuses abroad and figures that
  // count under another institution's campus left out); absent when equal
  // to the school's own counts that year
  counts?: Record<string, number>
}

export interface SharedFigure {
  year: number
  geo: 'On-campus' | 'Non-campus' | 'Public property'
  hostUnitid: number
  hostName: string
}

export interface SummaryStats {
  latestYear: number
  totalIncidents: number
  topOffense: string | null
  topOffenseCount: number
}

export interface YearlyTotal {
  year: number
  total: number
}

export interface TrendPoint {
  year: number
  offense: string
  offenseFamily: string
  count: number
}

export interface OffenseBreakdown {
  offense: string
  count: number
}

export interface GeoBreakdown {
  geo: string
  count: number
}

// =============================================================================
// Chart Types
// =============================================================================

export interface ChartDataPoint {
  year: number
  // null: a year the campus did not report (a gap in the chart)
  [key: string]: number | string | null
}

export interface TrendChartData {
  data: ChartDataPoint[]
  series: string[]
}

// =============================================================================
// Filter/UI State Types
// =============================================================================

export interface FilterState {
  year: number
  offense: string
  geo: string
  preset: string
}

export interface SortConfig {
  key: string
  direction: 'asc' | 'desc'
}

// =============================================================================
// API Response Types
// =============================================================================

export interface ApiError {
  message: string
  status?: number
}

export type ApiResult<T> =
  | { success: true; data: T }
  | { success: false; error: ApiError }
