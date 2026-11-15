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
import { ChevronUp, ChevronDown, ExternalLink, AlertCircle, Loader2, MapPin, Calendar, AlertTriangle, Plus, Check, GitCompare, X, ChevronRight, Info } from 'lucide-react'
import { fetchRankings, getMetadata } from '../lib/api'
import type { RankingsData, Metadata, Offense, RateInstitution, RateNotRankedEntry, RateRules } from '../lib/types'
import { cn, formatNumber, formatPercent, groupOffensesByFamily, withParams } from '../lib/utils'
import { VIOLENT, compareText, countHeader, countPhrase, noneOfPhrase } from '../lib/selection'
import {
  countNotes, intervalText, rateInterval, rateViewGroups, ratioPercent, reasonText, SPIKE_NOTE, joinAnd,
} from '../lib/rates'
import SchoolSearch from '../components/SchoolSearch'
import OffensePopover from '../components/OffensePopover'
import SeriesNotes from '../components/SeriesNotes'

// One row of the table: a campus (count view) or an institution, all its
// campuses together (rate view, as NCES publishes FTE per institution)
interface Row {
  key: number // campus UNITID, or base UNITID of an institution
  // count view: 'count'; rate view: 'ranked' (in the file's rate ranking),
  // 'few' (1 to minCount - 1 and no other reason: shown, not ranked by rate)
  // or 'zero'. Institutions shown but not ranked for another reason are in
  // their own section (NotRankedSection), not in the table.
  tier: 'count' | 'ranked' | 'few' | 'zero'
  rank: number // the rank in the file (ties share a rank: 1, 2, 2, 4); after the ranked ones for few and zero
  unitid: number // the school page the row links to
  name: string
  branch: boolean // count view: not the main campus
  campus: string | null // count view: the campus's own DOE name (shown as the title; name stays the sort key)
  campuses: number // the institution's campuses in the United States that year
  count: number
  pct: number // count view: share of the file's total
  fte: number | null
  rate: number | null
  // rate view: the rate's 95% interval, its rank range ('ranked'), and
  // whether the count is unusually high for the institution
  lo: number | null
  hi: number | null
  rankLo: number | null
  rankHi: number | null
  spike: boolean
  // rate view: notes on incidents the rate counts or leaves out, and on its
  // denominator (medical-center campuses, shared figures, pooled FTE)
  notes: string[]
  // count view: the count per 10,000 of its institution's FTE when the
  // pipeline flags it as very high for the institution's size (highForSize)
  highForSize: number | null
}

// The rank-range tooltip (rules.rankRanges: simulated, never recomputed here)
function rankRangeTitle(rules: RateRules | undefined): string {
  const pct = Math.round((rules?.ciLevel ?? 0.95) * 100)
  const draws = (rules?.rankRanges?.draws ?? 2000).toLocaleString('en-US')
  return `The middle ${pct}% of the ranks this institution held in ${draws} simulated rankings, each drawing every ` +
    "ranked institution's rate from a gamma distribution with the overdispersion of its interval; widened to " +
    'include its published rank. Ranks inside one range are not clearly different.'
}

