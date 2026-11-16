import { Link } from 'react-router-dom'
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
        <p key={n.id} className="text-meta text-ink-2 text-left">
          <strong className="font-semibold text-ink">{n.label}:</strong> {n.short}{' '}
          <Link
            to={`/methodology#${n.id}`}
            className="link whitespace-nowrap"
          >
            Details
          </Link>
        </p>
      ))}
    </div>
  )
}

// One line for trend charts: what a year's figure counts
export function ReportYearNote({ className }: { className?: string }) {
  return (
    <p className={cn('text-meta text-ink-2 text-left', className)}>
      Each year counts crimes reported that year, which can include incidents from earlier years.{' '}
      <Link to="/methodology#year-reported" className="link whitespace-nowrap">
        Details
      </Link>
    </p>
  )
}
