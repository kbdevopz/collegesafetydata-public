/**
 * Build-time renderer (not shipped to browsers): scripts/prerender.mjs calls
 * render() for each fixed-URL page and writes the HTML into dist/.
 */
import React from 'react'
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom'
import { AppRoutes, type PageComponents } from './routes'
import Rankings from './pages/Rankings'
import SchoolProfile from './pages/SchoolProfile'
import Compare from './pages/Compare'
import About from './pages/About'
import Methodology from './pages/Methodology'
import Contact from './pages/Contact'
import Privacy from './pages/Privacy'
import Terms from './pages/Terms'
import Changes from './pages/Changes'
import NotFound from './pages/NotFound'
import { seedMetadata } from './lib/api'
import { buildInfoFromAudit, seedBuildInfo } from './lib/build'
import type { Metadata } from './lib/types'

const pages: PageComponents = {
  rankings: Rankings,
  school: SchoolProfile,
  compare: Compare,
  about: About,
  methodology: Methodology,
  contact: Contact,
  privacy: Privacy,
  terms: Terms,
  changes: Changes,
  notFound: NotFound,
}

/**
 * The page at `url` as HTML. `metadata` (the build's metadata.json) and
 * `audit` (its audit.json) are given to the pages first, so the HTML shows
 * the coverage, dates, counts and build identifier they hold.
 */
export function render(url: string, metadata: Metadata | null = null, audit: unknown = null): string {
  seedMetadata(metadata)
  seedBuildInfo(buildInfoFromAudit(audit))
  return renderToString(
    <React.StrictMode>
      <StaticRouter location={url}>
        <AppRoutes pages={pages} />
      </StaticRouter>
    </React.StrictMode>
  )
}

export * from './lib/seo'
