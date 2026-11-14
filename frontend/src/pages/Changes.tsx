import { Link } from 'react-router-dom'
import { CHANGES, type ChangeKind } from '../data/changelog'

const KIND_LABEL: Record<ChangeKind, string> = {
  correction: 'Correction',
  method: 'Method',
  site: 'Site',
}

const KIND_CLASS: Record<ChangeKind, string> = {
  correction: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  method: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
  site: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function longDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

export default function Changes() {
  return (
    <div className="min-h-screen">
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
              Changes and Corrections
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              Changes to the figures this site shows and to how it counts, ranks and rates them, newest first.
            </p>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-8">
            A <strong className="text-gray-900 dark:text-gray-100">correction</strong> changes figures the site
            showed; a <strong className="text-gray-900 dark:text-gray-100">method</strong> change changes how they are
            counted, ranked or rated. Figures cited from an earlier build can differ from today's: cite the build
            identifier shown in the footer (see{' '}
            <Link to="/methodology#cite" className="text-primary-600 dark:text-primary-400 underline">how to cite</Link>).
            The full history of the code and data is in the{' '}
            <a
              href="https://github.com/kbdevopz/collegesafetydata-public/commits/main"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 dark:text-primary-400 underline"
            >
              repository
            </a>
            . To report an error, write to{' '}
            <a href="mailto:contact@collegesafetydata.org" className="text-primary-600 dark:text-primary-400 underline">
              contact@collegesafetydata.org
            </a>
            .
          </p>

          <ol className="space-y-6">
            {CHANGES.map((c) => (
              <li
                key={`${c.date}-${c.title}`}
                className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5"
              >
                <div className="flex flex-wrap items-center gap-2 mb-2 text-xs">
                  <time dateTime={c.date} className="text-gray-500 dark:text-gray-400">{longDate(c.date)}</time>
                  <span className={`px-2 py-0.5 rounded-full font-medium ${KIND_CLASS[c.kind]}`}>{KIND_LABEL[c.kind]}</span>
                </div>
                <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">{c.title}</h2>
                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                  {c.body.map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
                {c.methodology && (
                  <Link
                    to={`/methodology#${c.methodology}`}
                    className="inline-block mt-3 text-sm text-primary-600 dark:text-primary-400 underline"
                  >
                    Methodology
                  </Link>
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
