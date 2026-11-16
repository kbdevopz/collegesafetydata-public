/**
 * The 3-year on-campus rates, as the pipeline publishes them in rates/*.json
 * (etl/rates.py): every figure, verdict, list position and range is read
 * from the data and never recomputed here. This module only names windows,
 * formats numbers and turns the published fields into plain sentences.
 *
 * A rate is the on-campus incidents of an institution (all its campuses in
 * the United States) in a window's three years, per 10,000 of its on-campus
 * students (FTE) summed over the same years. Rates, interval bounds and the
 * national and peer rates are published to 2 decimals and shown that way.
 */

import type {
  AbsentYear, FteUncertain, InstitutionFlag, InstitutionWindow, Metadata, NamedInstitution, NotRatedReason, PooledInstitution,
  RateEntryFields, RateFlag, RateRules, RateRule, SchoolProfile, SharedSite, SharedSiteFigure, SharedSiteNotes, Verdict,
} from './types'
import {
  COUNTS_ONLY_REASONS, OFFENSE_NOUNS, RATE_CODE_LABELS, RATE_CODE_ORDER, RATE_CODE_PHRASES, SHOW_POINT_POSITION,
  VERDICT_LABELS, VERDICT_SHORT,
} from './rateDisplay'
import { formatNumber } from './format'
import { noneOfPhrase } from './selection'

// =============================================================================
// NCES FTE of a school's institution (count views)
// =============================================================================

type FteSource = Pick<SchoolProfile, 'fteByYear'> | null | undefined

