import { useState, useEffect } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { BarChart3, GitCompare, Info, Shield, Sun, Moon, Monitor, Menu, X, Coffee, BookOpen, Github } from 'lucide-react'
import { cn } from './lib/utils'
import { useTheme } from './hooks/useTheme'

export default function App() {
  const location = useLocation()
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

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

  const navLinks = [
    { path: '/', label: 'Rankings', icon: BarChart3 },
    { path: '/compare', label: 'Compare', icon: GitCompare },
    { path: '/about', label: 'About', icon: Info },
    { path: '/methodology', label: 'Methodology', icon: BookOpen },
  ]

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col transition-colors duration-200">
      {/* Header */}
      <header className="bg-white dark:bg-gray-900 shadow-sm dark:shadow-gray-900/50 sticky top-0 z-50 transition-colors duration-200">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link
              to="/"
              className="flex items-center gap-3 text-gray-900 dark:text-gray-100 hover:text-gray-700 dark:hover:text-gray-300 transition-colors group"
            >
              <div className="w-9 h-9 bg-gradient-to-br from-primary-600 to-primary-800 dark:from-primary-500 dark:to-primary-700 rounded-lg flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div className="flex items-center gap-2 sm:gap-3">
                <span className="text-lg font-bold tracking-tight">
                  CollegeSafetyData
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300 border border-primary-200 dark:border-primary-700">
                  BETA
                </span>
                <span className="hidden sm:block w-px h-5 bg-gray-300 dark:bg-gray-700" />
                <span className="hidden sm:block text-sm text-gray-500 dark:text-gray-400 font-medium">
                  Campus Crime Statistics
                </span>
              </div>
            </Link>

            {/* Desktop Navigation */}
            <div className="flex items-center gap-2">
              <nav className="hidden md:flex items-center gap-1">
                {navLinks.map(({ path, label, icon: Icon }) => (
                <Link
                  key={path}
                  to={path}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                    location.pathname === path
                      ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  <span>{label}</span>
                </Link>
              ))}

              {/* Theme Toggle */}
              <button
                type="button"
                onClick={cycleTheme}
                className="ml-2 p-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label={`Theme: ${themeLabel}. Click to change.`}
                title={`Theme: ${themeLabel}. Click to change.`}
              >
                {theme === 'system' ? (
                  <Monitor className="w-5 h-5" />
                ) : theme === 'dark' ? (
                  <Moon className="w-5 h-5" />
                ) : (
                  <Sun className="w-5 h-5" />
                )}
              </button>
            </nav>

              {/* Mobile Menu Button */}
              <button
                type="button"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="md:hidden p-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={isMobileMenuOpen}
              >
                {isMobileMenuOpen ? (
                  <X className="w-6 h-6" />
                ) : (
                  <Menu className="w-6 h-6" />
                )}
              </button>
            </div>
          </div>

          {/* Mobile Menu Dropdown */}
          {isMobileMenuOpen && (
            <div className="md:hidden border-t dark:border-gray-800 py-4 space-y-1">
              {navLinks.map(({ path, label, icon: Icon }) => (
                <Link
                  key={path}
                  to={path}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-lg text-base font-medium transition-colors',
                    location.pathname === path
                      ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800'
                  )}
                >
                  <Icon className="w-5 h-5" />
                  <span>{label}</span>
                </Link>
              ))}

              {/* Theme Toggle in Mobile Menu */}
              <div className="border-t dark:border-gray-800 mt-3 pt-3">
                <button
                  type="button"
                  onClick={cycleTheme}
                  className="flex items-center gap-3 w-full px-4 py-3 rounded-lg text-base font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  {theme === 'system' ? (
                    <Monitor className="w-5 h-5" />
                  ) : theme === 'dark' ? (
                    <Moon className="w-5 h-5" />
                  ) : (
                    <Sun className="w-5 h-5" />
                  )}
                  <span>Theme: {themeLabel}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-white dark:bg-gray-900 border-t dark:border-gray-800 mt-auto transition-colors duration-200">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* About */}
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                About This Dashboard
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                This dashboard displays publicly available campus crime
                statistics reported under the Clery Act. Data is sourced from
                the U.S. Department of Education.
              </p>
            </div>

            {/* Resources */}
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Resources</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a
                    href="https://ope.ed.gov/campussafety/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                  >
                    DOE Campus Safety Data
                  </a>
                </li>
                <li>
                  <a
                    href="https://clerycenter.org/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                  >
                    Clery Center
                  </a>
                </li>
              </ul>
            </div>

            {/* Disclaimer */}
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Data Disclaimer</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Reported incidents only — lower numbers may reflect reporting
                differences, not greater safety. Not an official government website.
              </p>
            </div>
          </div>

          <div className="mt-8 pt-6 border-t dark:border-gray-800 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center sm:text-left">
              <span className="font-medium">CollegeSafetyData.org</span>
              <span className="mx-2">&middot;</span>
              A public transparency tool
              <span className="mx-2">&middot;</span>
              <Link to="/about" className="text-primary-600 dark:text-primary-400 hover:underline">
                Learn More
              </Link>
            </p>

            <div className="flex items-center gap-4">
              {/* GitHub */}
              <a
                href="https://github.com/kbdevopz/collegesafetydata-public"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
              >
                <Github className="w-5 h-5" />
                <span className="text-sm">Open Source</span>
              </a>

              {/* Buy Me a Coffee */}
              <a
                href="https://buymeacoffee.com/karlisbaisden"
                target="_blank"
                rel="noopener noreferrer"
                className="group inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-amber-400 to-orange-500 hover:from-amber-500 hover:to-orange-600 text-white font-medium text-sm shadow-md hover:shadow-lg transition-all duration-200 hover:scale-105"
              >
                <Coffee className="w-4 h-4 group-hover:animate-bounce" />
                <span>Buy me a coffee</span>
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
