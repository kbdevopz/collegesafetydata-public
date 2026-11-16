/**
 * Small shared pieces of the site's design (tokens and classes in
 * src/index.css and tailwind.config.js).
 */
import type { ReactNode } from 'react'
import { Check, ChevronRight, GitCompare, Loader2 } from 'lucide-react'
import { cn } from '../lib/utils'

/** A page's title, with an optional lede under it; `children` go below. */
export function PageHeader({
  title, lede, children, className,
}: {
  title: ReactNode
  lede?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('wrap pt-8 pb-6 sm:pt-10', className)}>
      <h1 className="h1">{title}</h1>
      {lede && <p className="lede mt-2">{lede}</p>}
      {children}
    </header>
  )
}

/**
 * Text that is there to be read when wanted: a native disclosure (keyboard
 * and screen readers handle it), closed by default.
 */
export function Disclosure({
  summary, children, className, open,
}: {
  summary: ReactNode
  children: ReactNode
  className?: string
  open?: boolean
}) {
  return (
    <details className={cn('group', className)} open={open}>
      <summary className="inline-flex min-h-[1.5rem] cursor-pointer list-none items-center gap-1 text-meta font-semibold text-accent hover:text-accent-strong [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-4 w-4 flex-shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
        {summary}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  )
}

/**
 * The control that adds a school to, or removes it from, the comparison.
 * `cell`: a square button in a table cell or list; `column`: a full-height
 * column at the right of a card. `withTitle` adds the tooltip; `pressed`, when
 * given, is announced as the toggle's state.
 */
export function CompareButton({
  selected, name, onClick, variant = 'cell', withTitle = false, pressed, className,
}: {
  selected: boolean
  name: string
  onClick: (e: React.MouseEvent) => void
  variant?: 'cell' | 'column'
  withTitle?: boolean
  pressed?: boolean
  className?: string
}) {
  const Icon = selected ? Check : GitCompare
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={selected ? `Remove ${name} from comparison` : `Add ${name} to comparison`}
      aria-pressed={pressed}
      title={withTitle ? (selected ? 'Remove from comparison' : 'Add to comparison') : undefined}
      className={cn(
        variant === 'cell'
          ? 'inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded'
          : 'flex w-12 flex-shrink-0 items-center justify-center border-l border-rule',
        selected ? 'bg-accent-tint text-accent' : 'text-ink-3 hover:bg-subtle hover:text-ink',
        className
      )}
    >
      <Icon className={variant === 'cell' ? 'h-4 w-4' : 'h-[1.125rem] w-[1.125rem]'} aria-hidden="true" />
    </button>
  )
}

/** A loading state: a small spinner and a line of text. */
export function Loading({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center justify-center gap-2 py-16 text-meta text-ink-3', className)}>
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

/** A school's key: solid for the first school, hatched for the second */
export function SchoolSwatch({ color, hatched }: { color: string; hatched: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 flex-shrink-0 rounded-sm"
      style={hatched
        ? { border: `1.5px solid ${color}`, background: `repeating-linear-gradient(45deg, ${color} 0 1.5px, transparent 1.5px 3.5px)` }
        : { backgroundColor: color }}
    />
  )
}