/** FTE for one year from the profile's fteByYear, or null when that year has none above 0. */
export function fteFor(profile: FteSource, year: number | null | undefined): number | null {
  if (!profile || year === null || year === undefined || !Number.isFinite(year)) return null
  const value = profile.fteByYear?.[String(year)]
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

/** The newest year in fteByYear and its FTE, or null when there is none above 0. */
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

// =============================================================================
// Numbers and words
// =============================================================================

export const fmtInt = (n: number) => formatNumber(n)

/** A published rate (2 decimals) as published: "31.01", "1,204.50" */
export function fmtRate(x: number): string {
  return formatNumber(x, 2)
}

/** "1st", "2nd", "3rd", "11th", "12th", "21st", "101st", "111th" */
export function ordinal(n: number): string {
  const mod100 = n % 100
  const suffix = mod100 >= 11 && mod100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${fmtInt(n)}${suffix}`
}

/** "A", "A and B", "A, B and C" */
export function joinAnd(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0] ?? ''
}

/** "1 rape" / "3 rapes" for an offense code */
export function offenseCount(n: number, offense: string): string {
  const [one, many] = OFFENSE_NOUNS[offense] ?? [offense.replace(/_/g, ' '), `${offense.replace(/_/g, ' ')} incidents`]
  return `${fmtInt(n)} ${n === 1 ? one : many}`
}

/** "25%": a ratio [a, b] as a percentage of a / b (or of a / b - 1 with `above`). */
export function ratioPercent(ratio: [number, number], above = false): string {
  const value = above ? ratio[0] / ratio[1] - 1 : ratio[0] / ratio[1]
  return `${Math.round(value * 100)}%`
}

/** "95" from RateRules.ciLevel */
export function levelPct(rules: RateRules | null | undefined): number {
  return Math.round((rules?.ciLevel ?? 0.95) * 100)
}

/** "1 in 40": the chance of each one-sided verdict for an institution at the national rate */
export function oneSidedChance(rules: RateRules | null | undefined): string {
  const level = rules?.ciLevel ?? 0.95
  return `1 in ${Math.round(2 / (1 - level))}`
}

// =============================================================================
// Windows and codes
// =============================================================================

export const windowKey = (w: readonly [number, number]) => `${w[0]}-${w[1]}`

/** The windows' keys ("2015-2017", ...), oldest first */
export function windowKeys(rules: RateRules | null | undefined): string[] {
  return (rules?.windows ?? []).map(windowKey)
}

export function latestWindowKey(rules: RateRules | null | undefined): string | null {
  const keys = windowKeys(rules)
  return keys.length > 0 ? keys[keys.length - 1] : null
}

/** [first year, last year] of a window key */
export function windowYears(key: string): [number, number] {
  const [a, b] = key.split('-').map(Number)
  return [a, b]
}

/** "2022-2024" written for reading: "2022–2024" */
export function windowLabel(key: string): string {
  const [a, b] = windowYears(key)
  return `${a}–${b}`
}

/**
 * The window to show: `param` when it is a window; else the window ending
 * in `year` (a year chosen in the count view); else the latest.
 */
export function chooseWindow(rules: RateRules | null | undefined, param: string | null, year?: number | null): string | null {
  const keys = windowKeys(rules)
  if (param && keys.includes(param)) return param
  if (year) {
    const ending = keys.find((k) => windowYears(k)[1] === year)
    if (ending) return ending
  }
  return keys.length > 0 ? keys[keys.length - 1] : null
}

/** The rate codes in display order (those in RateRules.codes) */
export function rateCodes(rules: RateRules | null | undefined): string[] {
  const codes = Object.keys(rules?.codes ?? {})
  return [...RATE_CODE_ORDER.filter((c) => codes.includes(c)), ...codes.filter((c) => !(RATE_CODE_ORDER as readonly string[]).includes(c))]
}

export function isListCode(code: string, rules: RateRules | null | undefined): boolean {
  return !!rules?.lists?.codes?.includes(code)
}

export function rateCodeLabel(code: string): string {
  return RATE_CODE_LABELS[code] ?? code.replace(/_/g, ' ')
}

export function rateCodePhrase(code: string): string {
  return RATE_CODE_PHRASES[code] ?? `${code.replace(/_/g, ' ')} incidents`
}

/**
 * The rate code for a count selection (lib/selection.ts code): criminal
 * becomes criminal offenses except motor-vehicle theft, property becomes
 * burglary; a rate code stays; anything else has no rate (null).
 */
export function rateCodeForSelection(code: string, rules: RateRules | null | undefined): string | null {
  const codes = rules?.codes ?? {}
  if (code === 'criminal') return 'criminal_xmvt' in codes ? 'criminal_xmvt' : null
  if (code === 'property') return 'burglary' in codes ? 'burglary' : null
  return code in codes ? code : null
}

/** Why a count code has no rate, in one sentence */
export function countsOnlyReason(code: string, label?: string): string {
  return COUNTS_ONLY_REASONS[code] ?? `${label ?? code.replace(/_/g, ' ')} has no rate on this site; it is shown as counts only.`
}

// =============================================================================
// Sentences about one rated institution, window and code
// =============================================================================

/**
 * "12th; could be anywhere from 3rd to 61st of 206", or without the point
 * position (SHOW_POINT_POSITION false) "anywhere from 3rd to 61st of 206".
 * A range of one position is given as that range: "1st of 6 (its range is
 * this one position)".
 */
export function positionText(position: number, lo: number, hi: number, n: number): string {
  if (lo === hi) {
    return SHOW_POINT_POSITION
      ? `${ordinal(position)} of ${fmtInt(n)}; the range is that position alone`
      : `${ordinal(lo)} of ${fmtInt(n)} (its range is this one position)`
  }
  const range = `anywhere from ${ordinal(lo)} to ${ordinal(hi)} of ${fmtInt(n)}`
  return SHOW_POINT_POSITION ? `${ordinal(position)}; could be ${range}` : range
}

/** "Among four-year, primarily residential institutions on the list: …", or null when not in a type list */
export function typePositionText(e: RateEntryFields, peerType: string, rules: RateRules | null | undefined): string | null {
  if (!e.listed || e.typePosition === undefined || e.typeRankLo === undefined || e.typeRankHi === undefined || !e.typeN) return null
  return `Among the ${fmtInt(e.typeN)} ${peerLabel(peerType, rules).toLowerCase()} institutions on the list: ` +
    positionText(e.typePosition, e.typeRankLo, e.typeRankHi, e.typeN)
}

/** The list position of an entry, national or within its state, or null when not listed there */
export function entryPosition(e: RateEntryFields, listN: number | null, state = false): string | null {
  if (!e.listed) return null
  if (state) {
    if (e.statePosition === undefined || e.stateRankLo === undefined || e.stateRankHi === undefined || !e.stateN) return null
    return positionText(e.statePosition, e.stateRankLo, e.stateRankHi, e.stateN)
  }
  if (e.position === undefined || e.rankLo === undefined || e.rankHi === undefined || listN === null) return null
  return positionText(e.position, e.rankLo, e.rankHi, listN)
}

/**
 * A figure published to 2 decimals and to 4 (`x4`): to 4 decimals when
 * `digits` is 4 and the 4-decimal figure is published, else to 2.
 */
export function fmtRateAt(x: number, x4: number | null | undefined, digits: 2 | 4): string {
  return digits === 4 && x4 !== undefined && x4 !== null ? formatNumber(x4, 4) : fmtRate(x)
}

/**
 * The decimals at which an interval and the rate it is compared with are
 * shown: 2, unless the deciding end of the interval (the upper for "below",
 * the lower for "above") prints the same as that rate to 2 decimals, and
 * both are published to 4; then 4, so that the reader sees them differ.
 */
export function tieDigits(
  e: Pick<RateEntryFields, 'lo' | 'hi' | 'lo4' | 'hi4'>, verdict: Verdict | null, ref: number | null,
  ref4: number | null | undefined,
): 2 | 4 {
  if (ref === null || (verdict !== 'below' && verdict !== 'above')) return 2
  const end = verdict === 'below' ? e.hi : e.lo
  const end4 = verdict === 'below' ? e.hi4 : e.lo4
  if (fmtRate(end) !== fmtRate(ref)) return 2
  return end4 !== undefined && ref4 !== undefined && ref4 !== null ? 4 : 2
}

export function intervalSentence(
  e: Pick<RateEntryFields, 'lo' | 'hi' | 'lo4' | 'hi4'>, rules: RateRules | null | undefined, digits: 2 | 4 = 2,
): string {
  const shown = `${fmtRateAt(e.lo, e.lo4, digits)} to ${fmtRateAt(e.hi, e.hi4, digits)}${digits === 4 ? ' (to 4 decimals)' : ''}`
  return `${levelPct(rules)}% interval ${shown}. This range allows for how much the yearly counts vary: as much as ` +
    "is usual for an institution with this many incidents, or as much as this institution's own counts varied " +
    'from year to year when that is more. It does not allow for differences in how institutions record and ' +
    'report incidents.'
}

/** When the interval rests on the institution's own year-to-year spread (phiFrom "years"), with its yearly counts */
export function spreadSentence(e: Pick<RateEntryFields, 'phiFrom'>, nByYear: Record<string, number> | undefined): string | null {
  if (e.phiFrom !== 'years') return null
  const years = Object.keys(nByYear ?? {}).sort()
  const counts = years.length > 0 ? ` (${joinAnd(years.map((y) => `${fmtInt(nByYear?.[y] ?? 0)} in ${y}`))})` : ''
  return `Its yearly counts${counts} vary more than is usual for an institution with this many incidents, so the ` +
    'range is based on their own spread and is wider.'
}

/** What the national rate is and what "above" means */
export function nationalSentence(
  natl: number, key: string, rules: RateRules | null | undefined, natl4?: number | null, digits: 2 | 4 = 2,
): string {
  const chance = oneSidedChance(rules)
  return `National rate ${fmtRateAt(natl, natl4, digits)}${digits === 4 ? ' (to 4 decimals)' : ''} for ${windowLabel(key)}: the on-campus incidents of all rated ` +
    'institutions whose on-campus student count is certain, per 10,000 of their on-campus students a year. ' +
    `"Above" means the whole ${levelPct(rules)}% interval is above the national rate. If the intervals have their ` +
    `intended coverage, about ${chance} institutions whose underlying rate equals the national rate are shown as ` +
    `above by chance, and ${chance} as below.`
}

export function peerLabel(peerType: string, rules: RateRules | null | undefined): string {
  return rules?.peerTypes?.[peerType]?.label ?? peerType.replace(/_/g, ' ')
}

/** "Compared with Four-year, highly residential institutions (12.55): above." */
export function peerSentence(
  e: Pick<RateEntryFields, 'peerVerdict' | 'peerVerdictLargerFte' | 'peerVerdictSmallerFte'>,
  peerType: string, peerRate: number | null, rules: RateRules | null | undefined,
  peerRate4?: number | null, digits: 2 | 4 = 2,
): string | null {
  // "withheld": the shared-site sentence says why there is no comparison
  if (e.peerVerdict === null || e.peerVerdict === 'withheld' || peerRate === null) return null
  const label = peerLabel(peerType, rules)
  let verdict: string = VERDICT_SHORT[e.peerVerdict]
  if (e.peerVerdict === 'undetermined' && e.peerVerdictLargerFte && e.peerVerdictSmallerFte) {
    verdict += ` (${VERDICT_SHORT[e.peerVerdictLargerFte]} with the larger student count, ` +
      `${VERDICT_SHORT[e.peerVerdictSmallerFte]} with the smaller)`
  }
  const rate = `${fmtRateAt(peerRate, peerRate4, digits)}${digits === 4 ? ', to 4 decimals' : ''}`
  return `Compared with institutions of its type (${label}; their rate ${rate}): ${verdict}.`
}

/** One sentence on why the national and peer comparisons differ, or null when they agree */
export function differSentence(
  verdict: Verdict, peerVerdict: Verdict | null, natl: number, peerType: string, peerRate: number | null,
  rules: RateRules | null | undefined,
): string | null {
  if (peerVerdict === null || peerRate === null || peerVerdict === verdict) return null
  if (verdict === 'undetermined' || peerVerdict === 'undetermined') return null
  if (verdict === 'withheld' || peerVerdict === 'withheld') return null
  const label = peerLabel(peerType, rules)
  const direction = peerRate > natl ? 'higher' : peerRate < natl ? 'lower' : 'the same as'
  return `The two comparisons differ because institutions of its type (${label}) together have an on-campus ` +
    `rate of ${fmtRate(peerRate)}, ${direction}${direction === 'the same as' ? '' : ' than'} the national ` +
    `${fmtRate(natl)}.`
}

export function otherLocationsSentence(nNoncampus: number, nPublic: number): string | null {
  const more = nNoncampus + nPublic
  if (more <= 0) return null
  return `This rate counts only incidents on campus. ${fmtInt(more)} more ${more === 1 ? 'was' : 'were'} reported ` +
    `in these years at non-campus locations (${fmtInt(nNoncampus)}) or on public property in or next to campus ` +
    `(${fmtInt(nPublic)}).`
}

const GEO_PHRASES: Record<string, string> = {
  'On-campus': 'on campus',
  'Non-campus': 'at non-campus locations',
  'Public property': 'on public property',
}

/** An unusual-year flag in words (`usual` is the median of the other years) */
export function flagSentence(f: RateFlag | InstitutionFlag, geo = 'On-campus'): string {
  const where = GEO_PHRASES[('geo' in f && f.geo) || geo] ?? 'on campus'
  return `${f.year}: ${offenseCount(f.count, f.offense)} reported ${where}, compared with a median of ` +
    `${formatNumber(f.usual)} a year in this institution's other years. DOE counts each incident in ` +
    'the year it is reported.'
}

/** Why a list-sized institution has no position (notPlaced "unusual_year"), from its flags */
export function notPlacedSentence(e: Pick<RateEntryFields, 'notPlaced' | 'flags'>): string | null {
  if (e.notPlaced !== 'unusual_year') return null
  const flags = (e.flags ?? []).map((f) =>
    `in ${f.year} it reported ${offenseCount(f.count, f.offense)} on campus, against a median of ` +
    `${formatNumber(f.usual)} a year in its other years`)
  const what = flags.length > 0 ? `: ${joinAnd(flags)}` : ': it has an unusual year in this period'
  return `Not placed on the list${what}. An institution with an unusual year in the window is not given a ` +
    "position, so that one year's count does not set its place; its rate and comparisons are shown."
}

/** A hospital next to or inside the main campus whose incidents may be in the figures (hospitalUnresolved) */
export function hospitalNote(h: { name: string; years: number[] } | undefined, windowYearsN = 3, short = false): string | null {
  if (!h) return null
  const when = h.years.length > 0 && h.years.length < windowYearsN ? ` in ${joinAnd(h.years.map(String))}` : ''
  return short
    ? `A hospital adjoins or lies inside its main campus (${h.name}); whether its incidents are in these figures${when} is not established`
    : `A hospital adjoins or lies inside this institution's main campus (${h.name}); whether its incidents are in ` +
      `these figures${when} is not established. If they are, the rate may count incidents involving patients, ` +
      'visitors and hospital staff, who are not students.'
}

export const FLAG_NOTE =
  'Flags never change counts or rates: the rate above includes the flagged year as reported.'

export function withoutFlaggedSentence(v: Verdict): string {
  return 'Counting each flagged year at its median instead, the comparison with the national rate would be: ' +
    `${VERDICT_SHORT[v]}.`
}

/** Names of the institutions whose students are counted with this one in the window's years */
function pooledNames(profile: Pick<SchoolProfile, 'institution'> | null | undefined, years: number[]): string | null {
  const seen = new Map<number, string>()
  for (const y of years) {
    for (const p of profile?.institution?.byYear[String(y)]?.pooledWith ?? []) {
      seen.set(p.id, p.name ?? `institution ${p.id}`)
    }
  }
  return seen.size > 0 ? joinAnd(Array.from(seen.values())) : null
}

/**
 * The sentence for an institution whose on-campus student count is
 * uncertain (why "online"): the two estimates and whether the comparison
 * holds with both.
 */
export function onlineSentence(
  e: RateEntryFields, key: string, profile?: Pick<SchoolProfile, 'institution'> | null,
): string {
  const both = e.fteYearsSmaller !== undefined
    ? `(${fmtInt(e.fteYears)} and ${fmtInt(e.fteYearsSmaller)} student-years)`
    : `(${fmtInt(e.fteYears)} student-years)`
  const pooledOnly = Object.values(e.fteUncertain ?? {}).length > 0 &&
    Object.values(e.fteUncertain ?? {}).every((r) => r === 'pooled')
  const names = pooledOnly ? pooledNames(profile, Object.keys(e.fteUncertain ?? {}).map(Number)) : null
  const because = pooledOnly
    ? ` (because of ${names ?? 'another institution'}, whose students are counted with this institution's)`
    : ''
  if (e.verdict === 'undetermined') {
    if (e.undeterminedReason === 'noSecondEstimate') {
      return `Not determined: NCES's figures give only one estimate of on-campus students${because}.`
    }
    const larger = e.verdictLargerFte ? VERDICT_SHORT[e.verdictLargerFte] : 'unknown'
    const smaller = e.verdictSmallerFte ? VERDICT_SHORT[e.verdictSmallerFte] : 'unknown'
    return `Not determined: NCES's figures give two estimates of on-campus students ${both}${because}. With the ` +
      `larger the comparison with the national rate is "${larger}", with the smaller "${smaller}".`
  }
  return `NCES's figures give two estimates of on-campus students ${both}${because}; the rate uses the larger. ` +
    `The comparison with the national rate (${windowLabel(key)}) is the same with either.`
}

/** Medical-center incidents of an entry (why medical_campus, or a smaller share) */
export function medicalSentence(e: RateEntryFields, listCode: boolean): string | null {
  const m = e.medical ?? 0
  if (m <= 0) return null
  const fact = `${fmtInt(m)} of these ${fmtInt(e.n)} incidents were at a medical-center campus outside its ` +
    'residence halls, whose patients, visitors and staff are not students.'
  if (e.why === 'medical_campus') return listCode ? `Not on the list: ${fact}` : fact
  return fact
}

// =============================================================================
// Shared campus sites: a site where campuses of two or more institutions
// report the same incidents (owner/host, guests, participants; see
// Methodology). The notes are per institution and window.
// =============================================================================

/** "A", "A and B": the names of a shared-site note, or null when it has none */
export function namesOf(xs: NamedInstitution[] | undefined): string | null {
  return xs && xs.length > 0 ? joinAnd(xs.map((x) => x.name)) : null
}

/** "1 in 10" from RateRules.sharedSiteShare */
export function sharedSiteShareText(rules: RateRules | null | undefined): string | null {
  const r = rules?.sharedSiteShare
  return r ? `${fmtInt(r[0])} in ${fmtInt(r[1])}` : null
}

const yearsText = (years: number[]) => joinAnd(years.map(String))

/** "reports" / "report" after a list of names */
const verbS = (xs: NamedInstitution[] | undefined, one: string, many: string) => ((xs?.length ?? 0) > 1 ? many : one)

/** A guest or participant whose comparisons are withheld (verdict "withheld") */
export function isWithheld(e: Pick<RateEntryFields, 'verdict' | 'why'>): boolean {
  return e.verdict === 'withheld' || e.why === 'shared'
}

/**
 * A guest or participant at a shared site (notes.sharedSite, or verdict
 * "withheld"): why its comparisons are withheld, or why it is compared as
 * usual (sharedSite.exempt). Null for an institution that is neither.
 */
export function sharedGuestSentence(
  e: RateEntryFields, notes: SharedSiteNotes, code: string, listCode: boolean, rules: RateRules | null | undefined,
): string | null {
  const site = notes.sharedSite
  const withheld = isWithheld(e)
  if (!site && !withheld) return null
  const others = namesOf(notes.sharedOutWith) ?? 'another institution'
  const when = site && site.years.length > 0 ? `In ${yearsText(site.years)}` : 'In these years'
  const fact = `${when}, this institution shared one or more campus sites with ${others}: the institutions at ` +
    'such a site each report a campus there, covering the same incidents.'
  const sOut = e.sharedOut ?? 0
  const phrase = rateCodePhrase(code)
  const left = sOut > 1
    ? `The ${fmtInt(sOut)} ${phrase} it reported there are not in this rate.`
    : sOut === 1
      ? 'The 1 incident of this kind it reported there is not in this rate.'
      : `It reported no ${phrase} there.`
  const share = sharedSiteShareText(rules) ?? 'the share the rule allows'
  const figs = site?.figures ?? []
  const campuses = new Set(figs.map((f) => f.unitid)).size
  const multiYear = (site?.years.length ?? 0) > 1
  const added = multiYear && campuses > 1
    ? ' (added over its campuses there and those years)'
    : multiYear ? ' (added over those years)' : campuses > 1 ? ' (added over its campuses there)' : ''
  const figure = site && site.students !== null
    ? `Published enrollment figures put its students there, in the programs they count, at ` +
      `${site.upperBound ? 'no more than ' : ''}${fmtInt(site.students)}${added}`
    : null
  const against = `of the ${fmtInt(e.fteYears)} on-campus student-years in this rate`
  const detail = sharedFiguresSentence(site, rules)
  if (!withheld) {
    // Exempt: compared as usual
    return `${fact} ${left} ${figure ?? 'Published enrollment figures put its students there'}: at most ` +
      `${share} ${against}, so it is compared as usual.${detail ? ` ${detail}` : ''}`
  }
  const lead = listCode ? 'Not compared and not on the list.' : 'Not compared.'
  const missing = figs.filter((f) => f.students === null).length
  const campusThere = campuses > 1 ? 'campuses there' : 'campus there'
  const cover = figs.length === 0
    ? `do not cover ${multiYear ? 'all of those years' : 'that year'}`
    : missing === figs.length
      ? `cover none of its ${campusThere} in ${multiYear ? 'those years' : 'that year'}`
      : `cover ${fmtInt(figs.length - missing)} of the ${fmtInt(figs.length)} campus-years concerned, not all ` +
        '(listed below)'
  const why = figure
    ? `${figure}: more than ${share} ${against}${site?.upperBound ? ' (an upper bound: the true number may be smaller, but no figure shows that it is)' : ''}.${detail ? ` ${detail}` : ''}`
    : "Its student count is NCES's figure for the whole institution, so it may include students there, and how " +
      "many is not known: DOE's files give no enrollment per campus, and the published enrollment figures used " +
      `here ${cover}.`
  return `${lead} ${fact} ${left} ${why} So the rate may count students whose incidents it leaves out. It is ` +
    'shown, but not compared with the national rate or with institutions of its type.'
}

/**
 * What kind of figures a guest's student count rests on, in one sentence:
 * how many are upper bounds, how many of those are computed from published
 * class sizes or a cap per class, and how many are another year's figure.
 * Null when every figure is a published count for its own year (or none).
 */
export function sharedFiguresSentence(site: SharedSite | undefined, rules: RateRules | null | undefined): string | null {
  const figs = (site?.figures ?? []).filter((f) => f.students !== null)
  const n = figs.length
  if (n === 0) return null
  const subject = (k: number) => (k === n
    ? (n === 1 ? 'The figure' : n === 2 ? 'Both figures' : `All ${fmtInt(n)} figures`)
    : `${fmtInt(k)} of the ${fmtInt(n)} figures`)
  const ub = figs.filter((f) => f.upperBound).length
  const der = figs.filter((f) => f.derived).length
  const other = figs.filter((f) => f.figureYear !== null && f.figureYear !== f.year).length
  const clauses: string[] = []
  if (ub > 0) {
    const how = 'computed from published class sizes or a cap per class'
    const derived = der === 0 ? '' : der === ub ? (ub === 1 ? `, ${how}` : `, all ${how}`) : `, ${fmtInt(der)} of them ${how}`
    clauses.push(`${subject(ub)} ${ub === 1 ? 'is an upper bound' : 'are upper bounds'}${derived}`)
  }
  if (other > 0) {
    const k = rules?.sharedSiteFigureYears
    const within = k !== undefined ? `, at most ${fmtInt(k)} ${k === 1 ? 'year' : 'years'} away,` : ''
    const subj = clauses.length > 0 ? subject(other).replace(/^(The figure|Both|All)/, (m) => m.toLowerCase()) : subject(other)
    clauses.push(`${subj} ${other === 1 ? 'is' : 'are'} for another year${within} used because the year ` +
      `${other === 1 ? 'it stands for has' : 'each stands for has'} no figure of its own`)
  }
  if (clauses.length === 0) return null
  return `${clauses.join('; ')}.${n > 1 ? " Each year's figures are listed below." : ''}`
}

/** One site campus and year's figure in words: "at most 462 (computed from …), the figure for 2022" */
export function sharedFigureText(f: SharedSiteFigure): string {
  if (f.students === null) return 'no published figure'
  const kind = f.derived
    ? 'an upper bound computed from published class sizes or a cap per class'
    : f.upperBound ? 'a published upper bound' : 'a published count'
  const year = f.figureYear !== null && f.figureYear !== f.year
    ? `; it is the figure for ${f.figureYear}, used because ${f.year} has none`
    : ''
  return `${f.upperBound ? 'at most ' : ''}${fmtInt(f.students)} (${kind}${year})`
}

/** A host of shared sites (notes.sharedInWith): their incidents are in its rate, once */
export function sharedHostSentence(e: RateEntryFields, notes: SharedSiteNotes, code: string): string | null {
  const others = namesOf(notes.sharedInWith)
  if (!others) return null
  const sIn = e.sharedIn ?? 0
  const phrase = rateCodePhrase(code)
  const fact = `In these years, this institution shared one or more of its campus sites with ${others}, which ` +
    `also ${verbS(notes.sharedInWith, 'reports', 'report')} a campus there, covering the same incidents.`
  if (sIn <= 0) return `${fact} It reported no ${phrase} there.`
  if (sIn === e.n) {
    return sIn === 1
      ? `${fact} The 1 incident of this kind in this rate was reported there; it is counted here, once.`
      : `${fact} All ${fmtInt(sIn)} ${phrase} in this rate were reported there; they are counted here, once.`
  }
  return `${fact} ${fmtInt(sIn)} of these ${fmtInt(e.n)} ${phrase} ${sIn === 1 ? 'was' : 'were'} reported there; ` +
    `${sIn === 1 ? 'it is' : 'they are'} counted here, once.`
}

/** An owner whose rate adds the students of institutions on its campus site (notes.coLocated) */
export function coLocatedSentence(notes: SharedSiteNotes): string | null {
  const others = namesOf(notes.coLocated)
  if (!others) return null
  const many = (notes.coLocated?.length ?? 0) > 1
  return `This rate includes the students of ${others}, in the years when ${many ? 'they' : 'it'} reported a ` +
    'campus at a site shared with this institution, covering the same incidents.'
}

/** Short forms of the shared-site sentences, for list rows */
export function sharedShortNotes(e: RateEntryFields, notes: SharedSiteNotes, rules: RateRules | null | undefined): string[] {
  const out: string[] = []
  const guestOf = namesOf(notes.sharedOutWith) ?? 'another institution'
  const when = notes.sharedSite?.years.length ? `in ${yearsText(notes.sharedSite.years)} ` : ''
  if (isWithheld(e)) {
    out.push(`Not compared: ${when}it shared one or more campus sites with ${guestOf}, and the rate may count ` +
      'students there whose incidents it leaves out')
  } else if (notes.sharedSite?.exempt) {
    const share = sharedSiteShareText(rules) ?? 'the share the rule allows'
    out.push(`Compared as usual: ${when}it shared one or more campus sites with ${guestOf}, and published figures ` +
      `put its students there, in the programs they count, at most ${share} of its student-years`)
  }
  const host = namesOf(notes.sharedInWith)
  if (host) {
    const sIn = e.sharedIn ?? 0
    out.push(sIn > 0
      ? `${fmtInt(sIn)} of these at sites shared with ${host}; counted here, once`
      : `Shares campus sites with ${host}; none of these reported there`)
  }
  const co = namesOf(notes.coLocated)
  if (co) {
    out.push(`Includes the students of ${co}, which ${verbS(notes.coLocated, 'reports', 'report')} a campus at a ` +
      'site it shares')
  }
  return out
}

/** About how many on-campus students the list needs: student-years for E = minExpected, a year, to 100 */
export function listMinStudents(minFteYears: number, rules: RateRules | null | undefined): number {
  const years = rules?.windowYears ?? 3
  return Math.round(minFteYears / years / 100) * 100
}

export function notListedSentence(minFteYears: number | undefined, rules: RateRules | null | undefined): string {
  const minExpected = rules?.lists?.minExpected ?? 20
  const fmin = minFteYears !== undefined ? ` (the list needs about ${fmtInt(listMinStudents(minFteYears, rules))} or more on-campus students)` : ''
  return `Not on the list: fewer than ${minExpected} incidents expected at the national rate${fmin}.`
}

/** The composition of a violent or criminal_xmvt count */
export function compositionSentence(code: string, composition: Record<string, number> | undefined, n: number, key: string): string | null {
  if (!composition) return null
  if (code === 'violent') {
    const order = ['rape', 'aggravated_assault', 'robbery', 'murder']
    const parts = order.filter((o) => composition[o] !== undefined).map((o) => offenseCount(composition[o], o))
    const lead = 'Violent crimes here are murder, rape, robbery and aggravated assault.'
    return n > 0 && parts.length > 0 ? `${lead} By offense: ${joinAnd(parts)}.` : lead
  }
  if (code === 'criminal_xmvt' && composition.motor_vehicle_theft !== undefined) {
    return 'Motor-vehicle theft is shown as counts only and is not in this rate: ' +
      `${offenseCount(composition.motor_vehicle_theft, 'motor_vehicle_theft')} on campus here in ${windowLabel(key)}.`
  }
  return null
}

/** National composition from a window file, as shares of its on-campus count */
export function nationalCompositionSentence(
  code: string, composition: Record<string, number> | undefined, key: string, share?: Record<string, number>,
): string | null {
  if (!composition) return null
  if (code === 'violent') {
    const total = Object.values(composition).reduce((a, b) => a + b, 0)
    if (total <= 0) return null
    // The published shares (compositionShare, 4 decimals) as percentages to
    // 2 decimals, so that they are not rounded twice; else from the counts
    const pct = (o: string) => `${formatNumber(share?.[o] !== undefined ? share[o] * 100 : (composition[o] ?? 0) / total * 100, 2)}%`
    return 'Violent crimes are murder, rape, robbery and aggravated assault. Of the ' +
      `${fmtInt(total)} on-campus violent crimes counted in the national rate for ${windowLabel(key)}, ${pct('rape')} ` +
      `are reported rapes, ${pct('aggravated_assault')} aggravated assaults, ${pct('robbery')} robberies and ` +
      `${pct('murder')} murders.`
  }
  if (code === 'criminal_xmvt' && composition.motor_vehicle_theft !== undefined) {
    return 'Motor-vehicle theft is shown as counts only and is not in this rate ' +
      `(${fmtInt(composition.motor_vehicle_theft)} on campus at the institutions in the national rate in ${windowLabel(key)}).`
  }
  return null
}

// =============================================================================
// Institutions and years without a rate
// =============================================================================

export function scopeSentence(): string {
  return 'Not rated: rates cover institutions in the 50 states, the District of Columbia, Puerto Rico and the ' +
    'U.S. Virgin Islands.'
}

type StatusProfile = Pick<SchoolProfile, 'institution'>

/**
 * Why an institution has no figures of its own in a data year, from its
 * rates file's absentYears (etl/rates.py, absent_year), as a clause after
 * "in <years>"; without a reason in the file, only that it has none.
 */
export function absentYearClause(a: AbsentYear | undefined): string {
  if (!a) return "DOE's data has no figures of its own for it"
  if (a.reason === 'notReported') return "DOE's data has no figures for any of its campuses"
  const names = Array.from(new Set(a.under.map((h) => h.name)))
  return `the figures DOE publishes for it count under ${a.under.length > 1 ? 'campuses' : 'a campus'} of ` +
    joinAnd(names)
}

/** The same, short (a table cell) */
export function absentYearShort(a: AbsentYear | undefined): string {
  if (!a) return 'No figures of its own'
  if (a.reason === 'notReported') return "Not in DOE's data"
  return `Figures count under ${joinAnd(Array.from(new Set(a.under.map((h) => h.name))))}`
}

/**
 * Why a window has no rate when the institution has no figures of its own in
 * some of its years (`present` lists the years it has them; none when the
 * institution file has no status for the window): each such year's reason,
 * from the rates file's absentYears, with the years that share it. A year
 * without figures of its own is one in which none of its campuses has
 * figures in DOE's data, or one in which the figures DOE publishes for each
 * of its campuses all count under another institution's campus.
 */
export function missingYearsSentence(
  key: string, present: number[], rules: RateRules | null | undefined,
  absent: Record<string, AbsentYear> | undefined,
): string {
  const [y0, y1] = windowYears(key)
  const missing = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i)
    .filter((y) => !present.includes(y) && !(rules?.skipYears ?? []).includes(y))
  const groups = new Map<string, number[]>()
  for (const y of missing) {
    const clause = absentYearClause(absent?.[String(y)])
    groups.set(clause, [...(groups.get(clause) ?? []), y])
  }
  const parts = Array.from(groups.entries()).map(([clause, ys]) => `in ${joinAnd(ys.map(String))} ${clause}`)
  return `Not rated for ${windowLabel(key)}: ${parts.join('; ')}.`
}

