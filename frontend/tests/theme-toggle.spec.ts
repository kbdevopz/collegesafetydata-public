import { test, expect } from '@playwright/test'

test.describe('Theme Toggle', () => {
  test('clicking dark mode should change body background', async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.waitForLoadState('networkidle')

    // Clear any stored theme preference
    await page.evaluate(() => localStorage.removeItem('theme'))

    // Get initial body background (should be light)
    const initialBg = await page.evaluate(() => {
      document.documentElement.classList.remove('dark')
      return window.getComputedStyle(document.body).backgroundColor
    })
    console.log('Initial (light mode) bg:', initialBg)

    // Add dark class
    await page.evaluate(() => {
      document.documentElement.classList.add('dark')
    })
    // Wait for transition (duration-200 = 200ms)
    await page.waitForTimeout(300)

    // Get dark mode background
    const darkBg = await page.evaluate(() => {
      return window.getComputedStyle(document.body).backgroundColor
    })
    console.log('After adding .dark class:', darkBg)

    // Verify background changed
    const backgroundChanged = initialBg !== darkBg
    console.log('Background changed:', backgroundChanged)

    // Check for expected values
    // Light: rgb(249, 250, 251) = gray-50
    // Dark: rgb(3, 7, 18) = gray-950
    expect(initialBg).toBe('rgb(249, 250, 251)')
    expect(darkBg).toBe('rgb(3, 7, 18)')
  })

  test('clicking theme toggle button changes colors', async ({ page }) => {
    await page.goto('http://localhost:5175')
    await page.waitForLoadState('networkidle')

    // Force light mode first
    await page.evaluate(() => {
      localStorage.setItem('theme', 'light')
      document.documentElement.classList.remove('dark')
    })
    await page.waitForTimeout(200)

    const lightBg = await page.evaluate(() =>
      window.getComputedStyle(document.body).backgroundColor
    )
    console.log('Light mode bg:', lightBg)

    // Find and click the Dark button
    const darkButton = page.getByRole('button', { name: 'Dark' })
    if (await darkButton.isVisible()) {
      await darkButton.click()
      await page.waitForTimeout(200)

      const afterDarkClick = await page.evaluate(() => ({
        bg: window.getComputedStyle(document.body).backgroundColor,
        hasDarkClass: document.documentElement.classList.contains('dark'),
      }))
      console.log('After clicking Dark button:', afterDarkClick)

      // Background should change
      expect(afterDarkClick.hasDarkClass).toBe(true)
      expect(afterDarkClick.bg).toBe('rgb(3, 7, 18)')
    } else {
      console.log('Dark button not found, looking for other theme controls...')
      // Try finding theme toggle by other means
      const themeButtons = await page.locator('button').all()
      for (const btn of themeButtons) {
        const text = await btn.textContent()
        console.log('Button:', text)
      }
    }
  })
})
