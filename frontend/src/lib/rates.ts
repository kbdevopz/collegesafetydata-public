/**
 * Per-10,000-FTE rates, computed exactly the way the pipeline computes the
 * rates it publishes in rankings/*.json (etl/05_generate_json.py):
 *
 *   rate = round(count / fte * 10000, 2)   using that year's denominator
 *
 * and no rate at all when that year has no FTE. Another year's FTE is never
 * used. Display rounding (toFixed) is left to the pages.
 *
 * Rates are institution rates: NCES publishes FTE per institution (all
 * campuses with the same first six UNITID digits), not per campus, so the
 * count is that of all the institution's campuses in the United States
 * (institutionRate).
 *
 * Whether a rate is ranked is decided by the pipeline and read here
 * (rateStanding); rank ranges are the pipeline's (simulated) and are never
 * recomputed in the browser.
 */

import type {
  FteUncertain, InstitutionYear, NotRankedReason, PooledInstitution, RankingsData, RateEntry, RateInstitution,
  RateNoteCounts, RateNotRankedEntry, RateRule, RateRules, RateUnrankedEntry, SchoolProfile,
} from './types'
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

/** A school's institution in one year and one selection, as its rate counts it. */
export interface InstitutionRate extends Omit<InstitutionYear, 'counts'> {
  year: number
  code: string // the selection's code ("violent", "motor_vehicle_theft", ...)
  count: number // incidents of all its campuses in the United States
  fte: number | null
  rate: number | null // per 10,000 FTE; null without an FTE
  // Its institution is in a state or territory without rankings files
  // (Guam, the Northern Mariana Islands, ...): no rate ranking lists it
  outsideRankings?: boolean
}

/**
 * The states and territories that have rankings files (the presets with a
 * two-letter id): the 50 states, DC, Puerto Rico and the U.S. Virgin
 * Islands. State and national rankings list only institutions in them.
 */
export function rankingStates(presets: { id: string }[] | undefined): Set<string> {
  return new Set((presets ?? []).map((p) => p.id).filter((id) => /^[A-Z]{2}$/.test(id)))
}

/**
 * The rate of the school's institution for `selection` (a summary code or
 * an offense name) in `year`: the count of all the institution's campuses
 * (institution.byYear counts, or `ownCount`, the school's own count, when
 * the file leaves them out because they are the same) per 10,000 of its
 * denominator. Null when the institution has no entry that year; the rate
 * is null in a year the pipeline leaves out (rateExcludedReason).
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
  const code = selectionCode(selection)
  const { counts, ...rest } = entry
  const count = counts ? counts[code] ?? 0 : ownCount
  // The rate's denominator: the on-campus FTE of the year, plus that of the
  // institutions whose campus figures count here (rateFte); none at 0
  const denominator = entry.rateFte ?? fteFor(profile, year)
  const fte = denominator !== null && denominator > 0 ? denominator : null
  return {
    ...rest,
    year,
    code,
    count,
    fte,
    // No rate for a year whose incidents and FTE may not cover the same campuses
    rate: entry.rateExcludedReason || fte === null ? null : round2((count / fte) * 10000),
  }
}

// =============================================================================
// Intervals: negative binomial (gamma-Poisson)
// =============================================================================

// Lanczos approximation (g = 7, 9 terms): log Γ(x) for x > 0
const LANCZOS = [
  0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
  12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
]

function logGamma(x: number): number {
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x)
  const z = x - 1
  let sum = LANCZOS[0]
  for (let i = 1; i < LANCZOS.length; i++) sum += LANCZOS[i] / (z + i)
  const t = z + 7.5
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(sum)
}

/** P(a, x): the regularized lower incomplete gamma function (shape a > 0, scale 1). */
export function gammaP(a: number, x: number): number {
  if (x <= 0) return 0
  const logPrefix = a * Math.log(x) - x - logGamma(a)
  if (x < a + 1) {
    // Series: sum of x^n / (a (a+1) ... (a+n))
    let term = 1 / a
    let sum = term
    for (let n = 1; n < 1000; n++) {
      term *= x / (a + n)
      sum += term
      if (Math.abs(term) < Math.abs(sum) * 1e-16) break
    }
    return Math.min(1, sum * Math.exp(logPrefix))
  }
  // Continued fraction for Q(a, x) (modified Lentz)
  const tiny = 1e-300
  let b = x + 1 - a
  let c = 1 / tiny
  let d = 1 / b
  let h = d
  for (let i = 1; i < 1000; i++) {
    const an = -i * (i - a)
    b += 2
    d = an * d + b
    if (Math.abs(d) < tiny) d = tiny
    c = b + an / c
    if (Math.abs(c) < tiny) c = tiny
    d = 1 / d
    const delta = d * c
    h *= delta
    if (Math.abs(delta - 1) < 1e-16) break
  }
  return Math.max(0, 1 - Math.exp(logPrefix) * h)
}

