import { useState, useEffect, useMemo, useCallback, Fragment } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
  flexRender,
  SortingState,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, X, ChevronRight } from 'lucide-react'
import { fetchRankings, getMetadata } from '../lib/api'
import type { RankingsData, Metadata, Offense, Verdict } from '../lib/types'
import { cn, formatNumber, formatPercent, groupOffensesByFamily, withParams } from '../lib/utils'
import { VIOLENT, compareText, countHeader, countPhrase } from '../lib/selection'
import {
  chooseWindow, countsOnlyReason, highForSizeNote as countFlagNote, isListCode, rateCodeForSelection, rateCodeLabel,
  rateCodes, windowKeys, windowLabel,
} from '../lib/rates'
import { PLACES_WITHOUT_PRESET, VERDICT_ORDER } from '../lib/rateDisplay'
import SchoolSearch from '../components/SchoolSearch'
import OffensePopover from '../components/OffensePopover'
import SeriesNotes from '../components/SeriesNotes'
import RateRankingsView from '../components/RateRankingsView'
import RowNote, { type RowNoteItem } from '../components/RowNote'
import { CompareButton, Loading } from '../components/ui'

// One row of the count table: a campus
interface Row {
  key: number // campus UNITID
  rank: number // the rank in the file (ties share a rank: 1, 2, 2, 4)
  unitid: number // the school page the row links to
  name: string
  branch: boolean // not the main campus
  campus: string | null // the campus's own DOE name (shown as the title; name stays the sort key)
  campuses: number // the institution's campuses in the United States that year
  count: number
  pct: number // share of the file's total
  fte: number | null
  // The count per 10,000 of its institution's FTE when the pipeline flags it
  // as very high for the institution's size (highForSize)
  highForSize: number | null
}

