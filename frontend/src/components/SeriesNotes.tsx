import { Link } from 'react-router-dom'
import { Info } from 'lucide-react'
import { notesForYears } from '../data/seriesNotes'
import { cn } from '../lib/utils'

/**
 * Short notes for the years on screen that have a sourced comparability
 * note (data/seriesNotes.ts), each linking to its entry on the Methodology
 * page. Renders nothing when none of the years has one.
 */
export default function SeriesNotes({
  years,
  className,
}: {
  years: Iterable<number>
  className?: string
}) {
  const notes = notesForYears(years)
  if (notes.length === 0) return null
  return (
    <div role="note" className={cn('space-y-1', className)}>
      {notes.map((n) => (
        <p key={n.id} className="flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-400 text-left">
          <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            <strong className="font-medium text-gray-700 dark:text-gray-300">{n.label}:</strong> {n.short}{' '}
            <Link
              to={`/methodology#${n.id}`}
              className="text-primary-600 dark:text-primary-400 underline whitespace-nowrap"
            >
              Details
            </Link>
          </span>
        </p>
      ))}
    </div>
  )
}

// One line for trend charts: what a year's figure counts
export function ReportYearNote({ className }: { className?: string }) {
  return (
    <p className={cn('flex items-start gap-1.5 text-xs text-gray-600 dark:text-gray-400 text-left', className)}>
      <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <span>
        Each year counts crimes reported that year, which can include incidents from earlier years.{' '}
        <Link to="/methodology#year-reported" className="text-primary-600 dark:text-primary-400 underline whitespace-nowrap">
          Details
        </Link>
      </span>
    </p>
  )
}
