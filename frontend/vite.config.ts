import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const NEUTRAL_DESCRIPTION =
  'CollegeSafetyData.org - Clery Act campus crime statistics for U.S. college campuses. Compare rankings, trends, and detailed breakdowns.'

function isInteger(value: unknown): value is number {
  return typeof value === 'number' && isFinite(value) && Math.floor(value) === value
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// Years as ranges, like formatYearRanges in src/lib/enrollment.ts:
// [2015, 2016, 2017, 2019] -> "2015-2017, 2019".
function formatYearRanges(years: number[]): string {
  const sorted = years.slice().sort((a, b) => a - b)
  const parts: string[] = []
  let start = sorted[0]
  let prev = sorted[0]
  for (const year of sorted.slice(1)) {
    if (year === prev || year === prev + 1) {
      prev = year
      continue
    }
    parts.push(start === prev ? `${start}` : `${start}-${prev}`)
    start = year
    prev = year
  }
  parts.push(start === prev ? `${start}` : `${start}-${prev}`)
  return parts.join(', ')
}

// The page description with the school count and years of the published data
// (public/data/metadata.json). Any problem leaves the neutral description.
function dataDescription(): string {
  try {
    const file = resolve(dirname(fileURLToPath(import.meta.url)), 'public', 'data', 'metadata.json')
    const metadata = JSON.parse(readFileSync(file, 'utf-8'))
    const national = Array.isArray(metadata.presets)
      ? metadata.presets.find((p: { id?: unknown } | null) => p && p.id === 'national')
      : undefined
    const count = national?.schoolCount
    const years = metadata.years
    if (
      !isInteger(count) || count <= 0 ||
      !Array.isArray(years) || years.length === 0 || !years.every(isInteger)
    ) {
      return NEUTRAL_DESCRIPTION
    }
    return (
      `CollegeSafetyData.org - Clery Act campus crime statistics for ${count.toLocaleString('en-US')} ` +
      `U.S. college campuses (${formatYearRanges(years)}). Compare rankings, trends, and detailed breakdowns.`
    )
  } catch {
    return NEUTRAL_DESCRIPTION
  }
}

function dataDescriptionPlugin(): Plugin {
  return {
    name: 'data-description',
    transformIndexHtml(html) {
      return html.replace(
        `content="${NEUTRAL_DESCRIPTION}"`,
        () => `content="${escapeHtml(dataDescription())}"`
      )
    }
  }
}

// https://vitejs.dev/config/
// `vite build`: the site. `vite build --ssr src/entry-server.tsx`: the
// build-time page renderer (scripts/prerender.mjs). `vite build --mode
// worker`: the Cloudflare Pages worker for school pages (src/edge/worker.ts).
export default defineConfig(({ mode }) => {
  if (mode === 'worker') {
    return {
      build: {
        ssr: 'src/edge/worker.ts',
        outDir: '.prerender/worker',
        emptyOutDir: true,
        minify: false,
        target: 'es2022',
        rollupOptions: { output: { format: 'es', entryFileNames: 'worker.js' } },
      },
      ssr: { target: 'webworker', noExternal: true },
    }
  }
  return {
    plugins: [react(), dataDescriptionPlugin()],
    build: {
      outDir: 'dist',
      sourcemap: false,
      rollupOptions: {
        output: {
          // Charts are used only by the school and compare pages; icons by
          // every page, in one file rather than one small file per icon.
          // (Not for the build-time SSR bundle, whose dependencies are external.)
          manualChunks(id: string) {
            if (!id.includes('node_modules')) return undefined
            if (/[\\/]node_modules[\\/](recharts|recharts-scale|victory-vendor|d3-[^\\/]+|internmap|decimal\.js-light|eventemitter3|lodash|react-smooth|fast-equals|tiny-invariant)[\\/]/.test(id)) return 'charts'
            if (/[\\/]node_modules[\\/]lucide-react[\\/]/.test(id)) return 'icons'
            // Every other package in one file: without a chunk of their own, Rollup
            // would put the ones recharts shares with the app (React, clsx) into
            // the charts file and every page would load it.
            return 'vendor'
          },
        },
      },
    },
    server: {
      port: 5173,
      open: true,
    },
  }
})