import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, ExternalLink } from 'lucide-react'
import { cachedMetadata, getMetadata } from '../lib/api'
import type { Metadata } from '../lib/types'
import { formatDate, formatNumber, cn } from '../lib/utils'
import { summarizeEnrollmentStatus, describeFteAvailability } from '../lib/enrollment'
import { summarizeDataYears, describeReportingLag } from '../lib/coverage'
import {
  SOURCES,
  CRIMINAL_DEFINITIONS,
  VAWA_DEFINITIONS,
  LAW_VIOLATION_DEFINITIONS,
  GEOGRAPHY_DEFINITIONS,
} from '../data/sources'

// Collapsible section: a native disclosure (keyboard and screen readers
// handle it; find-in-page opens it)
function CollapsibleSection({
  title,
  children,
  defaultOpen = false
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details className="group border-b border-rule" open={defaultOpen}>
      <summary className="flex min-h-[2.75rem] cursor-pointer list-none items-center gap-2 py-2 text-left text-ui font-semibold text-ink hover:text-accent [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="h-4 w-4 flex-shrink-0 text-ink-3 transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        <span>{title}</span>
      </summary>
      <div className="pb-4 pl-6">
        {children}
      </div>
    </details>
  )
}

// Crime category item
function CrimeItem({ name, description }: { name: string; description: string }) {
  return (
    <div className="py-1.5">
      <span className="font-semibold text-ink">{name}</span>
      <span className="text-ink-2"> — {description}</span>
    </div>
  )
}

// Limitation item
function LimitationCard({
  title,
  description,
  className,
}: {
  title: string
  description: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('border-t border-rule pt-3', className)}>
      <h4 className="text-ui font-semibold text-ink">{title}</h4>
      <p className="mt-1 text-ui text-ink-2">{description}</p>
    </div>
  )
}

