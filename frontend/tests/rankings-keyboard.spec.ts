import { test, expect, type Page } from '@playwright/test'

// Keyboard focus on the Rankings page (the site's home page). Run against a
// served build (npx vite preview, port 4173) or a dev server:
//   BASE_URL=http://localhost:5173 npx playwright test tests/rankings-keyboard.spec.ts
const BASE_URL = process.env.BASE_URL ?? 'http://localhost:4173'
// Optional: a Chromium other than the one this Playwright version installs
if (process.env.PLAYWRIGHT_CHROMIUM_PATH) {
  test.use({ launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } })
}

// The scroll position past which the sticky filter bar shows its compact search
// (pages/Rankings.tsx)
const COMPACT_BAR_AT = 250

const SIZES: [number, number][] = [[1366, 900], [375, 812]]

async function openRankings(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height })
  await page.goto(`${BASE_URL}/`)
  // The first ranking row that is shown at this width (table or cards)
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll<HTMLElement>('a[href^="/school/"]')).some((a) => a.offsetParent !== null))
}

async function focused(page: Page) {
  return page.evaluate(() => {
    const a = document.activeElement
    return {
      body: a === null || a === document.body,
      label: a ? a.getAttribute('aria-label') ?? (a.textContent ?? '').trim().slice(0, 60) : '',
      y: Math.round(window.scrollY),
    }
  })
}

for (const [width, height] of SIZES) {
  test(`Tab never drops focus while the page scrolls past the compact search bar (${width} px)`, async ({ page }) => {
    await openRankings(page, width, height)
    let past = 0
    for (let i = 1; i <= 120 && past < 15; i++) {
      await page.keyboard.press('Tab')
      // The scroll handler runs and the page re-renders
      await page.waitForTimeout(60)
      const now = await focused(page)
      expect(now.body, `Tab ${i}: focus fell to the page body at scroll position ${now.y}`).toBe(false)
      if (now.y > COMPACT_BAR_AT) past++
    }
    expect(past, `the page scrolled past ${COMPACT_BAR_AT} px while tabbing`).toBeGreaterThan(0)
  })

  test(`Enter on a ranking row's compare button keeps focus on it (${width} px)`, async ({ page }) => {
    await openRankings(page, width, height)
    let label = ''
    for (let i = 0; i < 80 && !/^Add .+ to comparison$/.test(label); i++) {
      await page.keyboard.press('Tab')
      label = (await focused(page)).label
    }
    expect(label).toMatch(/^Add .+ to comparison$/)
    await page.keyboard.press('Enter')
    await page.waitForTimeout(100)
    const now = await focused(page)
    expect(now.body, 'focus fell to the page body after Enter').toBe(false)
    expect(now.label).toBe(label.replace(/^Add /, 'Remove ').replace(/ to comparison$/, ' from comparison'))
  })
}
