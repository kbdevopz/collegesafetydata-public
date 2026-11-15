import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Check, GitCompare, Info, Loader2, Plus } from 'lucide-react'
import { fetchPresets, fetchRateWindow } from '../lib/api'
import type { Metadata, RateRules, RateWindowEntry, RateWindowFile, Verdict } from '../lib/types'
import {
  entryPosition, fmtInt, fmtRate, isListCode, isWithheld, levelPct, listMinStudents, nationalCompositionSentence,
  nationalSentence, offenseCount, ordinal, peerLabel, rateCodeLabel, rateCodePhrase, roundedTieSentence,
  sharedShortNotes, windowLabel,
} from '../lib/rates'
import {
  PLACES_WITHOUT_PRESET, RATE_IS_NOT, RATE_MEASURE, stateDisplayMin, VERDICT_ORDER, VERDICT_SHORT,
} from '../lib/rateDisplay'
import { cn } from '../lib/utils'
import { VerdictLabel } from './RateCard'

const PAGE = 50

interface Props {
  metadata: Metadata
  preset: string
  windowKey: string
  code: string
  verdict: Verdict | null
  onVerdict: (v: Verdict | null) => void
  isInCompare: (unitid: number) => boolean
  toggleCompare: (unitid: number, name: string, e?: React.MouseEvent) => void
}

/**
 * The Rankings page's rate view: one window and rate code. For the three
 * list codes, the ordered national list (or a state's own list when it has
 * enough members); then every rated institution of the selection by name,
 * with its rate, interval and comparisons.
 */