/** The x with P(a, x) = q (0 < q < 1): the gamma quantile (shape a, scale 1), by bisection. */
export function gammaInv(q: number, a: number): number {
  let lo = 0
  let hi = Math.max(1, a + 10 * Math.sqrt(a) + 10)
  while (gammaP(a, hi) < q) hi *= 2
  for (let i = 0; i < 300; i++) {
    const mid = (lo + hi) / 2
    if (gammaP(a, mid) < q) lo = mid
    else hi = mid
    if (hi - lo <= 1e-15 * hi) break
  }
  return (lo + hi) / 2
}

const countIntervalCache = new Map<string, [number, number]>()

/**
 * The `level` (0.95) interval of a count n under a negative binomial
 * (gamma-Poisson) model with overdispersion k, as etl/config.py defines it:
 * phi = 1 + n / k, effective count m = n / phi; lower phi x G(alpha/2; m)
 * (0 for n = 0), upper phi x G(1 - alpha/2; m + 1), G the gamma quantile.
 * With phi = 1 it is the exact Poisson (Garwood) interval.
 */
export function countInterval(n: number, k: number, level: number): [number, number] {
  const key = `${n}|${k}|${level}`
  const cached = countIntervalCache.get(key)
  if (cached) return cached
  const alpha = 1 - level
  const phi = 1 + n / k
  const m = n / phi
  const lower = n === 0 ? 0 : phi * gammaInv(alpha / 2, m)
  const upper = phi * gammaInv(1 - alpha / 2, m + 1)
  const out: [number, number] = [lower, upper]
  countIntervalCache.set(key, out)
  return out
}

/**
 * The interval of a rate per 10,000 for `count` incidents of `code` over
 * `fte`: countInterval with the code's k (rules.dispersion.kByCode) / fte x
 * 10,000, each bound rounded to 2 decimals. Null without the rules or a k
 * for the code.
 */
export function rateInterval(
  count: number, fte: number, code: string, rules: RateRules | null | undefined
): { lo: number; hi: number } | null {
  const k = rules?.dispersion?.kByCode?.[code]
  if (!rules || k === undefined || !(fte > 0)) return null
  const [lower, upper] = countInterval(count, k, rules.ciLevel)
  return { lo: round2((lower / fte) * 10000), hi: round2((upper / fte) * 10000) }
}

/** "8.1–17.9": a rate interval's bounds to 1 decimal. */
export function intervalText(lo: number, hi: number): string {
  return `${lo.toFixed(1)}–${hi.toFixed(1)}`
}

// =============================================================================
// Where a rate stands under the rate rules
// =============================================================================

/** "25%": a ratio [a, b] as a percentage of a / b (or of a / b - 1 with `above`). */
export function ratioPercent(ratio: [number, number], above = false): string {
  const value = above ? ratio[0] / ratio[1] - 1 : ratio[0] / ratio[1]
  return `${Math.round(value * 100)}%`
}

