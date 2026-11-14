/**
 * Page titles, descriptions and canonical URLs, and the static HTML that the
 * build writes for each page so search engines and citation tools see the
 * page's subject and key figures without running JavaScript.
 *
 * No React here: the build (scripts/prerender.mjs), the Cloudflare worker
 * (src/edge/worker.ts) and the browser (src/components/RouteHead.tsx) all use
 * this module.
 */

import type { SchoolProfile } from './types'
import { formatYearRanges } from './enrollment'

export const SITE_NAME = 'CollegeSafetyData.org'
// Canonical host for every page (collegesafetydata.com serves the same site).
export const SITE_ORIGIN = 'https://collegesafetydata.org'
export const DOE_SOURCE_NAME = 'U.S. Department of Education, Campus Safety and Security'
export const DOE_SOURCE_URL = 'https://ope.ed.gov/campussafety/'

export interface Head {
  title: string
  description: string
  // Path of the canonical URL ('' for pages that have none, such as 404)
  path: string
  noindex?: boolean
}

export interface StaticPage {
  path: string
  // Output file in dist/ ("about.html" is served at /about on both hosts)
  file: string
  title: string
  // null: keep the description index.html already has (built from the data)
  description: string | null
  // Sitemap priority
  priority: number
}

// Every route with a fixed URL. A route added to src/routes.tsx must be added
// here too: the build writes an HTML file for each entry and lists it in
// sitemap.xml, and a URL without a file is answered with 404.
export const STATIC_PAGES: StaticPage[] = [
  {
    path: '/',
    file: 'index.html',
    title: `${SITE_NAME} - Campus Crime Statistics`,
    description: null,
    priority: 1.0,
  },
  {
    path: '/compare',
    file: 'compare.html',
    title: `Compare Campuses - ${SITE_NAME}`,
    description:
      'Compare Clery Act crime, arrest and disciplinary referral counts reported by U.S. college campuses, side by side by year and category.',
    priority: 0.6,
  },
  {
    path: '/about',
    file: 'about.html',
    title: `About - ${SITE_NAME}`,
    description:
      'What CollegeSafetyData.org shows, where its data comes from, and the limits of Clery Act statistics.',
    priority: 0.7,
  },
  {
    path: '/methodology',
    file: 'methodology.html',
    title: `Methodology - ${SITE_NAME}`,
    description:
      'How CollegeSafetyData.org builds its figures from U.S. Department of Education Clery Act data and NCES IPEDS enrollment data.',
    priority: 0.8,
  },
  {
    path: '/contact',
    file: 'contact.html',
    title: `Contact - ${SITE_NAME}`,
    description: 'How to contact CollegeSafetyData.org or report a problem with the data.',
    priority: 0.3,
  },
  {
    path: '/privacy',
    file: 'privacy.html',
    title: `Privacy Policy - ${SITE_NAME}`,
    description: 'The CollegeSafetyData.org privacy policy.',
    priority: 0.2,
  },
  {
    path: '/terms',
    file: 'terms.html',
    title: `Terms of Use - ${SITE_NAME}`,
    description: 'The CollegeSafetyData.org terms of use.',
    priority: 0.2,
  },
  {
    path: '/changes',
    file: 'changes.html',
    title: `Changes and Corrections - ${SITE_NAME}`,
    description:
      'Corrections to the figures CollegeSafetyData.org shows and changes to how it counts, ranks and rates them, newest first.',
    priority: 0.5,
  },
]

export const NOT_FOUND_HEAD: Head = {
  title: `Page not found - ${SITE_NAME}`,
  description: 'There is no page at this address.',
  path: '',
  noindex: true,
}

