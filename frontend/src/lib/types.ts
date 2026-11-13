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
  // Who rate rankings list (etl/config.py): institutions with at least
  // minFte FTE students and fewer than onlineExclusionPct percent of their
  // students enrolled exclusively online
  rateRules: RateRules
}

export interface RateRules {
  minFte: number
  onlineExclusionPct: number
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

// A campus of a rankings file (its "campuses" table)
export interface RankedCampus {
  name: string
  short: string | null
  state: string | null
  main: boolean
  // Its institution's FTE (NCES publishes FTE per institution, not campus)
  fte: number | null
  // Its institution's number of campuses that year
  campuses: number
}

// One campus of a count ranking (by count, ties by name, then UNITID)
export interface CountEntry {
  rank: number
  unitid: number
  count: number
}

// An institution of a rankings file's rate rankings: all campuses with the
// same first six UNITID digits, shown as `name` and linked to the school
// page of campus `unitid`
export interface RateInstitution {
  name: string
  unitid: number
  state: string | null
  fte: number
  campuses: number
}

// One institution of a rate ranking: `id` is its base UNITID (a key of
// RankingsData.institutions), `count` the incidents of all its campuses
export interface RateEntry {
  rank: number
  id: number
  count: number
  rate: number
}

export interface RankingsData {
  preset: string
  year: number
  campuses: Record<string, RankedCampus>
  // Count rankings per code, by campus
  rankings: Record<string, CountEntry[]>
  totals: Record<string, number>
  // Rate rankings per code, by institution (rate per 10,000 FTE)
  institutions: Record<string, RateInstitution>
  rateRankings: Record<string, RateEntry[]>
}

// =============================================================================
// School Profile Types
// =============================================================================

export interface SchoolProfile {
  unitid: number
  name: string
  shortName: string
  city: string
  state: string
  ivyLeague: boolean
  isMainCampus?: boolean
  campusType?: string
  fte: number | null // Full-time equivalent enrollment (latest year available)
  fteByYear: Record<string, number> | null // FTE by year for historical rate calculations
  summary: SummaryStats
  yearlyTotals: YearlyTotal[]
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
  campuses: number
  // Percent of its students enrolled exclusively online (NCES), or null
  online: number | null
  // Whether rate rankings list it that year (Metadata.rateRules)
  rateRanked: boolean
  // Counts of all its campuses per code (shadow blocks left out); absent
  // when equal to the school's own counts that year
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
  [key: string]: number | string
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