/**
 * Where an institution-year's rate of one code stands:
 * - 'excluded': a rule leaves the institution out that year; no rate
 *   (rateExcludedReason says why)
 * - 'noRate': no denominator that year
 * - 'unlisted': listed in no rate ranking (denominator under rules.minFte)
 * - 'outside': listed in no rate ranking (its institution's state or
 *   territory has no rankings files)
 * - 'countsOnly': the code has rankings by count only
 * - 'notRanked': shown, not ranked, for `reasons` (online, medical_campus,
 *   shared, and few together with another)
 * - 'few': fewer than rules.minCount incidents and no other reason
 * - 'ranked': in the rate ranking of the code
 * As the data contract has it: a code is ranked only when rateRanked is
 * true, fteUncertain is absent, notRanked[code] is absent, the count is at
 * least minCount and the code is not counts-only.
 */
export type RateStanding =
  | { kind: 'excluded' | 'noRate' | 'unlisted' | 'outside' | 'countsOnly' | 'few' | 'ranked' }
  | { kind: 'notRanked'; reasons: NotRankedReason[] }

export function rateStanding(inst: InstitutionRate | null, rules: RateRules | null | undefined): RateStanding {
  if (!inst) return { kind: 'noRate' }
  if (inst.rateExcludedReason) return { kind: 'excluded' }
  if (inst.fte === null || inst.rate === null) return { kind: 'noRate' }
  if (!inst.rateRanked) return { kind: 'unlisted' }
  if (inst.outsideRankings) return { kind: 'outside' }
  if (rules?.countsOnly?.includes(inst.code)) return { kind: 'countsOnly' }
  const minCount = rules?.minCount ?? 20
  const reasons: NotRankedReason[] = []
  if (inst.fteUncertain) reasons.push('online')
  for (const r of inst.notRanked?.[inst.code] ?? []) reasons.push(r)
  if (reasons.length > 0) {
    if (inst.count < minCount) reasons.push('few')
    return { kind: 'notRanked', reasons }
  }
  return inst.count < minCount ? { kind: 'few' } : { kind: 'ranked' }
}

// =============================================================================
// Notes (plain sentences shown with a rate)
// =============================================================================

const fmt = (n: number) => n.toLocaleString('en-US')

/** "A", "A and B", "A, B and C" */
export function joinAnd(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0] ?? ''
}

function pooledNames(pooled: PooledInstitution[] | undefined): string | null {
  if (!pooled || pooled.length === 0) return null
  return joinAnd(pooled.map((p) => p.name ?? `institution ${p.id}`))
}

/**
 * Why an institution's on-campus FTE is uncertain, from its two estimates
 * (rounded, as published) and the institutions whose FTE its rate adds.
 * The flag is set on unrounded estimates, and also when a pooled
 * institution's on-campus FTE is uncertain, so the text never claims a gap
 * the published figures do not show.
 * `short`: a phrase for a list; else a clause for a sentence.
 */