export default function About() {
  const [metadata, setMetadata] = useState<Metadata | null>(cachedMetadata)

  useEffect(() => {
    getMetadata().then(setMetadata).catch(console.error)
  }, [])

  // Year count, span and newest year from metadata.json "years"/"coverage",
  // FTE availability from "enrollmentStatus" and the school count from the
  // national preset (wording that names no year or count when absent)
  const dataYears = summarizeDataYears(metadata)
  const fteAvailabilityText = describeFteAvailability(summarizeEnrollmentStatus(metadata), metadata?.rateRules?.skipYears)
  const schoolCount = metadata?.presets?.find((p) => p.id === 'national')?.schoolCount

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="wrap pt-8 pb-8 sm:pt-10">
        <h1 className="h1">
          About CollegeSafetyData
        </h1>
        <p className="lede mt-2">
          Free, public access to campus crime statistics reported under the
          Jeanne Clery Act — making college safety data transparent and accessible.
        </p>
      </header>

      {/* Main Content */}
      <div className="wrap pb-12">
        <div className="max-w-[46rem] space-y-14">

          {/* What is the Clery Act */}
          <section>
            <h2 className="section-head">
              What is the Clery Act?
            </h2>

            <div className="prose-body">
              <p>
                The Clery Act is a federal law requiring colleges and universities
                participating in federal financial aid programs to disclose campus crime information.
              </p>
              <p>
                Named after <strong className="font-semibold text-ink">Jeanne Clery</strong>,
                who was murdered in her dorm room at Lehigh University in 1986, the Act ensures
                transparency about campus safety.
              </p>
            </div>

            {/* Requirements */}
            <ul className="mt-5 list-disc space-y-1.5 pl-5 text-ui text-ink-2 marker:text-ink-3">
              {[
                { text: "Publish Annual Security Reports with 3 years of crime data" },
                { text: "Report specific crime categories for campus areas" },
                { text: "Issue timely warnings about safety threats" },
                { text: "Keep a daily crime log open to the public, if the institution has a campus police or security department (34 CFR 668.46(f))" },
              ].map((item, i) => (
                <li key={i}>{item.text}</li>
              ))}
            </ul>
          </section>

          {/* Data Source */}
          <section>
            <h2 className="section-head">
              Data Source
            </h2>

            <h3 className="h3">
              U.S. Department of Education
            </h3>
            <p className="mt-0.5 text-ui text-ink-2">
              Campus Safety and Security Database
            </p>
            <a
              href="https://ope.ed.gov/campussafety/"
              target="_blank"
              rel="noopener noreferrer"
              className="link mt-2 inline-flex min-h-[1.5rem] items-center gap-1 text-ui font-semibold"
            >
              ope.ed.gov/campussafety
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
            {metadata && (
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-rule pt-3 text-meta text-ink-2">
                <span>Coverage: <strong className="font-semibold text-ink">{metadata.coverage || dataYears.span || '—'}</strong></span>
                <span>Updated: <strong className="font-semibold text-ink">{formatDate(metadata.lastUpdated)}</strong></span>
              </div>
            )}
          </section>

          {/* Crime Categories - Collapsible */}
          <section>
            <h2 className="section-head">
              Crime Categories
            </h2>

            <p className="prose-body mb-4">
              The Clery Act regulation (34 CFR 668.46) lists the categories institutions must count and defines
              them. Open a section for the definitions in plain words; the{' '}
              <Link to="/methodology#definitions" className="link">
                Methodology page
              </Link>{' '}
              links to the official text and explains how institutions count.
            </p>

            <div className="border-t border-rule">
              <CollapsibleSection title="Criminal Offenses (11 categories)" defaultOpen>
                <div className="text-ui">
                  {CRIMINAL_DEFINITIONS.map((d) => (
                    <CrimeItem key={d.name} name={d.name} description={d.text} />
                  ))}
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="VAWA Offenses (3 categories)">
                <div className="text-ui">
                  {VAWA_DEFINITIONS.map((d) => (
                    <CrimeItem key={d.name} name={d.name} description={d.text} />
                  ))}
                </div>
                <p className="mt-3 text-meta text-ink-3">
                  Added to the Clery Act by the Violence Against Women Reauthorization Act of 2013; ED's final rule
                  took effect on July 1, 2015.
                </p>
              </CollapsibleSection>

              <CollapsibleSection title="Arrests & Disciplinary Referrals (3 categories each)">
                <div className="text-ui">
                  {LAW_VIOLATION_DEFINITIONS.map((d) => (
                    <CrimeItem key={d.name} name={d.name} description={d.text} />
                  ))}
                </div>
                <p className="mt-3 text-meta text-ink-3">
                  These count people, not incidents: people arrested, and people referred for campus disciplinary
                  action who were not arrested. A person both arrested and referred is counted once, as an arrest.
                </p>
              </CollapsibleSection>
            </div>
          </section>

          {/* Geographic Definitions */}
          <section>
            <h2 className="section-head">
              Geographic Definitions
            </h2>

            <div className="mb-6 grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
              {GEOGRAPHY_DEFINITIONS.map((item) => {
                const highlight = item.name === 'Residence halls'
                return (
                  <div
                    key={item.name}
                    className="border-t border-rule pt-3"
                  >
                    <h4 className="mb-1 text-ui font-semibold text-ink">
                      {item.name}
                      {highlight && <span className="ml-1 text-ink-2">*</span>}
                    </h4>
                    <p className="text-ui text-ink-2">{item.text}</p>
                  </div>
                )
              })}
            </div>

            <div className="border-l-2 border-rule-strong pl-4">
              <p className="text-ui font-semibold text-ink">
                Avoid Double-Counting
              </p>
              <p className="mt-1 text-ui text-ink-2">
                Residence hall incidents are a <em>subset</em> of on-campus totals.
                Our calculations exclude residence halls when summing totals.
              </p>
            </div>
          </section>

          {/* Methodology */}
          <section>
            <h2 className="section-head">
              How We Calculate
            </h2>

            <div className="mb-8 grid grid-cols-1 border-y border-rule sm:grid-cols-2">
              <div className="py-4 sm:pr-6">
                <div className="tabular text-figure font-semibold text-ink">
                  {typeof schoolCount === 'number' && schoolCount > 0 ? formatNumber(schoolCount) : '—'}
                </div>
                <div className="mt-1 text-ui font-semibold text-ink">Campuses</div>
                <p className="mt-1 text-meta text-ink-2">
                  Every campus that reported to DOE in at least one year{dataYears.span ? ` of ${dataYears.span}` : ''}; each has a school page
                </p>
              </div>
              <div className="border-t border-rule py-4 sm:border-l sm:border-t-0 sm:pl-6">
                <div className="tabular text-figure font-semibold text-ink">{dataYears.count ?? '—'}</div>
                <div className="mt-1 text-ui font-semibold text-ink">{dataYears.count === 1 ? 'Year' : 'Years'} of Data</div>
                <p className="mt-1 text-meta text-ink-2">
                  {dataYears.span ? `Calendar years ${dataYears.span}` : 'Every year in the published data'}
                </p>
              </div>
            </div>

            <div className="space-y-5">
              <div className="flex items-start gap-4">
                <span className="tabular w-5 flex-shrink-0 text-right font-serif text-heading font-semibold text-ink-3">1</span>
                <div>
                  <h4 className="text-ui font-semibold text-ink">Total Counts</h4>
                  <p className="text-ui text-ink-2">
                    Sum of on-campus + non-campus + public property (excluding residence halls to avoid double-counting)
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <span className="tabular w-5 flex-shrink-0 text-right font-serif text-heading font-semibold text-ink-3">2</span>
                <div>
                  <h4 className="text-ui font-semibold text-ink">Per 10k Rates</h4>
                  <p className="text-ui text-ink-2">
                    Incidents reported on campus at all of an institution's campuses in the United States over three
                    years, per 10,000 of its on-campus FTE a year (an estimate of its FTE without students enrolled
                    only online): a size-adjusted figure, not a measure of risk. Each rate has an interval and is
                    compared with the national rate; the largest institutions are also placed on ordered lists, unless
                    one of their years in the window is unusually high. How
                    all of this is done is described on the{' '}
                    <Link to="/methodology#rates" className="link">Methodology page</Link>.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <span className="tabular w-5 flex-shrink-0 text-right font-serif text-heading font-semibold text-ink-3">3</span>
                <div>
                  <h4 className="text-ui font-semibold text-ink">Percentages</h4>
                  <p className="text-ui text-ink-2">
                    Each school's share of the total for the selected ranking (national, a state or the Ivy League)
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Data Limitations */}
          <section>
            <h2 className="section-head">
              Important Limitations
            </h2>

            <p className="prose-body mb-5">
              A short version; the{' '}
              <Link to="/methodology#limitations" className="link">Methodology page</Link>{' '}
              has the full list and sources.
            </p>

            {/* Key point */}
            <div className="mb-6 border-l-2 border-accent pl-4">
              <p className="text-ui font-semibold text-ink">
                Higher reported numbers do not by themselves mean more danger
              </p>
              <p className="mt-1 text-ui text-ink-2">
                Clery figures count reports. A higher count can reflect more crime, more reporting, or both, and a
                lower count does not show that a campus is safer.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
              <LimitationCard
                title="Reporting Lag"
                description={describeReportingLag(dataYears.latest)}
              />
              <LimitationCard
                title="Counted by Year Reported"
                description="Each year counts crimes reported that year, including some that happened earlier. Many reports of past abuse at one school can make one year jump."
              />
              {/* Underreporting, with its source */}
              <div className="border-t border-rule pt-3 sm:col-span-2">
                <h4 className="text-ui font-semibold text-ink">Many Crimes Are Never Reported</h4>
                <p className="mt-1 text-ui text-ink-2">
                  Clery data counts only <strong className="font-semibold text-ink">reported</strong> incidents.
                  In the Bureau of Justice Statistics' analysis of the National Crime Victimization Survey, 80% of
                  rape and sexual assault victimizations of female college students aged 18-24 (1995-2013) were not
                  reported to police. That survey does not measure reports to campus officials, which Clery figures
                  also include.
                </p>
                <p className="mt-2 text-meta text-ink-3">
                  Source:{' '}
                  <a href={SOURCES.bjsCollege2014.url} target="_blank" rel="noopener noreferrer" className="link">
                    BJS, Rape and Sexual Assault Victimization Among College-Age Females, 1995-2013 (2014)
                  </a>
                </p>
              </div>
              <LimitationCard
                title="Reporting Varies by School"
                description="Each institution classifies incidents, designates who receives reports and maps its own campus, so the same incidents can be reported differently."
              />
              <LimitationCard
                title="Definitions"
                description="The current categories took effect with ED's VAWA rule on July 1, 2015. This site starts in 2015; do not join its figures with earlier years."
              />
              <LimitationCard
                title="FTE Data Limited"
                description={fteAvailabilityText}
              />
              <LimitationCard
                title="What is FTE?"
                description="Full-time equivalent fall enrollment from NCES: full-time students plus part-time students weighted by factors that depend on the type of institution and student. It counts enrolled students only, for the whole institution."
              />
              <LimitationCard
                title="Small Numbers Swing"
                description={
                  'Rates average three years, and every rate has an interval (Methodology page). One incident more or less can still move a small school\'s rate a lot, so only institutions large enough to expect ' +
                  (metadata?.rateRules?.lists?.minExpected !== undefined
                    ? `at least ${metadata.rateRules.lists.minExpected} incidents at the national rate`
                    : 'enough incidents at the national rate') +
                  ' are placed on the ordered lists, and an institution with an unusually high year in the window is not placed.'
                }
              />
              <LimitationCard
                title="Geographic Context"
                description="Urban and rural campuses differ: public property next to a city campus is not comparable with a rural one."
              />
            </div>
          </section>

          {/* Call to explore */}
          <section className="border-y border-rule py-8">
            <h2 className="h2 mb-2">
              Ready to Explore?
            </h2>
            <p className="mb-5 max-w-md text-ui text-ink-2">
              View rankings, trends, and detailed breakdowns for thousands of U.S. colleges.
            </p>
            <Link
              to="/"
              className="btn-primary"
            >
              View Rankings
            </Link>
          </section>

          {/* Open Source */}
          <section>
            <h2 className="section-head">
              Open Source
            </h2>
            <div className="prose-body">
              <p>
                CollegeSafetyData is fully open source. Our data pipeline, methodology,
                and this website are publicly available for review, audit, and contribution.
              </p>
              <p>
                We welcome collaboration from researchers, journalists, and developers
                who want to improve campus safety transparency.
              </p>
            </div>
            <a
              href="https://github.com/kbdevopz/collegesafetydata-public"
              target="_blank"
              rel="noopener noreferrer"
              className="link mt-4 inline-flex min-h-[1.5rem] items-center gap-1 text-ui font-semibold"
            >
              <span>View on GitHub</span>
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          </section>

          {/* Resources */}
          <section>
            <h2 className="section-head">
              Additional Resources
            </h2>
            <ul className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
              {[
                {
                  href: "https://clerycenter.org/",
                  title: "Clery Center",
                  desc: "Nonprofit focused on campus safety"
                },
                {
                  href: SOURCES.edCampusSecurity.url,
                  title: "ED Campus Security",
                  desc: "Official guidance: the Clery Act Appendix and the 2016 Handbook"
                },
                {
                  href: SOURCES.reg66846.url,
                  title: "34 CFR 668.46",
                  desc: "The Clery Act regulation and its definitions"
                },
                {
                  href: SOURCES.vawaRule2014.url,
                  title: "VAWA Final Rule (2014)",
                  desc: "Regulations adding VAWA offenses, effective July 1, 2015"
                },
                {
                  href: "https://ucr.fbi.gov/crime-in-the-u.s",
                  title: "FBI UCR Program",
                  desc: "National crime reporting standards"
                },
              ].map((link) => (
                <li key={link.href} className="border-b border-rule">
                  <a
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group block py-3"
                  >
                    <div className="inline-flex items-center gap-1 font-semibold text-ink underline decoration-rule-strong/60 underline-offset-[3px] group-hover:text-accent group-hover:decoration-current">
                      {link.title}
                      <ExternalLink className="h-3.5 w-3.5 text-ink-3" aria-hidden="true" />
                    </div>
                    <div className="text-meta text-ink-2">
                      {link.desc}
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          </section>

          {/* Contact & Feedback */}
          <section>
            <h2 className="section-head">
              Contact & Feedback
            </h2>
            <p className="prose-body">
              We welcome feedback, bug reports, and collaboration inquiries from researchers, journalists, and the public.
            </p>
            <div className="mt-4 flex flex-col items-start gap-2 text-ui">
              <a
                href="mailto:contact@collegesafetydata.org"
                className="link inline-flex min-h-[1.5rem] items-center font-semibold"
              >
                <span>contact@collegesafetydata.org</span>
              </a>
              <a
                href="https://github.com/kbdevopz/collegesafetydata-public/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="link inline-flex min-h-[1.5rem] items-center gap-1 font-semibold"
              >
                <span>Report an issue on GitHub</span>
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
