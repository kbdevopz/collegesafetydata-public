import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { fetchSchoolProfile } from '../lib/api'
import { NOT_FOUND_HEAD, SITE_ORIGIN, STATIC_PAGES, schoolHead, staticPageHead, type Head } from '../lib/seo'

// The description index.html was built with, for pages that keep it
const initialDescription =
  typeof document !== 'undefined'
    ? document.querySelector('meta[name="description"]')?.getAttribute('content') ?? ''
    : ''

function setMeta(selector: string, attr: 'name' | 'property', key: string, content: string | null) {
  let el = document.head.querySelector<HTMLMetaElement>(selector)
  if (content === null) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function applyHead(head: Head) {
  document.title = head.title
  const url = head.path ? SITE_ORIGIN + head.path : null
  setMeta('meta[name="description"]', 'name', 'description', head.description)
  setMeta('meta[property="og:title"]', 'property', 'og:title', head.title)
  setMeta('meta[property="og:description"]', 'property', 'og:description', head.description)
  setMeta('meta[property="og:url"]', 'property', 'og:url', url)
  setMeta('meta[name="robots"]', 'name', 'robots', head.noindex ? 'noindex' : null)
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!url) {
    link?.remove()
  } else {
    if (!link) {
      link = document.createElement('link')
      link.rel = 'canonical'
      document.head.appendChild(link)
    }
    link.href = url
  }
}

/** Keeps the document title, description and canonical URL in step with the route. */
export default function RouteHead() {
  const { pathname } = useLocation()

  useEffect(() => {
    const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
    const page = STATIC_PAGES.find((p) => p.path === path)
    if (page) {
      applyHead(staticPageHead(page, initialDescription))
      return
    }
    const school = path.match(/^\/school\/(\d+)$/)
    if (!school) {
      applyHead(NOT_FOUND_HEAD)
      return
    }
    let current = true
    fetchSchoolProfile(Number(school[1]))
      .then((profile) => {
        if (current) applyHead(schoolHead(profile))
      })
      .catch(() => {
        if (current) applyHead(NOT_FOUND_HEAD)
      })
    return () => {
      current = false
    }
  }, [pathname])

  return null
}