/** Why a window has no rate for this institution, or null when it is rated */
export function windowStatusSentence(
  w: InstitutionWindow, key: string, rules: RateRules | null | undefined,
  profile: StatusProfile | null | undefined, absent: Record<string, AbsentYear> | undefined,
): string | null {
  const minFte = fmtInt(rules?.minFte ?? 1000)
  switch (w.status) {
    case 'rated':
      return null
    case 'missingYears':
      return missingYearsSentence(key, w.years, rules, absent)
    case 'scope':
      return scopeSentence()
    case 'size': {
      const years = Object.entries(w.fteByYear)
        .map(([y, f]) => `${y}: ${f === null ? 'no figure' : fmtInt(f)}`)
      return `Not rated for ${windowLabel(key)}: fewer than ${minFte} on-campus students in at least one year ` +
        `(${years.join('; ')}).`
    }
    case 'excluded': {
      // Each ruled year's reason (the school file's text, else the rule's),
      // with the years that share it
      const groups = new Map<string, string[]>()
      for (const y of Object.keys(w.rules).sort()) {
        const own = profile?.institution?.byYear[y]?.rateExcludedReason
        const text = own ?? `${ruleText(w.rules[y]).charAt(0).toUpperCase()}${ruleText(w.rules[y]).slice(1)}`
        groups.set(text, [...(groups.get(text) ?? []), y])
      }
      const parts = Array.from(groups.entries())
        .map(([text, ys]) => `${ys.length === 1 ? `In ${ys[0]}` : `In each of ${joinAnd(ys)}`}: ${text}`)
      return `Not rated for ${windowLabel(key)}. ${parts.join(' ')}`
    }
  }
}