export function fteUncertainText(
  fu: FteUncertain, pooled: PooledInstitution[] | undefined, rules: RateRules | null | undefined, short = false
): string {
  const ratio = rules?.onlineUncertainRatio ?? [5, 4]
  const pct = ratioPercent(ratio, true)
  const names = pooledNames(pooled)
  const a = fu.share
  const b = fu.partTimeFirst
  if (b === null) {
    return short
      ? `Uncertain on-campus FTE: the second estimate cannot be computed (first ${fmt(a)})`
      : `the second of its two estimates of on-campus FTE (part-time students counted after full-time ones) ` +
        `cannot be computed from NCES's headcounts, so its on-campus FTE (${fmt(a)}, from the online share alone) ` +
        'is uncertain'
  }
  const hi = Math.max(a, b)
  const lo = Math.min(a, b)
  const [num, den] = ratio
  // The published estimates show the gap
  const apart = hi * den > lo * num
  // Rounding to whole numbers could hide a gap just over the threshold
  const nearLimit = !apart && (hi + 0.5) * den > (lo - 0.5) * num
  if (apart) {
    return short
      ? `Uncertain on-campus FTE: estimates ${fmt(a)} and ${fmt(b)}`
      : `two estimates of its on-campus FTE from NCES's figures differ by more than ${pct} ` +
        `(${fmt(a)} and ${fmt(b)}); the rate uses the larger`
  }
  if (names && !nearLimit) {
    return short
      ? `Uncertain on-campus FTE of ${names}, which this rate adds`
      : `its own two estimates of on-campus FTE are within ${pct} of each other (${fmt(a)} and ${fmt(b)}), but ` +
        `those of ${names}, whose on-campus FTE this rate adds, differ by more than ${pct} or cannot both be computed`
  }
  if (names) {
    return short
      ? `Uncertain on-campus FTE: estimates ${fmt(a)} and ${fmt(b)}, or those of ${names}`
      : `two estimates of its on-campus FTE (${fmt(a)} and ${fmt(b)}, rounded), or those of ${names}, whose ` +
        `on-campus FTE this rate adds, differ by more than ${pct}`
  }
  if (nearLimit) {
    return short
      ? `Uncertain on-campus FTE: estimates ${fmt(a)} and ${fmt(b)} (rounded)`
      : `two estimates of its on-campus FTE differ by more than ${pct} before rounding (${fmt(a)} and ${fmt(b)} ` +
        'rounded); the rate uses the larger'
  }
  return short
    ? `Uncertain on-campus FTE (estimates ${fmt(a)} and ${fmt(b)})`
    : `its on-campus FTE is uncertain (estimates ${fmt(a)} and ${fmt(b)})`
}

function percentOf(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : '—'
}

/** The note counts (medical, sharedIn, sharedOut) of one code of an institution-year */
export function noteCounts(inst: InstitutionRate): RateNoteCounts {
  return {
    medical: inst.medical?.[inst.code],
    sharedIn: inst.sharedIn?.[inst.code],
    sharedOut: inst.sharedOut?.[inst.code],
  }
}

export interface ReasonContext extends RateNoteCounts {
  count: number
  fteUncertain?: FteUncertain
  pooled?: PooledInstitution[]
}

/**
 * One reason a rate is shown but not ranked, or a rule leaves it out:
 * `short` for a list row (Rankings), else a clause for a sentence.
 */
