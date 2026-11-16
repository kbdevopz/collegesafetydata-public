import { Link } from 'react-router-dom'

export default function Terms() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="wrap pt-8 pb-8 sm:pt-10">
        <h1 className="h1">
          Terms of Use
        </h1>
        <p className="lede mt-2">
          Please read these terms carefully before using CollegeSafetyData.org.
        </p>
        <p className="meta mt-3">
          Last updated: December 27, 2025
        </p>
      </header>

      {/* Main Content */}
      <div className="wrap pb-12">
        <div className="max-w-[46rem] space-y-12">

          {/* Acceptance Section */}
          <section>
            <h2 className="section-head">
              Acceptance of Terms
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                By accessing and using CollegeSafetyData.org, you accept and agree to be bound by these Terms of Use. If you do not agree to these terms, please do not use this site.
              </p>
            </div>
          </section>

          {/* Purpose Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Purpose of This Site
              </h2>
              <p>
                CollegeSafetyData.org is a public transparency tool that displays campus crime statistics reported under the Jeanne Clery Disclosure of Campus Security Policy and Campus Crime Statistics Act (Clery Act). The data is sourced from the U.S. Department of Education and presented for informational and research purposes.
              </p>
            </div>
          </section>

          {/* Data Disclaimer Section */}
          <section>
            <h2 className="section-head">
              Data Accuracy & Limitations
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p className="font-semibold text-ink">
                IMPORTANT: The data provided on this site has inherent limitations.
              </p>

              <div className="border-l-2 border-attention pl-4">
                <ul className="list-disc space-y-2 pl-5 text-ui text-ink-2 marker:text-ink-3">
                  <li><strong className="font-semibold text-ink">Source Data:</strong> All data is sourced from the U.S. Department of Education's Campus Safety and Security database. We do not verify, validate, or independently investigate the statistics reported by institutions.</li>
                  <li><strong className="font-semibold text-ink">Reporting Variations:</strong> Institutions may interpret Clery Act reporting requirements differently, leading to inconsistencies in how crimes are classified and counted.</li>
                  <li><strong className="font-semibold text-ink">Underreporting:</strong> Not all crimes are reported to campus authorities. Many incidents go unreported due to various factors including victim choice, fear of retaliation, or lack of awareness of reporting mechanisms.</li>
                  <li><strong className="font-semibold text-ink">Geographic Scope:</strong> Clery Act statistics only include crimes occurring on campus property, certain adjacent areas, and non-campus buildings owned or controlled by the institution. Crimes in surrounding neighborhoods are generally not included.</li>
                  <li><strong className="font-semibold text-ink">Temporal Lag:</strong> Data may be reported with a delay. The most recent year available may be 1-2 years behind the current date due to DOE publication schedules.</li>
                </ul>
              </div>

              <p>
                For a detailed explanation of data limitations and methodology, please see our <Link
                  to="/methodology"
                  className="link"
                >
                  Methodology
                </Link> and <Link
                  to="/about"
                  className="link"
                >
                  About
                </Link> pages.
              </p>
            </div>
          </section>

          {/* No Warranty Section */}
          <section>
            <h2 className="section-head">
              Disclaimer of Warranties
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                THIS SITE AND ALL INFORMATION, CONTENT, MATERIALS, AND DATA ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO:
              </p>
              <ul className="list-disc space-y-1.5 pl-5 text-ui marker:text-ink-3">
                <li>Warranties of merchantability or fitness for a particular purpose</li>
                <li>Accuracy, completeness, reliability, or timeliness of information</li>
                <li>Freedom from errors, bugs, or interruptions in service</li>
                <li>Suitability for making decisions about college enrollment, campus safety, or any other purpose</li>
              </ul>
            </div>
          </section>

          {/* Limitation of Liability Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Limitation of Liability
              </h2>
              <p>
                TO THE FULLEST EXTENT PERMITTED BY LAW, THE OPERATORS OF COLLEGESAFETYDATA.ORG SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS OR REVENUES, WHETHER INCURRED DIRECTLY OR INDIRECTLY, OR ANY LOSS OF DATA, USE, GOODWILL, OR OTHER INTANGIBLE LOSSES RESULTING FROM:
              </p>
              <ul className="list-disc space-y-1.5 pl-5 text-ui marker:text-ink-3">
                <li>Your access to, use of, or inability to access or use this site</li>
                <li>Any reliance on or decisions made based on information obtained from this site</li>
                <li>Any errors, inaccuracies, or omissions in the data presented</li>
                <li>Any unauthorized access to or alteration of your transmissions or data</li>
              </ul>
            </div>
          </section>

          {/* User Responsibilities Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                User Responsibilities
              </h2>
              <p>
                By using this site, you agree to:
              </p>
              <ul className="list-disc space-y-1.5 pl-5 text-ui marker:text-ink-3">
                <li>Use the site for lawful purposes only</li>
                <li>Not attempt to gain unauthorized access to any portion of the site or any systems or networks connected to the site</li>
                <li>Not use automated systems (bots, scrapers, etc.) to access the site in a manner that sends more request messages to our servers than a human could reasonably produce in the same period</li>
                <li>Verify information independently before making important decisions based on data from this site</li>
              </ul>
            </div>
          </section>

          {/* External Links Section */}
          <section>
            <h2 className="section-head">
              External Links
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                This site contains links to external websites, including the U.S. Department of Education, GitHub, and other resources. We do not control these external sites and are not responsible for their content, privacy policies, or practices. The inclusion of any link does not imply endorsement.
              </p>
            </div>
          </section>

          {/* Intellectual Property Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Intellectual Property & Open Source
              </h2>
              <p>
                The source code for this site is available under an open-source license on <a
                  href="https://github.com/kbdevopz/collegesafetydata-public"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link"
                >
                  GitHub
                </a>. The underlying crime statistics data is public domain information provided by the U.S. Department of Education.
              </p>
              <p>
                The design, compilation, and presentation of data on this site are the work of the site operators. You may use the data for research, journalism, or other lawful purposes with appropriate attribution.
              </p>
            </div>
          </section>

          {/* Changes to Terms Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Changes to These Terms
              </h2>
              <p>
                We reserve the right to modify these Terms of Use at any time. Changes will be effective immediately upon posting to this page. The "Last updated" date at the top indicates when these terms were last revised. Your continued use of the site after any changes constitutes acceptance of the updated terms.
              </p>
            </div>
          </section>

          {/* Governing Law Section */}
          <section>
            <div className="space-y-4 text-body text-ink-2">
              <h2 className="section-head">
                Governing Law
              </h2>
              <p>
                These Terms of Use shall be governed by and construed in accordance with the laws of the United States, without regard to its conflict of law provisions.
              </p>
            </div>
          </section>

          {/* Contact Section */}
          <section>
            <h2 className="section-head">
              Questions About These Terms
            </h2>
            <div className="space-y-4 text-body text-ink-2">
              <p>
                If you have questions about these Terms of Use, please contact us:
              </p>
              <a
                href="mailto:contact@collegesafetydata.org"
                className="link inline-flex min-h-[1.75rem] items-center text-heading font-semibold"
              >
                contact@collegesafetydata.org
              </a>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
