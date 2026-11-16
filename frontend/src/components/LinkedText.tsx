/**
 * Plain text whose web addresses become links (a reason or source taken from
 * the data, which writes addresses inline). An address ends at a space, a
 * semicolon or a quotation mark; a trailing period, comma or parenthesis is
 * left as text.
 */
export default function LinkedText({ text }: { text: string }) {
  const parts: (string | { url: string })[] = []
  const re = /https?:\/\/[^\s;"]+/g
  let last = 0
  for (const m of text.matchAll(re)) {
    let url = m[0]
    const trail = /[.,)]+$/.exec(url)?.[0] ?? ''
    url = url.slice(0, url.length - trail.length)
    const start = m.index ?? 0
    if (start > last) parts.push(text.slice(last, start))
    parts.push({ url })
    last = start + url.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return (
    <>
      {parts.map((p, i) =>
        typeof p === 'string'
          ? p
          : (
            <a key={i} href={p.url} className="link break-all" rel="noopener noreferrer" target="_blank">
              {p.url}
            </a>
          ),
      )}
    </>
  )
}
