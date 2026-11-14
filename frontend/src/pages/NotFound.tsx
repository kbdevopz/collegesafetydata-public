import { Link } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Rankings', note: 'search for a campus or browse the rankings' },
  { to: '/compare', label: 'Compare', note: 'compare campuses side by side' },
  { to: '/methodology', label: 'Methodology', note: 'how the figures are built' },
  { to: '/about', label: 'About', note: 'what this site shows' },
]

export default function NotFound() {
  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-16 max-w-2xl">
      <p className="text-sm font-semibold text-primary-600 dark:text-primary-400 mb-2">404</p>
      <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">Page not found</h1>
      <p className="text-gray-600 dark:text-gray-400 mb-8">
        There is no page at this address. It may have been mistyped, or a link may be out of date.
      </p>
      <ul className="space-y-3">
        {LINKS.map(({ to, label, note }) => (
          <li key={to}>
            <Link to={to} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">
              {label}
            </Link>
            <span className="text-gray-600 dark:text-gray-400">: {note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
