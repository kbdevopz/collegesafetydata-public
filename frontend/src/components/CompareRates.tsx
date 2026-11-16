import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchInstitutionRates } from '../lib/api'
import type { InstitutionRatesFile, Metadata, SchoolProfile } from '../lib/types'
import {
  isListCode, missingYearsSentence, noRatesSentence, ordinal, rateCodeLabel, windowLabel, windowStatusSentence,
} from '../lib/rates'
import { RATE_IS_NOT, RATE_MEASURE } from '../lib/rateDisplay'
import { RateCodeBlock } from './RateCard'
import LinkedText from './LinkedText'
import RowNote, { NoteJoiner } from './RowNote'
import { Loading, SchoolSwatch } from './ui'

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
    <div className="space-y-6 mb-8">
      <section className="max-w-prose text-ui text-ink-2 space-y-2">
        <h2 className="font-serif text-[1.25rem] font-semibold leading-snug text-ink">
          {rateCodeLabel(code)}, {windowLabel(windowKey)}
        </h2>
        <p>{RATE_MEASURE} {RATE_IS_NOT}</p>
        <p>
          Each rate is shown with its interval and its own comparisons. This page does not test whether the
          institutions' rates differ from each other.{' '}
          <Link to="/methodology#rates" className="link">Methodology</Link>
        </p>
        {sameInstitution && (
          <p className="font-semibold text-ink">
            Both pages belong to the same institution, and NCES counts enrollment per institution, so the rates are
            the same.
          </p>
        )}
        {rangeSentence && <p className="font-semibold text-ink">{rangeSentence}</p>}
      </section>
      <div className="grid grid-cols-1 border-t border-rule md:grid-cols-2">
        {profiles.map((p, i) => {
          const state = loaded[p.unitid]
          const file = state?.file ?? null
          const w = file?.windows[windowKey]
          const entry = entries[i]
          return (
            <section
              key={p.unitid}
              className={i === 1 ? 'min-w-0 space-y-2 border-t border-rule py-6 md:border-t-0 md:border-l md:pl-6' : 'min-w-0 space-y-2 py-6 md:pr-6'}
            >
              <p className="flex items-center gap-2 text-ui font-semibold text-ink">
                <SchoolSwatch color={colors[i]} hatched={i === 1} />
                {/* One flex item, so the note button stays on the line of the name's last word */}
                <span className="min-w-0">
                  {file?.name ?? p.name}
                  {(p.campus || p.isMainCampus === false) && (
                    <>
                      <NoteJoiner />
                      <RowNote
                        subject={file?.name ?? p.name}
                        notes={[{
                          kind: 'info',
                          text: "Rates are the institution's (all its campuses in the United States); the school " +
                            `compared here is one of its campuses${!p.state ? ', outside the United States, so its incidents are not in them' : ''}.`,
                        }]}
                        className="ml-1"
                      />
                    </>
                  )}
                </span>
              </p>
              {!state ? (
                <Loading className="justify-start py-2">Loading rates…</Loading>
              ) : state.failed ? (
                <p className="text-ui text-danger">The rates file could not be loaded.</p>
              ) : !file ? (
                <p className="text-ui font-semibold text-ink">{noRatesSentence(p, rules)}</p>
              ) : !w ? (
                <p className="text-ui font-semibold text-ink">
                  {missingYearsSentence(windowKey, [], rules, file.absentYears)}
                </p>
              ) : w.status !== 'rated' ? (
                <p className="text-ui font-semibold text-ink break-words">
                  <LinkedText text={windowStatusSentence(w, windowKey, rules, p, file.absentYears) ?? ''} />
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
                  notes={w}
                  hospital={file.hospitalUnresolved ?? []}
                />
              ) : (
                <p className="text-ui text-ink-2">No figure for this code.</p>
              )}
              <Link to={`/school/${p.unitid}?view=rate&window=${windowKey}&offense=${code}`} className="link inline-block text-meta">
                All rates of this institution
              </Link>
            </section>
          )
        })}
      </div>
    </div>
  )
}
