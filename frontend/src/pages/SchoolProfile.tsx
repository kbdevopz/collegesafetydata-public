import { useState, useEffect, useMemo } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
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
import { AlertTriangle } from 'lucide-react'
import { fetchRankings, fetchSchoolProfile, getMetadata } from '../lib/api'
import type { SchoolProfile as SchoolProfileType, OffenseBreakdown } from '../lib/types'
import {
  cn,
  formatNumber,
  formatPercent,
  transformTrendsForChart,
  getTopOffenses,
  calculateYoYChange,
  displayName,
  compactYears,
  withParams,
} from '../lib/utils'
import {
  chooseWindow, countsOnlyReason, flagSentence, highForSizeParagraph, latestFte, rateCodeForSelection, rateCodeLabel,
  rateCodes, windowKeys, windowLabel,
} from '../lib/rates'
import RatePanel from '../components/RatePanel'
import {
  ALL, CRIMINAL, PROPERTY, SUMMARY_LABELS, VIOLENT, inSelection, isSummary, selectionCode, selectionFromParam, selectionLabel,
} from '../lib/selection'
import { SERIES_DASHES, barCursor, lineCursor, tooltipProps, useChartTheme } from '../lib/chartTheme'
import { useMediaQuery } from '../hooks/useMediaQuery'
import SeriesNotes, { ReportYearNote } from '../components/SeriesNotes'
import CiteThisData from '../components/CiteThisData'
import { Loading } from '../components/ui'
import { SERIES_NOTES } from '../data/seriesNotes'
import type { Metadata } from '../lib/types'

// "on-campus", "on-campus and public property", "a, b and c"
function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

