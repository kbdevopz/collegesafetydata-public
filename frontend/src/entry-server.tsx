/**
 * Build-time renderer (not shipped to browsers): scripts/prerender.mjs calls
 * render() for each fixed-URL page and writes the HTML into dist/.
 */
import React from 'react'
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import { AppRoutes, type PageComponents } from './routes'
import Rankings from './pages/Rankings'
import SchoolProfile from './pages/SchoolProfile'
import Compare from './pages/Compare'
import About from './pages/About'
import Methodology from './pages/Methodology'
import Contact from './pages/Contact'
import Privacy from './pages/Privacy'
import Terms from './pages/Terms'
import NotFound from './pages/NotFound'

const pages: PageComponents = {
  rankings: Rankings,
  school: SchoolProfile,
  compare: Compare,
  about: About,
  methodology: Methodology,
  contact: Contact,
  privacy: Privacy,
  terms: Terms,
  notFound: NotFound,
}

export function render(url: string): string {
  return renderToString(
    <React.StrictMode>
      <StaticRouter location={url}>
        <AppRoutes pages={pages} />
      </StaticRouter>
    </React.StrictMode>
  )
}

export * from './lib/seo'
