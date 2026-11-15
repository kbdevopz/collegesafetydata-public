import { useState, useEffect, useRef, useMemo, useId } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X, Loader2, GitCompare, Check } from 'lucide-react'
import { fetchSchoolIndex } from '../lib/api'
import type { School } from '../lib/types'
import { cn, displayName, searchText } from '../lib/utils'

// A school prepared for matching: its names as search text
interface Searchable {
  school: School
  title: string
  names: string[] // title, institution name, short name (search text)
  aliases: { text: string; alias: string }[]
  all: string // every searchable word, city and state included
}

interface Match {
  school: School
  alias: string | null // the alias that matched, when no shown name did
  score: number
}

function prepare(school: School): Searchable {
  const title = displayName(school)
  const names = [title, school.name, school.short ?? ''].map(searchText).filter(Boolean)
  const aliases = (school.aliases ?? []).map((alias) => ({ text: searchText(alias), alias }))
  const all = [...names, ...aliases.map((a) => a.text), searchText(school.city), searchText(school.state)].join(' | ')
  return { school, title, names, aliases, all }
}

// Every word of the query must be in the school's search text. Exact name
// matches first, then names that start with the query, then main campuses,
// shorter titles and alphabetical order.
function findSchools(items: Searchable[], query: string, limit: number): Match[] {
  const q = searchText(query)
  if (!q) return []
  const words = q.split(' ')
  const id = /^\d{6,9}$/.test(query.trim()) ? Number(query.trim()) : null
  const matches: (Match & { title: string })[] = []
  for (const item of items) {
    if (id !== null && item.school.unitid === id) {
      matches.push({ school: item.school, alias: null, score: -1, title: item.title })
      continue
    }
    if (!words.every((w) => item.all.includes(w))) continue
    const nameHit = item.names.some((n) => words.every((w) => n.includes(w)))
    const alias = nameHit ? null : item.aliases.find((a) => words.every((w) => a.text.includes(w)))?.alias ?? null
    const texts = [...item.names, ...item.aliases.map((a) => a.text)]
    const score = texts.some((n) => n === q) ? 0 : texts.some((n) => n.startsWith(q)) ? 1 : nameHit || alias ? 2 : 3
    matches.push({ school: item.school, alias, score, title: item.title })
  }
  matches.sort((a, b) =>
    a.score - b.score ||
    Number(a.school.isMainCampus === false) - Number(b.school.isMainCampus === false) ||
    a.title.length - b.title.length ||
    a.title.localeCompare(b.title) ||
    a.school.unitid - b.school.unitid)
  return matches.slice(0, limit)
}

