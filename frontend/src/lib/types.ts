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
  // The rate rules (etl/config.py): windows, who is rated, the interval
  // model, verdicts, lists, flags and the count flag
  rateRules: RateRules
  // What the rate rules did, counted by the build (05): the figures the
  // pages quote. Absent in data built before 05 wrote it.
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
  // A window's institution-years need a rate denominator (on-campus FTE,
  // pooled FTE added) of at least this many in every year
  minFte: number
  // On-campus FTE is uncertain when the larger of its two estimates times
  // [1] is more than the smaller times [0] ([5, 4]: more than 25% apart)
  onlineUncertainRatio: Ratio
  // Years whose online share is another fall's, e.g. {"2021": 2019}
  onlineShareYear?: Record<string, number>
  // Years per window, the years no window contains, and the windows
  windowYears: number
  skipYears: number[]
  windows: [number, number][]
  // The codes with a rate and the offenses each adds up
  codes: Record<string, string[]>
  // Count codes without a rate (counts only)
  countsOnly: string[]
  // The level of each interval (0.95)
  ciLevel: number
  dispersion: Dispersion
  // A code's reason is medical_campus when incidents at listed
  // medical-center campuses outside their residence halls are at least this
  // share of the window's on-campus count ([1, 4]: a quarter)
  medicalShare: Ratio
  // A guest or participant at a shared site is compared as usual only when
  // a reviewed, published figure puts its students there at most this
  // share of its student-years ([1, 10])
  sharedSiteShare: Ratio
  // Near-copies that join two campuses into a shared site: the campus with
  // the smaller total has at least minNonzero nonzero cells, at least
  // match[0] / match[1] of them equal to the other's, and a total of at
  // least minTotal
  sharedNear: { minNonzero: number; match: Ratio; minTotal: number }
  lists: {
    // The codes with ordered lists
    codes: string[]
    // Members: expected count at the national rate of at least this
    minExpected: number
    // Rank ranges: 1 - alpha confidence, Bonferroni over n - 1 comparisons
    alpha: number
    // State fields are published for states with at least this many members
    stateMinMembers: number
    // The pages show a state's own positions from this many members up
    // (lib/rateDisplay.ts stateDisplayMin)
    stateDisplayMin: number
  }
  // Residential types of the peer comparison (Carnegie size and setting)
  peerTypes: Record<string, { label: string; sizeSetting: number[] }>
  sizeSettingFields: string[]
  // Unusual-year flags
  flags: {
    offenses: string[]
    geos: string[]
    minCount: number
    minOtherYears: number
    p: number
    c: number
    minMean: number
  }
  // Count rankings flag a count of at least minCount whose count per 10,000
  // institution FTE is more than factor times the percentile-th percentile of
  // that year's single-year rates of the code (reference[year][code])
  countFlag: {
    minCount: number
    factor: number
    percentile: number
    reference: Record<string, Record<string, number>>
  }
  // The audit's medical-campus name screen (check 14)
  medicalScreen?: { pattern: string; share: Ratio; minCount: number }
  // The audit's calibration check (check 13)
  calibration?: {
    codes: string[]
    periods: (string | [number, number])[]
    latestYears: number
    simulations: number
    seed: number
    bands: number[]
    // Overall, either way
    tolerance: number
    // A band of bandMinUnits or more institutions fails when its observed
    // coverage is below expected by more than bandToleranceBelow, or above
    // it by more than bandToleranceAbove
    bandToleranceBelow: number
    bandToleranceAbove: number
    bandMinUnits: number
  }
  testVectors?: {
    // interval: [lo, hi] of the count
    counts: { c: number; years: number; n: number; phi: number; interval: [number, number] }[]
    rates: { n: number; fteYears: number; c: number; rate: number; lo: number; hi: number }[]
  }
}

export interface Dispersion {
  // Var(m) = m + c g(m) m^power, g(m) = min(cap, max(1, m / start)) up to end
  power: number
  c: Record<string, number>
  fitted: Record<string, number>
  other: number
  ramp: { start: number; end: number; cap: number }
}

// The rules that give an institution no rate (in any window containing the year)
export type RateRule =
  | 'hospital' | 'medical' | 'listed' | 'merger' | 'family' | 'shared_pooled' | 'shared_campus'

// Why a rated institution is not on a list (its rate is still shown; with
// "shared" its comparisons are withheld)
export type RateWhy = 'online' | 'medical_campus' | 'shared'

// "undetermined" only with why "online"; "withheld" only with why "shared"
export type Verdict = 'above' | 'below' | 'nd' | 'undetermined' | 'withheld'

// An institution named in a shared-site note
export interface NamedInstitution {
  id: number
  name: string
}

