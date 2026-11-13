/**
 * What a page counts: one offense, or one of the two summary codes the
 * pipeline writes (etl/05_generate_json.py).
 *
 *   'criminal'  the 11 criminal offenses added up (the default view)
 *   'all'       every category added up: criminal offenses, VAWA offenses,
 *               arrests and disciplinary referrals. These are different
 *               kinds of counts (arrests and referrals count people, and a
 *               VAWA offense can also be counted as a criminal offense), so
 *               this total is labelled as a mix, not as incidents.
 *
 * Rankings use offense codes ('burglary'); school profiles use the offense
 * names in their trends ('Burglary') plus these two codes.
 */

import type { Offense, TrendPoint } from './types'

export const CRIMINAL = 'criminal'
export const ALL = 'all'

export const SUMMARY_LABELS: Record<string, string> = {
  [CRIMINAL]: 'All criminal offenses',
  [ALL]: 'All categories (crimes, arrests, referrals)',
}

// The offense family whose offenses 'criminal' adds up
const CRIMINAL_FAMILY = 'Criminal'

/** What one counted unit is called, by offense family (or summary code). */
function unitOf(code: string, family: string | undefined): 'offense' | 'arrest' | 'referral' | 'mixed' {
  if (code === ALL) return 'mixed'
  if (code === CRIMINAL) return 'offense'
  if (family === 'Arrest') return 'arrest'
  if (family === 'Disciplinary') return 'referral'
  return 'offense'
}

/** Column header for the counts of `offense` ("Offenses", "Arrests", "Referrals", "Total"). */
export function countHeader(offense: Pick<Offense, 'code' | 'family'> | undefined): string {
  if (!offense) return 'Count'
  return { offense: 'Offenses', arrest: 'Arrests', referral: 'Referrals', mixed: 'Total' }[
    unitOf(offense.code, offense.family)
  ]
}

/** "12 offenses", "1 arrest", "3 referrals", "40 in total" for `n` counts of `offense`. */
export function countPhrase(n: number, offense: Pick<Offense, 'code' | 'family'> | undefined, formatted: string): string {
  const unit = offense ? unitOf(offense.code, offense.family) : 'offense'
  if (unit === 'mixed') return `${formatted} in total`
  return `${formatted} ${unit}${n === 1 ? '' : 's'}`
}

/**
 * What "reported no ..." names for a rankings code: "criminal offenses",
 * "crimes, arrests or referrals", "drug arrests", "liquor discipline
 * referrals", or the offense itself ("burglary").
 */
export function noneOfPhrase(code: string, offense: Pick<Offense, 'display' | 'family'> | undefined): string {
  if (code === CRIMINAL) return 'criminal offenses'
  if (code === ALL) return 'crimes, arrests or referrals'
  const name = (offense?.display ?? code.split('_').join(' ')).toLowerCase()
  if (offense?.family === 'Arrest') return `${name}s`
  if (offense?.family === 'Disciplinary') return `${name} referrals`
  return name
}

/**
 * Text order the pipeline uses for ties (Python string order: by code
 * point), not the browser's locale order.
 */
export function compareText(a: string | null | undefined, b: string | null | undefined): number {
  const x = a ?? ''
  const y = b ?? ''
  return x < y ? -1 : x > y ? 1 : 0
}

/**
 * Standard competition ranks ("1, 2, 2, 4") of items already sorted from
 * the largest value down: tied values share a rank and the next rank skips.
 */
export function competitionRanks<T>(sorted: T[], value: (item: T) => number): number[] {
  const ranks: number[] = []
  sorted.forEach((item, i) => {
    ranks.push(i > 0 && value(item) === value(sorted[i - 1]) ? ranks[i - 1] : i + 1)
  })
  return ranks
}

/** Whether a profile trend row belongs to `selection` ('criminal', 'all' or an offense name). */
export function inSelection(point: Pick<TrendPoint, 'offense' | 'offenseFamily'>, selection: string): boolean {
  if (selection === ALL) return true
  if (selection === CRIMINAL) return point.offenseFamily === CRIMINAL_FAMILY
  return point.offense === selection
}

/** Label of a profile selection: a summary label, or the offense name itself. */
export function selectionLabel(selection: string): string {
  return SUMMARY_LABELS[selection] ?? selection
}

/** Whether `selection` is one of the summary codes rather than one offense. */
export function isSummary(selection: string): boolean {
  return selection === ALL || selection === CRIMINAL
}

/**
 * The code of a profile selection in the site files: a summary code as is,
 * an offense name the way the pipeline makes codes (05's offense_code:
 * lower case, spaces to "_", e.g. "Motor Vehicle Theft" ->
 * "motor_vehicle_theft").
 */
export function selectionCode(selection: string): string {
  return isSummary(selection) ? selection : selection.toLowerCase().split(' ').join('_')
}
