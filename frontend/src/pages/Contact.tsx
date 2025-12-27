import { Link } from 'react-router-dom'
import { Mail, Github, Bug, MessageSquare, ExternalLink } from 'lucide-react'

export default function Contact() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
              Contact & Feedback
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              We welcome your questions, feedback, and bug reports. Your input helps us improve this resource.
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto space-y-12">

          {/* Email Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Mail className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                General Inquiries
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                For general questions, feedback, or collaboration inquiries, please reach out via email:
              </p>
              <a
                href="mailto:contact@collegesafetydata.org"
                className="inline-flex items-center gap-2 text-lg text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
              >
                <Mail className="w-5 h-5" />
                contact@collegesafetydata.org
              </a>
            </div>
          </section>

          {/* Bug Reports Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Bug className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Report a Bug
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                Found a technical issue with the site? Please report it on our GitHub Issues page:
              </p>
              <a
                href="https://github.com/kbdevopz/collegesafetydata-public/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-lg text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
              >
                <Github className="w-5 h-5" />
                GitHub Issues
                <ExternalLink className="w-4 h-4" />
              </a>
              <div className="mt-6 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  When reporting an issue, please include:
                </p>
                <ul className="space-y-2 text-sm">
                  <li className="flex gap-2">
                    <span className="text-primary-600 dark:text-primary-400">•</span>
                    <span>Browser and operating system</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary-600 dark:text-primary-400">•</span>
                    <span>Clear steps to reproduce the issue</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary-600 dark:text-primary-400">•</span>
                    <span>Expected behavior vs. actual behavior</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary-600 dark:text-primary-400">•</span>
                    <span>Screenshots if applicable</span>
                  </li>
                </ul>
              </div>
            </div>
          </section>

          {/* Data Questions Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data & Methodology Questions
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                For information about our data sources, processing methodology, and limitations:
              </p>
              <div className="flex flex-col gap-3">
                <Link
                  to="/methodology"
                  className="inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
                >
                  <span>Methodology Page</span>
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    — How we process the data
                  </span>
                </Link>
                <Link
                  to="/about"
                  className="inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
                >
                  <span>About Page</span>
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    — Data sources, Clery Act, and limitations
                  </span>
                </Link>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