/** A population rule in words, when the school file gives no reason */
export function ruleText(rule: RateRule | undefined): string {
  switch (rule) {
    case 'hospital':
      return 'IPEDS reports that it has a hospital, whose patients, visitors and staff are not students.'
    case 'medical':
      return 'an edition of its Carnegie classification codes it as a special-focus medical school or research ' +
        'institution.'
    case 'listed':
      return 'it is on the reviewed list of institutions whose figures count many people its enrollment does not ' +
        'count.'
    case 'merger':
    case 'family':
      return 'a merger or renumbering means its incidents and enrollment may not cover the same campuses.'
    case 'shared_pooled':
      return "its main campus is shared with another institution, whose rate includes this institution's students " +
        "and the campus's incidents."
    case 'shared_campus':
      return "its main campus is shared with other institutions, and the campus's incidents cannot be assigned to " +
        "one institution's students."
    default:
      return 'a population rule leaves it out.'
  }
}

/** Why a single year has no rate, short (chart and table) */
export function notRatedYearText(reason: NotRatedReason | undefined, rules: RateRules | null | undefined, excluded?: string): string {
  switch (reason) {
    case 'skippedYear':
      return "Not shown: that year's student counts do not measure who was on campus"
    case 'size':
      // A small institution can also be under a population rule that year
      return `Fewer than ${fmtInt(rules?.minFte ?? 1000)} on-campus students${excluded ? `. ${excluded}` : ''}`
    case 'scope':
      return 'Outside the states and territories rates cover'
    case 'excluded':
      return excluded ?? 'Left out by a population rule'
    default:
      return 'No rate'
  }
}

