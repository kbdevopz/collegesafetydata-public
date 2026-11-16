import type { InstitutionRatesFile, RateRules, SchoolProfile } from '../lib/types'
import { fmtInt, fmtRate, joinAnd, levelPct, notRatedYearText, rateCodeLabel } from '../lib/rates'
import LinkedText from './LinkedText'
import { formatNumber } from '../lib/utils'
import RowNote, { type RowNoteItem } from './RowNote'

interface YearRow {
  year: number
  n: number | null
  rate: number | null
  lo: number | null
  hi: number | null
  // Why the year has no rate, or the rated year's notes (behind its note button)
  notes: RowNoteItem[]
}

/**
 * The institution's single-year rates of one code, each with its 1-year
 * interval: a trend only. No verdicts, positions or comparisons are made
 * from single years (none are published).
 */
export default function SingleYearRates({
  file, code, rules, profile,
}: {
  file: InstitutionRatesFile
  code: string
  rules: RateRules | null | undefined
  profile: Pick<SchoolProfile, 'institution'> | null
}) {
  const rows: YearRow[] = Object.keys(file.years)
    .map(Number)
    .sort((a, b) => a - b)
    .map((year) => {
      const y = file.years[String(year)]
      const r = y.rates?.[code]
      const notes: string[] = []
      if (y.fteUncertain === 'own') notes.push('two estimates of on-campus students differ')
      if (y.fteUncertain === 'pooled') notes.push('estimates of on-campus students differ for an institution counted with this one')
      if ((y.medical?.[code] ?? 0) > 0) notes.push(`${fmtInt(y.medical?.[code] ?? 0)} at a medical-center campus`)
      // Shared campus sites: a host's count includes them, once; a guest's leaves them out
      if ((y.sharedIn?.[code] ?? 0) > 0) notes.push(`${fmtInt(y.sharedIn?.[code] ?? 0)} at a campus site shared with another institution, counted here once`)
      if ((y.sharedOut?.[code] ?? 0) > 0) notes.push(`${fmtInt(y.sharedOut?.[code] ?? 0)} more at a campus site shared with another institution, not in this rate`)
      if (!r) {
        // The reason without its source (the sources are listed below the table)
        const excluded = profile?.institution?.byYear[String(year)]?.rateExcludedReason?.split(' Source: ')[0]
        const why = notRatedYearText(y.notRated, rules, excluded)
        return { year, n: null, rate: null, lo: null, hi: null, notes: [{ kind: 'info' as const, text: /[.!?]$/.test(why) ? why : `${why}.` }] }
      }
      const [n, rate, lo, hi] = r
      const text = notes.length > 0 ? joinAnd(notes) : null
      return {
        year, n, rate, lo, hi,
        notes: text ? [{ kind: 'info' as const, text: `${text.charAt(0).toUpperCase()}${text.slice(1)}.` }] : [],
      }
    })
  const rated = rows.filter((r) => r.rate !== null)
  // The sources of the reasons in the table, with the years that cite each
  const sources = new Map<string, number[]>()
  for (const r of rows) {
    if (r.rate !== null) continue
    const full = profile?.institution?.byYear[String(r.year)]?.rateExcludedReason
    const i = full?.indexOf(' Source: ') ?? -1
    if (full && i >= 0) {
      const src = full.slice(i + ' Source: '.length)
      sources.set(src, [...(sources.get(src) ?? []), r.year])
    }
  }
  const skip = rules?.skipYears ?? []
  const level = levelPct(rules)

  // Chart geometry (viewBox units; the SVG scales to its box)
  const W = 640
  const H = 200
  const pad = { l: 44, r: 12, t: 10, b: 26 }
  const years = rows.map((r) => r.year)
  const x0 = Math.min(...years)
  const x1 = Math.max(...years)
  const maxHi = Math.max(1, ...rated.map((r) => r.hi ?? 0))
  const yMax = niceMax(maxHi)
  const x = (year: number) => pad.l + (x1 === x0 ? (W - pad.l - pad.r) / 2 : ((year - x0) / (x1 - x0)) * (W - pad.l - pad.r))
  const y = (v: number) => pad.t + (1 - v / yMax) * (H - pad.t - pad.b)
  const ticks = [0, yMax / 2, yMax]

  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
        {rateCodeLabel(code)}: single years
      </h3>
      {rated.length > 0 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto text-gray-500 dark:text-gray-400" aria-hidden="true">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="currentColor" strokeOpacity={0.25} />
              <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="currentColor">{formatTick(t)}</text>
            </g>
          ))}
          {rows.map((r) => (
            <g key={r.year}>
              <text x={x(r.year)} y={H - 8} textAnchor="middle" fontSize={11} fill="currentColor">{String(r.year).slice(2)}</text>
              {r.rate !== null && r.lo !== null && r.hi !== null ? (
                <>
                  <line x1={x(r.year)} x2={x(r.year)} y1={y(r.lo)} y2={y(r.hi)} stroke="#2563eb" strokeWidth={2} />
                  <line x1={x(r.year) - 5} x2={x(r.year) + 5} y1={y(r.lo)} y2={y(r.lo)} stroke="#2563eb" strokeWidth={2} />
                  <line x1={x(r.year) - 5} x2={x(r.year) + 5} y1={y(r.hi)} y2={y(r.hi)} stroke="#2563eb" strokeWidth={2} />
                  <circle cx={x(r.year)} cy={y(r.rate)} r={4} fill="#1d4ed8" />
                </>
              ) : (
                <text x={x(r.year)} y={y(0) - 4} textAnchor="middle" fontSize={10} fill="currentColor">–</text>
              )}
            </g>
          ))}
        </svg>
      )}
      <p className="text-xs text-gray-600 dark:text-gray-400">
        Each year's rate (dot) with its {level}% interval (line). Single years vary more than 3-year averages;
        comparisons and lists use 3-year averages only.
        {skip.length > 0 && <> {joinAnd(skip.map(String))} {skip.length === 1 ? 'is' : 'are'} left out: student counts that year do not measure who was on campus.</>}
        {' '}A dash is a year without a rate; its note in the table gives the reason.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs sm:text-sm">
          <caption className="sr-only">{rateCodeLabel(code)}: single-year rates with {level}% intervals</caption>
          <thead>
            <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="py-1 pr-2 font-medium">Year</th>
              <th scope="col" className="py-1 pr-2 font-medium">Rate</th>
              <th scope="col" className="py-1 pr-2 font-medium">{level}% interval</th>
              <th scope="col" className="py-1 pr-2 font-medium">On campus</th>
              <th scope="col" className="py-1 font-medium">Note</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800 text-gray-700 dark:text-gray-300">
            {rows.map((r) => (
              <tr key={r.year}>
                <th scope="row" className="py-1 pr-2 font-medium tabular-nums">{r.year}</th>
                <td className="py-1 pr-2 tabular-nums">{r.rate !== null ? fmtRate(r.rate) : '–'}</td>
                <td className="py-1 pr-2 tabular-nums whitespace-nowrap">
                  {r.lo !== null && r.hi !== null ? `${fmtRate(r.lo)} to ${fmtRate(r.hi)}` : '–'}
                </td>
                <td className="py-1 pr-2 tabular-nums">{r.n !== null ? fmtInt(r.n) : '–'}</td>
                <td className="py-1 text-gray-600 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1">
                    {r.rate === null && <span>No rate</span>}
                    <RowNote subject={String(r.year)} notes={r.notes} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sources.size > 0 && (
        <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-0.5 break-words">
          {Array.from(sources.entries()).map(([src, ys]) => (
            <li key={src}>
              Source for {ys.length === 1 ? ys[0] : joinAnd(ys.map(String))}: <LinkedText text={src} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// A round axis maximum at or above `v`
function niceMax(v: number): number {
  const p = Math.pow(10, Math.floor(Math.log10(v)))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p
  return 10 * p
}

function formatTick(v: number): string {
  return Number.isInteger(v) ? formatNumber(v) : formatNumber(v, 1)
}
