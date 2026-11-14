/**
 * Cloudflare Pages worker for /school/<UNITID> (dist/_worker.js; dist/_routes.json
 * sends only /school/* here, everything else is served as static files).
 *
 * Cloudflare Pages allows 20,000 files per deployment on the free plan and
 * the site data alone is about 14,600, so the build cannot write one HTML file
 * per school there as it does for other hosts. This worker returns the same
 * HTML the build would have written (src/lib/seo.ts, same template), built
 * from the school's data file, and 404 for a UNITID without one.
 *
 * Cloudflare does not apply public/_headers to worker responses; the build
 * puts the headers of its "/*" rule into SECURITY_HEADERS.
 */
import type { SchoolProfile } from '../lib/types'
import { renderSchoolPage } from '../lib/seo'

// Replaced by scripts/prerender.mjs with the built index.html and the
// "/*" headers of public/_headers.
const SHELL_HTML: string = '__CSD_SHELL_HTML__'
const SECURITY_HEADERS: Record<string, string> = JSON.parse('__CSD_SECURITY_HEADERS__')

interface Env {
  ASSETS: { fetch(input: Request | string | URL, init?: RequestInit): Promise<Response> }
}

const HTML_HEADERS = {
  'Content-Type': 'text/html; charset=utf-8',
  'Cache-Control': 'public, max-age=0, must-revalidate',
}

function respond(body: string | null, status: number, method: string): Response {
  const headers = new Headers({ ...HTML_HEADERS, ...SECURITY_HEADERS })
  return new Response(method === 'HEAD' ? null : body, { status, headers })
}

async function notFound(request: Request, env: Env): Promise<Response> {
  // A path with no file: Pages answers it with 404.html and status 404.
  const res = await env.ASSETS.fetch(new URL('/__no_such_page__', request.url))
  return respond(await res.text(), 404, request.method)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    const match = url.pathname.match(/^\/school\/(\d{1,12})(\/?)$/)
    if (!match || (request.method !== 'GET' && request.method !== 'HEAD')) {
      return notFound(request, env)
    }
    if (match[2]) {
      url.pathname = `/school/${match[1]}`
      return Response.redirect(url.toString(), 308)
    }
    const data = await env.ASSETS.fetch(new URL(`/data/schools/${match[1]}.json`, request.url))
    if (!data.ok || !(data.headers.get('content-type') ?? '').includes('json')) {
      return notFound(request, env)
    }
    const profile = (await data.json()) as SchoolProfile
    return respond(renderSchoolPage(SHELL_HTML, profile), 200, request.method)
  },
}
