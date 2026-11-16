import { useState, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceArea,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import { X, ChevronDown } from 'lucide-react'
import { fetchSchoolProfile, fetchSchoolIndex, fetchPresets, getMetadata } from '../lib/api'
import type { SchoolProfile, School, PresetDetail, SchoolIndex, Metadata } from '../lib/types'
import { cn, formatNumber, calculateYoYChange, displayName as titleOf, withParams } from '../lib/utils'
import {
  chooseWindow, countsOnlyReason, fteFor, latestFte, rateCodeForSelection, rateCodeLabel, rateCodes, windowKeys,
  windowLabel,
} from '../lib/rates'
import CompareRates from '../components/CompareRates'
import {
  ALL, CRIMINAL, PROPERTY, SUMMARY_LABELS, VIOLENT, inSelection, isSummary, selectionCode, selectionFromParam, selectionLabel,
} from '../lib/selection'
import { SERIES_DASHES, barCursor, lineCursor, tooltipProps, useChartTheme } from '../lib/chartTheme'
import { Loading, SchoolSwatch } from '../components/ui'
import { useMediaQuery } from '../hooks/useMediaQuery'
import SeriesNotes, { ReportYearNote } from '../components/SeriesNotes'
import { SERIES_NOTES } from '../data/seriesNotes'

// One school's count of `selection` ('criminal', 'all' or an offense name)
// in `year`: 0 when it reported the year without any of it, null when it did
// not report that year (no figures at all).
function selectionCount(p: SchoolProfile, year: number, selection: string): number | null {
  if (!p.yearlyTotals.some((yt) => yt.year === year)) return null
  return p.trends
    .filter((t) => t.year === year && inSelection(t, selection))
    .reduce((sum, t) => sum + t.count, 0)
}

// The UNITIDs in ?schools= (at most 2)
function parseSchoolIds(value: string | null): number[] {
  return (value ?? '')
    .split(',')
    .map((id) => parseInt(id))
    .filter((id) => !isNaN(id))
    .slice(0, 2)
}

export default function Compare() {
  const [searchParams, setSearchParams] = useSearchParams()
  // Phone width: the year axis labels are angled so that every year fits
  const narrow = useMediaQuery('(max-width: 639px)')

  // State
  const [schools, setSchools] = useState<School[]>([])
  const [profiles, setProfiles] = useState<SchoolProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // The schools compared: ?schools=<UNITID>,<UNITID>. Adding or removing one
  // adds a history entry.
  const schoolsParam = searchParams.get('schools')
  const selectedIds = useMemo(() => parseSchoolIds(schoolsParam), [schoolsParam])
  const setSchoolIds = (ids: number[]) =>
    setSearchParams((prev) => withParams(prev, { schools: ids.length > 0 ? ids.join(',') : null }))

  // The other selections, changed in place: ?year=, ?offense= and ?view=rate
  const setSelection = (changes: Record<string, string | null>) =>
    setSearchParams((prev) => withParams(prev, changes), { replace: true })
  const showRate = searchParams.get('view') === 'rate'
  const setShowRate = (rate: boolean) => setSelection({ view: rate ? 'rate' : null })
  // metadata.json: the rate rules and figures
  const [metadata, setMetadata] = useState<Metadata | null>(null)
  const rateRules = metadata?.rateRules ?? null

  useEffect(() => {
    getMetadata()
      .then(setMetadata)
      .catch(() => setMetadata(null))
  }, [])

  // Load school list on mount - try school index first, fallback to Ivy preset
  useEffect(() => {
    fetchSchoolIndex()
      .then((index: SchoolIndex) => {
        setSchools(index.schools)
      })
      .catch(() => {
        // Fallback to Ivy League preset if school index not available
        fetchPresets()
          .then((presets) => {
            const ivyPreset = presets['ivy'] as PresetDetail
            if (ivyPreset) {
              setSchools(ivyPreset.schools)
            }
          })
          .catch(() => setError('Failed to load schools. Please try again.'))
      })
  }, [])

  // Load profiles when selection changes
  useEffect(() => {
    if (selectedIds.length === 0) {
      setProfiles([])
      return
    }

    setLoading(true)
    setError(null)

    Promise.all(selectedIds.map((id) => fetchSchoolProfile(id)))
      .then((results) => {
        setProfiles(results)
        setLoading(false)
      })
      .catch(() => {
        setError('Failed to load comparison data. Please try again.')
        setLoading(false)
      })
  }, [selectedIds])

  // Add a school
  const addSchool = (unitid: number) => {
    if (selectedIds.length < 2 && !selectedIds.includes(unitid)) {
      setSchoolIds([...selectedIds, unitid])
    }
    setIsDropdownOpen(false)
  }

  // Remove a school
  const removeSchool = (unitid: number) => {
    setSchoolIds(selectedIds.filter((id) => id !== unitid))
  }

  // Get available years from all profiles (union)
  const availableYears = useMemo(() => {
    if (profiles.length === 0) return []
    const years = new Set<number>()
    profiles.forEach(p => p.yearlyTotals.forEach(yt => years.add(yt.year)))
    return Array.from(years).sort((a, b) => b - a) // Newest first
  }, [profiles])

  // Get available offenses from all profiles (union)
  const availableOffenses = useMemo(() => {
    if (profiles.length === 0) return []
    const offenses = new Set<string>()
    profiles.forEach(p => p.trends.forEach(t => offenses.add(t.offense)))
    return Array.from(offenses).sort()
  }, [profiles])

  // ?year=: a year either school reported, or 'all' (default). ?offense=: a
  // summary or an offense code such as motor_vehicle_theft (default all
  // criminal offenses).
  const yearParam = searchParams.get('year')
  const selectedYear = yearParam !== null && availableYears.includes(Number(yearParam)) ? String(Number(yearParam)) : 'all'
  const setSelectedYear = (year: string) => setSelection({ year: year === 'all' ? null : year })
  // 'criminal' (default), 'all' (every category) or one offense name
  const selectedOffense = selectionFromParam(searchParams.get('offense'), availableOffenses, CRIMINAL)
  const setSelectedOffense = (offense: string) =>
    setSelection({ offense: offense === CRIMINAL ? null : selectionCode(offense) })
  // Rate view: ?window= (a 3-year window; default the one ending in ?year=,
  // else the latest) and ?offense= read as a rate code (criminal: criminal
  // offenses except motor-vehicle theft; property: burglary)
  const selectedWindow = chooseWindow(rateRules, searchParams.get('window'), yearParam ? Number(yearParam) : null)
  const rawOffense = searchParams.get('offense')?.trim().toLowerCase() ?? null
  const rateCode = rateRules
    ? (rawOffense && rawOffense in rateRules.codes ? rawOffense : rateCodeForSelection(selectionCode(selectedOffense), rateRules))
    : null
  const countsOnlyNote = rateRules && rateCode === null
    ? countsOnlyReason(selectionCode(selectedOffense), selectionLabel(selectedOffense))
    : null

  // Track which years have data for each profile (for the selected offense)
  const yearDataByProfile = useMemo(() => {
    const result: Map<number, Map<number, boolean>> = new Map()
    profiles.forEach(p => {
      const yearMap = new Map<number, boolean>()
      if (isSummary(selectedOffense)) {
        p.yearlyTotals.forEach(yt => yearMap.set(yt.year, (selectionCount(p, yt.year, selectedOffense) ?? 0) > 0))
      } else {
        availableYears.forEach(year => yearMap.set(year, false))
        p.trends
          .filter(t => t.offense === selectedOffense && t.count > 0)
          .forEach(t => yearMap.set(t.year, true))
      }
      result.set(p.unitid, yearMap)
    })
    return result
  }, [profiles, selectedOffense, availableYears])

  // Check if any profile has data for the current selection
  const anyProfileHasData = useMemo(() => {
    if (selectedYear === 'all') return true
    const year = parseInt(selectedYear)
    return profiles.some(p => {
      const yearMap = yearDataByProfile.get(p.unitid)
      return yearMap?.get(year) ?? false
    })
  }, [profiles, selectedYear, yearDataByProfile])

  // Get available schools (not already selected, filtered by search)
  const filteredSchools = useMemo(() => {
    const available = schools.filter((s) => !selectedIds.includes(s.unitid))

    if (!searchQuery.trim()) {
      // Show first 20 schools when no search
      return available.slice(0, 20)
    }

    const query = searchQuery.toLowerCase()
    return available
      .filter((s) =>
        s.name.toLowerCase().includes(query) ||
        (s.campus && s.campus.toLowerCase().includes(query)) ||
        (s.city && s.city.toLowerCase().includes(query)) ||
        (s.state && s.state.toLowerCase().includes(query))
      )
      .slice(0, 20) // Limit results for performance
  }, [schools, selectedIds, searchQuery])

  // Prepare trend chart data (respects offense filter, uses null for missing data)
  const trendChartData = useMemo(() => {
    if (profiles.length === 0) return []

    // Get all years across all schools
    const allYears = new Set<number>()
    profiles.forEach((p) => {
      p.yearlyTotals.forEach((yt) => allYears.add(yt.year))
    })

    const years = Array.from(allYears).sort()

    return years.map((year) => {
      const point: Record<string, number | string | null> = { year }
      profiles.forEach((p) => {
        // null if no data for this year (shows gap in chart)
        point[p.shortName || p.name] = selectionCount(p, year, selectedOffense)
      })
      return point
    })
  }, [profiles, selectedOffense])

  // Prepare offense comparison data (respects year filter, uses null for missing data)
  const offenseComparisonData = useMemo(() => {
    if (profiles.length !== 2) return []

    // Get offense counts for the selected year (or all years)
    const offenseCounts = new Map<string, number>()
    profiles.forEach((p) => {
      if (selectedYear === 'all') {
        // Sum across ALL years from trends (not breakdownByOffense which is latest year only)
        p.trends.forEach((t) => {
          offenseCounts.set(t.offense, (offenseCounts.get(t.offense) || 0) + t.count)
        })
      } else {
        // Filter to selected year
        const year = parseInt(selectedYear)
        p.trends
          .filter((t) => t.year === year)
          .forEach((t) => {
            offenseCounts.set(t.offense, (offenseCounts.get(t.offense) || 0) + t.count)
          })
      }
    })

    const topOffenses = Array.from(offenseCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([offense]) => offense)

    return topOffenses.map((offense) => {
      const point: Record<string, number | string | null> = { offense }
      profiles.forEach((p) => {
        if (selectedYear === 'all') {
          // Sum this offense across ALL years from trends (0 when it had none)
          point[p.shortName || p.name] = p.trends
            .filter((t) => t.offense === offense)
            .reduce((sum, t) => sum + t.count, 0)
        } else {
          // 0 in a reported year without it, null in a year not reported
          point[p.shortName || p.name] = selectionCount(p, parseInt(selectedYear), offense)
        }
      })
      return point
    })
  }, [profiles, selectedYear])

  // Compute filtered metrics for each profile
  const filteredMetrics = useMemo(() => {
    return profiles.map((profile) => {
      let totalIncidents: number | null = null
      let yoyChange: { absolute: number; percent: number | null } | null = null

      if (selectedYear === 'all') {
        // Sum across ALL years of the profile that have a count
        const counts = profile.yearlyTotals
          .map((yt) => selectionCount(profile, yt.year, selectedOffense))
          .filter((c): c is number => c !== null)
        totalIncidents = counts.length > 0 ? counts.reduce((sum, c) => sum + c, 0) : null
        // Don't show YoY for "All Years" - comparing latest 2 years is misleading when showing all-year totals
        yoyChange = null
      } else {
        const year = parseInt(selectedYear)
        totalIncidents = selectionCount(profile, year, selectedOffense)
        const previous = selectionCount(profile, year - 1, selectedOffense)
        if (totalIncidents !== null && previous !== null) {
          yoyChange = calculateYoYChange(totalIncidents, previous)
        }
      }

      return {
        unitid: profile.unitid,
        totalIncidents,
        yoyChange,
        hasData: totalIncidents !== null,
      }
    })
  }, [profiles, selectedYear, selectedOffense])

  // FTE label for each school, with the year it belongs to: the selected
  // year's FTE, or with "All Years" the newest FTE. The FTE is the whole
  // institution's (NCES counts enrollment per institution).
  const fteLabels = useMemo(() => {
    const year = selectedYear !== 'all' ? parseInt(selectedYear) : null
    const labels = new Map<number, string>()
    profiles.forEach((profile) => {
      const yearFte = year !== null ? fteFor(profile, year) : null
      const label = year === null ? latestFte(profile) : (yearFte !== null ? { year, fte: yearFte } : null)
      if (!label) return
      const campuses = profile.institution?.byYear[String(label.year)]?.campuses ?? 1
      const where = campuses > 1 ? `, all ${campuses} campuses` : ''
      labels.set(profile.unitid, `Institution FTE ${formatNumber(label.fte)} (${label.year}${where})`)
    })
    return labels
  }, [profiles, selectedYear])

  // Calculate top offense for each profile based on current filters (the
  // offenses of the selected summary only)
  const profileTopOffenses = useMemo(() => {
    return profiles.map(profile => {
      const trends = profile.trends.filter(t => inSelection(t, selectedOffense))
      if (selectedYear === 'all') {
        // Sum all offenses across all years from trends
        const offenseTotals = new Map<string, number>()
        trends.forEach(t => {
          offenseTotals.set(t.offense, (offenseTotals.get(t.offense) || 0) + t.count)
        })
        const sorted = Array.from(offenseTotals.entries()).sort((a, b) => b[1] - a[1])
        return sorted.length > 0 ? { offense: sorted[0][0], count: sorted[0][1] } : { offense: null, count: 0 }
      } else {
        // For single year, calculate from trends for that year
        const year = parseInt(selectedYear)
        const yearTrends = trends.filter(t => t.year === year)
        const sorted = yearTrends.sort((a, b) => b.count - a.count)
        return sorted.length > 0 ? { offense: sorted[0].offense, count: sorted[0].count } : { offense: null, count: 0 }
      }
    })
  }, [profiles, selectedYear, selectedOffense])

  // Chart styling for the current theme. The two schools are told apart by
  // colour and by pattern: the second school's line is dashed and its bars
  // hatched, and its swatch is hatched too
  const chart = useChartTheme()
  const schoolColors = [chart.series[0], chart.series[1]]
  // Years with a sourced comparability note (data/seriesNotes.ts), shaded on the trend chart
  const noteBands = SERIES_NOTES.map((n) => n.years.filter((y) => availableYears.includes(y)))
    .filter((ys) => ys.length > 0)
    .map((ys) => ({ x1: Math.min(...ys), x2: Math.max(...ys) }))
  const swatch = (index: number) => <SchoolSwatch color={schoolColors[index]} hatched={index === 1} />
  const filterLabel = 'sr-only sm:not-sr-only text-meta text-ink-2'
  const sectionTitle = 'font-serif text-[1.25rem] font-semibold leading-snug text-ink mb-4'
  const cellLabel = 'py-3 pr-4 text-meta text-ink-2'

  return (
    <div className="wrap pt-8 pb-8 sm:pt-10">
      {/* Header */}
      <div className="mb-6">
        <h1 className="h1">
          Compare Schools
        </h1>
      </div>

      {/* School Selection */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          {/* Selected Schools */}
          {selectedIds.map((id, index) => {
            const school = schools.find((s) => s.unitid === id)
            const profile = profiles.find((p) => p.unitid === id)
            const displayName = school?.short || profile?.shortName || (school ? titleOf(school) : null) || 'Unknown'
            if (!school && !profile) return null
            return (
              <div
                key={id}
                className="flex h-10 items-center gap-2 rounded border border-rule-strong bg-surface pl-3 pr-1"
              >
                {swatch(index)}
                <span className="text-ui font-semibold text-ink">
                  {displayName.length > 25 ? displayName.slice(0, 25) + '...' : displayName}
                </span>
                {school?.state && (
                  <span className="text-meta text-ink-3">
                    {school.state}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => removeSchool(id)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded text-ink-3 hover:bg-subtle hover:text-ink"
                  aria-label={`Remove ${school ? titleOf(school) : profile?.name || 'school'} from comparison`}
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>
            )
          })}

          {/* Add School Dropdown with Search */}
          {selectedIds.length < 2 && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                className="btn h-10 border-dashed font-normal text-ink-2"
              >
                <span>Add School</span>
                <ChevronDown className={cn('w-4 h-4 transition-transform', isDropdownOpen && 'rotate-180')} aria-hidden="true" />
              </button>

              {isDropdownOpen && (
                <div className="absolute left-0 top-full z-50 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded border border-rule-strong/60 bg-surface shadow-pop">
                  {/* Search Input */}
                  <div className="border-b border-rule p-2">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search schools..."
                      className="control w-full"
                      autoFocus
                    />
                  </div>

                  {/* School List */}
                  <div className="max-h-64 overflow-y-auto py-1">
                    {filteredSchools.length === 0 ? (
                      <div className="px-4 py-3 text-meta text-ink-2">
                        {searchQuery ? 'No schools found' : 'Loading schools...'}
                      </div>
                    ) : (
                      filteredSchools.map((school) => (
                        <button
                          key={school.unitid}
                          type="button"
                          onClick={() => {
                            addSchool(school.unitid)
                            setSearchQuery('')
                          }}
                          className="w-full px-3.5 py-2 text-left hover:bg-subtle"
                        >
                          <div className="text-ui font-semibold text-ink">
                            {titleOf(school)}
                            {school.isMainCampus === false && !school.campus && (
                              <span className="ml-1.5 text-meta font-normal text-ink-3">(Branch)</span>
                            )}
                          </div>
                          <div className="text-meta text-ink-3">
                            {school.city && school.state ? `${school.city}, ${school.state}` : school.state || ''}
                          </div>
                        </button>
                      ))
                    )}
                    {filteredSchools.length === 20 && searchQuery && (
                      <div className="border-t border-rule px-3.5 py-2 text-meta text-ink-3">
                        Showing first 20 results. Type more to narrow search.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {selectedIds.length === 0 && (
          <p className="mt-4 text-body text-ink-2">
            Select two schools above to begin comparing their statistics.
          </p>
        )}
      </div>

      {/* Sticky Filter Bar - only show when 2 schools selected */}
      {profiles.length === 2 && (
        <div className="sticky top-header z-40 -mx-4 mb-6 border-y border-rule bg-paper px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 py-2.5">
            {showRate && rateRules ? (
              <>
                {/* Window (rate view) */}
                <div className="flex items-center gap-2">
                  <label htmlFor="compare-window-select" className={filterLabel}>
                    Years:
                  </label>
                  <select
                    id="compare-window-select"
                    value={selectedWindow ?? ''}
                    onChange={(e) => setSelection({ window: e.target.value })}
                    className="control w-36"
                  >
                    {windowKeys(rateRules).slice().reverse().map((key) => (
                      <option key={key} value={key}>{windowLabel(key)}</option>
                    ))}
                  </select>
                </div>
                {/* Rate code (rate view) */}
                <div className="flex items-center gap-2 min-w-0 max-w-full">
                  <label htmlFor="compare-rate-code-select" className={filterLabel}>
                    Rate:
                  </label>
                  <select
                    id="compare-rate-code-select"
                    value={rateCode ?? ''}
                    onChange={(e) => setSelection({ offense: e.target.value })}
                    className="control w-64 max-w-full"
                  >
                    {rateCode === null && <option value="">Choose a rate</option>}
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
              <label htmlFor="compare-year-select" className={filterLabel}>
                Year:
              </label>
              <select
                id="compare-year-select"
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="control w-36"
              >
                <option value="all">All Years</option>
                {availableYears.map((year) => (
                  // A year a school reported without the offense is a 0, not missing data
                  <option key={year} value={year.toString()}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {/* Offense Dropdown */}
            <div className="flex items-center gap-2 min-w-0">
              <label htmlFor="compare-offense-select" className={filterLabel}>
                Crime:
              </label>
              <select
                id="compare-offense-select"
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
              </>
            )}

            {/* Rate Toggle */}
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
              >
                Rate
              </button>
            </div>

            {/* Clear filters */}
            {!showRate && (selectedYear !== 'all' || selectedOffense !== CRIMINAL) && (
              <button
                type="button"
                // One change of the address for both (two would each start
                // from the same address, and the second would undo the first)
                onClick={() => setSelection({ year: null, offense: null })}
                className="min-h-[1.5rem] text-meta font-semibold text-accent underline-offset-[3px] hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      )}

      {/* Comparability note for the selected year (data/seriesNotes.ts) */}
      {profiles.length === 2 && !showRate && selectedYear !== 'all' && (
        <SeriesNotes years={[parseInt(selectedYear)]} className="mb-3 max-w-prose" />
      )}

      {/* Comparison context (counts) */}
      {profiles.length === 2 && !showRate && (
        <p className="mb-6 max-w-prose text-meta text-ink-2">
          Comparing counts of {selectionLabel(selectedOffense).toLowerCase()}. Larger institutions report more
          incidents because they are larger; "Rate" shows 3-year rates per 10,000 on-campus students.
        </p>
      )}

      {/* Rate view */}
      {profiles.length === 2 && showRate && metadata && selectedWindow && !loading && (
        rateCode ? (
          <CompareRates
            profiles={profiles}
            metadata={metadata}
            windowKey={selectedWindow}
            code={rateCode}
            colors={schoolColors}
          />
        ) : (
          <p role="note" className="aside-note mb-8 max-w-prose">
            {countsOnlyNote} Choose a rate above.
          </p>
        )
      )}

      {/* No Data Message */}
      {profiles.length === 2 && !showRate && !anyProfileHasData && (selectedYear !== 'all' || !isSummary(selectedOffense)) && (
        <div className="mb-8 max-w-prose border-l-2 border-rule-strong pl-4">
          <h3 className="h3">
            None at either school
          </h3>
          <p className="mt-1 text-ui text-ink-2">
            Neither school has any {selectedOffense === CRIMINAL ? 'criminal offenses' : selectedOffense === VIOLENT ? 'violent crimes' : selectedOffense === PROPERTY ? 'property crimes' : selectedOffense === ALL ? 'crimes, arrests or referrals' : `${selectedOffense} incidents`}
            {selectedYear !== 'all' ? ` in ${selectedYear}` : ''}: each had 0, or did not report that year.
            Try selecting a different year or offense.
          </p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="mb-8 border-l-2 border-danger pl-4">
          <h3 className="h3 text-danger">Error Loading Data</h3>
          <p className="mt-1 text-body text-ink-2">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <Loading className="min-h-[400px]">Loading schools...</Loading>
      )}

      {/* Comparison Content */}
      {!loading && !showRate && profiles.length === 2 && (
        <>
          {/* Key Metrics */}
          <section className="mb-12">
            <h2 className={sectionTitle}>
              Key Metrics
              {selectedYear === 'all' ? ' (All Years)' : ` (${selectedYear})`}
              {` - ${selectionLabel(selectedOffense)}`}
            </h2>

            {/* Desktop: Table Layout */}
            <div className="hidden sm:block">
              <table className="w-full border-collapse text-ui">
                <thead>
                  <tr className="border-b border-ink/60">
                    <th className="w-1/3 py-2 pr-4 text-left align-bottom text-meta font-semibold text-ink-2">
                      Metric
                    </th>
                    {profiles.map((profile, index) => (
                      <th
                        key={profile.unitid}
                        className="py-2 pl-4 text-right align-bottom"
                      >
                        <div className="flex items-center justify-end gap-2 text-ui font-semibold text-ink">
                          {swatch(index)}
                          <span>
                            {profile.shortName || profile.name}
                            {profile.isMainCampus === false && (
                              <span className="ml-1 font-normal text-ink-3">(Branch)</span>
                            )}
                          </span>
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="tabular mt-0.5 text-meta font-normal text-ink-3">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule border-b border-rule">
                  {/* Total Incidents / Rate */}
                  <tr>
                    <td className={cellLabel}>
                      {selectionLabel(selectedOffense)}
                    </td>
                    {profiles.map((profile) => {
                      const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                      return (
                        <td key={profile.unitid} className="num py-3 pl-4">
                          {metrics?.totalIncidents !== null && metrics?.totalIncidents !== undefined ? (
                              <span className="text-figure font-semibold text-ink">
                                {formatNumber(metrics.totalIncidents)}
                              </span>
                            ) : (
                              // A year the school did not report: no figures, not 0
                              <span className="text-ui text-ink-3">
                                {selectedYear === 'all' ? 'N/A' : 'Not reported'}
                              </span>
                            )}
                        </td>
                      )
                    })}
                  </tr>

                  {/* YoY Change */}
                  <tr>
                    <td className={cellLabel}>
                      Year-over-Year Change
                    </td>
                    {profiles.map((profile) => {
                      const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                      const yoy = metrics?.yoyChange
                      return (
                        <td key={profile.unitid} className="num py-3 pl-4">
                          {yoy ? (
                            <span className="text-heading font-semibold text-ink">
                              {yoy.absolute > 0 ? '+' : ''}{formatNumber(yoy.absolute)}
                            </span>
                          ) : (
                            <span className="text-ink-3">N/A</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>

                  {/* Top Offense - only show when not filtering by specific offense */}
                  {isSummary(selectedOffense) && (
                    <tr>
                      <td className={cellLabel}>
                        Most Common Offense
                      </td>
                      {profiles.map((profile, index) => {
                        const topOffense = profileTopOffenses[index]
                        return (
                          <td key={profile.unitid} className="py-3 pl-4 text-right">
                            <div className="font-semibold text-ink">
                              {topOffense?.offense || 'N/A'}
                            </div>
                            {topOffense && topOffense.count > 0 && (
                              <div className="tabular text-meta text-ink-2">
                                {formatNumber(topOffense.count)} incidents
                              </div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Mobile: Card Layout */}
            <div className="sm:hidden divide-y divide-rule border-y border-rule">
              {/* Total Incidents / Rate */}
              <div className="py-4">
                <div className="mb-2 text-meta font-semibold text-ink-2">
                  {selectionLabel(selectedOffense)}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {profiles.map((profile, index) => {
                    const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                    return (
                      <div key={profile.unitid}>
                        <div className="flex items-center gap-1.5 text-meta font-semibold text-ink">
                          {swatch(index)}
                          <span>
                            {profile.shortName || profile.name}
                            {profile.isMainCampus === false && (
                              <span className="ml-1 font-normal text-ink-3">(Branch)</span>
                            )}
                          </span>
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="tabular mb-1 text-label text-ink-3">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                        {metrics?.totalIncidents !== null && metrics?.totalIncidents !== undefined ? (
                            <div className="tabular text-figure font-semibold text-ink">
                              {formatNumber(metrics.totalIncidents)}
                            </div>
                          ) : (
                            // A year the school did not report: no figures, not 0
                            <div className="text-ui text-ink-3">
                              {selectedYear === 'all' ? 'N/A' : 'Not reported'}
                            </div>
                          )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* YoY Change */}
              <div className="py-4">
                <div className="mb-2 text-meta font-semibold text-ink-2">
                  Year-over-Year Change
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {profiles.map((profile, index) => {
                    const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                    const yoy = metrics?.yoyChange ?? null
                    return (
                      <div key={profile.unitid}>
                        <div className="flex items-center gap-1.5 text-meta font-semibold text-ink">
                          {swatch(index)}
                          <span>
                            {profile.shortName || profile.name}
                            {profile.isMainCampus === false && (
                              <span className="ml-1 font-normal text-ink-3">(Branch)</span>
                            )}
                          </span>
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="tabular mb-1 text-label text-ink-3">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                        {yoy ? (
                          <div className="tabular text-heading font-semibold text-ink">
                            {yoy.absolute > 0 ? '+' : ''}{formatNumber(yoy.absolute)}
                          </div>
                        ) : (
                          <span className="text-ink-3">N/A</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top Offense - only show when not filtering by specific offense */}
              {isSummary(selectedOffense) && (
                <div className="py-4">
                  <div className="mb-2 text-meta font-semibold text-ink-2">
                    Most Common Offense
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    {profiles.map((profile, index) => {
                      const topOffense = profileTopOffenses[index]
                      return (
                        <div key={profile.unitid}>
                          <div className="flex items-center gap-1.5 text-meta font-semibold text-ink">
                            {swatch(index)}
                            <span>{profile.shortName || profile.name}</span>
                          </div>
                          {fteLabels.has(profile.unitid) && (
                            <div className="tabular mb-1 text-label text-ink-3">
                              {fteLabels.get(profile.unitid)}
                            </div>
                          )}
                          <div className="text-ui font-semibold text-ink">
                            {topOffense?.offense || 'N/A'}
                          </div>
                          {topOffense && topOffense.count > 0 && (
                            <div className="tabular text-meta text-ink-2">
                              {formatNumber(topOffense.count)}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Trend Chart */}
          <section className="mb-12">
            <h2 className={sectionTitle}>
              {`${selectionLabel(selectedOffense)} Over Time`}
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={trendChartData} margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={chart.grid} vertical={false} />
                {noteBands.map((b) => (
                  <ReferenceArea key={b.x1} x1={b.x1} x2={b.x2} fill={chart.band} fillOpacity={0.07} ifOverflow="extendDomain" />
                ))}
                {/* Every year labelled (interval 0), angled at phone width so they do not overlap */}
                <XAxis
                  dataKey="year"
                  interval={0}
                  tick={{ fill: chart.text, fontSize: narrow ? 11 : 12 }}
                  angle={narrow ? -45 : 0}
                  textAnchor={narrow ? 'end' : 'middle'}
                  height={narrow ? 44 : 30}
                  axisLine={{ stroke: chart.grid }}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(v: number) => formatNumber(v)}
                  tick={{ fill: chart.text, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                />
                <Tooltip
                  formatter={(value: number) => formatNumber(value)}
                  {...tooltipProps(chart)}
                  cursor={lineCursor(chart)}
                />
                <Legend iconSize={18} wrapperStyle={{ color: chart.text, fontSize: 13, paddingTop: 8 }} />
                {profiles.map((profile, index) => (
                  <Line
                    key={profile.unitid}
                    type="monotone"
                    dataKey={profile.shortName || profile.name}
                    stroke={schoolColors[index]}
                    strokeDasharray={SERIES_DASHES[index]}
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: schoolColors[index], strokeDasharray: '' }}
                    activeDot={{ r: 5 }}
                    legendType="plainline"
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <SeriesNotes years={availableYears} className="mt-3" />
            <ReportYearNote className="mt-1" />
          </section>

          {/* Offense Breakdown */}
          <section className="mb-12">
            <h2 className={sectionTitle}>
              Top Offenses Comparison{selectedYear !== 'all' ? ` (${selectedYear})` : ''}
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={offenseComparisonData} layout="vertical" margin={{ top: 4, right: 20, bottom: 0, left: 0 }}>
                <defs>
                  <pattern id="compare-hatch" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)">
                    <rect width="5" height="5" fill={schoolColors[1]} />
                    <line x1="0" y1="0" x2="0" y2="5" stroke={chart.tooltipBg} strokeWidth="1.5" />
                  </pattern>
                </defs>
                <CartesianGrid stroke={chart.grid} horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v: number) => formatNumber(v)}
                  tick={{ fill: chart.text, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="offense"
                  tick={{ fill: chart.text, fontSize: 11 }}
                  axisLine={{ stroke: chart.grid }}
                  tickLine={false}
                  width={100}
                />
                <Tooltip
                  formatter={(value: number) => formatNumber(value)}
                  {...tooltipProps(chart)}
                  cursor={barCursor(chart)}
                />
                <Legend iconSize={12} wrapperStyle={{ color: chart.text, fontSize: 13, paddingTop: 8 }} />
                {profiles.map((profile, index) => (
                  <Bar
                    key={profile.unitid}
                    dataKey={profile.shortName || profile.name}
                    fill={index === 1 ? 'url(#compare-hatch)' : schoolColors[index]}
                    stroke={schoolColors[index]}
                    strokeWidth={index === 1 ? 1 : 0}
                    radius={[0, 2, 2, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </section>

          {/* View Full Profiles Links */}
          <div className="grid grid-cols-1 border-t border-rule sm:grid-cols-2">
            {profiles.map((profile, index) => (
              <Link
                key={profile.unitid}
                to={`/school/${profile.unitid}`}
                className={cn('group flex items-center gap-3 border-b border-rule py-4 hover:bg-subtle', index === 1 && 'sm:border-l sm:pl-4')}
              >
                {swatch(index)}
                <div>
                  <div className="font-semibold text-ink underline decoration-rule-strong/60 underline-offset-[3px] group-hover:text-accent group-hover:decoration-current">
                    {profile.name}
                  </div>
                  <div className="text-meta text-ink-2">
                    View full profile
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      {/* Empty State - Only one school selected */}
      {!loading && selectedIds.length === 1 && (
        <div className="border-t border-rule py-12">
          <h3 className="h3 mb-1">
            Add Another School
          </h3>
          <p className="text-body text-ink-2">
            Select one more school to start comparing statistics.
          </p>
        </div>
      )}
    </div>
  )
}