// "Institution · City, ST · 2015–2024"
function detailLine(school: School): string {
  const place = school.city && school.state ? `${school.city}, ${school.state}` : school.city || school.state || ''
  const years = school.years ? (school.years[0] === school.years[1] ? `${school.years[0]}` : `${school.years[0]}–${school.years[1]}`) : ''
  return [school.campus ? school.name : '', place, years].filter(Boolean).join(' · ')
}

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
  // False after Escape closed the list; typing or an arrow key opens it again
  const [listOpen, setListOpen] = useState(true)

  // Combobox (WAI-ARIA combobox pattern): the input keeps focus and points
  // at the highlighted option with aria-activedescendant
  const baseId = useId()
  const listboxId = `${baseId}-listbox`
  const optionId = (index: number) => `${baseId}-option-${index}`

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

  // Escape outside the input (in the input, handleKeyDown handles it): close
  // the list; from a button in the list, focus goes back to the input
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const inside = !!containerRef.current?.contains(e.target as Node)
      if (!isHero) {
        setIsOpen(false)
        setQuery('')
        return
      }
      setListOpen(false)
      if (inside) inputRef.current?.focus()
    }

    if (isOpen || isFocused) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen, isHero, isFocused])

  // Filter schools based on query
  const searchable = useMemo(() => schools.map(prepare), [schools])
  const matches = useMemo(() => findSchools(searchable, query, 8), [searchable, query])
  const filteredSchools = useMemo(() => matches.map((m) => m.school), [matches])

  // Reset selected index when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [filteredSchools.length])

  // Navigate to school profile
  const navigateToSchool = (school: School) => {
    if (!isHero) {
      setIsOpen(false)
    }
    setQuery('')
    navigate(`/school/${school.unitid}`)
  }

  const showResults = !!query.trim() && (isFocused || isOpen) && listOpen
  // The listbox is shown (the input's aria-expanded)
  const expanded = showResults && filteredSchools.length > 0

  const changeQuery = (value: string) => {
    setQuery(value)
    setListOpen(true)
  }

  // Keyboard: arrows move the highlight (and open a closed list), Enter opens
  // the highlighted school, Escape closes the list (a second Escape clears
  // the text; in the header variant, then closes the search)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!listOpen) {
        setListOpen(true)
        return
      }
      if (filteredSchools.length === 0) return
      setSelectedIndex((prev) =>
        e.key === 'ArrowDown' ? Math.min(prev + 1, filteredSchools.length - 1) : Math.max(prev - 1, 0)
      )
    } else if (e.key === 'Enter') {
      if (expanded && filteredSchools[selectedIndex]) {
        e.preventDefault()
        navigateToSchool(filteredSchools[selectedIndex])
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      // Not also the document listener above
      e.stopPropagation()
      if (showResults) setListOpen(false)
      else if (query) setQuery('')
      else if (!isHero) setIsOpen(false)
    }
  }

  // The input's combobox attributes (both variants)
  const comboboxProps = {
    role: 'combobox',
    'aria-expanded': expanded,
    'aria-controls': listboxId,
    'aria-autocomplete': 'list' as const,
    'aria-activedescendant': expanded && filteredSchools[selectedIndex] ? optionId(selectedIndex) : undefined,
    'aria-label': 'Search for a school',
    autoComplete: 'off',
  }

  // An option: the whole row opens the school. Pressing the mouse on it
  // keeps focus in the input.
  const optionProps = (school: School, index: number) => ({
    id: optionId(index),
    role: 'option',
    'aria-selected': index === selectedIndex,
    onClick: () => navigateToSchool(school),
    onMouseDown: (e: React.MouseEvent) => e.preventDefault(),
    onMouseEnter: () => setSelectedIndex(index),
  })

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
            {...comboboxProps}
            value={query}
            onChange={(e) => changeQuery(e.target.value)}
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
                    Try a school or campus name, a former name, an abbreviation, a city, or a state
                  </p>
                )}
              </div>
            ) : (
              // The listbox holds only the options. The compare buttons are
              // in a column of their own beside it (not inside an option,
              // where a button is not allowed), on the same grid rows, so
              // each sits on its school's row.
              <div className="grid grid-cols-[minmax(0,1fr)_auto] py-1">
                <ul
                  id={listboxId}
                  role="listbox"
                  aria-label="Schools"
                  className="col-start-1 grid grid-rows-subgrid"
                  style={{ gridRow: `1 / span ${matches.length}` }}
                >
                  {matches.map(({ school, alias }, index) => (
                    <li
                      key={school.unitid}
                      {...optionProps(school, index)}
                      className={cn(
                        'px-4 py-2.5 cursor-pointer transition-colors',
                        index === selectedIndex
                          ? 'bg-primary-50 dark:bg-primary-900/30'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                      )}
                    >
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {displayName(school)}
                        {school.isMainCampus === false && !school.campus && (
                          <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {detailLine(school)}
                      </div>
                      {alias && (
                        <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">also: {alias}</div>
                      )}
                    </li>
                  ))}
                </ul>
                {onToggleCompare && (
                  <div
                    className="col-start-2 grid grid-rows-subgrid"
                    style={{ gridRow: `1 / span ${matches.length}` }}
                  >
                    {matches.map(({ school }, index) => {
                      const isComparing = compareSchools?.includes(school.unitid)
                      const name = displayName(school)
                      return (
                        <div
                          key={school.unitid}
                          onMouseEnter={() => setSelectedIndex(index)}
                          className={cn(
                            'flex items-center pr-3 transition-colors',
                            index === selectedIndex && 'bg-primary-50 dark:bg-primary-900/30'
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => onToggleCompare(school.unitid, name)}
                            className={cn(
                              'p-1.5 rounded-md transition-colors',
                              isComparing
                                ? 'bg-primary-100 dark:bg-primary-900/50 text-primary-600 dark:text-primary-400'
                                : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                            )}
                            aria-label={isComparing ? `Remove ${name} from comparison` : `Add ${name} to comparison`}
                            title={isComparing ? 'Remove from comparison' : 'Add to comparison'}
                          >
                            {isComparing ? (
                              <Check className="w-4 h-4" />
                            ) : (
                              <GitCompare className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
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
              {...comboboxProps}
              value={query}
              onChange={(e) => changeQuery(e.target.value)}
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
      {isOpen && showResults && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-50 overflow-hidden">
          {filteredSchools.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 text-center">
              {loading ? 'Loading schools...' : 'No schools found'}
            </div>
          ) : (
            <ul id={listboxId} className="py-1" role="listbox" aria-label="Schools">
              {matches.map(({ school, alias }, index) => (
                <li
                  key={school.unitid}
                  {...optionProps(school, index)}
                  className={cn(
                    'px-4 py-3 cursor-pointer transition-colors',
                    index === selectedIndex
                      ? 'bg-primary-50 dark:bg-primary-900/30'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  )}
                >
                  <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                    {displayName(school)}
                    {school.isMainCampus === false && !school.campus && (
                      <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400">(Branch)</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {detailLine(school)}
                  </div>
                  {alias && (
                    <div className="text-xs text-gray-400 dark:text-gray-500">also: {alias}</div>
                  )}
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
