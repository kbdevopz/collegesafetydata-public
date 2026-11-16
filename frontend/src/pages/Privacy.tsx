import { Link } from 'react-router-dom'

export default function Privacy() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="wrap pt-8 pb-8 sm:pt-10">
        <h1 className="h1">
          Privacy Policy
        </h1>
        <p className="lede mt-2">
          We are committed to protecting your privacy. This policy explains what data we collect and how we use it.
        </p>
        <p className="meta mt-3">
          Last updated: November 10, 2026
        </p>
      </header>

      {/* Main Content */}
      <div className="wrap pb-12">
        <div className="max-w-[46rem] space-y-12">

          {/* Overview Section */}
          <section>
            <h2 className="section-head">
              Overview
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                CollegeSafetyData.org is a static website that displays publicly available campus crime statistics. We do not collect, store, or process any personally identifiable information about our visitors.
              </p>
              <div className="border-l-2 border-accent pl-4">
                <p className="text-ui text-ink-2">
                  <strong className="font-semibold text-ink">Privacy-First Design:</strong> This site collects no personal data, uses no cookies, and requires no account registration. The only analytics is Cloudflare Web Analytics, which counts page views in aggregate without cookies or tracking you across sites (see below).
                </p>
              </div>
            </div>
          </section>

          {/* Data Collection Section */}
          <section>
            <h2 className="section-head">
              Data We Collect
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p className="font-semibold text-ink">
                We collect minimal data necessary for site functionality:
              </p>

              <div className="space-y-5">
                <div className="border-t border-rule pt-3">
                  <h3 className="h3 mb-2">
                    Theme Preference (Local Storage Only)
                  </h3>
                  <p className="text-ui">
                    Your dark/light mode preference is stored locally in your browser's localStorage. This data never leaves your device and contains no personally identifiable information.
                  </p>
                </div>

                <div className="border-t border-rule pt-3">
                  <h3 className="h3 mb-2">
                    Google Fonts
                  </h3>
                  <p className="text-ui">
                    This site uses Google Fonts CDN to load web fonts. When you visit our site, your browser makes a request to Google's servers to download font files. Google may collect basic connection information (IP address, user agent) as part of this standard web request. See <a
                      href="https://policies.google.com/privacy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link"
                    >
                      Google's Privacy Policy
                    </a> for details.
                  </p>
                </div>

                <div className="border-t border-rule pt-3">
                  <h3 className="h3 mb-2">
                    Cloudflare Web Analytics (collegesafetydata.org)
                  </h3>
                  <p className="text-ui">
                    Pages on collegesafetydata.org include Cloudflare Web Analytics, which records aggregate visit statistics such as page views, referring sites, countries and page load times. It sets no cookies, does not use your IP address to identify you, and does not follow you across other websites. We see only totals. See <a
                      href="https://www.cloudflare.com/web-analytics/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link"
                    >
                      Cloudflare Web Analytics
                    </a> for details.
                  </p>
                </div>
              </div>

              <p className="font-semibold text-ink mt-6">
                What we DON'T collect:
              </p>
              <ul className="list-disc space-y-1.5 pl-5 text-ui marker:text-ink-3">
                <li>No cookies</li>
                <li>No tracking or advertising scripts (no Google Analytics, no ad networks, no cross-site trackers)</li>
                <li>No user accounts or authentication</li>
                <li>No forms that submit data to our servers</li>
                <li>No server-side logging of visitor activity</li>
                <li>No email collection (our contact links use your email client)</li>
              </ul>
            </div>
          </section>

          {/* Cookies Section */}
          <section>
            <h2 className="section-head">
              Cookies
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                This website does not use cookies. We use browser localStorage instead to store your theme preference locally on your device.
              </p>
            </div>
          </section>

          {/* External Links Section */}
          <section>
            <h2 className="section-head">
              External Links
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                This site contains links to external websites, including:
              </p>
              <ul className="list-disc space-y-1.5 pl-5 text-ui marker:text-ink-3">
                <li>U.S. Department of Education Campus Safety Data</li>
                <li>GitHub repository</li>
                <li>Buy Me a Coffee donation platform</li>
              </ul>
              <p>
                We are not responsible for the privacy practices of these external sites. We encourage you to review their privacy policies before providing any personal information.
              </p>
            </div>
          </section>

          {/* Hosting Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Hosting & Infrastructure
              </h2>
              <p>
                This site is hosted on Cloudflare Pages and Vercel. These hosting providers may collect basic connection logs (IP addresses, timestamps) for infrastructure security and performance monitoring. This data is controlled by the hosting provider, not by us. See <a
                  href="https://www.cloudflare.com/privacypolicy/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link"
                >
                  Cloudflare's Privacy Policy
                </a> and <a
                  href="https://vercel.com/legal/privacy-policy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link"
                >
                  Vercel's Privacy Policy
                </a> for details.
              </p>
            </div>
          </section>

          {/* Changes to Policy Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Changes to This Policy
              </h2>
              <p>
                We may update this privacy policy from time to time. The "Last updated" date at the top of this page indicates when the policy was last revised. Continued use of the site after changes constitutes acceptance of the updated policy.
              </p>
            </div>
          </section>

          {/* Contact Section */}
          <section>
            <h2 className="section-head">
              Questions About Privacy
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                If you have questions about this privacy policy or our data practices, please contact us:
              </p>
              <a
                href="mailto:contact@collegesafetydata.org"
                className="link inline-flex min-h-[1.75rem] items-center text-heading font-semibold"
              >
                contact@collegesafetydata.org
              </a>
              <p className="text-ui">
                For more information about our site, see our <Link
                  to="/about"
                  className="link"
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
