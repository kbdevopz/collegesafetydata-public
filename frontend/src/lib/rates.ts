/**
 * Per-10,000-FTE rates, computed exactly the way the pipeline computes the
 * rates it publishes in rankings/*.json (etl/05_generate_json.py):
 *
 *   rate = round(count / fte * 10000, 2)   using that year's on-campus FTE
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
 * FTE. Null when the institution is not listed that year; the rate is null
 * in a year the pipeline leaves out (rateExcludedReason).
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
  // The rate's denominator: the on-campus FTE of the year, plus that of the
  // institutions whose campus figures count here (rateFte); none at 0
  const denominator = entry.rateFte ?? fteFor(profile, year)
  const fte = denominator !== null && denominator > 0 ? denominator : null
  return {
    year,
    campuses: entry.campuses,
    online: entry.online,
    onlineYear: entry.onlineYear,
    rateRanked: entry.rateRanked,
    rateExcludedReason: entry.rateExcludedReason,
    rateFte: entry.rateFte,
    pooledWith: entry.pooledWith,
    spikes: entry.spikes,
    count,
    fte,
    // No rate for a year whose incidents and FTE may not cover the same campuses
    rate: entry.rateExcludedReason || fte === null ? null : round2((count / fte) * 10000),
  }
}

// log(k!) for k = 0, 1, 2, ... (grown on demand)
const logFactorials: number[] = [0]

function logFactorial(k: number): number {
  for (let i = logFactorials.length; i <= k; i++) logFactorials.push(logFactorials[i - 1] + Math.log(i))
  return logFactorials[k]
}

/** P(X <= n) for X ~ Poisson(lam), summed in log space (as etl/05_generate_json.py does). */
export function poissonCdf(n: number, lam: number): number {
  if (lam <= 0) return 1
  const logLam = Math.log(lam)
  const terms: number[] = []
  let top = -Infinity
  for (let k = 0; k <= n; k++) {
    const t = k * logLam - lam - logFactorial(k)
    terms.push(t)
    if (t > top) top = t
  }
  let sum = 0
  for (const t of terms) sum += Math.exp(t - top)
  return Math.min(1, Math.exp(top) * sum)
}

/** The x in [lo, hi] where the decreasing f(x) equals target, by bisection. */
function solve(f: (x: number) => number, target: number, lo: number, hi: number): number {
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2
    if (f(mid) > target) lo = mid
    else hi = mid
    if (hi - lo <= 1e-12 * Math.max(1, hi)) break
  }
  return (lo + hi) / 2
}

const garwoodCache = new Map<string, [number, number]>()

/**
 * The exact (Garwood) Poisson interval of a count n at `level` (0.95): the
 * means at which P(X >= n) and P(X <= n) are (1 - level) / 2; the lower
 * bound is 0 for n = 0.
 */
export function garwood(n: number, level: number): [number, number] {
  const key = `${n}|${level}`
  const cached = garwoodCache.get(key)
  if (cached) return cached
  const alpha = 1 - level
  const span = n + 10 * Math.sqrt(n + 1) + 10
  const lower = n === 0 ? 0 : solve((lam) => poissonCdf(n - 1, lam), 1 - alpha / 2, 0, span)
  const upper = solve((lam) => poissonCdf(n, lam), alpha / 2, 0, span)
  const out: [number, number] = [lower, upper]
  garwoodCache.set(key, out)
  return out
}

/** The interval of a rate per 10,000: garwood(count) / fte x 10,000, rounded to 2 decimals. */
export function rateInterval(count: number, fte: number, level: number): { lo: number; hi: number } {
  const [lower, upper] = garwood(count, level)
  return { lo: round2((lower / fte) * 10000), hi: round2((upper / fte) * 10000) }
}

/** "8.1–17.9": a rate interval's bounds to 1 decimal. */
export function intervalText(lo: number, hi: number): string {
  return `${lo.toFixed(1)}–${hi.toFixed(1)}`
}

/**
 * Where a rate stands under the rate rules (Metadata.rateRules): 'countsOnly'
 * for an offense too rare nationally for a rate ranking, 'few' below
 * minCount incidents (shown, not ranked by rate), else 'ranked'.
 */
export function rateTier(code: string, count: number, rules: RateRules | null | undefined): 'countsOnly' | 'few' | 'ranked' {
  if (rules?.countsOnly?.includes(code)) return 'countsOnly'
  if (rules && count < rules.minCount) return 'few'
  return 'ranked'
}

/** The visible note of an unusually high count (Metadata.rateRules.spike). */
export const SPIKE_NOTE = 'Unusually high for this institution; DOE counts crimes in the year reported.'

/**
 * "Its 2015 rate also counts the 457 on-campus FTE of School of the Museum
 * of Fine Arts at Tufts, whose campus figures count under this institution
 * that year (a merger, a renumbering or a shared campus)." for a rate with
 * other institutions' FTE added, else null.
 */
export function pooledNote(inst: InstitutionRate | null): string | null {
  if (!inst || !inst.pooledWith || inst.pooledWith.length === 0) return null
  const parts = inst.pooledWith.map(
    (p) => `the ${p.fte.toLocaleString()} on-campus FTE of ${p.name ?? `institution ${p.id}`}`
  )
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0]
  return `Its ${inst.year} rate also counts ${list}, whose campus figures count under this institution that year (a merger, a renumbering or a shared campus).`
}

/**
 * Why an institution is left out of rate rankings, as a plain sentence, or
 * null when it is listed (or `rules` are not loaded yet).
 */
export function rateNote(inst: InstitutionRate | null, rules: RateRules | null | undefined): string | null {
  if (!inst || inst.rateRanked) return null
  // A reason the pipeline gives (population, merger, shared campus) comes first
  if (inst.rateExcludedReason) return inst.rateExcludedReason
  if (!rules) return null
  if (inst.fte !== null && inst.fte < rules.minFte) {
    return `Its on-campus enrollment is under ${rules.minFte.toLocaleString()} FTE students, so it is left out of rate rankings.`
  }
  return null
}

/**
 * How the on-campus FTE was found, as a plain sentence: the share of
 * students studying exclusively online taken out of the FTE (and, in a
 * pandemic year of rules.onlineShareYear, which fall's share), or null.
 */
export function onlineNote(inst: InstitutionRate | null, rules: RateRules | null | undefined): string | null {
  if (!inst || inst.online === null || inst.online === 0) return null
  const shareYear = rules?.onlineShareYear?.[String(inst.year)]
  if (shareYear !== undefined && inst.onlineYear !== undefined && inst.onlineYear !== inst.year) {
    return `On-campus FTE leaves out the ${inst.online}% of students who studied exclusively online in fall ${inst.onlineYear}, before the pandemic (the share used for ${inst.year}).`
  }
  return `On-campus FTE leaves out the ${inst.online}% of students who studied exclusively online (fall ${inst.onlineYear ?? inst.year}).`
}

/** "all 3 campuses combined" for an institution of more than one campus, else null. */
export function campusesPhrase(campuses: number): string | null {
  return campuses > 1 ? `all ${campuses} campuses combined` : null
}
