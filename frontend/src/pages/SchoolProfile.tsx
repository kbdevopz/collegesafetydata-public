import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { ArrowLeft, MapPin, AlertCircle, Loader2, TrendingUp, TrendingDown, Calendar, AlertTriangle, Users, Info } from 'lucide-react'
import { fetchSchoolProfile, getMetadata } from '../lib/api'
import type { SchoolProfile as SchoolProfileType, OffenseBreakdown, RateRules } from '../lib/types'
import {
  cn,
  formatNumber,
  formatPercent,
  getChartColors,
  transformTrendsForChart,
  getTopOffenses,
  calculateYoYChange,
  isSmallSample,
} from '../lib/utils'
import { fteFor, latestFte, institutionRate, rateNote, campusesPhrase } from '../lib/rates'
import { ALL, CRIMINAL, SUMMARY_LABELS, inSelection, isSummary, selectionLabel } from '../lib/selection'
import { useTheme } from '../hooks/useTheme'

// "on-campus", "on-campus and public property", "a, b and c"
function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

export default function SchoolProfile() {
  const { unitid } = useParams<{ unitid: string }>()
  const { resolvedTheme } = useTheme()
  const [profile, setProfile] = useState<SchoolProfileType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | null>(null)
  // 'criminal' (default), 'all' (every category) or one offense name
  const [selectedOffense, setSelectedOffense] = useState<string>(CRIMINAL)
  const [showRate, setShowRate] = useState(false)
  // Who rate rankings list (metadata.json), for the note on a left-out rate
  const [rateRules, setRateRules] = useState<RateRules | null>(null)

  useEffect(() => {
    getMetadata()
      .then((m) => setRateRules(m.rateRules))
      .catch(() => setRateRules(null))
  }, [])

  useEffect(() => {
    if (!unitid) return

    setLoading(true)
    setError(null)

    fetchSchoolProfile(parseInt(unitid))
      .then((data) => {
        setProfile(data)
        // Default to latest year
        setSelectedYear(data.summary.latestYear)
      })
      .catch(() => setError('Failed to load school data. Please try again.'))
      .finally(() => setLoading(false))
  }, [unitid])

  // Get available years from data (newest first)
  const availableYears = useMemo(() => {
    if (!profile) return []
    return profile.yearlyTotals.map(yt => yt.year).sort((a, b) => b - a)
  }, [profile])

  // Get unique offense types from trends
  const availableOffenses = useMemo(() => {
    if (!profile) return []
    const offenses = new Set<string>()
    profile.trends.forEach(t => offenses.add(t.offense))
    return Array.from(offenses).sort()
  }, [profile])

  // Get years that have data for the selected offense (every year for a summary)
  const yearsWithDataForOffense = useMemo(() => {
    if (!profile || isSummary(selectedOffense)) {
      return new Set(availableYears)
    }
    const years = new Set<number>()
    profile.trends
      .filter(t => t.offense === selectedOffense && t.count > 0)
      .forEach(t => years.add(t.year))
    return years
  }, [profile, selectedOffense, availableYears])

  // Check if current selection has data
  const hasDataForSelection = useMemo(() => {
    if (isSummary(selectedOffense)) return true
    return yearsWithDataForOffense.has(selectedYear || 0)
  }, [selectedOffense, yearsWithDataForOffense, selectedYear])

  // The selection's count in one year: the sum of its trend rows (0 when it has none)
  const countIn = useMemo(() => {
    const byYear = new Map<number, number>()
    profile?.trends
      .filter(t => inSelection(t, selectedOffense))
      .forEach(t => byYear.set(t.year, (byYear.get(t.year) ?? 0) + t.count))
    return (year: number) => byYear.get(year) ?? 0
  }, [profile, selectedOffense])

  // Compute offense breakdown for selected year from trends
  const selectedYearOffenseBreakdown = useMemo((): OffenseBreakdown[] => {
    if (!profile || !selectedYear) return []

    const yearTrends = profile.trends.filter(t => t.year === selectedYear)
    const breakdown = yearTrends
      .map(t => ({ offense: t.offense, count: t.count }))
      .sort((a, b) => b.count - a.count)

    return breakdown
  }, [profile, selectedYear])

  // Count of the selection (a summary or one offense) in the selected year
  const selectedYearTotal = useMemo(() => {
    if (!profile || !selectedYear) return 0
    return countIn(selectedYear)
  }, [profile, selectedYear, countIn])

  // FTE for the selected year only (null when that year has no FTE)
  const selectedYearFte = useMemo(() => fteFor(profile, selectedYear), [profile, selectedYear])

  // Newest FTE and the year it belongs to (for the header)
  const headerFte = useMemo(() => latestFte(profile), [profile])

  // The rate per 10k students in the selected year (that year's FTE only).
  // It is the institution's: the incidents of all its campuses per its FTE,
  // as NCES publishes FTE per institution.
  const selectedYearInstitution = useMemo(
    () => institutionRate(profile, selectedYear, selectedOffense, selectedYearTotal),
    [profile, selectedYear, selectedOffense, selectedYearTotal]
  )
  const selectedYearRate = selectedYearInstitution?.rate ?? null
  const selectedYearRateCount = selectedYearInstitution?.count ?? selectedYearTotal
  const selectedYearCampuses = campusesPhrase(selectedYearInstitution?.campuses ?? 1)
  const selectedYearRateNote = rateNote(selectedYearInstitution, rateRules)

  // Number of campuses of the institution in the header FTE's year
  const headerCampuses = headerFte
    ? profile?.institution?.byYear[String(headerFte.year)]?.campuses ?? 1
    : 1

  // Get top offense for selected year
  const selectedYearTopOffense = useMemo(() => {
    if (selectedYearOffenseBreakdown.length === 0) return { offense: null, count: 0 }
    return {
      offense: selectedYearOffenseBreakdown[0].offense,
      count: selectedYearOffenseBreakdown[0].count
    }
  }, [selectedYearOffenseBreakdown])

  // Figures for the selected year that DOE also publishes, identically, for
  // another campus; one entry per host, with the locations it shares.
  const selectedYearShared = useMemo(() => {
    if (!profile?.sharedFigures || !selectedYear) return []
    const byHost = new Map<number, { hostUnitid: number; hostName: string; geos: string[] }>()
    profile.sharedFigures
      .filter((f) => f.year === selectedYear)
      .forEach((f) => {
        const entry = byHost.get(f.hostUnitid) ?? { hostUnitid: f.hostUnitid, hostName: f.hostName, geos: [] }
        entry.geos.push(f.geo.toLowerCase())
        byHost.set(f.hostUnitid, entry)
      })
    return Array.from(byHost.values())
  }, [profile, selectedYear])

  // Calculate YoY change for selected year
  const selectedYearYoYChange = useMemo(() => {
    if (!profile || !selectedYear) return null

    if (isSummary(selectedOffense)) {
      // Both years must be in the profile
      const years = new Set(profile.yearlyTotals.map(yt => yt.year))
      if (!years.has(selectedYear) || !years.has(selectedYear - 1)) return null
      return calculateYoYChange(countIn(selectedYear), countIn(selectedYear - 1))
    } else {
      const currentData = profile.trends.find(
        t => t.year === selectedYear && t.offense === selectedOffense
      )
      const prevData = profile.trends.find(
        t => t.year === selectedYear - 1 && t.offense === selectedOffense
      )
      if (!currentData || !prevData) return null
      return calculateYoYChange(currentData.count, prevData.count)
    }
  }, [profile, selectedYear, selectedOffense, countIn])

  // Prepare chart data: the top offenses of the selected summary
  const selectionTrends = useMemo(
    () => (profile ? profile.trends.filter(t => inSelection(t, selectedOffense)) : []),
    [profile, selectedOffense]
  )

  const topOffenses = useMemo(() => getTopOffenses(selectionTrends, 5), [selectionTrends])

  const trendChartData = useMemo(() => {
    if (topOffenses.length === 0) return []
    return transformTrendsForChart(selectionTrends, topOffenses)
  }, [selectionTrends, topOffenses])

  // The selected summary's count in each year of the profile
  const yearlyChartData = useMemo(() => {
    if (!profile) return []
    return profile.yearlyTotals
      .map(yt => yt.year)
      .sort((a, b) => a - b)
      .map(year => ({ year, count: countIn(year) }))
  }, [profile, countIn])

  // Single offense trend data for when filtering by specific offense
  const singleOffenseTrendData = useMemo(() => {
    if (!profile || isSummary(selectedOffense)) return []
    return profile.trends
      .filter(t => t.offense === selectedOffense)
      .sort((a, b) => a.year - b.year)
      .map(t => ({ year: t.year, count: t.count }))
  }, [profile, selectedOffense])

  const chartColors = getChartColors()

  // By Location (latest year): each share is of the latest year's published
  // total (on-campus + non-campus + public property). Residence halls are a
  // subset of on-campus, so they are not part of that total and not a
  // separate pie slice; they keep their legend row and share.
  const geoTotal = profile ? profile.summary.totalIncidents : 0
  const geoRows = profile
    ? profile.breakdownByGeo.map((item, index) => ({
        ...item,
        color: chartColors[index % chartColors.length],
        pct: geoTotal > 0 ? (item.count / geoTotal) * 100 : null,
      }))
    : []
  const geoPieRows = geoRows.filter((item) => item.geo !== 'Residence halls')

  // Theme-aware chart styling
  const chartGridColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'
  const chartTextColor = resolvedTheme === 'dark' ? '#9ca3af' : '#6b7280'
  const chartBgColor = resolvedTheme === 'dark' ? '#111827' : 'white'
  const chartBorderColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'
  const barFillColor = resolvedTheme === 'dark' ? '#60a5fa' : '#3b82f6'

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-12 flex flex-col justify-center items-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" />
        <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading school data...</span>
      </div>
    )
  }

  if (error || !profile) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Rankings
        </Link>

        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-6 flex items-start gap-4">
          <AlertCircle className="w-6 h-6 text-red-500 dark:text-red-400 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-red-800 dark:text-red-300">School Not Found</h3>
            <p className="text-red-700 dark:text-red-400 mt-1">
              {error || `Could not find data for school ID ${unitid}`}
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Header Section */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-4">
        {/* Back Link */}
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Rankings
        </Link>

        {/* School Header */}
        <div className="mb-4">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            {profile.name}
            {profile.campusType && profile.isMainCampus === false && (
              <span className="ml-3 text-lg font-normal text-gray-500 dark:text-gray-400">
                (Branch Campus)
              </span>
            )}
          </h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-gray-600 dark:text-gray-400">
            <span className="flex items-center gap-1.5">
              <MapPin className="w-4 h-4" />
              {profile.city}, {profile.state}
            </span>
            {headerFte && (
              <span
                className="flex items-center gap-1.5"
                title="Enrollment (FTE) of the whole institution for the latest available year; NCES counts enrollment per institution, not per campus"
              >
                <Users className="w-4 h-4" />
                {formatNumber(headerFte.fte)} students
                {headerCampuses > 1 && <> at all {headerCampuses} campuses</>}
                <span className="text-xs text-gray-400 dark:text-gray-500">({headerFte.year})</span>
              </span>
            )}
            {profile.ivyLeague && (
              <span className="badge badge-success">Ivy League</span>
            )}
          </div>
        </div>
      </div>

      {/* Sticky Filter Bar */}
      <div className="sticky top-16 z-40 bg-white dark:bg-gray-900 border-y border-gray-200 dark:border-gray-800 shadow-sm">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center gap-4 py-3">
            {/* Year Dropdown */}
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <label htmlFor="year-select" className="text-sm text-gray-500 dark:text-gray-400 hidden sm:inline">
                Year:
              </label>
              <select
                id="year-select"
                value={selectedYear || ''}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className={cn(
                  "text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500",
                  isSummary(selectedOffense) ? 'w-24' : 'w-36'
                )}
              >
                {availableYears.map((year) => {
                  const hasData = yearsWithDataForOffense.has(year)
                  return (
                    <option
                      key={year}
                      value={year}
                      style={!hasData && !isSummary(selectedOffense) ? { color: '#9ca3af' } : undefined}
                    >
                      {year}{!hasData && !isSummary(selectedOffense) ? ' (no data)' : ''}
                    </option>
                  )
                })}
              </select>
            </div>

            {/* Offense/Crime Dropdown */}
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <label htmlFor="offense-select" className="text-sm text-gray-500 dark:text-gray-400 hidden sm:inline">
                Crime:
              </label>
              <select
                id="offense-select"
                value={selectedOffense}
                onChange={(e) => setSelectedOffense(e.target.value)}
                className="w-56 max-w-full text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value={CRIMINAL}>{SUMMARY_LABELS[CRIMINAL]}</option>
                <option value={ALL}>{SUMMARY_LABELS[ALL]}</option>
                {availableOffenses.map((offense) => (
                  <option key={offense} value={offense}>
                    {offense}
                  </option>
                ))}
              </select>
            </div>

            {/* Filter indicator */}
            {!isSummary(selectedOffense) && (
              <button
                type="button"
                onClick={() => setSelectedOffense(CRIMINAL)}
                className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
              >
                Clear filter
              </button>
            )}

            {/* Rate Toggle */}
            <div className="flex items-center gap-1 ml-auto">
              <span className="text-sm text-gray-500 dark:text-gray-400 hidden sm:inline mr-1">View:</span>
              <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                <button
                  type="button"
                  onClick={() => setShowRate(false)}
                  className={cn(
                    'px-3 py-1 text-sm font-medium rounded-md transition-colors',
                    !showRate
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
                  )}
                >
                  Total
                </button>
                <button
                  type="button"
                  onClick={() => setShowRate(true)}
                  disabled={!selectedYearFte}
                  title={!selectedYearFte ? `FTE data not available for ${selectedYear ?? 'this year'}` : 'Show rate per 10,000 students'}
                  className={cn(
                    'px-3 py-1 text-sm font-medium rounded-md transition-colors',
                    showRate
                      ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100',
                    !selectedYearFte && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  Rate
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
              {selectionLabel(selectedOffense)} ({selectedYear})
              {showRate && ' - Rate'}
            </div>
            <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">
              {showRate ? (
                selectedYearRate !== null ? (
                  <>
                    {selectedYearRate.toFixed(1)}
                    <span className="text-lg font-normal text-gray-500 dark:text-gray-400 ml-1">
                      per 10k
                    </span>
                    {isSmallSample(selectedYearFte, selectedYearRateCount) && (
                      <span className="text-amber-500 ml-1" title="Small sample size">*</span>
                    )}
                  </>
                ) : (
                  <span className="text-gray-400">N/A</span>
                )
              ) : (
                formatNumber(selectedYearTotal)
              )}
            </div>
            {!showRate && selectedYearYoYChange && (
              <div
                className={cn(
                  'flex items-center gap-1 text-sm mt-1',
                  selectedYearYoYChange.absolute > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
                )}
              >
                {selectedYearYoYChange.absolute > 0 ? (
                  <TrendingUp className="w-4 h-4" />
                ) : (
                  <TrendingDown className="w-4 h-4" />
                )}
                {selectedYearYoYChange.absolute > 0 ? '+' : ''}
                {formatNumber(selectedYearYoYChange.absolute)} from {selectedYear && selectedYear - 1}
              </div>
            )}
            {showRate && selectedYearFte && (
              <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {selectedYearCampuses ? (
                  // The institution's rate: all its campuses' incidents per its FTE
                  <>
                    Institution rate ({selectedYearCampuses}):{' '}
                    {formatNumber(selectedYearRateCount)} per {formatNumber(selectedYearFte)} FTE
                  </>
                ) : (
                  <>Based on {formatNumber(selectedYearFte)} FTE</>
                )}
              </div>
            )}
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Most Common Offense</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {selectedYearTopOffense.offense || 'N/A'}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {formatNumber(selectedYearTopOffense.count)} incidents
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Data Coverage</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {yearlyChartData.length > 0
                ? `${yearlyChartData[0].year}-${yearlyChartData[yearlyChartData.length - 1].year}`
                : 'N/A'}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {yearlyChartData.length} years of data
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Offense Types ({selectedYear})</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {selectedYearOffenseBreakdown.length}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Categories with incidents</div>
          </div>
        </div>

        {/* Figures shared with another campus (counted once, under the host) */}
        {selectedYearShared.length > 0 && (
          <div role="note" className="-mt-4 mb-6 space-y-1">
            {selectedYearShared.map((entry) => (
              <p
                key={entry.hostUnitid}
                className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
              >
                <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <span>
                  <span className="font-medium text-gray-700 dark:text-gray-300">
                    {selectedYear} {joinWithAnd(entry.geos)} figures:
                  </span>{' '}
                  These figures are also reported by{' '}
                  <Link
                    to={`/school/${entry.hostUnitid}`}
                    className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 underline"
                  >
                    {entry.hostName}
                  </Link>{' '}
                  and are counted once, under {entry.hostName}, in totals and rankings.
                </span>
              </p>
            ))}
          </div>
        )}

        {/* Rate Info Banner */}
        {showRate && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2 text-sm text-blue-700 dark:text-blue-300">
              <Users className="w-4 h-4 flex-shrink-0" />
              <span>
                <strong>Rate view:</strong> Incidents per 10,000 full-time equivalent (FTE) students.
                {selectedYearCampuses && (
                  <span className="ml-1">
                    NCES counts enrollment per institution, not per campus, so this is the institution's rate:
                    the incidents of {selectedYearCampuses} per its FTE.
                  </span>
                )}
                {isSmallSample(selectedYearFte, selectedYearRateCount) && (
                  <span className="ml-1">* indicates small sample size (FTE &lt; 1,000 or incidents &lt; 10).</span>
                )}
              </span>
            </div>
            {selectedYearRateNote && (
              <p role="note" className="flex items-start gap-2 mt-2 text-sm text-blue-700 dark:text-blue-300">
                <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                <span>In {selectedYear}: {selectedYearRateNote}</span>
              </p>
            )}
          </div>
        )}

        {/* No Data Message */}
        {!hasDataForSelection && !isSummary(selectedOffense) && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-6 mb-8">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-medium text-amber-800 dark:text-amber-300">
                  No data available
                </h3>
                <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                  No {selectedOffense} incidents were reported in {selectedYear}.
                  Try selecting a different year or view all offenses.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Yearly Trend Chart - changes based on offense filter */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {selectionLabel(selectedOffense)} Over Time
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={isSummary(selectedOffense) ? yearlyChartData : singleOffenseTrendData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                <XAxis
                  dataKey="year"
                  tick={{ fill: chartTextColor, fontSize: 12 }}
                  axisLine={{ stroke: chartGridColor }}
                />
                <YAxis
                  tick={{ fill: chartTextColor, fontSize: 12 }}
                  axisLine={{ stroke: chartGridColor }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: chartBgColor,
                    border: `1px solid ${chartBorderColor}`,
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: chartTextColor }}
                  itemStyle={{ color: chartTextColor }}
                />
                <Bar
                  dataKey="count"
                  name={selectionLabel(selectedOffense)}
                  radius={[4, 4, 0, 0]}
                >
                  {(isSummary(selectedOffense) ? yearlyChartData : singleOffenseTrendData).map((entry) => (
                    <Cell
                      key={entry.year}
                      fill={entry.year === selectedYear ? '#f59e0b' : barFillColor}
                      opacity={entry.year === selectedYear ? 1 : 0.6}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 text-center">
              Selected year highlighted in amber
            </p>
          </div>

          {/* Top Offenses Trend - only show when viewing a summary */}
          {isSummary(selectedOffense) ? (
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Top {Math.min(topOffenses.length, 5)} Offenses Over Time
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trendChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                  <XAxis
                    dataKey="year"
                    tick={{ fill: chartTextColor, fontSize: 12 }}
                    axisLine={{ stroke: chartGridColor }}
                  />
                  <YAxis
                    tick={{ fill: chartTextColor, fontSize: 12 }}
                    axisLine={{ stroke: chartGridColor }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: chartBgColor,
                      border: `1px solid ${chartBorderColor}`,
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: chartTextColor }}
                    itemStyle={{ color: chartTextColor }}
                  />
                  <Legend wrapperStyle={{ color: chartTextColor }} />
                  {topOffenses.map((offense, i) => (
                    <Line
                      key={offense}
                      type="monotone"
                      dataKey={offense}
                      stroke={chartColors[i % chartColors.length]}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      activeDot={{ r: 5 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {selectedOffense} Trend
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={singleOffenseTrendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                  <XAxis
                    dataKey="year"
                    tick={{ fill: chartTextColor, fontSize: 12 }}
                    axisLine={{ stroke: chartGridColor }}
                  />
                  <YAxis
                    tick={{ fill: chartTextColor, fontSize: 12 }}
                    axisLine={{ stroke: chartGridColor }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: chartBgColor,
                      border: `1px solid ${chartBorderColor}`,
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: chartTextColor }}
                    itemStyle={{ color: chartTextColor }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke={chartColors[0]}
                    strokeWidth={3}
                    dot={{ r: 4, fill: chartColors[0] }}
                    activeDot={{ r: 6 }}
                    name={selectedOffense}
                  />
                </LineChart>
              </ResponsiveContainer>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 text-center">
                Showing trend for {selectedOffense} only
              </p>
            </div>
          )}
        </div>

        {/* Breakdowns Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* By Offense Type */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              By Offense Type ({selectedYear})
            </h2>
            {selectedYearOffenseBreakdown.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                No incident data for {selectedYear}
              </div>
            ) : (
              <div className="space-y-3">
                {selectedYearOffenseBreakdown.slice(0, 10).map((item, index) => {
                  const maxCount = selectedYearOffenseBreakdown[0]?.count || 1
                  const percentage = (item.count / maxCount) * 100
                  const isSelected = item.offense === selectedOffense

                  return (
                    <button
                      key={item.offense}
                      type="button"
                      onClick={() => setSelectedOffense(item.offense === selectedOffense ? CRIMINAL : item.offense)}
                      className={cn(
                        'w-full flex items-center gap-4 p-2 -mx-2 rounded-lg transition-colors',
                        isSelected
                          ? 'bg-primary-50 dark:bg-primary-900/20'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                      )}
                    >
                      <div className="w-32 sm:w-40 text-sm text-left text-gray-700 dark:text-gray-300 truncate">
                        {item.offense}
                      </div>
                      <div className="flex-1">
                        <div className="h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${percentage}%`,
                              backgroundColor: isSelected ? '#f59e0b' : chartColors[index % chartColors.length],
                            }}
                          />
                        </div>
                      </div>
                      <div className="w-16 text-right font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                        {formatNumber(item.count)}
                      </div>
                    </button>
                  )
                })}
                {selectedYearOffenseBreakdown.length > 10 && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 text-center">
                    Showing top 10 of {selectedYearOffenseBreakdown.length} offense types
                  </p>
                )}
              </div>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-4 text-center">
              Click an offense to filter charts
            </p>
          </div>

          {/* By Location */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                By Location
                <span className="ml-2 text-sm font-normal text-amber-600 dark:text-amber-400">
                  ({profile.summary.latestYear}, all categories)
                </span>
              </h2>
            </div>

            <div className="flex flex-col lg:flex-row items-center gap-6">
              {/* Pie Chart */}
              <div className="w-48 h-48 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={geoPieRows}
                      dataKey="count"
                      nameKey="geo"
                      cx="50%"
                      cy="50%"
                      outerRadius={70}
                      innerRadius={40}
                      paddingAngle={2}
                    >
                      {geoPieRows.map((item) => (
                        <Cell
                          key={`cell-${item.geo}`}
                          fill={item.color}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => formatNumber(value)}
                      contentStyle={{
                        backgroundColor: chartBgColor,
                        border: `1px solid ${chartBorderColor}`,
                        borderRadius: '8px',
                      }}
                      labelStyle={{ color: chartTextColor }}
                      itemStyle={{ color: chartTextColor }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Legend */}
              <div className="flex-1 space-y-3">
                {geoRows.map((item) => {
                  const pct = item.pct

                  return (
                    <div key={item.geo} className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{
                          backgroundColor: item.color,
                        }}
                      />
                      <div className="flex-1 text-sm text-gray-700 dark:text-gray-300">{item.geo}</div>
                      <div className="text-right">
                        <div className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                          {formatNumber(item.count)}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                          {pct !== null ? formatPercent(pct) : '—'}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  <strong>Important:</strong> Residence hall incidents are a subset of on-campus incidents.
                  Do not add these categories together — this would result in double-counting.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
