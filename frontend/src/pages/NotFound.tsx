import { Link } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Rankings', note: 'search for a campus or browse the rankings' },
  { to: '/compare', label: 'Compare', note: 'compare campuses side by side' },
  { to: '/methodology', label: 'Methodology', note: 'how the figures are built' },
  { to: '/about', label: 'About', note: 'what this site shows' },
]

export default function NotFound() {
  return (
    <div className="wrap py-16">
      <p className="tabular text-meta font-semibold text-ink-3 mb-2">404</p>
      <h1 className="h1 mb-3">Page not found</h1>
      <p className="lede mb-8">
        There is no page at this address. It may have been mistyped, or a link may be out of date.
      </p>
      <ul className="max-w-prose space-y-2 text-body">
        {LINKS.map(({ to, label, note }) => (
          <li key={to}>
            <Link to={to} className="link font-semibold">
              {label}
            </Link>
            <span className="text-ink-2">: {note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
