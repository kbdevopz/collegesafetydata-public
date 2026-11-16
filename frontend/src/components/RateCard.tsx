import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type {
  HospitalUnresolved, InstitutionWindowCode, RateEntryFields, RateRules, SchoolProfile, SharedSiteFigure,
  SharedSiteNotes, Verdict,
} from '../lib/types'
import {
  coLocatedSentence, compositionSentence, differSentence, entryPosition, flagSentence, FLAG_NOTE, fmtInt, fmtRate,
  hospitalNote, intervalSentence, isListCode, medicalSentence, nationalSentence, notListedSentence, notPlacedSentence,
  onlineSentence, otherLocationsSentence, peerSentence, rateCodeLabel, sharedFigureText, sharedGuestSentence,
  sharedHostSentence, spreadSentence, tieDigits, typePositionText, windowLabel, withoutFlaggedSentence,
} from '../lib/rates'
import LinkedText from './LinkedText'
import { stateDisplayMin, VERDICT_LABELS } from '../lib/rateDisplay'
import { cn, formatNumber } from '../lib/utils'

const VERDICT_TONES: Record<Verdict, string> = {
  above: 'bg-amber-50 text-amber-900 border-amber-300 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-700',
  below: 'bg-sky-50 text-sky-900 border-sky-300 dark:bg-sky-900/30 dark:text-sky-200 dark:border-sky-700',
  nd: 'bg-gray-50 text-gray-800 border-gray-300 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600',
  undetermined: 'bg-gray-50 text-gray-800 border-gray-300 border-dashed dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600',
  withheld: 'bg-white text-gray-700 border-gray-400 border-dashed dark:bg-gray-900 dark:text-gray-300 dark:border-gray-500',
}

/** The verdict against the national rate, in words (the colour only repeats it) */
export function VerdictLabel({ verdict, short, className }: { verdict: Verdict; short?: string; className?: string }) {
  return (
    <span className={cn('inline-block rounded border px-1.5 py-0.5 text-xs font-medium', VERDICT_TONES[verdict], className)}>
      {short ?? VERDICT_LABELS[verdict]}
    </span>
  )
}

/**
 * Every sentence the pages show for one rated institution, window and code,
 * in reading order. `listN`: members of the national list (list codes);
 * `minFteYears`: the list's size threshold in student-years.
 */
export interface EntryText {
  verdict: Verdict
  interval: string
  peer: string | null
  differ: string | null
  position: string | null
  statePosition: string | null
  typePosition: string | null
  // Not on the list: too few expected incidents, or not placed (unusual year)
  notListed: string | null
  // A hospital next to the main campus (hospitalUnresolved)
  hospital: string | null
  why: string | null
  notes: string[]
  // A guest's shared-site sentence (in `why` when withheld, else in `notes`)
  // and the per-year figures listed after it (empty when none is published)
  guest: string | null
  figures: SharedSiteFigure[]
  flags: string[]
  withoutFlagged: string | null
  composition: string | null
  national: string
}

