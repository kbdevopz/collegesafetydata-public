/**
 * Per-10,000-FTE rates for one school-year, computed exactly the way the
 * pipeline computes the rates it publishes in rankings/*.json
 * (etl/04_create_aggregates.py and etl/05_generate_json.py):
 *
 *   rate = round(count / fte * 10000, 2)   using that year's FTE
 *
 * and no rate at all when that year has no FTE. Another year's FTE is never
 * used. Display rounding (toFixed) is left to the pages.
 */

import type { SchoolProfile } from './types'

type FteSource = Pick<SchoolProfile, 'fteByYear'> | null | undefined

/**
 * FTE for one year from the profile's fteByYear, or null when that year has
 * no FTE above 0.
 */
export function fteFor(profile: FteSource, year: number | null | undefined): number | null {
  if (!profile || year === null || year === undefined || !Number.isFinite(year)) return null
  const value = profile.fteByYear?.[String(year)]
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

/**
 * Round to 2 decimals the way numpy/pandas round(2) does: scale by 100,
 * round half to even, scale back.
 */
export function round2(x: number): number {
  const scaled = x * 100
  const floor = Math.floor(scaled)
  const diff = scaled - floor
  let rounded: number
  if (diff > 0.5) rounded = floor + 1
  else if (diff < 0.5) rounded = floor
  else rounded = floor % 2 === 0 ? floor : floor + 1
  return rounded / 100
}

/**
 * Rate per 10,000 FTE for `count` incidents in `year`, or null when that year
 * has no FTE (or there is no count).
 */
export function rateFor(
  profile: FteSource,
  year: number | null | undefined,
  count: number | null | undefined
): number | null {
  const fte = fteFor(profile, year)
  if (fte === null || count === null || count === undefined || !Number.isFinite(count)) return null
  return round2((count / fte) * 10000)
}

/**
 * The newest year in fteByYear and its FTE (the value 05 also writes as
 * profile.fte), or null when there is none above 0.
 */
export function latestFte(profile: FteSource): { year: number; fte: number } | null {
  if (!profile || !profile.fteByYear) return null
  let newest: number | null = null
  for (const key of Object.keys(profile.fteByYear)) {
    const year = Number(key)
    if (Number.isInteger(year) && (newest === null || year > newest)) newest = year
  }
  if (newest === null) return null
  const fte = fteFor(profile, newest)
  return fte === null ? null : { year: newest, fte }
}
