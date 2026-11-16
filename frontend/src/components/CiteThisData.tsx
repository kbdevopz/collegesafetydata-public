import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Check, Copy, Quote } from 'lucide-react'
import { cachedMetadata, getMetadata } from '../lib/api'
import { useBuildInfo } from '../lib/build'
import { SITE_ORIGIN } from '../lib/seo'
import type { Metadata } from '../lib/types'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? null : d
}

function longDate(d: Date): string {
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function bibEscape(s: string): string {
  return s.replace(/([&%$#_{}])/g, '\\$1')
}

interface Props {
  /** Cite one school page instead of the whole site */
  school?: { unitid: number; name: string }
  className?: string
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  const copy = () => {
    navigator.clipboard?.writeText(text).then(
      () => {
        setDone(true)
        window.setTimeout(() => setDone(false), 2000)
      },
      () => undefined,
    )
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400 hover:underline"
      aria-label={`Copy ${label} citation`}
    >
      {done ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {done ? 'Copied' : 'Copy'}
    </button>
  )
}

export default function CiteThisData({ school, className }: Props) {
  const [metadata, setMetadata] = useState<Metadata | null>(cachedMetadata)
  const build = useBuildInfo()
  // The router's location, not window.location, so the build's prerender
  // (no window) renders it too
  const { search } = useLocation()

  // The access date is set in the browser, not when the page is prerendered
  const [accessed, setAccessed] = useState<Date | null>(null)

  useEffect(() => {
    setAccessed(new Date())
    getMetadata().then(setMetadata).catch(() => undefined)
  }, [])

  const built = parseDate(metadata?.lastUpdated)
  const retrieved = accessed ? `Retrieved ${longDate(accessed)}, from` : 'Retrieved from'
  const years = metadata?.years?.length
    ? `${Math.min(...metadata.years)}-${Math.max(...metadata.years)}`
    : null
  const buildYear = built ? built.getFullYear() : accessed ? accessed.getFullYear() : 'n.d.'
  const buildParts = [
    build ? `build ${build.id}` : null,
    built ? `built ${longDate(built)}` : null,
  ].filter(Boolean)
  const buildNote = buildParts.length ? ` (${buildParts.join(', ')})` : ''

  // A school page is cited with the selections in its address (?year=,
  // ?offense=, ?view=rate), so the link opens the view the reader cites; on
  // the canonical host, as the page's canonical URL is. The site as a whole
  // is cited at its home page.
  const url = school ? `${SITE_ORIGIN}/school/${school.unitid}${search}` : `${SITE_ORIGIN}/`
  const title = school
    ? `${school.name}: Clery Act crime statistics${years ? `, ${years}` : ''}`
    : `CollegeSafetyData: Clery Act campus crime statistics${years ? `, ${years}` : ''}`

  const apaSite =
    `CollegeSafetyData. (${buildYear}). ${title}${buildNote} [Data set]. ` +
    `${retrieved} ${url}`
  const apaDoe =
    'U.S. Department of Education, Office of Postsecondary Education. (n.d.). ' +
    `Campus Safety and Security Survey [Data set]. ${retrieved} https://ope.ed.gov/campussafety/`
  const apaNces =
    'National Center for Education Statistics. (n.d.). Integrated Postsecondary Education Data System (IPEDS), ' +
    `fall enrollment and derived fall enrollment (DRVEF) [Data set]. ${retrieved} https://nces.ed.gov/ipeds/`

  const key = school ? `collegesafetydata_${school.unitid}_${buildYear}` : `collegesafetydata_${buildYear}`
  const noteParts = [
    build ? `Build ${build.id}` : null,
    built ? `built ${isoDate(built)}` : null,
    'Data: U.S. Department of Education, Campus Safety and Security Survey; NCES IPEDS',
  ].filter(Boolean)
  const bibtex = [
    `@misc{${key},`,
    `  author       = {{CollegeSafetyData}},`,
    `  title        = {${bibEscape(title)}},`,
    `  year         = {${buildYear}},`,
    `  howpublished = {\\url{${url}}},`,
    `  note         = {${bibEscape(noteParts.join('. '))}${accessed ? `. Accessed ${isoDate(accessed)}` : ''}},`,
    `}`,
  ].join('\n')

  return (
    <section id="cite" className={`scroll-mt-20 ${className ?? ''}`}>
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
        <h3 className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100 mb-1">
          <Quote className="w-4 h-4 text-gray-500 dark:text-gray-400" />
          Cite this data
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          The build identifier names the exact published files (see <a href="/methodology#data" className="underline">Data and
          downloads</a>). Cite the original sources too; the figures are theirs.
        </p>

        <div className="space-y-4 text-sm">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">APA</span>
              <CopyButton text={[apaSite, apaDoe, apaNces].join('\n\n')} label="APA" />
            </div>
            <div className="space-y-2 text-gray-700 dark:text-gray-300 break-words">
              <p className="pl-6 -indent-6">{apaSite}</p>
              <p className="pl-6 -indent-6">{apaDoe}</p>
              <p className="pl-6 -indent-6">{apaNces}</p>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">BibTeX</span>
              <CopyButton text={bibtex} label="BibTeX" />
            </div>
            <pre className="bg-gray-50 dark:bg-gray-800/60 rounded-lg p-3 text-xs text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre">
              {bibtex}
            </pre>
          </div>
        </div>
      </div>
    </section>
  )
}
