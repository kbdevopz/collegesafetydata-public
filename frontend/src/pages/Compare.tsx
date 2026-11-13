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
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import {
  Plus,
  X,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertCircle,
  Loader2,
  ChevronDown,
  ArrowRight,
  Calendar,
  AlertTriangle,
  Info,
} from 'lucide-react'
import { fetchSchoolProfile, fetchSchoolIndex, fetchPresets, getMetadata } from '../lib/api'
import type { SchoolProfile, School, PresetDetail, SchoolIndex, RateRules } from '../lib/types'
import { cn, formatNumber, calculateYoYChange, isSmallSample } from '../lib/utils'
import { fteFor, latestFte, institutionRate, rateNote, campusesPhrase } from '../lib/rates'
import { ALL, CRIMINAL, SUMMARY_LABELS, inSelection, isSummary, selectionLabel } from '../lib/selection'
import { useTheme } from '../hooks/useTheme'

// School colors for comparison
const SCHOOL_COLORS = ['#3b82f6', '#10b981'] // Blue, Emerald

// One school's count of `selection` ('criminal', 'all' or an offense name)
// in `year`: 0 when it reported the year without any of it, null when it did
// not report that year (no figures at all).
function selectionCount(p: SchoolProfile, year: number, selection: string): number | null {
  if (!p.yearlyTotals.some((yt) => yt.year === year)) return null
  return p.trends
    .filter((t) => t.year === year && inSelection(t, selection))
    .reduce((sum, t) => sum + t.count, 0)
}

