import React, { lazy, type ComponentType } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes, pageFor, pageLoaders, type PageComponents, type PageKey } from './routes'
import './index.css'

// Each page is its own chunk, loaded when first shown. A page whose chunk has
// already loaded renders directly, so the first page (loaded before the app
// renders, below) never shows an empty Suspense fallback over the prerendered
// HTML.
type PageModule = { default: ComponentType }

function loadablePage(load: () => Promise<PageModule>) {
  let loaded: PageModule | null = null
  const preload = () =>
    load().then((m) => {
      loaded = m
      return m
    })
  // A loaded module is handed to lazy() through a thenable that resolves
  // synchronously, which React renders at once instead of suspending.
  const Lazy = lazy(() =>
    loaded
      ? ({ then: (resolve: (m: PageModule) => void) => resolve(loaded!) } as unknown as Promise<PageModule>)
      : preload()
  )
  function Page() {
    return (
      <React.Suspense fallback={<div className="min-h-[60vh]" />}>
        <Lazy />
      </React.Suspense>
    )
  }
  return { Page, preload }
}

const loadable = Object.fromEntries(
  Object.entries(pageLoaders).map(([key, load]) => [key, loadablePage(load)])
) as unknown as Record<PageKey, ReturnType<typeof loadablePage>>

const pages = Object.fromEntries(
  Object.entries(loadable).map(([key, { Page }]) => [key, Page])
) as unknown as PageComponents

function render() {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter>
        <AppRoutes pages={pages} />
      </BrowserRouter>
    </React.StrictMode>
  )
}

loadable[pageFor(window.location.pathname)].preload().then(render, render)
