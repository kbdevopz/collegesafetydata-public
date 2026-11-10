/**
 * Which calendar years the published crime data covers, read from
 * metadata.json "years" (or "coverage" when "years" is absent), and the
 * page wording built from them.
 */

import type { Metadata } from './types'
import { formatYearRanges } from './enrollment'

export interface DataYearsSummary {
  // Number of years with data; null when metadata has no usable "years".
  count: number | null
  // "2015-2024" (a gap shows as "2015-2019, 2021-2024"); null when unknown.
  span: string | null
  // Newest year with data; null when unknown.
  latest: number | null
}

/**
 * Year count, span and newest year from metadata.years. Without "years" the
 * span and newest year come from metadata.coverage and the count is unknown;
 * with neither, everything is null so callers can use wording that names no
 * year.
 */
export function summarizeDataYears(
  metadata: Pick<Metadata, 'years' | 'coverage'> | null | undefined
): DataYearsSummary {
  const raw: unknown = metadata?.years
  const years = Array.isArray(raw)
    ? [...new Set(raw.filter((y): y is number => Number.isInteger(y)))]
    : []
  if (years.length > 0) {
    return { count: years.length, span: formatYearRanges(years), latest: Math.max(...years) }
  }
  const coverage = typeof metadata?.coverage === 'string' ? metadata.coverage.trim() : ''
  const coverageYears = (coverage.match(/\b\d{4}\b/g) || []).map(Number)
  return {
    count: null,
    span: coverage || null,
    latest: coverageYears.length > 0 ? Math.max(...coverageYears) : null,
  }
}

/**
 * Reporting-lag sentence. DOE's release for year R contains calendar years
 * R-3 to R-1, so the newest data year L comes from release L+1. With no
 * newest year the wording names no year.
 */
export function describeReportingLag(latest: number | null): string {
  if (latest === null) {
    return 'DOE releases data ~1 year late. Each annual release contains statistics for the three calendar years before it.'
  }
  return `DOE releases data ~1 year late. The ${latest + 1} release contains ${latest - 2}-${latest} statistics.`
}
