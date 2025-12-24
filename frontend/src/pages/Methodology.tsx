import React from 'react'
import {
  ExternalLink,
  Database,
  Calculator,
  MapPin,
  BarChart3,
  FileText,
  Shield,
  CheckCircle,
  BookOpen,
  Download,
  AlertTriangle,
  Info,
  Users,
} from 'lucide-react'
import { getMetadata } from '../lib/api'
import type { Metadata } from '../lib/types'
import { formatDate } from '../lib/utils'

export default function Methodology() {
  const [metadata, setMetadata] = React.useState<Metadata | null>(null)

  React.useEffect(() => {
    getMetadata().then(setMetadata).catch(console.error)
  }, [])

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="bg-gradient-to-b from-primary-50 to-white dark:from-gray-900 dark:to-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:8 py-12 sm:py-16">
          <div className="max-w-3xl mx-auto text-center">
            <div className="flex items-center justify-center gap-3 mb-4">
              <BookOpen className="w-8 h-8 text-primary-600 dark:text-primary-400" />
              <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-gray-100">
                Data Methodology
              </h1>
            </div>
            <p className="text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
              Detailed information about our data sources, calculations, and quality assurance processes.
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:8 py-12">
        <div className="max-w-3xl mx-auto space-y-16">

          {/* Data Sources */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Database className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data Sources
              </h2>
            </div>

            <div className="space-y-4">
              {/* Campus Crime Data */}
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center flex-shrink-0">
                    <Shield className="w-6 h-6 text-red-600 dark:text-red-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      Campus Crime Data
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                      U.S. Department of Education Campus Safety and Security Data
                    </p>
                    <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600 dark:text-gray-400 mb-3">
                      <span>Source: <strong className="text-gray-900 dark:text-gray-200">DOE OPE</strong></span>
                      <span>Legal Basis: <strong className="text-gray-900 dark:text-gray-200">Clery Act</strong></span>
                      <span>Coverage: <strong className="text-gray-900 dark:text-gray-200">2015-2023</strong></span>
                    </div>
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
              </div>

              {/* Enrollment Data */}
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                    <Users className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      Enrollment Data (FTE)
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                      IPEDS (Integrated Postsecondary Education Data System)
                    </p>
                    <div className="space-y-3 text-sm">
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">2021-2023:</strong> IPEDS provides pre-calculated FTE values directly — we use the official published numbers.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">2015-2020:</strong> Pre-calculated FTE isn't available, so we calculate it ourselves from raw enrollment data (full-time and part-time students) using the official IPEDS formula — the same method the government uses.
                        </span>
                      </div>
                    </div>
                    <a
                      href="https://nces.ed.gov/ipeds/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 mt-3"
                    >
                      nces.ed.gov/ipeds
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* FTE Calculation */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Calculator className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                FTE (Full-Time Equivalent) Calculation
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              FTE is used as the denominator for calculating per-student crime rates, enabling fair comparisons between institutions of different sizes.
            </p>

            {/* Formula Box */}
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 rounded-xl p-6 border border-blue-100 dark:border-blue-900/50 mb-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Official IPEDS Formula (2015-2020)</h4>
              <code className="block bg-white dark:bg-gray-900 rounded-lg p-4 text-sm text-gray-800 dark:text-gray-200 font-mono">
                FTE = FT_Undergrad + FT_Graduate<br />
                &nbsp;&nbsp;&nbsp;&nbsp;+ (PT_Undergrad × 0.403543)<br />
                &nbsp;&nbsp;&nbsp;&nbsp;+ (PT_Graduate × 0.361702)
              </code>
            </div>

            {/* Conversion Factors Table */}
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden mb-6">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-gray-900 dark:text-gray-100">Student Type</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-900 dark:text-gray-100">Factor</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-900 dark:text-gray-100">Interpretation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  <tr>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">Full-time Undergraduate</td>
                    <td className="px-4 py-3 font-mono text-gray-900 dark:text-gray-100">1.0</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">Counts as 1.0 FTE</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">Full-time Graduate</td>
                    <td className="px-4 py-3 font-mono text-gray-900 dark:text-gray-100">1.0</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">Counts as 1.0 FTE</td>
                  </tr>
                  <tr className="bg-primary-50 dark:bg-primary-900/20">
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">Part-time Undergraduate</td>
                    <td className="px-4 py-3 font-mono text-primary-700 dark:text-primary-300 font-semibold">0.403543</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">~40% of full-time load</td>
                  </tr>
                  <tr className="bg-primary-50 dark:bg-primary-900/20">
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">Part-time Graduate</td>
                    <td className="px-4 py-3 font-mono text-primary-700 dark:text-primary-300 font-semibold">0.361702</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">~36% of full-time load</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="text-xs text-gray-500 dark:text-gray-500">
              <strong>Source:</strong> NCES IPEDS Survey Methodology —{' '}
              <a href="https://nces.ed.gov/ipeds/survey-components/8" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-300">
                nces.ed.gov/ipeds/survey-components/8
              </a>
            </p>
          </section>

          {/* Crime Rate Calculation */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Crime Rate Calculation
              </h2>
            </div>

            <div className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl p-6 border border-green-100 dark:border-green-900/50 mb-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Per 10,000 Students</h4>
              <code className="block bg-white dark:bg-gray-900 rounded-lg p-4 text-sm text-gray-800 dark:text-gray-200 font-mono mb-3">
                Rate = (Incident Count / FTE) × 10,000
              </code>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                This rate standardization allows for fair comparison between institutions of different sizes.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Total Counts</h5>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Sum of on-campus + non-campus + public property (excluding residence halls to avoid double-counting)
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Rate Display Threshold</h5>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Rates only displayed for institutions with FTE ≥ 1,000 to avoid misleading statistics
                </p>
              </div>
            </div>
          </section>

          {/* Geographic Classifications */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <MapPin className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Geographic Classifications
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              {[
                { title: "On-Campus", desc: "All property owned or controlled by the institution" },
                { title: "Residence Halls", desc: "Student housing (subset of on-campus)" },
                { title: "Non-Campus", desc: "Property owned but not contiguous to campus" },
                { title: "Public Property", desc: "Public areas adjacent to campus" },
              ].map((item, i) => (
                <div
                  key={i}
                  className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4"
                >
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-1">
                    {item.title}
                  </h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{item.desc}</p>
                </div>
              ))}
            </div>

            <div className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-800 dark:text-amber-300">
                <strong>Important:</strong> Residence hall incidents are a <em>subset</em> of on-campus incidents.
                Our calculations exclude residence halls when summing totals to avoid double-counting.
              </p>
            </div>
          </section>

          {/* Offense Categories */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Offense Categories
              </h2>
            </div>

            <div className="space-y-4">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Criminal Offenses (11)</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Traditional serious crimes reported under the Clery Act:
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-700 dark:text-gray-300">
                  <span>• Murder/Non-negligent Manslaughter</span>
                  <span>• Rape</span>
                  <span>• Manslaughter by Negligence</span>
                  <span>• Fondling</span>
                  <span>• Robbery</span>
                  <span>• Incest</span>
                  <span>• Aggravated Assault</span>
                  <span>• Statutory Rape</span>
                  <span>• Burglary</span>
                  <span>• Motor Vehicle Theft</span>
                  <span></span>
                  <span>• Arson</span>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">VAWA Offenses (3)</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Added in 2014 under the Violence Against Women Act:
                </p>
                <div className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
                  <span>• Domestic Violence</span>
                  <span>• Dating Violence</span>
                  <span>• Stalking</span>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Arrests & Disciplinary Actions (3)</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Includes both arrests and campus disciplinary referrals:
                </p>
                <div className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
                  <span>• Weapons Violations</span>
                  <span>• Drug Law Violations</span>
                  <span>• Liquor Law Violations</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
                  Note: High counts in these categories may reflect enforcement practices rather than safety levels.
                </p>
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
                Data Limitations
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Understanding these limitations is essential for interpreting the data correctly.
            </p>

            {/* Key Insight */}
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
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Underreporting</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  ~80% of campus crimes are never reported. Only 20% of sexual assaults are reported (RAINN).
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Reporting Lag</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  DOE releases data ~1 year late. Current data contains 2015-2023 statistics.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Institutional Variation</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Reporting practices, police staffing, and definitions may vary by institution.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Definition Changes</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  FBI rape definition changed in 2013; VAWA offenses added in 2014.
                </p>
              </div>
            </div>
          </section>

          {/* Data Audit Download */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <FileText className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data Quality Audit
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              We maintain a comprehensive data quality audit that validates all 8,600+ schools in our dataset.
              The audit checks for data completeness, accuracy, and consistency.
            </p>

            <div className="bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-950/50 dark:to-primary-900/30 rounded-xl p-6 border border-primary-200 dark:border-primary-800">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <h4 className="font-semibold text-primary-900 dark:text-primary-100 mb-2">
                    Download Full Audit Report
                  </h4>
                  <p className="text-sm text-primary-700 dark:text-primary-300 mb-4">
                    Machine-readable JSON file containing validation results for all schools,
                    including coverage statistics, rate calculation accuracy, and ranking order validation.
                  </p>
                  <div className="flex flex-wrap gap-4 text-sm text-primary-700 dark:text-primary-300">
                    <span>Format: <strong>JSON</strong></span>
                    <span>Schools: <strong>8,683</strong></span>
                    <span>Last Updated: <strong>{metadata ? formatDate(metadata.lastUpdated) : 'Loading...'}</strong></span>
                  </div>
                </div>
                <a
                  href="/audit.json"
                  download="collegesafetydata-audit.json"
                  className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 dark:bg-primary-500 dark:hover:bg-primary-600 text-white font-medium rounded-lg shadow-md transition-all hover:shadow-lg"
                >
                  <Download className="w-4 h-4" />
                  <span>Download</span>
                </a>
              </div>
            </div>

            <div className="mt-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
              <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-3">Audit Checks Performed:</h5>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                {[
                  "School completeness (all schools have JSON files)",
                  "Incident total accuracy (JSON matches aggregates)",
                  "FTE coverage by year",
                  "Rate calculation verification",
                  "Ranking order validation",
                  "Percentage sum validation",
                  "Source traceability",
                ].map((check, i) => (
                  <div key={i} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                    <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                    <span>{check}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Source Code Reference */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-gray-100 dark:bg-gray-800 rounded-xl flex items-center justify-center">
                <FileText className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Source Code
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-4">
              The complete ETL (Extract, Transform, Load) pipeline is open source and available for inspection.
            </p>

            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 font-mono text-sm">
              <div className="space-y-1 text-gray-700 dark:text-gray-300">
                <div>etl/01_download_raw_data.py — Download DOE data</div>
                <div>etl/01b_download_ipeds.py — Download IPEDS enrollment</div>
                <div>etl/02a_transform_enrollment.py — Process DRVEF FTE (2021-2023)</div>
                <div>etl/02b_transform_ef_enrollment.py — Calculate FTE from EF (2015-2020)</div>
                <div>etl/03_transform_to_parquet.py — Transform crime data</div>
                <div>etl/04_create_aggregates.py — Create aggregated tables</div>
                <div>etl/05_generate_json.py — Generate JSON outputs</div>
                <div>etl/07_comprehensive_audit.py — Run data quality audit</div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
