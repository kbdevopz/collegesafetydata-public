import { Link } from 'react-router-dom'
import { Shield, Database, Cookie, ExternalLink, Mail } from 'lucide-react'

export default function Privacy() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
              Privacy Policy
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              We are committed to protecting your privacy. This policy explains what data we collect and how we use it.
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-500 mt-4">
              Last updated: December 27, 2025
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto space-y-12">

          {/* Overview Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Overview
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                CollegeSafetyData.org is a static website that displays publicly available campus crime statistics. We do not collect, store, or process any personally identifiable information about our visitors.
              </p>
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <p className="text-sm text-green-700 dark:text-green-300 font-medium">
                  <strong>Privacy-First Design:</strong> This site collects no user data, uses no cookies, has no analytics tracking, and requires no account registration.
                </p>
              </div>
            </div>
          </section>

          {/* Data Collection Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Database className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data We Collect
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed font-medium text-gray-900 dark:text-gray-100">
                We collect minimal data necessary for site functionality:
              </p>

              <div className="space-y-3">
                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    Theme Preference (Local Storage Only)
                  </h3>
                  <p className="text-sm">
                    Your dark/light mode preference is stored locally in your browser's localStorage. This data never leaves your device and contains no personally identifiable information.
                  </p>
                </div>

                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    Google Fonts
                  </h3>
                  <p className="text-sm">
                    This site uses Google Fonts CDN to load web fonts. When you visit our site, your browser makes a request to Google's servers to download font files. Google may collect basic connection information (IP address, user agent) as part of this standard web request. See <a
                      href="https://policies.google.com/privacy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                    >
                      Google's Privacy Policy
                    </a> for details.
                  </p>
                </div>
              </div>

              <p className="leading-relaxed font-medium text-gray-900 dark:text-gray-100 mt-6">
                What we DON'T collect:
              </p>
              <ul className="space-y-2 text-sm">
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No cookies</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No analytics or tracking scripts (no Google Analytics, no third-party trackers)</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No user accounts or authentication</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No forms that submit data to our servers</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No server-side logging of visitor activity</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400">✓</span>
                  <span>No email collection (our contact links use your email client)</span>
                </li>
              </ul>
            </div>
          </section>

          {/* Cookies Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Cookie className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Cookies
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                This website does not use cookies. We use browser localStorage instead to store your theme preference locally on your device.
              </p>
            </div>
          </section>

          {/* External Links Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <ExternalLink className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                External Links
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                This site contains links to external websites, including:
              </p>
              <ul className="space-y-2 text-sm ml-4">
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>U.S. Department of Education Campus Safety Data</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>GitHub repository</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Buy Me a Coffee donation platform</span>
                </li>
              </ul>
              <p className="leading-relaxed">
                We are not responsible for the privacy practices of these external sites. We encourage you to review their privacy policies before providing any personal information.
              </p>
            </div>
          </section>

          {/* Hosting Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Hosting & Infrastructure
              </h2>
              <p className="leading-relaxed">
                This site is hosted on Cloudflare Pages and Vercel. These hosting providers may collect basic connection logs (IP addresses, timestamps) for infrastructure security and performance monitoring. This data is controlled by the hosting provider, not by us. See <a
                  href="https://www.cloudflare.com/privacypolicy/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  Cloudflare's Privacy Policy
                </a> and <a
                  href="https://vercel.com/legal/privacy-policy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  Vercel's Privacy Policy
                </a> for details.
              </p>
            </div>
          </section>

          {/* Changes to Policy Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Changes to This Policy
              </h2>
              <p className="leading-relaxed">
                We may update this privacy policy from time to time. The "Last updated" date at the top of this page indicates when the policy was last revised. Continued use of the site after changes constitutes acceptance of the updated policy.
              </p>
            </div>
          </section>

          {/* Contact Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Mail className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Questions About Privacy
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                If you have questions about this privacy policy or our data practices, please contact us:
              </p>
              <a
                href="mailto:contact@collegesafetydata.org"
                className="inline-flex items-center gap-2 text-lg text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
              >
                <Mail className="w-5 h-5" />
                contact@collegesafetydata.org
              </a>
              <p className="text-sm">
                For more information about our site, see our <Link
                  to="/about"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  About
                </Link> page.
              </p>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
