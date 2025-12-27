import { Link } from 'react-router-dom'
import { Scale, AlertTriangle, FileText, ExternalLink, Mail } from 'lucide-react'

export default function Terms() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
              Terms of Use
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              Please read these terms carefully before using CollegeSafetyData.org.
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

          {/* Acceptance Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Scale className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Acceptance of Terms
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                By accessing and using CollegeSafetyData.org, you accept and agree to be bound by these Terms of Use. If you do not agree to these terms, please do not use this site.
              </p>
            </div>
          </section>

          {/* Purpose Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Purpose of This Site
              </h2>
              <p className="leading-relaxed">
                CollegeSafetyData.org is a public transparency tool that displays campus crime statistics reported under the Jeanne Clery Disclosure of Campus Security Policy and Campus Crime Statistics Act (Clery Act). The data is sourced from the U.S. Department of Education and presented for informational and research purposes.
              </p>
            </div>
          </section>

          {/* Data Disclaimer Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data Accuracy & Limitations
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed font-medium text-gray-900 dark:text-gray-100">
                IMPORTANT: The data provided on this site has inherent limitations.
              </p>

              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                <ul className="space-y-2 text-sm text-amber-800 dark:text-amber-200">
                  <li className="flex gap-2">
                    <span className="text-amber-600 dark:text-amber-400 flex-shrink-0">•</span>
                    <span><strong>Source Data:</strong> All data is sourced from the U.S. Department of Education's Campus Safety and Security database. We do not verify, validate, or independently investigate the statistics reported by institutions.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-amber-600 dark:text-amber-400 flex-shrink-0">•</span>
                    <span><strong>Reporting Variations:</strong> Institutions may interpret Clery Act reporting requirements differently, leading to inconsistencies in how crimes are classified and counted.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-amber-600 dark:text-amber-400 flex-shrink-0">•</span>
                    <span><strong>Underreporting:</strong> Not all crimes are reported to campus authorities. Many incidents go unreported due to various factors including victim choice, fear of retaliation, or lack of awareness of reporting mechanisms.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-amber-600 dark:text-amber-400 flex-shrink-0">•</span>
                    <span><strong>Geographic Scope:</strong> Clery Act statistics only include crimes occurring on campus property, certain adjacent areas, and non-campus buildings owned or controlled by the institution. Crimes in surrounding neighborhoods are generally not included.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-amber-600 dark:text-amber-400 flex-shrink-0">•</span>
                    <span><strong>Temporal Lag:</strong> Data may be reported with a delay. The most recent year available may be 1-2 years behind the current date due to DOE publication schedules.</span>
                  </li>
                </ul>
              </div>

              <p className="leading-relaxed">
                For a detailed explanation of data limitations and methodology, please see our <Link
                  to="/methodology"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  Methodology
                </Link> and <Link
                  to="/about"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  About
                </Link> pages.
              </p>
            </div>
          </section>

          {/* No Warranty Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <FileText className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Disclaimer of Warranties
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                THIS SITE AND ALL INFORMATION, CONTENT, MATERIALS, AND DATA ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO:
              </p>
              <ul className="space-y-2 text-sm ml-4">
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Warranties of merchantability or fitness for a particular purpose</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Accuracy, completeness, reliability, or timeliness of information</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Freedom from errors, bugs, or interruptions in service</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Suitability for making decisions about college enrollment, campus safety, or any other purpose</span>
                </li>
              </ul>
            </div>
          </section>

          {/* Limitation of Liability Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Limitation of Liability
              </h2>
              <p className="leading-relaxed">
                TO THE FULLEST EXTENT PERMITTED BY LAW, THE OPERATORS OF COLLEGESAFETYDATA.ORG SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS OR REVENUES, WHETHER INCURRED DIRECTLY OR INDIRECTLY, OR ANY LOSS OF DATA, USE, GOODWILL, OR OTHER INTANGIBLE LOSSES RESULTING FROM:
              </p>
              <ul className="space-y-2 text-sm ml-4">
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Your access to, use of, or inability to access or use this site</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Any reliance on or decisions made based on information obtained from this site</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Any errors, inaccuracies, or omissions in the data presented</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Any unauthorized access to or alteration of your transmissions or data</span>
                </li>
              </ul>
            </div>
          </section>

          {/* User Responsibilities Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                User Responsibilities
              </h2>
              <p className="leading-relaxed">
                By using this site, you agree to:
              </p>
              <ul className="space-y-2 text-sm ml-4">
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Use the site for lawful purposes only</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Not attempt to gain unauthorized access to any portion of the site or any systems or networks connected to the site</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Not use automated systems (bots, scrapers, etc.) to access the site in a manner that sends more request messages to our servers than a human could reasonably produce in the same period</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-primary-600 dark:text-primary-400">•</span>
                  <span>Verify information independently before making important decisions based on data from this site</span>
                </li>
              </ul>
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
                This site contains links to external websites, including the U.S. Department of Education, GitHub, and other resources. We do not control these external sites and are not responsible for their content, privacy policies, or practices. The inclusion of any link does not imply endorsement.
              </p>
            </div>
          </section>

          {/* Intellectual Property Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Intellectual Property & Open Source
              </h2>
              <p className="leading-relaxed">
                The source code for this site is available under an open-source license on <a
                  href="https://github.com/kbdevopz/collegesafetydata-public"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 hover:underline"
                >
                  GitHub
                </a>. The underlying crime statistics data is public domain information provided by the U.S. Department of Education.
              </p>
              <p className="leading-relaxed">
                The design, compilation, and presentation of data on this site are the work of the site operators. You may use the data for research, journalism, or other lawful purposes with appropriate attribution.
              </p>
            </div>
          </section>

          {/* Changes to Terms Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Changes to These Terms
              </h2>
              <p className="leading-relaxed">
                We reserve the right to modify these Terms of Use at any time. Changes will be effective immediately upon posting to this page. The "Last updated" date at the top indicates when these terms were last revised. Your continued use of the site after any changes constitutes acceptance of the updated terms.
              </p>
            </div>
          </section>

          {/* Governing Law Section */}
          <section>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                Governing Law
              </h2>
              <p className="leading-relaxed">
                These Terms of Use shall be governed by and construed in accordance with the laws of the United States, without regard to its conflict of law provisions.
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
                Questions About These Terms
              </h2>
            </div>
            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                If you have questions about these Terms of Use, please contact us:
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

        </div>
      </div>
    </div>
  )
}