/** Why a single year has no rate, in a few words (a table cell; the note gives notRatedYearText) */
export function notRatedYearShort(reason: NotRatedReason | undefined, rules: RateRules | null | undefined): string {
  switch (reason) {
    case 'skippedYear':
      return 'Year left out of rates'
    case 'size':
      return `Under ${fmtInt(rules?.minFte ?? 1000)} on-campus students`
    case 'scope':
      return 'Outside the area rates cover'
    case 'excluded':
      return 'Left out by a population rule'
    default:
      return 'No rate'
  }
}

/**
 * For an institution without a rates file: one sentence on why it has no
 * rate, from its years' notRated reasons. `yearsListed`: the page lists
 * each year's reason after it, so the sentence need not repeat them.
 */
export function noRatesSentence(
  profile: Pick<SchoolProfile, 'institution' | 'yearlyTotals'> | null | undefined, rules: RateRules | null | undefined,
  yearsListed = false,
): string {
  const byYear = Object.entries(profile?.institution?.byYear ?? {}).sort(([a], [b]) => a.localeCompare(b))
  if (byYear.length === 0) {
    // The institution has figures of its own in none of the years this
    // campus is in DOE's data: each of those years' figures counts under
    // another institution's campus
    const ys = (profile?.yearlyTotals ?? []).map((t) => t.year).sort((a, b) => a - b)
    if (ys.length > 0) {
      return `No rate: it has no figures of its own in DOE's data. In ${joinAnd(ys.map(String))} the figures DOE ` +
        'publishes for it count under another institution\'s campus.'
    }
    return 'No rate: it has no figures of its own in DOE\'s data.'
  }
  const reasons = new Set(byYear.map(([, y]) => y.notRated).filter((r) => r && r !== 'skippedYear'))
  // Each year's reason in words, with the years that share it
  const groups = (pick: (v: (typeof byYear)[number][1]) => string | null) => {
    const m = new Map<string, string[]>()
    for (const [y, v] of byYear) {
      const t = pick(v)
      if (t) m.set(t, [...(m.get(t) ?? []), y])
    }
    return Array.from(m.entries())
      .map(([t, ys]) => ` ${ys.length === 1 ? `In ${ys[0]}` : `In each of ${joinAnd(ys)}`}: ${t}${t.endsWith('.') ? '' : '.'}`)
      .join('')
  }
  if (reasons.size === 1 && reasons.has('size')) {
    // A population rule can apply in some of those years too: name it
    const also = yearsListed ? '' : groups((v) => v.rateExcludedReason ?? null)
    return `No rate: fewer than ${fmtInt(rules?.minFte ?? 1000)} on-campus students in every year.${also}`
  }
  if (reasons.size === 1 && reasons.has('scope')) return `No rate. ${scopeSentence()}`
  if (yearsListed) return 'No rate in any window. Each year\'s reason is below.'
  return `No rate in any window.${groups((v) => (v.rated ? null : notRatedYearText(v.notRated, rules, v.rateExcludedReason)))}`
}
/**
 * Not included in counts or rates: the institution's campuses abroad in a
 * year and their incidents of `code`, or null.
 */