// A guest or participant at a shared site: the years, its students there by
// a reviewed published figure (summed over those years; null when a year
// has none), whether that figure is an upper bound, and whether it is small
// enough (students x sharedSiteShare[1] <= fteYears x sharedSiteShare[0])
// for the institution to be compared as usual
export interface SharedSite {
  years: number[]
  students: number | null
  upperBound: boolean
  exempt: boolean
}

// The shared-site notes of an institution and window (window-file entries;
// the rated window status of an institution file)
export interface SharedSiteNotes {
  // The guests at the sites it owns
  sharedInWith?: NamedInstitution[]
  // The owners or other participants of the sites it is a guest or participant of
  sharedOutWith?: NamedInstitution[]
  sharedSite?: SharedSite
  // Institutions whose students its rate adds, because their campuses at a
  // shared site copy its own
  coLocated?: NamedInstitution[]
}

export interface WindowCodeStats {
  natl: number
  rated: number
  byWhy: Record<'none' | RateWhy, number>
  verdicts: Record<Verdict, number>
  verdictsNoReason: Partial<Record<Verdict, number>>
  peerVerdicts: Partial<Record<Verdict, number>>
  withFlags: number
  verdictWithoutFlaggedDiffers: number
  // List codes only
  listed?: number
  minFteYears?: number
  stateLists?: number
  stateListsDisplayMin?: number
}

export interface RateStats {
  // The exact set each count counts, in words
  definitions: Record<string, string>
  // windows["2022-2024"][code]
  windows: Record<string, Record<string, WindowCodeStats>>
  flags: {
    total: number
    byGeo: Record<string, number>
    byYear: Record<string, number>
    byOffense: Record<string, number>
  }
  // Institutions with a single-year rate, per year
  singleYear: Record<string, number>
  institutionFiles: number
  // Count-ranking entries flagged highForSize, per year and code
  countFlags: Record<string, Record<string, number>>
  institutionYears: {
    // Institution-years each rule gives no rate (as the first rule), and how
    // many of them have a denominator of at least minFte
    rules: Record<RateRule, { institutionYears: number; withFte: number }>
    // Institution-years rated with another institution's FTE added
    pooled: { merger: number; shared: number }
    byYear: Record<string, {
      withFte: number
      excluded: number
      rated: number
      fteUncertain: number
      fteUncertainPooledOnly: number
      abroad: number
      outsideScopeWithFte: number
    }>
    // Pandemic years whose own online share was used (no fall 2019 share)
    onlineOwnYear: Record<string, { all: number; withFte: number }>
  }
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
  // The count is at least RateRules.countFlag.minCount and its count per
  // 10,000 of its institution's FTE is more than countFlag.factor times
  // countFlag.reference[year][code] (the percentile-th percentile of that
  // year's institution rates of the code)
  highForSize?: boolean
}

// An institution whose FTE another's rate adds: `id` its base UNITID
export interface PooledInstitution {
  id: number
  name: string | null
  fte: number
}

export interface RankingsData {
  preset: string
  year: number
  campuses: Record<string, RankedCampus>
  // Count rankings per code, by campus: the campuses with a count above 0
  // (every other campus of `campuses` had 0)
  rankings: Record<string, CountEntry[]>
  totals: Record<string, number>
}

// =============================================================================
// Rate files (rates/*.json)
// =============================================================================

// An unusual-year flag: `usual` is the median of the institution's counts of
// the offense and geography in its other years (may end in .5)
export interface RateFlag {
  year: number
  offense: string
  count: number
  usual: number
}

export interface InstitutionFlag extends RateFlag {
  geo: 'On-campus' | 'Non-campus' | 'Public property'
}

// One rated institution of a window and code: its 3-year on-campus rate
export interface RateEntryFields {
  // On-campus incidents in the window's years; other geographies (not in the rate)
  n: number
  nNoncampus: number
  nPublic: number
  // The rate's denominator: on-campus FTE summed over the years
  fteYears: number
  // Per 10,000 on-campus students a year (2 decimals) and its interval
  rate: number
  lo: number
  hi: number
  // Incidents expected at the national rate (1 decimal)
  E: number
  verdict: Verdict
  why?: RateWhy
  // why "online": the verdict with each FTE estimate, and why undetermined
  verdictLargerFte?: Verdict
  verdictSmallerFte?: Verdict
  undeterminedReason?: 'estimates' | 'noSecondEstimate'
  fteYearsSmaller?: number
  fteUncertain?: Record<string, 'own' | 'pooled'>
  peerVerdict: Verdict | null
  peerVerdictLargerFte?: Verdict
  peerVerdictSmallerFte?: Verdict
  medical?: number
  // A host's on-campus incidents at the shared sites it owns (in n); a
  // guest's or participant's at its campuses at shared sites (not in n)
  sharedIn?: number
  sharedOut?: number
  // On-campus unusual-year flags of the code's offenses in the window
  flags?: RateFlag[]
  // The verdict without the flagged years' excess, only when it differs
  verdictWithoutFlagged?: Verdict
  // List codes only
  listed?: boolean
  position?: number
  rankLo?: number
  rankHi?: number
  statePosition?: number
  stateRankLo?: number
  stateRankHi?: number
  stateN?: number
  // violent: its four offenses; criminal_xmvt: motor-vehicle thefts
  composition?: Record<string, number>
}