export function reasonText(
  reason: NotRankedReason | RateRule, ctx: ReasonContext, rules: RateRules | null | undefined, short = false
): string {
  const minCount = rules?.minCount ?? 20
  switch (reason) {
    case 'online':
      return ctx.fteUncertain
        ? fteUncertainText(ctx.fteUncertain, ctx.pooled, rules, short)
        : short ? 'Uncertain on-campus FTE' : 'its on-campus FTE is uncertain'
    case 'medical_campus': {
      const m = ctx.medical ?? 0
      const share = ratioPercent(rules?.medicalShare ?? [1, 4])
      return short
        ? `Medical-center campuses: ${fmt(m)} of ${fmt(ctx.count)} incidents (${percentOf(m, ctx.count)})`
        : `${fmt(m)} of its ${fmt(ctx.count)} incidents (${percentOf(m, ctx.count)}) were at medical-center ` +
          'campuses, whose patients, visitors and hospital staff are not in the enrollment the rate divides by ' +
          `(${share} or more is not ranked)`
    }
    case 'shared': {
      const sIn = ctx.sharedIn ?? 0
      const sOut = ctx.sharedOut ?? 0
      const whole = ctx.count + sOut
      const share = ratioPercent(rules?.sharedShare ?? [1, 20])
      if (short) return `Shared figures: ${fmt(sIn + sOut)} of ${fmt(whole)} incidents (${percentOf(sIn + sOut, whole)})`
      const parts: string[] = []
      if (sIn > 0) parts.push(`${fmt(sIn)} of its incidents are also reported, identically, by another institution's campus`)
      if (sOut > 0) parts.push(`${fmt(sOut)} incidents it reports count under another institution's campus and are not in its count`)
      return `${joinAnd(parts)}: more than ${share} of its incidents (${fmt(sIn + sOut)} of ${fmt(whole)}) are ` +
        `figures shared with another institution, so its count could be off by more than ${share}`
    }
    case 'few':
      return short ? `Fewer than ${minCount} incidents` : `it has fewer than ${minCount} incidents`
    case 'hospital':
      return short
        ? 'Left out: IPEDS reports that it has a hospital'
        : 'IPEDS reports that it has a hospital, whose patients, visitors and staff are not in its enrollment'
    case 'medical':
      return short
        ? 'Left out: special-focus medical school or research institution (Carnegie)'
        : 'its Carnegie classification is a special-focus medical school or research institution'
    case 'listed':
      return short
        ? 'Left out: on the reviewed list (its campus holds people its FTE does not count)'
        : 'it is on the reviewed list of institutions whose campus holds a population its FTE does not count'
    case 'merger':
      return short
        ? 'Left out: a merger or renumbering (incidents and enrollment may not cover the same campuses)'
        : 'a merger or renumbering means its incidents and enrollment may not cover the same campuses'
    case 'family':
      return short
        ? 'Left out: merged institutions (incidents and enrollment may not cover the same campuses)'
        : 'a merger means the incidents and enrollment of its group may not cover the same campuses'
  }
}

/** "Not ranked by rate: A; B; and it has fewer than 20 incidents." */
export function notRankedSentence(
  reasons: NotRankedReason[], ctx: ReasonContext, rules: RateRules | null | undefined
): string {
  const main = reasons.filter((r) => r !== 'few').map((r) => reasonText(r, ctx, rules))
  const few = reasons.includes('few') ? `; and ${reasonText('few', ctx, rules)}` : ''
  return `Not ranked by rate: ${main.join('; ')}${few}.`
}

/**
 * Notes for incidents a ranked (or too-few) rate counts or leaves out:
 * medical-center campuses and shared figures below the thresholds. A
 * reason that keeps the rate from being ranked is not repeated here.
 */
export function countNotes(
  ctx: ReasonContext, reasons: NotRankedReason[], rules: RateRules | null | undefined, short = false
): string[] {
  const notes: string[] = []
  const m = ctx.medical ?? 0
  if (m > 0 && !reasons.includes('medical_campus')) {
    notes.push(short
      ? `Includes ${fmt(m)} incidents (${percentOf(m, ctx.count)}) at medical-center campuses.`
      : `${fmt(m)} of these ${fmt(ctx.count)} incidents (${percentOf(m, ctx.count)}) were at medical-center ` +
        'campuses, whose patients, visitors and hospital staff are not in the enrollment the rate divides by. ' +
        `A rate is not ranked when such incidents are ${ratioPercent(rules?.medicalShare ?? [1, 4])} or more.`)
  }
  if (!reasons.includes('shared')) {
    const sIn = ctx.sharedIn ?? 0
    const sOut = ctx.sharedOut ?? 0
    if (sIn > 0) {
      notes.push(`${fmt(sIn)} of these incidents ${sIn === 1 ? 'is' : 'are'} also reported, identically, by another institution's campus.`)
    }
    if (sOut > 0) {
      notes.push(`${fmt(sOut)} ${sOut === 1 ? 'incident' : 'incidents'} it reports ${sOut === 1 ? 'counts' : 'count'} under another institution's campus and ${sOut === 1 ? 'is' : 'are'} not in this count.`)
    }
  }
  return notes
}

/** The visible note of an unusually high count (Metadata.rateRules.spike). */
export const SPIKE_NOTE = 'Unusually high for this institution; DOE counts crimes in the year reported.'