export function abroadNote(abroad: { campuses: number; counts: Record<string, number> } | undefined, code: string, year: number): string | null {
  if (!abroad || abroad.campuses <= 0) return null
  const n = abroad.counts?.[code] ?? 0
  const where = `its ${abroad.campuses} ${abroad.campuses === 1 ? 'campus' : 'campuses'} abroad`
  const what = n > 0
    ? `${fmtInt(n)} ${n === 1 ? 'incident' : 'incidents'} at ${where} ${n === 1 ? 'is' : 'are'} not included`
    : `${where} ${abroad.campuses === 1 ? 'is' : 'are'} not included (no incident of this kind was reported there)`
  return `${year}: ${what}, because NCES fall enrollment leaves out students at branch campuses abroad.`
}

/** Pooled partners of an institution-year, for the denominator note */
export function pooledNote(pooled: PooledInstitution[] | undefined, year: number): string | null {
  if (!pooled || pooled.length === 0) return null
  const parts = pooled.map((p) => `the ${fmtInt(p.fte)} on-campus students of ${p.name ?? `institution ${p.id}`}`)
  return `${year}: the denominator also counts ${joinAnd(parts)}, whose campus figures count under this ` +
    'institution that year (a merger, a renumbering or a shared campus).'
}

/** The two on-campus FTE estimates of a year with an uncertain count */
export function fteUncertainNote(fu: FteUncertain | undefined, year: number): string | null {
  if (!fu) return null
  const second = fu.partTimeFirst === null ? 'a second estimate cannot be computed' : `${fmtInt(fu.partTimeFirst)}`
  const own = fu.reason === 'pooled'
    ? ' Only the estimates of an institution whose students are counted with this one differ.'
    : ''
  return `${year}: two estimates of on-campus students from NCES's figures, ${fmtInt(fu.share)} and ${second}.${own}`
}

