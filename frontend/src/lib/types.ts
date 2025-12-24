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
}

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

export interface RankingEntry {
  rank: number
  rankByRate: number | null
  unitid: number
  name: string
  short: string
  state?: string | null
  count: number
  pct: number
  fte: number | null
  rate: number | null
  isMainCampus?: boolean
}

export interface RankingsData {
  preset: string
  year: number
  rankings: Record<string, RankingEntry[]>
  totals: Record<string, number>
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
