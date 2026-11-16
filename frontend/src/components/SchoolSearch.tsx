import { useState, useEffect, useRef, useMemo, useId } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X, Loader2 } from 'lucide-react'
import { fetchSchoolIndex } from '../lib/api'
import type { School } from '../lib/types'
import { cn, displayName, searchText } from '../lib/utils'
import { CompareButton } from './ui'

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

  // Load the school index (a large file) when it is first needed: when the
  // hero input gets focus or text, or when the header search first opens
  // (once: a failed load is not retried in a loop)
  const indexRequested = useRef(false)
  useEffect(() => {
    const needed = isHero ? isFocused || query !== '' : isOpen
    if (needed && schools.length === 0 && !loading && !indexRequested.current) {
      indexRequested.current = true
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
  }, [isOpen, isHero, isFocused, query, schools.length, loading])

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
        'relative w-full',
        compact ? 'max-w-md' : 'max-w-xl',
        className
      )}>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden="true" />
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
              'control w-full pl-9 pr-10',
              compact ? 'h-9' : 'h-11 text-body'
            )}
          />
          {loading && (
            <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-ink-3" aria-hidden="true" />
          )}
          {query && !loading && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="absolute right-1.5 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded text-ink-3 hover:bg-subtle hover:text-ink"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* Results Dropdown - Hero style */}
        {showResults && (
          <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded border border-rule-strong/60 bg-surface shadow-pop">
            {filteredSchools.length === 0 ? (
              <div className="px-4 py-4">
                <p className="text-meta text-ink-2">
                  {loading ? 'Loading schools...' : 'No schools found'}
                </p>
                {!loading && query.length < 3 && (
                  <p className="text-meta text-ink-3 mt-1">
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
                        'cursor-pointer border-l-2 px-3.5 py-2',
                        index === selectedIndex
                          ? 'border-accent bg-accent-tint'
                          : 'border-transparent hover:bg-subtle'
                      )}
                    >
                      <div className="text-ui font-semibold text-ink">
                        {displayName(school)}
                        {school.isMainCampus === false && !school.campus && (
                          <span className="ml-2 text-meta font-normal text-ink-3">(Branch)</span>
                        )}
                      </div>
                      <div className="text-meta text-ink-3">
                        {detailLine(school)}
                      </div>
                      {alias && (
                        <div className="text-meta text-ink-3">also: {alias}</div>
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
                      const isComparing = !!compareSchools?.includes(school.unitid)
                      const name = displayName(school)
                      return (
                        <div
                          key={school.unitid}
                          onMouseEnter={() => setSelectedIndex(index)}
                          className={cn(
                            'flex items-center pr-2',
                            index === selectedIndex && 'bg-accent-tint'
                          )}
                        >
                          <CompareButton
                            selected={isComparing}
                            name={name}
                            onClick={() => onToggleCompare(school.unitid, name)}
                            withTitle
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {filteredSchools.length > 0 && (
              <div className="border-t border-rule bg-subtle px-3.5 py-1.5">
                <div className="flex items-center justify-between text-label text-ink-3">
                  <span>
                    {filteredSchools.length} result{filteredSchools.length !== 1 && 's'}
                  </span>
                  <span className="hidden sm:flex items-center gap-1">
                    <kbd className="rounded-sm border border-rule px-1 font-sans">↑↓</kbd>
                    <span className="ml-1">navigate</span>
                    <kbd className="ml-2 rounded-sm border border-rule px-1 font-sans">↵</kbd>
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
          className="flex h-9 items-center gap-2 rounded px-3 text-ink-2 hover:bg-subtle hover:text-ink"
          aria-label="Search schools"
        >
          <Search className="w-4 h-4" aria-hidden="true" />
          <span className="hidden lg:inline text-ui">Search schools...</span>
        </button>
      ) : (
        <div className="flex items-center">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-3" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              {...comboboxProps}
              value={query}
              onChange={(e) => changeQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search schools..."
              className="control w-64 sm:w-80 pl-9 pr-10"
            />
            {loading ? (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-3 animate-spin" aria-hidden="true" />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  setQuery('')
                }}
                className="absolute right-1.5 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded text-ink-3 hover:bg-subtle hover:text-ink"
                aria-label="Close search"
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Results Dropdown */}
      {isOpen && showResults && (
        <div className="absolute top-full left-0 right-0 mt-1 z-50 overflow-hidden rounded border border-rule-strong/60 bg-surface shadow-pop">
          {filteredSchools.length === 0 ? (
            <div className="px-4 py-3 text-meta text-ink-2">
              {loading ? 'Loading schools...' : 'No schools found'}
            </div>
          ) : (
            <ul id={listboxId} className="py-1" role="listbox" aria-label="Schools">
              {matches.map(({ school, alias }, index) => (
                <li
                  key={school.unitid}
                  {...optionProps(school, index)}
                  className={cn(
                    'cursor-pointer border-l-2 px-3.5 py-2',
                    index === selectedIndex
                      ? 'border-accent bg-accent-tint'
                      : 'border-transparent hover:bg-subtle'
                  )}
                >
                  <div className="text-ui font-semibold text-ink">
                    {displayName(school)}
                    {school.isMainCampus === false && !school.campus && (
                      <span className="ml-1.5 text-meta font-normal text-ink-3">(Branch)</span>
                    )}
                  </div>
                  <div className="text-meta text-ink-3">
                    {detailLine(school)}
                  </div>
                  {alias && (
                    <div className="text-meta text-ink-3">also: {alias}</div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {filteredSchools.length > 0 && (
            <div className="border-t border-rule bg-subtle px-3.5 py-1.5">
              <div className="flex items-center justify-between text-label text-ink-3">
                <span>
                  {filteredSchools.length} result{filteredSchools.length !== 1 && 's'}
                </span>
                <span className="hidden sm:inline">
                  <kbd className="rounded-sm border border-rule px-1 font-sans">↑</kbd>
                  <kbd className="ml-1 rounded-sm border border-rule px-1 font-sans">↓</kbd>
                  <span className="ml-1">to navigate</span>
                  <kbd className="ml-2 rounded-sm border border-rule px-1 font-sans">↵</kbd>
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