type CountFlagMetadata = Pick<Metadata, 'rateRules' | 'offenses'> | null

/**
 * The two figures of a count flagged very high for its institution's size:
 * its count per 10,000 of the institution's FTE and the reference rate it is
 * more than `factor` times. A figure of 1,000 or more gets at most one
 * decimal (the count per 10,000 none); more decimals are used only where the
 * rounded figures would not show the first as more than `factor` times the
 * second.
 */
function countFlagFigures(perTenK: number, reference: number | undefined, factor: number): { value: string; ref: string | null } {
  if (reference === undefined) return { value: formatNumber(perTenK, perTenK >= 1000 ? 0 : 1), ref: null }
  const tries: [number, number][] = [[perTenK >= 1000 ? 0 : 1, reference >= 1000 ? 1 : 2], [1, 2], [2, 2], [4, 4]]
  const shown = (x: number, d: number) => Number(x.toFixed(d))
  const [dv, dr] = tries.find(([v, r]) => shown(perTenK, v) > factor * shown(reference, r)) ?? tries[tries.length - 1]
  return { value: formatNumber(perTenK, dv), ref: formatNumber(reference, dr) }
}

/** The category of a count ranking in running text: "violent crimes", "burglary", "drug arrests" */
function countCategory(code: string, metadata: CountFlagMetadata): string {
  return noneOfPhrase(code, metadata?.offenses.find((o) => o.code === code))
}

