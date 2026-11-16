import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

export default function Contact() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="wrap pt-8 pb-8 sm:pt-10">
        <h1 className="h1">
          Contact & Feedback
        </h1>
        <p className="lede mt-2">
          We welcome your questions, feedback, and bug reports. Your input helps us improve this resource.
        </p>
      </header>

      {/* Main Content */}
      <div className="wrap pb-12">
        <div className="max-w-[46rem] space-y-12">

          {/* Email Section */}
          <section>
            <h2 className="section-head">
              General Inquiries
            </h2>
            <div className="space-y-3">
              <p className="prose-body">
                For general questions, feedback, or collaboration inquiries, please reach out via email:
              </p>
              <a
                href="mailto:contact@collegesafetydata.org"
                className="link inline-flex min-h-[1.75rem] items-center text-heading font-semibold"
              >
                contact@collegesafetydata.org
              </a>
            </div>
          </section>

          {/* Bug Reports Section */}
          <section>
            <h2 className="section-head">
              Report a Bug
            </h2>
            <div className="space-y-3">
              <p className="prose-body">
                Found a technical issue with the site? Please report it on our GitHub Issues page:
              </p>
              <a
                href="https://github.com/kbdevopz/collegesafetydata-public/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="link inline-flex min-h-[1.75rem] items-center gap-1 text-heading font-semibold"
              >
                GitHub Issues
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
              <div className="!mt-6 border-l-2 border-rule-strong pl-4">
                <p className="text-ui font-semibold text-ink mb-2">
                  When reporting an issue, please include:
                </p>
                <ul className="list-disc space-y-1 pl-5 text-ui text-ink-2 marker:text-ink-3">
                  <li>Browser and operating system</li>
                  <li>Clear steps to reproduce the issue</li>
                  <li>Expected behavior vs. actual behavior</li>
                  <li>Screenshots if applicable</li>
                </ul>
              </div>
            </div>
          </section>

          {/* Data Questions Section */}
          <section>
            <h2 className="section-head">
              Data & Methodology Questions
            </h2>
            <div className="space-y-3">
              <p className="prose-body">
                For information about our data sources, processing methodology, and limitations:
              </p>
              <ul className="space-y-2 text-ui">
                <li>
                  <Link to="/methodology" className="group">
                    <span className="link font-semibold">Methodology Page</span>
                    <span className="text-ink-2">
                      {' '}— How we process the data
                    </span>
                  </Link>
                </li>
                <li>
                  <Link to="/about" className="group">
                    <span className="link font-semibold">About Page</span>
                    <span className="text-ink-2">
                      {' '}— Data sources, Clery Act, and limitations
                    </span>
                  </Link>
                </li>
              </ul>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
