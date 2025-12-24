/**
 * Utility functions for the Clery Dashboard
 */

import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { TrendPoint, ChartDataPoint, Offense } from './types'

// =============================================================================
// Class Name Utilities
// =============================================================================

/**
 * Merge Tailwind CSS classes with clsx
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

// =============================================================================
// Number Formatting
// =============================================================================

/**
 * Format a number with thousand separators
 */
export function formatNumber(n: number): string {
  return n.toLocaleString()
}

/**
 * Format a number as a percentage
 */
export function formatPercent(value: number, decimals: number = 1): string {
  return `${value.toFixed(decimals)}%`
}

/**
 * Format a number with + sign if positive
 */
export function formatChange(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value)}`
}

/**
 * Format a percentage change
 */
export function formatPercentChange(value: number, decimals: number = 1): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

// =============================================================================
// String Utilities
// =============================================================================

/**
 * Convert offense code to display name
 */
export function offenseCodeToDisplay(code: string): string {
  return code
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Convert display name to offense code
 */
export function offenseDisplayToCode(display: string): string {
  return display.toLowerCase().replace(/\s+/g, '_')
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 3) + '...'
}

// =============================================================================
// Data Transformation
// =============================================================================

/**
 * Transform trend data for Recharts
 */
export function transformTrendsForChart(
  trends: TrendPoint[],
  offenses: string[]
): ChartDataPoint[] {
  // Group by year
  const byYear = new Map<number, ChartDataPoint>()

  for (const point of trends) {
    if (!offenses.includes(point.offense)) continue

    if (!byYear.has(point.year)) {
      byYear.set(point.year, { year: point.year })
    }

    const yearData = byYear.get(point.year)!
    yearData[point.offense] = point.count
  }

  // Convert to array and sort by year
  return Array.from(byYear.values()).sort((a, b) => a.year - b.year)
}

/**
 * Get top N offenses by total count from trends
 */
export function getTopOffenses(
  trends: TrendPoint[],
  n: number = 3
): string[] {
  const totals = new Map<string, number>()

  for (const point of trends) {
    const current = totals.get(point.offense) || 0
    totals.set(point.offense, current + point.count)
  }

  return Array.from(totals.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([offense]) => offense)
}

/**
 * Calculate year-over-year change
 */
export function calculateYoYChange(
  current: number,
  previous: number
): { absolute: number; percent: number | null } {
  const absolute = current - previous
  const percent = previous !== 0 ? ((current - previous) / previous) * 100 : null
  return { absolute, percent }
}

/**
 * Check if rate is based on small sample size
 * Returns true if FTE < 1000 or incidents < 10
 */
export function isSmallSample(fte: number | null, incidents: number): boolean {
  return (fte !== null && fte < 1000) || incidents < 10
}

// =============================================================================
// Offense Utilities
// =============================================================================

/**
 * Group offenses by family
 */
export function groupOffensesByFamily(
  offenses: Offense[]
): Map<string, Offense[]> {
  const groups = new Map<string, Offense[]>()

  for (const offense of offenses) {
    const family = offense.familyDisplay || offense.family
    if (!groups.has(family)) {
      groups.set(family, [])
    }
    groups.get(family)!.push(offense)
  }

  return groups
}

/**
 * Get offense families in order
 */
export function getOffenseFamilyOrder(): string[] {
  return [
    'Criminal Offenses',
    'VAWA Offenses',
    'Arrests',
    'Disciplinary Actions',
  ]
}

// =============================================================================
// Color Utilities
// =============================================================================

const CHART_COLORS = [
  '#3b82f6', // blue-500
  '#ef4444', // red-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#06b6d4', // cyan-500
  '#84cc16', // lime-500
]

/**
 * Get color for chart series
 */
export function getChartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

/**
 * Get all chart colors
 */
export function getChartColors(): string[] {
  return [...CHART_COLORS]
}

// =============================================================================
// Sorting Utilities
// =============================================================================

/**
 * Sort rankings by a specific key
 */
export function sortBy<T>(
  items: T[],
  key: keyof T,
  direction: 'asc' | 'desc' = 'asc'
): T[] {
  return [...items].sort((a, b) => {
    const aVal = a[key]
    const bVal = b[key]

    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return direction === 'asc' ? aVal - bVal : bVal - aVal
    }

    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return direction === 'asc'
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal)
    }

    return 0
  })
}

// =============================================================================
// URL Utilities
// =============================================================================

/**
 * Build school profile URL
 */
export function getSchoolUrl(unitid: number): string {
  return `/school/${unitid}`
}

/**
 * Build rankings URL with filters
 */
export function getRankingsUrl(params?: {
  year?: number
  offense?: string
}): string {
  const searchParams = new URLSearchParams()

  if (params?.year) {
    searchParams.set('year', params.year.toString())
  }
  if (params?.offense) {
    searchParams.set('offense', params.offense)
  }

  const query = searchParams.toString()
  return query ? `/?${query}` : '/'
}

// =============================================================================
// Date Utilities
// =============================================================================

/**
 * Format ISO date string for display
 */
export function formatDate(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

/**
 * Get relative time (e.g., "2 days ago")
 */
export function getRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'today'
  if (diffDays === 1) return 'yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
  return `${Math.floor(diffDays / 365)} years ago`
}