export default function SchoolProfile() {
  const { unitid } = useParams<{ unitid: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  // Phone width: the year axis labels are angled so that every year fits
  const narrow = useMediaQuery('(max-width: 639px)')
  const [profile, setProfile] = useState<SchoolProfileType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // metadata.json: the rate rules and figures, and known DOE file errors
  // (for the note on residence-hall figures they touch)
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const rateRules = metadata?.rateRules ?? null
  const knownDefects = metadata?.knownDefects

  useEffect(() => {
    getMetadata()
      .then(setMetadata)
      .catch(() => setMetadata(null))
  }, [])

  useEffect(() => {
    if (!unitid) return

    setLoading(true)
    setError(null)

    fetchSchoolProfile(parseInt(unitid))
      .then((data) => setProfile(data))
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

  // The selections are in the address, so a view of the page can be cited
  // or shared: ?year= (a reported year; default the latest), ?offense= (a
  // summary or an offense code such as motor_vehicle_theft; default all
  // criminal offenses) and ?view=rate (default counts). They are changed in
  // place, without a new history entry for each change.
  const yearParam = Number(searchParams.get('year'))
  const selectedYear = profile
    ? (availableYears.includes(yearParam) ? yearParam : profile.summary.latestYear)
    : null
  // 'criminal' (default), 'all' (every category) or one offense name
  const selectedOffense = selectionFromParam(searchParams.get('offense'), availableOffenses, CRIMINAL)
  const showRate = searchParams.get('view') === 'rate'
  const setSelection = (changes: Record<string, string | null>) =>
    setSearchParams((prev) => withParams(prev, changes), { replace: true })
  const setSelectedYear = (year: number) => setSelection({ year: String(year) })
  const setSelectedOffense = (offense: string) =>
    setSelection({ offense: offense === CRIMINAL ? null : selectionCode(offense) })
  const setShowRate = (rate: boolean) => setSelection({ view: rate ? 'rate' : null })
  // Rate view: ?window= (a 3-year window; default the one ending in the
  // selected year, else the latest) and the rate code of the selection,
  // whose single-year trend is shown (violent when the selection has none)
  const selectedWindow = chooseWindow(rateRules, searchParams.get('window'), yearParam || null)
  const setSelectedWindow = (key: string) => setSelection({ window: key })
  const rawOffense = searchParams.get('offense')?.trim().toLowerCase() ?? null
  const selectionRateCode = rateRules
    ? (rawOffense && rawOffense in rateRules.codes ? rawOffense : rateCodeForSelection(selectionCode(selectedOffense), rateRules))
    : null
  const trendCode = selectionRateCode ?? 'violent'
  const setTrendCode = (code: string) => setSelection({ offense: code })
  const countsOnlyNote = showRate && rateRules && !selectionRateCode
    ? `${countsOnlyReason(selectionCode(selectedOffense), selectionLabel(selectedOffense))} The rates below are for the offenses that have one.`
    : null

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

  // Newest FTE and the year it belongs to (for the header)
  const headerFte = useMemo(() => latestFte(profile), [profile])

  // Unusual-year flags of the selected year (every location) whose offense
  // is in the selection: notes beside the counts. Flags never change counts.
  const selectedYearFlags = useMemo(() => {
    if (!profile || !selectedYear) return []
    const flags = profile.institution?.byYear[String(selectedYear)]?.flags ?? []
    return flags
      .filter((f) => {
        const offense = metadata?.offenses.find((o) => o.code === f.offense)
        return !!offense && inSelection({ offense: offense.display, offenseFamily: offense.family }, selectedOffense)
      })
      .map((f) => flagSentence({ ...f, year: selectedYear }))
  }, [profile, selectedYear, selectedOffense, metadata])
  // Flags are the institution's: all its campuses together
  const institutionCampuses = selectedYear ? profile?.institution?.byYear[String(selectedYear)]?.campuses ?? 1 : 1

  // The selection's count in the selected year when the rankings by count
  // flag it as very high for the institution's size (highForSize), read from
  // the state's rankings file (every rankings file of a year flags a campus's
  // count the same way, and every ranked campus is in its state's file)
  const [sizeFlag, setSizeFlag] = useState<{
    year: number; code: string; count: number; fte: number; campuses: number
  } | null>(null)
  useEffect(() => {
    setSizeFlag(null)
    const state = profile?.state
    if (!profile || !selectedYear || showRate || !state || !metadata?.presets.some((p) => p.id === state)) return
    const code = selectionCode(selectedOffense)
    let live = true
    fetchRankings(state, selectedYear)
      .then((file) => {
        const entry = file.rankings[code]?.find((e) => e.unitid === profile.unitid)
        const campus = file.campuses[String(profile.unitid)]
        if (live && entry?.highForSize && campus?.fte) {
          setSizeFlag({ year: selectedYear, code, count: entry.count, fte: campus.fte, campuses: campus.campuses })
        }
      })
      .catch(() => {
        // Without the file the page shows no size note; the counts are unaffected
      })
    return () => {
      live = false
    }
  }, [profile, selectedYear, selectedOffense, showRate, metadata])

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

  const chart = useChartTheme()

  // By Location (latest year): each share is of the latest year's published
  // total (on-campus + non-campus + public property). Residence halls are a
  // subset of on-campus, so they are not part of that total and not a
  // separate pie slice; they keep their legend row and share.
  const geoTotal = profile ? profile.summary.totalIncidents : 0
  // Colours follow the slices; residence halls take on-campus's colour
  const pieGeos = profile ? profile.breakdownByGeo.map((item) => item.geo).filter((geo) => geo !== 'Residence halls') : []
  const geoRows = profile
    ? profile.breakdownByGeo.map((item) => ({
        ...item,
        color: chart.series[Math.max(pieGeos.indexOf(item.geo === 'Residence halls' ? 'On-campus' : item.geo), 0) % chart.series.length],
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

  // Year axis of the trend charts: every year labelled (interval 0), the
  // labels angled at phone width so they do not overlap
  const yearAxisProps = {
    dataKey: 'year',
    interval: 0,
    tick: { fill: chart.text, fontSize: narrow ? 11 : 12 },
    angle: narrow ? -45 : 0,
    textAnchor: narrow ? ('end' as const) : ('middle' as const),
    height: narrow ? 44 : 30,
    axisLine: { stroke: chart.grid },
    tickLine: false,
  }
  const countAxisProps = {
    tickFormatter: (v: number) => formatNumber(v),
    tick: { fill: chart.text, fontSize: 12 },
    axisLine: false,
    tickLine: false,
    width: 44,
  }
  const gridProps = { stroke: chart.grid, vertical: false }
  const bandProps = { fill: chart.band, fillOpacity: 0.07, ifOverflow: 'extendDomain' as const }

  if (loading) {
    return <Loading className="min-h-[60vh]">Loading school data...</Loading>
  }

  if (error || !profile) {
    return (
      <div className="wrap py-10">
        <Link
          to="/"
          className="link inline-flex min-h-[1.5rem] items-center text-meta"
        >
          Back to Rankings
        </Link>

        <div className="mt-6 border-l-2 border-danger pl-4">
          <h3 className="h3 text-danger">School Not Found</h3>
          <p className="mt-1 text-body text-ink-2">
            {error || `Could not find data for school ID ${unitid}`}
          </p>
        </div>
      </div>
    )
  }

  const statLabel = 'text-meta text-ink-3'
  const statSub = 'mt-1 text-meta text-ink-2'
  const statFigure = 'tabular mt-1 text-figure font-semibold text-ink'
  const statText = 'mt-1 text-heading font-semibold text-ink'
  const filterLabel = 'sr-only sm:not-sr-only text-meta text-ink-2'
  const chartTitle = 'font-serif text-[1.25rem] font-semibold leading-snug text-ink mb-4'
  const caption = 'mt-3 text-meta text-ink-3'

  return (
    <div className="min-h-screen">
      {/* Header Section */}
      <div className="wrap pt-6 pb-6 sm:pt-8">
        {/* Back Link */}
        <Link
          to="/"
          className="link inline-flex min-h-[1.5rem] items-center text-meta"
        >
          Back to Rankings
        </Link>

        {/* School Header */}
        <div className="mt-4">
          <h1 className="h1">
            {displayName(profile)}
            {!profile.campus && profile.campusType && profile.isMainCampus === false && (
              <span className="ml-3 font-sans text-heading font-normal text-ink-3">
                (Branch Campus)
              </span>
            )}
          </h1>
          {profile.campus && (
            <p className="mt-1 text-body text-ink-2">Campus of {profile.name}</p>
          )}
          <div className="mt-3 flex flex-col gap-y-1 text-ui text-ink-2 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-5">
            <span>
              {[profile.city, profile.state].filter(Boolean).join(', ')}
            </span>
            {headerFte && (
              <span
                className="tabular"
                title="Enrollment (FTE) of the whole institution for the latest available year; NCES counts enrollment per institution, not per campus"
              >
                Institution FTE: {formatNumber(headerFte.fte)}
                {headerCampuses > 1 && <> (all {headerCampuses} campuses)</>}
                <span className="ml-1 text-meta text-ink-3">({headerFte.year})</span>
              </span>
            )}
            {profile.ivyLeague && (
              <span className="self-center rounded-sm border border-rule-strong px-1.5 text-label font-semibold text-ink-2">Ivy League</span>
            )}
          </div>
          {profile.idChanges && profile.idChanges.length > 0 && (
            <div className="mt-5 max-w-prose border-l-2 border-accent pl-4 text-ui text-ink-2">
              <p className="font-semibold text-ink mb-1">
                This campus has more than one DOE ID
              </p>
              <ul className="space-y-1">
                {profile.idChanges.map((link) => (
                  <li key={link.unitid}>
                    DOE reported this campus under ID {link.unitid} in {compactYears(link.years)}. Those years are on
                    a separate page:{' '}
                    <Link
                      to={`/school/${link.unitid}`}
                      className="link font-semibold"
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
      <div className="sticky top-header z-40 border-y border-rule bg-paper">
        <div className="wrap">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 py-2.5">
            {showRate && rateRules ? (
              <>
                {/* Window (rate view) */}
                <div className="flex items-center gap-2">
                  <label htmlFor="window-select" className={filterLabel}>
                    Years:
                  </label>
                  <select
                    id="window-select"
                    value={selectedWindow ?? ''}
                    onChange={(e) => setSelectedWindow(e.target.value)}
                    className="control w-36"
                  >
                    {windowKeys(rateRules).slice().reverse().map((key) => (
                      <option key={key} value={key}>{windowLabel(key)}</option>
                    ))}
                  </select>
                </div>
                {/* Rate code of the single-year trend (rate view) */}
                <div className="flex items-center gap-2 min-w-0">
                  <label htmlFor="rate-code-select" className={filterLabel}>
                    Trend:
                  </label>
                  <select
                    id="rate-code-select"
                    value={trendCode}
                    onChange={(e) => setTrendCode(e.target.value)}
                    className="control w-64 max-w-full"
                  >
                    {rateCodes(rateRules).map((code) => (
                      <option key={code} value={code}>{rateCodeLabel(code)}</option>
                    ))}
                  </select>
                </div>
              </>
            ) : (
              <>
            {/* Year Dropdown */}
            <div className="flex items-center gap-2">
              <label htmlFor="year-select" className={filterLabel}>
                Year:
              </label>
              <select
                id="year-select"
                value={selectedYear || ''}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className="control w-[6.5rem]"
              >
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {/* Offense/Crime Dropdown */}
            <div className="flex items-center gap-2 min-w-0">
              <label htmlFor="offense-select" className={filterLabel}>
                Crime:
              </label>
              <select
                id="offense-select"
                value={selectedOffense}
                onChange={(e) => setSelectedOffense(e.target.value)}
                className="control w-64 max-w-full"
              >
                <option value={CRIMINAL}>{SUMMARY_LABELS[CRIMINAL]}</option>
                <option value={VIOLENT}>{SUMMARY_LABELS[VIOLENT]}</option>
                <option value={PROPERTY}>{SUMMARY_LABELS[PROPERTY]}</option>
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
                className="min-h-[1.5rem] text-meta font-semibold text-accent underline-offset-[3px] hover:underline"
              >
                Clear filter
              </button>
            )}
              </>
            )}

            {/* Rate Toggle */}
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-meta text-ink-2 hidden sm:inline">View:</span>
              <div role="group" aria-label="View" className="segmented">
                <button
                  type="button"
                  onClick={() => setShowRate(false)}
                  aria-pressed={!showRate}
                >
                  Total
                </button>
                <button
                  type="button"
                  onClick={() => setShowRate(true)}
                  aria-pressed={showRate}
                  title="3-year rates per 10,000 on-campus students"
                >
                  Rate
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="wrap py-8">
        {showRate && metadata && selectedWindow && (
          <RatePanel
            profile={profile}
            metadata={metadata}
            windowKey={selectedWindow}
            trendCode={trendCode}
            countsOnlyNote={countsOnlyNote}
          />
        )}
        {showRate && !metadata && (
          <Loading className="mb-8 justify-start py-8">Loading rates…</Loading>
        )}
        {!showRate && (<>
        {/* Summary figures */}
        <div className="grid grid-cols-1 border-y border-rule sm:grid-cols-2 lg:grid-cols-4">
          <div className="border-b border-rule py-4 sm:pr-6 lg:border-b-0">
            <div className={statLabel}>
              {selectionLabel(selectedOffense)} ({selectedYear})
            </div>
            <div className={statFigure}>
              {formatNumber(selectedYearTotal)}
            </div>
            {selectedYearYoYChange && selectedYearYoYChange.absolute === 0 && (
              <div className={statSub}>
                Same number reported as in {selectedYear && selectedYear - 1}
              </div>
            )}
            {selectedYearYoYChange && selectedYearYoYChange.absolute !== 0 && (
              <div
                className={cn(statSub, 'tabular')}
                title="A change in reported counts can reflect changes in reporting, not only in crime"
              >
                {selectedYearYoYChange.absolute > 0 ? '+' : ''}
                {formatNumber(selectedYearYoYChange.absolute)} reported vs {selectedYear && selectedYear - 1}
              </div>
            )}
          </div>

          <div className="border-b border-rule py-4 sm:border-l sm:pl-6 lg:border-b-0 lg:pr-6">
            <div className={statLabel}>Most Common Criminal Offense</div>
            <div className={statText}>
              {selectedYearTopOffense.offense || 'None'}
            </div>
            <div className={cn(statSub, 'tabular')}>
              {selectedYearTopOffense.offense
                ? `${formatNumber(selectedYearTopOffense.count)} reported ${selectedYearTopOffense.count === 1 ? 'offense' : 'offenses'}`
                : `No criminal offenses reported in ${selectedYear}`}
            </div>
          </div>

          <div className="border-b border-rule py-4 sm:border-b-0 sm:pr-6 lg:border-l lg:pl-6">
            <div className={statLabel}>Data Coverage</div>
            <div className={cn(statText, 'tabular')}>
              {chartYears.length > 0
                ? `${chartYears[0]}-${chartYears[chartYears.length - 1]}`
                : 'N/A'}
            </div>
            <div className={statSub}>
              {availableYears.length} {availableYears.length === 1 ? 'year' : 'years'} reported
            </div>
            {notReportedYears.length > 0 && (
              <div className="mt-0.5 text-meta text-ink-3">
                Not reported: {notReportedYears.join(', ')}
              </div>
            )}
          </div>

          <div className="py-4 sm:border-l sm:pl-6">
            <div className={statLabel}>Categories ({selectedYear})</div>
            <div className={statFigure}>
              {selectedYearOffenseBreakdown.length}
            </div>
            <div className={statSub}>Categories above 0 (crimes, arrests, referrals)</div>
          </div>
        </div>

        {/* Notes on the selected year's figures */}
        <div className="mt-4 max-w-prose space-y-3 empty:hidden">
          {/* Comparability note for the selected year (data/seriesNotes.ts) */}
          {selectedYear !== null && <SeriesNotes years={[selectedYear]} />}

          {/* Figures shared with another campus (counted once, under the host) */}
          {selectedYearShared.length > 0 && (
            <div role="note" className="space-y-1">
              {selectedYearShared.map((entry) => (
                <p
                  key={entry.hostUnitid}
                  className="text-meta text-ink-2"
                >
                  <span className="font-semibold text-ink">
                    {selectedYear} {joinWithAnd(entry.geos)} figures:
                  </span>{' '}
                  These figures are also reported by{' '}
                  <Link
                    to={`/school/${entry.hostUnitid}`}
                    className="link"
                  >
                    {entry.hostName}
                  </Link>{' '}
                  and are counted once, under {entry.hostName}, in totals and rankings.
                </p>
              ))}
            </div>
          )}

          {/* Unusual-year flags of the selected year (the institution's, every location) */}
          {selectedYearFlags.length > 0 && (
            <div role="note" className="space-y-1 border-l-2 border-attention pl-3 text-meta text-ink-2">
              <p className="flex items-center gap-1.5 font-semibold text-ink">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-attention" aria-hidden="true" />
                Unusual year{institutionCampuses > 1 ? ` for ${profile.name} (all ${institutionCampuses} of its campuses)` : ''}
              </p>
              {selectedYearFlags.map((f) => (
                <p key={f}>{f}</p>
              ))}
              <p>
                Flags never change counts.{' '}
                <Link to="/methodology#rate-flags" className="link">How flags work</Link>
              </p>
            </div>
          )}

          {/* A count very high for the institution's size (rankings by count, highForSize) */}
          {sizeFlag && (
            <div role="note" className="space-y-1 border-l-2 border-attention pl-3 text-meta text-ink-2">
              <p className="flex items-center gap-1.5 font-semibold text-ink">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-attention" aria-hidden="true" />
                Very high for its institution's size
              </p>
              <p>
                {highForSizeParagraph(sizeFlag.count, sizeFlag.fte, sizeFlag.campuses, sizeFlag.code, sizeFlag.year, metadata)}{' '}
                <Link to="/methodology#count-flag" className="link">How this flag works</Link>
              </p>
            </div>
          )}
        </div>

        {/* Charts Row */}
        <div className="mt-10 grid grid-cols-1 gap-x-12 gap-y-12 lg:grid-cols-2">
          {/* Yearly Trend Chart - changes based on offense filter */}
          <section className="min-w-0">
            <h2 className={chartTitle}>
              {selectionLabel(selectedOffense)} Over Time
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={yearlyChartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid {...gridProps} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} {...bandProps} />
                ))}
                <XAxis {...yearAxisProps} />
                <YAxis {...countAxisProps} />
                <Tooltip
                  formatter={(value: number) => formatNumber(value)}
                  {...tooltipProps(chart)}
                  cursor={barCursor(chart)}
                />
                <Bar
                  dataKey="count"
                  name={selectionLabel(selectedOffense)}
                  radius={[2, 2, 0, 0]}
                  // A reported 0 gets a thin bar so it differs from a year not
                  // reported (null), which gets none
                  minPointSize={(value: number | null | undefined) => (value == null ? 0 : 3)}
                >
                  {yearlyChartData.map((entry) => (
                    <Cell
                      key={entry.year}
                      fill={entry.year === selectedYear ? chart.selected : chart.bar}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className={caption}>
              Selected year highlighted in blue · A thin bar is 0
              {chartGaps.length > 0 && (
                <> · No bar for {chartGaps.join(', ')}: not reported (no figures, not 0)</>
              )}
              {noteBands.length > 0 && <> · Shaded years have a note below</>}
            </p>
            <SeriesNotes years={chartYears} className="mt-2" />
            <ReportYearNote className="mt-1" />
          </section>

          {/* Top Offenses Trend - only show when viewing a summary */}
          {isSummary(selectedOffense) ? (
            <section className="min-w-0">
              <h2 className={chartTitle}>
                {topOffenses.length > 0 ? `Top ${Math.min(topOffenses.length, 5)} Offenses Over Time` : 'Offenses Over Time'}
              </h2>
              {topOffenses.length === 0 ? (
                <div className="flex h-[300px] items-center justify-center border-y border-rule text-center text-meta text-ink-3">
                  0 in every year this campus reported ({selectionLabel(selectedOffense).toLowerCase()})
                </div>
              ) : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trendChartData} margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid {...gridProps} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} {...bandProps} />
                ))}
                  <XAxis {...yearAxisProps} />
                  <YAxis {...countAxisProps} />
                  <Tooltip
                    formatter={(value: number) => formatNumber(value)}
                    {...tooltipProps(chart)}
                    cursor={lineCursor(chart)}
                  />
                  <Legend
                    iconSize={18}
                    wrapperStyle={{ color: chart.text, fontSize: 13, paddingTop: 8 }}
                  />
                  {topOffenses.map((offense, i) => (
                    <Line
                      key={offense}
                      type="monotone"
                      dataKey={offense}
                      stroke={chart.series[i % chart.series.length]}
                      strokeDasharray={SERIES_DASHES[i % SERIES_DASHES.length]}
                      strokeWidth={2}
                      dot={{ r: 2.5, strokeDasharray: '' }}
                      activeDot={{ r: 4.5 }}
                      legendType="plainline"
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              )}
            </section>
          ) : (
            <section className="min-w-0">
              <h2 className={chartTitle}>
                {selectedOffense} Trend
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={yearlyChartData} margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid {...gridProps} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} {...bandProps} />
                ))}
                  <XAxis {...yearAxisProps} />
                  <YAxis {...countAxisProps} />
                  <Tooltip
                    formatter={(value: number) => formatNumber(value)}
                    {...tooltipProps(chart)}
                    cursor={lineCursor(chart)}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke={chart.selected}
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: chart.selected }}
                    activeDot={{ r: 5 }}
                    name={selectedOffense}
                  />
                </LineChart>
              </ResponsiveContainer>
              <p className={caption}>
                Showing trend for {selectedOffense} only
              </p>
            </section>
          )}
        </div>

        {/* Breakdowns Row */}
        <div className="mt-12 grid grid-cols-1 gap-x-12 gap-y-12 lg:grid-cols-2">
          {/* By Offense Type */}
          <section className="min-w-0">
            <h2 className={chartTitle}>
              By Category ({selectedYear})
            </h2>
            {selectedYearOffenseBreakdown.length === 0 ? (
              <div className="border-y border-rule py-8 text-center text-meta text-ink-3">
                {/* Only reported years can be selected, so this is a 0, not missing data */}
                No incidents in {selectedYear} (every figure reported was 0)
              </div>
            ) : (
              <div className="border-t border-rule">
                {selectedYearOffenseBreakdown.slice(0, 10).map((item) => {
                  const maxCount = selectedYearOffenseBreakdown[0]?.count || 1
                  const percentage = (item.count / maxCount) * 100
                  const isSelected = item.offense === selectedOffense

                  return (
                    <button
                      key={item.offense}
                      type="button"
                      onClick={() => setSelectedOffense(item.offense === selectedOffense ? CRIMINAL : item.offense)}
                      aria-pressed={isSelected}
                      className={cn(
                        'flex w-full items-center gap-4 border-b border-rule px-2 py-2 text-left',
                        isSelected ? 'bg-accent-tint' : 'hover:bg-subtle'
                      )}
                    >
                      <div className={cn(
                        'w-36 sm:w-44 flex-shrink-0 truncate text-meta',
                        isSelected ? 'font-semibold text-ink' : 'text-ink-2'
                      )}>
                        {item.offense}
                      </div>
                      <div className="flex-1">
                        <div
                          className="h-2.5 rounded-r-sm"
                          style={{
                            width: `${Math.max(percentage, 0.5)}%`,
                            backgroundColor: isSelected ? chart.selected : chart.bar,
                          }}
                        />
                      </div>
                      <div className="tabular w-14 text-right text-ui font-semibold text-ink">
                        {formatNumber(item.count)}
                      </div>
                    </button>
                  )
                })}
                {selectedYearOffenseBreakdown.length > 10 && (
                  <p className="mt-3 text-meta text-ink-3">
                    Showing top 10 of {selectedYearOffenseBreakdown.length} offense types
                  </p>
                )}
              </div>
            )}
            <p className="mt-2 text-meta text-ink-3">
              Click an offense to filter charts
            </p>
          </section>

          {/* By Location */}
          <section className="min-w-0">
            <h2 className={chartTitle}>
              By Location
              <span className="ml-2 font-sans text-meta font-normal text-ink-3">
                ({profile.summary.latestYear}, all categories)
              </span>
            </h2>

            {geoRows.length === 0 ? (
              // A reported year in which every figure was 0
              <div className="border-y border-rule py-8 text-center text-meta text-ink-3">
                No incidents in {profile.summary.latestYear} (every figure reported was 0)
              </div>
            ) : (
            <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
              {/* Pie Chart */}
              <div className="h-44 w-44 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={geoPieRows}
                      dataKey="count"
                      nameKey="geo"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      innerRadius={50}
                      paddingAngle={0}
                      stroke={chart.tooltipBg}
                      strokeWidth={2}
                      isAnimationActive={false}
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
                      {...tooltipProps(chart)}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Legend */}
              <div className="w-full flex-1 border-t border-rule">
                {geoRows.map((item) => {
                  const pct = item.pct
                  // Residence halls are part of on-campus (not a slice of their own)
                  const subset = item.geo === 'Residence halls'

                  return (
                    <div key={item.geo} className="flex items-center gap-3 border-b border-rule py-2">
                      <div
                        className={cn('h-3 w-3 flex-shrink-0 rounded-sm', subset && 'ml-4 border-2 bg-transparent')}
                        style={subset ? { borderColor: item.color } : { backgroundColor: item.color }}
                      />
                      <div className="flex-1 text-meta text-ink-2">{item.geo}</div>
                      <div className="tabular w-16 text-right text-ui font-semibold text-ink">
                        {formatNumber(item.count)}
                      </div>
                      <div className="tabular w-14 text-right text-meta text-ink-3">
                        {pct !== null ? formatPercent(pct) : '—'}
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
                  <p key={d.file} className="text-meta text-ink-2">
                    {d.takenFrom
                      ? <>{d.year} residence-hall {categoryLabel(d.category)} come from DOE's {releaseLabel(d.takenFrom)} release, because that file of the {releaseLabel(d.release)} release, which this campus's {d.year} figures come from, is wrong.</>
                      : <>{d.year} residence-hall {categoryLabel(d.category)} are not included: that file of DOE's {releaseLabel(d.release)} release, which this campus's {d.year} figures come from, is wrong, and no other release has them.</>}{' '}
                    <Link to="/methodology#known-defects" className="link">Details</Link>
                  </p>
                ))}
              </div>
            )}

            <p className="mt-4 text-meta text-ink-2">
              <strong className="font-semibold text-ink">Important:</strong> Residence hall incidents are a subset of on-campus incidents.
              Do not add these categories together — this would result in double-counting.
            </p>
          </section>
        </div>
        </>)}

        <CiteThisData school={{ unitid: profile.unitid, name: profile.campus ? `${profile.campus} (${profile.name})` : profile.name }} className="mt-12" />
      </div>
    </div>
  )
}
