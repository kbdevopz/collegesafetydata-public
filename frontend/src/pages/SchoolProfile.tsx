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
  ReferenceArea,
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
  displayName,
  compactYears,
} from '../lib/utils'
import { fteFor, latestFte, institutionRate, rateNote, campusesPhrase } from '../lib/rates'
import { ALL, CRIMINAL, SUMMARY_LABELS, inSelection, isSummary, selectionLabel } from '../lib/selection'
import { useTheme } from '../hooks/useTheme'
import SeriesNotes, { ReportYearNote } from '../components/SeriesNotes'
import CiteThisData from '../components/CiteThisData'
import { SERIES_NOTES } from '../data/seriesNotes'
import type { Metadata } from '../lib/types'

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

  // Known DOE file errors (metadata.json "knownDefects"), for the note on
  // residence-hall figures they touch
  const [knownDefects, setKnownDefects] = useState<Metadata['knownDefects']>(undefined)

  useEffect(() => {
    getMetadata()
      .then((m) => {
        setRateRules(m.rateRules)
        setKnownDefects(m.knownDefects)
      })
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

  // The years the campus reported, newest first (0 included for a year
  // without an incident); a year it did not report has no figures at all
  const availableYears = useMemo(() => {
    if (!profile) return []
    return profile.yearlyTotals.map(yt => yt.year).sort((a, b) => b - a)
  }, [profile])
  const notReportedYears = useMemo(() => profile?.notReported ?? [], [profile])

  // Chart years: from the first to the last reported year, a year it did
  // not report in between included (shown as a gap, not as 0)
  const chartYears = useMemo(() => {
    if (availableYears.length === 0) return []
    const first = availableYears[availableYears.length - 1]
    const last = availableYears[0]
    return Array.from({ length: last - first + 1 }, (_, i) => first + i)
  }, [availableYears])

  // Get unique offense types from trends
  const availableOffenses = useMemo(() => {
    if (!profile) return []
    const offenses = new Set<string>()
    profile.trends.forEach(t => offenses.add(t.offense))
    return Array.from(offenses).sort()
  }, [profile])

  // The selection's count in one year: the sum of its trend rows (0 when it
  // has none; a reported year without the selection had 0)
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

  // Most common criminal offense in the selected year (arrests, referrals
  // and VAWA offenses are other kinds of counts, so they are not compared)
  const selectedYearTopOffense = useMemo(() => {
    const top = (profile?.trends ?? [])
      .filter(t => t.year === selectedYear && inSelection(t, CRIMINAL) && t.count > 0)
      .sort((a, b) => b.count - a.count)[0]
    return top ? { offense: top.offense, count: top.count } : { offense: null, count: 0 }
  }, [profile, selectedYear])

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

  // YoY change for the selected year: both years must have been reported
  const selectedYearYoYChange = useMemo(() => {
    if (!profile || !selectedYear) return null
    const years = new Set(profile.yearlyTotals.map(yt => yt.year))
    if (!years.has(selectedYear) || !years.has(selectedYear - 1)) return null
    return calculateYoYChange(countIn(selectedYear), countIn(selectedYear - 1))
  }, [profile, selectedYear, countIn])

  // Prepare chart data: the top offenses of the selected summary
  const selectionTrends = useMemo(
    () => (profile ? profile.trends.filter(t => inSelection(t, selectedOffense)) : []),
    [profile, selectedOffense]
  )

  const topOffenses = useMemo(() => getTopOffenses(selectionTrends, 5), [selectionTrends])

  const trendChartData = useMemo(() => {
    if (topOffenses.length === 0) return []
    return transformTrendsForChart(selectionTrends, topOffenses, chartYears, new Set(availableYears))
  }, [selectionTrends, topOffenses, chartYears, availableYears])

  // The selection's count in each chart year: 0 for a reported year without
  // it, null (a gap) for a year the campus did not report
  const yearlyChartData = useMemo(() => {
    const reported = new Set(availableYears)
    return chartYears.map(year => ({ year, count: reported.has(year) ? countIn(year) : null }))
  }, [chartYears, availableYears, countIn])

  // Not reported years between the first and last reported one (chart gaps)
  const chartGaps = useMemo(
    () => notReportedYears.filter(year => chartYears.includes(year)),
    [notReportedYears, chartYears]
  )

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

  // Known DOE file errors that touch this campus's residence-hall figures
  // in the By Location year (its figures come from the defective release)
  const geoYearDefects = useMemo(() => {
    if (!profile || !knownDefects) return []
    const year = profile.summary.latestYear
    return knownDefects.filter(
      (d) => d.year === year && d.geo === 'residencehall' && d.unitids.includes(profile.unitid)
    )
  }, [profile, knownDefects])
  const releaseLabel = (suffix: string) => `20${suffix.slice(0, 2)}-20${suffix.slice(4, 6)}`
  const categoryLabel = (category: string) =>
    category === 'discipline' ? 'disciplinary referrals' : category === 'arrest' ? 'liquor-law arrests' : category

  // Chart years with a sourced comparability note (data/seriesNotes.ts),
  // shaded on the trend charts
  const noteBands = useMemo(
    () =>
      SERIES_NOTES.map((n) => n.years.filter((y) => chartYears.includes(y)))
        .filter((ys) => ys.length > 0)
        .map((ys) => ({ x1: Math.min(...ys), x2: Math.max(...ys) })),
    [chartYears]
  )

  // Theme-aware chart styling
  const chartGridColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'
  const chartTextColor = resolvedTheme === 'dark' ? '#9ca3af' : '#6b7280'
  const chartBgColor = resolvedTheme === 'dark' ? '#111827' : 'white'
  const chartBorderColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'
  const barFillColor = resolvedTheme === 'dark' ? '#60a5fa' : '#3b82f6'
  const noteBandColor = resolvedTheme === 'dark' ? '#fbbf24' : '#d97706'

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
            {displayName(profile)}
            {!profile.campus && profile.campusType && profile.isMainCampus === false && (
              <span className="ml-3 text-lg font-normal text-gray-500 dark:text-gray-400">
                (Branch Campus)
              </span>
            )}
          </h1>
          {profile.campus && (
            <p className="text-base text-gray-600 dark:text-gray-400 mb-2">Campus of {profile.name}</p>
          )}
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
                Institution FTE: {formatNumber(headerFte.fte)}
                {headerCampuses > 1 && <> (all {headerCampuses} campuses)</>}
                <span className="text-xs text-gray-400 dark:text-gray-500">({headerFte.year})</span>
              </span>
            )}
            {profile.ivyLeague && (
              <span className="badge badge-success">Ivy League</span>
            )}
          </div>
          {profile.idChanges && profile.idChanges.length > 0 && (
            <div className="mt-4 rounded-lg border-2 border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
              <p className="font-semibold mb-1 flex items-center gap-1.5">
                <Info className="w-4 h-4 flex-shrink-0" />
                This campus has more than one DOE ID
              </p>
              <ul className="space-y-1">
                {profile.idChanges.map((link) => (
                  <li key={link.unitid}>
                    DOE reported this campus under ID {link.unitid} in {compactYears(link.years)}. Those years are on
                    a separate page:{' '}
                    <Link
                      to={`/school/${link.unitid}`}
                      className="font-medium text-primary-700 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-300 underline"
                    >
                      {displayName(link)}
                    </Link>
                    .
                  </li>
                ))}
              </ul>
              <p className="mt-1">This page shows only the years DOE reported under ID {profile.unitid}.</p>
            </div>
          )}
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
                className="w-24 text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
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
            {!showRate && selectedYearYoYChange && selectedYearYoYChange.absolute === 0 && (
              <div className="text-sm mt-1 text-gray-500 dark:text-gray-400">
                Same number reported as in {selectedYear && selectedYear - 1}
              </div>
            )}
            {!showRate && selectedYearYoYChange && selectedYearYoYChange.absolute !== 0 && (
              <div
                className="flex items-center gap-1 text-sm mt-1 text-gray-600 dark:text-gray-400"
                title="A change in reported counts can reflect changes in reporting, not only in crime"
              >
                {selectedYearYoYChange.absolute > 0 ? (
                  <TrendingUp className="w-4 h-4" />
                ) : (
                  <TrendingDown className="w-4 h-4" />
                )}
                {selectedYearYoYChange.absolute > 0 ? '+' : ''}
                {formatNumber(selectedYearYoYChange.absolute)} reported vs {selectedYear && selectedYear - 1}
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
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Most Common Criminal Offense</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {selectedYearTopOffense.offense || 'None'}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {selectedYearTopOffense.offense
                ? `${formatNumber(selectedYearTopOffense.count)} reported ${selectedYearTopOffense.count === 1 ? 'offense' : 'offenses'}`
                : `No criminal offenses reported in ${selectedYear}`}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Data Coverage</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {chartYears.length > 0
                ? `${chartYears[0]}-${chartYears[chartYears.length - 1]}`
                : 'N/A'}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {availableYears.length} {availableYears.length === 1 ? 'year' : 'years'} reported
            </div>
            {notReportedYears.length > 0 && (
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Not reported: {notReportedYears.join(', ')}
              </div>
            )}
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-all duration-300">
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Categories ({selectedYear})</div>
            <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {selectedYearOffenseBreakdown.length}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Categories above 0 (crimes, arrests, referrals)</div>
          </div>
        </div>

        {/* Comparability note for the selected year (data/seriesNotes.ts) */}
        {selectedYear !== null && <SeriesNotes years={[selectedYear]} className="-mt-4 mb-6" />}

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

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Yearly Trend Chart - changes based on offense filter */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {selectionLabel(selectedOffense)} Over Time
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={yearlyChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} fill={noteBandColor} fillOpacity={0.12} ifOverflow="extendDomain" />
                ))}
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
                  // A reported 0 gets a thin bar so it differs from a year not
                  // reported (null), which gets none
                  minPointSize={(value: number | null | undefined) => (value == null ? 0 : 3)}
                >
                  {yearlyChartData.map((entry) => (
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
              Selected year highlighted in amber · A thin bar is 0
              {chartGaps.length > 0 && (
                <> · No bar for {chartGaps.join(', ')}: not reported (no figures, not 0)</>
              )}
              {noteBands.length > 0 && <> · Shaded years have a note below</>}
            </p>
            <SeriesNotes years={chartYears} className="mt-2" />
            <ReportYearNote className="mt-1" />
          </div>

          {/* Top Offenses Trend - only show when viewing a summary */}
          {isSummary(selectedOffense) ? (
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {topOffenses.length > 0 ? `Top ${Math.min(topOffenses.length, 5)} Offenses Over Time` : 'Offenses Over Time'}
              </h2>
              {topOffenses.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center text-center text-gray-500 dark:text-gray-400">
                  0 in every year this campus reported ({selectionLabel(selectedOffense).toLowerCase()})
                </div>
              ) : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trendChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} fill={noteBandColor} fillOpacity={0.12} ifOverflow="extendDomain" />
                ))}
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
              )}
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 transition-colors duration-200">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {selectedOffense} Trend
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={yearlyChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} fill={noteBandColor} fillOpacity={0.12} ifOverflow="extendDomain" />
                ))}
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
              By Category ({selectedYear})
            </h2>
            {selectedYearOffenseBreakdown.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                {/* Only reported years can be selected, so this is a 0, not missing data */}
                No incidents in {selectedYear} (every figure reported was 0)
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

            {geoRows.length === 0 ? (
              // A reported year in which every figure was 0
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                No incidents in {profile.summary.latestYear} (every figure reported was 0)
              </div>
            ) : (
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
            )}

            {geoYearDefects.length > 0 && (
              <div role="note" className="mt-4 space-y-1">
                {geoYearDefects.map((d) => (
                  <p key={d.file} className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                    <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
                    <span>
                      {d.takenFrom
                        ? <>{d.year} residence-hall {categoryLabel(d.category)} come from DOE's {releaseLabel(d.takenFrom)} release, because that file of the {releaseLabel(d.release)} release, which this campus's {d.year} figures come from, is wrong.</>
                        : <>{d.year} residence-hall {categoryLabel(d.category)} are not included: that file of DOE's {releaseLabel(d.release)} release, which this campus's {d.year} figures come from, is wrong, and no other release has them.</>}{' '}
                      <Link to="/methodology#known-defects" className="text-primary-600 dark:text-primary-400 underline">Details</Link>
                    </span>
                  </p>
                ))}
              </div>
            )}

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

        <CiteThisData school={{ unitid: profile.unitid, name: profile.campus ? `${profile.campus} (${profile.name})` : profile.name }} className="mt-6" />
      </div>
    </div>
  )
}
