import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchPresets, fetchRateWindow } from '../lib/api'
import type { Metadata, PeerRate, RateRules, RateWindowEntry, RateWindowFile, Verdict } from '../lib/types'
import {
  entryPosition, fmtInt, fmtRate, fmtRateAt, hospitalNote, isListCode, isWithheld, joinAnd, levelPct, listMinStudents,
  nationalCompositionSentence, nationalSentence, offenseCount, ordinal, peerLabel, positionText, rateCodeLabel,
  rateCodePhrase, sharedShortNotes, tieDigits, windowLabel,
} from '../lib/rates'
import {
  PLACES_WITHOUT_PRESET, RATE_IS_NOT, RATE_MEASURE, SHOW_POINT_POSITION, stateDisplayMin, VERDICT_ORDER,
  VERDICT_SHORT,
} from '../lib/rateDisplay'
import { formatNumber } from '../lib/utils'
import { VerdictLabel } from './RateCard'
import RowNote, { NoteJoiner, type RowNoteItem } from './RowNote'
import { CompareButton, Disclosure, Loading } from './ui'

const PAGE = 50

interface Props {
  metadata: Metadata
  preset: string
  windowKey: string
  code: string
  verdict: Verdict | null
  onVerdict: (v: Verdict | null) => void
  // ?type=: positions within one peer type (national selection, list codes)
  peerType: string | null
  onPeerType: (t: string | null) => void
  isInCompare: (unitid: number) => boolean
  toggleCompare: (unitid: number, name: string, e?: React.MouseEvent) => void
}

/**
 * The Rankings page's rate view: one window and rate code. For the three
 * list codes, three groups: the placed members of the ordered list (national,
 * a state's own list when it has enough members, or the members of one
 * institution type), the institutions not placed because of an unusual year,
 * and the other rated institutions by name with the reason they are not on
 * the list. For the other codes, every rated institution by name.
 */
