// Fails when public/_headers (Cloudflare Pages) and ../vercel.json (Vercel)
// do not set exactly the same response headers for the same paths, so the two
// hosts cannot drift apart. Run by `npm run build`.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontend = resolve(here, '..')

// Cloudflare `_headers`: a path line, then indented "Name: value" lines.
export function parseHeadersFile(text) {
  const rules = new Map()
  let current = null
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim() || raw.trim().startsWith('#')) continue
    if (!/^\s/.test(raw)) {
      current = raw.trim()
      if (!rules.has(current)) rules.set(current, new Map())
      continue
    }
    if (!current) throw new Error(`_headers: header line before any path: ${raw}`)
    const i = raw.indexOf(':')
    if (i < 0) throw new Error(`_headers: not a "Name: value" line: ${raw}`)
    rules.get(current).set(raw.slice(0, i).trim().toLowerCase(), raw.slice(i + 1).trim())
  }
  return rules
}

// vercel.json sources are path-to-regexp; this repo uses only "/x/(.*)" and
// exact paths, which map to Cloudflare's "/x/*" and the same exact path.
function vercelSourceToPattern(source) {
  return source.replace(/\(\.\*\)$/, '*')
}

export function parseVercel(json) {
  const rules = new Map()
  for (const rule of json.headers ?? []) {
    const pattern = vercelSourceToPattern(rule.source)
    const map = rules.get(pattern) ?? new Map()
    for (const { key, value } of rule.headers) map.set(key.toLowerCase(), value)
    rules.set(pattern, map)
  }
  return rules
}

export function loadHeaderRules() {
  return parseHeadersFile(readFileSync(resolve(frontend, 'public', '_headers'), 'utf-8'))
}

function main() {
  const cf = loadHeaderRules()
  const vercel = parseVercel(JSON.parse(readFileSync(resolve(frontend, '..', 'vercel.json'), 'utf-8')))
  const problems = []
  for (const pattern of new Set([...cf.keys(), ...vercel.keys()])) {
    const a = cf.get(pattern)
    const b = vercel.get(pattern)
    if (!a || !b) {
      problems.push(`${pattern}: only in ${a ? 'public/_headers' : 'vercel.json'}`)
      continue
    }
    for (const name of new Set([...a.keys(), ...b.keys()])) {
      if (a.get(name) !== b.get(name)) {
        problems.push(`${pattern} ${name}:\n    _headers:    ${a.get(name) ?? '(missing)'}\n    vercel.json: ${b.get(name) ?? '(missing)'}`)
      }
    }
  }
  // Cloudflare joins the values of a header set by two matching rules with a
  // comma, so Cache-Control must not be set on "/*" as well as a narrower path.
  if (cf.get('/*')?.has('cache-control')) problems.push('/*: set Cache-Control only on specific paths')
  if (problems.length) {
    console.error('Response headers differ between public/_headers and vercel.json:\n  ' + problems.join('\n  '))
    process.exit(1)
  }
  console.log(`Response headers match on both hosts (${cf.size} path rules).`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main()