/** What the spike flag means, from rules.spike */
export function spikeDetail(rules: RateRules | null | undefined): string {
  const s = rules?.spike
  if (!s) return ''
  return `The count is at least ${s.minCount}, more than ${s.factor} times the median of the institution's counts ` +
    `in its other years with figures (at least ${s.minOtherYears}; a year without an incident counts as 0) and more ` +
    `than ${s.maxFactor} times the largest of them, ` +
    `and a negative binomial count with that median as its mean (and the overdispersion of the rate's interval) ` +
    `reaches it with a probability under ${s.p}. The flag does not take a rate out of rate rankings.`
}

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
  return `Its ${inst.year} rate also counts ${joinAnd(parts)}, whose campus figures count under this institution that year (a merger, a renumbering or a shared campus).`
}

/**
 * Why an institution-year has no rate or is in no rate ranking, as a plain
 * sentence, or null when it is listed (or `rules` are not loaded yet).
 */
export function rateNote(inst: InstitutionRate | null, rules: RateRules | null | undefined): string | null {
  if (!inst || inst.rateRanked) return null
  // A reason the pipeline gives (population, merger) comes first
  if (inst.rateExcludedReason) return inst.rateExcludedReason
  if (!rules) return null
  if (inst.fte !== null && inst.fte < rules.minFte) {
    return `Its on-campus FTE is under ${rules.minFte.toLocaleString()}, so rate rankings do not list it.`
  }
  return null
}

/**
 * How the on-campus FTE was found, as a plain sentence: from NCES's FTE and
 * its share of students studying exclusively online (in a pandemic year of
 * rules.onlineShareYear, which fall's share), or null.
 */
export function onlineNote(inst: InstitutionRate | null, rules: RateRules | null | undefined): string | null {
  if (!inst || inst.online === null || inst.online === 0) return null
  const shareYear = rules?.onlineShareYear?.[String(inst.year)]
  const fall = shareYear !== undefined && inst.onlineYear !== undefined && inst.onlineYear !== inst.year
    ? `in fall ${inst.onlineYear}, before the pandemic (the share used for ${inst.year})`
    : `in fall ${inst.onlineYear ?? inst.year}`
  return `On-campus FTE is estimated from NCES's FTE and the ${inst.online}% of students who studied exclusively ` +
    `online ${fall}: the larger of two estimates (see Rate Rules).`
}

/**
 * Not included in the rate: the institution's campuses abroad and their
 * incidents of the code, or null without a campus abroad that year.
 */
export function abroadNote(inst: InstitutionRate | null): string | null {
  const abroad = inst?.abroad
  if (!inst || !abroad || abroad.campuses <= 0) return null
  const n = abroad.counts?.[inst.code] ?? 0
  const where = `its ${abroad.campuses} ${abroad.campuses === 1 ? 'campus' : 'campuses'} abroad`
  const why = 'NCES fall enrollment leaves out students at branch campuses abroad'
  return n > 0
    ? `Not included: ${fmt(n)} ${n === 1 ? 'incident' : 'incidents'} at ${where}, because ${why}.`
    : `Not included: ${where} (none of these incidents), because ${why}.`
}

/**
 * The institutions of a rankings file's rate view of `code`, in the file's
 * order: ranked (rateRankings), too few incidents (rateUnranked), shown but
 * not ranked or left out by a rule (rateNotRanked), and those with none of
 * the code: `zero` (with a rate of 0) and `excludedZero` (left out by a rule,
 * so no rate). Every institution of the file is in exactly one group.
 */
export interface RateViewGroups {
  ranked: RateEntry[]
  few: RateUnrankedEntry[]
  notRanked: RateNotRankedEntry[]
  zero: { id: number; inst: RateInstitution }[]
  excludedZero: { id: number; inst: RateInstitution }[]
}