export function schoolPath(unitid: number): string {
  return `/school/${unitid}`
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatCount(n: number): string {
  return n.toLocaleString('en-US')
}

function place(profile: Pick<SchoolProfile, 'city' | 'state'>): string {
  return [profile.city, profile.state].filter(Boolean).join(', ')
}

function reportedYears(profile: SchoolProfile): number[] {
  return profile.yearlyTotals.map((y) => y.year).sort((a, b) => a - b)
}

export function schoolHead(profile: SchoolProfile): Head {
  const where = place(profile)
  const years = reportedYears(profile)
  const { latestYear, totalIncidents } = profile.summary
  const description =
    `Clery Act statistics for ${profile.name}${where ? ` (${where})` : ''}: ` +
    `${formatCount(totalIncidents)} crimes, arrests and disciplinary referrals reported for ${latestYear}` +
    (years.length ? `; yearly figures for ${formatYearRanges(years)}` : '') +
    `. Source: ${DOE_SOURCE_NAME}.`
  return {
    title: `${profile.name}${where ? `, ${where}` : ''} - Campus Crime Statistics - ${SITE_NAME}`,
    description,
    path: schoolPath(profile.unitid),
  }
}

export function staticPageHead(page: StaticPage, fallbackDescription: string): Head {
  return { title: page.title, description: page.description ?? fallbackDescription, path: page.path }
}

/**
 * The school page's key figures as plain HTML: the yearly totals and the
 * latest year's categories, the same numbers the page shows.
 */
export function schoolBodyHtml(profile: SchoolProfile): string {
  const e = escapeHtml
  const where = place(profile)
  const { latestYear, totalIncidents } = profile.summary
  const notReported = new Set(profile.notReported ?? [])
  const totals = new Map(profile.yearlyTotals.map((y) => [y.year, y.total]))
  const allYears = Array.from(new Set([...totals.keys(), ...notReported])).sort((a, b) => b - a)

  const yearRows = allYears
    .map((year) => {
      const cell = totals.has(year) ? formatCount(totals.get(year)!) : 'Not reported'
      return `<tr><td class="pr-6 py-1">${year}</td><td class="py-1 text-right">${cell}</td></tr>`
    })
    .join('')

  const latest = profile.trends
    .filter((t) => t.year === latestYear && t.count > 0)
    .sort((a, b) => b.count - a.count || a.offense.localeCompare(b.offense))
  const categoryRows = latest
    .map((t) => `<tr><td class="pr-6 py-1">${e(t.offense)}</td><td class="py-1 text-right">${formatCount(t.count)}</td></tr>`)
    .join('')

  return (
    `<main class="container mx-auto px-4 sm:px-6 lg:px-8 py-8 text-gray-900 dark:text-gray-100">` +
    `<h1 class="text-3xl font-bold mb-2">${e(profile.name)}</h1>` +
    (where ? `<p class="text-gray-600 dark:text-gray-400 mb-6">${e(where)}</p>` : '') +
    `<p class="mb-6">${formatCount(totalIncidents)} crimes, arrests and disciplinary referrals reported for ${latestYear} ` +
    `(on campus, noncampus and public property).</p>` +
    `<h2 class="text-xl font-semibold mb-2">Reported each year</h2>` +
    `<table class="mb-6"><thead><tr><th class="pr-6 text-left">Year</th><th class="text-right">All categories</th></tr></thead>` +
    `<tbody>${yearRows}</tbody></table>` +
    (categoryRows
      ? `<h2 class="text-xl font-semibold mb-2">${latestYear} by category</h2>` +
        `<table class="mb-6"><thead><tr><th class="pr-6 text-left">Category</th><th class="text-right">Count</th></tr></thead>` +
        `<tbody>${categoryRows}</tbody></table>`
      : '') +
    `<p class="text-sm text-gray-600 dark:text-gray-400">Source: ${e(DOE_SOURCE_NAME)}, ` +
    `<a class="underline" href="${DOE_SOURCE_URL}">${DOE_SOURCE_URL}</a>. ` +
    `Reported incidents only; lower numbers may reflect reporting differences, not greater safety.</p>` +
    `</main>`
  )
}

const ROOT_EMPTY = '<div id="root"></div>'

/**
 * Put a page's head tags and static body into the built index.html (the
 * shell). Throws when the shell is not an unmodified Vite build, so a broken
 * template cannot ship pages without content silently.
 */
export function renderPage(shell: string, head: Head, bodyHtml: string): string {
  if (!shell.includes(ROOT_EMPTY)) throw new Error('shell has no empty <div id="root"></div>')
  if (!/<title>[^<]*<\/title>/.test(shell)) throw new Error('shell has no <title>')
  if (!/<meta name="description" content="[^"]*"\s*\/?>/.test(shell)) throw new Error('shell has no meta description')
  const e = escapeHtml
  const url = head.path ? SITE_ORIGIN + head.path : ''
  const tags = [
    url ? `<link rel="canonical" href="${e(url)}" />` : '',
    head.noindex ? '<meta name="robots" content="noindex" />' : '',
    `<meta property="og:site_name" content="${SITE_NAME}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:title" content="${e(head.title)}" />`,
    `<meta property="og:description" content="${e(head.description)}" />`,
    url ? `<meta property="og:url" content="${e(url)}" />` : '',
    `<meta name="twitter:card" content="summary" />`,
  ]
    .filter(Boolean)
    .map((t) => `    ${t}\n`)
    .join('')
  return shell
    .replace(/<title>[^<]*<\/title>/, () => `<title>${e(head.title)}</title>`)
    .replace(/<meta name="description" content="[^"]*"\s*\/?>/, () => `<meta name="description" content="${e(head.description)}" />`)
    .replace('</head>', () => `${tags}  </head>`)
    .replace(ROOT_EMPTY, () => `<div id="root">${bodyHtml}</div>`)
}

/** The description index.html was built with (data-driven, see vite.config.ts). */
export function shellDescription(shell: string): string {
  const m = shell.match(/<meta name="description" content="([^"]*)"/)
  return m ? m[1].replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&') : ''
}

export function renderSchoolPage(shell: string, profile: SchoolProfile): string {
  return renderPage(shell, schoolHead(profile), schoolBodyHtml(profile))
}
