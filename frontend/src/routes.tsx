/**
 * The site's routes, shared by the browser (src/main.tsx, pages loaded on
 * demand) and the build's prerender (src/entry-server.tsx, pages imported
 * directly). A route with a fixed URL must also be listed in STATIC_PAGES
 * (src/lib/seo.ts) so the build writes its HTML file; otherwise the hosts
 * answer it with 404.
 */
import type { ComponentType } from 'react'
import { Routes, Route, matchPath } from 'react-router-dom'
import App from './App'
import RouteHead from './components/RouteHead'

export const pageLoaders = {
  rankings: () => import('./pages/Rankings'),
  school: () => import('./pages/SchoolProfile'),
  compare: () => import('./pages/Compare'),
  about: () => import('./pages/About'),
  methodology: () => import('./pages/Methodology'),
  contact: () => import('./pages/Contact'),
  privacy: () => import('./pages/Privacy'),
  terms: () => import('./pages/Terms'),
  changes: () => import('./pages/Changes'),
  notFound: () => import('./pages/NotFound'),
}

export type PageKey = keyof typeof pageLoaders
export type PageComponents = Record<PageKey, ComponentType>

const PATHS: [string, PageKey][] = [
  ['/', 'rankings'],
  ['/school/:unitid', 'school'],
  ['/compare', 'compare'],
  ['/about', 'about'],
  ['/methodology', 'methodology'],
  ['/contact', 'contact'],
  ['/privacy', 'privacy'],
  ['/terms', 'terms'],
  ['/changes', 'changes'],
]

/** The page a URL path shows (notFound when no route matches). */
export function pageFor(pathname: string): PageKey {
  for (const [path, key] of PATHS) {
    if (matchPath({ path, end: true }, pathname)) return key
  }
  return 'notFound'
}

export function AppRoutes({ pages }: { pages: PageComponents }) {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <>
            <RouteHead />
            <App />
          </>
        }
      >
        {PATHS.map(([path, key]) => {
          const Page = pages[key]
          return path === '/' ? (
            <Route key={key} index element={<Page />} />
          ) : (
            <Route key={key} path={path.slice(1)} element={<Page />} />
          )
        })}
        <Route path="*" element={<pages.notFound />} />
      </Route>
    </Routes>
  )
}