export function entryText(
  e: RateEntryFields, opts: {
    code: string
    windowKey: string
    rules: RateRules | null | undefined
    natl: number
    peerType: string
    peerRate: number | null
    listN: number | null
    minFteYears?: number
    profile?: Pick<SchoolProfile, 'institution'> | null
    state?: string
    // The window's shared-site notes (on a window-file entry: the entry itself)
    notes?: SharedSiteNotes
    // The national and peer rates to 4 decimals, and the yearly counts
    natl4?: number | null
    peerRate4?: number | null
    nByYear?: Record<string, number>
  },
): EntryText {
  const { code, windowKey, rules, natl, peerType, peerRate, listN, minFteYears, profile } = opts
  const site = opts.notes ?? {}
  const listCode = isListCode(code, rules)
  let why: string | null = null
  if (e.why === 'online' || e.verdict === 'undetermined') {
    why = onlineSentence(e, windowKey, profile)
    if (listCode) why = `${why} Institutions with an uncertain on-campus student count are not on the lists.`
  }
  const medical = medicalSentence(e, listCode)
  // A guest or participant at a shared site: why it is not compared (the
  // headline reason), or why it is compared as usual (a note)
  const guest = sharedGuestSentence(e, site, code, listCode, rules)
  const withheld = e.verdict === 'withheld' || e.why === 'shared'
  if (e.why === 'medical_campus') why = medical
  if (withheld) why = guest
  const notes: string[] = []
  if (medical && e.why !== 'medical_campus') notes.push(medical)
  if (guest && !withheld) notes.push(guest)
  const host = sharedHostSentence(e, site, code)
  if (host) notes.push(host)
  const coLocated = coLocatedSentence(site)
  if (coLocated) notes.push(coLocated)
  const other = otherLocationsSentence(e.nNoncampus, e.nPublic)
  if (other) notes.push(other)
  const minState = stateDisplayMin(rules)
  const statePosition = e.listed && e.stateN !== undefined && minState !== null && e.stateN >= minState
    ? entryPosition(e, null, true)
    : null
  const figures = site.sharedSite?.figures ?? []
  // A deciding end of the interval that prints the same as the rate it is
  // compared with: both to 4 decimals
  const natDigits = tieDigits(e, e.verdict, natl, opts.natl4)
  const peerDigits = tieDigits(e, e.peerVerdict, peerRate, opts.peerRate4)
  const digits = natDigits === 4 || peerDigits === 4 ? 4 : 2
  const spread = spreadSentence(e, opts.nByYear)
  return {
    verdict: e.verdict,
    interval: `${intervalSentence(e, rules, digits)}${spread ? ` ${spread}` : ''}`,
    peer: peerSentence(e, peerType, peerRate, rules, opts.peerRate4, peerDigits),
    differ: differSentence(e.verdict, e.peerVerdict, natl, peerType, peerRate, rules),
    position: listCode && e.listed ? entryPosition(e, listN) : null,
    statePosition: statePosition && opts.state ? `Among the ${fmtInt(e.stateN ?? 0)} on the list in ${opts.state}: ${statePosition}` : null,
    typePosition: listCode ? typePositionText(e, peerType, rules) : null,
    notListed: listCode && !e.listed && !e.why
      ? (notPlacedSentence(e) ?? notListedSentence(minFteYears, rules))
      : null,
    hospital: hospitalNote(e.hospitalUnresolved),
    why,
    notes,
    guest,
    figures: figures.some((f) => f.students !== null) ? figures : [],
    flags: (e.flags ?? []).map((f) => flagSentence(f)),
    withoutFlagged: e.verdictWithoutFlagged ? withoutFlaggedSentence(e.verdictWithoutFlagged) : null,
    composition: compositionSentence(code, e.composition, e.n, windowKey),
    national: nationalSentence(natl, windowKey, rules, opts.natl4, natDigits),
  }
}

