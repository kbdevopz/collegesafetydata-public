/**
 * Which years have final, provisional or no NCES fall enrollment (FTE), read
 * from metadata.json "enrollmentStatus" (written by etl/05_generate_json.py).
 */

import type { EnrollmentStatus, Metadata } from './types'

export type EnrollmentStatusSummary = Record<EnrollmentStatus, number[]>

/**
 * Group metadata.years by their enrollment status, oldest first. Returns null
 * when metadata has no usable "enrollmentStatus" (for example data built
 * before the key existed), so callers can fall back to wording that names no
 * year.
 */
export function summarizeEnrollmentStatus(
  metadata: Pick<Metadata, 'years' | 'enrollmentStatus'> | null | undefined
): EnrollmentStatusSummary | null {
  const status = metadata?.enrollmentStatus
  if (!metadata || !status || typeof status !== 'object' || Array.isArray(status)) return null
  const summary: EnrollmentStatusSummary = { final: [], provisional: [], missing: [] }
  const years = Array.isArray(metadata.years) ? [...metadata.years].sort((a, b) => a - b) : []
  for (const year of years) {
    const value = status[String(year)]
    if (value === 'final' || value === 'provisional' || value === 'missing') {
      summary[value].push(year)
    }
  }
  if (summary.final.length + summary.provisional.length + summary.missing.length === 0) return null
  return summary
}

/**
 * Plain sentences saying which falls have final, provisional or no NCES
 * enrollment. With no summary (metadata without "enrollmentStatus") the
 * wording names no year.
 */
export function describeEnrollmentStatus(summary: EnrollmentStatusSummary | null): string[] {
  if (!summary) {
    return [
      'Each year uses the newest enrollment file NCES has published. The most recent fall can be ' +
        'provisional release data until NCES publishes its final revision, and a year whose fall ' +
        'enrollment NCES has not published yet has no rates.',
    ]
  }
  const sentences: string[] = []
  if (summary.final.length > 0) {
    sentences.push(`Fall ${formatYearRanges(summary.final)} enrollment is final NCES data.`)
  }
  if (summary.provisional.length > 0) {
    const one = summary.provisional.length === 1
    sentences.push(
      `Fall ${formatYearRanges(summary.provisional)} ${one ? 'is' : 'are'} provisional release data; ` +
        `${one ? 'its' : 'their'} FTE and rates can change when NCES publishes the final revision.`
    )
  }
  if (summary.missing.length > 0) {
    const ranges = formatYearRanges(summary.missing)
    sentences.push(
      `Fall ${ranges} enrollment has not been published by NCES yet, so rates for ${ranges} are not available yet.`
    )
  }
  return sentences
}

/**
 * Short wording for which falls have NCES enrollment (FTE) for rates, e.g.
 * "Rate calculations use IPEDS FTE enrollment data, available for 2015-2024
 * (2024 is provisional)." With no summary (metadata without
 * "enrollmentStatus") the wording names no year.
 */
export function describeFteAvailability(summary: EnrollmentStatusSummary | null): string {
  const lead = 'Rate calculations use IPEDS FTE enrollment data'
  if (!summary) {
    return `${lead}. A year whose fall enrollment NCES has not published yet has no rates.`
  }
  const available = [...summary.final, ...summary.provisional]
  let text = available.length > 0 ? `${lead}, available for ${formatYearRanges(available)}` : lead
  if (summary.provisional.length > 0) {
    const one = summary.provisional.length === 1
    text += ` (${formatYearRanges(summary.provisional)} ${one ? 'is' : 'are'} provisional)`
  }
  text += '.'
  if (summary.missing.length > 0) {
    const ranges = formatYearRanges(summary.missing)
    const one = summary.missing.length === 1
    text += ` NCES has not published fall ${ranges} enrollment yet, so ${ranges} ${one ? 'has' : 'have'} no rates.`
  }
  return text
}

/**
 * Years as ranges: [2015, 2016, 2017, 2019] -> "2015-2017, 2019".
 */
export function formatYearRanges(years: number[]): string {
  const sorted = [...new Set(years)].sort((a, b) => a - b)
  const parts: string[] = []
  let start: number | null = null
  let prev: number | null = null
  for (const year of sorted) {
    if (start !== null && prev !== null && year === prev + 1) {
      prev = year
      continue
    }
    if (start !== null && prev !== null) parts.push(start === prev ? `${start}` : `${start}-${prev}`)
    start = year
    prev = year
  }
  if (start !== null && prev !== null) parts.push(start === prev ? `${start}` : `${start}-${prev}`)
  return parts.join(', ')
}
