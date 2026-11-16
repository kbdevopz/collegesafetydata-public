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
import { AlertTriangle } from 'lucide-react'
import LinkedText from './LinkedText'
import { stateDisplayMin, VERDICT_LABELS } from '../lib/rateDisplay'
import { cn, formatNumber } from '../lib/utils'

// Neutral tones that differ by fill and outline, not by hue: the words say
// which verdict it is
const VERDICT_TONES: Record<Verdict, string> = {
  above: 'bg-tint text-ink border-rule-strong',
  below: 'bg-surface text-ink border-rule-strong',
  nd: 'bg-transparent text-ink-2 border-rule',
  undetermined: 'bg-transparent text-ink-2 border-rule-strong border-dashed',
  withheld: 'bg-transparent text-ink-3 border-rule-strong border-dashed',
}

/** The verdict against the national rate, in words (the colour only repeats it) */
export function VerdictLabel({ verdict, short, className }: { verdict: Verdict; short?: string; className?: string }) {
  return (
    <span className={cn('inline-block rounded-sm border px-1.5 py-px text-label font-semibold', VERDICT_TONES[verdict], className)}>
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
  return <p className={cn('text-ui text-ink-2', className)}>{children}</p>
}

/** A guest's shared-site figures, one per site campus and year, behind a disclosure */
function SiteFigures({ figures }: { figures: SharedSiteFigure[] }) {
  return (
    <details className="text-meta text-ink-2">
      <summary className="cursor-pointer font-semibold text-accent underline-offset-[3px] hover:underline">
        Students there by year and campus
      </summary>
      <ul className="mt-1 ml-5 list-disc space-y-0.5">
        {figures.map((f) => (
          <li key={`${f.year}-${f.unitid}`}>
            {f.year},{' '}
            <Link to={`/school/${f.unitid}`} className="link">DOE campus {f.unitid}</Link>: {sharedFigureText(f)}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-meta text-ink-3">
        A figure's year is the fall term it describes, or the academic year that begins that fall. Which figures
        are accepted and what they count:{' '}
        <Link to="/methodology#rate-shared" className="link">Shared campuses</Link>.
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
        <Heading className="h3">{rateCodeLabel(code)}</Heading>
        <VerdictLabel verdict={t.verdict} />
      </div>
      <p className="text-ink">
        <span className="tabular text-figure font-semibold">{fmtRate(entry.rate)}</span>{' '}
        <span className="text-meta text-ink-2">
          reported incidents on campus per 10,000 on-campus students a year, {windowLabel(windowKey)} average
        </span>
      </p>
      <Line>{t.interval}</Line>
      {t.why && <Line className="font-semibold text-ink">{t.why}</Line>}
      {t.why !== null && t.why === t.guest && t.figures.length > 0 && <SiteFigures figures={t.figures} />}
      {t.peer && <Line>{t.peer}</Line>}
      {t.differ && <Line>{t.differ}</Line>}
      {t.position && (
        <Line>
          <span className="font-semibold text-ink">National list position:</span> {t.position}.
        </Line>
      )}
      {t.statePosition && <Line>{t.statePosition}.</Line>}
      {t.typePosition && <Line>{t.typePosition}.</Line>}
      {t.notListed && <Line>{t.notListed}</Line>}
      <Line className="tabular text-meta">
        On campus: {fmtInt(entry.n)} {entry.n === 1 ? 'incident' : 'incidents'}
        {years.length > 0 && <> ({years.map((y) => `${fmtInt(entry.nByYear[y])} in ${y}`).join(', ')})</>}, over{' '}
        {fmtInt(entry.fteYears)} student-years (on-campus students added up over the three years). At the national
        rate, about {formatNumber(entry.E, 1)} would be expected.
      </Line>
      {t.notes.map((n) => (
        <Fragment key={n}>
          <Line className="text-meta">{n}</Line>
          {n === t.guest && t.figures.length > 0 && <SiteFigures figures={t.figures} />}
        </Fragment>
      ))}
      {t.flags.length > 0 && (
        <div className="space-y-1 border-l-2 border-attention pl-3">
          <p className="flex items-center gap-1.5 text-meta font-semibold text-ink">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-attention" aria-hidden="true" />
            Unusual {t.flags.length === 1 ? 'year' : 'years'}
          </p>
          {t.flags.map((f) => <Line key={f} className="text-meta">{f}</Line>)}
          {t.withoutFlagged && <Line className="text-meta">{t.withoutFlagged}</Line>}
          <Line className="text-meta">{FLAG_NOTE}</Line>
        </div>
      )}
      {t.composition && <Line className="text-meta">{t.composition}</Line>}
      {hospital !== null && entry.hospitalUnresolved && (
        <HospitalNote note={entry.hospitalUnresolved} rows={hospital ?? []} />
      )}
      <Line className="text-meta text-ink-3">{t.national}</Line>
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
    <div className="text-meta text-ink-2">
      <p>{hospitalNote(note, windowYearsN)}</p>
      {row && (
        <details className="mt-1">
          <summary className="cursor-pointer font-semibold text-accent underline-offset-[3px] hover:underline">
            More: what its reports say
          </summary>
          <p className="mt-1">{row.known}</p>
          <p className="mt-1 text-meta text-ink-3 break-words">Source: <LinkedText text={row.source} /></p>
        </details>
      )}
    </div>
  )
}
