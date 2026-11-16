import { Link } from 'react-router-dom'
import { CHANGES, type ChangeKind } from '../data/changelog'

const KIND_LABEL: Record<ChangeKind, string> = {
  correction: 'Correction',
  method: 'Method',
  site: 'Site',
}

// The kind is in words; the outline only repeats it
const KIND_CLASS: Record<ChangeKind, string> = {
  correction: 'border-attention text-attention',
  method: 'border-accent text-accent',
  site: 'border-rule-strong text-ink-2',
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
      <header className="wrap pt-8 pb-8 sm:pt-10">
        <h1 className="h1">
          Changes and Corrections
        </h1>
        <p className="lede mt-2">
          Changes to the figures this site shows and to how it counts, ranks and rates them, newest first.
        </p>
      </header>

      <div className="wrap pb-12">
        <div className="max-w-[46rem]">
          <p className="text-ui text-ink-2 mb-8">
            A <strong className="font-semibold text-ink">correction</strong> changes figures the site
            showed; a <strong className="font-semibold text-ink">method</strong> change changes how they are
            counted, ranked or rated. Figures cited from an earlier build can differ from today's: cite the build
            identifier shown in the footer (see{' '}
            <Link to="/methodology#cite" className="link">how to cite</Link>).
            The full history of the code and data is in the{' '}
            <a
              href="https://github.com/kbdevopz/collegesafetydata-public/commits/main"
              target="_blank"
              rel="noopener noreferrer"
              className="link"
            >
              repository
            </a>
            . To report an error, write to{' '}
            <a href="mailto:contact@collegesafetydata.org" className="link">
              contact@collegesafetydata.org
            </a>
            .
          </p>

          <ol className="border-b border-rule">
            {CHANGES.map((c) => (
              <li
                key={`${c.date}-${c.title}`}
                className="border-t border-rule py-6"
              >
                <div className="flex flex-wrap items-center gap-2 mb-2 text-meta">
                  <time dateTime={c.date} className="text-ink-3">{longDate(c.date)}</time>
                  <span className={`rounded-sm border px-1.5 text-label font-semibold ${KIND_CLASS[c.kind]}`}>{KIND_LABEL[c.kind]}</span>
                </div>
                <h2 className="h-sub mb-2">{c.title}</h2>
                <div className="space-y-2 text-ui text-ink-2">
                  {c.body.map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
                {c.methodology && (
                  <Link
                    to={`/methodology#${c.methodology}`}
                    className="link inline-block mt-3 text-meta"
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
