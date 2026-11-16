import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { fetchInstitutionRates } from '../lib/api'
import type { InstitutionRatesFile, Metadata, SchoolProfile } from '../lib/types'
import {
  abroadNote, entryPosition, fmtInt, fmtRate, fteUncertainNote, isListCode, missingYearsSentence, noRatesSentence,
  notRatedYearText, offenseCount, pooledNote,
  rateCodeLabel, rateCodes, windowKeys, windowLabel, windowStatusSentence, windowYears,
} from '../lib/rates'
import { MAIN_RATE_CODES, RATE_IS_NOT, RATE_MEASURE } from '../lib/rateDisplay'
import { HospitalNote, RateCodeBlock, VerdictLabel } from './RateCard'
import LinkedText from './LinkedText'
import { cn } from '../lib/utils'
import SingleYearRates from './SingleYearRates'
import { Loading } from './ui'

const sectionTitle = 'font-serif text-[1.25rem] font-semibold leading-snug text-ink'
const section = 'border-t border-rule pt-6'

/**
 * The school page's rate view: the institution's 3-year rates in one window
 * (every code), why a window has none, and the single-year trend of
 * `trendCode`.
 */
export default function RatePanel({
  profile, metadata, windowKey, trendCode, countsOnlyNote,
}: {
  profile: SchoolProfile
  metadata: Metadata
  windowKey: string
  trendCode: string
  // When the page's selection has no rate: why (shown first)
  countsOnlyNote: string | null
}) {
  const rules = metadata.rateRules
  const path = profile.institution?.ratesFile
  const [file, setFile] = useState<InstitutionRatesFile | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    setFile(null)
    setError(false)
    if (!path) return
    let live = true
    fetchInstitutionRates(path)
      .then((f) => live && setFile(f))
      .catch(() => live && setError(true))
    return () => {
      live = false
    }
  }, [path])

  const institutionName = file?.name ?? profile.name
  const campusAbroad = !profile.state
  const intro = (
    <div className="max-w-prose space-y-2 text-ui text-ink-2">
      <p>
        <strong className="font-semibold text-ink">What these rates measure.</strong> {RATE_MEASURE} {RATE_IS_NOT}{' '}
        <Link to="/methodology#rates" className="link">Methodology</Link>
      </p>
      <p>
        NCES counts enrollment per institution, not per campus, so a rate is made for {institutionName} as a
        whole: the on-campus incidents of all its campuses in the United States.
        {profile.campus || profile.isMainCampus === false ? ' This page is one of its campuses.' : ''}
      </p>
      {campusAbroad && (
        <p>
          This campus is outside the United States. Its incidents are not in its institution's rates, because NCES
          fall enrollment leaves out students at branch campuses abroad.
        </p>
      )}
    </div>
  )

  if (!path) {
    // No rates file: no rated window, single-year rate or flag. Each year's
    // reason, with the years that share it
    const years = Object.entries(profile.institution?.byYear ?? {}).sort(([a], [b]) => Number(a) - Number(b))
    const groups = new Map<string, string[]>()
    for (const [y, v] of years) {
      const text = v.rated
        ? 'single-year rate'
        : `${notRatedYearText(v.notRated, rules, v.rateExcludedReason)}` +
          `${v.rateFte !== undefined && v.notRated === 'size' ? ` (${fmtInt(v.rateFte)})` : ''}`
      groups.set(text, [...(groups.get(text) ?? []), y])
    }
    return (
      <div className="space-y-6 mb-8">
        {countsOnlyNote && <Note>{countsOnlyNote}</Note>}
        <section>
          <h2 className={cn(sectionTitle, 'mb-3')}>Rates</h2>
          {intro}
          <p className="mt-4 max-w-prose text-ui font-semibold text-ink">{noRatesSentence(profile, rules, years.length > 0)}</p>
          {years.length > 0 && (
            <ul className="tabular mt-2 max-w-prose text-meta text-ink-2 space-y-0.5 break-words">
              {Array.from(groups.entries()).map(([text, ys]) => (
                <li key={ys[0]}>
                  {ys.join(', ')}: <LinkedText text={text} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mb-8">
        <Note>The rates file of this institution could not be loaded. Please try again.</Note>
      </div>
    )
  }
  if (!file) {
    return <Loading className="mb-8 justify-start py-8">Loading rates…</Loading>
  }

  const win = file.windows[windowKey]
  const status = win ? windowStatusSentence(win, windowKey, rules, profile) : null
  const stats = metadata.rateStats?.windows?.[windowKey] ?? {}
  const codes = rateCodes(rules)
  const main = codes.filter((c) => (MAIN_RATE_CODES as readonly string[]).includes(c))
  const others = codes.filter((c) => !(MAIN_RATE_CODES as readonly string[]).includes(c))
  const [y0, y1] = windowYears(windowKey)
  const winYears = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i)

  // Notes on the window's years: the denominator's partners and estimates
  const yearNotes: string[] = []
  if (win?.status === 'rated') {
    for (const y of winYears) {
      const iy = profile.institution?.byYear[String(y)]
      const pooled = pooledNote(iy?.pooledWith, y)
      if (pooled) yearNotes.push(pooled)
      const fu = fteUncertainNote(iy?.fteUncertain, y)
      if (fu) yearNotes.push(fu)
    }
  }
  const abroadNotes = (code: string) =>
    winYears.map((y) => abroadNote(profile.institution?.byYear[String(y)]?.abroad, code, y)).filter((s): s is string => !!s)

  const block = (code: string, level: 3 | 4) => {
    if (win?.status !== 'rated') return null
    const entry = win.codes[code]
    if (!entry) return null
    return (
      <>
        <RateCodeBlock
          code={code}
          windowKey={windowKey}
          entry={entry}
          rules={rules}
          peerType={file.peerType}
          listN={stats[code]?.listed ?? null}
          minFteYears={stats[code]?.minFteYears}
          profile={profile}
          state={file.state}
          notes={win}
          headingLevel={level}
          hospital={null}
        />
        {abroadNotes(code).map((n) => (
          <p key={n} className="mt-2 text-meta text-ink-2">{n}</p>
        ))}
        {isListCode(code, rules) && <PositionHistory file={file} code={code} metadata={metadata} current={windowKey} />}
      </>
    )
  }

  return (
    <div className="space-y-8 mb-8">
      {countsOnlyNote && <Note>{countsOnlyNote}</Note>}
      <section aria-labelledby="rates-heading">
        <h2 id="rates-heading" className={cn(sectionTitle, 'mb-3')}>
          Rates, {windowLabel(windowKey)}
        </h2>
        {intro}
        {status && <p className="mt-4 max-w-prose text-ui font-semibold text-ink break-words"><LinkedText text={status} /></p>}
        {!win && (
          <p className="mt-4 max-w-prose text-ui font-semibold text-ink break-words">
            {missingYearsSentence(windowKey, [], rules, profile)}
          </p>
        )}
        {win?.status === 'rated' && (
          <p className="tabular mt-3 max-w-prose text-meta text-ink-2">
            On-campus students (FTE) in the denominator:{' '}
            {winYears.map((y) => `${y}: ${fmtInt(win.fteByYear[String(y)] ?? 0)}`).join('; ')}
            {win.fteSmallerByYear && (
              <> (smaller estimate: {winYears.map((y) => `${y}: ${fmtInt(win.fteSmallerByYear?.[String(y)] ?? 0)}`).join('; ')})</>
            )}
            .
          </p>
        )}
        {yearNotes.map((n) => (
          <p key={n} className="mt-1 max-w-prose text-meta text-ink-2">{n}</p>
        ))}
        {win?.status === 'rated' && win.hospitalUnresolved && (
          <div className="mt-3 max-w-prose">
            <HospitalNote note={win.hospitalUnresolved} rows={file.hospitalUnresolved ?? []} windowYearsN={winYears.length} />
          </div>
        )}
      </section>

      {win?.status === 'rated' && (
        <>
          <div className="grid grid-cols-1 border-t border-rule lg:grid-cols-3">
            {main.map((code, i) => (
              <section
                key={code}
                className={cn('min-w-0 py-6', i > 0 && 'border-t border-rule lg:border-t-0 lg:border-l lg:pl-6', i < main.length - 1 && 'lg:pr-6')}
              >
                {block(code, 3)}
              </section>
            ))}
          </div>
          <section className={section}>
            <h2 className={cn(sectionTitle, 'mb-1')}>Single offenses</h2>
            <p className="max-w-prose text-meta text-ink-2 mb-3">
              These rates have no ordered list. Each shows its comparisons with the national rate and with
              institutions of the same type.
            </p>
            <div className="divide-y divide-rule border-y border-rule">
              {others.map((code) => {
                const entry = win.codes[code]
                return (
                  <details key={code} className="group py-2" open={code === trendCode}>
                    <summary className="flex min-h-[1.75rem] cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-1 text-ui font-semibold text-ink [&::-webkit-details-marker]:hidden">
                      <ChevronRight className="h-4 w-4 flex-shrink-0 text-ink-3 transition-transform group-open:rotate-90" aria-hidden="true" />
                      {rateCodeLabel(code)}
                      {entry && (
                        <>
                          <span className="tabular font-normal text-ink-2">{fmtRate(entry.rate)}</span>
                          <VerdictLabel verdict={entry.verdict} />
                        </>
                      )}
                    </summary>
                    <div className="mt-2 mb-2 max-w-prose pl-6">{block(code, 4)}</div>
                  </details>
                )
              })}
            </div>
          </section>
        </>
      )}

      <section className={cn(section, 'single-year-rates')}>
        <SingleYearRates file={file} code={trendCode} rules={rules} profile={profile} />
      </section>

      {file.flags.length > 0 && (
        <section className={section}>
          <h2 className={cn(sectionTitle, 'mb-2')}>Unusual years, every location</h2>
          <p className="max-w-prose text-meta text-ink-2 mb-2">
            A year is flagged when its count of an offense at one location is at least{' '}
            {rules.flags?.minCount ?? 10} and far above this institution's other years.{' '}
            <Link to="/methodology#rate-flags" className="link">How flags work</Link>
          </p>
          <ul className="tabular max-w-prose space-y-1 text-ui text-ink-2">
            {file.flags.map((f) => (
              <li key={`${f.year}-${f.offense}-${f.geo}`}>
                {f.year}, {f.geo.toLowerCase()}: {offenseCount(f.count, f.offense)} (median of its other years{' '}
                {fmtInt(f.usual)})
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p role="note" className="aside-note max-w-prose">
      {children}
    </p>
  )
}

/** A list code's position in every window, or why it has none there */
function PositionHistory({
  file, code, metadata, current,
}: {
  file: InstitutionRatesFile
  code: string
  metadata: Metadata
  current: string
}) {
  const keys = windowKeys(metadata.rateRules).filter((k) => k !== current)
  const rows = keys.map((k) => {
    const w = file.windows[k]
    // The window's own view says why (some years are not in DOE's data, or
    // their figures count under another institution)
    if (!w || w.status !== 'rated') return { k, text: 'not rated' }
    const e = w.codes[code]
    if (!e) return { k, text: 'no figure' }
    const n = metadata.rateStats?.windows?.[k]?.[code]?.listed ?? null
    const pos = entryPosition(e, n)
    if (pos) return { k, text: pos }
    if (e.why) return { k, text: 'not on the list (see that window)' }
    if (e.notPlaced) return { k, text: 'not placed: an unusual year in that period' }
    return { k, text: 'not on the list (too few expected incidents)' }
  })
  return (
    <div className="tabular mt-3 text-meta text-ink-2">
      <p className="font-semibold text-ink">Other windows</p>
      <ul className="space-y-0.5">
        {rows.map((r) => (
          <li key={r.k}>{windowLabel(r.k)}: {r.text}</li>
        ))}
      </ul>
    </div>
  )
}
