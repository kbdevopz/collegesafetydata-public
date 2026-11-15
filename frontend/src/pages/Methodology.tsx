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
  Calendar,
} from 'lucide-react'
import { cachedMetadata, getMetadata } from '../lib/api'
import type { Metadata } from '../lib/types'
import { formatDate, formatNumber } from '../lib/utils'
import { summarizeEnrollmentStatus, describeEnrollmentStatus } from '../lib/enrollment'
import { summarizeDataYears } from '../lib/coverage'
import { countInterval, ratioPercent } from '../lib/rates'
import SourceLink from '../components/SourceLink'
import CiteThisData from '../components/CiteThisData'
import { useBuildInfo } from '../lib/build'
import { SERIES_NOTES, SERIES_CONTEXT } from '../data/seriesNotes'
import { Link, useLocation } from 'react-router-dom'

// The Limitations section, in reading order
const LIMITATIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: 'Reports, not how often crimes happen',
    body: (
      <>
        Clery figures count crimes reported to campus security authorities or police, not victimization. Many
        crimes are never reported: in the Bureau of Justice Statistics' analysis of the National Crime
        Victimization Survey, 80% of rape and sexual assault victimizations of female college students aged 18-24
        (1995-2013) were not reported to police (
        <SourceLink source={SOURCES.bjsCollege2014}>BJS, NCJ 248471</SourceLink>). That survey does not measure
        reports to campus officials, which Clery figures include, so the share is not a Clery figure. A higher count
        can mean more crime, more reporting, or both; a lower count does not show that a campus is safer.
      </>
    ),
  },
  {
    title: 'Counted by the year reported',
    body: (
      <>
        A year's figure is the crimes reported that year, including some that happened earlier. Many reports of
        past abuse at one institution can make one year jump (see{' '}
        <a href="#year-reported" className="underline">How Institutions Count</a>).
      </>
    ),
  },
  {
    title: 'Institutions classify, count and map differently',
    body: (
      <>
        Each institution decides which incidents fit which category, who its campus security authorities are,
        and which buildings and streets are its campus, noncampus and public property. ED's 2020 Appendix says ED
        will accept an institution's reasonable interpretation of terms and applies no measurable distance to a
        campus's "reasonably contiguous geographic area". Two institutions with the same incidents can report
        different figures, and public property next to a city campus is not comparable with a rural one.
      </>
    ),
  },
  {
    title: 'Rates are per enrolled student, not per person on campus',
    body: (
      <>
        Rates divide by an estimate of the institution's on-campus FTE, made from NCES's FTE, headcounts and
        share of students enrolled exclusively online; when its two estimates differ by more than 25%, the rate
        is not ranked. Rates do not count residents who are not students, employees, visitors or patients, or how
        many students live on campus, and FTE is per institution, not per campus. For this reason rate rankings
        leave out institutions with a hospital and special-focus medical and research institutions, and do not
        rank a rate when a quarter or more of its incidents were at one of 13 listed medical-center campuses
        (see <a href="#rate-rules" className="underline">Rate Rules</a>). Other institutions' Clery geography
        can also include places used mostly by people who are not their students, such as a clinic or a medical
        center not on that list, and there the rate per student says little about risk to a student.
      </>
    ),
  },
  {
    title: 'Small numbers swing',
    body: (
      <>
        Rate rankings rank only rates built on at least 20 incidents, and show each rate's 95% interval and the
        range of ranks it allows (see <a href="#rate-rules" className="underline">Rate Rules</a>). A rate on fewer
        incidents is shown but not ranked: one or two incidents more or less change it a lot, and a small
        institution's rate can change several-fold from one year to the next. Large counts are uncertain too:
        institutions' yearly counts vary more than chance alone would make them vary, so the interval of 1,000
        violent crimes runs from 534 to 1,706 (Rate Rules 6). Treat ranks inside one range as ties.
      </>
    ),
  },
  {
    title: 'A rate of 0 is a reported zero',
    body: (
      <>
        An institution listed with rate 0 reported no incident of that category that year at any of its
        campuses; its interval still runs above 0, and it is listed after the ranked rates, not ranked. A zero
        can reflect how an institution classifies or reports incidents, not only how safe it is, and a small
        institution can have 0 by chance. A year a campus did not report is not 0: it has no figures and is
        not in rankings.
      </>
    ),
  },
  {
    title: 'Rates leave out campuses abroad',
    body: (
      <>
        NCES's fall enrollment excludes students enrolled at an institution's branch campuses in foreign
        countries (<SourceLink source={SOURCES.ncesFallEnrollment2024}>NCES, Fall Enrollment instructions</SourceLink>),
        so an institution's rate leaves out the incidents at its campuses abroad (see{' '}
        <a href="#rate-rules" className="underline">Rate Rules</a>). Those incidents are on each such campus's
        own school page.
      </>
    ),
  },
  {
    title: 'Totals add unlike crimes',
    body: (
      <>
        "All criminal offenses" adds the 11 offenses with equal weight: a murder and a motor vehicle theft each
        count 1. In this data, motor vehicle theft was about 15% of the national total in 2015 and about 37% in
        2024, so much of the recent rise in that total is vehicle theft. For this reason rankings open on violent
        crimes. Look at single offenses before drawing conclusions from a total.
      </>
    ),
  },
  {
    title: 'Reported by institutions, not audited here',
    body: (
      <>
        The figures are what institutions submitted to ED's survey, as ED publishes them. This site does not check
        them against institutions' records or Annual Security Reports. Its audit checks that the published files
        are consistent with the pipeline's tables built from DOE's and NCES's files; it does not verify what
        institutions reported.
      </>
    ),
  },
  {
    title: 'Not every Clery category is shown',
    body: (
      <>
        Hate crimes, unfounded reports and fire statistics are not shown (see{' '}
        <a href="#not-shown" className="underline">What This Site Does Not Show</a>).
      </>
    ),
  },
]

// Campuses whose figures for `year` come from a release with a known DOE
// file error (metadata.json "knownDefects"), or null when not published
function defectCampuses(metadata: Metadata | null, year: number): number | null {
  const ds = metadata?.knownDefects?.filter((d) => d.year === year)
  if (!ds || ds.length === 0) return null
  return new Set(ds.flatMap((d) => d.unitids)).size
}
import {
  SOURCES,
  CRIMINAL_DEFINITIONS,
  VAWA_DEFINITIONS,
  LAW_VIOLATION_DEFINITIONS,
  GEOGRAPHY_DEFINITIONS,
} from '../data/sources'

