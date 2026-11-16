import type { InstitutionRatesFile, RateRules, SchoolProfile } from '../lib/types'
import {
  absentYearClause, absentYearShort, fmtInt, fmtRate, joinAnd, levelPct, notRatedYearShort, notRatedYearText,
  rateCodeLabel,
} from '../lib/rates'
import LinkedText from './LinkedText'
import { formatNumber } from '../lib/utils'
import RowNote, { NoteJoiner, type RowNoteItem } from './RowNote'

interface YearRow {
  year: number
  n: number | null
  rate: number | null
  lo: number | null
  hi: number | null
  // Why the year has no rate, in a few words (null: rated)
  short: string | null
  // Why the year has no rate, or the rated year's notes (behind its note button)
  notes: RowNoteItem[]
}

/**
 * The rate denominator of a year without a rate, as far as the files say:
 * a number, null when NCES has no figure, undefined when they do not say
 * (the school file's institution years, else a window's fteByYear).
 */
function yearFte(file: InstitutionRatesFile, profile: Pick<SchoolProfile, 'institution'> | null, year: number) {
  const iy = profile?.institution?.byYear[String(year)]
  if (iy) return iy.rateFte ?? null
  for (const w of Object.values(file.windows)) {
    if ((w.status === 'size' || w.status === 'rated') && String(year) in w.fteByYear) return w.fteByYear[String(year)]
  }
  return undefined
}

/**
 * The institution's single-year rates of one code, each with its 1-year
 * interval: a trend only. No verdicts, positions or comparisons are made
 * from single years (none are published). Every data year has a row; a year
 * without a rate says why: its notRated reason, or why the institution has
 * no figures of its own that year (absentYears).
 */
export default function SingleYearRates({
  file, code, rules, profile, dataYears,
}: {
  file: InstitutionRatesFile
  code: string
  rules: RateRules | null | undefined
  profile: Pick<SchoolProfile, 'institution'> | null
  // The site's data years (metadata.years)
  dataYears?: number[]
}) {
  const allYears = Array.from(new Set([
    ...(dataYears ?? []), ...Object.keys(file.years).map(Number), ...Object.keys(file.absentYears ?? {}).map(Number),
  ])).sort((a, b) => a - b)
  const rows: YearRow[] = allYears
    .map((year) => {
      const y = file.years[String(year)]
      if (!y) {
        // No figures of its own that year
        const a = file.absentYears?.[String(year)]
        const clause = absentYearClause(a)
        return {
          year, n: null, rate: null, lo: null, hi: null, short: absentYearShort(a),
          notes: [{ kind: 'info' as const, text: `In ${year} ${clause}.` }],
        }
      }
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
        let why = notRatedYearText(y.notRated, rules, excluded)
        let short = notRatedYearShort(y.notRated, rules)
        if (y.notRated === 'size') {
          // Under the minimum, or no NCES figure at all; this page's files do
          // not always say which (a year this campus is not in DOE's data)
          const min = fmtInt(rules?.minFte ?? 1000)
          const fte = yearFte(file, profile, year)
          if (fte === null) {
            short = 'No NCES enrollment figure'
            why = `NCES has no enrollment figure for it that year${excluded ? `. ${excluded}` : ''}`
          } else if (fte === undefined) {
            short = `No NCES figure of ${min} or more`
            why = `NCES has no figure of ${min} or more on-campus students for it that year, the least a rate needs`
          }
        }
        return {
          year, n: null, rate: null, lo: null, hi: null, short,
          notes: [{ kind: 'info' as const, text: /[.!?]$/.test(why) ? why : `${why}.` }],
        }
      }
      const [n, rate, lo, hi] = r
      const text = notes.length > 0 ? joinAnd(notes) : null
      return {
        year, n, rate, lo, hi, short: null,
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
      <h3 className="h3">
        {rateCodeLabel(code)}: single years
      </h3>
      {rated.length > 0 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[44rem] text-ink-3" aria-hidden="true">
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
                  <line x1={x(r.year)} x2={x(r.year)} y1={y(r.lo)} y2={y(r.hi)} className="stroke-accent" strokeWidth={2} />
                  <line x1={x(r.year) - 5} x2={x(r.year) + 5} y1={y(r.lo)} y2={y(r.lo)} className="stroke-accent" strokeWidth={2} />
                  <line x1={x(r.year) - 5} x2={x(r.year) + 5} y1={y(r.hi)} y2={y(r.hi)} className="stroke-accent" strokeWidth={2} />
                  <circle cx={x(r.year)} cy={y(r.rate)} r={4} className="fill-accent-strong" />
                </>
              ) : (
                <text x={x(r.year)} y={y(0) - 4} textAnchor="middle" fontSize={10} fill="currentColor">–</text>
              )}
            </g>
          ))}
        </svg>
      )}
      <p className="text-meta text-ink-2">
        Each year's rate (dot) with its {level}% interval (line). Single years vary more than 3-year averages;
        comparisons and lists use 3-year averages only.
        {skip.length > 0 && <> {joinAnd(skip.map(String))} {skip.length === 1 ? 'is' : 'are'} left out: student counts that year do not measure who was on campus.</>}
        {' '}A dash is a year without a rate; the table gives the reason.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-meta sm:text-ui">
          <caption className="sr-only">{rateCodeLabel(code)}: single-year rates with {level}% intervals</caption>
          <thead>
            <tr className="border-b border-rule-strong text-left text-ink-2">
              <th scope="col" className="py-1.5 pr-3 text-meta font-semibold">Year</th>
              <th scope="col" className="py-1.5 pr-3 text-meta font-semibold">Rate</th>
              <th scope="col" className="py-1.5 pr-3 text-meta font-semibold">{level}% interval</th>
              <th scope="col" className="py-1.5 pr-3 text-meta font-semibold">On campus</th>
              <th scope="col" className="py-1.5 text-meta font-semibold">Note</th>
            </tr>
          </thead>
          <tbody className="tabular divide-y divide-rule text-ink-2">
            {rows.map((r) => (
              <tr key={r.year}>
                <th scope="row" className="py-1.5 pr-3 text-left font-semibold text-ink">{r.year}</th>
                <td className="py-1.5 pr-3">{r.rate !== null ? fmtRate(r.rate) : '–'}</td>
                {r.short !== null ? (
                  // No rate: the reason takes the row's other cells, so it can wrap on a phone
                  <td colSpan={3} className="py-1.5">
                    {r.short}
                    <NoteJoiner />
                    <RowNote subject={String(r.year)} notes={r.notes} className="ml-1" />
                  </td>
                ) : (
                  <>
                    <td className="whitespace-nowrap py-1.5 pr-3">
                      {r.lo !== null && r.hi !== null ? `${fmtRate(r.lo)} to ${fmtRate(r.hi)}` : '–'}
                    </td>
                    <td className="py-1.5 pr-3">{r.n !== null ? fmtInt(r.n) : '–'}</td>
                    <td className="py-1.5">
                      <RowNote subject={String(r.year)} notes={r.notes} />
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sources.size > 0 && (
        <ul className="space-y-0.5 break-words text-meta text-ink-2">
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
