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
      className={cn('link break-words', className)}
    >
      {children ?? source.label}
      <ExternalLink className="ml-0.5 inline-block h-3 w-3 align-[-0.05em]" aria-hidden="true" />
    </a>
  )
}
