import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X, Loader2, GitCompare, Check } from 'lucide-react'
import { fetchSchoolIndex } from '../lib/api'
import type { School } from '../lib/types'
import { cn } from '../lib/utils'

interface SchoolSearchProps {
  className?: string
  variant?: 'header' | 'hero'
  // Compare functionality (only used by hero variant on Rankings page)
  compareSchools?: number[]
  onToggleCompare?: (unitid: number, name: string) => void
  // Compact mode for sticky filter bar
  compact?: boolean
}

export default function SchoolSearch({ className, variant = 'header', compareSchools, onToggleCompare, compact = false }: SchoolSearchProps) {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // For header variant, we track open/closed state
  // For hero variant, it's always "open" (visible input)
  const [isOpen, setIsOpen] = useState(variant === 'hero')
  const [query, setQuery] = useState('')
  const [schools, setSchools] = useState<School[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [isFocused, setIsFocused] = useState(false)

  const isHero = variant === 'hero'

  // Load school index on mount for hero, or first open for header
  useEffect(() => {
    const shouldLoad = isHero ? schools.length === 0 : isOpen && schools.length === 0
    if (shouldLoad && !loading) {
      setLoading(true)
      fetchSchoolIndex()
        .then((index) => {
          setSchools(index.schools)
          setLoading(false)
        })
        .catch(() => {
          setLoading(false)
        })
    }
  }, [isOpen, isHero, schools.length, loading])

  // Focus input when opened (header variant only)
  useEffect(() => {
    if (isOpen && inputRef.current && !isHero) {
      inputRef.current.focus()
    }
  }, [isOpen, isHero])

  // Close on click outside (only for header variant or when showing results)
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        if (!isHero) {
          setIsOpen(false)
        }
        setQuery('')
        setIsFocused(false)
      }
    }

    if (isOpen || isFocused) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen, isHero, isFocused])

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (!isHero) {
          setIsOpen(false)
        }
        setQuery('')
        inputRef.current?.blur()
      }
    }

    if (isOpen || isFocused) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen, isHero, isFocused])

  // Filter schools based on query
  const filteredSchools = useMemo(() => {
    if (!query.trim()) return []

    const q = query.toLowerCase()
    return schools
      .filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          (s.city && s.city.toLowerCase().includes(q)) ||
          (s.state && s.state.toLowerCase().includes(q))
      )
      .slice(0, 8) // Limit results
  }, [schools, query])

  // Reset selected index when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [filteredSchools.length])

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => Math.min(prev + 1, filteredSchools.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && filteredSchools[selectedIndex]) {
      e.preventDefault()
      navigateToSchool(filteredSchools[selectedIndex])
    }
  }

  // Navigate to school profile
  const navigateToSchool = (school: School) => {
    if (!isHero) {
      setIsOpen(false)
    }
    setQuery('')
    navigate(`/school/${school.unitid}`)
  }

  const showResults = query.trim() && (isFocused || isOpen)

  // Hero variant - always visible large input
  if (isHero) {
    return (
      <div ref={containerRef} className={cn(
        'relative w-full mx-auto',
        compact ? 'max-w-md' : 'max-w-lg',
        className
      )}>
        <div className="relative">
          <Search className={cn(
            'absolute top-1/2 -translate-y-1/2 text-gray-400',
            compact ? 'left-3 w-4 h-4' : 'left-4 w-4 h-4 sm:w-5 sm:h-5'
          )} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setTimeout(() => setIsFocused(false), 150)}
            placeholder="Search for any school..."
            className={cn(
              'w-full',
              compact
                ? 'pl-10 pr-10 py-2.5 text-sm rounded-lg shadow-sm border'
                : 'pl-11 pr-11 py-3 text-sm sm:text-base rounded-xl shadow-md border',
              'bg-white dark:bg-gray-800',
              'border-gray-200 dark:border-gray-700',
              'text-gray-900 dark:text-gray-100',
              'placeholder-gray-400 dark:placeholder-gray-500',
              compact
                ? 'focus:outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900/30'
                : 'focus:outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900/30',
              'transition-all duration-200'
            )}
          />
          {loading && (
            <Loader2 className={cn(
              'absolute top-1/2 -translate-y-1/2 text-gray-400 animate-spin',
              compact ? 'right-3 w-4 h-4' : 'right-4 w-4 h-4'
            )} />
          )}
          {query && !loading && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className={cn(
                'absolute top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors',
                compact ? 'right-2' : 'right-3'
              )}
              aria-label="Clear search"
            >
              <X className={compact ? 'w-4 h-4' : 'w-4 h-4'} />
            </button>
          )}
        </div>

        {/* Results Dropdown - Hero style */}
        {showResults && (
          <div className={cn(
            'absolute top-full left-0 right-0 mt-2',
            'bg-white dark:bg-gray-800',
            'rounded-lg shadow-lg',
            'border border-gray-200 dark:border-gray-700',
            'z-50 overflow-hidden',
            'animate-in fade-in-0 slide-in-from-top-2 duration-150'
          )}>
            {filteredSchools.length === 0 ? (
              <div className="px-4 py-4 text-center">
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {loading ? 'Loading schools...' : 'No schools found'}
                </p>
                {!loading && query.length < 3 && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Try searching by school name, city, or state
                  </p>
                )}
              </div>
            ) : (
              <ul className="py-1" role="listbox">
                {filteredSchools.map((school, index) => {
                  const isComparing = compareSchools?.includes(school.unitid)
                  return (
                    <li
                      key={school.unitid}
                      role="option"
                      aria-selected={index === selectedIndex}
                      className={cn(
                        'flex items-center transition-colors',
                        index === selectedIndex
                          ? 'bg-primary-50 dark:bg-primary-900/30'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => navigateToSchool(school)}
                        onMouseEnter={() => setSelectedIndex(index)}
                        className="flex-1 text-left px-4 py-2.5"
                      >
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {school.name}
                          {school.isMainCampus === false && (
                            <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {school.city && school.state
                            ? `${school.city}, ${school.state}`
                            : school.state || ''}
                        </div>
                      </button>
                      {onToggleCompare && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            onToggleCompare(school.unitid, school.name)
                          }}
                          className={cn(
                            'mr-3 p-1.5 rounded-md transition-colors',
                            isComparing
                              ? 'bg-primary-100 dark:bg-primary-900/50 text-primary-600 dark:text-primary-400'
                              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                          )}
                          title={isComparing ? 'Remove from compare' : 'Add to compare'}
                        >
                          {isComparing ? (
                            <Check className="w-4 h-4" />
                          ) : (
                            <GitCompare className="w-4 h-4" />
                          )}
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}

            {filteredSchools.length > 0 && (
              <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-700">
                <div className="flex items-center justify-between text-xs text-gray-400 dark:text-gray-500">
                  <span>
                    {filteredSchools.length} result{filteredSchools.length !== 1 && 's'}
                  </span>
                  <span className="hidden sm:flex items-center gap-1">
                    <kbd className="px-1 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-[10px] font-mono">↑↓</kbd>
                    <span className="ml-1">navigate</span>
                    <kbd className="px-1 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-[10px] font-mono ml-2">↵</kbd>
                    <span className="ml-1">select</span>
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // Header variant - compact, button that expands to input
  return (
    <div ref={containerRef} className={cn('relative', className)}>
      {/* Search Button / Input */}
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Search schools"
        >
          <Search className="w-5 h-5" />
          <span className="hidden lg:inline text-sm">Search schools...</span>
        </button>
      ) : (
        <div className="flex items-center">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search schools..."
              className="w-64 sm:w-80 pl-10 pr-10 py-2 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
            {loading ? (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  setQuery('')
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                aria-label="Close search"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Results Dropdown */}
      {isOpen && query.trim() && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50 overflow-hidden">
          {filteredSchools.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 text-center">
              {loading ? 'Loading schools...' : 'No schools found'}
            </div>
          ) : (
            <ul className="py-1" role="listbox">
              {filteredSchools.map((school, index) => (
                <li key={school.unitid} role="option" aria-selected={index === selectedIndex}>
                  <button
                    type="button"
                    onClick={() => navigateToSchool(school)}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cn(
                      'w-full text-left px-4 py-3 transition-colors',
                      index === selectedIndex
                        ? 'bg-primary-50 dark:bg-primary-900/30'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                    )}
                  >
                    <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                      {school.name}
                      {school.isMainCampus === false && (
                        <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {school.city && school.state
                        ? `${school.city}, ${school.state}`
                        : school.state || ''}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {filteredSchools.length > 0 && (
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-100 dark:border-gray-800">
              <div className="flex items-center justify-between text-xs text-gray-400 dark:text-gray-500">
                <span>
                  {filteredSchools.length} result{filteredSchools.length !== 1 && 's'}
                </span>
                <span className="hidden sm:inline">
                  <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-[10px]">↑</kbd>
                  <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-[10px] ml-1">↓</kbd>
                  <span className="ml-1">to navigate</span>
                  <kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-[10px] ml-2">↵</kbd>
                  <span className="ml-1">to select</span>
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
