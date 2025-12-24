import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ExternalLink,
  Database,
  Shield,
  BarChart3,
  FileText,
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  Clock,
  Users,
  Calculator,
  MapPin,
  Info,
} from 'lucide-react'
import { getMetadata } from '../lib/api'
import type { Metadata } from '../lib/types'
import { formatDate, cn } from '../lib/utils'

// Collapsible section component
function CollapsibleSection({
  title,
  children,
  defaultOpen = false
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-left"
      >
        <span className="font-medium text-gray-900 dark:text-gray-100">{title}</span>
        <ChevronDown
          className={cn(
            "w-5 h-5 text-gray-500 transition-transform duration-200",
            isOpen && "rotate-180"
          )}
        />
      </button>
      <div
        className={cn(
          "overflow-hidden transition-all duration-200",
          isOpen ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="px-4 py-4 bg-white dark:bg-gray-900">
          {children}
        </div>
      </div>
    </div>
  )
}

// Crime category item
function CrimeItem({ name, description }: { name: string; description: string }) {
  return (
    <div className="flex gap-3 py-2">
      <div className="w-1.5 h-1.5 rounded-full bg-primary-500 dark:bg-primary-400 mt-2 flex-shrink-0" />
      <div>
        <span className="font-medium text-gray-900 dark:text-gray-100">{name}</span>
        <span className="text-gray-600 dark:text-gray-400"> — {description}</span>
      </div>
    </div>
  )
}

// Limitation card
function LimitationCard({
  icon: Icon,
  title,
  description
}: {
  icon: React.ElementType
  title: string
  description: string
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">{title}</h4>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{description}</p>
        </div>
      </div>
    </div>
  )
}

export default function About() {
  const [metadata, setMetadata] = useState<Metadata | null>(null)

  useEffect(() => {
    getMetadata().then(setMetadata).catch(console.error)
  }, [])

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
              About CollegeSafetyData
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              Free, public access to campus crime statistics reported under the
              Jeanne Clery Act — making college safety data transparent and accessible.
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto space-y-16">

          {/* What is the Clery Act */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                What is the Clery Act?
              </h2>
            </div>

            <div className="space-y-4 text-gray-600 dark:text-gray-400">
              <p className="leading-relaxed">
                The Clery Act is a federal law requiring colleges and universities
                participating in federal financial aid programs to disclose campus crime information.
              </p>
              <p className="leading-relaxed">
                Named after <strong className="text-gray-900 dark:text-gray-200">Jeanne Clery</strong>,
                who was murdered in her dorm room at Lehigh University in 1986, the Act ensures
                transparency about campus safety.
              </p>
            </div>

            {/* Requirements Grid */}
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { text: "Publish Annual Security Reports with 3 years of crime data" },
                { text: "Report specific crime categories for campus areas" },
                { text: "Issue timely warnings about safety threats" },
                { text: "Maintain a public daily crime log" },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                  <CheckCircle className="w-5 h-5 text-green-500 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">{item.text}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Data Source */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Database className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data Source
              </h2>
            </div>

            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 rounded-xl p-6 border border-blue-100 dark:border-blue-900/50">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-white dark:bg-gray-800 shadow-sm flex items-center justify-center flex-shrink-0">
                  <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                    U.S. Department of Education
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    Campus Safety and Security Database
                  </p>
                  <a
                    href="https://ope.ed.gov/campussafety/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
                  >
                    ope.ed.gov/campussafety
                    <ExternalLink className="w-4 h-4" />
                  </a>
                </div>
              </div>
              {metadata && (
                <div className="mt-4 pt-4 border-t border-blue-200/50 dark:border-blue-800/50 flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600 dark:text-gray-400">
                  <span>Coverage: <strong className="text-gray-900 dark:text-gray-200">{metadata.coverage}</strong></span>
                  <span>Updated: <strong className="text-gray-900 dark:text-gray-200">{formatDate(metadata.lastUpdated)}</strong></span>
                </div>
              )}
            </div>
          </section>

          {/* Crime Categories - Collapsible */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Crime Categories
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              The Clery Act requires reporting of specific crime categories.
              Click each section to view definitions.
            </p>

            <div className="space-y-3">
              <CollapsibleSection title="Criminal Offenses (11 categories)" defaultOpen>
                <div className="space-y-1 text-sm">
                  <CrimeItem name="Murder/Non-negligent Manslaughter" description="Willful killing of one human being by another" />
                  <CrimeItem name="Manslaughter by Negligence" description="Killing through gross negligence" />
                  <CrimeItem name="Rape" description="Penetration without consent (FBI definition since 2013)" />
                  <CrimeItem name="Fondling" description="Touching of private body parts for sexual gratification" />
                  <CrimeItem name="Incest" description="Sexual intercourse between persons related by law" />
                  <CrimeItem name="Statutory Rape" description="Sexual intercourse with person under age of consent" />
                  <CrimeItem name="Robbery" description="Taking something of value by force or threat" />
                  <CrimeItem name="Aggravated Assault" description="Attack with intent to cause severe injury" />
                  <CrimeItem name="Burglary" description="Unlawful entry to commit a felony or theft" />
                  <CrimeItem name="Motor Vehicle Theft" description="Theft or attempted theft of a vehicle" />
                  <CrimeItem name="Arson" description="Willful burning of property" />
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="VAWA Offenses (3 categories)">
                <div className="space-y-1 text-sm">
                  <CrimeItem name="Domestic Violence" description="Violence by current/former spouse or partner" />
                  <CrimeItem name="Dating Violence" description="Violence in romantic/intimate relationships" />
                  <CrimeItem name="Stalking" description="Course of conduct causing fear for safety" />
                </div>
                <p className="mt-3 text-xs text-gray-500 dark:text-gray-500">
                  VAWA = Violence Against Women Act, added to Clery reporting in 2014
                </p>
              </CollapsibleSection>

              <CollapsibleSection title="Arrests & Disciplinary Actions (3 categories)">
                <div className="space-y-1 text-sm">
                  <CrimeItem name="Weapons Violations" description="Illegal possession, sale, or use of weapons" />
                  <CrimeItem name="Drug Violations" description="Drug abuse violations (possession, sale, use)" />
                  <CrimeItem name="Liquor Violations" description="Liquor law violations (not public intoxication)" />
                </div>
                <p className="mt-3 text-xs text-gray-500 dark:text-gray-500">
                  Includes both arrests and disciplinary referrals
                </p>
              </CollapsibleSection>
            </div>
          </section>

          {/* Geographic Definitions */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <MapPin className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Geographic Definitions
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              {[
                {
                  title: "On-Campus",
                  desc: "Buildings or property owned/controlled by the institution",
                  highlight: false
                },
                {
                  title: "Residence Halls",
                  desc: "Student residential facilities (subset of on-campus)",
                  highlight: true
                },
                {
                  title: "Non-Campus",
                  desc: "Off-site buildings controlled by institution (satellites, research)",
                  highlight: false
                },
                {
                  title: "Public Property",
                  desc: "Adjacent public areas (sidewalks, streets, parks)",
                  highlight: false
                },
              ].map((item, i) => (
                <div
                  key={i}
                  className={cn(
                    "rounded-lg p-4 border",
                    item.highlight
                      ? "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800"
                      : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800"
                  )}
                >
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-1">
                    {item.title}
                    {item.highlight && <span className="text-amber-600 dark:text-amber-400 ml-1">*</span>}
                  </h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{item.desc}</p>
                </div>
              ))}
            </div>

            <div className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-300 text-sm">
                  Avoid Double-Counting
                </p>
                <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                  Residence hall incidents are a <em>subset</em> of on-campus totals.
                  Our calculations exclude residence halls when summing totals.
                </p>
              </div>
            </div>
          </section>

          {/* Methodology */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Calculator className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                How We Calculate
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
                <div className="text-3xl font-bold text-primary-600 dark:text-primary-400 mb-2">6,000+</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Schools Covered</div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">All U.S. colleges reporting Clery data</p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
                <div className="text-3xl font-bold text-primary-600 dark:text-primary-400 mb-2">9</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Years of Data</div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">2015-2023 for consistency</p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
                <div className="text-3xl font-bold text-primary-600 dark:text-primary-400 mb-2">1,000+</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">FTE Minimum</div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">For rate-based rankings</p>
              </div>
            </div>

            <div className="space-y-3 mb-8">
              <div className="flex items-start gap-3 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className="w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-xs font-bold text-primary-600 dark:text-primary-400">1</span>
                </div>
                <div>
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">Total Counts</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Sum of on-campus + non-campus + public property (excluding residence halls to avoid double-counting)
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className="w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-xs font-bold text-primary-600 dark:text-primary-400">2</span>
                </div>
                <div>
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">Per 10k Rates</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Incidents per 10,000 FTE students — enables fair comparison between schools of different sizes
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
                <div className="w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-xs font-bold text-primary-600 dark:text-primary-400">3</span>
                </div>
                <div>
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">Percentages</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Each school's share of total incidents within the selected filter group (state, region, etc.)
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Data Limitations */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/50 rounded-xl flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Important Limitations
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Understanding these limitations is essential for interpreting the data correctly.
            </p>

            {/* Key Insight Callout */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    Key insight: Higher reported numbers ≠ more dangerous
                  </p>
                  <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                    Schools with robust reporting systems, campus police, and survivor support services often have
                    higher reported numbers—which can indicate a healthier reporting culture, not more crime.
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <LimitationCard
                icon={Clock}
                title="Reporting Lag"
                description="DOE releases data ~1 year late. '2024 data' contains 2021-2023 statistics."
              />
              <LimitationCard
                icon={Users}
                title="Reporting Varies by School"
                description="Higher numbers may indicate better reporting, not more crime. Lower numbers ≠ safer."
              />
              {/* Expanded Underreporting Section with Statistics */}
              <div className="col-span-1 sm:col-span-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4 border border-amber-200 dark:border-amber-800">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
                    <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm">Significant Underreporting</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 mb-3">
                      Clery data represents only <strong className="text-gray-900 dark:text-gray-200">reported</strong> incidents.
                      Research indicates most campus crimes go unreported:
                    </p>
                    <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1.5 ml-4 list-disc">
                      <li><strong className="text-gray-900 dark:text-gray-200">~80%</strong> of campus crimes are never reported to authorities (DOJ NCVS)</li>
                      <li><strong className="text-gray-900 dark:text-gray-200">Only 20%</strong> of college sexual assaults are reported (RAINN)</li>
                      <li><strong className="text-gray-900 dark:text-gray-200">Higher numbers may indicate better reporting culture</strong>, not more crime</li>
                    </ul>
                    <div className="mt-3 text-xs text-gray-500 dark:text-gray-500">
                      Sources:{' '}
                      <a href="https://www.rainn.org/statistics/campus-sexual-violence" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-300">RAINN</a>,{' '}
                      <a href="https://bjs.ojp.gov/library/publications/rape-and-sexual-assault-victimization-among-college-age-females-1995-2013" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-300">DOJ Bureau of Justice Statistics</a>
                    </div>
                  </div>
                </div>
              </div>
              <LimitationCard
                icon={FileText}
                title="Definition Changes"
                description="FBI rape definition changed in 2013; VAWA added in 2014. Pre-2015 data differs."
              />
              <LimitationCard
                icon={Calculator}
                title="FTE Data Limited"
                description="Rate calculations use IPEDS FTE data, only available for 2021-2023."
              />
              <LimitationCard
                icon={Info}
                title="What is FTE?"
                description="Full-Time Equivalent: full-time = 1.0, part-time ≈ 0.33. Standardized enrollment measure."
              />
              <LimitationCard
                icon={BarChart3}
                title="Small School Volatility"
                description="Rates for <1,000 students or <10 incidents can be misleading. Look for * markers."
              />
              <LimitationCard
                icon={MapPin}
                title="Geographic Context"
                description="Urban vs rural campuses have different contexts. NYC 'public property' ≠ rural Vermont."
              />
            </div>
          </section>

          {/* CTA */}
          <section className="bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-950/50 dark:to-primary-900/30 rounded-2xl p-8 sm:p-10 text-center border border-primary-200 dark:border-primary-800">
            <h2 className="text-2xl font-bold text-primary-900 dark:text-primary-100 mb-3">
              Ready to Explore?
            </h2>
            <p className="text-primary-700 dark:text-primary-300 mb-6 max-w-md mx-auto">
              View rankings, trends, and detailed breakdowns for thousands of U.S. colleges.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 hover:bg-primary-700 dark:bg-primary-500 dark:hover:bg-primary-600 text-white font-medium rounded-xl shadow-lg shadow-primary-500/25 transition-all hover:shadow-xl hover:shadow-primary-500/30 hover:-translate-y-0.5"
            >
              <BarChart3 className="w-5 h-5" />
              View Rankings
            </Link>
          </section>

          {/* Resources */}
          <section>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
              Additional Resources
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                {
                  href: "https://clerycenter.org/",
                  title: "Clery Center",
                  desc: "Nonprofit focused on campus safety"
                },
                {
                  href: "https://www2.ed.gov/admins/lead/safety/campus.html",
                  title: "DOE Campus Safety",
                  desc: "Official guidance and resources"
                },
                {
                  href: "https://www.federalregister.gov/documents/2014/10/20/2014-24284/violence-against-women-act",
                  title: "VAWA Final Rule",
                  desc: "2014 regulations adding VAWA offenses"
                },
                {
                  href: "https://ucr.fbi.gov/crime-in-the-u.s",
                  title: "FBI UCR Program",
                  desc: "National crime reporting standards"
                },
              ].map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-md transition-all flex items-start gap-3"
                >
                  <div className="w-10 h-10 rounded-lg bg-gray-100 dark:bg-gray-800 group-hover:bg-primary-100 dark:group-hover:bg-primary-900/50 flex items-center justify-center flex-shrink-0 transition-colors">
                    <ExternalLink className="w-5 h-5 text-gray-400 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors" />
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                      {link.title}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {link.desc}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
