/**
 * Display decisions for the 3-year rates (rates/*.json). The data carries
 * every figure; these constants decide only what the pages show and how
 * they name it. Change them here, not in the pages.
 */

import type { RateRules, Verdict } from './types'

// A listed institution's point position is shown next to its rank range,
// always together ("12th; could be anywhere from 3rd to 61st of 206").
export const SHOW_POINT_POSITION = true

/**
 * A state's own positions are shown only when at least this many of its
 * institutions are on the national list (metadata.json
 * rateRules.lists.stateDisplayMin). The data publishes state fields from
 * lists.stateMinMembers up; with fewer members the pages show the national
 * positions and say how many are on the list. Null without the rules: then
 * no state positions are shown.
 */
export function stateDisplayMin(rules: RateRules | null | undefined): number | null {
  const n = rules?.lists?.stateDisplayMin
  return typeof n === 'number' ? n : null
}

// Names of the places in DOE's data that have no state preset (and no
// rates), for a page asked for one of them (?preset=GU)
export const PLACES_WITHOUT_PRESET: Record<string, string> = {
  AS: 'American Samoa',
  FM: 'the Federated States of Micronesia',
  GU: 'Guam',
  MH: 'the Marshall Islands',
  MP: 'the Northern Mariana Islands',
  PW: 'Palau',
}

// The codes whose window and list are shown first on school pages, in this order
export const MAIN_RATE_CODES = ['violent', 'criminal_xmvt', 'burglary'] as const

// Every rate code, in the order the selects list them
export const RATE_CODE_ORDER = [
  'violent', 'criminal_xmvt', 'burglary', 'rape', 'fondling', 'robbery', 'aggravated_assault',
  'stalking', 'dating_violence', 'domestic_violence',
] as const

export const RATE_CODE_LABELS: Record<string, string> = {
  violent: 'Violent crimes',
  criminal_xmvt: 'Criminal offenses except motor-vehicle theft',
  burglary: 'Burglary',
  rape: 'Rape',
  fondling: 'Fondling',
  robbery: 'Robbery',
  aggravated_assault: 'Aggravated assault',
  stalking: 'Stalking',
  dating_violence: 'Dating violence',
  domestic_violence: 'Domestic violence',
}

// "incidents of ..." in running text
export const RATE_CODE_PHRASES: Record<string, string> = {
  violent: 'violent crimes',
  criminal_xmvt: 'criminal offenses other than motor-vehicle theft',
  burglary: 'burglaries',
  rape: 'rapes',
  fondling: 'fondling incidents',
  robbery: 'robberies',
  aggravated_assault: 'aggravated assaults',
  stalking: 'stalking incidents',
  dating_violence: 'dating-violence incidents',
  domestic_violence: 'domestic-violence incidents',
}

// Offense codes as counted nouns, for flags and compositions: [one, many]
export const OFFENSE_NOUNS: Record<string, [string, string]> = {
  murder: ['murder', 'murders'],
  negligent_manslaughter: ['negligent manslaughter', 'negligent manslaughters'],
  rape: ['rape', 'rapes'],
  fondling: ['fondling incident', 'fondling incidents'],
  incest: ['incest incident', 'incest incidents'],
  statutory_rape: ['statutory rape', 'statutory rapes'],
  robbery: ['robbery', 'robberies'],
  aggravated_assault: ['aggravated assault', 'aggravated assaults'],
  burglary: ['burglary', 'burglaries'],
  motor_vehicle_theft: ['motor-vehicle theft', 'motor-vehicle thefts'],
  arson: ['arson', 'arsons'],
  stalking: ['stalking incident', 'stalking incidents'],
  dating_violence: ['dating-violence incident', 'dating-violence incidents'],
  domestic_violence: ['domestic-violence incident', 'domestic-violence incidents'],
}

// The verdict against the national rate, as a headline
export const VERDICT_LABELS: Record<Verdict, string> = {
  above: 'Above the national rate',
  below: 'Below the national rate',
  nd: 'Not distinguishable from the national rate',
  undetermined: 'Not determined',
  withheld: 'Not compared (shared campus)',
}

// The same verdict in a short phrase (peer comparisons, filters)
export const VERDICT_SHORT: Record<Verdict, string> = {
  above: 'above',
  below: 'below',
  nd: 'not distinguishable',
  undetermined: 'not determined',
  withheld: 'not compared (shared campus)',
}

export const VERDICT_ORDER: Verdict[] = ['above', 'nd', 'below', 'undetermined', 'withheld']

// What a rate is, said once wherever rates appear
export const RATE_MEASURE =
  'Incidents reported on campus under the Clery Act per 10,000 on-campus students (full-time equivalent) a ' +
  'year, averaged over three years.'

export const RATE_IS_NOT =
  'It is not any one student\'s risk, it is not a count of crimes against students (incidents involving staff ' +
  'and visitors count too), and it does not compare like with like when institutions record and report ' +
  'incidents differently.'

// Why codes without a rate are shown as counts only. A code missing here
// falls back to a plain statement that it has no rate.
export const COUNTS_ONLY_REASONS: Record<string, string> = {
  drug_arrest: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  liquor_arrest: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  weapons_arrest: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  drug_discipline: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  liquor_discipline: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  weapons_discipline: 'Arrests and disciplinary referrals are shown as counts only: they measure enforcement activity, not incidents.',
  all: '"All categories" adds crimes to arrests and disciplinary referrals, which measure enforcement activity, so it is shown as counts only.',
  motor_vehicle_theft: 'Motor-vehicle theft is shown as counts only and is left out of the criminal-offense rate; Methodology gives the reason and the national figures.',
  murder: 'Murder has no rate of its own because it is rare on campus; murders are counted in the violent-crime rate.',
  negligent_manslaughter: 'Negligent manslaughter has no rate of its own because it is rare; it is counted in the rate of criminal offenses except motor-vehicle theft.',
  incest: 'Incest has no rate of its own because it is rare; it is counted in the rate of criminal offenses except motor-vehicle theft.',
  statutory_rape: 'Statutory rape has no rate of its own because it is rare; it is counted in the rate of criminal offenses except motor-vehicle theft.',
  arson: 'Arson has no rate of its own; it is counted in the rate of criminal offenses except motor-vehicle theft.',
}