export default function Rankings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // State
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [data, setData] = useState<RankingsData | null>(null)
  const [sorting, setSorting] = useState<SortingState>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false)
  const [compareSchools, setCompareSchools] = useState<{ unitid: number; name: string }[]>([])
  const [isScrolled, setIsScrolled] = useState(false)

  // Total or rate view, in the address so a view can be cited: ?view=rate
  // (absent: counts). Changed in place, without a new history entry.
  const sortByRate = searchParams.get('view') === 'rate'
  const setSortByRate = (rate: boolean) =>
    setSearchParams((prev) => withParams(prev, { view: rate ? 'rate' : null }), { replace: true })

  // Toggle school in comparison list (max 2)
  const toggleCompare = (unitid: number, name: string, e?: React.MouseEvent) => {
    e?.preventDefault()
    e?.stopPropagation()
    setCompareSchools((prev) => {
      const exists = prev.find((s) => s.unitid === unitid)
      if (exists) {
        return prev.filter((s) => s.unitid !== unitid)
      }
      if (prev.length >= 2) {
        // Replace the oldest selection
        return [...prev.slice(1), { unitid, name }]
      }
      return [...prev, { unitid, name }]
    })
  }

  const isInCompare = useCallback(
    (unitid: number) => compareSchools.some((s) => s.unitid === unitid),
    [compareSchools]
  )

  const goToCompare = () => {
    if (compareSchools.length >= 2) {
      navigate(`/compare?schools=${compareSchools.map((s) => s.unitid).join(',')}`)
    }
  }

  // Get filter values from URL or defaults (default year = newest available)
  const latestYear = metadata?.years?.length ? metadata.years[metadata.years.length - 1] : 2024
  const selectedPreset = searchParams.get('preset') || 'national'
  const selectedYear = parseInt(searchParams.get('year') || '') || latestYear
  // Violent crimes by default: motor vehicle theft, a large share of all
  // criminal offenses (37% in 2024), would otherwise decide most of the
  // order. ?offense=criminal and ?offense=all still work
  const offenseParam = searchParams.get('offense') || VIOLENT
  // The rate view's code criminal_xmvt is criminal offenses in the count view
  const selectedOffense = offenseParam === 'criminal_xmvt' ? 'criminal' : offenseParam

  // Load More state - show 25 initially, +25 per click
  const [displayCount, setDisplayCount] = useState(25)
  const LOAD_MORE_INCREMENT = 25

  // Load metadata on mount
  useEffect(() => {
    getMetadata()
      .then(setMetadata)
      .catch(() => setError('Failed to load data. Please try again.'))
  }, [])

  // Load rankings when filters change
  useEffect(() => {
    if (!metadata) return
    // No file for a place without a preset (?preset=GU): the page says so
    if (!metadata.presets.some((p) => p.id === selectedPreset)) {
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    setError(null)
    setDisplayCount(25) // Reset display count on filter change

    fetchRankings(selectedPreset, selectedYear)
      .then((file) => {
        setData(file)
        setLoading(false)
      })
      .catch(() => {
        setError('Failed to load data. Please try again.')
        setLoading(false)
      })
  }, [selectedPreset, selectedYear, selectedOffense, metadata])

  // Track scroll position to show compact search in sticky bar
  useEffect(() => {
    const handleScroll = () => {
      // Show compact search when scrolled past hero section (~250px)
      setIsScrolled(window.scrollY > 250)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // The rate view (lib/rates.ts, data in rates/*.json): a 3-year window and
  // a rate code. ?window= (default the window ending in ?year=, else the
  // latest), ?offense= read as a rate code (criminal: criminal offenses
  // except motor-vehicle theft; property: burglary) and ?verdict= (filter).
  const rules = metadata?.rateRules
  const rateCode = rules ? rateCodeForSelection(offenseParam, rules) : null
  const rateView = sortByRate && rateCode !== null && !!rules
  const selectedWindow = chooseWindow(rules, searchParams.get('window'), parseInt(searchParams.get('year') || '') || null)
  const verdictParam = searchParams.get('verdict')
  const selectedVerdict = (VERDICT_ORDER as string[]).includes(verdictParam ?? '') ? (verdictParam as Verdict) : null
  const setRateParams = (changes: Record<string, string | null>) =>
    setSearchParams((prev) => withParams(prev, changes), { replace: true })

  // The rows of the count view, in the file's order and with its ranks.
  // Campuses that reported the year but had none of the selection are ranked
  // after the entries with 0, tied: rank = entries + 1, listed by name, then
  // UNITID (the pipeline's tie rule)
  const sortedRankings = useMemo((): Row[] => {
    if (!data) return []
    const total = data.totals[selectedOffense] || 0
    const entries = data.rankings[selectedOffense] || []
    const rows: Row[] = entries.map((e) => {
      const campus = data.campuses[String(e.unitid)]
      const fte = campus?.fte ?? null
      return {
        key: e.unitid,
        rank: e.rank,
        unitid: e.unitid,
        name: campus?.name ?? `School ${e.unitid}`,
        branch: campus ? !campus.main : false,
        campus: campus?.campus ?? null,
        campuses: campus?.campuses ?? 1,
        count: e.count,
        pct: total > 0 ? (e.count / total) * 100 : 0,
        fte,
        highForSize: e.highForSize && fte ? (e.count / fte) * 10000 : null,
      }
    })
    const listed = new Set(entries.map((e) => e.unitid))
    const zeros = Object.entries(data.campuses)
      .map(([id, campus]) => ({ id: Number(id), campus }))
      .filter(({ id }) => !listed.has(id))
      .sort((a, b) => compareText(a.campus.name, b.campus.name) || a.id - b.id)
    zeros.forEach(({ id, campus }) => rows.push({
      key: id,
      rank: entries.length + 1,
      unitid: id,
      name: campus.name,
      branch: !campus.main,
      campus: campus.campus ?? null,
      campuses: campus.campuses,
      count: 0,
      pct: 0,
      fte: campus.fte,
      highForSize: null,
    }))
    return rows
  }, [data, selectedOffense])

  // A row's notes (behind its note button): a count flagged as very high for
  // the institution's size (highForSize), with the reference it is over
  // (metadata.rateRules.countFlag)
  const countRowNotes = useCallback(
    (row: Row): RowNoteItem[] => (row.highForSize !== null
      ? [{ kind: 'attention', text: countFlagNote(row.highForSize, selectedOffense, selectedYear, metadata) }]
      : []),
    [selectedOffense, selectedYear, metadata]
  )

  const displayedRankings = useMemo(() => {
    return sortedRankings.slice(0, displayCount)
  }, [sortedRankings, displayCount])

  // What the rows are
  const rowUnit = 'campuses'

  const hasMoreToLoad = displayCount < sortedRankings.length
  const remainingCount = sortedRankings.length - displayCount

  const loadMore = () => {
    setDisplayCount((prev) => prev + LOAD_MORE_INCREMENT)
  }

  // Update URL when filters change
  const updateFilters = (preset?: string, year?: number, offense?: string) => {
    const params = new URLSearchParams(searchParams)
    if (preset) params.set('preset', preset)
    if (year) params.set('year', year.toString())
    if (offense) params.set('offense', offense)
    setSearchParams(params)
  }

  // Find current offense info
  const currentOffense = metadata?.offenses.find((o) => o.code === selectedOffense)
  const currentTotal = data?.totals[selectedOffense] || 0
  const countLabel = countHeader(currentOffense)

  // Table setup
  const columnHelper = createColumnHelper<Row>()

  const columns = useMemo(
    () => [
      columnHelper.accessor('rank', {
        header: 'Rank',
        cell: (info) => (
          // The published rank by count (ties share a rank)
          <span className="text-ink-3">#{info.getValue()}</span>
        ),
        size: 80,
      }),
      columnHelper.accessor('name', {
        header: 'School',
        cell: (info) => (
          <div className="flex items-start gap-1">
            <span className="min-w-0">
              {/* One link holds the name, the institution and "(Branch)", as before */}
              <Link
                to={`/school/${info.row.original.unitid}`}
                className="group inline-block py-0.5"
              >
                <span className="link-name group-hover:text-accent group-hover:decoration-current">
                  {info.row.original.campus ?? info.getValue()}
                </span>
                {info.row.original.branch && !info.row.original.campus && (
                  <span className="ml-1.5 text-meta text-ink-3">(Branch)</span>
                )}
                {info.row.original.campus && (
                  <span className="block text-meta text-ink-3">{info.getValue()}</span>
                )}
              </Link>
            </span>
            <RowNote
              subject={info.row.original.campus ?? info.getValue()}
              notes={countRowNotes(info.row.original)}
              className="mt-0.5"
            />
          </div>
        ),
      }),
      columnHelper.accessor('count', {
        header: countLabel,
        cell: (info) => (
          <span className="font-semibold text-ink">
            {formatNumber(info.getValue())}
          </span>
        ),
        size: 100,
      }),
        columnHelper.accessor('fte', {
          header: () => (
            <span title="NCES full-time equivalent enrollment of the whole institution (all its campuses), not of this campus">
              Institution FTE
            </span>
          ),
          cell: (info) => {
            const fte = info.getValue()
            return (
              <span className="text-ink-2">
                {fte !== null ? formatNumber(fte) : '—'}
              </span>
            )
          },
          size: 100,
        }),
        columnHelper.accessor('pct', {
          header: '% of Total',
          cell: (info) => (
            <span className="text-ink-2">
              {formatPercent(info.getValue())}
            </span>
          ),
          size: 180,
        }),
      columnHelper.display({
        id: 'compare',
        header: () => (
          <span>Compare</span>
        ),
        cell: (info) => (
          <CompareButton
            selected={isInCompare(info.row.original.unitid)}
            name={info.row.original.campus ?? info.row.original.name}
            onClick={(e) => toggleCompare(info.row.original.unitid, info.row.original.campus ?? info.row.original.name, e)}
            withTitle
            className="-my-1"
          />
        ),
        size: 50,
      }),
    ],
    [columnHelper, isInCompare, countLabel, countRowNotes]
  )

  // The table gets the full list so a column sort orders every campus, not
  // just the rows loaded so far; the rows shown are sliced after sorting.
  const table = useReactTable({
    data: sortedRankings,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const tableRows = table.getRowModel().rows
  // An offense without a rate: why, shown with the disabled Rate button
  const countsOnlyNote = rules && rateCode === null
    ? countsOnlyReason(selectedOffense, currentOffense?.display)
    : null

  // Group offenses by family for dropdown
  const offenseGroups = useMemo(() => {
    if (!metadata) return new Map()
    return groupOffensesByFamily(metadata.offenses)
  }, [metadata])

  // Total school count for hero - use national preset's count (not sum of all presets)
  const totalSchoolCount = useMemo(() => {
    if (!metadata) return 0
    const nationalPreset = metadata.presets.find(p => p.id === 'national')
    return nationalPreset?.schoolCount || 0
  }, [metadata])

  // The filter bar sticks below the site header from sm up; the table's
  // header sticks below the bar, so it needs the bar's height (which changes
  // when the bar wraps or shows the compact search)
  const [filterBar, setFilterBar] = useState<HTMLDivElement | null>(null)
  const [filterBarHeight, setFilterBarHeight] = useState(0)
  useEffect(() => {
    if (!filterBar || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => setFilterBarHeight(filterBar.offsetHeight))
    observer.observe(filterBar)
    return () => observer.disconnect()
  }, [filterBar])

  if (error && !metadata) {
    return (
      <div className="wrap py-12">
        <div className="border-l-2 border-danger pl-4">
          <h3 className="h3 text-danger">Error Loading Data</h3>
          <p className="mt-1 text-body text-ink-2">{error}</p>
          <p className="mt-2 text-meta text-ink-3">
            Make sure the ETL pipeline has been run to generate the JSON data files.
          </p>
        </div>
      </div>
    )
  }

  if (!metadata) {
    return <Loading className="min-h-[60vh]">Loading...</Loading>
  }

  const selectClass = 'control min-w-0 max-w-full'
  const fieldClass = 'flex min-w-0 max-w-full flex-col gap-1'
  const labelClass = 'sr-only sm:not-sr-only label'

  return (
    <div>
      {/* Masthead */}
      <section className="wrap pt-8 pb-5 sm:pt-10 sm:pb-6">
        <h1 className="h1">
          Campus Crime Statistics
        </h1>
        <p className="lede mt-2">
          Explore safety data for{' '}
          <span className="tabular font-semibold text-ink">
            {formatNumber(totalSchoolCount)}
          </span>{' '}
          college campuses
        </p>

        {/* Hero Search */}
        <div className="mt-5">
          <SchoolSearch
            variant="hero"
            compareSchools={compareSchools.map(s => s.unitid)}
            onToggleCompare={toggleCompare}
          />
        </div>
      </section>

      {/* Compact Filter Bar - Sticky from the sm breakpoint up (on a phone
          it would cover much of the screen) */}
      <div ref={setFilterBar} className="border-b border-rule bg-paper sm:sticky sm:top-header sm:z-40">
        <div className="wrap py-3">
          {/* Compact Search - shows when scrolled past hero (sticky bar only) */}
          {isScrolled && (
            <div className="hidden sm:block pb-3 mb-3 border-b border-rule">
              <SchoolSearch
                variant="hero"
                compareSchools={compareSchools.map(s => s.unitid)}
                onToggleCompare={toggleCompare}
                compact
              />
            </div>
          )}
          {/* One row that wraps on narrow screens */}
          <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
            {/* Preset */}
            <div className={fieldClass}>
              <label htmlFor="preset-select" className={labelClass}>Schools</label>
              <select
                id="preset-select"
                value={selectedPreset}
                onChange={(e) => updateFilters(e.target.value)}
                className={selectClass}
              >
                {metadata.presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}
                  </option>
                ))}
                {/* A place asked for in the address that has no preset (?preset=GU): named, not replaced */}
                {!metadata.presets.some((p) => p.id === selectedPreset) && (
                  <option value={selectedPreset}>
                    {(PLACES_WITHOUT_PRESET[selectedPreset] ?? selectedPreset).replace(/^the /, 'The ')}
                  </option>
                )}
              </select>
            </div>

            {rateView && rules ? (
              <>
                {/* Window */}
                <div className={fieldClass}>
                  <label htmlFor="window-select" className={labelClass}>Years</label>
                  <select
                    id="window-select"
                    value={selectedWindow ?? ''}
                    onChange={(e) => setRateParams({ window: e.target.value })}
                    className={selectClass}
                  >
                    {windowKeys(rules).slice().reverse().map((key) => (
                      <option key={key} value={key}>{windowLabel(key)}</option>
                    ))}
                  </select>
                </div>
                {/* Rate code */}
                <div className={fieldClass}>
                  <label htmlFor="rate-code-select" className={labelClass}>Offense</label>
                  <select
                    id="rate-code-select"
                    value={rateCode ?? ''}
                    onChange={(e) => setRateParams({ offense: e.target.value })}
                    className={selectClass}
                  >
                    <optgroup label="With an ordered list">
                      {rateCodes(rules).filter((c) => isListCode(c, rules)).map((c) => (
                        <option key={c} value={c}>{rateCodeLabel(c)}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Rates without a list">
                      {rateCodes(rules).filter((c) => !isListCode(c, rules)).map((c) => (
                        <option key={c} value={c}>{rateCodeLabel(c)}</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
              </>
            ) : (
              <>
                {/* Year */}
                <div className={fieldClass}>
                  <label htmlFor="year-select" className={labelClass}>Year</label>
                  <select
                    id="year-select"
                    value={selectedYear}
                    onChange={(e) => updateFilters(undefined, parseInt(e.target.value))}
                    className={selectClass}
                  >
                    {metadata.years
                      .slice()
                      .reverse()
                      .map((year) => (
                        <option key={year} value={year}>
                          {year}
                        </option>
                      ))}
                  </select>
                </div>
                {/* Offense */}
                <div className={fieldClass}>
                  <label htmlFor="offense-select" className={labelClass}>Offense</label>
                  <div className="flex min-w-0 max-w-full items-center gap-1">
                    <select
                      id="offense-select"
                      value={selectedOffense}
                      onChange={(e) => updateFilters(undefined, undefined, e.target.value)}
                      className={selectClass}
                    >
                      {Array.from(offenseGroups.entries()).map(([family, offenses]) => (
                        <optgroup key={family} label={family}>
                          {offenses.map((offense: Offense) => (
                            <option key={offense.code} value={offense.code}>
                              {offense.display}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    {currentOffense && (
                      <OffensePopover offense={currentOffense} />
                    )}
                  </div>
                </div>
              </>
            )}

            {/* Total or rate */}
            <div role="group" aria-label="View" className="segmented h-9 items-stretch">
              <button
                type="button"
                onClick={() => setSortByRate(false)}
                aria-pressed={!rateView}
              >
                Total
              </button>
              <button
                type="button"
                onClick={() => setSortByRate(true)}
                disabled={rateCode === null}
                aria-pressed={rateView}
                aria-describedby={countsOnlyNote ? 'counts-only-note' : undefined}
              >
                Rate
              </button>
            </div>

            {/* Spacer */}
            <div className="hidden sm:block flex-1" />

            {/* Summary Toggle (counts) */}
            {!rateView && (
              <button
                type="button"
                onClick={() => setIsSummaryExpanded(!isSummaryExpanded)}
                aria-expanded={isSummaryExpanded}
                aria-controls="rankings-summary"
                className="hidden sm:inline-flex h-9 items-center gap-1 rounded px-2 text-meta text-ink-2 hover:bg-subtle hover:text-ink"
              >
                <span className="tabular">{formatNumber(currentTotal)} total</span>
                <ChevronRight aria-hidden="true" className={cn(
                  'w-4 h-4 transition-transform',
                  isSummaryExpanded && 'rotate-90'
                )} />
              </button>
            )}
          </div>
          {countsOnlyNote && (
            <p id="counts-only-note" className="mt-2 text-meta text-ink-2">
              No rate: {countsOnlyNote}
            </p>
          )}

          {/* Expandable Summary - Desktop only */}
          {isSummaryExpanded && !rateView && (
            <div id="rankings-summary" className="hidden sm:block mt-3 border-t border-rule pt-2">
              <div className="flex items-center gap-6 text-meta">
                <div>
                  <span className="text-ink-3">Showing: </span>
                  <span className="tabular font-semibold text-ink">{formatNumber(sortedRankings.length)} {rowUnit}</span>
                </div>
                <div>
                  <span className="text-ink-3">{countLabel === 'Total' ? 'Total' : `Total ${countLabel.toLowerCase()}`}: </span>
                  <span className="tabular font-semibold text-ink">{formatNumber(currentTotal)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div
        className="wrap pt-4 sm:pt-5"
        style={{ '--table-top': `calc(var(--header-h) + ${filterBarHeight}px)` } as React.CSSProperties}
      >
        {/* Size-bias note (shown when viewing by Total) */}
        {!rateView && (
          <p className="mb-3 max-w-prose text-meta text-ink-2">
            Larger schools report more incidents because they are larger
            {rateCode !== null && <> (use "Rate" for 3-year rates per 10,000 on-campus students)</>}. Lower numbers
            may reflect reporting differences, not safety.
            {' '}<Link to="/about" className="link">Learn more</Link>
          </p>
        )}

        {/* Comparability note for the selected year (data/seriesNotes.ts) */}
        {!rateView && <SeriesNotes years={[selectedYear]} className="mb-3" />}
        {/* Rate view (rates/*.json) */}
        {rateView && rateCode && selectedWindow ? (
          <RateRankingsView
            metadata={metadata}
            preset={selectedPreset}
            windowKey={selectedWindow}
            code={rateCode}
            verdict={selectedVerdict}
            onVerdict={(v) => setRateParams({ verdict: v })}
            peerType={searchParams.get('type')}
            onPeerType={(t) => setRateParams({ type: t })}
            isInCompare={isInCompare}
            toggleCompare={toggleCompare}
          />
        ) : (<>
        {/* Rankings Table (Desktop) / Cards (Mobile) */}
        <div>
          {!metadata.presets.some((p) => p.id === selectedPreset) ? (
            <p className="border-t border-rule py-6 text-body text-ink-2">
              {PLACES_WITHOUT_PRESET[selectedPreset]
                ? <><strong className="font-semibold text-ink">{PLACES_WITHOUT_PRESET[selectedPreset].replace(/^the /, 'The ')}</strong> has no ranking on this site.</>
                : <><strong className="font-semibold text-ink">{selectedPreset}</strong> is not a state, territory or group on this site.</>}{' '}
              Rankings and rates cover institutions in the 50 states, the District of Columbia, Puerto Rico and the
              U.S. Virgin Islands.{' '}
              <Link to="/" className="link">See all schools</Link>
            </p>
          ) : loading ? (
            <Loading className="min-h-[400px]">Loading rankings...</Loading>
          ) : error ? (
            <p className="border-t border-rule py-6 text-body text-danger">{error}</p>
          ) : sortedRankings.length === 0 ? (
            <p className="border-t border-rule py-6 text-body text-ink-2">
              No data available for {currentOffense?.display || selectedOffense} in{' '}
              {selectedYear}
            </p>
          ) : (
            <>
              {/* Mobile Card View */}
              <div className="sm:hidden">
                {/* Mobile header row */}
                <div className="flex items-end justify-between border-b border-ink/70 pb-1.5 text-meta text-ink-2">
                  <span className="tabular">
                    Showing {formatNumber(displayedRankings.length)} of {formatNumber(sortedRankings.length)} {rowUnit}
                  </span>
                  <span className="w-12 text-center">
                    Compare
                  </span>
                </div>
                <div className="divide-y divide-rule border-b border-rule">
                {displayedRankings.map((item) => (
                  <Fragment key={item.key}>
                  <div className="flex items-stretch">
                    {/* The name's link covers the whole card (its ::after), so the
                        card is one tap target and the note button can sit beside
                        the name without being inside the link */}
                    <div className="relative flex min-w-0 flex-1 gap-3 py-3 pr-2 hover:bg-subtle">
                      <span className="tabular w-8 flex-shrink-0 pt-px text-right text-meta text-ink-3">
                        {item.rank}
                      </span>
                      <div className="min-w-0">
                        <span className="min-w-0 font-semibold text-ink">
                          <Link
                            to={`/school/${item.unitid}`}
                            className="after:absolute after:inset-0 focus:outline-none focus-visible:after:outline focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-accent"
                          >
                            {item.campus ?? item.name}
                          </Link>
                          {item.branch && !item.campus && (
                            <span className="ml-1.5 text-meta font-normal text-ink-3">(Branch)</span>
                          )}
                          <RowNote subject={item.campus ?? item.name} notes={countRowNotes(item)} className="z-10 ml-1" />
                          {item.campus && (
                            <span className="block text-meta font-normal text-ink-3">{item.name}</span>
                          )}
                        </span>
                        <div className="tabular mt-1 flex flex-wrap items-baseline gap-x-2 text-meta text-ink-2">
                          <span className="font-semibold text-ink">
                            {countPhrase(item.count, currentOffense, formatNumber(item.count))}
                          </span>
                          {item.fte && (
                            <>
                              <span className="text-ink-3" aria-hidden="true">&middot;</span>
                              <span>
                                {formatNumber(item.fte)} FTE (institution)
                              </span>
                            </>
                          )}
                          <span className="text-ink-3" aria-hidden="true">&middot;</span>
                          <span>
                            {formatPercent(item.pct)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <CompareButton
                      variant="column"
                      selected={isInCompare(item.unitid)}
                      name={item.campus ?? item.name}
                      onClick={(e) => toggleCompare(item.unitid, item.campus ?? item.name, e)}
                    />
                  </div>
                  </Fragment>
                ))}
                </div>
              </div>

              {/* Desktop Table View */}
              <div className="hidden sm:block">
                {/* Desktop header row */}
                <p className="tabular mb-1 text-meta text-ink-3">
                  Showing {formatNumber(displayedRankings.length)} of {formatNumber(sortedRankings.length)} {rowUnit}
                </p>
                <div className="overflow-x-auto lg:overflow-visible">
                <table className="data-table">
                  <thead>
                    {table.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id}>
                        {headerGroup.headers.map((header) => (
                          <th
                            key={header.id}
                            className={cn(
                              COLUMN_CLASS[header.column.id],
                              'cursor-pointer select-none hover:text-ink',
                              header.column.getIsSorted() && 'text-ink'
                            )}
                            onClick={header.column.getToggleSortingHandler()}
                            aria-sort={
                              header.column.getIsSorted() === 'asc' ? 'ascending'
                                : header.column.getIsSorted() === 'desc' ? 'descending'
                                : undefined
                            }
                          >
                            <div className={cn(
                              'flex items-center gap-1',
                              NUMERIC_COLUMNS.has(header.column.id) && 'flex-row-reverse',
                              header.column.id === 'compare' && 'justify-center'
                            )}>
                              {flexRender(
                                header.column.columnDef.header,
                                header.getContext()
                              )}
                              {header.column.getIsSorted() === 'asc' ? (
                                <ChevronUp className="w-4 h-4" aria-hidden="true" />
                              ) : header.column.getIsSorted() === 'desc' ? (
                                <ChevronDown className="w-4 h-4" aria-hidden="true" />
                              ) : header.column.id !== 'compare' ? (
                                <div className="w-4 h-4" />
                              ) : null}
                            </div>
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody>
                    {tableRows.slice(0, displayCount).map((row) => (
                      <Fragment key={row.id}>
                        <tr>
                          {row.getVisibleCells().map((cell) => (
                            <td key={cell.id} className={COLUMN_CLASS[cell.column.id]}>
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </td>
                          ))}
                        </tr>
                      </Fragment>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>

              {/* Load More Button */}
              {hasMoreToLoad && (
                <div className="py-5 text-center">
                  <button
                    type="button"
                    onClick={loadMore}
                    className="btn"
                  >
                    Load {formatNumber(Math.min(LOAD_MORE_INCREMENT, remainingCount))} More
                    <span className="tabular font-normal text-ink-3">
                      ({formatNumber(remainingCount)} remaining)
                    </span>
                  </button>
                </div>
              )}

              {/* Showing count footer */}
              {!hasMoreToLoad && sortedRankings.length > 25 && (
                <p className="tabular py-5 text-center text-meta text-ink-3">
                  Showing all {formatNumber(sortedRankings.length)} {rowUnit}
                </p>
              )}
            </>
          )}
        </div>
        </>)}

        {/* Data Note */}
        <p className="mt-6 max-w-prose text-meta text-ink-3">
          <span className="font-semibold text-ink-2">Note:</span> {metadata.note}
        </p>
      </div>

      {/* Floating Compare Bar */}
      {compareSchools.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-rule-strong/60 bg-surface shadow-pop">
          <div className="wrap py-2.5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <div className="flex min-w-0 items-center gap-2 overflow-x-auto">
                  {compareSchools.map((school, idx) => (
                    <div key={school.unitid} className="flex items-center gap-2">
                      {idx > 0 && <span className="text-meta text-ink-3">vs</span>}
                      <span className="inline-flex items-center gap-0.5 whitespace-nowrap rounded border border-rule-strong/60 py-0.5 pl-2 pr-0.5 text-meta font-semibold text-ink">
                        {school.name.length > 20 ? school.name.slice(0, 20) + '...' : school.name}
                        <button
                          type="button"
                          onClick={() => toggleCompare(school.unitid, school.name)}
                          className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-ink-3 hover:bg-subtle hover:text-ink"
                          aria-label={`Remove ${school.name} from comparison`}
                        >
                          <X className="w-3.5 h-3.5" aria-hidden="true" />
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
                {compareSchools.length === 1 && (
                  <span className="whitespace-nowrap text-meta text-ink-3">
                    Select 1 more
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={goToCompare}
                disabled={compareSchools.length < 2}
                className="btn-primary flex-shrink-0"
              >
                Compare
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Column widths and alignment of the count table; the school column takes
// the rest of the width
const NUMERIC_COLUMNS = new Set(['rank', 'count', 'fte', 'pct'])
const COLUMN_CLASS: Record<string, string> = {
  rank: 'num w-[4.5rem]',
  name: 'min-w-[16rem]',
  count: 'num w-[7.5rem]',
  fte: 'num w-[8.5rem]',
  pct: 'num w-[7rem]',
  compare: 'w-[5.5rem] text-center',
}