export function rateViewGroups(
  data: Pick<RankingsData, 'institutions' | 'rateRankings' | 'rateUnranked' | 'rateNotRanked'>,
  code: string,
  compareNames: (a: string, b: string) => number
): RateViewGroups {
  const ranked = data.rateRankings[code] ?? []
  const few = data.rateUnranked?.[code] ?? []
  const notRanked = data.rateNotRanked?.[code] ?? []
  const listed = new Set([...ranked, ...few, ...notRanked].map((e) => e.id))
  const rest = Object.entries(data.institutions)
    .map(([id, inst]) => ({ id: Number(id), inst }))
    .filter(({ id }) => !listed.has(id))
    .sort((a, b) => compareNames(a.inst.name, b.inst.name) || a.id - b.id)
  return {
    ranked,
    few,
    notRanked,
    zero: rest.filter(({ inst }) => !inst.excluded),
    excludedZero: rest.filter(({ inst }) => !!inst.excluded),
  }
}

/** "all 3 campuses combined" for an institution of more than one campus, else null. */
export function campusesPhrase(campuses: number): string | null {
  return campuses > 1 ? `all ${campuses} campuses combined` : null
}

/**
 * Everything the school page and Compare say about one institution-year
 * rate: its standing, its interval, and the notes to show with it, in
 * reading order (each a plain sentence).
 */
export interface RateSummary {
  standing: RateStanding
  interval: { lo: number; hi: number } | null
  // Where the rate stands (not ranked and why, too few, counts only, not listed)
  status: string | null
  // Other notes: incidents counted or left out, the denominator, spikes
  notes: string[]
  spike: boolean
}

export function rateSummary(inst: InstitutionRate | null, rules: RateRules | null | undefined): RateSummary {
  const standing = rateStanding(inst, rules)
  const interval = inst && inst.rate !== null && inst.fte !== null ? rateInterval(inst.count, inst.fte, inst.code, rules) : null
  const spike = !!inst?.spikes?.includes(inst.code)
  if (!inst) return { standing, interval, status: null, notes: [], spike }
  const ctx: ReasonContext = { count: inst.count, ...noteCounts(inst), fteUncertain: inst.fteUncertain, pooled: inst.pooledWith }
  const reasons = standing.kind === 'notRanked' ? standing.reasons : []
  const minCount = rules?.minCount ?? 20
  let status: string | null = null
  switch (standing.kind) {
    case 'excluded':
    case 'unlisted':
      status = rateNote(inst, rules)
      break
    case 'outside':
      status = 'Rate rankings list institutions in the 50 states, the District of Columbia, Puerto Rico and the ' +
        'U.S. Virgin Islands, so they do not list this one. The rate is shown with its interval.'
      break
    case 'countsOnly':
      status = 'This offense is too rare nationally for rates to be compared, so rate rankings leave it out (counts only).'
      break
    case 'notRanked':
      status = notRankedSentence(standing.reasons, ctx, rules)
      break
    case 'few':
      status = `${fmt(inst.count)} ${inst.count === 1 ? 'incident is' : 'incidents are'} too few to rank by rate ` +
        `(rate rankings rank institutions with at least ${minCount}); the rate is shown with its interval.`
      break
    case 'ranked':
      status = `Ranked in rate rankings (at least ${minCount} incidents, and no reason not to rank it).`
      break
  }
  const notes: string[] = []
  if (standing.kind !== 'excluded' && standing.kind !== 'noRate') {
    notes.push(...countNotes(ctx, reasons, rules))
    const abroad = abroadNote(inst)
    if (abroad) notes.push(abroad)
    // The denominator: an uncertain on-campus FTE not already given as the reason
    if (inst.fteUncertain && !reasons.includes('online')) {
      const text = fteUncertainText(inst.fteUncertain, inst.pooledWith, rules)
      notes.push(`Its on-campus FTE is uncertain: ${text}.`)
    }
    const pooled = pooledNote(inst)
    if (pooled) notes.push(pooled)
  }
  return { standing, interval, status, notes, spike }
}
