import { useState, useEffect } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { Sun, Moon, Monitor, Menu, X } from 'lucide-react'
import { cn } from './lib/utils'
import { useTheme } from './hooks/useTheme'
import ErrorBoundary from './components/ErrorBoundary'
import { useBuildInfo } from './lib/build'

export default function App() {
  const location = useLocation()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const build = useBuildInfo()

  // Close mobile menu and scroll to top on route change
  useEffect(() => {
    setIsMobileMenuOpen(false)
    window.scrollTo(0, 0)
  }, [location.pathname])

  // Cycle through: light → dark → system → light
  const cycleTheme = () => {
    if (theme === 'light') setTheme('dark')
    else if (theme === 'dark') setTheme('system')
    else setTheme('light')
  }

  const themeLabel = theme === 'system'
    ? `System (${resolvedTheme})`
    : theme === 'dark' ? 'Dark' : 'Light'
  const ThemeIcon = theme === 'system' ? Monitor : theme === 'dark' ? Moon : Sun

  const navLinks = [
    { path: '/', label: 'Rankings' },
    { path: '/compare', label: 'Compare' },
    { path: '/about', label: 'About' },
    { path: '/methodology', label: 'Methodology' },
    { path: '/contact', label: 'Contact' },
  ]

  // Skip link: focus the main content (which scrolls it into view) without
  // adding #main-content to the address
  const skipToMain = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const main = document.getElementById('main-content')
    if (!main) return
    e.preventDefault()
    main.focus()
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <a
        href="#main-content"
        onClick={skipToMain}
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded focus:border focus:border-rule-strong focus:bg-surface focus:px-4 focus:py-2 focus:text-ui focus:font-semibold focus:text-accent"
      >
        Skip to main content
      </a>

      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-rule bg-paper">
        <div className="wrap">
          <div className="flex h-header items-center justify-between gap-4">
            {/* Wordmark */}
            <Link to="/" className="flex min-h-[2.5rem] min-w-0 items-center gap-3 text-ink hover:text-ink-2">
              <span className="font-serif text-[1.1875rem] font-semibold leading-none tracking-[-0.005em]">
                CollegeSafetyData
              </span>
              <span className="hidden xl:block self-center w-px h-4 bg-rule-strong/50" />
              <span className="hidden xl:block text-meta text-ink-3">
                Campus Crime Statistics
              </span>
            </Link>

            <div className="flex items-center gap-1">
              {/* Desktop Navigation */}
              <nav className="hidden lg:flex items-stretch self-stretch gap-1">
                {navLinks.map(({ path, label }) => {
                  const current = location.pathname === path
                  return (
                    <Link
                      key={path}
                      to={path}
                      aria-current={current ? 'page' : undefined}
                      className={cn(
                        'flex h-header items-center border-b-2 px-3 text-ui',
                        current
                          ? 'border-accent font-semibold text-ink'
                          : 'border-transparent text-ink-2 hover:text-ink hover:border-rule-strong'
                      )}
                    >
                      {label}
                    </Link>
                  )
                })}
              </nav>

              {/* Theme Toggle */}
              <button
                type="button"
                onClick={cycleTheme}
                className="hidden lg:inline-flex ml-2 h-9 w-9 items-center justify-center rounded text-ink-2 hover:bg-subtle hover:text-ink"
                aria-label={`Theme: ${themeLabel}. Click to change.`}
                title={`Theme: ${themeLabel}. Click to change.`}
              >
                <ThemeIcon className="h-[1.125rem] w-[1.125rem]" aria-hidden="true" />
              </button>

              {/* Mobile Menu Button */}
              <button
                type="button"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="lg:hidden -mr-2 inline-flex h-10 w-10 items-center justify-center rounded text-ink-2 hover:bg-subtle hover:text-ink"
                aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={isMobileMenuOpen}
              >
                {isMobileMenuOpen ? (
                  <X className="h-5 w-5" aria-hidden="true" />
                ) : (
                  <Menu className="h-5 w-5" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          {/* Mobile Menu Dropdown */}
          {isMobileMenuOpen && (
            <div className="lg:hidden border-t border-rule py-2">
              {navLinks.map(({ path, label }) => {
                const current = location.pathname === path
                return (
                  <Link
                    key={path}
                    to={path}
                    aria-current={current ? 'page' : undefined}
                    className={cn(
                      'flex items-center border-l-2 px-3 py-2.5 text-body',
                      current
                        ? 'border-accent font-semibold text-ink'
                        : 'border-transparent text-ink-2 hover:text-ink hover:bg-subtle'
                    )}
                  >
                    {label}
                  </Link>
                )
              })}

              {/* Theme Toggle in Mobile Menu */}
              <div className="mt-2 border-t border-rule pt-2">
                <button
                  type="button"
                  onClick={cycleTheme}
                  className="flex w-full items-center gap-3 border-l-2 border-transparent px-3 py-2.5 text-body text-ink-2 hover:bg-subtle hover:text-ink"
                >
                  <ThemeIcon className="h-[1.125rem] w-[1.125rem]" aria-hidden="true" />
                  <span>Theme: {themeLabel}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>

      {/* Footer */}
      <footer className="mt-16 border-t border-rule bg-paper">
        <div className="wrap py-10">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
            {/* About */}
            <div>
              <h3 className="label text-ink mb-2">
                About This Dashboard
              </h3>
              <p className="text-meta text-ink-2 max-w-sm">
                This dashboard displays publicly available campus crime
                statistics reported under the Clery Act. Data is sourced from
                the U.S. Department of Education.
              </p>
            </div>

            {/* Resources */}
            <div>
              <h3 className="label text-ink mb-2">Resources</h3>
              <ul className="space-y-1.5 text-meta">
                <li>
                  <a
                    href="https://ope.ed.gov/campussafety/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="link"
                  >
                    DOE Campus Safety Data
                  </a>
                </li>
                <li>
                  <a
                    href="https://clerycenter.org/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="link"
                  >
                    Clery Center
                  </a>
                </li>
              </ul>
            </div>

            {/* Contact & Feedback */}
            <div>
              <h3 className="label text-ink mb-2">
                Contact & Feedback
              </h3>
              <ul className="space-y-1.5 text-meta">
                <li>
                  <a
                    href="mailto:contact@collegesafetydata.org"
                    className="link"
                  >
                    contact@collegesafetydata.org
                  </a>
                </li>
                <li>
                  <a
                    href="https://github.com/kbdevopz/collegesafetydata-public/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="link"
                  >
                    Report a Bug
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-8 flex flex-col gap-3 border-t border-rule pt-5 sm:flex-row sm:items-baseline sm:justify-between">
            <p className="text-meta text-ink-3">
              <span className="font-semibold text-ink-2">CollegeSafetyData.org</span>
              <span className="mx-2">&middot;</span>
              A public transparency tool
              <span className="mx-2">&middot;</span>
              <Link to="/about" className="link">
                Learn More
              </Link>
              <span className="mx-2">&middot;</span>
              <Link to="/privacy" className="link">
                Privacy
              </Link>
              <span className="mx-2">&middot;</span>
              <Link to="/terms" className="link">
                Terms
              </Link>
            </p>

            <p className="flex items-center gap-4 text-meta">
              <a
                href="https://github.com/kbdevopz/collegesafetydata-public"
                target="_blank"
                rel="noopener noreferrer"
                className="link inline-flex min-h-[1.5rem] items-center"
              >
                Open Source
              </a>
              <a
                href="https://buymeacoffee.com/karlisbaisden"
                target="_blank"
                rel="noopener noreferrer"
                className="link inline-flex min-h-[1.5rem] items-center"
              >
                Buy me a coffee
              </a>
            </p>
          </div>

          <p className="mt-4 max-w-prose text-meta text-ink-3">
            Reported incidents only. Lower numbers may reflect reporting differences, not greater safety.
            Data from the U.S. Department of Education. Not an official government website.
          </p>
          <p className="mt-2 text-meta text-ink-3">
            {build ? (
              <>
                Data build{' '}
                <Link to="/methodology#data" className="font-mono text-[0.8em] text-ink-2 underline decoration-rule-strong underline-offset-[3px] hover:text-accent" title={`SHA-256 of /data/build_inputs.json: ${build.sha256}`}>
                  {build.id}
                </Link>
                <span className="mx-2">&middot;</span>
              </>
            ) : null}
            <Link to="/methodology#cite" className="text-ink-2 underline decoration-rule-strong underline-offset-[3px] hover:text-accent">How to cite</Link>
            <span className="mx-2">&middot;</span>
            <Link to="/changes" className="text-ink-2 underline decoration-rule-strong underline-offset-[3px] hover:text-accent">Changes and corrections</Link>
          </p>
        </div>
      </footer>
    </div>
  )
}
