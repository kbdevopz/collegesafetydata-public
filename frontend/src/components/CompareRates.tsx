import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { fetchInstitutionRates } from '../lib/api'
import type { InstitutionRatesFile, Metadata, SchoolProfile } from '../lib/types'
import {
  isListCode, noRatesSentence, ordinal, rateCodeLabel, windowLabel, windowStatusSentence,
} from '../lib/rates'
import { RATE_IS_NOT, RATE_MEASURE } from '../lib/rateDisplay'
import { RateCodeBlock } from './RateCard'

type Loaded = { file: InstitutionRatesFile | null; failed: boolean }

/**
 * Compare's rate view: the two schools' institutions side by side for one
 * window and rate code, each with its interval and comparisons. No test of
 * the difference between the two is made; for list codes the page says
 * whether their position ranges overlap.
 */
export default function CompareRates({
  profiles, metadata, windowKey, code, colors,
}: {
  profiles: SchoolProfile[]
  metadata: Metadata
  windowKey: string
  code: string
  colors: string[]
}) {
  const rules = metadata.rateRules
  const [loaded, setLoaded] = useState<Record<number, Loaded>>({})

  useEffect(() => {
    let live = true
    setLoaded({})
    profiles.forEach((p) => {
      const path = p.institution?.ratesFile
      if (!path) {
        setLoaded((prev) => ({ ...prev, [p.unitid]: { file: null, failed: false } }))
        return
      }
      fetchInstitutionRates(path)
        .then((file) => live && setLoaded((prev) => ({ ...prev, [p.unitid]: { file, failed: false } })))
        .catch(() => live && setLoaded((prev) => ({ ...prev, [p.unitid]: { file: null, failed: true } })))
    })
    return () => {
      live = false
    }
  }, [profiles])

  const stats = metadata.rateStats?.windows?.[windowKey]?.[code]
  const sameInstitution = profiles.length === 2 && profiles[0].institution?.id !== undefined &&
    profiles[0].institution?.id === profiles[1].institution?.id
  const entries = profiles.map((p) => {
    const f = loaded[p.unitid]?.file
    const w = f?.windows[windowKey]
    return w?.status === 'rated' ? w.codes[code] ?? null : null
  })
  const listCode = isListCode(code, rules)
  const ranges = entries.map((e) => (e?.listed && e.rankLo !== undefined && e.rankHi !== undefined ? [e.rankLo, e.rankHi] as const : null))
  let rangeSentence: string | null = null
  if (listCode && !sameInstitution && ranges[0] && ranges[1]) {
    const [a, b] = ranges
    const overlap = a[0] <= b[1] && b[0] <= a[1]
    const names = profiles.map((p) => loaded[p.unitid]?.file?.name ?? p.name)
    const text = `${names[0]} ${ordinal(a[0])} to ${ordinal(a[1])}; ${names[1]} ${ordinal(b[0])} to ${ordinal(b[1])}`
    rangeSentence = overlap
      ? `Their position ranges on the national list overlap (${text}), so the list does not tell their order apart.`
      : `Their position ranges on the national list do not overlap (${text}).`
  }

  return (
    <div className="space-y-4 mb-8">
      <section className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 sm:p-6 text-sm text-gray-700 dark:text-gray-300 space-y-2">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {rateCodeLabel(code)}, {windowLabel(windowKey)}
        </h2>
        <p>{RATE_MEASURE} {RATE_IS_NOT}</p>
        <p>
          Each rate is shown with its interval and its own comparisons. This page does not test whether the
          institutions' rates differ from each other.{' '}
          <Link to="/methodology#rates" className="text-primary-600 dark:text-primary-400 underline">Methodology</Link>
        </p>
        {sameInstitution && (
          <p className="font-medium">
            Both pages belong to the same institution, and NCES counts enrollment per institution, so the rates are
            the same.
          </p>
        )}
        {rangeSentence && <p className="font-medium">{rangeSentence}</p>}
      </section>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {profiles.map((p, i) => {
          const state = loaded[p.unitid]
          const file = state?.file ?? null
          const w = file?.windows[windowKey]
          const entry = entries[i]
          return (
            <section
              key={p.unitid}
              className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border-2 p-4 sm:p-6 space-y-2"
              style={{ borderColor: colors[i] }}
            >
              <p className="text-sm font-medium" style={{ color: colors[i] }}>
                {file?.name ?? p.name}
                {(p.campus || p.isMainCampus === false) && (
                  <span className="block text-xs font-normal text-gray-500 dark:text-gray-400">
                    Rates are the institution's (all its campuses in the United States); this page is one of its campuses
                    {!p.state ? ', outside the United States, so its incidents are not in them' : ''}.
                  </span>
                )}
              </p>
              {!state ? (
                <p className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Loading rates…
                </p>
              ) : state.failed ? (
                <p className="text-sm text-red-700 dark:text-red-400">The rates file could not be loaded.</p>
              ) : !file ? (
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{noRatesSentence(p, rules)}</p>
              ) : !w ? (
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Not rated for {windowLabel(windowKey)}: not in DOE's data in any of its years.
                </p>
              ) : w.status !== 'rated' ? (
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {windowStatusSentence(w, windowKey, rules, p)}
                </p>
              ) : entry ? (
                <RateCodeBlock
                  code={code}
                  windowKey={windowKey}
                  entry={entry}
                  rules={rules}
                  peerType={file.peerType}
                  listN={stats?.listed ?? null}
                  minFteYears={stats?.minFteYears}
                  profile={p}
                  state={file.state}
                />
              ) : (
                <p className="text-sm text-gray-600 dark:text-gray-400">No figure for this code.</p>
              )}
              <Link to={`/school/${p.unitid}?view=rate&window=${windowKey}&offense=${code}`} className="inline-block text-sm text-primary-600 dark:text-primary-400 underline">
                All rates of this institution
              </Link>
            </section>
          )
        })}
      </div>
    </div>
  )
}
