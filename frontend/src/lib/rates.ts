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
  FteUncertain, InstitutionFlag, InstitutionWindow, Metadata, NamedInstitution, NotRatedReason, PooledInstitution,
  RateEntryFields, RateFlag, RateRules, RateRule, SchoolProfile, SharedSiteNotes, Verdict,
} from './types'
import {
  COUNTS_ONLY_REASONS, OFFENSE_NOUNS, RATE_CODE_LABELS, RATE_CODE_ORDER, RATE_CODE_PHRASES, VERDICT_LABELS,
  VERDICT_SHORT,
} from './rateDisplay'

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

export const fmtInt = (n: number) => n.toLocaleString('en-US')

/** A published rate (2 decimals) as published: "31.01" */
export function fmtRate(x: number): string {
  return x.toFixed(2)
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

/** "12th; could be anywhere from 3rd to 61st of 206" */
export function positionText(position: number, lo: number, hi: number, n: number): string {
  if (lo === hi) return `${ordinal(position)} of ${fmtInt(n)}; the range is that position alone`
  return `${ordinal(position)}; could be anywhere from ${ordinal(lo)} to ${ordinal(hi)} of ${fmtInt(n)}`
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

export function intervalSentence(e: Pick<RateEntryFields, 'lo' | 'hi'>, rules: RateRules | null | undefined): string {
  return `${levelPct(rules)}% interval ${fmtRate(e.lo)} to ${fmtRate(e.hi)}. This range allows for how much an ` +
    "institution's yearly counts vary. It does not allow for differences in how institutions record and report " +
    'incidents.'
}

/** What the national rate is and what "above" means */
export function nationalSentence(natl: number, key: string, rules: RateRules | null | undefined): string {
  const chance = oneSidedChance(rules)
  return `National rate ${fmtRate(natl)} for ${windowLabel(key)}: the on-campus incidents of all rated ` +
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
): string | null {
  // "withheld": the shared-site sentence says why there is no comparison
  if (e.peerVerdict === null || e.peerVerdict === 'withheld' || peerRate === null) return null
  const label = peerLabel(peerType, rules)
  let verdict: string = VERDICT_SHORT[e.peerVerdict]
  if (e.peerVerdict === 'undetermined' && e.peerVerdictLargerFte && e.peerVerdictSmallerFte) {
    verdict += ` (${VERDICT_SHORT[e.peerVerdictLargerFte]} with the larger student count, ` +
      `${VERDICT_SHORT[e.peerVerdictSmallerFte]} with the smaller)`
  }
  return `Compared with institutions of its type (${label}; their rate ${fmtRate(peerRate)}): ${verdict}.`
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
    `${f.usual.toLocaleString('en-US')} a year in this institution's other years. DOE counts incidents in the ` +
    'year they are reported, so a single investigation or series of reports can add many to one year.'
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
  const figure = site && site.students !== null
    ? `Published enrollment figures put its students there at ${site.upperBound ? 'no more than ' : ''}` +
      `${fmtInt(site.students)}${site.years.length > 1 ? ' (added over those years)' : ''}`
    : null
  const against = `of the ${fmtInt(e.fteYears)} on-campus student-years in this rate`
  if (!withheld) {
    // Exempt: compared as usual
    return `${fact} ${left} ${figure ?? 'Published enrollment figures put its students there'}: at most ` +
      `${share} ${against}, so it is compared as usual.`
  }
  const lead = listCode ? 'Not compared and not on the list.' : 'Not compared.'
  const why = figure
    ? `${figure}: more than ${share} ${against}${site?.upperBound ? ' (an upper bound: the true number may be smaller, but no figure shows that it is)' : ''}.`
    : "Its student count is NCES's figure for the whole institution, so it may include students there, and how " +
      "many is not known: DOE's files give no enrollment per campus, and the published enrollment figures used " +
      `here do not cover ${site && site.years.length > 1 ? 'all of those years' : 'that year'}.`
  return `${lead} ${fact} ${left} ${why} So the rate may count students whose incidents it leaves out. It is ` +
    'shown, but not compared with the national rate or with institutions of its type.'
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
      `put its students there at most ${share} of its student-years`)
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
export function nationalCompositionSentence(code: string, composition: Record<string, number> | undefined, key: string): string | null {
  if (!composition) return null
  if (code === 'violent') {
    const total = Object.values(composition).reduce((a, b) => a + b, 0)
    if (total <= 0) return null
    const pct = (o: string) => `${((composition[o] ?? 0) / total * 100).toFixed(1)}%`
    return 'Violent crimes are murder, rape, robbery and aggravated assault. In ' +
      `${windowLabel(key)}, of the ${fmtInt(total)} on-campus violent crimes at the institutions in the national rate, ${pct('rape')} ` +
      `were rapes, ${pct('aggravated_assault')} aggravated assaults, ${pct('robbery')} robberies and ` +
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

/** Why a window has no rate for this institution, or null when it is rated */
export function windowStatusSentence(
  w: InstitutionWindow, key: string, rules: RateRules | null | undefined,
  profile?: Pick<SchoolProfile, 'institution'> | null,
): string | null {
  const minFte = fmtInt(rules?.minFte ?? 1000)
  switch (w.status) {
    case 'rated':
      return null
    case 'missingYears':
      return `Not rated for ${windowLabel(key)}: not in DOE's data all three years (only ${joinAnd(w.years.map(String))}).`
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
      return 'its Carnegie classification is a special-focus medical school or research institution.'
    case 'listed':
      return 'it is on the reviewed list of institutions whose campus holds people its enrollment does not count.'
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

/**
 * For an institution without a rates file: one sentence on why it has no
 * rate, from its years' notRated reasons. `yearsListed`: the page lists
 * each year's reason after it, so the sentence need not repeat them.
 */
export function noRatesSentence(
  profile: Pick<SchoolProfile, 'institution'> | null | undefined, rules: RateRules | null | undefined, yearsListed = false,
): string {
  const byYear = Object.entries(profile?.institution?.byYear ?? {}).sort(([a], [b]) => a.localeCompare(b))
  if (byYear.length === 0) return 'No rate: NCES enrollment figures do not cover this institution.'
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

/** The highForSize note of a count ranking (RateRules.countFlag) */
export function highForSizeNote(perTenK: number, code: string, year: number, metadata: Pick<Metadata, 'rateRules'> | null): string {
  const flag = metadata?.rateRules?.countFlag
  const reference = flag?.reference?.[String(year)]?.[code]
  const factor = flag?.factor ?? 3
  const pct = flag?.percentile ?? 99
  const ref = reference !== undefined ? `${reference.toFixed(2)}, ` : ''
  return `Very high for its institution's size: ${perTenK.toFixed(1)} per 10,000 of its institution's FTE, more ` +
    `than ${factor} times ${ref}the ${pct}th percentile of ${year} institution rates of this category. Shown as ` +
    "reported; check the institution's Annual Security Report."
}

export { VERDICT_LABELS }