function Line({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-sm text-gray-700 dark:text-gray-300', className)}>{children}</p>
}

/** A guest's shared-site figures, one per site campus and year, behind a disclosure */
function SiteFigures({ figures }: { figures: SharedSiteFigure[] }) {
  return (
    <details className="text-sm text-gray-600 dark:text-gray-400">
      <summary className="cursor-pointer text-primary-600 dark:text-primary-400 hover:underline">
        Students there by year and campus
      </summary>
      <ul className="mt-1 ml-5 list-disc space-y-0.5">
        {figures.map((f) => (
          <li key={`${f.year}-${f.unitid}`}>
            {f.year},{' '}
            <Link to={`/school/${f.unitid}`} className="underline">DOE campus {f.unitid}</Link>: {sharedFigureText(f)}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs">
        A figure's year is the fall term it describes, or the academic year that begins that fall. Which figures
        are accepted and what they count:{' '}
        <Link to="/methodology#rate-shared" className="underline">Shared campuses</Link>.
      </p>
    </details>
  )
}

/**
 * One code of an institution's rated window: the rate, its interval, the
 * comparisons, list position or why it is not on a list, and every note.
 */
export function RateCodeBlock({
  code, windowKey, entry, rules, peerType, listN, minFteYears, profile, state, notes, headingLevel = 3,
  hospital,
}: {
  code: string
  windowKey: string
  entry: InstitutionWindowCode
  rules: RateRules | null | undefined
  peerType: string
  listN: number | null
  minFteYears?: number
  profile?: Pick<SchoolProfile, 'institution'> | null
  state?: string
  // The window's shared-site notes (institution file: the rated window status)
  notes?: SharedSiteNotes
  headingLevel?: 3 | 4
  // The institution file's hospital rows, for the hospital note's "more";
  // null: the page shows the note once elsewhere, not in this block
  hospital?: HospitalUnresolved[] | null
}) {
  const t = entryText(entry, {
    code, windowKey, rules, natl: entry.natl, peerType, peerRate: entry.peerRate, listN, minFteYears, profile, state,
    notes, natl4: entry.natl4, peerRate4: entry.peerRate4, nByYear: entry.nByYear,
  })
  const Heading = headingLevel === 3 ? 'h3' : 'h4'
  const years = Object.keys(entry.nByYear).sort()
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Heading className="text-base font-semibold text-gray-900 dark:text-gray-100">{rateCodeLabel(code)}</Heading>
        <VerdictLabel verdict={t.verdict} />
      </div>
      <p className="text-gray-900 dark:text-gray-100">
        <span className="text-2xl font-bold tabular-nums">{fmtRate(entry.rate)}</span>{' '}
        <span className="text-sm text-gray-600 dark:text-gray-400">
          reported incidents on campus per 10,000 on-campus students a year, {windowLabel(windowKey)} average
        </span>
      </p>
      <Line>{t.interval}</Line>
      {t.why && <Line className="font-medium">{t.why}</Line>}
      {t.why !== null && t.why === t.guest && t.figures.length > 0 && <SiteFigures figures={t.figures} />}
      {t.peer && <Line>{t.peer}</Line>}
      {t.differ && <Line>{t.differ}</Line>}
      {t.position && (
        <Line>
          <span className="font-medium">National list position:</span> {t.position}.
        </Line>
      )}
      {t.statePosition && <Line>{t.statePosition}.</Line>}
      {t.typePosition && <Line>{t.typePosition}.</Line>}
      {t.notListed && <Line>{t.notListed}</Line>}
      <Line className="text-gray-600 dark:text-gray-400">
        On campus: {fmtInt(entry.n)} {entry.n === 1 ? 'incident' : 'incidents'}
        {years.length > 0 && <> ({years.map((y) => `${fmtInt(entry.nByYear[y])} in ${y}`).join(', ')})</>}, over{' '}
        {fmtInt(entry.fteYears)} student-years (on-campus students added up over the three years). At the national
        rate, about {formatNumber(entry.E, 1)} would be expected.
      </Line>
      {t.notes.map((n) => (
        <Fragment key={n}>
          <Line className="text-gray-600 dark:text-gray-400">{n}</Line>
          {n === t.guest && t.figures.length > 0 && <SiteFigures figures={t.figures} />}
        </Fragment>
      ))}
      {t.flags.length > 0 && (
        <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-2 space-y-1">
          <p className="text-xs font-medium text-amber-900 dark:text-amber-200">Unusual {t.flags.length === 1 ? 'year' : 'years'}</p>
          {t.flags.map((f) => <Line key={f} className="text-amber-900 dark:text-amber-200">{f}</Line>)}
          {t.withoutFlagged && <Line className="text-amber-900 dark:text-amber-200">{t.withoutFlagged}</Line>}
          <Line className="text-amber-900 dark:text-amber-200">{FLAG_NOTE}</Line>
        </div>
      )}
      {t.composition && <Line className="text-gray-600 dark:text-gray-400">{t.composition}</Line>}
      {hospital !== null && entry.hospitalUnresolved && (
        <HospitalNote note={entry.hospitalUnresolved} rows={hospital ?? []} />
      )}
      <Line className="text-xs text-gray-500 dark:text-gray-400">{t.national}</Line>
    </div>
  )
}

/**
 * The hospital note (hospitalUnresolved) with what the institution's reports
 * say and where, from the institution file's reviewed rows, behind "More".
 */
export function HospitalNote({
  note, rows, windowYearsN = 3,
}: {
  note: { name: string; years: number[] }
  rows: HospitalUnresolved[]
  windowYearsN?: number
}) {
  const row = rows.find((r) => r.name === note.name)
  return (
    <div className="text-sm text-gray-700 dark:text-gray-300">
      <p>{hospitalNote(note, windowYearsN)}</p>
      {row && (
        <details className="mt-1 text-gray-600 dark:text-gray-400">
          <summary className="cursor-pointer text-primary-600 dark:text-primary-400 hover:underline">
            More: what its reports say
          </summary>
          <p className="mt-1">{row.known}</p>
          <p className="mt-1 text-xs break-words">Source: <LinkedText text={row.source} /></p>
        </details>
      )}
    </div>
  )
}