export default function Compare() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { resolvedTheme } = useTheme()

  // State
  const [schools, setSchools] = useState<School[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [profiles, setProfiles] = useState<SchoolProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Filter state
  const [selectedYear, setSelectedYear] = useState<string>('all')
  const [selectedOffense, setSelectedOffense] = useState<string>(CRIMINAL)
  const [showRate, setShowRate] = useState(false)
  // Who rate rankings list (metadata.json), for the note on a left-out rate
  const [rateRules, setRateRules] = useState<RateRules | null>(null)

  useEffect(() => {
    getMetadata()
      .then((m) => setRateRules(m.rateRules))
      .catch(() => setRateRules(null))
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

  // Initialize from URL params
  useEffect(() => {
    const schoolsParam = searchParams.get('schools')
    if (schoolsParam) {
      const ids = schoolsParam.split(',').map((id) => parseInt(id)).filter((id) => !isNaN(id))
      setSelectedIds(ids.slice(0, 2)) // Max 2
    }
  }, [searchParams])

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

  // Update URL when selection changes
  useEffect(() => {
    if (selectedIds.length > 0) {
      setSearchParams({ schools: selectedIds.join(',') })
    } else {
      setSearchParams({})
    }
  }, [selectedIds, setSearchParams])

  // Add a school
  const addSchool = (unitid: number) => {
    if (selectedIds.length < 2 && !selectedIds.includes(unitid)) {
      setSelectedIds([...selectedIds, unitid])
    }
    setIsDropdownOpen(false)
  }

  // Remove a school
  const removeSchool = (unitid: number) => {
    setSelectedIds(selectedIds.filter((id) => id !== unitid))
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

      // Rate per 10k FTE - only for a single year, with that year's FTE
      // (no rate when that year has no FTE). It is the institution's rate:
      // the incidents of all its campuses per its FTE, as NCES publishes FTE
      // per institution.
      const year = selectedYear !== 'all' ? parseInt(selectedYear) : null
      const fte = year !== null ? fteFor(profile, year) : null
      const inst = year !== null && totalIncidents !== null
        ? institutionRate(profile, year, selectedOffense, totalIncidents)
        : null

      return {
        unitid: profile.unitid,
        totalIncidents,
        yoyChange,
        hasData: totalIncidents !== null,
        fte,
        rate: inst?.rate ?? null,
        rateCount: inst?.count ?? totalIncidents ?? 0,
        campuses: campusesPhrase(inst?.campuses ?? 1),
        note: rateNote(inst, rateRules),
      }
    })
  }, [profiles, selectedYear, selectedOffense, rateRules])

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
      const where = campuses > 1 ? ` at all ${campuses} campuses` : ''
      labels.set(profile.unitid, `${formatNumber(label.fte)} students${where} (${label.year})`)
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

  // Theme-aware chart styling
  const chartGridColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'
  const chartTextColor = resolvedTheme === 'dark' ? '#9ca3af' : '#6b7280'
  const chartBgColor = resolvedTheme === 'dark' ? '#111827' : 'white'
  const chartBorderColor = resolvedTheme === 'dark' ? '#374151' : '#e5e7eb'

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
          Compare Schools
        </h1>
      </div>

      {/* School Selection */}
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 sm:p-6 mb-8">
        <div className="flex flex-wrap items-center gap-3">
          {/* Selected Schools */}
          {selectedIds.map((id, index) => {
            const school = schools.find((s) => s.unitid === id)
            const profile = profiles.find((p) => p.unitid === id)
            const displayName = school?.short || profile?.shortName || school?.name || 'Unknown'
            if (!school && !profile) return null
            return (
              <div
                key={id}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border-2"
                style={{ borderColor: SCHOOL_COLORS[index] }}
              >
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: SCHOOL_COLORS[index] }}
                />
                <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                  {displayName.length > 25 ? displayName.slice(0, 25) + '...' : displayName}
                </span>
                {school?.state && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {school.state}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => removeSchool(id)}
                  className="ml-1 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  aria-label={`Remove ${school?.name || 'school'}`}
                >
                  <X className="w-4 h-4" />
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
                className="flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:border-primary-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              >
                <Plus className="w-4 h-4" />
                <span>Add School</span>
                <ChevronDown className={cn('w-4 h-4 transition-transform', isDropdownOpen && 'rotate-180')} />
              </button>

              {isDropdownOpen && (
                <div className="absolute top-full left-0 mt-2 w-80 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50">
                  {/* Search Input */}
                  <div className="p-2 border-b border-gray-200 dark:border-gray-700">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search schools..."
                      className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      autoFocus
                    />
                  </div>

                  {/* School List */}
                  <div className="max-h-64 overflow-y-auto py-2">
                    {filteredSchools.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 text-center">
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
                          className="w-full text-left px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                        >
                          <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                            {school.name}
                            {school.isMainCampus === false && (
                              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                            )}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {school.city && school.state ? `${school.city}, ${school.state}` : school.state || ''}
                          </div>
                        </button>
                      ))
                    )}
                    {filteredSchools.length === 20 && searchQuery && (
                      <div className="px-4 py-2 text-xs text-gray-400 dark:text-gray-500 text-center border-t border-gray-100 dark:border-gray-800">
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
          <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
            Select two schools above to begin comparing their statistics.
          </p>
        )}
      </div>

      {/* Sticky Filter Bar - only show when 2 schools selected */}
      {profiles.length === 2 && (
        <div className="sticky top-16 z-40 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm mb-8">
          <div className="flex flex-wrap items-center gap-4 p-4">
            {/* Year Dropdown */}
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <label htmlFor="compare-year-select" className="text-sm text-gray-500 dark:text-gray-400 hidden sm:inline">
                Year:
              </label>
              <select
                id="compare-year-select"
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="w-36 text-sm font-medium bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1.5 cursor-pointer focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
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
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <label htmlFor="compare-offense-select" className="text-sm text-gray-500 dark:text-gray-400 hidden sm:inline">
                Crime:
              </label>
              <select
                id="compare-offense-select"
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

            {/* Divider */}
            <div className="hidden sm:block w-px h-5 bg-gray-200 dark:bg-gray-700" />

            {/* Rate Toggle */}
            <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
              <button
                type="button"
                onClick={() => setShowRate(false)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
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
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                  showRate
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
                )}
              >
                Rate
              </button>
            </div>

            {/* Clear filters */}
            {(selectedYear !== 'all' || selectedOffense !== CRIMINAL) && (
              <button
                type="button"
                onClick={() => {
                  setSelectedYear('all')
                  setSelectedOffense(CRIMINAL)
                }}
                className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      )}

      {/* Comparison Context Banner */}
      {profiles.length === 2 && (
        <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-3 mb-4 flex items-start gap-2">
          <Info className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {showRate ? (
              <>Per 10,000 students. <span className="text-amber-600 dark:text-amber-400">*</span> = small sample.</>
            ) : (
              <>Comparing counts of {selectionLabel(selectedOffense).toLowerCase()}. Toggle "Rate" for per-student comparison.</>
            )}
          </p>
        </div>
      )}

      {/* No Data Message */}
      {profiles.length === 2 && !anyProfileHasData && (selectedYear !== 'all' || !isSummary(selectedOffense)) && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-6 mb-8">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-medium text-amber-800 dark:text-amber-300">
                None at either school
              </h3>
              <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                Neither school has any {selectedOffense === 'criminal' ? 'criminal offenses' : selectedOffense === 'all' ? 'crimes, arrests or referrals' : `${selectedOffense} incidents`}
                {selectedYear !== 'all' ? ` in ${selectedYear}` : ''}: each had 0, or did not report that year.
                Try selecting a different year or offense.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-6 flex items-start gap-4 mb-8">
          <AlertCircle className="w-6 h-6 text-red-500 dark:text-red-400 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-red-800 dark:text-red-300">Error Loading Data</h3>
            <p className="text-red-700 dark:text-red-400 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-16 min-h-[400px]">
          <Loader2 className="w-8 h-8 text-primary-600 dark:text-primary-400 animate-spin" />
          <span className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading schools...</span>
        </div>
      )}

      {/* Comparison Content */}
      {!loading && profiles.length === 2 && (
        <>
          {/* Key Metrics */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden mb-8">
            <div className="px-4 sm:px-6 py-4 border-b dark:border-gray-800">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Key Metrics
                {selectedYear === 'all' ? ' (All Years)' : ` (${selectedYear})`}
                {` - ${selectionLabel(selectedOffense)}`}
              </h2>
            </div>

            {/* Desktop: Table Layout */}
            <div className="hidden sm:block">
              <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Metric
                    </th>
                    {profiles.map((profile, index) => (
                      <th
                        key={profile.unitid}
                        className="px-6 py-3 text-center"
                      >
                        <div
                          className="text-xs font-medium uppercase"
                          style={{ color: SCHOOL_COLORS[index] }}
                        >
                          {profile.shortName || profile.name}
                          {profile.isMainCampus === false && (
                            <span className="ml-1 text-gray-400 dark:text-gray-500 font-normal normal-case">(Branch)</span>
                          )}
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="text-xs font-normal text-gray-400 dark:text-gray-500 mt-0.5 normal-case">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {/* Total Incidents / Rate */}
                  <tr>
                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                      {showRate ? `${selectionLabel(selectedOffense)}: rate (per 10k)` : selectionLabel(selectedOffense)}
                    </td>
                    {profiles.map((profile) => {
                      const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                      return (
                        <td key={profile.unitid} className="px-6 py-4 text-center">
                          {showRate ? (
                            metrics?.rate !== null && metrics?.rate !== undefined ? (
                              <div>
                                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                  {metrics.rate.toFixed(1)}{isSmallSample(metrics.fte, metrics.rateCount) ? '*' : ''}
                                </span>
                                <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-1">
                                  per 10k
                                </span>
                                {metrics.campuses && (
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Institution rate, {metrics.campuses}
                                  </div>
                                )}
                                {metrics.note && (
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-xs mx-auto">
                                    {metrics.note}
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="text-xl text-gray-400 dark:text-gray-500">N/A</span>
                            )
                          ) : (
                            metrics?.totalIncidents !== null && metrics?.totalIncidents !== undefined ? (
                              <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                {formatNumber(metrics.totalIncidents)}
                              </span>
                            ) : (
                              // A year the school did not report: no figures, not 0
                              <span className="text-xl text-gray-400 dark:text-gray-500">
                                {selectedYear === 'all' ? 'N/A' : 'Not reported'}
                              </span>
                            )
                          )}
                        </td>
                      )
                    })}
                  </tr>

                  {/* YoY Change */}
                  <tr>
                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                      Year-over-Year Change
                    </td>
                    {profiles.map((profile) => {
                      const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                      const yoy = metrics?.yoyChange
                      return (
                        <td key={profile.unitid} className="px-6 py-4 text-center">
                          {yoy ? (
                            <div className={cn(
                              'flex items-center justify-center gap-1 text-lg font-semibold',
                              yoy.absolute > 0 ? 'text-purple-600 dark:text-purple-400' :
                              yoy.absolute < 0 ? 'text-blue-600 dark:text-blue-400' :
                              'text-gray-500 dark:text-gray-400'
                            )}>
                              {yoy.absolute > 0 ? <TrendingUp className="w-5 h-5" /> :
                               yoy.absolute < 0 ? <TrendingDown className="w-5 h-5" /> :
                               <Minus className="w-5 h-5" />}
                              {yoy.absolute > 0 ? '+' : ''}{yoy.absolute}
                            </div>
                          ) : (
                            <span className="text-gray-400">N/A</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>

                  {/* Top Offense - only show when not filtering by specific offense */}
                  {isSummary(selectedOffense) && (
                    <tr>
                      <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                        Most Common Offense
                      </td>
                      {profiles.map((profile, index) => {
                        const topOffense = profileTopOffenses[index]
                        return (
                          <td key={profile.unitid} className="px-6 py-4 text-center">
                            <div className="font-medium text-gray-900 dark:text-gray-100">
                              {topOffense?.offense || 'N/A'}
                            </div>
                            {topOffense && topOffense.count > 0 && (
                              <div className="text-sm text-gray-500 dark:text-gray-400">
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
            <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
              {/* Total Incidents / Rate */}
              <div className="p-4">
                <div className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                  {showRate ? `${selectionLabel(selectedOffense)}: rate (per 10k)` : selectionLabel(selectedOffense)}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {profiles.map((profile, index) => {
                    const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                    return (
                      <div key={profile.unitid} className="text-center">
                        <div
                          className="text-xs font-medium"
                          style={{ color: SCHOOL_COLORS[index] }}
                        >
                          {profile.shortName || profile.name}
                          {profile.isMainCampus === false && (
                            <span className="ml-1 text-gray-400 dark:text-gray-500 font-normal">(Branch)</span>
                          )}
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                        {showRate ? (
                          metrics?.rate !== null && metrics?.rate !== undefined ? (
                            <div>
                              <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                {metrics.rate.toFixed(1)}{isSmallSample(metrics.fte, metrics.rateCount) ? '*' : ''}
                                <span className="text-xs font-normal text-gray-500 dark:text-gray-400 ml-1">
                                  per 10k
                                </span>
                              </div>
                              {metrics.campuses && (
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                  Institution rate, {metrics.campuses}
                                </div>
                              )}
                              {metrics.note && (
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                  {metrics.note}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-xl text-gray-400 dark:text-gray-500">N/A</div>
                          )
                        ) : (
                          metrics?.totalIncidents !== null && metrics?.totalIncidents !== undefined ? (
                            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                              {formatNumber(metrics.totalIncidents)}
                            </div>
                          ) : (
                            // A year the school did not report: no figures, not 0
                            <div className="text-xl text-gray-400 dark:text-gray-500">
                              {selectedYear === 'all' ? 'N/A' : 'Not reported'}
                            </div>
                          )
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* YoY Change */}
              <div className="p-4">
                <div className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                  Year-over-Year Change
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {profiles.map((profile, index) => {
                    const metrics = filteredMetrics.find(m => m.unitid === profile.unitid)
                    const yoy = metrics?.yoyChange ?? null
                    return (
                      <div key={profile.unitid} className="text-center">
                        <div
                          className="text-xs font-medium"
                          style={{ color: SCHOOL_COLORS[index] }}
                        >
                          {profile.shortName || profile.name}
                          {profile.isMainCampus === false && (
                            <span className="ml-1 text-gray-400 dark:text-gray-500 font-normal">(Branch)</span>
                          )}
                        </div>
                        {fteLabels.has(profile.unitid) && (
                          <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
                            {fteLabels.get(profile.unitid)}
                          </div>
                        )}
                        {yoy ? (
                          <div className={cn(
                            'flex items-center justify-center gap-1 text-lg font-semibold',
                            yoy.absolute > 0 ? 'text-purple-600 dark:text-purple-400' :
                            yoy.absolute < 0 ? 'text-blue-600 dark:text-blue-400' :
                            'text-gray-500 dark:text-gray-400'
                          )}>
                            {yoy.absolute > 0 ? <TrendingUp className="w-4 h-4" /> :
                             yoy.absolute < 0 ? <TrendingDown className="w-4 h-4" /> :
                             <Minus className="w-4 h-4" />}
                            {yoy.absolute > 0 ? '+' : ''}{yoy.absolute}
                          </div>
                        ) : (
                          <span className="text-gray-400">N/A</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top Offense - only show when not filtering by specific offense */}
              {isSummary(selectedOffense) && (
                <div className="p-4">
                  <div className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                    Most Common Offense
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    {profiles.map((profile, index) => {
                      const topOffense = profileTopOffenses[index]
                      return (
                        <div key={profile.unitid} className="text-center">
                          <div
                            className="text-xs font-medium"
                            style={{ color: SCHOOL_COLORS[index] }}
                          >
                            {profile.shortName || profile.name}
                          </div>
                          {fteLabels.has(profile.unitid) && (
                            <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
                              {fteLabels.get(profile.unitid)}
                            </div>
                          )}
                          <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                            {topOffense?.offense || 'N/A'}
                          </div>
                          {topOffense && topOffense.count > 0 && (
                            <div className="text-xs text-gray-500 dark:text-gray-400">
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
          </div>

          {/* Trend Chart */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 sm:p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {`${selectionLabel(selectedOffense)} Over Time`}
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
                {profiles.map((profile, index) => (
                  <Line
                    key={profile.unitid}
                    type="monotone"
                    dataKey={profile.shortName || profile.name}
                    stroke={SCHOOL_COLORS[index]}
                    strokeWidth={3}
                    dot={{ r: 4, fill: SCHOOL_COLORS[index] }}
                    activeDot={{ r: 6 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Offense Breakdown */}
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 sm:p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Top Offenses Comparison{selectedYear !== 'all' ? ` (${selectedYear})` : ''}
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={offenseComparisonData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke={chartGridColor} />
                <XAxis
                  type="number"
                  tick={{ fill: chartTextColor, fontSize: 12 }}
                  axisLine={{ stroke: chartGridColor }}
                />
                <YAxis
                  type="category"
                  dataKey="offense"
                  tick={{ fill: chartTextColor, fontSize: 11 }}
                  axisLine={{ stroke: chartGridColor }}
                  width={100}
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
                {profiles.map((profile, index) => (
                  <Bar
                    key={profile.unitid}
                    dataKey={profile.shortName || profile.name}
                    fill={SCHOOL_COLORS[index]}
                    radius={[0, 4, 4, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* View Full Profiles Links */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {profiles.map((profile, index) => (
              <Link
                key={profile.unitid}
                to={`/school/${profile.unitid}`}
                className="flex items-center justify-between p-4 rounded-lg border-2 hover:shadow-md transition-shadow"
                style={{ borderColor: SCHOOL_COLORS[index] }}
              >
                <div>
                  <div className="font-medium text-gray-900 dark:text-gray-100">
                    {profile.name}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    View full profile
                  </div>
                </div>
                <ArrowRight className="w-5 h-5 text-gray-400" />
              </Link>
            ))}
          </div>
        </>
      )}

      {/* Empty State - Only one school selected */}
      {!loading && selectedIds.length === 1 && (
        <div className="text-center py-16">
          <div className="text-gray-400 dark:text-gray-500 mb-4">
            <Plus className="w-16 h-16 mx-auto" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
            Add Another School
          </h3>
          <p className="text-gray-600 dark:text-gray-400">
            Select one more school to start comparing statistics.
          </p>
        </div>
      )}
    </div>
  )
}
