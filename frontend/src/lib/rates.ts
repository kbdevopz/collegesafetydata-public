/**
 * Per-10,000-FTE rates, computed exactly the way the pipeline computes the
 * rates it publishes in rankings/*.json (etl/05_generate_json.py):
 *
 *   rate = round(count / fte * 10000, 2)   using that year's FTE
 *
 * and no rate at all when that year has no FTE. Another year's FTE is never
 * used. Display rounding (toFixed) is left to the pages.
 *
 * Rates are institution rates: NCES publishes FTE per institution (all
 * campuses with the same first six UNITID digits), not per campus, so the
 * count is that of all the institution's campuses (institutionRate).
 */

import type { InstitutionYear, RateRules, SchoolProfile } from './types'
import { selectionCode } from './selection'

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

/** A school's institution in one year, as its rate counts it. */
export interface InstitutionRate extends Omit<InstitutionYear, 'counts'> {
  year: number
  count: number // incidents of all its campuses
  fte: number | null
  rate: number | null // per 10,000 FTE; null without an FTE
}

/**
 * The rate of the school's institution for `selection` (a summary code or
 * an offense name) in `year`: the count of all the institution's campuses
 * (institution.byYear counts, or `ownCount`, the school's own count, when
 * the file leaves them out because they are the same) per 10,000 of its
 * FTE. Null when the institution is not listed that year.
 */
export function institutionRate(
  profile: Pick<SchoolProfile, 'fteByYear' | 'institution'> | null | undefined,
  year: number | null | undefined,
  selection: string,
  ownCount: number
): InstitutionRate | null {
  if (!profile || year === null || year === undefined) return null
  const entry = profile.institution?.byYear[String(year)]
  if (!entry) return null
  const count = entry.counts ? entry.counts[selectionCode(selection)] ?? 0 : ownCount
  return {
    year,
    campuses: entry.campuses,
    online: entry.online,
    onlineYear: entry.onlineYear,
    rateRanked: entry.rateRanked,
    count,
    fte: fteFor(profile, year),
    rate: rateFor(profile, year, count),
  }
}

/**
 * Why an institution is left out of rate rankings, as a plain sentence, or
 * null when it is listed (or `rules` are not loaded yet).
 */
export function rateNote(inst: InstitutionRate | null, rules: RateRules | null | undefined): string | null {
  if (!inst || inst.rateRanked || !rules) return null
  if (inst.online !== null && inst.online >= rules.onlineExclusionPct) {
    const leftOut = 'so its rate is not comparable and it is left out of rate rankings.'
    // A pandemic year (rules.onlineShareYear) is judged by another fall's
    // share, so the note says which share and fall it used
    const shareYear = rules.onlineShareYear?.[String(inst.year)]
    if (shareYear !== undefined && inst.onlineYear !== undefined) {
      if (inst.onlineYear !== inst.year) {
        return `${inst.online}% of its students studied exclusively online in fall ${inst.onlineYear}, before the pandemic (the share used for ${inst.year}), ${leftOut}`
      }
      return `${inst.online}% of its students studied exclusively online in fall ${inst.year} (NCES has no fall ${shareYear} figure for it), ${leftOut}`
    }
    return `${inst.online}% of its students study exclusively online, ${leftOut}`
  }
  if (inst.fte !== null && inst.fte < rules.minFte) {
    return `Its enrollment is under ${rules.minFte.toLocaleString()} FTE students, so it is left out of rate rankings.`
  }
  return null
}

/** "all 3 campuses combined" for an institution of more than one campus, else null. */
export function campusesPhrase(campuses: number): string | null {
  return campuses > 1 ? `all ${campuses} campuses combined` : null
}
