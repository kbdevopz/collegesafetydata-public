/**
 * API layer for fetching static JSON data
 */

import type {
  Metadata,
  Presets,
  RankingsData,
  SchoolProfile,
  SchoolIndex,
  ApiResult,
} from './types'

const BASE_URL = '/data'

// =============================================================================
// Fetch Utilities
// =============================================================================

async function fetchJson<T>(path: string): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${BASE_URL}${path}`)

    if (!response.ok) {
      return {
        success: false,
        error: {
          message: `Failed to fetch ${path}`,
          status: response.status,
        },
      }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    return {
      success: false,
      error: {
        message: error instanceof Error ? error.message : 'Unknown error',
      },
    }
  }
}

// =============================================================================
// Metadata
// =============================================================================

let metadataCache: Metadata | null = null

export async function fetchMetadata(): Promise<Metadata> {
  if (metadataCache) {
    return metadataCache
  }

  const result = await fetchJson<Metadata>('/metadata.json')

  if (!result.success) {
    throw new Error(result.error.message)
  }

  metadataCache = result.data
  return result.data
}

export async function getMetadata(): Promise<Metadata> {
  return fetchMetadata()
}

// =============================================================================
// Presets
// =============================================================================

let presetsCache: Presets | null = null

export async function fetchPresets(): Promise<Presets> {
  if (presetsCache) {
    return presetsCache
  }

  const result = await fetchJson<Presets>('/presets.json')

  if (!result.success) {
    throw new Error(result.error.message)
  }

  presetsCache = result.data
  return result.data
}

// =============================================================================
// Rankings
// =============================================================================

const rankingsCache = new Map<string, RankingsData>()

export async function fetchRankings(
  preset: string,
  year: number
): Promise<RankingsData> {
  const cacheKey = `${preset}-${year}`

  if (rankingsCache.has(cacheKey)) {
    return rankingsCache.get(cacheKey)!
  }

  const result = await fetchJson<RankingsData>(
    `/rankings/${preset}-${year}-all.json`
  )

  if (!result.success) {
    throw new Error(result.error.message)
  }

  rankingsCache.set(cacheKey, result.data)
  return result.data
}

// =============================================================================
// School Profiles
// =============================================================================

const schoolCache = new Map<number, SchoolProfile>()

export async function fetchSchoolProfile(
  unitid: number
): Promise<SchoolProfile> {
  if (schoolCache.has(unitid)) {
    return schoolCache.get(unitid)!
  }

  const result = await fetchJson<SchoolProfile>(`/schools/${unitid}.json`)

  if (!result.success) {
    throw new Error(result.error.message)
  }

  schoolCache.set(unitid, result.data)
  return result.data
}

// =============================================================================
// School Index (Search)
// =============================================================================

let schoolIndexCache: SchoolIndex | null = null

export async function fetchSchoolIndex(): Promise<SchoolIndex> {
  if (schoolIndexCache) {
    return schoolIndexCache
  }

  const result = await fetchJson<SchoolIndex>('/school-index.json')

  if (!result.success) {
    throw new Error(result.error.message)
  }

  schoolIndexCache = result.data
  return result.data
}

// =============================================================================
// Batch Operations
// =============================================================================

export async function prefetchRankings(
  preset: string,
  years: number[]
): Promise<void> {
  await Promise.all(
    years.map((year) => fetchRankings(preset, year))
  )
}

export async function prefetchSchools(unitids: number[]): Promise<void> {
  await Promise.all(
    unitids.map((unitid) => fetchSchoolProfile(unitid))
  )
}

// =============================================================================
// Cache Management
// =============================================================================

export function clearCache(): void {
  metadataCache = null
  presetsCache = null
  rankingsCache.clear()
  schoolCache.clear()
  schoolIndexCache = null
}

export function getCacheStats(): {
  metadata: boolean
  presets: boolean
  rankings: number
  schools: number
} {
  return {
    metadata: metadataCache !== null,
    presets: presetsCache !== null,
    rankings: rankingsCache.size,
    schools: schoolCache.size,
  }
}
