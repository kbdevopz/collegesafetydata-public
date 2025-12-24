import { useState, useEffect, useCallback, useLayoutEffect } from 'react'

type Theme = 'light' | 'dark' | 'system'
type ResolvedTheme = 'light' | 'dark'

const THEME_CHANGE_EVENT = 'theme-change'
const MEDIA_QUERY = '(prefers-color-scheme: dark)'
const STORAGE_KEY = 'theme'

const isTheme = (value: string | null): value is Theme =>
  value === 'light' || value === 'dark' || value === 'system'

const getSystemTheme = (): ResolvedTheme =>
  typeof window !== 'undefined' && window.matchMedia(MEDIA_QUERY).matches ? 'dark' : 'light'

const resolveTheme = (theme: Theme): ResolvedTheme =>
  theme === 'system' ? getSystemTheme() : theme

const applyThemeClass = (theme: Theme): ResolvedTheme => {
  const resolved = resolveTheme(theme)
  const isDark = resolved === 'dark'
  document.documentElement.classList.toggle('dark', isDark)
  document.documentElement.dataset.theme = resolved
  // body may not exist during early render in some environments
  if (document.body) {
    document.body.classList.toggle('dark', isDark)
  }
  return resolved
}

const getInitialTheme = (): Theme => {
  if (typeof window === 'undefined') return 'light'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (isTheme(stored)) return stored
  return 'system'
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => getInitialTheme())
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolveTheme(getInitialTheme()))

  // Apply theme immediately on changes to avoid flashes
  useLayoutEffect(() => {
    const nextResolved = applyThemeClass(theme)
    setResolvedTheme(nextResolved)

    if (theme === 'system') {
      localStorage.removeItem(STORAGE_KEY)
    } else {
      localStorage.setItem(STORAGE_KEY, theme)
    }
  }, [theme])

  // Sync with other hook instances
  useEffect(() => {
    const handleThemeChange = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail
      if (isTheme(detail)) {
        setThemeState(detail)
      }
    }
    window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange as EventListener)
    return () => window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange as EventListener)
  }, [])

  // Track system preference when following system
  useEffect(() => {
    const mediaQuery = window.matchMedia(MEDIA_QUERY)
    const handleChange = (event: MediaQueryListEvent) => {
      if (theme !== 'system') return
      const nextResolved = event.matches ? 'dark' : 'light'
      setResolvedTheme(nextResolved)
      document.documentElement.classList.toggle('dark', nextResolved === 'dark')
    }
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme])

  const setTheme = useCallback((value: Theme) => {
    setThemeState(value)
    window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: value }))
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState(prev => {
      const next = prev === 'dark' || (prev === 'system' && resolvedTheme === 'dark') ? 'light' : 'dark'
      window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: next }))
      return next
    })
  }, [resolvedTheme])

  return { theme, resolvedTheme, setTheme, toggleTheme }
}