export default function RateRankingsView({
  metadata, preset, windowKey, code, verdict, onVerdict, peerType, onPeerType, isInCompare, toggleCompare,
}: Props) {
  const rules = metadata.rateRules
  const [file, setFile] = useState<RateWindowFile | null>(null)
  const [error, setError] = useState(false)
  const [ivyIds, setIvyIds] = useState<Set<number> | null>(null)
  const [shown, setShown] = useState(PAGE)

  useEffect(() => {
    setFile(null)
    setError(false)
    setShown(PAGE)
    let live = true
    fetchRateWindow(windowKey, code)
      .then((f) => live && setFile(f))
      .catch(() => live && setError(true))
    return () => {
      live = false
    }
  }, [windowKey, code])

  // A group preset (Ivy League): its institutions' base UNITIDs
  const isState = /^[A-Z]{2}$/.test(preset)
  const isGroup = preset !== 'national' && !isState
  useEffect(() => {
    if (!isGroup) return
    let live = true
    fetchPresets()
      .then((p) => {
        const detail = p[preset]
        if (live && detail && 'schools' in detail) {
          setIvyIds(new Set(detail.schools.map((s) => Math.floor(s.unitid / 1000))))
        }
      })
      .catch(() => live && setIvyIds(new Set()))
    return () => {
      live = false
    }
  }, [preset, isGroup])

  const presetKnown = metadata.presets.some((p) => p.id === preset)
  const presetName = metadata.presets.find((p) => p.id === preset)?.name ?? PLACES_WITHOUT_PRESET[preset] ?? preset
  const listCode = isListCode(code, rules)

  // The types with a type list (typeLists >= typeMinMembers), in metadata order
  const typeMin = rules.lists?.typeMinMembers ?? 2
  const typeOptions = useMemo(
    () => (listCode && preset === 'national' && file?.typeLists
      ? Object.keys(rules.peerTypes).filter((t) => (file.typeLists?.[t] ?? 0) >= typeMin)
      : []),
    [listCode, preset, file, rules.peerTypes, typeMin],
  )
  const type = peerType !== null && typeOptions.includes(peerType) ? peerType : null

  const scoped = useMemo(() => {
    if (!file) return []
    if (isState) return file.entries.filter((e) => e.state === preset)
    if (isGroup) return ivyIds ? file.entries.filter((e) => ivyIds.has(e.id)) : []
    if (type !== null) return file.entries.filter((e) => e.peerType === type)
    return file.entries
  }, [file, isState, isGroup, ivyIds, preset, type])

  const byVerdict = (e: RateWindowEntry) => verdict === null || e.verdict === verdict
  const stateMembers = isState ? file?.stateLists?.[preset] ?? 0 : 0
  const minState = stateDisplayMin(rules)
  const useStatePositions = isState && minState !== null && stateMembers >= minState
  // Placed members, in the order of the positions shown
  const listed = useMemo(() => {
    const xs = scoped.filter((e) => e.listed)
    const key = (e: RateWindowEntry) => (type !== null ? e.typePosition : useStatePositions ? e.statePosition : e.position) ?? Infinity
    return xs.sort((a, b) => key(a) - key(b) || b.rate - a.rate || a.id - b.id)
  }, [scoped, type, useStatePositions])
  const byName = (xs: RateWindowEntry[]) =>
    xs.slice().sort((a, b) => a.name.localeCompare(b.name, 'en-US') || a.id - b.id)
  const notPlaced = useMemo(() => byName(scoped.filter((e) => !e.listed && e.notPlaced)), [scoped])
  const others = useMemo(() => byName(listCode ? scoped.filter((e) => !e.listed && !e.notPlaced) : scoped), [scoped, listCode])
  const tally = useMemo(() => {
    const t: Partial<Record<Verdict, number>> = {}
    for (const e of scoped) t[e.verdict] = (t[e.verdict] ?? 0) + 1
    return t
  }, [scoped])

  // A place outside the rates' states and territories, or no known selection
  if (preset !== 'national' && !presetKnown) {
    return (
      <section className="max-w-prose text-body text-ink-2">
        <p>
          {PLACES_WITHOUT_PRESET[preset]
            ? <><strong className="font-semibold text-ink">{presetName}:</strong> institutions there are not rated.</>
            : <><strong className="font-semibold text-ink">{preset}</strong> is not a state, territory or group on this site, so no institution is shown.</>}{' '}
          Rates cover institutions in the 50 states, the District of Columbia, Puerto Rico and the U.S. Virgin
          Islands.{' '}
          <Link to={`/?view=rate&window=${windowKey}&offense=${code}`} className="link">See the national rates</Link>
        </p>
      </section>
    )
  }

  if (error) {
    return (
      <p className="py-6 text-body text-danger">Failed to load the rates. Please try again.</p>
    )
  }
  if (!file || (isGroup && !ivyIds)) {
    return <Loading className="min-h-[300px]">Loading rates...</Loading>
  }

  const listN = file.list?.n ?? 0
  const minStudents = file.list ? listMinStudents(file.list.minFteYears, rules) : null
  const shownList = listed.filter(byVerdict)
  const shownNotPlaced = notPlaced.filter(byVerdict)
  const shownOthers = others.filter(byVerdict)
  const nationalListed = file.entries.filter((e) => e.listed)
  const example = nationalListed[Math.min(11, nationalListed.length - 1)]
  const composition = nationalCompositionSentence(code, file.composition, windowKey, file.compositionShare)
  const level = levelPct(rules)
  const phrase = rateCodePhrase(code)
  const typeLabel = type !== null ? peerLabel(type, rules) : null
  const typeRate: PeerRate | undefined = type !== null ? file.peer?.[type] : undefined
  // The highest and lowest rate among the classified types (not "other")
  const classified = Object.keys(rules.peerTypes)
    .filter((t) => (rules.peerTypes[t]?.sizeSetting.length ?? 0) > 0 && file.peer?.[t])
    .sort((a, b) => file.peer[b].rate - file.peer[a].rate)
  const hiType = classified[0]
  const loType = classified[classified.length - 1]

  return (
    <div className="space-y-5">
      {/* What the rates are and who is on the list: the first paragraph and
          the national rate in view, the rest behind a disclosure */}
      <section className="max-w-prose space-y-2 text-ui text-ink-2">
        <p>
          <strong className="font-semibold text-ink">{rateCodeLabel(code)}, {windowLabel(windowKey)}.</strong> {RATE_MEASURE} {RATE_IS_NOT} Rates are
          per institution (all its campuses in the United States), because NCES counts enrollment per institution.
        </p>
        {!(listCode && file.list) && (
          <p>
            This rate has no ordered list. Institutions are shown by name with their rates and their comparisons with
            the national rate and with institutions of the same type.
          </p>
        )}
        <p>{nationalSentence(file.natl, windowKey, rules)}</p>
        <Disclosure summary={listCode && file.list ? 'More about the list and these rates' : 'More about these rates'}>
          <div className="space-y-2 border-l-2 border-rule pl-4">
            {listCode && file.list && (
              <>
                <p>
                  <strong className="font-semibold text-ink">Who is on the list:</strong> rated institutions expected, at the national rate, to have at least{' '}
                  {file.list.minExpected} on-campus {phrase} over the three years, which takes about{' '}
                  {fmtInt(minStudents ?? 0)} or more on-campus students. Institutions whose on-campus student count is
                  uncertain, whose count includes many incidents at a medical-center campus, or that are not compared
                  because they share a campus site with another institution, are not on it. An institution with an unusual
                  year in the period (an on-campus count of an offense counted here far above its other years) is not
                  placed, so that one year's count does not set its place. {fmtInt(listN)} institutions are placed,
                  ordered by rate, highest first.
                </p>
                <p>
                  {SHOW_POINT_POSITION
                    ? 'Each position comes with a range: '
                    : 'Each institution on the list is shown with a range of positions: '}
                  with {level}% confidence the institution's position among these {fmtInt(listN)} is within it. This holds
                  for each institution on its own, not for the whole list at once. Two institutions whose ranges overlap
                  may still differ, and positions closer together than these ranges cannot be told apart.
                  {example && example.rankLo !== undefined && example.rankHi !== undefined && (
                    SHOW_POINT_POSITION && example.position !== undefined
                      ? <> For example, {example.name} is {ordinal(example.position)} nationally: its position among the{' '}
                        {fmtInt(listN)} could be anywhere from {ordinal(example.rankLo)} to {ordinal(example.rankHi)}.</>
                      : <> For example, {example.name}'s position among the {fmtInt(listN)} could be anywhere from{' '}
                        {ordinal(example.rankLo)} to {ordinal(example.rankHi)}.</>
                  )}
                </p>
              </>
            )}
            {listCode && (
              <p>
                The order depends on counting only on-campus incidents (counting all locations changes it) and on the size
                threshold. An institution's position can change substantially between windows five years apart.{' '}
                <Link to="/methodology#rates" className="link">Methodology</Link>
              </p>
            )}
            <p>
              A rate needs an institution in the 50 states, DC, Puerto Rico or the U.S. Virgin Islands that has figures of
              its own in DOE's data all three years (not only figures counted under another institution's campus), has at
              least {fmtInt(rules.minFte)} on-campus students in each of them, and is under
              none of the rules that give no rate (for example a hospital, or a main campus whose incidents cannot be
              assigned to one of the institutions sharing it). Institutions without a rate are not shown here; each one's
              page says why.
            </p>
          </div>
        </Disclosure>
      </section>

      {/* Positions within one type of institution (national selection) */}
      {typeOptions.length > 0 && (
        <section className="max-w-prose space-y-2 text-ui text-ink-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <label htmlFor="rate-type" className="label">{SHOW_POINT_POSITION ? 'Positions' : 'List'}</label>
            <select
              id="rate-type"
              value={type ?? ''}
              onChange={(ev) => onPeerType(ev.target.value === '' ? null : ev.target.value)}
              className="control max-w-full"
            >
              <option value="">On the national list ({fmtInt(listN)})</option>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  Among {peerLabel(t, rules).toLowerCase()} institutions ({fmtInt(file.typeLists?.[t] ?? 0)})
                </option>
              ))}
            </select>
          </div>
          {hiType && loType && hiType !== loType && (
            <p className="text-meta">
              Types come from the Carnegie size and setting classification (two-year institutions, four-year
              institutions by how residential they are, and others), and on-campus rates differ by type: in{' '}
              {windowLabel(windowKey)} the rate of{' '}
              {rateCodePhrase(code)} of {peerLabel(hiType, rules).toLowerCase()} institutions together was{' '}
              {fmtRate(file.peer[hiType].rate)} and of {peerLabel(loType, rules).toLowerCase()} institutions{' '}
              {fmtRate(file.peer[loType].rate)}, against {fmtRate(file.natl)} nationally.
            </p>
          )}
          {typeLabel && typeRate && (
            <p className="text-meta">
              The rate of {typeLabel.toLowerCase()} institutions, computed like the national rate within the type
              (over the {fmtInt(typeRate.members)} whose on-campus student count is certain):{' '}
              <span className="tabular font-semibold text-ink">{fmtRate(typeRate.rate)}</span>.
            </p>
          )}
        </section>
      )}

      {/* Verdict filter */}
      <div role="group" aria-label="Filter by comparison with the national rate" className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-meta text-ink-2">Compared with the national rate:</span>
        <FilterChip pressed={verdict === null} onClick={() => onVerdict(null)}>All ({fmtInt(scoped.length)})</FilterChip>
        {VERDICT_ORDER.filter((v) => (tally[v] ?? 0) > 0 || (v !== 'undetermined' && v !== 'withheld')).map((v) => (
          <FilterChip key={v} pressed={verdict === v} onClick={() => onVerdict(verdict === v ? null : v)}>
            {VERDICT_SHORT[v].charAt(0).toUpperCase() + VERDICT_SHORT[v].slice(1)} ({fmtInt(tally[v] ?? 0)})
          </FilterChip>
        ))}
      </div>

      {/* 1. The placed members */}
      {listCode && file.list && (
        <section className={group} aria-labelledby="rate-list-heading">
          <div className={groupHead}>
            <h2 id="rate-list-heading" className={groupTitle}>
              {type !== null && typeLabel
                ? `On the list, among ${typeLabel.toLowerCase()} institutions: ${fmtInt(file.typeLists?.[type] ?? 0)}`
                : preset === 'national'
                  ? `On the list: ${fmtInt(listN)} institutions`
                  : useStatePositions
                    ? `${presetName}: ${fmtInt(stateMembers)} institutions on the national list, with their ${SHOW_POINT_POSITION ? 'positions' : 'ranges of positions'} in ${presetName}`
                    : `${presetName}: institutions on the national list`}
            </h2>
            <p className={groupText}>
              {type !== null && typeLabel
                ? `The national list's ${typeLabel.toLowerCase()} institutions, ordered by rate, highest first, with ${SHOW_POINT_POSITION ? 'positions and ranges' : 'ranges of positions'} worked out among them alone.`
                : isState && !useStatePositions
                  ? (stateMembers === 0
                      ? `None of the ${fmtInt(listN)} institutions on the national list is in ${presetName}.`
                      : `${fmtInt(stateMembers)} of the ${fmtInt(listN)} institutions on the national list ${stateMembers === 1 ? 'is' : 'are'} in ${presetName}; ` +
                        (minState !== null ? `${SHOW_POINT_POSITION ? "a state's own positions are" : 'ranges within a state are'} shown from ${minState} institutions on the list, so ` : '') +
                        (SHOW_POINT_POSITION
                          ? `${stateMembers === 1 ? 'its national position is' : 'their national positions are'} shown.`
                          : `${stateMembers === 1 ? 'its range' : 'their ranges'} on the national list ${stateMembers === 1 ? 'is' : 'are'} shown.`))
                  : isGroup
                    ? `${listed.length} of the ${fmtInt(listN)} institutions on the national list ${listed.length === 1 ? 'is' : 'are'} in this group; their ${SHOW_POINT_POSITION ? 'national positions are' : 'ranges on the national list are'} shown.`
                    : useStatePositions
                      ? `Ordered by rate, highest first, with ${SHOW_POINT_POSITION ? 'positions and ranges' : 'ranges of positions'} worked out among the ${fmtInt(stateMembers)} alone.`
                      : `Ordered by rate, highest first, each with ${SHOW_POINT_POSITION ? 'its position and the range its position could be in' : 'the range its position could be in'}.`}
              {isState && !useStatePositions && stateMembers > 0 && (
                <>
                  {' '}
                  <Link to={`/?view=rate&window=${windowKey}&offense=${code}`} className="link">
                    See the national list
                  </Link>
                </>
              )}
            </p>
            {composition && <p className={groupText}>{composition}</p>}
          </div>
          {shownList.length === 0 ? (
            <p className={groupEmpty}>
              {listed.length === 0 ? 'No institution here is on the list.' : 'No institution on the list matches this filter.'}
            </p>
          ) : (
            <ol className={groupList}>
              {shownList.map((e) => (
                <EntryRow
                  key={e.id}
                  e={e}
                  file={file}
                  code={code}
                  rules={rules}
                  listN={listN}
                  windowKey={windowKey}
                  position={type !== null ? 'type' : useStatePositions ? 'state' : 'national'}
                  isInCompare={isInCompare}
                  toggleCompare={toggleCompare}
                />
              ))}
            </ol>
          )}
        </section>
      )}

      {/* 2. Not placed: an unusual year in the window */}
      {listCode && file.list && (
        <section className={group} aria-labelledby="rate-notplaced-heading">
          <div className={groupHead}>
            <h2 id="rate-notplaced-heading" className={groupTitle}>
              Not placed: an unusual year in this period ({fmtInt(notPlaced.length)})
            </h2>
            <p className={groupText}>
              These institutions meet the list's conditions, but each has a year in {windowLabel(windowKey)} whose
              on-campus count of an offense counted here is at least {rules.flags?.minCount ?? 10} and far above its
              other years; so that one year does not set a place, they have no position and are shown by name with
              their rates and comparisons.{' '}
              <Link to="/methodology#rate-flags" className="link">How flags work</Link>
            </p>
          </div>
          {shownNotPlaced.length === 0 ? (
            <p className={groupEmpty}>
              {notPlaced.length === 0 ? 'No institution here is in this group.' : 'No institution in this group matches this filter.'}
            </p>
          ) : (
            <ul className={groupList}>
              {shownNotPlaced.map((e) => (
                <EntryRow
                  key={e.id}
                  e={e}
                  file={file}
                  code={code}
                  rules={rules}
                  listN={listN}
                  windowKey={windowKey}
                  position="notPlaced"
                  isInCompare={isInCompare}
                  toggleCompare={toggleCompare}
                />
              ))}
            </ul>
          )}
        </section>
      )}

      {/* 3. The other rated institutions, by name (every one, for codes without a list) */}
      <section className={group} aria-labelledby="rate-all-heading">
        <div className={groupHead}>
          <h2 id="rate-all-heading" className={groupTitle}>
            {listCode
              ? `Rated, not on the list: ${fmtInt(others.length)}`
              : `Every institution with a ${windowLabel(windowKey)} rate${preset === 'national' ? '' : ` in ${presetName}`}: ${fmtInt(scoped.length)}`}
          </h2>
          <p className={groupText}>
            {listCode
              ? `Listed by name, each with the reason it is not on the list: fewer than ${rules.lists?.minExpected ?? 20} incidents expected at the national rate, an uncertain on-campus student count, many incidents at a medical-center campus, or a campus site shared with another institution.`
              : 'Listed by name, each with its rate, interval and comparisons.'}
          </p>
        </div>
        {shownOthers.length === 0 ? (
          <p className={groupEmpty}>
            {others.length === 0 ? 'No institution here is in this group.' : 'No institution matches this filter.'}
          </p>
        ) : (
          <ul className={groupList}>
            {shownOthers.slice(0, shown).map((e) => (
              <EntryRow
                key={e.id}
                e={e}
                file={file}
                code={code}
                rules={rules}
                listN={listN}
                windowKey={windowKey}
                position="status"
                isInCompare={isInCompare}
                toggleCompare={toggleCompare}
              />
            ))}
          </ul>
        )}
        {shownOthers.length > shown && (
          <div className="py-5 text-center">
            <button
              type="button"
              onClick={() => setShown((s) => s + PAGE)}
              className="btn"
            >
              Show {Math.min(PAGE, shownOthers.length - shown)} more
              <span className="tabular font-normal text-ink-3">({fmtInt(shownOthers.length - shown)} remaining)</span>
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

const group = 'pt-4'
const groupHead = 'max-w-prose space-y-1 pb-3'
const groupTitle = 'font-serif text-[1.25rem] font-semibold leading-snug text-ink'
const groupText = 'text-meta text-ink-2'
const groupEmpty = 'border-y border-rule py-4 text-meta text-ink-2'
const groupList = 'divide-y divide-rule border-y border-t-ink/60 border-b-rule'

function FilterChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className="chip tabular"
    >
      {children}
    </button>
  )
}