export default function Methodology() {
  const [metadata, setMetadata] = React.useState<Metadata | null>(cachedMetadata)
  const build = useBuildInfo()

  React.useEffect(() => {
    getMetadata().then(setMetadata).catch(console.error)
  }, [])

  // Links such as /methodology#series-breaks: scroll to the section once
  // the page is drawn (after the app's scroll to the top on navigation)
  const { hash } = useLocation()
  React.useEffect(() => {
    if (!hash) return
    const id = decodeURIComponent(hash.slice(1))
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView(), 50)
    return () => window.clearTimeout(t)
  }, [hash])

  // Which falls have final, provisional or no enrollment yet, from
  // metadata.json "enrollmentStatus" (neutral wording when it is absent)
  const enrollmentStatusText = describeEnrollmentStatus(summarizeEnrollmentStatus(metadata))
  const schoolCount = metadata?.presets.find((p) => p.id === 'national')?.schoolCount
  // Year span from metadata.json "coverage" (or "years" when it is absent)
  const coverageText = metadata ? metadata.coverage || summarizeDataYears(metadata).span : null

  // The rate rules and what they did (metadata.json rateRules and
  // rateStats), for Rate Rules; "…" until metadata.json is loaded
  const rr = metadata?.rateRules
  const rs = metadata?.rateStats
  const iy = rs?.institutionYears
  const y24 = rs?.byYear['2024']
  const ci = Math.round((rr?.ciLevel ?? 0.95) * 100)
  const num = (v: number | null | undefined) => (v === null || v === undefined ? '…' : formatNumber(v))
  const share = (r: [number, number] | undefined, above = false) => (r ? ratioPercent(r, above) : '…')
  const group = (g: string) => rr?.dispersion.groups[g]
  const example = (code: string, n: number) => rs?.intervalExamples[code]?.[String(n)]
  // "8.6 to 39.4": a count's interval to 1 decimal ("0" for 0)
  const oneDecimal = (x: number) => (x === 0 ? '0' : x.toFixed(1))
  const intervalPair = (p: [number, number] | undefined) => (p ? `${oneDecimal(p[0])} to ${oneDecimal(p[1])}` : '…')
  // The interval of 1,000 incidents of `code`, and how far it runs below and above
  const wide = (code: string) => {
    const k = rr?.dispersion.kByCode[code]
    if (!rr || k === undefined) return '…'
    const [lo, hi] = countInterval(1000, k, rr.ciLevel)
    const pct = (x: number) => Math.round((x / 1000 - 1) * 100)
    return `${formatNumber(Math.round(lo))} to ${formatNumber(Math.round(hi))} (−${-pct(lo)}% to +${pct(hi)}%)`
  }
  const ruleTotals = iy
    ? Object.values(iy.rules).reduce((a, r) => ({ all: a.all + r.institutionYears, listed: a.listed + r.listed }), { all: 0, listed: 0 })
    : null
  const yearRows = rs ? Object.entries(rs.byYear).sort(([a], [b]) => a.localeCompare(b)) : []

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
                  <div className="flex-1 min-w-0 break-words">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      Campus Crime Data
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                      U.S. Department of Education Campus Safety and Security Data
                    </p>
                    <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-600 dark:text-gray-400 mb-3">
                      <span>Source: <strong className="text-gray-900 dark:text-gray-200">DOE OPE</strong></span>
                      <span>Legal Basis: <strong className="text-gray-900 dark:text-gray-200">Clery Act</strong></span>
                      <span>Coverage: <strong className="text-gray-900 dark:text-gray-200">{metadata ? coverageText || '—' : 'Loading...'}</strong></span>
                    </div>
                    <div className="space-y-3 text-sm mb-3">
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">One release per campus-year:</strong> Each yearly DOE release covers three calendar years, and a campus that reports in one release is sometimes missing from the next. For each campus and year we use the newest release that reports that campus for that year (any figure, including zero), and take all of that campus-year's figures from that one release. Releases are never mixed, and a blank figure is never filled in from another release.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Zero is not the same as not reported:</strong> A campus reported a year when its row in that release has at least one figure that is not blank. A reported year without incidents shows as 0 on the school page and in its charts, and in rankings by count the campus is ranked with 0, after the campuses with incidents, sharing one rank, by name. In rate rankings an institution with no incident at any of its campuses is listed with rate 0 and its interval, not ranked. A year a campus did not report has no figures at all: its page lists it as not reported and its charts leave a gap there, not a 0. Campuses that reported but never had an incident have school pages too.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Known errors in DOE files:</strong> In the 2021-2023 release (Crime2024SAS.zip), the residence-hall disciplinary file repeats the on-campus figures for 2022 and 2023, and the residence-hall arrest file has no 2022 liquor-law column. For campuses whose 2022 or 2023 figures come from that release, 2022 residence-hall disciplinary actions and liquor-law arrests come from the 2020-2022 release, and 2023 residence-hall disciplinary actions are left blank.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Figures reported by more than one campus:</strong> Some campuses report exactly the same 20 figures for a location (on-campus, non-campus or public property) as another campus in the same state and year, at least six of them nonzero, usually because a branch repeats its parent's statistics. When a campus's whole year (all three locations, at least six figures nonzero) matches another campus's, all of its locations count as copies. For a campus-year taken from an older release, a match with another campus in that same release counts too, even if that campus has since corrected its figures. School pages show the figures as DOE publishes them; state and national totals and rankings count them once, under one host campus, which the school page names. The host is the campus whose figures come from the newest release for that year, then the main campus, then the one with more students (FTE), then the larger total, then the lower IPEDS ID. One more case: when DOE reported a campus under a new ID (see below) and both IDs have the same whole year (every figure, at least one nonzero) from different releases, the older release's copy counts under the newer ID, whatever the number of nonzero figures.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Campus names and IDs:</strong> A campus that is not an institution's main campus is titled with its own DOE campus name (the BRANCH field), with its institution's name under it. Search matches campus names, institution names, cities and the names DOE and IPEDS have used for a campus before (IPEDS IALIAS and former DOE names). When a campus was renumbered or moved to another institution (a merger), DOE lists it under a new ID and its years are split across two pages. We link the two pages when the IDs never appear in the same DOE release, one follows the other, and they are in the same city with the same address or the same campus name; each pair was reviewed by hand and is listed with its evidence in etl/reference/campus_id_changes.csv in the open-source pipeline. The pages are linked, not merged: each keeps the years DOE reported under its own ID.
                        </span>
                      </div>
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
                  <div className="flex-1 min-w-0 break-words">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      Enrollment Data (FTE)
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                      IPEDS (Integrated Postsecondary Education Data System)
                    </p>
                    <div className="space-y-3 text-sm">
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">2021 onward:</strong> NCES's own FTE from its published DRVEF (Derived Fall Enrollment) files.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">2015-2020:</strong> NCES's own FTE as well, from the DRVEF tables of its final IPEDS databases for those years (NCES publishes them only inside those databases). We do not calculate FTE ourselves.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Status by year:</strong> {enrollmentStatusText.join(' ')}
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
          <section id="fte" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Calculator className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                FTE (Full-Time Equivalent) Enrollment
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              FTE is the basis of the per-student rates: full-time students count fully and part-time students count in part, so schools of different sizes and mixes can be compared. We use the FTE that NCES publishes for each institution and fall, for every year; we do not calculate it. Rates divide by an estimate of the part of it on campus, made from NCES's FTE, its fall headcounts and its share of students enrolled exclusively in distance education (see <a href="#rate-rules" className="underline">Rate Rules</a>).
            </p>

            <dl className="space-y-3 text-sm text-gray-600 dark:text-gray-400 mb-6">
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">FTE (DRVEF variable FTE, "Full-time equivalent fall enrollment")</dt>
                <dd>
                  NCES adds the institution's full-time fall enrollment to an estimate of the full-time equivalent of
                  its part-time enrollment: part-time students multiplied by factors that depend on the institution's
                  control and level and the student's level (for example 0.403543 for part-time undergraduates at
                  public 4-year institutions, 0.335737 at public 2-year institutions). It counts students enrolled
                  for credit in the fall, not over the whole year, and it is published for each institution, not
                  each campus.
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">PCTDEEXC ("Percent of students enrolled exclusively in distance education courses")</dt>
                <dd>
                  Students enrolled only in distance education courses, divided by all students enrolled, as of the
                  institution's official fall reporting date or October 15. Rates use it, with NCES's fall headcounts
                  of full-time and part-time students, to estimate on-campus FTE (see{' '}
                  <a href="#rate-rules" className="underline">Rate Rules</a>).
                </dd>
              </div>
              <div>
                Source: <SourceLink source={SOURCES.drvefDictionary}>NCES, DRVEF data dictionary for 2023</SourceLink>; see also the{' '}
                <SourceLink source={SOURCES.ipedsGlossary}>IPEDS Glossary</SourceLink>.
              </div>
            </dl>

            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden mb-6">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-gray-900 dark:text-gray-100">Years</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-900 dark:text-gray-100">Where NCES's FTE comes from</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  <tr>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">2021-2024</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">The DRVEF (Derived Fall Enrollment) data file of each year, the final revised version once NCES publishes it</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">2015-2020</td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">The DRVEF table inside NCES's final IPEDS database of each collection year (IPEDS_2015-16_Final.zip to IPEDS_2020-21_Final.zip). NCES publishes these years' FTE only there, so we copied it, with each database's checksum, into the open-source pipeline</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="text-sm text-gray-600 dark:text-gray-400">
              Earlier versions of this site estimated 2015-2020 FTE with one formula for every school (part-time undergraduates × 0.403543, part-time graduate students × 0.361702). That matched NCES's figure exactly for only about 58% of institutions, and was off by more than 5% for about 830 institutions a year, so it is no longer used.
            </p>
          </section>

          {/* Crime Rate Calculation */}
          <section id="rates" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Crime Rate Calculation
              </h2>
            </div>

            <div className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl p-6 border border-green-100 dark:border-green-900/50 mb-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">Per 10,000 Students on Campus</h4>
              <code className="block bg-white dark:bg-gray-900 rounded-lg p-4 text-sm text-gray-800 dark:text-gray-200 font-mono mb-3">
                Rate = (Incident Count / On-campus FTE) × 10,000
              </code>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                A size-adjusted figure: it removes the effect of enrollment size on counts, not the other
                differences between institutions listed under Limitations. On-campus FTE and every other rule rates
                follow are under <a href="#rate-rules" className="underline">Rate Rules</a> below.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 sm:col-span-2">
                <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Rates Are Per Institution</h5>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  NCES publishes enrollment (FTE) for each institution, not for each campus, and every campus of an
                  institution (all campuses whose UNITID starts with the same six digits) carries the same FTE. So a
                  rate divides the incidents of all the institution's campuses in the United States that year
                  (campuses abroad are left out: Rate Rules 12) by the institution's on-campus FTE. Rate rankings
                  list institutions, one row each, under the institution's name and linked to its main campus (or,
                  when the main campus did not report, its campus with the most incidents that year); school pages
                  and Compare label such a rate "all N campuses combined".
                  Rankings by count still list each campus. The incidents are counted as in rankings: residence
                  halls are not added (they are part of on-campus), and figures also reported by another campus
                  count once.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Total Counts</h5>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Sum of on-campus + non-campus + public property (excluding residence halls to avoid double-counting).
                  Figures reported identically by two campuses count once, under the host campus, in state and national totals and rankings.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h5 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Ties in Rankings</h5>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Schools with the same count (or the same rate) share a rank, and the next rank skips the places
                  the tie takes: 1, 2, 2, 4. Tied schools are listed by name. By count, campuses that reported the
                  year but had none of the selected category come last, with 0, sharing one rank. By rate, only
                  institutions with at least 20 incidents and no reason not to rank them are ranked (Rate Rules
                  below); those with 1 to 19 incidents follow, then those with none, and a separate list shows the
                  rates shown but not ranked and the institutions a rule leaves out. A reported zero can reflect how
                  an institution classifies or reports incidents, not only how safe it is.
                </p>
              </div>
            </div>

            <h3 id="rate-rules" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              Rate Rules
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Every rule that rates and rate rankings follow, with its threshold. None of them changes a count or the
              order of a ranking by count; rule 13 adds a flag to rankings by count. In a rate ranking an
              institution's rate is ranked; shown but not ranked, with the reason (rules 1, 9 and 11); listed as
              too few incidents to rank (rule 4); or, in a year rule 3 or 8 leaves the institution out, listed under
              "Not ranked by rate" with the rule and no rate. School pages and Compare say the same, and also show
              the rate of an institution under the floor of rule 2, with a note. The numbers cover 2015-2024; an
              institution-year is one institution in one year, and "the 2024 national rate rankings" are the
              national rankings file for 2024.
            </p>
            <ol className="list-decimal pl-5 space-y-4 text-sm text-gray-600 dark:text-gray-400">
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Denominator: on-campus FTE.</strong>{' '}
                Clery figures cover the campus, so rates divide by an estimate of the institution's FTE without its
                students enrolled exclusively in distance education. NCES gives their share of the fall headcount
                (PCTDEEXC), not of FTE, and the part of FTE they make up depends on how many of them study
                part-time, so there are two estimates: (a)
                proportional, FTE × (1 − PCTDEEXC / 100); (b) part-time first: the on-campus headcount, headcount ×
                (1 − PCTDEEXC / 100), holds all the full-time students it can, and the rest are part-time students,
                each counting the institution's FTE per part-time student, (FTE − full-time students) / part-time
                students. Estimate (b) is made for undergraduates and graduate students separately when NCES gives
                the year's own share for each level (2021 on), else from the totals. The on-campus FTE is the larger
                estimate, rounded half up to a whole number. A student who takes some courses online counts as on
                campus. When the larger estimate is more than {share(rr?.onlineUncertainRatio, true)} above the
                smaller, or (b) cannot be computed because NCES's headcounts do not add up, the on-campus FTE is
                uncertain: the rate is shown with the larger estimate and not ranked, for every offense that year
                (Grand Canyon University in 2024: 12,503 and 23,110). The same holds when rule 8 or 9 adds the
                on-campus FTE of another institution and that institution's estimates are uncertain. The 2024
                national rate rankings list {num(y24?.fteUncertain)} institutions with an uncertain on-campus FTE
                that rules 3 and 8 do not leave out. For 2020 and 2021, when many institutions taught remotely for the
                pandemic, the estimates use the institution's fall 2019 share, so those years divide by the same
                kind of enrollment as the others (the year's own share when NCES has no 2019 share:{' '}
                {num(iy?.onlineOwnYear['2020']?.all)} institutions in 2020, {num(iy?.onlineOwnYear['2021']?.all)} in
                2021). The number of uncertain institutions rises in 2022 (table below), the first year after 2020
                and 2021 that uses each fall's own share. Every institution with an NCES FTE in these years has a
                PCTDEEXC. Sources:{' '}
                <SourceLink source={SOURCES.drvefDictionary}>NCES, DRVEF data dictionary</SourceLink>.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">At least {num(rr?.minFte)} on-campus FTE.</strong>{' '}
                Rate rankings list an institution only in a year its denominator (its on-campus FTE, with any FTE
                added under rules 8 and 9) is at least {num(rr?.minFte)}, because with fewer students a few incidents
                move the rate far. The 2024 national rate rankings list {num(y24?.listed)} institutions. State and
                national rankings cover the 50 states, the District of Columbia, Puerto Rico and the U.S. Virgin
                Islands; school pages of institutions elsewhere, such as Guam, show their rate with a note that no
                rate ranking lists it.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Campuses whose population is not mostly students.</strong>{' '}
                A rate per student says little where many people on campus are not in FTE. Rate rankings leave out
                an institution in a year IPEDS reports that it has a hospital (HD variable HOSPITAL = 1: patients,
                visitors and hospital staff; {num(iy?.rules.hospital.institutionYears)} institution-years,{' '}
                {num(iy?.rules.hospital.listed)} of them with a denominator of at least {num(rr?.minFte)},{' '}
                {num(y24?.excludedBy.hospital)} in the 2024 national rate rankings); else one whose Carnegie basic
                classification in IPEDS is "Special Focus Four-Year: Medical Schools &amp; Centers" (code 25 of
                C15BASIC, C18BASIC and C21BASIC) or the 2021 category "Special Focus Research Institution" (C21BASIC
                27; 20 of its 22 institutions in 2024 were medical schools and centers in the 2018 classification):{' '}
                {num(iy?.rules.medical.institutionYears)} institution-years, {num(iy?.rules.medical.listed)} with a
                denominator of at least {num(rr?.minFte)}, {num(y24?.excludedBy.medical)} in 2024; and the
                institutions of a reviewed list with a sourced reason ({num(iy?.rules.listed.institutionYears)}{' '}
                institution-years): Gallaudet University for 2015-2024, whose campus also holds the Clerc Center's
                Kendall Demonstration Elementary School and Model Secondary School for the Deaf, whose pupils are not
                in its FTE (<SourceLink source={SOURCES.clercCenter}>Laurent Clerc National Deaf Education Center</SourceLink>),
                and The University of Tennessee Health Science Center for 2015-2017 and Albert Einstein College of
                Medicine for 2019-2020, the years IPEDS gives them no Carnegie basic classification. In the 2024
                national rate rankings the median rate of all criminal offenses per 10,000 of the denominator was
                79.1 at research universities with very high research activity (Carnegie R1, C21BASIC 15) with a
                hospital (37 institutions) and 33.3 at those without one (109). Limitation: IPEDS reports HOSPITAL =
                1 only when the institution itself runs the hospital. A university whose medical center is a
                separate legal entity is not left out by this rule; rule 11 covers the medical-center campuses DOE
                lists for such universities. Sources:{' '}
                <SourceLink source={SOURCES.ipedsHdDictionary}>IPEDS HD data dictionary</SourceLink>,{' '}
                <SourceLink source={SOURCES.carnegie2021}>Carnegie Classification, 2021 Basic Classification</SourceLink>.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">At least {num(rr?.minCount)} incidents for a rank.</strong>{' '}
                A rate gets a rank only when it is built on at least {num(rr?.minCount)} incidents. Taking a year's
                count as a Poisson count, its relative standard error is 1/√count: 22.4% at 20, 31.6% at 10, 50% at
                4 (more with the year-to-year variation of rule 6). CDC WONDER flags rates based on fewer than 20
                deaths as unreliable for the same reason (a relative standard error of 23% or more;{' '}
                <SourceLink source={SOURCES.cdcWonderUnreliable}>CDC WONDER</SourceLink>). Institutions with 1 to{' '}
                {rr ? rr.minCount - 1 : '…'} incidents and no other reason not to rank them follow the ranked ones as
                "too few incidents to rank by rate", in order of rate, with the rate and its interval shown. In the
                2024 national rate rankings ({num(y24?.listed)} institutions), {num(y24?.criminal?.ranked)} are ranked
                for all criminal offenses, {num(y24?.violent?.ranked)} for violent crimes and{' '}
                {num(y24?.property?.ranked)} for property crimes; {num(y24?.criminal?.few)},{' '}
                {num(y24?.violent?.few)} and {num(y24?.property?.few)} have too few incidents.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Counts only for rare offenses.</strong>{' '}
                An offense with fewer than 1,000 incidents a year on average in national totals (the 50 states, DC,
                Puerto Rico and the U.S. Virgin Islands) has rankings by count only: incest (
                {num(rs?.countsOnly.averagePerYear.incest)} a year), negligent manslaughter (
                {num(rs?.countsOnly.averagePerYear.negligent_manslaughter)}), murder (
                {num(rs?.countsOnly.averagePerYear.murder)}), statutory rape (
                {num(rs?.countsOnly.averagePerYear.statutory_rape)}) and arson (
                {num(rs?.countsOnly.averagePerYear.arson)}). Across 2015-2024 only{' '}
                {rs ? num(Object.values(rs.countsOnly.reachingMinCount).reduce((a, b) => a + b, 0)) : '…'}{' '}
                institution-years in rate rankings reached {num(rr?.minCount)} incidents of any of them (statutory
                rape {num(rs?.countsOnly.reachingMinCount.statutory_rape)}, arson{' '}
                {num(rs?.countsOnly.reachingMinCount.arson)}), so a rate ranking would rank almost no one. The next
                rarest offense, robbery, averages{' '}
                {rs ? num(Math.round(rs.countsOnly.averagePerYear.robbery)) : '…'} a year.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">{ci}% intervals and rank ranges.</strong>{' '}
                Each rate is shown with a {ci}% interval for the institution's underlying yearly rate. Institutions'
                yearly counts vary more than chance alone (a Poisson count) would make them vary: in{' '}
                {rr ? `${rr.dispersion.years[0]}-${rr.dispersion.years[1]}` : '…'}, among institutions in rate
                rankings without a rule in every year and with at least {num(rr?.dispersion.minMean)} incidents a
                year on average, the variance of an institution's yearly counts around a model with an institution
                and a year effect was, at the median, {num(group('violent')?.phi)} times that of a Poisson count for
                violent crimes ({num(group('violent')?.units)} institutions), {num(group('criminal')?.phi)} times for
                all criminal offenses ({num(group('criminal')?.units)}) and {num(group('property')?.phi)} times for
                property crimes ({num(group('property')?.units)}). So the interval is that of a negative binomial
                (gamma-Poisson) count whose variance is n(1 + n/k), with k fitted on those years: {num(group('violent')?.k)}{' '}
                for violent crimes, {num(group('criminal')?.k)} for all criminal offenses, {num(group('property')?.k)}{' '}
                for property crimes, {num(group('all')?.k)} for all categories, {num(group('crime_offense')?.k)} for
                each single criminal or VAWA offense and {num(group('enforcement_offense')?.k)} for each arrest or
                disciplinary referral category. For a count n, φ = 1 + n/k, and the interval is φ times the gamma
                interval of the effective count n/φ (
                <SourceLink source={SOURCES.fayFeuer1997}>Fay and Feuer, 1997</SourceLink>; with φ = 1 it is the exact
                Poisson interval, <SourceLink source={SOURCES.garwood1936}>Garwood, 1936</SourceLink>), divided by the
                denominator and multiplied by 10,000. For a count of 20 the interval of the count is{' '}
                {intervalPair(example('violent', 20))} for violent crimes and {intervalPair(example('criminal', 20))}{' '}
                for all criminal offenses; for a count of 0 it is {intervalPair(example('violent', 0))}. Because k is
                fixed, the interval stays wide for large counts: for 1,000 violent crimes it runs from{' '}
                {wide('violent')}, for 1,000 criminal offenses from {wide('criminal')}. It does not cover differences
                in reporting or classification between institutions. A ranked institution's rank range comes from{' '}
                {num(rr?.rankRanges.draws)} simulated rankings: each draws every ranked institution's rate from a gamma
                distribution around its count, with the same k, and ranks them. The range is the middle {ci}% of the
                institution's simulated ranks, widened to hold its rank; the draws use a fixed seed, so every build
                gives the same ranges. Ranks inside one range are not clearly different. In the 2024 national rate
                rankings the median ranked institution's range spans {num(y24?.violent?.medianRange)} ranks (of{' '}
                {num(y24?.violent?.ranked)}) for violent crimes, {num(y24?.criminal?.medianRange)} (of{' '}
                {num(y24?.criminal?.ranked)}) for all criminal offenses and {num(y24?.property?.medianRange)} (of{' '}
                {num(y24?.property?.ranked)}) for property crimes.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Violent and property crimes.</strong>{' '}
                "Violent crimes" adds murder (non-negligent manslaughter included), rape, robbery and aggravated
                assault, the four offenses of the FBI's violent crime (
                <SourceLink source={SOURCES.fbiViolent2019}>FBI, Crime in the United States 2019: Violent Crime</SourceLink>).
                "Property crimes" adds burglary, motor vehicle theft and arson, the FBI's property crime offenses
                without larceny-theft, which Clery does not collect (
                <SourceLink source={SOURCES.fbiProperty2019}>FBI, Property Crime</SourceLink>). Fondling, incest,
                statutory rape and negligent manslaughter are in neither; all 11 offenses are in "All criminal
                offenses", which is still offered. Rankings open on violent crimes because motor vehicle theft was
                37% of all criminal offenses in 2024 (15% in 2015) and so decides much of that total's order.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Mergers and renumbered campuses.</strong>{' '}
                In a year DOE reported a campus under two institutions (its old and its new ID, from different
                releases), the institution whose NCES FTE holds the campus's students is the only one of the two
                with an FTE or, when both have one, the one whose every campus that year is such a linked campus.
                When the other institution counts the campus and the students' institution counts no campus of its
                own that year, the other's rate adds the students' institution's on-campus FTE (both institutions'
                students over both institutions' incidents). An institution gets no rate that year, and is left out
                of rate rankings with a note on its school page, only when a campus with at least one incident that
                year has its incidents counted under one institution and its students under another, when it cannot
                be told which FTE holds the students, or when those students' FTE would be split among several
                institutions. In a year a merged institution's campuses count under several institutions and one of
                them has no NCES FTE while counting a campus with incidents that no institution with an FTE also
                counts, every institution of the group is left out. A campus with no incident that year needs none
                of this: whichever FTE holds its students, every rate is the same. In all, these rules leave out{' '}
                {iy ? num(iy.rules.merger.institutionYears + iy.rules.family.institutionYears) : '…'} institution-years
                that rule 3 does not already leave out ({iy ? num(iy.rules.merger.listed + iy.rules.family.listed) : '…'}{' '}
                with a denominator of at least {num(rr?.minFte)}; before this rule was narrowed, 295, 97 of them with
                at least 1,000 FTE), and {num(iy?.pooled.merger)} are rated with another institution's FTE added.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Shared campuses.</strong>{' '}
                When DOE publishes the same figures for campuses of two institutions in a year, they count once,
                under the host campus, while each institution's students are in its own FTE. When the other
                institution counts no campus of its own that year and its figures count under one host institution,
                the host's rate adds the other's on-campus FTE ({num(iy?.pooled.shared)} institution-years).
                Otherwise neither rate can be made exact: adding the other institution's FTE would add its students
                at its other campuses, and not adding it would leave its students on the shared campus out. So, for
                each offense, the shared figures are measured against the institution's count: the host's figures
                that another institution also reports, and the figures an institution reports for its own campus
                that count under another institution's campus (and so are not in its count). When they are more than{' '}
                {share(rr?.sharedShare)} of its count (with the figures counted elsewhere added to it), the rate is
                shown, not ranked; at {share(rr?.sharedShare)} or less it is ranked with a note. In the 2024 national
                rate rankings this leaves {num(y24?.violent?.notRanked.shared)} institutions' violent-crime rates,{' '}
                {num(y24?.criminal?.notRanked.shared)} for all criminal offenses and{' '}
                {num(y24?.property?.notRanked.shared)} for property crimes not ranked (some also for another
                reason), among them, for all criminal
                offenses, Texas A&amp;M University-College Station, Indiana University-Bloomington and Purdue
                University-Main Campus; ranked with a note are {num(y24?.violent?.sharedNote)},{' '}
                {num(y24?.criminal?.sharedNote)} and {num(y24?.property?.sharedNote)}. Most shared campuses are a
                program of one institution on another's campus, such as the Indiana University School of Medicine at
                Bloomington or the University of Maryland Global Campus at College Park.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Unusually high years.</strong>{' '}
                A rate is marked "Unusually high for this institution; DOE counts crimes in the year reported" when
                its count is at least {num(rr?.spike.minCount)}, the institution has figures for at least{' '}
                {num(rr?.spike.minOtherYears)} other years (a year without an incident counts as 0), the count is
                more than {num(rr?.spike.factor)} times the median of its counts of that category in those years and
                more than{' '}
                {num(rr?.spike.maxFactor)} times the largest of them, and a negative binomial count with that median
                as its mean and the k of rule 6 reaches it with a probability below {rr ? rr.spike.p : '…'}. It
                stays ranked: a year's figure is the crimes reported that year, and one report of many past incidents
                can raise one year (see <a href="#year-reported" className="underline">How Institutions Count</a>).
                In the 2024 national rate rankings {num(y24?.violent?.spikes)} rate is marked for violent crimes,{' '}
                {num(y24?.criminal?.spikes)} for all criminal offenses and {num(y24?.property?.spikes)} for property
                crimes; over every offense and total, {num(y24?.spikes)} of {num(y24?.rankedEntries)} ranked rates.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Medical-center campuses.</strong>{' '}
                The hospital test of rule 3 catches only institutions that run a hospital themselves. Some
                universities' Clery geography
                includes a medical-center campus whose hospital another entity runs, where many people are patients,
                visitors and hospital staff, not students. The incidents at 13 medical-center campuses that DOE lists
                are counted apart; each was
                reviewed from DOE's campus name and address (etl/reference/medical_campuses.csv in the open-source
                pipeline): Johns Hopkins University's East Baltimore medical campus and Bayview Medical Center; the
                Boston University Medical Campus; the University of Kansas Medical Center; Washington University in
                St. Louis's Medical School campus; Columbia University Medical Center; New York University's NYU
                Langone medical center campus and NYU Langone Hospital - Brooklyn; Wake Forest University's Medical
                Center campus (2015-2018); the University of Florida's UF Health Jacksonville campus; Loyola
                University Chicago's Medical Center campus; the University of the District of Columbia's United
                Medical Center site; and the College of Our Lady of the Elms's site at Berkshire Medical Center. Each
                is still part of its institution's count. When incidents at these campuses
                are {share(rr?.medicalShare)} or more of an institution's count of an offense, its rate is shown, not
                ranked; below that it is ranked with a note giving the number. In 2024, 97 of Johns Hopkins
                University's 144 violent crimes were at its medical campuses. In the 2024 national rate rankings this
                leaves {num(y24?.violent?.notRanked.medical_campus)} violent-crime rates,{' '}
                {num(y24?.criminal?.notRanked.medical_campus)} for all criminal offenses and{' '}
                {num(y24?.property?.notRanked.medical_campus)} for property crimes not ranked (some also for another
                reason), and {num(y24?.violent?.medicalNote)}, {num(y24?.criminal?.medicalNote)} and{' '}
                {num(y24?.property?.medicalNote)} ranked with a note. Incidents at a medical center that is not on
                this list, or that DOE does not list as a campus of its own, are not counted apart.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Campuses abroad.</strong>{' '}
                A campus DOE lists without a state is abroad. NCES's fall enrollment excludes "students enrolled in
                any branch campus located in a foreign country" (
                <SourceLink source={SOURCES.ncesFallEnrollment2024}>NCES, Fall Enrollment instructions, Who to Exclude</SourceLink>),
                so an institution's count and rate leave out the incidents at its campuses abroad; they stay on each
                such campus's own school page. Campuses in Puerto Rico, Guam and other U.S. territories are not
                abroad, and state and national rankings by count never included campuses abroad. In the 2024
                national rate rankings {num(y24?.abroad)} institutions have a campus abroad; the 32 criminal
                offenses at those campuses that year are not in their rates (audit.json, check Institution Rates).
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-100">Counts very high for an institution's size.</strong>{' '}
                Rankings by count rank campuses whatever their size. A count is flagged "very high for an institution
                of this size" when it is at least {num(rr?.countFlag.minCount)} and its number per 10,000 of the
                institution's FTE (NCES's FTE of the whole institution) is more than {num(rr?.countFlag.factor)} times
                the highest rate in that year's national rate ranking of the offense. The count is shown as reported;
                the flag says to check the institution's Annual Security Report. In the 2024 national rankings by
                count {num(y24?.countFlags.violent)} counts of violent crimes, {num(y24?.countFlags.criminal)} of all
                criminal offenses, {num(y24?.countFlags.property)} of property crimes and {num(y24?.countFlags.all)}{' '}
                of all categories are flagged.
              </li>
            </ol>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-4">
              Rules 3 and 8 leave out {num(ruleTotals?.all)} institution-years ({num(ruleTotals?.listed)} with a
              denominator of at least {num(rr?.minFte)}). By year, in the national rate rankings:
            </p>
            <div className="mt-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Institutions in the national rate rankings by year</caption>
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Year</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Listed</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Left out by a rule</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Uncertain on-campus FTE</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">With a campus abroad</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {yearRows.map(([y, s]) => {
                    return (
                      <tr key={y}>
                        <th scope="row" className="px-3 py-2 text-left font-normal text-gray-700 dark:text-gray-300">{y}</th>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.listed)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.excluded)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.fteUncertain)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.abroad)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              Listed: institutions with a denominator of at least {num(rr?.minFte)}. Left out by a rule: rule 3 or 8,
              no rate. Uncertain on-campus FTE: rule 1, shown but not ranked (institutions not left out by a rule).
              With a campus abroad: rule 12.
            </p>
          </section>

          {/* Definitions */}
          <section id="definitions" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Definitions
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-4">
              Every category on this site is a Clery Act category, counted by each institution and reported to the
              U.S. Department of Education (ED) in its yearly Campus Safety and Security survey. The definitions below
              are the regulation's, shortened: the crimes in{' '}
              <SourceLink source={SOURCES.regAppendixA}>Appendix A to Subpart D of Part 668</SourceLink>{' '}
              (taken from the FBI's Uniform Crime Reporting manuals), and the VAWA offenses and locations in{' '}
              <SourceLink source={SOURCES.reg66846}>34 CFR 668.46</SourceLink>. Where the DOE data uses another
              name, it is given in brackets.
            </p>

            <div className="space-y-4">
              {[
                { title: 'Criminal offenses (11)', note: 'Crimes reported to campus security authorities or local police that occurred on the institution\'s Clery geography.', items: CRIMINAL_DEFINITIONS },
                { title: 'VAWA offenses (3)', note: 'Added to the Clery Act by the Violence Against Women Reauthorization Act of 2013.', items: VAWA_DEFINITIONS },
                { title: 'Arrests and disciplinary referrals (3 violations each)', note: 'Counts of people arrested, and of people referred for campus disciplinary action, for violating these laws.', items: LAW_VIOLATION_DEFINITIONS },
              ].map((group) => (
                <div key={group.title} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">{group.title}</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">{group.note}</p>
                  <dl className="space-y-2 text-sm">
                    {group.items.map((d) => (
                      <div key={d.name}>
                        <dt className="inline font-medium text-gray-900 dark:text-gray-100">
                          {d.name}
                          {d.doeName && <span className="font-normal text-gray-500 dark:text-gray-400"> [{d.doeName}]</span>}:
                        </dt>{' '}
                        <dd className="inline text-gray-600 dark:text-gray-400">{d.text}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>

            <h3 id="geography" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              <MapPin className="w-4 h-4 inline mr-2 text-primary-600 dark:text-primary-400" aria-hidden="true" />
              Locations (Clery geography)
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              {GEOGRAPHY_DEFINITIONS.map((d) => (
                <div key={d.name} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-1">
                    {d.name}
                    {d.doeName && <span className="font-normal text-gray-500 dark:text-gray-400"> [{d.doeName}]</span>}
                  </h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{d.text}</p>
                </div>
              ))}
            </div>
            <div className="flex items-start gap-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-800 dark:text-amber-300">
                <strong>Residence halls are not added to totals.</strong> The regulation asks for the number of
                on-campus crimes that took place in student housing, so every residence-hall incident is already
                in the on-campus count. Totals on this site are on-campus + non-campus + public property; adding
                residence halls would count those incidents twice.
              </p>
            </div>

            <h3 id="counting" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              How institutions count
            </h3>
            <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 list-disc ml-5">
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Reports, not convictions.</strong> A crime is
                counted when it is reported to a campus security authority or to local police and occurred on the
                institution's Clery geography (34 CFR 668.46(c)(1)). Only sworn or commissioned law enforcement
                personnel may determine a report false or baseless ("unfounded"); unfounded reports are left out of
                the counts and reported separately (668.46(c)(2)(iii)). This site does not show unfounded reports.
              </li>
              <li id="year-reported" className="scroll-mt-20">
                <strong className="text-gray-900 dark:text-gray-200">By the year reported, not the year it happened.</strong>{' '}
                Statistics are disclosed by "the year in which the crimes were reported" (2016 Handbook, chapter
                2). A crime reported in 2019 counts in 2019 even if it happened years earlier, so a year's figure
                can jump when many people report past abuse at one institution. For example, the national number
                one campus by count of criminal offenses was Ohio State University in 2018, 2019 and 2021 (mostly
                fondling) and the University of Michigan in 2020 (fondling and rape), and Michigan State
                University's 1,012 rapes in 2018 are about 12% of that year's national total. These are the
                figures the institutions reported; this site does not mark or remove them.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">One offense per incident, with exceptions.</strong>{' '}
                When several criminal offenses happen in one incident, only the most serious is counted (the FBI's
                Hierarchy Rule, 668.46(c)(9)(v)). Arson is always counted, and a rape, fondling, incest or statutory
                rape in the same incident as a murder is counted along with the murder (668.46(c)(9)(vi)-(vii)). The
                Hierarchy Rule does not apply to VAWA offenses, so an incident can be counted both as, say, an
                aggravated assault and as dating violence (2016 Handbook, chapter 3).
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Arrests and referrals count people.</strong> The
                arrest figures count people arrested (the 2016 Handbook defines an arrest as a person processed by
                arrest, citation or summons). The disciplinary figures count people "not included" in the arrest
                count who were referred for campus disciplinary action (668.46(c)(1)(ii)), so a person both arrested
                and referred for the same violation is counted once, as an arrest. A referral counts only for a
                violation of the law: breaking a campus rule alone (for example, a student of legal drinking age on
                a dry campus) is not counted (2016 Handbook, chapter 3). These counts are not subject to the
                Hierarchy Rule and are counted in addition to any criminal offense in the same incident.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Stalking is counted per year.</strong> Stalking
                that continues into another calendar year is counted in each year in which the course of conduct
                was reported (668.46(c)(6)).
              </li>
            </ul>

            <h3 id="not-shown" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              What this site does not show
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              DOE also publishes hate crimes, unfounded crime reports and fire statistics; this site does not read
              or show them. Hate crimes are a breakdown rather than a separate total: the criminal offenses above
              that were hate crimes (already in those counts, so adding them would count them twice), plus four
              crimes counted only when they are hate crimes: larceny-theft, simple assault, intimidation and
              destruction/damage/vandalism of property (668.46(c)(1)(iii)). The site has not added that breakdown;
              use{' '}
              <SourceLink source={SOURCES.cssData}>DOE's data tool</SourceLink> for it. Unfounded reports are
              the reports withheld from the counts.
            </p>

            <h3 id="totals" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              Totals on this site
            </h3>
            <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
              <p>
                <strong className="text-gray-900 dark:text-gray-100">All criminal offenses</strong> (what school
                pages and Compare open on; rankings open on violent crimes, Rate Rules 7): the 11 criminal offenses
                above, added up.
              </p>
              <p>
                <strong className="text-gray-900 dark:text-gray-100">All categories (crimes, arrests,
                referrals)</strong>: every category added up. These are different kinds of counts: arrests
                and disciplinary referrals count people (each person arrested or referred), not incidents,
                and an incident of dating violence, domestic violence or stalking can also be counted as a
                criminal offense such as aggravated assault. So this total is not a number of incidents,
                and high totals often reflect drug and alcohol enforcement rather than violent crime.
              </p>
            </div>
          </section>

          {/* Series breaks and context */}
          <section id="series-breaks" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Calendar className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Comparing Years
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Changes in definitions, reporting or circumstances between 2015 and 2024 that affect comparisons
              over time. Notes marked with years also appear next to charts and rankings that show those years.
            </p>
            <div className="space-y-4">
              {SERIES_NOTES.map((n) => (
                <div key={n.id} id={n.id} className="scroll-mt-20 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                  <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    <span className="inline-block mr-2 px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 text-xs font-semibold align-middle">
                      {n.label}
                    </span>
                    {n.title}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{n.detail}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Sources:{' '}
                    {n.sources.map((s, i) => (
                      <span key={s.url}>
                        {i > 0 && '; '}
                        <SourceLink source={s} />
                      </span>
                    ))}
                  </p>
                </div>
              ))}

              <div id="known-defects" className="scroll-mt-20 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5">
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                  <span className="inline-block mr-2 px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 text-xs font-semibold align-middle">
                    2022-2023
                  </span>
                  Residence-hall figures from DOE's 2021-2023 release
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  For campuses whose 2022 or 2023 figures come from DOE's 2021-2023 release (Crime2024SAS.zip;
                  campuses missing from the 2022-2024 release), two of that release's residence-hall files are
                  wrong (see Known Errors in DOE Files above). Their 2022 residence-hall disciplinary referrals and
                  liquor-law arrests come from the 2020-2022 release instead, and their 2023 residence-hall
                  disciplinary referrals are left out
                  {defectCampuses(metadata, 2023) !== null && (
                    <> ({formatNumber(defectCampuses(metadata, 2023)!)} campuses in 2023)</>
                  )}
                  . Residence halls are not part of totals, so only residence-hall figures are affected; the school
                  page of each such campus says so.
                </p>
              </div>
            </div>

            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              Context for every year
            </h3>
            <div className="space-y-4">
              {SERIES_CONTEXT.map((n) => (
                <div key={n.id} id={n.id === 'year-reported' ? undefined : n.id} className="scroll-mt-20">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-1">{n.title}</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{n.detail}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Sources:{' '}
                    {n.sources.map((s, i) => (
                      <span key={s.url}>
                        {i > 0 && '; '}
                        <SourceLink source={s} />
                      </span>
                    ))}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* Data Limitations */}
          <section id="limitations" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/50 rounded-xl flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Limitations
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              What these figures can and cannot support. Read these before comparing schools or years.
            </p>

            <div className="space-y-4">
              {LIMITATIONS.map((item) => (
                <div key={item.title} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                  <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-1">{item.title}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{item.body}</p>
                </div>
              ))}
            </div>

            <h3 id="corrections" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              What this site corrects, and what it does not
            </h3>
            <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 list-disc ml-5">
              <li>
                <strong className="text-gray-900 dark:text-gray-200">One DOE release per campus-year.</strong> Each
                campus-year comes from the newest DOE release that reports it, with all of its figures from that
                release, so a campus missing from the latest release keeps the years an earlier release published.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Figures reported by two campuses count once.</strong>{' '}
                When campuses in the same state report exactly the same figures for a location (or a whole year),
                totals and rankings count them once, under one host campus. School pages still show each campus's
                figures as DOE publishes them.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Known errors in DOE's 2021-2023 release.</strong>{' '}
                Its residence-hall disciplinary file repeats the on-campus figures for 2022 and 2023, and its
                residence-hall arrest file has no 2022 liquor-law column. For campuses whose figures come from that
                release, 2022 values are taken from the 2020-2022 release and 2023 residence-hall disciplinary
                referrals are left out (see <a href="#known-defects" className="underline">Comparing Years</a>).
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">DOE's 2015 and 2016 files are read correctly.</strong>{' '}
                Those SAS files are read with a reader that returns every row; an earlier reader lost 13 Alabama
                campuses' 2015 and 2016 figures.
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Enrollment is NCES's own FTE</strong> for every
                year. The on-campus part of it that rates divide by is an estimate made from NCES's figures (Rate
                Rules 1).
              </li>
              <li>
                <strong className="text-gray-900 dark:text-gray-200">Not corrected:</strong> the figures themselves.
                This site does not audit institutions or change what they reported; it publishes DOE's figures with
                the rules above. An implausible figure here is an institution's report as DOE publishes it: ask the
                institution, or check its Annual Security Report. See also the{' '}
                <Link to="/changes" className="underline">list of corrections to this site's data</Link>.
              </li>
            </ul>
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
              Each build runs an audit of internal consistency over {schoolCount !== undefined ? `all ${formatNumber(schoolCount)} campus pages` : 'every campus page'}:
              the published files must agree with each other and with the pipeline's tables. It does not show
              that institutions' figures are accurate; they are published as reported to the Department of Education.
            </p>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              The audit compares the published files with the pipeline's own tables; it does not re-read the
              Department of Education's source files. The{' '}
              <a href="/data/build_inputs.json" className="underline hover:text-gray-700 dark:hover:text-gray-300">build record</a>{' '}
              lists every source file the build read, with a checksum (and its size, for the Department of Education
              files), and a SHA-256 checksum of every other published data file (everything under /data/).
            </p>

            <div className="bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-950/50 dark:to-primary-900/30 rounded-xl p-6 border border-primary-200 dark:border-primary-800">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0 break-words">
                  <h4 className="font-semibold text-primary-900 dark:text-primary-100 mb-2">
                    Download Full Audit Report
                  </h4>
                  <p className="text-sm text-primary-700 dark:text-primary-300 mb-4">
                    JSON file with the result of each check below, coverage counts by year, and the checksum
                    of the build it audited.
                  </p>
                  <div className="flex flex-wrap gap-4 text-sm text-primary-700 dark:text-primary-300">
                    <span>Format: <strong>JSON</strong></span>
                    <span>Schools: <strong>{schoolCount !== undefined ? formatNumber(schoolCount) : metadata ? '—' : 'Loading...'}</strong></span>
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
                  "School completeness (every campus that reported a year, zeros included, has a published file and is in the search)",
                  "Incident total accuracy (each school file has exactly the years the campus reported, and its yearly totals match the aggregate table)",
                  "FTE coverage by year",
                  "Rate calculation verification",
                  "Ranking order validation (ties share a rank: 1, 2, 2, 4)",
                  "Ranking totals (each ranking's total and tables agree with its entries)",
                  "Aggregate consistency (the school-year aggregate table matches the fact table it is built from)",
                  "Shared figures (figures two campuses, or one campus under its old and new DOE ID, report identically are counted once in totals and rankings)",
                  "Enrollment matches NCES (every FTE is NCES's own published figure)",
                  "Institution rates (recomputed from the facts: the incidents of all campuses in the United States per on-campus FTE, both on-campus FTE estimates, the institutions each rule leaves out, and the reasons each rate is shown but not ranked)",
                  "Campus identity (the reviewed list of renumbered campuses matches the DOE files, linked pages name each other, every school is in the search with its campus name, and merger years follow the merger rate rule)",
                  "Rate rules (the overdispersion k fitted again, each 95% interval recomputed another way, the simulated rank ranges, unusually high years, counts flagged as very high for an institution's size, and the counts-only offenses)",
                ].map((check, i) => (
                  <div key={i} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                    <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                    <span>{check}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Data and downloads */}
          <section id="data" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <Download className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data and Downloads
              </h2>
            </div>

            <dl className="space-y-4 text-sm text-gray-600 dark:text-gray-400 mb-6">
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">Build identifier</dt>
                <dd>
                  {build ? (
                    <>This build is <code className="font-mono text-gray-800 dark:text-gray-200 break-all">{build.sha256}</code>{metadata ? `, built ${formatDate(metadata.lastUpdated)}` : ''}. </>
                  ) : null}
                  The identifier is the SHA-256 of the{' '}
                  <a href="/data/build_inputs.json" className="underline">build record</a>, which lists a checksum of
                  every source file the build read and every data file it published; the footer shows its first 12
                  characters. Rebuilding from the same source files gives the same figures, but the build date is
                  part of the record, so every run has a new identifier. Cite it with the date you accessed the data.
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100"><a href="/audit.json" className="underline">audit.json</a></dt>
                <dd>
                  The result of the build's audit (below): <code>overall_status</code>, each check with its details,
                  coverage counts by year, and <code>audited_build.site_record_sha256</code>, the identifier of the
                  build it checked.
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">
                  <a href="/data/downloads/campus-years.csv" className="underline">campus-years.csv</a>
                </dt>
                <dd>
                  One row per campus and year the site shows (each year a campus reported to DOE, zeros included):{' '}
                  <code>year</code>, <code>unitid</code> (DOE campus ID), <code>base_unitid</code> (the IPEDS
                  institution: the first six digits), <code>campus_name</code> (the campus's own DOE name, or the
                  institution's when DOE gives none), <code>institution_name</code>, <code>city</code>, <code>state</code>,{' '}
                  <code>main_campus</code>, <code>doe_release</code> (the DOE file suffix the figures come from, e.g.
                  222324 for the 2022-2024 release), <code>counts_in_rankings</code> (false when every figure the
                  campus reported that year is counted under another campus), <code>institution_fte</code> (NCES FTE
                  of the whole institution), <code>institution_online_pct</code> (percent of students enrolled
                  exclusively in distance education), <code>online_pct_fall</code> (the fall that share is from),{' '}
                  <code>institution_rate_fte</code> (the denominator of the institution's rates: its on-campus FTE,
                  the larger of the two estimates of Rate Rules 1, with any FTE added under Rate Rules 8 and 9),{' '}
                  <code>institution_rate_rule</code> (the rule that leaves the institution out of rate rankings that
                  year: <code>hospital</code>, <code>medical</code> or <code>listed</code> for rule 3,{' '}
                  <code>merger</code> or <code>family</code> for rule 8; empty when none),{' '}
                  <code>institution_oncampus_fte_proportional</code> and{' '}
                  <code>institution_oncampus_fte_part_time_first</code> (the two estimates of rule 1; the second is
                  empty when it cannot be computed), <code>institution_oncampus_fte_uncertain</code> (True when the
                  on-campus FTE is uncertain under rule 1: its own estimates, or those of an institution whose FTE
                  its rate adds) and{' '}
                  <code>medical_center_campus</code> (True when the campus is one of the medical-center campuses of
                  rule 11 that year).
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">counts-YYYY.csv, one per year</dt>
                <dd>
                  Every nonzero count, by campus, location and offense, as the campus reported it: <code>year</code>,{' '}
                  <code>unitid</code>, <code>geo</code> (On-campus, Residence halls, Non-campus, Public property),{' '}
                  <code>offense</code>, <code>count</code>, <code>counted_under_unitid</code> (set when another campus,
                  or the same campus under its new DOE ID, reported the same figures for that location; totals and rankings count them under that campus).
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                    {(metadata?.years ?? []).map((y) => (
                      <a key={y} href={`/data/downloads/counts-${y}.csv`} className="underline font-mono">{y}</a>
                    ))}
                  </div>
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">Reproducing the site's totals</dt>
                <dd>
                  From <code>counts-YYYY.csv</code>: leave out Residence halls (part of on-campus), keep rows with an
                  empty <code>counted_under_unitid</code>, and, for national totals, keep campuses whose state in{' '}
                  <code>campus-years.csv</code> is one of the 50 states, DC, PR or VI. The site's JSON files (school
                  pages, rankings) are under <code>/data/</code> and listed in the build record.
                </dd>
              </div>
              <div>
                <dt className="font-medium text-gray-900 dark:text-gray-100">Rebuilding from DOE's and NCES's files</dt>
                <dd>
                  The pipeline downloads the source files and builds every file above. With Python 3.11 or later, in{' '}
                  <code>etl/</code> of the{' '}
                  <a href="https://github.com/kbdevopz/collegesafetydata-public" target="_blank" rel="noopener noreferrer" className="underline">repository</a>:
                  <pre className="mt-2 bg-gray-50 dark:bg-gray-800/60 rounded-lg p-3 text-xs text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre">{`python -m venv venv
venv\\Scripts\\activate        # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python 01_download_raw_data.py
python 01b_download_ipeds.py
python 02_transform_to_parquet.py
python 02b_transform_ef_enrollment.py
python 02a_transform_enrollment.py
python 03_build_dimensions.py
python 04_create_aggregates.py
python 05_generate_json.py
python 06_validate.py
python 07_comprehensive_audit.py`}</pre>
                  The README has the details, including the optional step that re-extracts NCES's 2015-2020 FTE.
                </dd>
              </div>
            </dl>
          </section>

          <CiteThisData />

          {/* Official sources */}
          <section id="sources" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Official Sources
              </h2>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              The 2016 Handbook was rescinded in October 2020 and replaced by the Clery Act Appendix for the FSA
              Handbook; ED keeps the Handbook online for historical purposes. ED said at the time that no statutory
              or regulatory requirement for Clery Act reporting had changed. The definitions above are the
              regulation's, set by the VAWA final rule that took effect on July 1, 2015; eCFR's version history of
              34 CFR 668.46 and its Appendix A, which begins in December 2016, shows no substantive amendment
              since. The Handbook is cited only where it explains how to count.
            </p>
            <ul className="space-y-2 text-sm">
              {Object.values(SOURCES).map((s) => (
                <li key={s.url} className="text-gray-600 dark:text-gray-400">
                  {s.publisher}.{' '}
                  <SourceLink source={s} />
                </li>
              ))}
            </ul>
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
                <div>etl/00_check_for_updates.py — Check DOE and NCES for newer data</div>
                <div>etl/01_download_raw_data.py — Download DOE crime data</div>
                <div>etl/01b_download_ipeds.py — Download IPEDS enrollment</div>
                <div>etl/02_transform_to_parquet.py — Transform crime data</div>
                <div>etl/01c_extract_ipeds_official.ps1 — Copy NCES's 2015-2020 FTE from its IPEDS databases (Windows)</div>
                <div>etl/02b_transform_ef_enrollment.py — NCES's FTE for 2015-2020</div>
                <div>etl/02a_transform_enrollment.py — Process DRVEF FTE (2021 onward)</div>
                <div>etl/03_build_dimensions.py — Build school and offense tables</div>
                <div>etl/04_create_aggregates.py — Create aggregated tables</div>
                <div>etl/05_generate_json.py — Generate JSON outputs</div>
                <div>etl/06_validate.py — Validate the generated data</div>
                <div>etl/07_comprehensive_audit.py — Run data quality audit</div>
              </div>
            </div>
          </section>

        </div>
      </div>
    </div>
  )
}