export interface RateWindowEntry extends RateEntryFields, SharedSiteNotes {
  id: number
  unitid: number
  name: string
  state: string
  peerType: string
}

export interface PeerRate {
  rate: number
  n: number
  fteYears: number
  members: number
}

// rates/{y0}-{y1}-{code}.json: every rated institution, ordered by rate
export interface RateWindowFile {
  window: [number, number]
  code: string
  years: number[]
  c: number
  natl: number
  natlN: number
  natlF: number
  peer: Record<string, PeerRate>
  summary: {
    rated: number
    byWhy: Record<string, number>
    verdicts: Record<string, number>
    verdictsNoReason: Record<string, number>
    peerVerdicts: Record<string, number>
    withFlags: number
    verdictWithoutFlaggedDiffers: number
  }
  composition?: Record<string, number>
  list?: { n: number; minExpected: number; minFteYears: number; zc: number | null }
  stateLists?: Record<string, number>
  entries: RateWindowEntry[]
}

// A code of an institution's rated window: the window-file entry plus its
// on-campus incidents per year, the national and peer-type rates
export interface InstitutionWindowCode extends RateEntryFields {
  nByYear: Record<string, number>
  natl: number
  peerRate: number | null
}

export type InstitutionWindow =
  | ({
      status: 'rated'
      why?: 'online' | 'shared'
      fteByYear: Record<string, number>
      fteSmallerByYear?: Record<string, number>
      codes: Record<string, InstitutionWindowCode>
    } & SharedSiteNotes)
  | { status: 'missingYears'; years: number[] }
  | { status: 'scope' }
  | { status: 'size'; fteByYear: Record<string, number | null> }
  | { status: 'excluded'; rules: Record<string, RateRule> }

export type NotRatedReason = 'scope' | 'size' | 'excluded' | 'skippedYear'

// A single year: [n, rate, lo, hi] per code (1-year interval), or why not
export interface InstitutionRateYear {
  fte?: number
  rates?: Record<string, [number, number, number, number]>
  fteUncertain?: 'own' | 'pooled'
  medical?: Record<string, number>
  sharedIn?: Record<string, number>
  sharedOut?: Record<string, number>
  notRated?: NotRatedReason
}

// rates/institutions/{base}.json
export interface InstitutionRatesFile {
  id: number
  unitid: number
  name: string
  state: string
  peerType: string
  years: Record<string, InstitutionRateYear>
  windows: Record<string, InstitutionWindow>
  flags: InstitutionFlag[]
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
  // "rates/institutions/{id}.json" when the institution has one (a rated
  // window, a single-year rate or an unusual-year flag)
  ratesFile?: string
  byYear: Record<string, InstitutionYear>
}

// The two estimates of an institution's on-campus FTE (rounded) when they
// are more than RateRules.onlineUncertainRatio apart: proportional, FTE x
// (1 - online share); and part-time first, null when NCES's headcounts do
// not allow it. reason "pooled": only a pooled partner's estimates differ.
export interface FteUncertain {
  share: number
  partTimeFirst: number | null
  reason: 'own' | 'pooled'
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
  // The year has a single-year rate (school-page trend only)
  rated: boolean
  // Why it has none, the first that applies
  notRated?: NotRatedReason
  // Why a population rule leaves it out that year, in words
  rateExcludedReason?: string
  // The rate's denominator: the larger on-campus FTE estimate, with the
  // on-campus FTE of pooledWith added (institutions whose campus figures
  // count here that year: a merger, renumbering or shared campus); absent
  // without an FTE
  rateFte?: number
  pooledWith?: PooledInstitution[]
  fteUncertain?: FteUncertain
  // Its campuses abroad and their incidents per code (not in counts or rates)
  abroad?: { campuses: number; counts: Record<string, number> }
  // That year's unusual-year flags (every geography)
  flags?: Omit<InstitutionFlag, 'year'>[]
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
