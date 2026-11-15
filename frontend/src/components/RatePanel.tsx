import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Info, Loader2 } from 'lucide-react'
import { fetchInstitutionRates } from '../lib/api'
import type { InstitutionRatesFile, Metadata, SchoolProfile } from '../lib/types'
import {
  abroadNote, entryPosition, fmtInt, fteUncertainNote, isListCode, noRatesSentence, notRatedYearText, offenseCount,
  pooledNote,
  rateCodeLabel, rateCodes, windowKeys, windowLabel, windowStatusSentence, windowYears,
} from '../lib/rates'
import { MAIN_RATE_CODES, RATE_IS_NOT, RATE_MEASURE } from '../lib/rateDisplay'
import { RateCodeBlock, VerdictLabel } from './RateCard'
import SingleYearRates from './SingleYearRates'

const card = 'bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 sm:p-6'

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
    <div className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
      <p>
        <strong className="font-semibold">What these rates measure.</strong> {RATE_MEASURE} {RATE_IS_NOT}{' '}
        <Link to="/methodology#rates" className="text-primary-600 dark:text-primary-400 underline">Methodology</Link>
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
    // No rates file: no rated window, single-year rate or flag
    const years = Object.entries(profile.institution?.byYear ?? {}).sort(([a], [b]) => Number(a) - Number(b))
    return (
      <div className="space-y-4 mb-8">
        {countsOnlyNote && <Note>{countsOnlyNote}</Note>}
        <section className={card}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Rates</h2>
          {intro}
          <p className="mt-3 font-medium text-gray-900 dark:text-gray-100">{noRatesSentence(profile, rules)}</p>
          {years.length > 0 && (
            <ul className="mt-2 text-sm text-gray-600 dark:text-gray-400 space-y-0.5">
              {years.map(([y, v]) => (
                <li key={y}>
                  {y}: {v.rated ? 'single-year rate' : notRatedYearText(v.notRated, rules, v.rateExcludedReason)}
                  {v.rateFte !== undefined && !v.rated && v.notRated === 'size' && ` (${fmtInt(v.rateFte)})`}
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
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-gray-500 dark:text-gray-400 mb-8">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Loading rates…
      </div>
    )
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
          headingLevel={level}
        />
        {abroadNotes(code).map((n) => (
          <p key={n} className="mt-2 text-sm text-gray-600 dark:text-gray-400">{n}</p>
        ))}
        {isListCode(code, rules) && <PositionHistory file={file} code={code} metadata={metadata} current={windowKey} />}
      </>
    )
  }

  return (
    <div className="space-y-4 mb-8">
      {countsOnlyNote && <Note>{countsOnlyNote}</Note>}
      <section className={card} aria-labelledby="rates-heading">
        <h2 id="rates-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Rates, {windowLabel(windowKey)}
        </h2>
        {intro}
        {status && <p className="mt-3 font-medium text-gray-900 dark:text-gray-100">{status}</p>}
        {!win && (
          <p className="mt-3 font-medium text-gray-900 dark:text-gray-100">
            Not rated for {windowLabel(windowKey)}: not in DOE's data in any of its years.
          </p>
        )}
        {win?.status === 'rated' && (
          <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">
            On-campus students (FTE) in the denominator:{' '}
            {winYears.map((y) => `${y}: ${fmtInt(win.fteByYear[String(y)] ?? 0)}`).join('; ')}
            {win.fteSmallerByYear && (
              <> (smaller estimate: {winYears.map((y) => `${y}: ${fmtInt(win.fteSmallerByYear?.[String(y)] ?? 0)}`).join('; ')})</>
            )}
            .
          </p>
        )}
        {yearNotes.map((n) => (
          <p key={n} className="mt-1 text-sm text-gray-600 dark:text-gray-400">{n}</p>
        ))}
      </section>

      {win?.status === 'rated' && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {main.map((code) => (
              <section key={code} className={card}>{block(code, 3)}</section>
            ))}
          </div>
          <section className={card}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">Single offenses</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
              These rates have no ordered list. Each shows its comparisons with the national rate and with
              institutions of the same type.
            </p>
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {others.map((code) => {
                const entry = win.codes[code]
                return (
                  <details key={code} className="py-2" open={code === trendCode}>
                    <summary className="cursor-pointer flex flex-wrap items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                      {rateCodeLabel(code)}
                      {entry && (
                        <>
                          <span className="tabular-nums text-gray-700 dark:text-gray-300">{entry.rate.toFixed(2)}</span>
                          <VerdictLabel verdict={entry.verdict} />
                        </>
                      )}
                    </summary>
                    <div className="mt-2">{block(code, 4)}</div>
                  </details>
                )
              })}
            </div>
          </section>
        </>
      )}

      <section className={card}>
        <SingleYearRates file={file} code={trendCode} rules={rules} profile={profile} />
      </section>

      {file.flags.length > 0 && (
        <section className={card}>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Unusual years, every location</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            A year is flagged when its count of an offense at one location is at least{' '}
            {rules.flags?.minCount ?? 10} and far above this institution's other years.{' '}
            <Link to="/methodology#rate-flags" className="text-primary-600 dark:text-primary-400 underline">How flags work</Link>
          </p>
          <ul className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {file.flags.map((f) => (
              <li key={`${f.year}-${f.offense}-${f.geo}`}>
                {f.year}, {f.geo.toLowerCase()}: {offenseCount(f.count, f.offense)} (median of its other years{' '}
                {f.usual.toLocaleString('en-US')})
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
    <p role="note" className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-blue-800 dark:text-blue-200">
      <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <span>{children}</span>
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
    if (!w) return { k, text: 'not in DOE\'s data' }
    if (w.status !== 'rated') return { k, text: 'not rated' }
    const e = w.codes[code]
    if (!e) return { k, text: 'no figure' }
    const n = metadata.rateStats?.windows?.[k]?.[code]?.listed ?? null
    const pos = entryPosition(e, n)
    if (pos) return { k, text: pos }
    if (e.why) return { k, text: 'not on the list (see that window)' }
    return { k, text: 'not on the list (too few expected incidents)' }
  })
  return (
    <div className="mt-3 text-xs text-gray-600 dark:text-gray-400">
      <p className="font-medium">Other windows</p>
      <ul className="space-y-0.5">
        {rows.map((r) => (
          <li key={r.k}>{windowLabel(r.k)}: {r.text}</li>
        ))}
      </ul>
    </div>
  )
}
