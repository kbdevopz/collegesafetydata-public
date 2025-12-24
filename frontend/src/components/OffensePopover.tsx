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
          'p-1 rounded-full transition-colors',
          'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
          'dark:text-gray-500 dark:hover:text-gray-300 dark:hover:bg-gray-800',
          isOpen && 'text-primary-600 dark:text-primary-400'
        )}
        aria-label={`More info about ${offense.display}`}
        aria-expanded={isOpen}
      >
        <Info className="w-4 h-4" />
      </button>

      {/* Popover */}
      {isOpen && (
        <div
          ref={popoverRef}
          className={cn(
            'absolute z-50 w-80 p-4',
            'bg-white dark:bg-gray-800',
            'rounded-xl shadow-xl',
            'border border-gray-200 dark:border-gray-700',
            'animate-in fade-in-0 zoom-in-95 duration-150',
            // Position below trigger, centered
            'top-full left-1/2 -translate-x-1/2 mt-2',
            // On small screens, align to left edge
            'sm:left-0 sm:translate-x-0'
          )}
          role="dialog"
          aria-labelledby="offense-title"
        >
          {/* Arrow */}
          <div className="absolute -top-2 left-1/2 -translate-x-1/2 sm:left-4 sm:translate-x-0 w-4 h-4 rotate-45 bg-white dark:bg-gray-800 border-l border-t border-gray-200 dark:border-gray-700" />

          {/* Close button */}
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="absolute top-2 right-2 p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          {/* Content */}
          <div className="relative">
            {/* Family badge */}
            <span className={cn(
              'inline-block px-2 py-0.5 text-xs font-medium rounded-full mb-2',
              offense.family === 'Criminal' && 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
              offense.family === 'VAWA' && 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
              offense.family === 'Arrests' && 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
              offense.family === 'Referrals' && 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
              !['Criminal', 'VAWA', 'Arrests', 'Referrals'].includes(offense.family) && 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
            )}>
              {offense.family}
            </span>

            {/* Title */}
            <h3
              id="offense-title"
              className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2"
            >
              {offense.display}
            </h3>

            {/* Description */}
            {offense.description ? (
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                {offense.description}
              </p>
            ) : (
              <p className="text-sm text-gray-400 dark:text-gray-500 italic">
                No description available.
              </p>
            )}

            {/* Source */}
            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Source: Clery Act, 34 CFR 668.46
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
