import { useState, useRef, useEffect } from 'react'
import { Info, X } from 'lucide-react'
import { cn } from '../lib/utils'
import type { Offense } from '../lib/types'

interface OffensePopoverProps {
  offense: Offense
  className?: string
}

export default function OffensePopover({ offense, className }: OffensePopoverProps) {
  const [isOpen, setIsOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Close on Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen])

  return (
    <div className={cn('relative inline-flex items-center', className)}>
      {/* Trigger Button */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'inline-flex h-7 w-7 items-center justify-center rounded',
          'text-ink-3 hover:text-ink hover:bg-subtle',
          isOpen && 'bg-tint text-ink'
        )}
        aria-label={`More info about ${offense.display}`}
        aria-expanded={isOpen}
      >
        <Info className="w-4 h-4" aria-hidden="true" />
      </button>

      {/* Popover */}
      {isOpen && (
        <div
          ref={popoverRef}
          className={cn(
            'absolute z-50 w-80 max-w-[calc(100vw-2rem)] p-4',
            'bg-surface rounded border border-rule-strong/60 shadow-pop',
            // Below the trigger: at its right edge on small screens, at its left from sm up
            'top-full right-0 mt-1.5',
            'sm:right-auto sm:left-0'
          )}
          role="dialog"
          aria-labelledby="offense-title"
        >
          {/* Close button */}
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="absolute top-2 right-2 inline-flex h-7 w-7 items-center justify-center rounded text-ink-3 hover:text-ink hover:bg-subtle"
            aria-label="Close"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>

          {/* Content */}
          <div className="relative pr-6">
            {/* Family */}
            <span className="label mb-1 block text-ink-3">
              {offense.family}
            </span>

            {/* Title */}
            <h3
              id="offense-title"
              className="h3 mb-2"
            >
              {offense.display}
            </h3>

            {/* Description */}
            {offense.description ? (
              <p className="text-meta text-ink-2">
                {offense.description}
              </p>
            ) : (
              <p className="text-meta text-ink-3 italic">
                No description available.
              </p>
            )}

            {/* Source */}
            <div className="mt-3 pt-3 border-t border-rule">
              <p className="text-label text-ink-3">
                Source: Clery Act, 34 CFR 668.46
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