/** Why a rated entry has no position, in a few words shown in its row (the notes say more) */
function notListedShort(e: RateWindowEntry, rules: RateRules): string {
  if (isWithheld(e)) return 'Not on the list: shared campus site'
  if (e.why === 'online') return 'Not on the list: uncertain on-campus student count'
  if (e.why === 'medical_campus') return 'Not on the list: incidents at a medical-center campus'
  if (e.notPlaced) return 'Not placed: an unusual year in this period'
  return `Not on the list: fewer than ${rules.lists?.minExpected ?? 20} incidents expected at the national rate`
}

/** A note as a sentence: capitalized, with a full stop */
const sentence = (s: string) => {
  const t = s.trim()
  return `${t.charAt(0).toUpperCase()}${t.slice(1)}${/[.!?]$/.test(t) ? '' : '.'}`
}

function EntryRow({
  e, file, code, rules, listN, windowKey, position, isInCompare, toggleCompare,
}: {
  e: RateWindowEntry
  // The window file: the national and type rates the comparisons use
  file: RateWindowFile
  code: string
  rules: RateRules
  listN: number
  windowKey: string
  // national, state or type position first (placed members), not placed, or
  // the reason it is not on the list (by-name table)
  position: 'national' | 'state' | 'type' | 'notPlaced' | 'status'
  isInCompare: (unitid: number) => boolean
  toggleCompare: (unitid: number, name: string, ev?: React.MouseEvent) => void
}) {
  const listCode = isListCode(code, rules)
  const national = entryPosition(e, listN)
  const state = entryPosition(e, null, true)
  const typePos = e.listed && e.typePosition !== undefined && e.typeRankLo !== undefined && e.typeRankHi !== undefined && e.typeN
    ? positionText(e.typePosition, e.typeRankLo, e.typeRankHi, e.typeN)
    : null
  const head = position === 'state' ? state : position === 'national' ? national : position === 'type' ? typePos : null
  // Its national range under a state's or a type's (shown with the position)
  const nationalToo = (position === 'state' || position === 'type') && national ? national : null
  // Why it has no position, in a few words (shown in the row)
  const status = (position === 'status' && listCode) || position === 'notPlaced' ? notListedShort(e, rules) : null

  // The row's notes, behind its note button: first the ones that question a
  // figure (unusual years), then the ones that explain it
  const notes: RowNoteItem[] = []
  const info = (text: string) => notes.push({ kind: 'info', text: sentence(text) })
  for (const f of e.flags ?? []) {
    notes.push({
      kind: 'attention',
      text: `Unusual year ${f.year}: ${offenseCount(f.count, f.offense)} on campus (median of its other years ` +
        `${fmtInt(f.usual)}).`,
    })
  }
  if (e.verdictWithoutFlagged) {
    notes.push({
      kind: 'attention',
      text: `Counting the flagged ${(e.flags ?? []).length === 1 ? 'year' : 'years'} at the median: ` +
        `${VERDICT_SHORT[e.verdictWithoutFlagged]}.`,
    })
  }
  // Shared campus sites: why it is not compared (first, when it is not), host and co-located notes
  const site = sharedShortNotes(e, e, rules)
  if (isWithheld(e) && site.length > 0) info(site.shift() ?? '')
  if (e.verdict === 'undetermined' && e.verdictLargerFte && e.verdictSmallerFte) {
    info(`Not determined: ${VERDICT_SHORT[e.verdictLargerFte]} with the larger estimate of on-campus students, ${VERDICT_SHORT[e.verdictSmallerFte]} with the smaller`)
  } else if (e.why === 'online') {
    info('Two estimates of on-campus students; the comparison is the same with either')
  }
  if ((e.medical ?? 0) > 0) info(`${fmtInt(e.medical ?? 0)} of the ${fmtInt(e.n)} at a medical-center campus`)
  site.forEach(info)
  const hospital = hospitalNote(e.hospitalUnresolved, file.years.length, true)
  if (hospital) info(hospital)
  if (e.phiFrom === 'years') {
    info('Its yearly counts vary more than is usual for an institution with this many incidents, so its interval is based on their own spread and is wider')
  }
  if (e.composition && code === 'violent') {
    info(`On campus, by offense: ${joinAnd(['rape', 'aggravated_assault', 'robbery', 'murder'].filter((o) => e.composition?.[o] !== undefined)
      .map((o) => offenseCount(e.composition?.[o] ?? 0, o)))}`)
  }
  if (e.composition && code === 'criminal_xmvt' && e.composition.motor_vehicle_theft !== undefined) {
    info(`Not in the rate: ${offenseCount(e.composition.motor_vehicle_theft, 'motor_vehicle_theft')} on campus`)
  }
  const more = e.nNoncampus + e.nPublic
  if (more > 0) info(`${fmtInt(more)} more at non-campus locations or on public property (not in the rate)`)

  // An interval end that prints as the rate it is compared with: both to 4 decimals
  const peer = file.peer?.[e.peerType]
  const dNatl = tieDigits(e, e.verdict, file.natl, file.natl4)
  const dPeer = tieDigits(e, e.peerVerdict, peer?.rate ?? null, peer?.rate4)
  const digits: 2 | 4 = dNatl === 4 || dPeer === 4 ? 4 : 2
  const refs4 = [
    dNatl === 4 && file.natl4 !== undefined ? `the national rate ${formatNumber(file.natl4, 4)}` : null,
    dPeer === 4 && peer?.rate4 !== undefined ? `the rate of ${peerLabel(e.peerType, rules).toLowerCase()} institutions ${formatNumber(peer.rate4, 4)}` : null,
  ].filter((s): s is string => s !== null)
  if (digits === 4 && refs4.length > 0) info(`Interval to 4 decimals, because to 2 an end prints the same as ${joinAnd(refs4)}`)

  const inCompare = isInCompare(e.unitid)
  return (
    <li className="flex items-stretch hover:bg-subtle/60">
      <div className="flex-1 min-w-0 py-3 pr-3 flex flex-col sm:flex-row gap-1.5 sm:gap-5">
        {head !== null && (
          <div className="tabular sm:w-44 flex-shrink-0 text-ui text-ink">
            <span className="font-semibold">{head.split(';')[0]}</span>
            {head.includes(';') && <span className="text-ink-2">;{head.slice(head.indexOf(';') + 1)}</span>}
            {nationalToo && (
              <span className="block text-meta text-ink-3">National list: {nationalToo}</span>
            )}
          </div>
        )}
        <div className="flex-1 min-w-0 space-y-1">
          {/* On a phone the note button follows the name in the line, with the state on the line of
              the name's last word; from sm up it sits beside the name */}
          <div className="sm:flex sm:items-start sm:gap-1">
            <span className="sm:min-w-0">
              <Link to={`/school/${e.unitid}`} className="link-name">
                {e.name}
              </Link>
              {'\u2060'}
              <span className="ml-1.5 text-meta text-ink-3">{e.state}</span>
              <NoteJoiner />
            </span>
            <RowNote subject={e.name} notes={notes} className="ml-1 sm:ml-0 sm:mt-0.5" />
          </div>
          <div className="tabular flex flex-wrap items-baseline gap-x-4 gap-y-0.5 text-meta text-ink-2">
            <span>
              <span className="text-ui font-semibold text-ink">{fmtRate(e.rate)}</span> a year per
              10,000 students{' '}
              <span className="text-ink-3 whitespace-nowrap">
                ({levelPct(rules)}% interval {fmtRateAt(e.lo, e.lo4, digits)} to {fmtRateAt(e.hi, e.hi4, digits)})
              </span>
            </span>
            <span>{fmtInt(e.n)} on campus in {windowLabel(windowKey)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-2">
            <VerdictLabel verdict={e.verdict} />
            {e.peerVerdict !== null && e.peerVerdict !== 'withheld' && (
              <span>Against {peerLabel(e.peerType, rules).toLowerCase()} institutions: {VERDICT_SHORT[e.peerVerdict]}</span>
            )}
          </div>
          {status && <p className="text-meta font-semibold text-ink-2">{status}</p>}
        </div>
      </div>
      <CompareButton
        variant="column"
        selected={inCompare}
        name={e.name}
        pressed={inCompare}
        onClick={(ev) => toggleCompare(e.unitid, e.name, ev)}
      />
    </li>
  )
}
