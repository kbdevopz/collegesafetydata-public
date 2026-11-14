// Writes the static HTML of every page into dist/ after `vite build`, plus
// sitemap.xml and robots.txt.
//
//   - Fixed-URL pages (STATIC_PAGES in src/lib/seo.ts): rendered with React
//     (src/entry-server.tsx) into dist/<name>.html, served at /<name>.
//   - 404.html: the not-found page; both hosts send it with status 404 for
//     any URL without a file.
//   - School pages, one per data file in dist/data/schools:
//       static  dist/school/<UNITID>.html (any host but Cloudflare Pages)
//       worker  dist/_worker.js + dist/_routes.json: a Cloudflare Pages worker
//               renders the same HTML per request, because one file per school
//               would pass the free plan's 20,000-file limit.
//     SCHOOL_PAGES=static|worker overrides the choice; the default is worker
//     when CF_PAGES is set (Cloudflare Pages builds set it), else static.
import { readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync, existsSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { loadHeaderRules } from './check-headers.mjs'

// React's production build: no development-only warnings in the build log
process.env.NODE_ENV ??= 'production'

const started = Date.now()
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(frontend, 'dist')
const server = await import(pathToFileURL(join(frontend, '.prerender', 'server', 'entry-server.js')).href)
const { render, renderPage, renderSchoolPage, staticPageHead, shellDescription, STATIC_PAGES, NOT_FOUND_HEAD, SITE_ORIGIN } = server

const mode = process.env.SCHOOL_PAGES || (process.env.CF_PAGES ? 'worker' : 'static')
if (mode !== 'static' && mode !== 'worker') throw new Error(`SCHOOL_PAGES must be static or worker, not ${mode}`)

// The template: index.html as Vite built it. Kept in .prerender/ because this
// script overwrites dist/index.html, so a second run uses the saved copy.
const shellCopy = join(frontend, '.prerender', 'shell.html')
const built = readFileSync(join(dist, 'index.html'), 'utf-8')
const fresh = built.includes('<div id="root"></div>')
if (!fresh && !existsSync(shellCopy)) {
  throw new Error('dist/index.html is not a fresh Vite build (its root is not empty); run vite build first')
}
if (fresh) writeFileSync(shellCopy, built)
const shell = fresh ? built : readFileSync(shellCopy, 'utf-8')
const homeDescription = shellDescription(shell)

// 1. Fixed-URL pages
for (const page of STATIC_PAGES) {
  writeFileSync(join(dist, page.file), renderPage(shell, staticPageHead(page, homeDescription), render(page.path)))
}

// 2. Not-found page
writeFileSync(join(dist, '404.html'), renderPage(shell, NOT_FOUND_HEAD, render('/__not_found__')))

// 3. School pages
const schoolsDir = join(dist, 'data', 'schools')
const ids = readdirSync(schoolsDir)
  .filter((f) => /^\d+\.json$/.test(f))
  .map((f) => f.slice(0, -5))
  .sort((a, b) => Number(a) - Number(b))

rmSync(join(dist, 'school'), { recursive: true, force: true })
rmSync(join(dist, '_worker.js'), { force: true })
rmSync(join(dist, '_routes.json'), { force: true })

if (mode === 'static') {
  mkdirSync(join(dist, 'school'))
  for (const id of ids) {
    const profile = JSON.parse(readFileSync(join(schoolsDir, `${id}.json`), 'utf-8'))
    if (String(profile.unitid) !== id) throw new Error(`data/schools/${id}.json has unitid ${profile.unitid}`)
    writeFileSync(join(dist, 'school', `${id}.html`), renderSchoolPage(shell, profile))
  }
} else {
  const workerFile = join(frontend, '.prerender', 'worker', 'worker.js')
  if (!existsSync(workerFile)) throw new Error('no .prerender/worker/worker.js; run vite build --mode worker first')
  const security = Object.fromEntries(loadHeaderRules().get('/*') ?? [])
  let code = readFileSync(workerFile, 'utf-8')
  for (const [placeholder, value] of [
    ['__CSD_SHELL_HTML__', shell],
    ['__CSD_SECURITY_HEADERS__', JSON.stringify(security)],
  ]) {
    const quoted = `"${placeholder}"`
    const quotedSingle = `'${placeholder}'`
    if (code.includes(quoted)) code = code.replace(quoted, () => JSON.stringify(value))
    else if (code.includes(quotedSingle)) code = code.replace(quotedSingle, () => JSON.stringify(value))
    else throw new Error(`worker.js has no ${placeholder}`)
  }
  writeFileSync(join(dist, '_worker.js'), code)
  writeFileSync(join(dist, '_routes.json'), JSON.stringify({ version: 1, include: ['/school/*'], exclude: [] }, null, 2) + '\n')
}

// 4. sitemap.xml and robots.txt (canonical host only)
const metadata = JSON.parse(readFileSync(join(dist, 'data', 'metadata.json'), 'utf-8'))
const lastmod = /^\d{4}-\d{2}-\d{2}/.test(String(metadata.lastUpdated ?? '')) ? String(metadata.lastUpdated).slice(0, 10) : null
const entry = (path, priority) =>
  `  <url><loc>${SITE_ORIGIN}${path}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}<priority>${priority.toFixed(1)}</priority></url>`
const urls = [
  ...STATIC_PAGES.map((p) => entry(p.path, p.priority)),
  ...ids.map((id) => entry(`/school/${id}`, 0.5)),
]
writeFileSync(
  join(dist, 'sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`
)
writeFileSync(join(dist, 'robots.txt'), `User-agent: *\nAllow: /\n\nSitemap: ${SITE_ORIGIN}/sitemap.xml\n`)

const files = (dir) => readdirSync(dir, { withFileTypes: true }).reduce((n, d) => n + (d.isDirectory() ? files(join(dir, d.name)) : 1), 0)
console.log(
  `prerender: ${STATIC_PAGES.length} pages, 404.html, ${ids.length} school pages (${mode}), ` +
    `sitemap with ${urls.length} URLs; dist has ${files(dist)} files; ${((Date.now() - started) / 1000).toFixed(1)}s`
)