// "Rate adds the on-campus FTE of A and B" for an institution with pooled FTE
function pooledShort(inst: RateInstitution | undefined): string | null {
  if (!inst?.pooled || inst.pooled.length === 0) return null
  return `Rate adds the on-campus FTE of ${joinAnd(inst.pooled.map((p) => p.name ?? `institution ${p.id}`))}, ` +
    'whose campus figures count here.'
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
  // Rate view: the "Not ranked by rate" section below the table
  const [isNotRankedOpen, setIsNotRankedOpen] = useState(false)
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
  const selectedOffense = searchParams.get('offense') || VIOLENT

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

  // The rate view is always offered; a year without NCES enrollment has no rate rankings
  const canShowRate = true

  // Who rate rankings list and rank (etl/config.py, written to metadata.json)
  const rules = metadata?.rateRules
  const rateRulesText = rules
    ? `${formatNumber(rules.minFte)}+ on-campus FTE, at least ${rules.minCount} incidents to rank, ${Math.round(rules.ciLevel * 100)}% intervals`
    : ''
  // An offense too rare nationally for a rate ranking: counts only
  const countsOnly = !!rules?.countsOnly?.includes(selectedOffense)
  const rateView = sortByRate && !countsOnly
  const level = rules?.ciLevel ?? 0.95
  const rankTitle = rankRangeTitle(rules)

  // The institutions of the rate view, by group (lib/rates.ts): ranked, too
  // few incidents, not ranked for another reason, none of the selection
  const rateGroups = useMemo(
    () => (data && rateView ? rateViewGroups(data, selectedOffense, compareText) : null),
    [data, rateView, selectedOffense]
  )

  // The rows of the selected view, in the file's order and with its ranks:
  // campuses by count, or institutions by rate
  // Campuses (or institutions) that reported the year but had none of the
  // selection are ranked after the entries with 0, tied: rank = entries + 1,
  // listed by name, then UNITID (the pipeline's tie rule)
  const sortedRankings = useMemo((): Row[] => {
    if (!data) return []
    if (rateView && rateGroups) {
      // Ranked by rate, then too few to rank (by rate, as the file lists
      // them), then none. Those not ranked for another reason, and those a
      // rule leaves out, are in the "Not ranked by rate" section.
      const after = rateGroups.ranked.length + 1
      const rows: Row[] = [
        ...rateGroups.ranked.map((e) => ({ e, tier: 'ranked' as const, rank: e.rank, rankLo: e.rankLo, rankHi: e.rankHi, spike: !!e.spike })),
        ...rateGroups.few.map((e) => ({ e, tier: 'few' as const, rank: after, rankLo: null, rankHi: null, spike: false })),
      ].map(({ e, tier, rank, rankLo, rankHi, spike }) => {
        const inst = data.institutions[String(e.id)]
        const pooled = pooledShort(inst)
        return {
          key: e.id,
          tier,
          rank,
          unitid: inst?.unitid ?? e.id * 1000 + 1,
          name: inst?.name ?? `Institution ${e.id}`,
          branch: false,
          campus: null,
          campuses: inst?.campuses ?? 1,
          count: e.count,
          pct: 0,
          fte: inst?.fte ?? null,
          rate: e.rate,
          lo: e.lo,
          hi: e.hi,
          rankLo,
          rankHi,
          spike,
          notes: [...countNotes(e, [], rules, true), ...(pooled ? [pooled] : [])],
          highForSize: null,
        }
      })
      rateGroups.zero.forEach(({ id, inst }) => {
        const interval = rateInterval(0, inst.fte, selectedOffense, rules)
        const pooled = pooledShort(inst)
        rows.push({
          key: id,
          tier: 'zero',
          rank: after,
          unitid: inst.unitid,
          name: inst.name,
          branch: false,
          campus: null,
          campuses: inst.campuses,
          count: 0,
          pct: 0,
          fte: inst.fte,
          rate: 0,
          lo: interval?.lo ?? null,
          hi: interval?.hi ?? null,
          rankLo: null,
          rankHi: null,
          spike: false,
          notes: pooled ? [pooled] : [],
          highForSize: null,
        })
      })
      return rows
    }
    const total = data.totals[selectedOffense] || 0
    const entries = data.rankings[selectedOffense] || []
    const rows: Row[] = entries.map((e) => {
      const campus = data.campuses[String(e.unitid)]
      const fte = campus?.fte ?? null
      return {
        key: e.unitid,
        tier: 'count' as const,
        rank: e.rank,
        unitid: e.unitid,
        name: campus?.name ?? `School ${e.unitid}`,
        branch: campus ? !campus.main : false,
        campus: campus?.campus ?? null,
        campuses: campus?.campuses ?? 1,
        count: e.count,
        pct: total > 0 ? (e.count / total) * 100 : 0,
        fte,
        rate: null,
        lo: null,
        hi: null,
        rankLo: null,
        rankHi: null,
        spike: false,
        notes: [],
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
      tier: 'count',
      rank: entries.length + 1,
      unitid: id,
      name: campus.name,
      branch: !campus.main,
      campus: campus.campus ?? null,
      campuses: campus.campuses,
      count: 0,
      pct: 0,
      fte: campus.fte,
      rate: null,
      lo: null,
      hi: null,
      rankLo: null,
      rankHi: null,
      spike: false,
      notes: [],
      highForSize: null,
    }))
    return rows
  }, [data, selectedOffense, rateView, rateGroups, rules])

  // The note of a count flagged as very high for the institution's size
  // (highForSize), with the national limit it is over (metadata.rateStats)
  const flagLimit = metadata?.rateStats?.countFlagLimits?.[String(selectedYear)]?.[selectedOffense]
  const highForSizeNote = useCallback((perTenK: number) => {
    const factor = rules?.countFlag?.factor ?? 3
    const limit = flagLimit !== undefined ? ` (${flagLimit.toFixed(1)})` : ''
    return `Very high for an institution of this size: ${formatNumber(Math.round(perTenK))} per 10,000 of its ` +
      `institution's FTE, more than ${factor} times the highest ranked rate in the ${selectedYear} national rate ` +
      `ranking${limit}. Shown as reported; check the institution's Annual Security Report.`
  }, [rules, flagLimit, selectedYear])

  const displayedRankings = useMemo(() => {
    return sortedRankings.slice(0, displayCount)
  }, [sortedRankings, displayCount])

  // Whether the selected year has rates (NCES enrollment)
  const hasRateData = useMemo(() => {
    return Object.keys(data?.institutions ?? {}).length > 0
  }, [data])

  // What the rows are
  const rowUnit = rateView ? 'institutions' : 'campuses'

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
        header: rateView ? () => <span title={rankTitle}>Rank (range)</span> : 'Rank',
        cell: (info) => {
          // The published rank, by count or by rate, and in the rate view the
          // ranks the intervals allow; no rank below minCount incidents
          const row = info.row.original
          if (row.tier === 'few' || row.tier === 'zero') {
            return <span className="text-gray-400 dark:text-gray-500" title="Not ranked by rate">—</span>
          }
          return (
            <span className="flex flex-col">
              <span className="font-medium text-gray-500 dark:text-gray-400">#{info.getValue()}</span>
              {row.tier === 'ranked' && row.rankLo !== null && row.rankHi !== null && (
                <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums whitespace-nowrap" title={rankTitle}>
                  {row.rankLo === row.rankHi ? row.rankLo : `${row.rankLo}–${row.rankHi}`}
                </span>
              )}
            </span>
          )
        },
        size: 80,
      }),
      columnHelper.accessor('name', {
        header: rateView ? 'Institution' : 'School',
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
            {rateView && info.row.original.campuses > 1 && (
              <span
                className="text-xs font-normal text-gray-500 dark:text-gray-400"
                title="The rate counts the incidents of all the institution's campuses in the United States"
              >
                ({info.row.original.campuses} campuses)
              </span>
            )}
            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
          </Link>
          {info.row.original.spike && (
            <span className="block text-xs text-amber-700 dark:text-amber-400 mt-0.5">{SPIKE_NOTE}</span>
          )}
          {info.row.original.notes.map((note) => (
            <span key={note} className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">{note}</span>
          ))}
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
      ...(rateView ? [
        columnHelper.accessor('rate', {
          header: () => (
            <span title={`Per 10,000 on-campus FTE students, with the rate's ${Math.round(level * 100)}% interval below it (negative binomial: it allows for year-to-year variation beyond chance, not for differences in reporting)`}>
              Rate ({Math.round(level * 100)}% interval)
            </span>
          ),
          cell: (info) => {
            const rate = info.getValue()
            const { lo, hi } = info.row.original
            return (
              <span className="flex flex-col">
                <span className="font-semibold tabular-nums text-primary-600 dark:text-primary-400">
                  {rate !== null ? rate.toFixed(1) : '—'}
                </span>
                {lo !== null && hi !== null && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums whitespace-nowrap">
                    {intervalText(lo, hi)}
                  </span>
                )}
              </span>
            )
          },
          size: 110,
        }),
        columnHelper.accessor('fte', {
          header: () => (
            <span title="The rate's denominator: the whole institution's on-campus FTE, the larger of two estimates from NCES's full-time equivalent enrollment and its share of students enrolled exclusively online, plus that of any institution whose campus figures count under it">
              On-campus FTE
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
      ] : [
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
    [columnHelper, isInCompare, rateView, countLabel, level, rankTitle, highForSizeNote]
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

  // Rate view: the notes shown where the institutions with too few incidents
  // to rank by rate, and those with none of the selection, begin
  const tierNotes = useMemo((): Partial<Record<Row['tier'], string>> => {
    if (!rateView || !rules) return {}
    const few = sortedRankings.filter((r) => r.tier === 'few').length
    const zero = sortedRankings.filter((r) => r.tier === 'zero').length
    const what = noneOfPhrase(selectedOffense, currentOffense)
    const notes: Partial<Record<Row['tier'], string>> = {}
    const fewElsewhere = (rateGroups?.notRanked ?? []).some((e) => e.why.includes('few'))
    if (few > 0) {
      notes.few = `${formatNumber(few)} ${few === 1 ? 'institution' : 'institutions'} had 1 to ${rules.minCount - 1} ` +
        `${what} in ${selectedYear}: too few incidents to rank by rate. Their rates are shown with their ` +
        `${Math.round(rules.ciLevel * 100)}% intervals, which are wide, and are listed by rate without a rank.` +
        (fewElsewhere ? ' Those also not ranked for another reason are under "Not ranked by rate", below the table.' : '')
    }
    if (zero > 0) {
      notes.zero = `${formatNumber(zero)} ${zero === 1 ? 'institution' : 'institutions'} reported no ${what} for ` +
        `${selectedYear}. A reported zero can reflect how an institution classifies or reports incidents, not only ` +
        'how safe it is.'
    }
    return notes
  }, [rateView, rules, sortedRankings, rateGroups, selectedOffense, currentOffense, selectedYear])

  // Rate view: the institutions shown but not ranked, or left out by a rule
  // (rateNotRanked), each with its reasons in plain words
  const notRankedRows = useMemo(() => {
    if (!data || !rateGroups) return []
    return rateGroups.notRanked.map((e: RateNotRankedEntry) => {
      const inst = data.institutions[String(e.id)]
      const ctx = {
        count: e.count, medical: e.medical, sharedIn: e.sharedIn, sharedOut: e.sharedOut,
        fteUncertain: inst?.fteUncertain, pooled: inst?.pooled,
      }
      const reasons = e.why.filter((r) => r !== 'few').map((r) => reasonText(r, ctx, rules, true))
      if (e.why.includes('few')) reasons.push(reasonText('few', ctx, rules, true))
      const notRankedReasons = e.why.filter(
        (r): r is 'online' | 'medical_campus' | 'shared' | 'few' => ['online', 'medical_campus', 'shared', 'few'].includes(r)
      )
      const pooled = e.rate !== undefined ? pooledShort(inst) : null
      const notes = [...countNotes(ctx, notRankedReasons, rules, true), ...(pooled ? [pooled] : [])]
      return { e, inst, reasons, notes }
    })
  }, [data, rateGroups, rules])
  // How many of them have each reason
  const notRankedTally = useMemo(() => {
    const tally = new Map<string, number>()
    for (const { e } of notRankedRows) for (const r of e.why) tally.set(r, (tally.get(r) ?? 0) + 1)
    return tally
  }, [notRankedRows])
  const notRankedWithRate = notRankedRows.filter(({ e }) => e.rate !== undefined).length
  const excludedNone = rateGroups?.excludedZero.length ?? 0
  const openNotRanked = () => {
    setIsNotRankedOpen(true)
    window.requestAnimationFrame(() => {
      const section = document.getElementById('not-ranked')
      section?.scrollIntoView({ block: 'start' })
      section?.focus({ preventScroll: true })
    })
  }
  // Desktop: each note goes before the first row of its kind in the table's
  // order when those rows are together (the default order, or sorted by
  // rank, count or rate); when a column sort mixes them in, above the first row
  const tableRows = table.getRowModel().rows
  const notesBefore = new Map<number, string[]>()
  for (const tier of ['few', 'zero'] as const) {
    const note = tierNotes[tier]
    if (!note) continue
    const idx = tableRows.flatMap((row, i) => (row.original.tier === tier ? [i] : []))
    const together = idx.length > 0 && idx[idx.length - 1] - idx[0] === idx.length - 1
    const at = together ? idx[0] : 0
    notesBefore.set(at, [...(notesBefore.get(at) ?? []), note])
  }
  const countsOnlyNote = countsOnly
    ? `${currentOffense?.display ?? selectedOffense} is too rare nationally for rates to be compared, so it has ` +
      'rankings by count only.'
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
              {totalSchoolCount.toLocaleString()}
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
            {/* Desktop: Single row with dividers (wraps on narrow screens
                rather than running off the page) */}
            <div className="hidden sm:flex flex-wrap items-center gap-x-4 gap-y-2">
              {/* Data Filters Group */}
              <div className="flex items-center gap-3">
                {/* Preset */}
                <div className="flex items-center gap-1.5">
                  <MapPin className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <label htmlFor="preset-select" className="sr-only">Schools</label>
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

                {/* Divider */}
                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700" />

                {/* Offense */}
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                  <label htmlFor="offense-select" className="sr-only">Offense</label>
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
                  <div role="group" aria-label="View" className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5">
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
                      onClick={() => canShowRate && setSortByRate(true)}
                      disabled={!canShowRate || countsOnly}
                      aria-pressed={rateView}
                      title={countsOnly ? 'Counts only: too rare nationally for a rate ranking' : undefined}
                      className={cn(
                        'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                        rateView
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
                        (!canShowRate || countsOnly) && 'opacity-50 cursor-not-allowed'
                      )}
                    >
                      Rate
                    </button>
                  </div>
                  {rateView && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      per 10k on-campus FTE, whole institutions · {rateRulesText}
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
                aria-expanded={isSummaryExpanded}
                aria-controls="rankings-summary"
                className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
              >
                <span>{formatNumber(currentTotal)} total</span>
                <ChevronRight aria-hidden="true" className={cn(
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
                  <label htmlFor="preset-select-mobile" className="sr-only">Schools</label>
                  <select
                    id="preset-select-mobile"
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
                  <label htmlFor="year-select-mobile" className="sr-only">Year</label>
                  <select
                    id="year-select-mobile"
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
                  <label htmlFor="offense-select-mobile" className="sr-only">Offense</label>
                  <select
                    id="offense-select-mobile"
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
                  <div role="group" aria-label="View" className="flex items-center gap-1 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => setSortByRate(false)}
                      aria-pressed={!rateView}
                      className={cn(
                        'px-2 py-1 text-xs font-medium rounded-md transition-colors',
                        !rateView
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400'
                      )}
                    >
                      Total
                    </button>
                    <button
                      type="button"
                      onClick={() => canShowRate && setSortByRate(true)}
                      disabled={!canShowRate || countsOnly}
                      aria-pressed={rateView}
                      title={countsOnly ? 'Counts only: too rare nationally for a rate ranking' : undefined}
                      className={cn(
                        'px-2 py-1 text-xs font-medium rounded-md transition-colors',
                        rateView
                          ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-gray-600'
                          : 'text-gray-500 dark:text-gray-400',
                        (!canShowRate || countsOnly) && 'opacity-50 cursor-not-allowed'
                      )}
                    >
                      Rate
                    </button>
                  </div>
                )}
              </div>
              {/* Mobile rate legend */}
              {rateView && hasRateData && (
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  per 10k on-campus FTE, whole institutions · {rateRulesText}
                </div>
              )}
            </div>
          </div>

          {/* Expandable Summary - Desktop only */}
          {isSummaryExpanded && (
            <div id="rankings-summary" className="hidden sm:block border-t border-gray-100 dark:border-gray-800 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 rounded-b-xl">
              <div className="flex items-center gap-6 text-sm">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Showing: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{sortedRankings.length.toLocaleString()} {rowUnit}</span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{countLabel === 'Total' ? 'Total' : `Total ${countLabel.toLowerCase()}`}: </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{formatNumber(currentTotal)}</span>
                </div>
                {rateView && (
                  <div className="text-xs text-amber-600 dark:text-amber-400">
                    Institutions with {rateRulesText}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Size-bias warning banner (shown when viewing by Total) */}
        {!rateView && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-300">
              {countsOnlyNote ? <>{countsOnlyNote} </> : null}
              Larger schools report more incidents due to size{hasRateData && !countsOnly && <> — use "Rate" for size-adjusted comparison</>}. Lower numbers may reflect reporting differences, not safety.
              {' '}<Link to={countsOnly ? '/methodology#rates' : '/about'} className="underline hover:text-amber-800 dark:hover:text-amber-200">Learn more</Link>
            </p>
          </div>
        )}

        {/* Rate view context banner */}
        {rateView && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 mb-4 flex items-center gap-2">
            <Info className="w-4 h-4 text-blue-500 flex-shrink-0" />
            <p className="text-sm text-blue-700 dark:text-blue-300">
              Rates are per institution: the incidents of all its campuses in the United States per 10,000
              on-campus FTE students, because NCES counts enrollment per institution, not per campus. On-campus FTE
              is estimated from NCES's FTE and the institution's share of students enrolled exclusively online.
              {rules && (
                <>
                  {' '}Institutions under {formatNumber(rules.minFte)} on-campus FTE are not listed. Institutions
                  with a hospital (IPEDS), special-focus medical schools and research institutions (Carnegie) and
                  the few on a reviewed list have no rate. An institution with at least {rules.minCount} incidents
                  is ranked unless its on-campus FTE is uncertain (its two estimates, or those of an institution
                  whose FTE its rate adds, differ by more than{' '}
                  {ratioPercent(rules.onlineUncertainRatio ?? [5, 4], true)} or cannot both be computed),{' '}
                  {ratioPercent(rules.medicalShare ?? [1, 4])} or more of its incidents were at medical-center
                  campuses on the site's reviewed list, or more than {ratioPercent(rules.sharedShare ?? [1, 20])} are
                  figures shared with another institution's campus. Each rate's {Math.round(rules.ciLevel * 100)}%
                  interval allows for the year-to-year variation institutions' counts show beyond chance; the rank
                  range is the middle {Math.round(rules.ciLevel * 100)}% of the institution's ranks in{' '}
                  {formatNumber(rules.rankRanges?.draws ?? 2000)} simulated rankings, so ranks inside one range are
                  not clearly different.
                </>
              )}
              {notRankedRows.length > 0 && (
                <>
                  {' '}{formatNumber(notRankedWithRate)} {notRankedWithRate === 1 ? 'institution is' : 'institutions are'} shown
                  with a rate but not ranked
                  {notRankedRows.length > notRankedWithRate && (
                    <>, and {formatNumber(notRankedRows.length - notRankedWithRate)} with these incidents have no rate under a rule</>
                  )}
                  :{' '}
                  <button
                    type="button"
                    onClick={openNotRanked}
                    className="underline hover:text-blue-800 dark:hover:text-blue-200"
                  >
                    see Not ranked by rate
                  </button>
                  .
                </>
              )}
              {' '}Lower numbers may reflect reporting differences.
              {' '}<Link to="/methodology#rate-rules" className="underline hover:text-blue-800 dark:hover:text-blue-200">Learn more</Link>
            </p>
          </div>
        )}

        {/* Comparability note for the selected year (data/seriesNotes.ts) */}
        <SeriesNotes years={[selectedYear]} className="mb-4" />

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
                    Showing {displayedRankings.length} of {sortedRankings.length.toLocaleString()} {rowUnit}
                  </span>
                  <span className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    <GitCompare className="w-3.5 h-3.5" />
                    Compare
                  </span>
                </div>
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {displayedRankings.map((item, i) => (
                  <Fragment key={item.key}>
                  {/* Too few to rank, then none, come last: each note goes before the first of its kind */}
                  {tierNotes[item.tier] && (i === 0 || displayedRankings[i - 1].tier !== item.tier) && (
                    <p className="flex items-start gap-2 px-4 py-3 text-sm bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300">
                      <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                      <span>{tierNotes[item.tier]}</span>
                    </p>
                  )}
                  <div className="flex items-stretch">
                    <Link
                      to={`/school/${item.unitid}`}
                      className="flex-1 min-w-0 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300 text-sm font-bold flex items-center justify-center">
                            {item.tier === 'few' || item.tier === 'zero' ? '–' : item.rank}
                          </span>
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {item.campus ?? item.name}
                            {item.branch && !item.campus && (
                              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                            )}
                            {item.campus && (
                              <span className="block text-xs font-normal text-gray-500 dark:text-gray-400">{item.name}</span>
                            )}
                            {rateView && item.campuses > 1 && (
                              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">
                                ({item.campuses} campuses)
                              </span>
                            )}
                            {item.spike && (
                              <span className="block text-xs font-normal text-amber-700 dark:text-amber-400">{SPIKE_NOTE}</span>
                            )}
                            {item.notes.map((note) => (
                              <span key={note} className="block text-xs font-normal text-gray-500 dark:text-gray-400">{note}</span>
                            ))}
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
                        {rateView ? (
                          <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-sm">
                            <span className="font-semibold text-primary-600 dark:text-primary-400 tabular-nums">
                              {item.rate !== null ? `${item.rate.toFixed(1)} per 10k` : '—'}
                            </span>
                            {item.lo !== null && item.hi !== null && (
                              <span className="text-gray-500 dark:text-gray-400 tabular-nums text-xs">
                                {Math.round(level * 100)}% interval {intervalText(item.lo, item.hi)}
                              </span>
                            )}
                            {item.tier === 'ranked' && item.rankLo !== null && item.rankHi !== null && (
                              <span className="text-gray-500 dark:text-gray-400 tabular-nums text-xs" title={rankTitle}>
                                ranks {item.rankLo === item.rankHi ? item.rankLo : `${item.rankLo}–${item.rankHi}`}
                              </span>
                            )}
                            <span className="text-gray-400">&middot;</span>
                            <span className="text-gray-600 dark:text-gray-400 tabular-nums">
                              {countPhrase(item.count, currentOffense, formatNumber(item.count))}
                            </span>
                            {item.fte && (
                              <>
                                <span className="text-gray-400">&middot;</span>
                                <span className="text-gray-500 dark:text-gray-500 tabular-nums text-xs">
                                  {formatNumber(item.fte)} on-campus FTE
                                </span>
                              </>
                            )}
                          </div>
                        ) : (
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
                        )}
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
                    Showing {displayedRankings.length} of {sortedRankings.length.toLocaleString()} {rowUnit}
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
                    {tableRows.slice(0, displayCount).map((row, i) => (
                      <Fragment key={row.id}>
                        {(notesBefore.get(i) ?? []).map((note) => (
                          <tr key={note}>
                            <td colSpan={row.getVisibleCells().length} className="!py-3 bg-amber-50 dark:bg-amber-900/20">
                              <p className="flex items-start gap-2 text-sm text-amber-800 dark:text-amber-300">
                                <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                                <span>{note}</span>
                              </p>
                            </td>
                          </tr>
                        ))}
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
                  Showing all {sortedRankings.length.toLocaleString()} {rowUnit}
                </div>
              )}
            </>
          )}
        </div>

        {/* Rate view: every institution shown but not ranked, or left out
            by a rule, with its reasons, so none is silently absent */}
        {rateView && !loading && !error && (notRankedRows.length > 0 || excludedNone > 0) && (
          <section
            id="not-ranked"
            tabIndex={-1}
            aria-labelledby="not-ranked-heading"
            className="mt-6 bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 focus:outline-none scroll-mt-20"
          >
            <h2 id="not-ranked-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
              <button
                type="button"
                onClick={() => setIsNotRankedOpen(!isNotRankedOpen)}
                aria-expanded={isNotRankedOpen}
                aria-controls="not-ranked-list"
                className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-xl transition-colors"
              >
                <span>
                  Not ranked by rate
                  <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                    {formatNumber(notRankedRows.length)} {notRankedRows.length === 1 ? 'institution' : 'institutions'}
                  </span>
                </span>
                <ChevronRight aria-hidden="true" className={cn('w-4 h-4 flex-shrink-0 transition-transform', isNotRankedOpen && 'rotate-90')} />
              </button>
            </h2>
            {isNotRankedOpen && (
              <div id="not-ranked-list" className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">
                <div className="text-sm text-gray-600 dark:text-gray-400 space-y-2 py-3">
                  <p>
                    Institutions in this {selectedYear} rate view that are not ranked
                    for {noneOfPhrase(selectedOffense, currentOffense)}, with their count and, when they have one,
                    their rate and {Math.round(level * 100)}% interval. The reasons:
                  </p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>
                      <strong className="text-gray-800 dark:text-gray-200">Uncertain on-campus FTE</strong>: NCES's
                      figures give two estimates of the institution's on-campus FTE that differ by more than{' '}
                      {ratioPercent(rules?.onlineUncertainRatio ?? [5, 4], true)}, or the second cannot be computed,
                      or the same is true of an institution whose FTE its rate adds. The rate uses the larger
                      estimate.
                    </li>
                    <li>
                      <strong className="text-gray-800 dark:text-gray-200">Medical-center campuses</strong>:{' '}
                      {ratioPercent(rules?.medicalShare ?? [1, 4])} or more of its incidents were at medical-center
                      campuses on the site's reviewed list, whose patients, visitors and hospital staff are not in
                      the enrollment the rate divides by.
                    </li>
                    <li>
                      <strong className="text-gray-800 dark:text-gray-200">Shared figures</strong>: more
                      than {ratioPercent(rules?.sharedShare ?? [1, 20])} of its incidents are figures DOE publishes
                      identically for a campus of another institution, so its count could be off by more than that.
                    </li>
                    <li>
                      <strong className="text-gray-800 dark:text-gray-200">Fewer than {rules?.minCount ?? 20} incidents</strong>,
                      listed here only together with another reason.
                    </li>
                    <li>
                      <strong className="text-gray-800 dark:text-gray-200">No rate</strong>: a rule leaves the
                      institution out: IPEDS reports that it has a hospital; its Carnegie classification is a
                      special-focus medical school or research institution; it is on a reviewed list; or a merger
                      means its incidents and enrollment may not cover the same campuses.
                    </li>
                  </ul>
                  <p>
                    {[
                      ['online', 'uncertain on-campus FTE'],
                      ['medical_campus', 'medical-center campuses'],
                      ['shared', 'shared figures'],
                      ['few', `also fewer than ${rules?.minCount ?? 20} incidents`],
                      ['hospital', 'hospital, no rate'],
                      ['medical', 'medical school or research institution, no rate'],
                      ['listed', 'reviewed list, no rate'],
                      ['merger', 'merger or renumbering, no rate'],
                      ['family', 'merged institutions, no rate'],
                    ]
                      .filter(([key]) => (notRankedTally.get(key) ?? 0) > 0)
                      .map(([key, label]) => `${label}: ${formatNumber(notRankedTally.get(key) ?? 0)}`)
                      .join(' · ')}
                  </p>
                  {excludedNone > 0 && (
                    <p>
                      {formatNumber(excludedNone)} more {excludedNone === 1 ? 'institution' : 'institutions'} that a
                      rule leaves out reported no {noneOfPhrase(selectedOffense, currentOffense)} for {selectedYear}.
                    </p>
                  )}
                  <p>
                    <Link to="/methodology#rate-rules" className="underline text-primary-600 dark:text-primary-400">
                      Rate Rules
                    </Link>{' '}
                    gives each rule and its source.
                  </p>
                </div>
                <ul className="divide-y divide-gray-100 dark:divide-gray-800 border-t border-gray-100 dark:border-gray-800">
                  {notRankedRows.map(({ e, inst, reasons, notes }) => (
                    <li key={e.id} className="py-3 flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
                      <div className="sm:w-2/5 min-w-0">
                        <Link
                          to={`/school/${inst?.unitid ?? e.id * 1000 + 1}`}
                          className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
                        >
                          {inst?.name ?? `Institution ${e.id}`}
                        </Link>
                        {inst && inst.campuses > 1 && (
                          <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">({inst.campuses} campuses)</span>
                        )}
                      </div>
                      <div className="sm:w-1/4 text-sm text-gray-700 dark:text-gray-300 tabular-nums">
                        <span>{countPhrase(e.count, currentOffense, formatNumber(e.count))}</span>
                        {e.rate !== undefined ? (
                          <span className="block">
                            <span className="font-semibold text-primary-600 dark:text-primary-400">{e.rate.toFixed(1)} per 10k</span>
                            {e.lo !== undefined && e.hi !== undefined && (
                              <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                {Math.round(level * 100)}% interval {intervalText(e.lo, e.hi)}
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="block text-gray-500 dark:text-gray-400">No rate</span>
                        )}
                      </div>
                      <div className="sm:flex-1 min-w-0 text-xs text-gray-600 dark:text-gray-400">
                        {reasons.map((r) => (
                          <span key={r} className="block">{r}</span>
                        ))}
                        {e.spike && <span className="block text-amber-700 dark:text-amber-400">{SPIKE_NOTE}</span>}
                        {notes.map((n) => (
                          <span key={n} className="block text-gray-500 dark:text-gray-400">{n}</span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

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
