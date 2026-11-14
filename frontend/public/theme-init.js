// Apply the saved theme before React renders, so the page does not flash and
// Tailwind's dark styles are active from the first paint. Kept as a separate
// file (not an inline script) so the Content-Security-Policy needs no
// 'unsafe-inline' or hash for scripts.
(function () {
  var STORAGE_KEY = 'theme'
  var MEDIA_QUERY = '(prefers-color-scheme: dark)'
  try {
    var stored = localStorage.getItem(STORAGE_KEY)
    var theme = stored === 'light' || stored === 'dark' ? stored : 'system'
    var systemDark = window.matchMedia(MEDIA_QUERY).matches
    var resolved = theme === 'dark' || (theme === 'system' && systemDark) ? 'dark' : 'light'
    var isDark = resolved === 'dark'
    document.documentElement.classList.toggle('dark', isDark)
    document.documentElement.dataset.theme = resolved
    if (document.body) document.body.classList.toggle('dark', isDark)
  } catch (err) {
    if (window.matchMedia && window.matchMedia(MEDIA_QUERY).matches) {
      document.documentElement.classList.add('dark')
      document.documentElement.dataset.theme = 'dark'
      if (document.body) document.body.classList.add('dark')
    }
  }
})()