/**
 * The note of a count ranking's row flagged very high for its institution's
 * size (highForSize; RateRules.countFlag), short. `perTenK`: the count per
 * 10,000 of the institution's FTE.
 */
export function highForSizeNote(perTenK: number, code: string, year: number, metadata: CountFlagMetadata): string {
  const flag = metadata?.rateRules?.countFlag
  const factor = flag?.factor ?? 3
  const { value, ref } = countFlagFigures(perTenK, flag?.reference?.[String(year)]?.[code], factor)
  return `Very high for its institution's size: ${value} per 10,000 students (the institution's FTE), more than ` +
    `${factor} times the ${flag?.percentile ?? 99}th-percentile institution rate for ${countCategory(code, metadata)} ` +
    `in ${year}${ref !== null ? ` (${ref})` : ''}. The count is shown as DOE reports it; the figures do not say why ` +
    'it is high.'
}

/**
 * The same note in full, for the school page: the count, the institution's
 * FTE (`campuses`: its campuses that year) and why the year's count may
 * include incidents of earlier years.
 */
export function highForSizeParagraph(
  count: number, fte: number, campuses: number, code: string, year: number, metadata: CountFlagMetadata,
): string {
  const flag = metadata?.rateRules?.countFlag
  const factor = flag?.factor ?? 3
  const { value, ref } = countFlagFigures((count / fte) * 10000, flag?.reference?.[String(year)]?.[code], factor)
  const category = countCategory(code, metadata)
  const counted = code in OFFENSE_NOUNS ? offenseCount(count, code) : `${fmtInt(count)} ${category}`
  const all = campuses > 1 ? `, all ${fmtInt(campuses)} of its campuses` : ''
  return `${year}: ${counted} reported by this campus, ${value} per 10,000 of its institution's ` +
    `full-time-equivalent students (NCES's FTE for the whole institution: ${fmtInt(fte)}${all}). That is more than ${factor} times ` +
    `${ref !== null ? `${ref}, ` : ''}the ${flag?.percentile ?? 99}th percentile of ${year} institution rates of ` +
    `${category}. The count is shown as reported and keeps its place in the rankings by count. DOE counts each ` +
    'incident in the year it is reported, so some may have happened earlier, and the figures do not say why a ' +
    'count is high.'
}

export { VERDICT_LABELS }
