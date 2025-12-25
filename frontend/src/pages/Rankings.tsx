import { useState, useEffect, useMemo } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
  flexRender,
  SortingState,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, ExternalLink, AlertCircle, Loader2, MapPin, Calendar, AlertTriangle, Plus, Check, GitCompare, X, ChevronRight, Info } from 'lucide-react'
import { fetchRankings, getMetadata } from '../lib/api'
import type { RankingEntry, Metadata, Offense } from '../lib/types'
import { cn, formatNumber, formatPercent, groupOffensesByFamily, isSmallSample } from '../lib/utils'
import SchoolSearch from '../components/SchoolSearch'
import OffensePopover from '../components/OffensePopover'

export default function Rankings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // State
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const [rankings, setRankings] = useState<RankingEntry[]>([])
  const [totals, setTotals] = useState<Record<string, number>>({})
  const [sorting, setSorting] = useState<SortingState>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false)
  const [compareSchools, setCompareSchools] = useState<{ unitid: number; name: string }[]>([])
  const [sortByRate, setSortByRate] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)

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

  const isInCompare = (unitid: number) => compareSchools.some((s) => s.unitid === unitid)

  const goToCompare = () => {
    if (compareSchools.length >= 2) {
      navigate(`/compare?schools=${compareSchools.map((s) => s.unitid).join(',')}`)
    }
  }

  // Get filter values from URL or defaults
  const selectedPreset = searchParams.get('preset') || 'national'
  const selectedYear = parseInt(searchParams.get('year') || '2023')
  const selectedOffense = searchParams.get('offense') || 'all'

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

    setLoading(true)
    setError(null)
    setDisplayCount(25) // Reset display count on filter change

    fetchRankings(selectedPreset, selectedYear)
      .then((data) => {
        const offenseRankings = data.rankings[selectedOffense] || []
        setRankings(offenseRankings)
        setTotals(data.totals)
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

  // FTE data now available for all years (2015-2023)
  const canShowRate = true

  // Minimum FTE threshold for rate rankings (prevents small schools from dominating)
  const MIN_FTE_FOR_RATE = 1000

  // Sort and slice rankings for display (Load More pattern)
  const sortedRankings = useMemo(() => {
    if (!sortByRate) return rankings

    // Filter to schools with sufficient enrollment for meaningful rates
    const qualified = rankings.filter(
      (r) => r.fte !== null && r.fte >= MIN_FTE_FOR_RATE && r.rate !== null
    )

    // Sort by rate descending
    return qualified.sort((a, b) => (b.rate ?? 0) - (a.rate ?? 0))
  }, [rankings, sortByRate])

  const displayedRankings = useMemo(() => {
    return sortedRankings.slice(0, displayCount)
  }, [sortedRankings, displayCount])

  // Check if rate data is available (only for 2021-2023)
  const hasRateData = useMemo(() => {
    return rankings.some(r => r.rate !== null)
  }, [rankings])

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

  // Table setup
  const columnHelper = createColumnHelper<RankingEntry>()

  const columns = useMemo(
    () => [
      columnHelper.accessor('rank', {
        header: 'Rank',
        cell: (info) => {
          // When sorting by rate, use row index (1-based) since we re-sorted/filtered the list
          // When sorting by total, use the pre-computed rank
          const displayRank = sortByRate ? info.row.index + 1 : info.getValue()
          return (
            <span className="font-medium text-gray-500 dark:text-gray-400">
              #{displayRank}
            </span>
          )
        },
        size: 70,
      }),
      columnHelper.accessor('name', {
        header: 'School',
        cell: (info) => (
          <Link
            to={`/school/${info.row.original.unitid}`}
            className="group flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium"
          >
            {info.getValue()}
            {info.row.original.isMainCampus === false && (
              <span className="text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
            )}
            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
          </Link>
        ),
      }),
      columnHelper.accessor('count', {
        header: 'Incidents',
        cell: (info) => (
          <span className="font-semibold tabular-nums">
            {formatNumber(info.getValue())}
          </span>
        ),
        size: 100,
      }),
      ...(sortByRate ? [
        columnHelper.accessor('rate', {
          header: 'Rate',
          cell: (info) => {
            const rate = info.getValue()
            const { fte, count } = info.row.original
            const needsAsterisk = isSmallSample(fte, count)
            return (
              <span className="font-semibold tabular-nums text-primary-600 dark:text-primary-400">
                {rate !== null ? (
                  <>
                    {rate.toFixed(1)}
                    {needsAsterisk && (
                      <span
                        className="text-amber-600 dark:text-amber-400 cursor-help"
                        title="Small sample: under 1,000 students or fewer than 10 incidents. Interpret with caution."
                      >*</span>
                    )}
                  </>
                ) : '—'}
              </span>
            )
          },
          size: 100,
        }),
        columnHelper.accessor('fte', {
          header: 'Enrollment',
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
      ] : [
        columnHelper.accessor('fte', {
          header: 'Enrollment',
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
      ]),
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
            onClick={(e) => toggleCompare(info.row.original.unitid, info.row.original.name, e)}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              isInCompare(info.row.original.unitid)
                ? 'bg-primary-100 dark:bg-primary-900/50 text-primary-600 dark:text-primary-400'
                : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
            )}
            aria-label={isInCompare(info.row.original.unitid) ? 'Remove from comparison' : 'Add to comparison'}
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
    [columnHelper, compareSchools, sortByRate]
  )

  const table = useReactTable({
    data: displayedRankings,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  // Group offenses by family for dropdown
  const offenseGroups = useMemo(() => {
    if (!metadata) return new Map()
    return groupOffensesByFamily(metadata.offenses)
  }, [metadata])

  // Find current offense info
  const currentOffense = metadata?.offenses.find((o) => o.code === selectedOffense)
  const currentTotal = totals[selectedOffense] || 0

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
              {totalSchoolCount.toLocaleString()}+
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
        {/* Compact Filter Bar - Sticky */}
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 mb-4 transition-colors duration-200 sticky top-16 z-40">
          <div className="p-3 sm:p-4">
            {/* Compact Search - shows when scrolled past hero */}
            {isScrolled && (
              <div className="pb-3 mb-3 border-b border-gray-200 dark:border-gray-700">
                <SchoolSearch
                  variant="hero"
                  compareSchools={compareSchools.map(s => s.unitid)}
                  onToggleCompare={toggleCompare}
                  compact
                />
              </div>
            )}
            {/* Desktop: Single row with dividers */}
            <div className="hidden sm:flex items-center gap-4">
              {/* Data Filters Group */}
              <div className="flex items-center gap-3">
                {/* Preset */}
                <div className="flex items-center gap-1.5">
                  <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <select
                    id="preset-select"
                    value={selectedPreset}
                    onChange={(e) => updateFilters(e.target.value)}
                    className="text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  >
                    {metadata.presets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Divider */}
                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700" />

                {/* Year */}
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
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

                {/* Divider */}
                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700" />

                {/* Offense */}
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <select
                    id="offense-select"
                    value={selectedOffense}
                    onChange={(e) => updateFilters(undefined, undefined, e.target.value)}
                    className="text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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

              {/* Sort Toggle - outlined pill style */}
              {hasRateData && (
                <div className="flex items-center gap-2 ml-2 pl-3 border-l border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5">
                    <button
                      type="button"
                      onClick={() => setSortByRate(false)}
                      className={cn(
                        'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                        !sortByRate
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                      )}
                    >
                      Total
                    </button>
                    <button
                      type="button"
                      onClick={() => canShowRate && setSortByRate(true)}
                      disabled={!canShowRate}
                      title={!canShowRate ? 'Rate data requires enrollment data' : undefined}
                      className={cn(
                        'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                        sortByRate
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
                        !canShowRate && 'opacity-50 cursor-not-allowed'
                      )}
                    >
                      Rate
                    </button>
                  </div>
                  {sortByRate && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      per 10k students · 1,000+ FTE only · <span className="text-amber-600 dark:text-amber-400">*small sample</span>
                    </span>
                  )}
                </div>
              )}

              {/* Spacer */}
              <div className="flex-1" />

              {/* Summary Toggle */}
              <button
                type="button"
                onClick={() => setIsSummaryExpanded(!isSummaryExpanded)}
                className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
              >
                <span>{formatNumber(currentTotal)} total</span>
                <ChevronRight className={cn(
                  'w-4 h-4 transition-transform',
                  isSummaryExpanded && 'rotate-90'
                )} />
              </button>
            </div>

            {/* Mobile: Two-row layout */}
            <div className="sm:hidden space-y-3">
              {/* Row 1: Preset + Year */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 flex-1">
                  <MapPin className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <select
                    value={selectedPreset}
                    onChange={(e) => updateFilters(e.target.value)}
                    className="flex-1 text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5"
                  >
                    {metadata.presets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <select
                    value={selectedYear}
                    onChange={(e) => updateFilters(undefined, parseInt(e.target.value))}
                    className="w-20 text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5"
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
              </div>

              {/* Row 2: Offense + Sort Toggle */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                  <AlertTriangle className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <select
                    value={selectedOffense}
                    onChange={(e) => updateFilters(undefined, undefined, e.target.value)}
                    className="flex-1 min-w-0 text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5"
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
                {hasRateData && (
                  <div className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => setSortByRate(false)}
                      className={cn(
                        'px-2 py-1 text-xs font-medium rounded-md transition-colors',
                        !sortByRate
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400'
                      )}
                    >
                      Total
                    </button>
                    <button
                      type="button"
                      onClick={() => canShowRate && setSortByRate(true)}
                      disabled={!canShowRate}
                      title={!canShowRate ? 'Rate data requires enrollment data' : undefined}
                      className={cn(
                        'px-2 py-1 text-xs font-medium rounded-md transition-colors',
                        sortByRate
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400',
                        !canShowRate && 'opacity-50 cursor-not-allowed'
                      )}
                    >
                      Rate
                    </button>
                  </div>
                )}
              </div>
              {/* Mobile asterisk legend */}
              {sortByRate && hasRateData && (
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  per 10k students · 1,000+ FTE only · <span className="text-amber-600 dark:text-amber-400">*small sample</span>
                </div>
              )}
            </div>
          </div>

          {/* Expandable Summary - Desktop only */}
          {isSummaryExpanded && (
            <div className="hidden sm:block border-t border-gray-100 dark:border-gray-800 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 rounded-b-xl">
              <div className="flex items-center gap-6 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Showing: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{sortedRankings.length.toLocaleString()} campuses</span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Total incidents: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{formatNumber(currentTotal)}</span>
                </div>
                {sortByRate && (
                  <div className="text-xs text-amber-600 dark:text-amber-400">
                    Filtered to schools with 1,000+ FTE students
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Size-bias warning banner (shown when viewing by Total) */}
        {!sortByRate && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Larger schools report more incidents due to size{hasRateData && <> — use "Rate" for size-adjusted comparison</>}. Lower numbers may reflect reporting differences, not safety.
              {' '}<Link to="/about" className="underline hover:text-amber-800 dark:hover:text-amber-200">Learn more</Link>
            </p>
          </div>
        )}

        {/* Rate view context banner */}
        {sortByRate && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 mb-4 flex items-center gap-2">
            <Info className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <p className="text-sm text-blue-700 dark:text-blue-300">
              Per 10k students (1,000+ FTE only). Lower numbers may reflect reporting differences.
              {' '}<Link to="/about" className="underline hover:text-blue-800 dark:hover:text-blue-200">Learn more</Link>
            </p>
          </div>
        )}

        {/* Rankings Table (Desktop) / Cards (Mobile) */}
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden transition-colors duration-200">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 min-h-[400px]">
              <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" />
              <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading rankings...</span>
            </div>
          ) : error ? (
            <div className="p-6 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 dark:text-red-400 mx-auto mb-2" />
              <p className="text-red-700 dark:text-red-400">{error}</p>
            </div>
          ) : rankings.length === 0 ? (
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
                    Showing {displayedRankings.length} of {sortedRankings.length.toLocaleString()} campuses
                  </span>
                  <span className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    <GitCompare className="w-3.5 h-3.5" />
                    Compare
                  </span>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {displayedRankings.map((item, index) => (
                  <div key={item.unitid} className="flex items-stretch">
                    <Link
                      to={`/school/${item.unitid}`}
                      className="flex-1 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="flex items-center gap-3">
                          <span className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300 text-sm font-bold flex items-center justify-center">
                            {sortByRate ? index + 1 : item.rank}
                          </span>
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {item.name}
                            {item.isMainCampus === false && (
                              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                            )}
                          </span>
                        </div>
                        <ExternalLink className="w-4 h-4 text-gray-400 flex-shrink-0 mt-1" />
                      </div>
                      <div className="ml-11">
                        {sortByRate ? (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="font-semibold text-primary-600 dark:text-primary-400 tabular-nums">
                              {item.rate !== null ? (
                                <>
                                  {item.rate.toFixed(1)}
                                  {isSmallSample(item.fte, item.count) && (
                                    <span
                                      className="text-amber-600 dark:text-amber-400"
                                      title="Small sample: under 1,000 students or fewer than 10 incidents. Interpret with caution."
                                    >*</span>
                                  )}
                                  {' per 10k'}
                                </>
                              ) : '—'}
                            </span>
                            <span className="text-gray-400">&middot;</span>
                            <span className="text-gray-600 dark:text-gray-400 tabular-nums">
                              {formatNumber(item.count)} incidents
                            </span>
                            {item.fte && (
                              <>
                                <span className="text-gray-400">&middot;</span>
                                <span className="text-gray-500 dark:text-gray-500 tabular-nums text-xs">
                                  {formatNumber(item.fte)} FTE
                                </span>
                              </>
                            )}
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-sm mb-2">
                              <span className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                                {formatNumber(item.count)} incidents
                              </span>
                              {item.fte && (
                                <>
                                  <span className="text-gray-400">&middot;</span>
                                  <span className="text-gray-500 dark:text-gray-500 tabular-nums text-xs">
                                    {formatNumber(item.fte)} students
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
                        )}
                      </div>
                    </Link>
                    <button
                      type="button"
                      onClick={(e) => toggleCompare(item.unitid, item.name, e)}
                      className={cn(
                        'flex items-center justify-center w-12 border-l transition-colors',
                        isInCompare(item.unitid)
                          ? 'bg-primary-50 dark:bg-primary-900/30 border-primary-200 dark:border-primary-800 text-primary-600 dark:text-primary-400'
                          : 'border-gray-100 dark:border-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                      )}
                      aria-label={isInCompare(item.unitid) ? 'Remove from comparison' : 'Add to comparison'}
                    >
                      {isInCompare(item.unitid) ? (
                        <Check className="w-5 h-5" />
                      ) : (
                        <GitCompare className="w-5 h-5" />
                      )}
                    </button>
                  </div>
                ))}
                </div>
              </div>

              {/* Desktop Table View */}
              <div className="hidden sm:block">
                {/* Desktop header row */}
                <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-800 border-b dark:border-gray-700">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Showing {displayedRankings.length} of {sortedRankings.length.toLocaleString()} campuses
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
                    {table.getRowModel().rows.map((row) => (
                      <tr key={row.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
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
                    Load {Math.min(LOAD_MORE_INCREMENT, remainingCount)} More
                    <span className="text-gray-500 dark:text-gray-400 text-sm">
                      ({remainingCount.toLocaleString()} remaining)
                    </span>
                  </button>
                </div>
              )}

              {/* Showing count footer */}
              {!hasMoreToLoad && sortedRankings.length > 25 && (
                <div className="p-4 border-t border-gray-100 dark:border-gray-800 text-center text-sm text-gray-500 dark:text-gray-400">
                  Showing all {sortedRankings.length.toLocaleString()} campuses
                </div>
              )}
            </>
          )}
        </div>

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
                          aria-label={`Remove ${school.name}`}
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
