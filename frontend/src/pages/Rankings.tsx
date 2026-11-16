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
import { ChevronUp, ChevronDown, ExternalLink, AlertCircle, Loader2, MapPin, Calendar, AlertTriangle, Plus, Check, GitCompare, X, ChevronRight } from 'lucide-react'
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

  // The note of a count flagged as very high for the institution's size
  // (highForSize), with the reference it is over (metadata.rateRules.countFlag)
  const highForSizeNote = useCallback(
    (perTenK: number) => countFlagNote(perTenK, selectedOffense, selectedYear, metadata),
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
          <span className="font-medium text-gray-500 dark:text-gray-400">#{info.getValue()}</span>
        ),
        size: 80,
      }),
      columnHelper.accessor('name', {
        header: 'School',
        cell: (info) => (
          <div>
          <Link
            to={`/school/${info.row.original.unitid}`}
            className="group flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium"
          >
            <span className="flex flex-col">
              <span>{info.row.original.campus ?? info.getValue()}</span>
              {info.row.original.campus && (
                <span className="text-xs font-normal text-gray-500 dark:text-gray-400">{info.getValue()}</span>
              )}
            </span>
            {info.row.original.branch && !info.row.original.campus && (
              <span className="text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
            )}
            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
          </Link>
          {info.row.original.highForSize !== null && (
            <span className="block text-xs text-amber-700 dark:text-amber-400 mt-0.5 max-w-xl">
              {highForSizeNote(info.row.original.highForSize)}
            </span>
          )}
          </div>
        ),
      }),
      columnHelper.accessor('count', {
        header: countLabel,
        cell: (info) => (
          <span className="font-semibold tabular-nums">
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
              <span className="text-gray-600 dark:text-gray-400 tabular-nums text-sm">
                {fte !== null ? formatNumber(fte) : '—'}
              </span>
            )
          },
          size: 100,
        }),
        columnHelper.accessor('pct', {
          header: '% of Total',
          cell: (info) => (
            <div className="flex items-center gap-2">
              <div className="w-24 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary-500 dark:bg-primary-400 rounded-full"
                  style={{ width: `${Math.min(info.getValue(), 100)}%` }}
                />
              </div>
              <span className="text-gray-600 dark:text-gray-400 tabular-nums text-sm">
                {formatPercent(info.getValue())}
              </span>
            </div>
          ),
          size: 180,
        }),
      columnHelper.display({
        id: 'compare',
        header: () => (
          <span className="flex items-center gap-1 text-xs">
            <GitCompare className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">Compare</span>
          </span>
        ),
        cell: (info) => (
          <button
            type="button"
            onClick={(e) => toggleCompare(info.row.original.unitid, info.row.original.campus ?? info.row.original.name, e)}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              isInCompare(info.row.original.unitid)
                ? 'bg-primary-100 dark:bg-primary-900/50 text-primary-600 dark:text-primary-400'
                : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
            )}
            aria-label={isInCompare(info.row.original.unitid)
              ? `Remove ${info.row.original.campus ?? info.row.original.name} from comparison`
              : `Add ${info.row.original.campus ?? info.row.original.name} to comparison`}
            title={isInCompare(info.row.original.unitid) ? 'Remove from comparison' : 'Add to comparison'}
          >
            {isInCompare(info.row.original.unitid) ? (
              <Check className="w-4 h-4" />
            ) : (
              <GitCompare className="w-4 h-4" />
            )}
          </button>
        ),
        size: 50,
      }),
    ],
    [columnHelper, isInCompare, countLabel, highForSizeNote]
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

  if (error && !metadata) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-6 flex items-start gap-4">
          <AlertCircle className="w-6 h-6 text-red-500 dark:text-red-400 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-red-800 dark:text-red-300">Error Loading Data</h3>
            <p className="text-red-700 dark:text-red-400 mt-1">{error}</p>
            <p className="text-red-600 dark:text-red-500 text-sm mt-2">
              Make sure the ETL pipeline has been run to generate the JSON data files.
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!metadata) {
    return (
      <div className="container mx-auto px-4 py-12 flex flex-col justify-center items-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" />
        <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading...</span>
      </div>
    )
  }

  return (
    <div>
      {/* Hero Section */}
      <section className="bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-700 transition-colors duration-200">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 text-center">
          {/* Headline */}
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900 dark:text-gray-100 mb-1 sm:mb-2">
            Campus Crime Statistics
          </h1>
          <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400 mb-4 sm:mb-5 max-w-2xl mx-auto">
            Explore safety data for{' '}
            <span className="font-semibold text-gray-900 dark:text-gray-100">
              {formatNumber(totalSchoolCount)}
            </span>{' '}
            college campuses
          </p>

          {/* Hero Search */}
          <div className="mb-2 sm:mb-4 px-4">
            <SchoolSearch
              variant="hero"
              compareSchools={compareSchools.map(s => s.unitid)}
              onToggleCompare={toggleCompare}
            />
          </div>

        </div>
      </section>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
        {/* Compact Filter Bar - Sticky from the sm breakpoint up (on a phone
            it would cover much of the screen) */}
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 mb-4 transition-colors duration-200 sm:sticky sm:top-16 sm:z-40">
          <div className="p-3 sm:p-4">
            {/* Compact Search - shows when scrolled past hero (sticky bar only) */}
            {isScrolled && (
              <div className="hidden sm:block pb-3 mb-3 border-b border-gray-200 dark:border-gray-700">
                <SchoolSearch
                  variant="hero"
                  compareSchools={compareSchools.map(s => s.unitid)}
                  onToggleCompare={toggleCompare}
                  compact
                />
              </div>
            )}
            {/* One row that wraps on narrow screens */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              {/* Preset */}
              <div className="flex items-center gap-1.5 min-w-0 max-w-full">
                <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                <label htmlFor="preset-select" className="sr-only">Schools</label>
                <select
                  id="preset-select"
                  value={selectedPreset}
                  onChange={(e) => updateFilters(e.target.value)}
                  className="min-w-0 max-w-full text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                    <label htmlFor="window-select" className="sr-only">Years</label>
                    <select
                      id="window-select"
                      value={selectedWindow ?? ''}
                      onChange={(e) => setRateParams({ window: e.target.value })}
                      className="text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                      {windowKeys(rules).slice().reverse().map((key) => (
                        <option key={key} value={key}>{windowLabel(key)}</option>
                      ))}
                    </select>
                  </div>
                  {/* Rate code */}
                  <div className="flex items-center gap-1.5 min-w-0 max-w-full">
                    <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                    <label htmlFor="rate-code-select" className="sr-only">Offense</label>
                    <select
                      id="rate-code-select"
                      value={rateCode ?? ''}
                      onChange={(e) => setRateParams({ offense: e.target.value })}
                      className="min-w-0 max-w-full text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                    <label htmlFor="year-select" className="sr-only">Year</label>
                    <select
                      id="year-select"
                      value={selectedYear}
                      onChange={(e) => updateFilters(undefined, parseInt(e.target.value))}
                      className="text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
                  <div className="flex items-center gap-1.5 min-w-0 max-w-full">
                    <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                    <label htmlFor="offense-select" className="sr-only">Offense</label>
                    <select
                      id="offense-select"
                      value={selectedOffense}
                      onChange={(e) => updateFilters(undefined, undefined, e.target.value)}
                      className="min-w-0 max-w-full text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
                </>
              )}

              {/* Total or rate */}
              <div role="group" aria-label="View" className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => setSortByRate(false)}
                  aria-pressed={!rateView}
                  className={cn(
                    'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                    !rateView
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  )}
                >
                  Total
                </button>
                <button
                  type="button"
                  onClick={() => setSortByRate(true)}
                  disabled={rateCode === null}
                  aria-pressed={rateView}
                  aria-describedby={countsOnlyNote ? 'counts-only-note' : undefined}
                  className={cn(
                    'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                    rateView
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
                    rateCode === null && 'opacity-50 cursor-not-allowed'
                  )}
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
                  className="hidden sm:flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                >
                  <span>{formatNumber(currentTotal)} total</span>
                  <ChevronRight aria-hidden="true" className={cn(
                    'w-4 h-4 transition-transform',
                    isSummaryExpanded && 'rotate-90'
                  )} />
                </button>
              )}
            </div>
            {countsOnlyNote && (
              <p id="counts-only-note" className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                No rate: {countsOnlyNote}
              </p>
            )}
          </div>

          {/* Expandable Summary - Desktop only */}
          {isSummaryExpanded && !rateView && (
            <div id="rankings-summary" className="hidden sm:block border-t border-gray-100 dark:border-gray-800 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 rounded-b-xl">
              <div className="flex items-center gap-6 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Showing: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{formatNumber(sortedRankings.length)} {rowUnit}</span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{countLabel === 'Total' ? 'Total' : `Total ${countLabel.toLowerCase()}`}: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{formatNumber(currentTotal)}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Size-bias warning banner (shown when viewing by Total) */}
        {!rateView && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" aria-hidden="true" />
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Larger schools report more incidents because they are larger
              {rateCode !== null && <> (use "Rate" for 3-year rates per 10,000 on-campus students)</>}. Lower numbers
              may reflect reporting differences, not safety.
              {' '}<Link to="/about" className="underline hover:text-amber-800 dark:hover:text-amber-200">Learn more</Link>
            </p>
          </div>
        )}

        {/* Comparability note for the selected year (data/seriesNotes.ts) */}
        {!rateView && <SeriesNotes years={[selectedYear]} className="mb-4" />}
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
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden transition-colors duration-200">
          {!metadata.presets.some((p) => p.id === selectedPreset) ? (
            <p className="p-6 text-sm text-gray-700 dark:text-gray-300">
              {PLACES_WITHOUT_PRESET[selectedPreset]
                ? <><strong>{PLACES_WITHOUT_PRESET[selectedPreset].replace(/^the /, 'The ')}</strong> has no ranking on this site.</>
                : <><strong>{selectedPreset}</strong> is not a state, territory or group on this site.</>}{' '}
              Rankings and rates cover institutions in the 50 states, the District of Columbia, Puerto Rico and the
              U.S. Virgin Islands.{' '}
              <Link to="/" className="text-primary-600 dark:text-primary-400 underline">See all schools</Link>
            </p>
          ) : loading ? (
            <div className="flex flex-col items-center justify-center py-16 min-h-[400px]">
              <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" />
              <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading rankings...</span>
            </div>
          ) : error ? (
            <div className="p-6 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 dark:text-red-400 mx-auto mb-2" />
              <p className="text-red-700 dark:text-red-400">{error}</p>
            </div>
          ) : sortedRankings.length === 0 ? (
            <div className="p-6 text-center text-gray-500 dark:text-gray-400">
              No data available for {currentOffense?.display || selectedOffense} in{' '}
              {selectedYear}
            </div>
          ) : (
            <>
              {/* Mobile Card View */}
              <div className="sm:hidden">
                {/* Mobile header row */}
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-800 border-b dark:border-gray-700">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Showing {formatNumber(displayedRankings.length)} of {formatNumber(sortedRankings.length)} {rowUnit}
                  </span>
                  <span className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    <GitCompare className="w-3.5 h-3.5" />
                    Compare
                  </span>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {displayedRankings.map((item) => (
                  <Fragment key={item.key}>
                  <div className="flex items-stretch">
                    <Link
                      to={`/school/${item.unitid}`}
                      className="flex-1 min-w-0 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300 text-sm font-bold flex items-center justify-center">
                            {item.rank}
                          </span>
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {item.campus ?? item.name}
                            {item.branch && !item.campus && (
                              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                            )}
                            {item.campus && (
                              <span className="block text-xs font-normal text-gray-500 dark:text-gray-400">{item.name}</span>
                            )}
                            {item.highForSize !== null && (
                              <span className="block text-xs font-normal text-amber-700 dark:text-amber-400">
                                {highForSizeNote(item.highForSize)}
                              </span>
                            )}
                          </span>
                        </div>
                        <ExternalLink className="w-4 h-4 text-gray-400 flex-shrink-0 mt-1" />
                      </div>
                      <div className="ml-11">
                          <>
                            <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-sm mb-2">
                              <span className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                                {countPhrase(item.count, currentOffense, formatNumber(item.count))}
                              </span>
                              {item.fte && (
                                <>
                                  <span className="text-gray-400">&middot;</span>
                                  <span className="text-gray-500 dark:text-gray-500 tabular-nums text-xs">
                                    {formatNumber(item.fte)} FTE (institution)
                                  </span>
                                </>
                              )}
                              <span className="text-gray-400">&middot;</span>
                              <span className="text-gray-600 dark:text-gray-400 tabular-nums">
                                {formatPercent(item.pct)}
                              </span>
                            </div>
                            <div className="w-full h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary-500 dark:bg-primary-400 rounded-full"
                                style={{ width: `${Math.min(item.pct, 100)}%` }}
                              />
                            </div>
                          </>
                      </div>
                    </Link>
                    <button
                      type="button"
                      onClick={(e) => toggleCompare(item.unitid, item.campus ?? item.name, e)}
                      className={cn(
                        'flex items-center justify-center w-12 border-l transition-colors',
                        isInCompare(item.unitid)
                          ? 'bg-primary-50 dark:bg-primary-900/30 border-primary-200 dark:border-primary-800 text-primary-600 dark:text-primary-400'
                          : 'border-gray-100 dark:border-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                      )}
                      aria-label={isInCompare(item.unitid)
                        ? `Remove ${item.campus ?? item.name} from comparison`
                        : `Add ${item.campus ?? item.name} to comparison`}
                    >
                      {isInCompare(item.unitid) ? (
                        <Check className="w-5 h-5" />
                      ) : (
                        <GitCompare className="w-5 h-5" />
                      )}
                    </button>
                  </div>
                  </Fragment>
                ))}
                </div>
              </div>

              {/* Desktop Table View */}
              <div className="hidden sm:block">
                {/* Desktop header row */}
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-800 border-b dark:border-gray-700">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Showing {formatNumber(displayedRankings.length)} of {formatNumber(sortedRankings.length)} {rowUnit}
                  </span>
                </div>
                <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    {table.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id}>
                        {headerGroup.headers.map((header) => (
                          <th
                            key={header.id}
                            style={{ width: header.getSize() }}
                            className={cn(
                              'cursor-pointer select-none hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
                              header.column.getIsSorted() && 'bg-gray-100 dark:bg-gray-700'
                            )}
                            onClick={header.column.getToggleSortingHandler()}
                            aria-sort={
                              header.column.getIsSorted() === 'asc' ? 'ascending'
                                : header.column.getIsSorted() === 'desc' ? 'descending'
                                : undefined
                            }
                          >
                            <div className="flex items-center gap-2">
                              {flexRender(
                                header.column.columnDef.header,
                                header.getContext()
                              )}
                              {header.column.getIsSorted() === 'asc' ? (
                                <ChevronUp className="w-4 h-4" />
                              ) : header.column.getIsSorted() === 'desc' ? (
                                <ChevronDown className="w-4 h-4" />
                              ) : (
                                <div className="w-4 h-4" />
                              )}
                            </div>
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody>
                    {tableRows.slice(0, displayCount).map((row) => (
                      <Fragment key={row.id}>
                        <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                          {row.getVisibleCells().map((cell) => (
                            <td key={cell.id}>
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
                <div className="p-4 border-t border-gray-100 dark:border-gray-800 text-center">
                  <button
                    type="button"
                    onClick={loadMore}
                    className="inline-flex items-center gap-2 px-6 py-2.5 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-medium transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Load {formatNumber(Math.min(LOAD_MORE_INCREMENT, remainingCount))} More
                    <span className="text-gray-500 dark:text-gray-400 text-sm">
                      ({formatNumber(remainingCount)} remaining)
                    </span>
                  </button>
                </div>
              )}

              {/* Showing count footer */}
              {!hasMoreToLoad && sortedRankings.length > 25 && (
                <div className="p-4 border-t border-gray-100 dark:border-gray-800 text-center text-sm text-gray-500 dark:text-gray-400">
                  Showing all {formatNumber(sortedRankings.length)} {rowUnit}
                </div>
              )}
            </>
          )}
        </div>
        </>)}

        {/* Data Note */}
        <div className="mt-6 p-4 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 rounded-lg">
          <p className="text-sm text-amber-800 dark:text-amber-300">
            <span className="font-medium">Note:</span> {metadata.note}
          </p>
        </div>
      </div>

      {/* Floating Compare Bar */}
      {compareSchools.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 shadow-lg z-50 animate-in slide-in-from-bottom-4 duration-200">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-3">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <GitCompare className="w-5 h-5 text-primary-600 dark:text-primary-400 flex-shrink-0" />
                <div className="flex items-center gap-2 min-w-0 overflow-x-auto">
                  {compareSchools.map((school, idx) => (
                    <div key={school.unitid} className="flex items-center gap-1.5">
                      {idx > 0 && <span className="text-gray-400 dark:text-gray-500">vs</span>}
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded-md text-sm font-medium whitespace-nowrap">
                        {school.name.length > 20 ? school.name.slice(0, 20) + '...' : school.name}
                        <button
                          type="button"
                          onClick={() => toggleCompare(school.unitid, school.name)}
                          className="ml-0.5 p-0.5 hover:bg-primary-100 dark:hover:bg-primary-800/50 rounded"
                          aria-label={`Remove ${school.name} from comparison`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
                {compareSchools.length === 1 && (
                  <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    Select 1 more
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={goToCompare}
                disabled={compareSchools.length < 2}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex-shrink-0',
                  compareSchools.length >= 2
                    ? 'bg-primary-600 hover:bg-primary-700 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                )}
              >
                <span className="hidden sm:inline">Compare</span>
                <GitCompare className="w-4 h-4 sm:hidden" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
