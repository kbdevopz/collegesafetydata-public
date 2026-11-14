import { ExternalLink } from 'lucide-react'
import type { Source } from '../data/sources'
import { cn } from '../lib/utils'

// A link to an official source, opening in a new tab
export default function SourceLink({
  source,
  children,
  className,
}: {
  source: Source
  children?: React.ReactNode
  className?: string
}) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'inline-flex items-baseline gap-1 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 underline break-words',
        className
      )}
    >
      <span>{children ?? source.label}</span>
      <ExternalLink className="w-3 h-3 flex-shrink-0 self-center" aria-hidden="true" />
    </a>
  )
}