export default function RateRankingsView({
  metadata, preset, windowKey, code, verdict, onVerdict, isInCompare, toggleCompare,
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

  const scoped = useMemo(() => {
    if (!file) return []
    if (isState) return file.entries.filter((e) => e.state === preset)
    if (isGroup) return ivyIds ? file.entries.filter((e) => ivyIds.has(e.id)) : []
    return file.entries
  }, [file, isState, isGroup, ivyIds, preset])

  const byVerdict = (e: RateWindowEntry) => verdict === null || e.verdict === verdict
  const listed = scoped.filter((e) => e.listed)
  const stateMembers = isState ? file?.stateLists?.[preset] ?? 0 : 0
  const minState = stateDisplayMin(rules)
  const useStatePositions = isState && minState !== null && stateMembers >= minState
  const byName = useMemo(
    () => scoped.slice().sort((a, b) => a.name.localeCompare(b.name, 'en-US') || a.id - b.id),
    [scoped],
  )
  const tally = useMemo(() => {
    const t: Partial<Record<Verdict, number>> = {}
    for (const e of scoped) t[e.verdict] = (t[e.verdict] ?? 0) + 1
    return t
  }, [scoped])

  // A place outside the rates' states and territories, or no known selection
  if (preset !== 'national' && !presetKnown) {
    return (
      <section className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-sm text-blue-900 dark:text-blue-100 space-y-2">
        <p className="flex items-start gap-2">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            {PLACES_WITHOUT_PRESET[preset]
              ? <><strong>{presetName}:</strong> institutions there are not rated.</>
              : <><strong>{preset}</strong> is not a state, territory or group on this site, so no institution is shown.</>}{' '}
            Rates cover institutions in the 50 states, the District of Columbia, Puerto Rico and the U.S. Virgin
            Islands.{' '}
            <Link to={`/?view=rate&window=${windowKey}&offense=${code}`} className="underline">See the national rates</Link>
          </span>
        </p>
      </section>
    )
  }

  if (error) {
    return (
      <div className="p-6 text-center">
        <AlertCircle className="w-8 h-8 text-red-500 dark:text-red-400 mx-auto mb-2" aria-hidden="true" />
        <p className="text-red-700 dark:text-red-400">Failed to load the rates. Please try again.</p>
      </div>
    )
  }
  if (!file || (isGroup && !ivyIds)) {
    return (
      <div className="flex flex-col items-center justify-center py-16 min-h-[300px]">
        <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" aria-hidden="true" />
        <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading rates...</span>
      </div>
    )
  }

  const listN = file.list?.n ?? 0
  const minStudents = file.list ? listMinStudents(file.list.minFteYears, rules) : null
  const shownList = listed.filter(byVerdict)
  const shownAll = byName.filter(byVerdict)
  const example = (useStatePositions ? listed.filter((e) => e.statePosition !== undefined) : listed)[Math.min(11, listed.length - 1)]
  const composition = nationalCompositionSentence(code, file.composition, windowKey)
  const level = levelPct(rules)

  return (
    <div className="space-y-4">
      {/* What the rates are and who is on the list */}
      <section className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-sm text-blue-900 dark:text-blue-100 space-y-2">
        <p className="flex items-start gap-2">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            <strong>{rateCodeLabel(code)}, {windowLabel(windowKey)}.</strong> {RATE_MEASURE} {RATE_IS_NOT} Rates are
            per institution (all its campuses in the United States), because NCES counts enrollment per institution.
          </span>
        </p>
        {listCode && file.list ? (
          <>
            <p>
              <strong>Who is on the list:</strong> the {fmtInt(listN)} rated institutions expected, at the national
              rate, to have at least {file.list.minExpected} on-campus {rateCodePhrase(code)} over the three years, which
              takes about {fmtInt(minStudents ?? 0)} or more on-campus students. Institutions whose on-campus student
              count is uncertain, whose count includes many incidents at a medical-center campus, or that are not
              compared because they share a campus site with another institution, are not on it. The list is ordered by
              rate, highest first.
            </p>
            <p>
              Each position comes with a range: with {level}% confidence the institution's position among these{' '}
              {fmtInt(listN)} is within it. This holds for each institution on its own, not for the whole list at once.
              Two institutions whose ranges overlap may still differ, and positions closer together than these ranges
              cannot be told apart.
              {example && example.position !== undefined && example.rankLo !== undefined && example.rankHi !== undefined && (
                <> For example, {example.name} is {ordinal(example.position)} nationally: its position among the{' '}
                {fmtInt(listN)} could be anywhere from {ordinal(example.rankLo)} to {ordinal(example.rankHi)}.</>
              )}
            </p>
          </>
        ) : (
          <p>
            This rate has no ordered list. Institutions are shown by name with their rates and their comparisons with
            the national rate and with institutions of the same type.
          </p>
        )}
        <p>{nationalSentence(file.natl, windowKey, rules)}</p>
        {listCode && (
          <p>
            The order depends on counting only on-campus incidents (counting all locations changes it) and on the size
            threshold. An institution's position can change substantially between windows five years apart.{' '}
            <Link to="/methodology#rates" className="underline">Methodology</Link>
          </p>
        )}
        {composition && <p>{composition}</p>}
      </section>

      {/* Verdict filter */}
      <div role="group" aria-label="Filter by comparison with the national rate" className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-600 dark:text-gray-400">Compared with the national rate:</span>
        <FilterChip pressed={verdict === null} onClick={() => onVerdict(null)}>All ({fmtInt(scoped.length)})</FilterChip>
        {VERDICT_ORDER.filter((v) => (tally[v] ?? 0) > 0 || (v !== 'undetermined' && v !== 'withheld')).map((v) => (
          <FilterChip key={v} pressed={verdict === v} onClick={() => onVerdict(verdict === v ? null : v)}>
            {VERDICT_SHORT[v].charAt(0).toUpperCase() + VERDICT_SHORT[v].slice(1)} ({fmtInt(tally[v] ?? 0)})
          </FilterChip>
        ))}
      </div>

      {/* The ordered list */}
      {listCode && file.list && (
        <section className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800" aria-labelledby="rate-list-heading">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800">
            <h2 id="rate-list-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
              {preset === 'national'
                ? `Ordered list: ${fmtInt(listN)} institutions`
                : useStatePositions
                  ? `${presetName}: ${fmtInt(stateMembers)} institutions on the national list, with their positions in ${presetName}`
                  : `${presetName}: institutions on the national list`}
            </h2>
            {isState && !useStatePositions && (
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                {stateMembers === 0
                  ? `None of the ${fmtInt(listN)} institutions on the national list is in ${presetName}.`
                  : `${fmtInt(stateMembers)} of the ${fmtInt(listN)} institutions on the national list ${stateMembers === 1 ? 'is' : 'are'} in ${presetName}. ` +
                    (minState !== null ? `A state's own positions are shown when it has at least ${minState} institutions on the list, so ` : '') +
                    `${minState !== null ? '' : 'Here '}${stateMembers === 1 ? 'its national position is' : 'their national positions are'} shown.`}{' '}
                {stateMembers > 0 && (
                  <Link to={`/?view=rate&window=${windowKey}&offense=${code}`} className="text-primary-600 dark:text-primary-400 underline">
                    See the national list
                  </Link>
                )}
              </p>
            )}
            {isGroup && (
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                {listed.length} of the {fmtInt(listN)} institutions on the national list {listed.length === 1 ? 'is' : 'are'} in this group; their national positions are shown.
              </p>
            )}
          </div>
          {shownList.length === 0 ? (
            <p className="p-4 text-sm text-gray-600 dark:text-gray-400">
              {listed.length === 0 ? 'No institution here is on the list.' : 'No institution on the list matches this filter.'}
            </p>
          ) : (
            <ol className="divide-y divide-gray-100 dark:divide-gray-800">
              {shownList.map((e) => (
                <EntryRow
                  key={e.id}
                  e={e}
                  code={code}
                  rules={rules}
                  listN={listN}
                  windowKey={windowKey}
                  natl={file.natl}
                  position={useStatePositions ? 'state' : 'national'}
                  isInCompare={isInCompare}
                  toggleCompare={toggleCompare}
                />
              ))}
            </ol>
          )}
        </section>
      )}

      {/* Every rated institution of the selection, by name */}
      <section className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800" aria-labelledby="rate-all-heading">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800">
          <h2 id="rate-all-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Every institution with a {windowLabel(windowKey)} rate{preset === 'national' ? '' : ` in ${presetName}`}:{' '}
            {fmtInt(scoped.length)}
          </h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Listed by name. A rate needs an institution in the 50 states, DC, Puerto Rico or the U.S. Virgin Islands
            that is in DOE's data all three years, has at least {fmtInt(rules.minFte)} on-campus students in each of
            them, and is under none of the rules that give no rate (for example a hospital, or a main campus whose
            incidents cannot be assigned to one of the institutions sharing it). Institutions without a rate are not
            in this table; each one's page says why.
          </p>
        </div>
        {shownAll.length === 0 ? (
          <p className="p-4 text-sm text-gray-600 dark:text-gray-400">No institution matches this filter.</p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {shownAll.slice(0, shown).map((e) => (
              <EntryRow
                key={e.id}
                e={e}
                code={code}
                rules={rules}
                listN={listN}
                windowKey={windowKey}
                natl={file.natl}
                position="status"
                isInCompare={isInCompare}
                toggleCompare={toggleCompare}
              />
            ))}
          </ul>
        )}
        {shownAll.length > shown && (
          <div className="p-4 border-t border-gray-100 dark:border-gray-800 text-center">
            <button
              type="button"
              onClick={() => setShown((s) => s + PAGE)}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-medium transition-colors"
            >
              <Plus className="w-4 h-4" aria-hidden="true" />
              Show {Math.min(PAGE, shownAll.length - shown)} more
              <span className="text-gray-500 dark:text-gray-400 text-sm">({fmtInt(shownAll.length - shown)} remaining)</span>
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

function FilterChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 text-xs font-medium rounded-full border transition-colors',
        pressed
          ? 'bg-primary-600 text-white border-primary-600 dark:bg-primary-500 dark:border-primary-500'
          : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
      )}
    >
      {children}
    </button>
  )
}

/** Why a rated entry is not on the list, short */
function notListedShort(e: RateWindowEntry, rules: RateRules, listN: number): string {
  if (e.why === 'online') return 'Not on the list: uncertain on-campus student count'
  if (e.why === 'medical_campus') return `Not on the list: ${fmtInt(e.medical ?? 0)} of ${fmtInt(e.n)} at a medical-center campus`
  return `Not on the list of ${fmtInt(listN)}: fewer than ${rules.lists?.minExpected ?? 20} incidents expected at the national rate`
}

function EntryRow({
  e, code, rules, listN, windowKey, natl, position, isInCompare, toggleCompare,
}: {
  e: RateWindowEntry
  code: string
  rules: RateRules
  listN: number
  windowKey: string
  // The national rate shown above the list
  natl: number
  // national or state position first (lists), or the list status (by-name table)
  position: 'national' | 'state' | 'status'
  isInCompare: (unitid: number) => boolean
  toggleCompare: (unitid: number, name: string, ev?: React.MouseEvent) => void
}) {
  const listCode = isListCode(code, rules)
  const national = entryPosition(e, listN)
  const state = entryPosition(e, null, true)
  const head = position === 'state' ? state : position === 'national' ? national : null
  const notes: string[] = []
  const tie = roundedTieSentence(e, e.verdict, natl, 'the national rate', true)
  if (tie) notes.push(tie)
  if (position === 'state' && national) notes.push(`National list: ${national}`)
  // Shared campus sites: why it is not compared (first, when it is not), host and co-located notes
  const site = sharedShortNotes(e, e, rules)
  if (position === 'status' && listCode) {
    if (e.listed && national) notes.push(`On the list: ${national}`)
    else if (isWithheld(e)) notes.push(`Not on the list. ${site.shift() ?? ''}`)
    else notes.push(notListedShort(e, rules, listN))
  }
  if (e.verdict === 'undetermined' && e.verdictLargerFte && e.verdictSmallerFte) {
    notes.push(`Not determined: ${VERDICT_SHORT[e.verdictLargerFte]} with the larger estimate of on-campus students, ${VERDICT_SHORT[e.verdictSmallerFte]} with the smaller`)
  } else if (e.why === 'online') {
    notes.push('Two estimates of on-campus students; the comparison is the same with either')
  }
  if ((e.medical ?? 0) > 0 && !(position === 'status' && e.why === 'medical_campus')) notes.push(`${fmtInt(e.medical ?? 0)} of the ${fmtInt(e.n)} at a medical-center campus`)
  notes.push(...site)
  const more = e.nNoncampus + e.nPublic
  if (more > 0) notes.push(`${fmtInt(more)} more at non-campus locations or on public property (not in the rate)`)
  if (e.composition && code === 'violent') {
    notes.push(['rape', 'aggravated_assault', 'robbery', 'murder'].filter((o) => e.composition?.[o] !== undefined)
      .map((o) => offenseCount(e.composition?.[o] ?? 0, o)).join(', '))
  }
  if (e.composition && code === 'criminal_xmvt' && e.composition.motor_vehicle_theft !== undefined) {
    notes.push(`Not in the rate: ${offenseCount(e.composition.motor_vehicle_theft, 'motor_vehicle_theft')} on campus`)
  }
  const flags = (e.flags ?? []).map((f) =>
    `Unusual year ${f.year}: ${offenseCount(f.count, f.offense)} on campus (median of other years ${f.usual.toLocaleString('en-US')})`)
  if (e.verdictWithoutFlagged) flags.push(`Counting the flagged ${flags.length === 1 ? 'year' : 'years'} at the median: ${VERDICT_SHORT[e.verdictWithoutFlagged]}`)
  const inCompare = isInCompare(e.unitid)
  return (
    <li className="flex items-stretch">
      <div className="flex-1 min-w-0 p-3 sm:p-4 flex flex-col sm:flex-row gap-2 sm:gap-4">
        {head !== null && (
          <div className="sm:w-48 flex-shrink-0 text-sm text-gray-900 dark:text-gray-100">
            <span className="font-semibold">{head.split(';')[0]}</span>
            {head.includes(';') && <span className="text-gray-600 dark:text-gray-400">;{head.slice(head.indexOf(';') + 1)}</span>}
          </div>
        )}
        <div className="flex-1 min-w-0 space-y-1">
          <div>
            <Link to={`/school/${e.unitid}`} className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300">
              {e.name}
            </Link>
            <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">{e.state}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-700 dark:text-gray-300">
            <span>
              <span className="font-semibold tabular-nums text-gray-900 dark:text-gray-100">{fmtRate(e.rate)}</span> a year per
              10,000 students <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">({levelPct(rules)}% interval {fmtRate(e.lo)} to {fmtRate(e.hi)})</span>
            </span>
            <span className="tabular-nums">{fmtInt(e.n)} on campus in {windowLabel(windowKey)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <VerdictLabel verdict={e.verdict} />
            {e.peerVerdict !== null && e.peerVerdict !== 'withheld' && (
              <span>Against {peerLabel(e.peerType, rules).toLowerCase()} institutions: {VERDICT_SHORT[e.peerVerdict]}</span>
            )}
          </div>
          {notes.map((n) => <p key={n} className="text-xs text-gray-600 dark:text-gray-400">{n}</p>)}
          {flags.map((f) => <p key={f} className="text-xs text-amber-800 dark:text-amber-300">{f}</p>)}
        </div>
      </div>
      <button
        type="button"
        onClick={(ev) => toggleCompare(e.unitid, e.name, ev)}
        className={cn(
          'flex items-center justify-center w-12 border-l transition-colors flex-shrink-0',
          inCompare
            ? 'bg-primary-50 dark:bg-primary-900/30 border-primary-200 dark:border-primary-800 text-primary-600 dark:text-primary-400'
            : 'border-gray-100 dark:border-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50'
        )}
        aria-label={inCompare ? `Remove ${e.name} from comparison` : `Add ${e.name} to comparison`}
        aria-pressed={inCompare}
      >
        {inCompare ? <Check className="w-5 h-5" aria-hidden="true" /> : <GitCompare className="w-5 h-5" aria-hidden="true" />}
      </button>
    </li>
  )
}
