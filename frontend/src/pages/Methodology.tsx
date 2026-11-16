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
import { cachedMetadata, fetchRateWindow, getMetadata } from '../lib/api'
import type { Metadata, RateWindowEntry, RateWindowFile } from '../lib/types'
import { cn, formatDate, formatNumber } from '../lib/utils'
import { summarizeEnrollmentStatus, describeEnrollmentStatus } from '../lib/enrollment'
import { summarizeDataYears } from '../lib/coverage'
import {
  fmtRate, joinAnd, latestWindowKey, levelPct, listMinStudents, nationalCompositionSentence, oneSidedChance,
  peerLabel, rateCodeLabel, rateCodePhrase, rateCodes, ratioPercent, sharedSiteShareText, windowKeys, windowLabel,
  windowYears,
} from '../lib/rates'
import { SHOW_POINT_POSITION, VERDICT_LABELS } from '../lib/rateDisplay'
import SourceLink from '../components/SourceLink'
import CiteThisData from '../components/CiteThisData'
import { useBuildInfo } from '../lib/build'
import type { AuditCheck, BuildInfo, CalibrationRow } from '../lib/build'
import { SERIES_NOTES, SERIES_CONTEXT } from '../data/seriesNotes'
import { Link, useLocation } from 'react-router-dom'
import {
  SOURCES,
  CRIMINAL_DEFINITIONS,
  VAWA_DEFINITIONS,
  LAW_VIOLATION_DEFINITIONS,
  GEOGRAPHY_DEFINITIONS,
} from '../data/sources'

// "1,234", or "…" while the figure is not loaded
const num = (v: number | null | undefined) => (v === null || v === undefined ? '…' : formatNumber(v))
// "29.3%"
const pct1 = (x: number) => `${formatNumber(x * 100, 1)}%`
// "3 percentage points"
const pctPoints = (x: number) => `${Math.round(x * 100)} percentage ${Math.round(x * 100) === 1 ? 'point' : 'points'}`
// "2015-2019" written for reading: "2015–2019"
const periodLabel = (p: string) => p.replace(/(\d{4})-(\d{4})/, '$1–$2')

// What the figures on this page are drawn from: metadata.json, the window
// files of the latest window (violent crimes, criminal offenses except
// motor-vehicle theft) and of the first (criminal offenses except
// motor-vehicle theft), and the audit
interface RateFacts {
  metadata: Metadata | null
  latest: string | null
  first: string | null
  violent: RateWindowFile | null
  criminalLatest: RateWindowFile | null
  criminalFirst: RateWindowFile | null
  build: BuildInfo | null
}

// On-campus motor-vehicle thefts of a criminal_xmvt window file and their
// share of on-campus criminal offenses (the same institutions: rated, with
// a certain on-campus FTE)
function mvtShare(f: RateWindowFile | null): { mvt: number; share: number } | null {
  const mvt = f?.composition?.motor_vehicle_theft
  if (!f || mvt === undefined || mvt + f.natlN <= 0) return null
  return { mvt, share: mvt / (mvt + f.natlN) }
}

// Where a window's incidents were reported: on campus, or elsewhere
function locationFacts(f: RateWindowFile | null) {
  if (!f || f.entries.length === 0) return null
  let on = 0
  let other = 0
  let more = 0
  let top: RateWindowEntry | null = null
  const gap = (e: RateWindowEntry) => e.nNoncampus + e.nPublic - e.n
  for (const e of f.entries) {
    on += e.n
    other += e.nNoncampus + e.nPublic
    if (gap(e) > 0) more += 1
    if (!top || gap(e) > gap(top)) top = e
  }
  return { rated: f.entries.length, more, onShare: on + other > 0 ? on / (on + other) : null, top: top && gap(top) > 0 ? top : null }
}

// The peer types of a window file, in metadata order, with their rates
function peerRows(f: RateWindowFile | null, metadata: Metadata | null) {
  const types = Object.keys(metadata?.rateRules?.peerTypes ?? {})
  return types
    .filter((t) => f?.peer?.[t])
    .map((t) => ({ key: t, label: peerLabel(t, metadata?.rateRules), ...f!.peer[t] }))
}

// The median width (positions) of the list members' rank ranges
function medianRange(f: RateWindowFile | null): { width: number; n: number } | null {
  const n = f?.list?.n
  if (!f || !n) return null
  const widths = f.entries
    .filter((e) => e.listed && e.rankLo !== undefined && e.rankHi !== undefined)
    .map((e) => e.rankHi! - e.rankLo! + 1)
    .sort((a, b) => a - b)
  if (widths.length === 0) return null
  const mid = Math.floor(widths.length / 2)
  const width = widths.length % 2 ? widths[mid] : (widths[mid - 1] + widths[mid]) / 2
  return { width, n }
}

// The audit check of that name, if the audit has it
const auditCheck = (build: BuildInfo | null, name: string): AuditCheck | null =>
  build?.checks.find((c) => c.name === name) ?? null

// The band limit below the expected share (metadata.json): the one the text
// names. A small top band that the audit tests has a wider limit of its own
// (the row's toleranceBelow), so it can be short by more than this and pass.
const belowLimit = (metadata: Metadata | null): number | undefined =>
  metadata?.rateRules?.calibration?.bandToleranceBelow

// Groups of similar counts (bands, tested or not) whose share inside the
// predicted range is below the expected share by more than the band limit:
// computed here from audit.json, never written in
function shortBands(rows: CalibrationRow[], metadata: Metadata | null): CalibrationRow[] {
  return rows.filter((r) => {
    const limit = belowLimit(metadata)
    return !r.band.startsWith('all') && r.observed !== null && r.expected !== null && limit !== undefined &&
      r.observed < r.expected - limit
  })
}

// A calibration band in words: "all>=2", "2-5", "20+"
function bandLabel(band: string): string {
  let m = band.match(/^all>=(\d+)$/)
  if (m) return `${m[1]} or more a year on average`
  m = band.match(/^(\d+)-(\d+)$/)
  if (m) return `${m[1]} to ${m[2]} a year`
  m = band.match(/^(\d+)\+$/)
  if (m) return `${m[1]} or more a year`
  return band
}

// "Rape in 2015–2019, institutions with 20 or more a year: 86.0% inside against 95.0% expected (20 institutions, too few to test)"
const calibrationText = (r: CalibrationRow) =>
  `${rateCodeLabel(r.code)} in ${periodLabel(r.period)}, institutions with ${bandLabel(r.band)}: ` +
  `${r.observed !== null ? pct1(r.observed) : '–'} inside against ${r.expected !== null ? pct1(r.expected) : '–'} ` +
  `expected (${formatNumber(r.units)} ${r.units === 1 ? 'institution' : 'institutions'}` +
  `${r.tested ? (r.ok === false ? ', fails' : '') : ', too few to test'})`

// Calibration rows as a list, one per line
function CalibrationList({ rows }: { rows: CalibrationRow[] }) {
  return (
    <ul className="list-disc ml-5 my-1 space-y-0.5">
      {rows.map((r) => <li key={`${r.code}-${r.period}-${r.band}`}>{calibrationText(r)}</li>)}
    </ul>
  )
}

// The medical-campus screen's result, in a sentence
function screenSentence(build: BuildInfo | null): string {
  const check = auditCheck(build, 'Medical-Campus Screen')
  if (!check) return ''
  if (check.status === 'PASS') return "This build's screen found no campus that is in neither file."
  // The audit's own messages, without the instruction to maintainers that
  // follows a semicolon
  const text = [...check.warnings, ...check.errors].map((m) => m.split(';')[0].trim().replace(/\.$/, '')).join('; ')
  return `This build's screen reports ${text}.`
}

// The Limitations section, in reading order
function limitations(d: RateFacts): { title: string; body: React.ReactNode }[] {
  const rr = d.metadata?.rateRules
  const rs = d.metadata?.rateStats
  const latest = d.latest
  const latestLabel = latest ? windowLabel(latest) : '…'
  const loc = locationFacts(d.violent)
  const peers = peerRows(d.violent, d.metadata)
  const peer = (key: string) => peers.find((p) => p.key === key)
  const residential = ['nonresidential', 'residential', 'highly_residential'].map(peer)
  const rising = residential.every((p) => p) && residential[0]!.rate < residential[1]!.rate && residential[1]!.rate < residential[2]!.rate
  const range = medianRange(d.violent)
  const cal = d.build?.calibration ?? []
  const short = shortBands(cal, d.metadata)
  const failing = cal.filter((r) => r.tested && r.ok === false)
  const tolBelow = rr?.calibration?.bandToleranceBelow
  const minUnits = rr?.calibration?.bandMinUnits
  // Rated institutions whose comparisons are withheld for a shared campus
  // site (violent crimes, latest window), largest first
  const withheld = (d.violent?.entries ?? []).filter((e) => e.verdict === 'withheld')
    .sort((a, b) => b.fteYears - a.fteYears)
  const noRateShared = rs?.institutionYears?.rules?.shared_campus
  const mvtFirst = mvtShare(d.criminalFirst)
  const mvtLatest = mvtShare(d.criminalLatest)
  const listCodes = rr?.lists?.codes ?? []
  const listSizes = latest
    ? listCodes
        .map((code) => ({ code, f: rs?.windows?.[latest]?.[code]?.minFteYears }))
        .filter((x): x is { code: string; f: number } => x.f !== undefined)
        .map((x) => `${formatNumber(listMinStudents(x.f, rr))} for ${rateCodePhrase(x.code)}`)
    : []
  const chance = oneSidedChance(rr)

  return [
    {
      title: 'Reports, not how often crimes happen',
      body: (
        <>
          Clery figures count crimes reported to campus security authorities or police, not victimization. Many
          crimes are never reported: in the Bureau of Justice Statistics' analysis of the National Crime
          Victimization Survey, 80% of rape and sexual assault victimizations of female college students aged
          18-24 (1995-2013) were not reported to police (
          <SourceLink source={SOURCES.bjsCollege2014}>BJS, NCJ 248471</SourceLink>). That survey does not measure
          reports to campus officials, which Clery figures include, so the share is not a Clery figure. Reporting
          also depends on the institution: universities reported about 44% more sexual assaults while the
          Department of Education was auditing them, and the numbers fell back after the audits (
          <SourceLink source={SOURCES.yung2015}>Yung, 2015</SourceLink>). Nothing on this site corrects for
          differences in reporting. A higher count or rate can mean more crime, more reporting, or both; a lower
          one does not show that a campus is safer.
        </>
      ),
    },
    {
      title: 'Counted by the year reported',
      body: (
        <>
          A year's figure is the crimes reported that year, including some that happened earlier. Many reports of
          past abuse at one institution can make one year jump, and that year raises the rate of every window
          containing it (see <a href="#year-reported" className="underline">How Institutions Count</a>). The site
          flags such years and leaves the figures as reported (
          <a href="#rate-flags" className="underline">Unusual years</a>).
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
      title: 'Rates count only incidents on campus',
      body: (
        <>
          A rate counts the incidents DOE lists as on campus (residence halls included). Incidents at non-campus
          locations and on public property in or next to campus are shown beside it as counts, not in it, and how many
          there are depends on the streets and buildings around a campus.{' '}
          {loc ? (
            <>
              In {latestLabel}, {formatNumber(loc.more)} of the {formatNumber(loc.rated)} institutions with a
              violent-crime rate had more violent crimes reported at those locations than on campus
              {loc.top && (
                <>
                  ; the largest difference was at {loc.top.name}: {formatNumber(loc.top.n)} on campus,{' '}
                  {formatNumber(loc.top.nNoncampus + loc.top.nPublic)} elsewhere
                </>
              )}
              .{' '}
            </>
          ) : null}
          Counting every location would change the order of the lists.
        </>
      ),
    },
    {
      title: 'Rates are per enrolled student, not per person on campus',
      body: (
        <>
          Rates divide by an estimate of the institution's students on campus (FTE). Residents who are not
          students, employees, visitors and patients are not in it, and incidents involving them are counted.
          Because so many people at a hospital or medical center are not students, institutions that IPEDS
          reports have a hospital, special-focus medical institutions and the institutions of a reviewed list
          have no rate, and an institution whose incidents at listed medical-center campuses are{' '}
          {rr ? ratioPercent(rr.medicalShare) : '…'} or more of its on-campus count is not on a list (
          <a href="#rate-population-rules" className="underline">Population rules</a>,{' '}
          <a href="#rate-medical-campuses" className="underline">Medical-center campuses</a>). Gaps remain. The
          hospital rule depends on what the institution reports to IPEDS: a university next to a hospital run by
          a separate organization, such as a health system, can report no hospital. The reviewed list adds the
          universities whose annual security reports say that their figures count incidents at such a hospital,
          and a second reviewed list marks the universities with a hospital next to or inside the main campus
          whose reports do not say whether its incidents are counted; those keep their rates and their places on
          the lists, with a note on their pages (<a href="#rate-hospital-notes" className="underline">Hospital notes</a>). Only
          the reports of universities near the top of the ordered lists were read for these two lists, so a
          university elsewhere can count hospital incidents in its figures without a note. And the list of
          medical-center campuses was reviewed by hand, campus by campus: incidents at a medical center that is
          not on it, or that DOE does not list as a campus of its own, count as ordinary campus incidents.{' '}
          {screenSentence(d.build)}
          {peers.length > 0 && (
            <>
              {' '}On-campus rates also differ by type of institution. In {latestLabel} the violent-crime rate was:{' '}
              {peers.filter((p) => p.key !== 'other').map((p) => `${p.label} ${fmtRate(p.rate)}`).join('; ')}
              {rising ? '. Among four-year institutions it rises from primarily nonresidential to highly residential ones' : ''}.
            </>
          )}
        </>
      ),
    },
    {
      title: 'Shared campuses leave some institutions without a comparison',
      body: (
        <>
          DOE's files give no enrollment per campus. Where campuses of different institutions are at one site and
          report the same incidents, the site's incidents are in one institution's rate or in none, and an
          institution whose students there cannot be counted is shown without a comparison and is not on a list (
          <a href="#rate-shared" className="underline">Shared campuses</a>). The figures that let a guest be
          compared count only the students of the programs their sources cover (the Texas A&amp;M pharmacy
          college's PharmD students, not its PhD students; the Indiana University School of Medicine's MD
          students), and a figure may be another year's, or an upper bound computed from class sizes or a cap per
          class.
          {d.violent && latest && (
            <>
              {' '}In {latestLabel}, {formatNumber(withheld.length)} rated{' '}
              {withheld.length === 1 ? 'institution is' : 'institutions are'} shown without a comparison for this
              reason
              {(() => {
                const minE = rr?.lists?.minExpected
                const big = minE !== undefined ? withheld.filter((e) => e.E >= minE) : []
                if (big.length === 0) return '.'
                return (
                  <>
                    ; {formatNumber(big.length)} of them {big.length === 1 ? 'is' : 'are'} large enough for the
                    violent-crime list (
                    {joinAnd(big.slice(0, 3).map((e) => e.name))}
                    {big.length > 3 ? ', among others' : ''}). Some large institutions therefore have no comparison
                    on this site.
                  </>
                )
              })()}
            </>
          )}
          {noRateShared && noRateShared.withFte > 0 && (
            <>
              {' '}Where the main campuses of two or more institutions are at one site and the site cannot be
              counted with one of them, none of them has a rate in those years:{' '}
              {formatNumber(noRateShared.withFte)} institution-years with a denominator of at least{' '}
              {num(rr?.minFte)}.
            </>
          )}
        </>
      ),
    },
    {
      title: 'Intervals rest on a model fitted to all institutions',
      body: (
        <>
          Each interval allows for year-to-year variation with one variance model per category, fitted to
          institutions' counts together, or with the institution's own spread over the window's three years when
          that is larger (<a href="#rate-interval" className="underline">Intervals</a>). Three yearly counts say
          little about an institution's own variation, so the model sets the least width an interval can have.
          The audit tests the intervals on every build
          by predicting each year's count from the institution's other years (
          <a href="#calibration" className="underline">How well the intervals fit</a>).
          {short.length > 0 && tolBelow !== undefined && (
            <>
              {' '}In {formatNumber(short.length)} {short.length === 1 ? 'group' : 'groups'} of institutions with
              similar counts, fewer counts fall inside the predicted range than the model expects, by more than{' '}
              {pctPoints(tolBelow)}:
              <CalibrationList rows={short} />
              There the intervals understate how much counts vary, so they may be too narrow, and an "above" or
              "below" can be due to chance more often than {chance}.
              {minUnits !== undefined && short.some((r) => !r.tested) && (
                <>
                  {' '}{short.every((r) => !r.tested) ? 'All of these groups have' : `${formatNumber(short.filter((r) => !r.tested).length)} of them have`}{' '}
                  fewer than {formatNumber(minUnits)} institutions, too few for the audit's pass rule, so the audit
                  reports them without failing.
                </>
              )}
              {short.some((r) => r.tested && r.ok !== false && (r.toleranceBelow ?? 0) > (tolBelow ?? 0)) && (
                <>
                  {' '}{short.every((r) => r.tested && r.ok !== false && (r.toleranceBelow ?? 0) > (tolBelow ?? 0))
                    ? 'These groups are'
                    : `${formatNumber(short.filter((r) => r.tested && r.ok !== false && (r.toleranceBelow ?? 0) > (tolBelow ?? 0)).length)} of them are`}{' '}
                  the group with the most incidents of a category the audit tests whatever its size, with limits
                  widened for its number of institutions (
                  <a href="#calibration" className="underline">How well the intervals fit</a>), and pass.
                </>
              )}
            </>
          )}
          {failing.length > 0 && (
            <>
              {' '}The audit reports a failure for{' '}
              {joinAnd(failing.map((r) => `${rateCodeLabel(r.code).toLowerCase()} in ${periodLabel(r.period)} (institutions with ${bandLabel(r.band)})`))}:{' '}
              {failing.every((r) => r.observed !== null && r.expected !== null && r.observed > r.expected)
                ? 'more counts fall inside the predicted range than expected, so those intervals are wider than they need to be on average'
                : 'coverage differs from what the model expects by more than its limit'}{' '}
              (<a href="#audit" className="underline">Data Quality Audit</a>).
            </>
          )}
        </>
      ),
    },
    {
      title: 'A position is a range',
      body: (
        <>
          A listed institution's range holds its position among the list's members with{' '}
          {levelPct(rr)}% confidence, for that institution on its own, not for every range of a list at once.
          Two institutions whose ranges overlap may still differ, and ranges that do not overlap are not a test of
          those two institutions against each other.
          {range && latest && (
            <>
              {' '}For violent crimes in {latestLabel}, the median member's range covers{' '}
              {Number.isInteger(range.width) ? '' : 'about '}{formatNumber(Math.round(range.width))} of the{' '}
              {formatNumber(range.n)} positions.
            </>
          )}{' '}
          Positions in windows five years apart can differ substantially.
        </>
      ),
    },
    {
      title: 'The lists hold only large institutions',
      body: (
        <>
          {listSizes.length > 0 ? (
            <>
              In {latestLabel} a list needs about this many on-campus students or more: {listSizes.join('; ')}.{' '}
            </>
          ) : null}
          At the national rate, a smaller institution would expect fewer than {rr?.lists?.minExpected ?? '…'}{' '}
          incidents in three years, too few to place. Smaller institutions have rates and comparisons, not
          positions (<a href="#rate-lists" className="underline">Ordered lists</a>).
        </>
      ),
    },
    {
      title: 'A rate of 0 is a reported zero',
      body: (
        <>
          A rate of 0 means that no incident of the category was reported on campus at any of the institution's
          campuses in the three years. Its interval still runs above 0, and a large institution with 0 can be on a
          list. A zero can reflect how an institution classifies or reports incidents, not only how safe it is,
          and a small institution can have 0 by chance. A year a campus did not report is not 0: it has no
          figures, and an institution missing from DOE's data in a year has no rate for the windows containing it.
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
          <a href="#rate-abroad" className="underline">Campuses abroad</a>). Those incidents are on each such
          campus's own school page.
        </>
      ),
    },
    {
      title: 'Totals add unlike crimes',
      body: (
        <>
          "All criminal offenses" adds the 11 offenses with equal weight: a murder and a motor-vehicle theft each
          count 1.
          {mvtFirst && mvtLatest && d.first && latest && (
            <>
              {' '}On campus, at the institutions in the national rate, motor-vehicle theft was{' '}
              {pct1(mvtFirst.share)} of criminal offenses in {windowLabel(d.first)} and {pct1(mvtLatest.share)} in{' '}
              {windowLabel(latest)}.
            </>
          )}{' '}
          For this reason the criminal-offense rate leaves motor-vehicle theft out, and rankings open on violent
          crimes. Look at single offenses before drawing conclusions from a total.
        </>
      ),
    },
    {
      title: 'Some years and categories have no rate',
      body: (
        <>
          {rr?.skipYears?.length ? `${joinAnd(rr.skipYears.map(String))} has counts but no rate. ` : ''}
          Motor-vehicle theft, arrests, disciplinary referrals and several rare offenses are shown as counts only (
          <a href="#rate-codes" className="underline">Categories without a rate</a>).
        </>
      ),
    },
    {
      title: 'Reported by institutions, not audited here',
      body: (
        <>
          The figures are what institutions submitted to ED's survey, as ED publishes them. This site does not check
          them against institutions' records or Annual Security Reports; the reviewed lists read some reports only
          for which places and people their figures cover. Its audit checks that the published files
          are consistent with each other and with the pipeline's tables built from DOE's and NCES's files, and
          tests the rate model; it does not verify what institutions reported.
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
}

// Campuses whose figures for `year` come from a release with a known DOE
// file error (metadata.json "knownDefects"), or null when not published
function defectCampuses(metadata: Metadata | null, year: number): number | null {
  const ds = metadata?.knownDefects?.filter((d) => d.year === year)
  if (!ds || ds.length === 0) return null
  return new Set(ds.flatMap((d) => d.unitids)).size
}

// One rule of Rate Rules, with an anchor
function Rule({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <li id={id} className="scroll-mt-20">
      <strong className="text-gray-900 dark:text-gray-100">{title}.</strong> {children}
    </li>
  )
}

// What each audit check verifies, by its name in audit.json
const CHECK_DESCRIPTIONS: Record<string, string> = {
  'School Completeness': 'every campus that reported a year, zeros included, has a published file and is in the search',
  'Incident Total Accuracy': 'each school file has exactly the years the campus reported, and its yearly totals match the aggregate table',
  'FTE Coverage': 'enrollment coverage by year',
  'Rate Calculation Accuracy': 'every published rate, of three-year windows and single years, is its count per 10,000 student-years to 2 decimals and lies inside its interval',
  'Ranking Order Validation': 'ranks by count are shared on ties (1, 2, 2, 4); rate files are in rate order, and list positions and ranges agree with it',
  'Ranking Totals and Tables': "each ranking's totals and tables agree with its entries, and the rate files agree with each other and with the school files",
  'Aggregate Consistency': 'the aggregate tables match the fact table they are built from, per year and location',
  'Shared Statistics Counted Once': 'figures two campuses, or one campus under its old and new DOE ID, report identically are counted once in totals and rankings',
  'Enrollment Matches NCES': "every FTE, online share and headcount the rates use is NCES's own published figure",
  'Institution Rates': 'the figures rates are made of: U.S. campuses, both on-campus FTE estimates, the rules that give no rate, pooled institutions, counts per location, medical-center and shared figures, and the peer type',
  'Campus Identity': 'the reviewed list of renumbered campuses matches the DOE files, linked pages name each other, and every school is in the search under its campus name',
  'Rate Rules': 'every three-year rate, interval, comparison, list, position, range, state and type list, unusual-year flag, single-year rate and count flag recomputed with a separate implementation, and the rules in metadata.json checked against the design',
  'Interval Calibration': "how often each year's count falls inside the range the interval model predicts from the institution's other years, against how often it should",
  'Medical-Campus Screen': "campuses whose DOE name or address suggests a medical center, and that hold a material share of an institution's on-campus count, are on the medical-center campus list or recorded as reviewed (a warning otherwise, never a failure)",
}

const STATUS_STYLES: Record<string, string> = {
  PASS: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  WARNING: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  FAIL: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
}

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
  // rateStats); "…" until metadata.json is loaded
  const rr = metadata?.rateRules
  const rs = metadata?.rateStats
  const iy = rs?.institutionYears
  const keys = windowKeys(rr)
  const latest = latestWindowKey(rr)
  const first = keys.length > 0 ? keys[0] : null
  const latestLabel = latest ? windowLabel(latest) : '…'
  const latestYear = latest ? String(windowYears(latest)[1]) : null
  const w = latest ? rs?.windows?.[latest] : undefined
  const ci = levelPct(rr)
  const share = (r: [number, number] | undefined, above = false) => (r ? ratioPercent(r, above) : '…')
  const offenseName = (code: string) => {
    const o = metadata?.offenses.find((x) => x.code === code)
    return o ? o.display.toLowerCase() : code.replace(/_/g, ' ')
  }
  const listCodes = rr?.lists?.codes ?? []
  const codesWithRate = rateCodes(rr)

  // The window files the text draws on (fetched here; the figures show "…" until they arrive)
  const [files, setFiles] = React.useState<Record<string, RateWindowFile>>({})
  React.useEffect(() => {
    if (!latest || !rr) return
    let live = true
    const wanted: [string, string][] = [[latest, 'violent'], [latest, 'criminal_xmvt']]
    if (first && first !== latest) wanted.push([first, 'criminal_xmvt'])
    wanted
      .filter(([, code]) => code in rr.codes)
      .forEach(([key, code]) => {
        fetchRateWindow(key, code)
          .then((f) => live && setFiles((prev) => ({ ...prev, [`${key}-${code}`]: f })))
          .catch(() => {})
      })
    return () => {
      live = false
    }
  }, [latest, first, rr])
  const facts: RateFacts = {
    metadata,
    latest,
    first,
    violent: latest ? files[`${latest}-violent`] ?? null : null,
    criminalLatest: latest ? files[`${latest}-criminal_xmvt`] ?? null : null,
    criminalFirst: first ? files[`${first}-criminal_xmvt`] ?? null : null,
    build,
  }
  const peers = peerRows(facts.violent, metadata)
  const range = medianRange(facts.violent)
  // Shared campus sites, latest window, violent crimes: guests compared as
  // usual because of a published figure, and withheld institutions large
  // enough for the list
  const siteShare = sharedSiteShareText(rr) ?? '…'
  const violentEntries = facts.violent?.entries ?? []
  const exemptN = violentEntries.filter((e) => e.sharedSite?.exempt && e.verdict !== 'withheld').length
  const minExpected = rr?.lists?.minExpected
  const bigWithheld = minExpected === undefined
    ? 0
    : violentEntries.filter((e) => e.verdict === 'withheld' && e.E >= minExpected).length
  const mvtFirst = mvtShare(facts.criminalFirst)
  const mvtLatest = mvtShare(facts.criminalLatest)

  // Interval examples: the published test vectors of a code's c over a window
  const vector = (code: string, n: number) => {
    const c = rr?.dispersion?.c?.[code]
    return rr?.testVectors?.counts.find((v) => v.c === c && v.years === rr.windowYears && v.n === n) ?? null
  }
  const interval = (code: string, n: number, digits: number) => {
    const v = vector(code, n)
    if (!v) return '…'
    const [lo, hi] = v.interval
    const f = (x: number) => (x === 0 ? '0' : formatNumber(x, digits))
    return `${f(lo)} to ${f(hi)}`
  }

  const yearRows = iy ? Object.entries(iy.byYear).sort(([a], [b]) => a.localeCompare(b)) : []
  const ruleTotals = iy
    ? Object.values(iy.rules).reduce((a, r) => ({ all: a.all + r.institutionYears, withFte: a.withFte + r.withFte }), { all: 0, withFte: 0 })
    : null
  // The first year after the years that use another fall's online share,
  // and whether more institutions have an uncertain on-campus FTE in it
  const shareYears = Object.keys(rr?.onlineShareYear ?? {}).map(Number)
  const lastShared = shareYears.length > 0 ? Math.max(...shareYears) : null
  const ownAgain = lastShared !== null ? iy?.byYear[String(lastShared + 1)] : undefined
  const before = lastShared !== null ? iy?.byYear[String(lastShared)] : undefined
  const uncertainRises = !!ownAgain && !!before && ownAgain.fteUncertain > before.fteUncertain
  // Counts-only categories counted inside the criminal-offense rate (rare offenses)
  const rareCodes = (rr?.countsOnly ?? []).filter((c) => rr?.codes?.criminal_xmvt?.includes(c) && c !== 'motor_vehicle_theft')
  const checks = build?.checks ?? []
  const statusCount = (s: string) => checks.filter((c) => c.status === s).length
  const calibration = build?.calibration ?? []
  // The calibration table: one row per category and period, one column per
  // group of counts, in the audit's order
  const calColumns = Array.from(new Set(calibration.map((r) => r.band)))
  const calKeys = calibration
    .filter((r, i) => calibration.findIndex((x) => x.code === r.code && x.period === r.period) === i)
    .map((r) => ({ code: r.code, period: r.period }))
  const calBands = rr?.calibration?.bands ?? []
  const calShort = shortBands(calibration, metadata)

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
                          <strong className="text-gray-900 dark:text-gray-200">Zero is not the same as not reported:</strong> A campus reported a year when its row in that release has at least one figure that is not blank. A reported year without incidents shows as 0 on the school page and in its charts, and in rankings by count the campus is ranked with 0, after the campuses with incidents, sharing one rank, by name. An institution with no incident on campus at any of its campuses in a rate's three years has a rate of 0, with an interval above 0. A year a campus did not report has no figures at all: its page lists it as not reported and its charts leave a gap there, not a 0. Campuses that reported but never had an incident have school pages too.
                        </span>
                      </div>
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Known errors in DOE files:</strong> In the 2021-2023 release (Crime2024SAS.zip), the residence-hall disciplinary file repeats the on-campus figures for 2022 and 2023, and the residence-hall arrest file has no 2022 liquor-law column. For campuses whose 2022 or 2023 figures come from that release, 2022 residence-hall disciplinary actions and liquor-law arrests come from the 2020-2022 release, and 2023 residence-hall disciplinary actions are left blank.
                        </span>
                      </div>
                      <div id="copies" className="flex items-start gap-2 scroll-mt-20">
                        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                        <span className="min-w-0 text-gray-600 dark:text-gray-400">
                          <strong className="text-gray-900 dark:text-gray-200">Figures reported by more than one campus:</strong> Some campuses report exactly the same {metadata ? metadata.offenses.filter((o) => o.family !== 'Summary').length : '…'} figures for a location (on-campus, non-campus or public property) as another campus in the same state and year, at least {rr?.sharedCopies?.minNonzero ?? '…'} of them nonzero, usually because a branch repeats its parent's statistics. When a campus's whole year (all three locations, at least {rr?.sharedCopies?.minNonzero ?? '…'} figures nonzero) matches another campus's, all of its locations count as copies. For a campus-year taken from an older release, a match with another campus in that same release counts too, even if that campus has since corrected its figures. School pages show the figures as DOE publishes them; state and national totals and rankings count them once, under one host campus, which the school page names. The host is the campus whose figures come from the newest release for that year, then the main campus, then the one with more students (FTE), then the larger total, then the lower IPEDS ID. One more case: when DOE reported a campus under a new ID (see below) and both IDs have the same whole year (every figure, at least one nonzero) from different releases, the older release's copy counts under the newer ID, whatever the number of nonzero figures. And when campuses of different institutions in the same city have the same whole year (all three locations), with figures adding up to at least {rr?.sharedCopies?.cityMinTotal ?? '…'}, they count as one report filed by each (for example by the schools of one hospital, or by institutions on one shared campus), whatever the number of nonzero figures, and count once under the host chosen as above. The rates treat such a campus as described under <a href="#rate-shared" className="underline">Shared campuses</a>: an institution with no other campus counting that year has no figures of its own that year, and its students are added to the host's rate.
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
              FTE is the basis of the per-student rates: full-time students count fully and part-time students count in part, so schools of different sizes and mixes can be compared. We use the FTE that NCES publishes for each institution and fall, for every year; we do not calculate it. Rates divide by an estimate of the part of it on campus, made from NCES's FTE, its fall headcounts and its share of students enrolled exclusively in distance education, added over a rate's three years (see <a href="#rate-denominator" className="underline">On-campus students</a>).
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
                  <a href="#rate-denominator" className="underline">On-campus students</a>).
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

          {/* Crime rates */}
          <section id="rates" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Crime Rates
              </h2>
            </div>

            <div className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl p-6 border border-green-100 dark:border-green-900/50 mb-6">
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">In plain words</h3>
              <ul className="list-disc ml-5 space-y-2 text-sm text-gray-700 dark:text-gray-300 mb-4">
                <li>
                  A rate is the number of incidents reported on campus over {rr?.windowYears ?? '…'} years, per 10,000
                  on-campus students a year. The years are {keys.length > 0 ? joinAnd(keys.map(windowLabel)) : '…'}
                  {rr?.skipYears?.length ? <>; no rate includes {joinAnd(rr.skipYears.map(String))}</> : null}.
                </li>
                <li>
                  Each rate has a {ci}% interval: the underlying rates its counts are consistent with, given how much
                  yearly counts vary, as much as is usual for an institution with that many incidents or as much as
                  its own three yearly counts varied when that is more. It does not allow for differences in how
                  institutions record and report incidents.
                </li>
                <li>
                  Each rate is compared with the national rate: "{VERDICT_LABELS.above}" or "{VERDICT_LABELS.below}"
                  when its whole interval is on one side, otherwise "{VERDICT_LABELS.nd}". It is also compared, the
                  same way, with institutions of its type.
                </li>
                <li>
                  For {listCodes.length > 0 ? joinAnd(listCodes.map(rateCodePhrase)) : '…'}, institutions large enough
                  to expect at least {rr?.lists?.minExpected ?? '…'} incidents at the national rate are placed on an
                  ordered list, unless one of their years in the window is unusually high.{' '}
                  {SHOW_POINT_POSITION
                    ? 'Each position is given with a range: positions closer together than the ranges cannot be told apart. Positions within a state and within a type of institution are given the same way.'
                    : 'A list is ordered by rate, and each institution on it is shown with the range of positions it could hold: positions closer together than the ranges cannot be told apart. Ranges within a state and within a type of institution are given the same way.'}
                </li>
                <li>
                  A year that is unusually high for an institution is flagged, not removed: the rate counts it as
                  reported.
                </li>
                <li>
                  Arrests, disciplinary referrals, motor-vehicle theft and several rare offenses are shown as counts
                  only.
                </li>
              </ul>
              <code className="block bg-white dark:bg-gray-900 rounded-lg p-4 text-sm text-gray-800 dark:text-gray-200 font-mono mb-3 whitespace-normal break-words">
                Rate = on-campus incidents in the {rr?.windowYears ?? '…'} years ÷ (on-campus FTE of each of the{' '}
                {rr?.windowYears ?? '…'} years, added) × 10,000
              </code>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                A size-adjusted figure: it removes the effect of enrollment size on counts, not the other differences
                between institutions listed under <a href="#limitations" className="underline">Limitations</a>. Every
                rule, with its threshold, is under <a href="#rate-rules" className="underline">Rate Rules</a> below.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 sm:col-span-2">
                <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Rates Are Per Institution</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  NCES publishes enrollment (FTE) for each institution, not for each campus, and every campus of an
                  institution (all campuses whose UNITID starts with the same six digits) carries the same FTE. So a
                  rate adds the on-campus incidents of all the institution's campuses in the United States (campuses
                  abroad are left out: <a href="#rate-abroad" className="underline">Campuses abroad</a>) and divides
                  them by the institution's on-campus FTE. Rate lists name the institution as of the window's last
                  year and link to its main campus (or, when the main campus did not report that year, to its campus
                  with the most incidents); the school page of any of its campuses shows the institution's rates.
                  Rankings by count still list each campus.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Total Counts</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Sum of on-campus + non-campus + public property (excluding residence halls to avoid double-counting).
                  Figures reported identically by two campuses count once, under the host campus, in state and national totals and rankings.
                </p>
              </div>
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-2">Ties</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  In rankings by count, campuses with the same count share a rank, and the next rank skips the places
                  the tie takes: 1, 2, 2, 4. Tied campuses are listed by name, and campuses that reported the year but
                  had none of the selected category come last, with 0, sharing one rank. On rate lists, institutions
                  with the same rate {SHOW_POINT_POSITION ? 'share a position the same way and are listed by name' : 'are listed by name (in the data they share a position the same way)'}.
                </p>
              </div>
            </div>

            <h3 id="rate-rules" className="scroll-mt-20 text-lg font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-3">
              Rate Rules
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Every rule the rates follow, with the thresholds published in <code>metadata.json</code> (
              <code>rateRules</code>). None of them changes a count or the order of a ranking by count; the last one
              adds a flag to rankings by count. Figures that depend on the data are this build's. An institution-year
              is one institution in one year; a window is one of the {rr?.windowYears ?? '…'}-year periods rates
              cover.
            </p>
            <ol className="list-decimal pl-5 space-y-4 text-sm text-gray-600 dark:text-gray-400">
              <Rule id="rate-windows" title="Windows">
                Rates are {rr?.windowYears ?? '…'}-year averages, for {keys.length > 0 ? joinAnd(keys.map(windowLabel)) : '…'}.
                {rr?.skipYears?.length ? (
                  <>
                    {' '}No window contains {joinAnd(rr.skipYears.map(String))}: in fall 2020 many institutions taught
                    remotely for the pandemic, and NCES's fall enrollment does not show who was on campus, so{' '}
                    {joinAnd(rr.skipYears.map(String))} has counts but no rate.
                  </>
                ) : null}{' '}
                A window holds more incidents than one year, so its interval is narrower. There are no comparisons
                or lists for single years (<a href="#rate-single-years" className="underline">Single years</a>).
              </Rule>
              <Rule id="rate-numerator" title="Incidents">
                The incidents DOE lists as on campus (its On-campus figures, which include residence halls), at every
                campus of the institution in the United States, added over the window's years. Incidents at
                non-campus locations and on public property are shown beside the rate as counts, not in it. The
                incidents of a campus site that campuses of two or more institutions report are in one institution's
                rate at most (<a href="#rate-shared" className="underline">Shared campuses</a>). The categories with a
                rate and the offenses each adds:
                <ul className="list-disc ml-5 mt-2 space-y-1">
                  {codesWithRate.map((code) => (
                    <li key={code}>
                      <span className="text-gray-900 dark:text-gray-100">{rateCodeLabel(code)}</span>:{' '}
                      {joinAnd((rr?.codes[code] ?? []).map(offenseName))}
                    </li>
                  ))}
                </ul>
                <span className="block mt-2">
                  Violent crimes are the four offenses of the FBI's violent crime (
                  <SourceLink source={SOURCES.fbiViolent2019}>FBI, Crime in the United States 2019: Violent Crime</SourceLink>).
                  The other categories are under{' '}
                  <a href="#rate-codes" className="underline">Categories without a rate</a>.
                </span>
              </Rule>
              <Rule id="rate-denominator" title="On-campus students">
                The denominator is student-years: the institution's on-campus FTE in each year of the window, added.
                Clery figures cover the campus, so the on-campus FTE leaves out students enrolled exclusively in
                distance education. NCES gives their share of the fall headcount (PCTDEEXC), not of FTE, and the part
                of FTE they make up depends on how many of them study part-time, so there are two estimates: (a)
                proportional, FTE × (1 − PCTDEEXC / 100); (b) part-time first: the on-campus headcount, headcount ×
                (1 − PCTDEEXC / 100), holds all the full-time students it can, and the rest are part-time students,
                each counting the institution's FTE per part-time student, (FTE − full-time students) / part-time
                students. Estimate (b) is made for undergraduates and graduate students separately when the year's own
                share is used and NCES gives each level's headcounts, full-time headcounts and share (2021 on), and
                the levels add up to the totals (a level without students counts a share of 0); else it is made from
                the totals. It cannot be computed when the headcounts are missing, the full-time and part-time
                headcounts do not add up to the total, or the FTE is below the full-time headcount or above the total
                headcount. The on-campus FTE is the larger estimate, rounded half up to a whole number, and the
                smaller is rounded the same way; an institution without a PCTDEEXC, or with a PCTDEEXC of 0, keeps its
                full FTE, and its FTE is certain. A student who takes some courses online counts as on campus.
                {rr?.onlineShareYear && Object.keys(rr.onlineShareYear).length > 0 && (
                  <>
                    {' '}For {joinAnd(Object.keys(rr.onlineShareYear))}, when many institutions taught remotely for the
                    pandemic, the estimates use the institution's fall{' '}
                    {joinAnd(Array.from(new Set(Object.values(rr.onlineShareYear))).map(String))} share (its own year's
                    share when NCES has none for that fall:{' '}
                    {joinAnd(Object.keys(rr.onlineShareYear).map((y) => `${num(iy?.onlineOwnYear[y]?.all)} institutions in ${y}`))}).
                  </>
                )}{' '}
                When the larger estimate is more than {share(rr?.onlineUncertainRatio, true)} above the smaller, or
                (b) cannot be computed, the on-campus FTE is uncertain. The
                rate then uses the larger estimate, each comparison is made with both, and when the two give
                different results the comparison is "{VERDICT_LABELS.undetermined}". Such an institution is never on
                a list, and the national and peer rates leave it out. The same holds when the denominator adds the
                on-campus FTE of another institution (
                <a href="#rate-mergers" className="underline">Mergers</a>,{' '}
                <a href="#rate-shared" className="underline">Shared campuses</a>) whose estimates are uncertain.
                {w?.violent && (
                  <>
                    {' '}In {latestLabel}, {num(w.violent.byWhy.online)} of the {num(w.violent.rated)} rated
                    institutions have an uncertain on-campus FTE in at least one year; for violent crimes,{' '}
                    {num(w.violent.verdicts.undetermined)} of them are "{VERDICT_LABELS.undetermined}".
                  </>
                )}
                {uncertainRises && lastShared !== null && (
                  <>
                    {' '}More institution-years have an uncertain on-campus FTE from {lastShared + 1} on (table below),
                    the first year after {joinAnd(shareYears.map(String))} that uses each fall's own share.
                  </>
                )}{' '}
                Sources: <SourceLink source={SOURCES.drvefDictionary}>NCES, DRVEF data dictionary</SourceLink>.
              </Rule>
              <Rule id="rate-population" title="Who has a rate">
                An institution has a rate for a window when DOE's data has figures of its own for it in every year of
                the window (a year whose figures all count under another institution's campus has none:{' '}
                <a href="#copies" className="underline">Figures reported by more than one campus</a>); the campus
                its rates link to in the window's last year is in one of the 50 states, the District of Columbia,
                Puerto Rico or the U.S. Virgin Islands; its denominator is at least {num(rr?.minFte)} in every year,
                because with fewer students a few incidents move the rate far; and none of the population rules below
                applies in any year of the window. Otherwise its school page says which of these it fails (the first,
                in this order). Institutions elsewhere, such as in Guam, have counts but no rate.
                {w?.violent && <> In {latestLabel}, {num(w.violent.rated)} institutions have a rate.</>}
              </Rule>
              <Rule id="rate-population-rules" title="Population rules: campuses whose population is not mostly students">
                A rate per student says little where many people on campus are not in FTE. An institution has no rate
                for any window containing a year in which IPEDS reports that it has a hospital (HD variable HOSPITAL =
                1: patients, visitors and hospital staff; {num(iy?.rules.hospital.institutionYears)} institution-years,{' '}
                {num(iy?.rules.hospital.withFte)} of them in the states covered with a denominator of at least{' '}
                {num(rr?.minFte)}); else, in every year, an institution that any edition of the Carnegie basic
                classification, in the IPEDS file of any data year, codes as "Special Focus Four-Year: Medical Schools
                &amp; Centers" (code 25 of C15BASIC, C18BASIC or C21BASIC) or as the 2021 category "Special Focus
                Research Institution" (C21BASIC 27; {num(rs?.carnegieResearch?.c18Medical)} of its{' '}
                {num(rs?.carnegieResearch?.institutions)} institutions in {rs?.carnegieResearch?.year ?? '…'} were
                medical schools and centers in the 2018 classification) ({num(iy?.rules.medical.institutionYears)}{' '}
                institution-years, {num(iy?.rules.medical.withFte)}); else that is on a reviewed list with a sourced
                reason, etl/reference/rate_population_exclusions.csv in the open-source pipeline (
                {num(iy?.rules.listed.institutionYears)} institution-years, {num(iy?.rules.listed.withFte)}): Gallaudet
                University, whose campus also holds the Clerc Center's Kendall Demonstration Elementary School and
                Model Secondary School for the Deaf, whose pupils are not in its FTE (
                <SourceLink source={SOURCES.clercCenter}>Laurent Clerc National Deaf Education Center</SourceLink>);
                AdventHealth University, whose main campus's Clery geography includes a hospital that IPEDS does not
                flag (<SourceLink source={SOURCES.adventHealthAsr2018}>AdventHealth University, Annual Security Report 2018</SourceLink>);
                and Vanderbilt University, Yale University, the University of North Carolina at Chapel Hill, West
                Virginia University, the University of Pittsburgh-Pittsburgh Campus and George Washington University,
                in the years their annual security reports count incidents at a hospital whose patients, visitors and
                staff are not in their FTE (each school page gives the years, the report's account and its source).
                Such a year also has no single-year rate. HOSPITAL is what the institution reports to IPEDS, so a
                university next to a hospital run by a separate organization, such as a health system, can report no
                hospital; see{' '}
                <a href="#rate-hospital-notes" className="underline">Hospital notes</a> and{' '}
                <a href="#rate-medical-campuses" className="underline">Medical-center campuses</a>. Two more rules can
                give no rate to an institution whose main campus shares a site with another institution's main
                campus (
                <a href="#rate-shared" className="underline">Shared campuses</a>). Sources:{' '}
                <SourceLink source={SOURCES.ipedsHdDictionary}>IPEDS HD data dictionary</SourceLink>,{' '}
                <SourceLink source={SOURCES.carnegie2021}>Carnegie Classification, 2021 Basic Classification</SourceLink>.
              </Rule>
              <Rule id="rate-mergers" title="Mergers and renumbered campuses">
                In a year DOE reported a campus under two institutions (its old and its new ID, from different
                releases), the institution whose NCES FTE holds the campus's students is the only one of the two with
                an FTE or, when both have one, the one whose every campus that year is such a linked campus. When the
                other institution counts the campus and the students' institution counts no campus of its own that
                year, the other's denominator adds the students' institution's on-campus FTE (both institutions'
                students over both institutions' incidents). An institution has no rate for a window containing that
                year, and no single-year rate that year, only when a campus with at least one incident that year has
                its incidents counted under one institution and its students under another, when it cannot be told
                which FTE holds the students, or when those students' FTE would be split among several institutions.
                In a year a merged institution's campuses count under several institutions and one of them has no
                NCES FTE while counting a campus with incidents that no institution with an FTE also counts, every
                institution of the group has no rate. A campus with no incident that year needs none of this:
                whichever FTE holds its students, every rate is the same. These rules give no rate to{' '}
                {iy ? num(iy.rules.merger.institutionYears + iy.rules.family.institutionYears) : '…'} institution-years
                that the population rules do not already cover (
                {iy ? num(iy.rules.merger.withFte + iy.rules.family.withFte) : '…'} in the states covered with a
                denominator of at least {num(rr?.minFte)}), and {num(iy?.pooled.merger)} institution-years have
                another institution's FTE added.
              </Rule>
              <Rule id="rate-interval" title="Intervals">
                Each rate has a {ci}% interval. Institutions' yearly counts vary more than chance alone (a Poisson
                count) would make them vary, and more so where counts are larger. For a yearly mean m the variance is
                m + c·g(m)·m<sup>{rr?.dispersion?.power ?? '…'}</sup>, the NB-P form (
                <SourceLink source={SOURCES.greene2008}>Greene, 2008</SourceLink>), with g(m) = min(
                {rr?.dispersion?.ramp.cap ?? '…'}, max(1, m / {rr?.dispersion?.ramp.start ?? '…'})): g rises from 1 at{' '}
                {rr?.dispersion?.ramp.start ?? '…'} a year to {rr?.dispersion?.ramp.cap ?? '…'} at{' '}
                {rr?.dispersion?.ramp.end ?? '…'} a year. Every value of the constant c was fitted the same way, on
                the on-campus counts of 2015–2019 of the institutions that reported all five years with an on-campus
                FTE of at least {num(rr?.minFte)}, none of the rules that give no rate, and a certain on-campus FTE (the method is
                described in etl/config.py of the open-source pipeline). Fitted on each category's own counts, c is{' '}
                {rr
                  ? joinAnd(rateCodes(rr).filter((code) => rr.dispersion.fitted[code] !== undefined)
                      .map((code) => `${rr.dispersion.fitted[code]} for ${rateCodePhrase(code)}`))
                  : '…'}
                . Fitted on the single crime offenses together, it is {rr?.dispersion?.other ?? '…'}, which the
                categories without a fit of their own use:{' '}
                {rr
                  ? joinAnd(rateCodes(rr).filter((code) => rr.dispersion.fitted[code] === undefined).map(rateCodePhrase))
                  : '…'}
                . For a window total N
                over T years the model's variance is φ·N with φ = 1 + c·g(N/T)·√(N/T).
                {rr?.dispersion?.spread === 'max' && (
                  <>
                    {' '}An institution's own yearly counts can vary more than that: one year of many reports between
                    two quiet ones, for example. So φ is the larger of the model's and T·s²/N, where s² is the sample
                    variance of the institution's yearly counts in the window (n − 1 in the denominator); with N = 0
                    it is the model's. When its own spread is the larger, the school page says so and gives the yearly
                    counts.
                  </>
                )}{' '}
                The interval of the count is φ times the gamma interval of the effective count N/φ (
                <SourceLink source={SOURCES.fayFeuer1997}>Fay and Feuer, 1997</SourceLink>; with φ = 1 it is the exact
                Poisson interval, <SourceLink source={SOURCES.garwood1936}>Garwood, 1936</SourceLink>), with a lower end
                of 0 when N is 0. Divided by the student-years and multiplied by 10,000, it is the rate's interval.
                For violent crimes over {rr?.windowYears ?? '…'} years, the interval of a count of 20 is{' '}
                {interval('violent', 20, 1)}, of 1,000 it is {interval('violent', 1000, 0)}, and of 0 it is{' '}
                {interval('violent', 0, 1)}. The interval does not allow for differences in how institutions record
                and report incidents. Whether the model fits is tested on every build (
                <a href="#calibration" className="underline">How well the intervals fit</a>).
              </Rule>
              <Rule id="rate-verdicts" title="Comparisons with the national rate">
                The national rate of a window and category is the on-campus incidents of the rated institutions,
                divided by their student-years and multiplied by 10,000, leaving out the institutions whose on-campus
                FTE is uncertain. A rate is "{VERDICT_LABELS.above}" when the lower end of its interval is above the
                national rate, "{VERDICT_LABELS.below}" when the upper end is below it, and otherwise "
                {VERDICT_LABELS.nd}"; the test uses unrounded figures, so an end of the interval and the national rate
                can be equal to two decimals, as the site shows them, and still differ: the page then shows both to
                four decimals. If the
                intervals have their intended coverage,
                an institution whose underlying rate equals the national rate is shown as above with a chance of about{' '}
                {oneSidedChance(rr)}, and as below with the same chance
                {w?.violent && rr && (
                  <>
                    : if all {num(w.violent.rated)} institutions rated in {latestLabel} had the national rate, about{' '}
                    {formatNumber(Math.round(w.violent.rated * (1 - rr.ciLevel) / 2))} would be shown as above and as
                    many as below by chance alone
                  </>
                )}
                . A comparison is with the national rate, not with another institution. An institution with a campus
                at a site shared with another institution may have both comparisons withheld ("
                {VERDICT_LABELS.withheld}"; <a href="#rate-shared" className="underline">Shared campuses</a>).
              </Rule>
              <Rule id="rate-peers" title="Comparisons with institutions of the same type">
                Each rate is also compared, the same way, with the rate of institutions of its type, computed like the
                national rate within the type. The type comes from the Carnegie Size &amp; Setting classification in
                IPEDS (the newest of {rr ? joinAnd(rr.sizeSettingFields) : '…'} that classifies the institution):{' '}
                {rr
                  ? Object.values(rr.peerTypes)
                      .map((t) => (t.sizeSetting.length > 0 ? `${t.label} (codes ${t.sizeSetting.join(', ')})` : t.label))
                      .join('; ')
                  : '…'}
                .
                {peers.length > 0 && (
                  <>
                    {' '}Violent-crime rates by type in {latestLabel}:{' '}
                    {peers.map((p) => `${p.label} ${fmtRate(p.rate)} (${formatNumber(p.members)} institutions)`).join('; ')}.
                  </>
                )}{' '}
                When the two comparisons differ, the school page says why.
              </Rule>
              <Rule id="rate-lists" title="Ordered lists">
                For {listCodes.length > 0 ? joinAnd(listCodes.map(rateCodePhrase)) : '…'}, the rated institutions
                that none of the reasons below keeps off are placed on an ordered list when they are large enough that
                at least {rr?.lists?.minExpected ?? '…'} incidents would be expected at the national rate (the
                national rate times their student-years). That depends on size only, never on the count. Rates on
                fewer than 20 events are marked unreliable by CDC WONDER (
                <SourceLink source={SOURCES.cdcWonderUnreliable}>CDC WONDER</SourceLink>). An institution that meets
                these conditions but has an unusual year (<a href="#rate-flags" className="underline">Unusual years</a>)
                on campus, of one of the category's offenses, in the window is not placed, so that one year's count
                does not set its place; the list page shows it in a group of its own, with its rate and comparisons.
                {w && latest && (
                  <>
                    {' '}In {latestLabel},{' '}
                    {joinAnd(listCodes.filter((c) => w[c]?.listed !== undefined).map((c) =>
                      `the list of ${rateCodePhrase(c)} has ${formatNumber(w[c].listed!)} members (about ${formatNumber(listMinStudents(w[c].minFteYears ?? 0, rr))} or more on-campus students)` +
                      (w[c].notPlaced !== undefined ? ` and ${formatNumber(w[c].notPlaced!)} not placed` : '')))}
                    .
                  </>
                )}{' '}
                Members are ordered by rate, highest first; equal rates share a position (1, 2, 2, 4) and are listed
                by name.{SHOW_POINT_POSITION ? '' : ' The pages show each member\'s range, not its position; the data have both.'} Each member's rate is compared with every other member's by a z-test of the difference,
                with each member's variance the larger of the interval model's at their pooled rate and its own
                yearly spread (<a href="#rate-interval" className="underline">Intervals</a>), at the level{' '}
                {rr?.lists?.alpha ?? '…'} / (2(n − 1)) for a list of n members (Bonferroni). The range runs from 1 +
                the number of members whose rate is significantly higher to n − the number whose rate is significantly
                lower, widened to hold its position. With {ci}% confidence the institution's position among the n
                members lies in its range (
                <SourceLink source={SOURCES.mogstad2024}>Mogstad, Romano, Shaikh and Wilhelm, 2024</SourceLink>). This
                holds for each institution on its own, not for all ranges of a list at once; two institutions whose
                ranges overlap may still differ.
                {range && (
                  <>
                    {' '}For violent crimes in {latestLabel}, the median member's range covers{' '}
                    {Number.isInteger(range.width) ? '' : 'about '}{formatNumber(Math.round(range.width))} of the{' '}
                    {formatNumber(range.n)} positions.
                  </>
                )}{' '}
                League tables of institutions have these limits in general (
                <SourceLink source={SOURCES.goldsteinSpiegelhalter1996}>Goldstein and Spiegelhalter, 1996</SourceLink>).
              </Rule>
              <Rule id="rate-state-lists" title="Positions within a state">
                A state's positions are the national list's members in that state, with positions and ranges
                recomputed among them alone. The data has them for every state with at least{' '}
                {rr?.lists?.stateMinMembers ?? '…'} members; this site shows {SHOW_POINT_POSITION ? 'them' : 'their ranges'} for states with at least{' '}
                {rr?.lists?.stateDisplayMin ?? '…'}, and for a state with fewer it shows its members'{' '}
                {SHOW_POINT_POSITION ? 'national positions' : 'ranges on the national list'}.
                {w?.violent?.stateListsDisplayMin !== undefined && rr?.lists?.stateDisplayMin !== undefined && (
                  <>
                    {' '}In {latestLabel}, {formatNumber(w.violent.stateListsDisplayMin)} states have at least{' '}
                    {rr.lists.stateDisplayMin} members on the violent-crime list.
                  </>
                )}
              </Rule>
              <Rule id="rate-type-lists" title="Positions within a type">
                A type's positions are the national list's members of one type of institution (
                <a href="#rate-peers" className="underline">Comparisons with institutions of the same type</a>), with
                positions and ranges recomputed among them alone, like a state's. The data has them for every type
                with at least {rr?.lists?.typeMinMembers ?? '…'} members, and the list page and school pages show
                {SHOW_POINT_POSITION ? ' them' : ' their ranges'}. On-campus rates differ by type, and a position within a type compares an institution only with
                institutions of the same type.
                {w?.violent?.typeLists !== undefined && (
                  <>
                    {' '}In {latestLabel}, {formatNumber(w.violent.typeLists)} types have{' '}
                    {SHOW_POINT_POSITION ? 'positions' : 'ranges of their own'} on the violent-crime list.
                  </>
                )}
              </Rule>
              <Rule id="rate-reasons" title="Rated but not on a list">
                Three reasons keep a rated institution off a list: an uncertain on-campus FTE (
                <a href="#rate-denominator" className="underline">On-campus students</a>); incidents at listed
                medical-center campuses, outside their residence halls, of {share(rr?.medicalShare)} or more of its
                on-campus count (<a href="#rate-medical-campuses" className="underline">Medical-center campuses</a>),
                with its rate and comparisons shown; and a campus at a site shared with another institution whose
                students there are not shown by a published figure to be few (
                <a href="#rate-shared" className="underline">Shared campuses</a>), with its rate shown and its
                comparisons withheld. Institutions with the second or third reason stay in the national rate. An
                institution not placed for an unusual year (<a href="#rate-lists" className="underline">Ordered lists</a>)
                has none of these reasons and stays in the national rate too.
                {w && (
                  <>
                    {' '}Institutions with each reason in {latestLabel}, in that order:{' '}
                    {listCodes.filter((c) => w[c]).map((c) =>
                      `${rateCodePhrase(c)} ${formatNumber(w[c].byWhy.online)}, ${formatNumber(w[c].byWhy.medical_campus)} and ${formatNumber(w[c].byWhy.shared)}`).join('; ')}
                    .
                  </>
                )}
              </Rule>
              <Rule id="rate-medical-campuses" title="Medical-center campuses">
                Some universities' Clery geography includes a medical-center campus whose hospital another
                organization runs, where many people are patients, visitors and hospital staff, not students. The
                campuses of a hand-reviewed list (etl/reference/medical_campuses.csv in the open-source pipeline, each
                with its evidence) are counted apart: for each rate, the on-campus incidents at those campuses outside
                their residence halls. When they are {share(rr?.medicalShare)} or more of the institution's on-campus
                count in the window, it is not on a list; its rate and comparisons are shown with the number. A
                smaller number is shown as a note. Campuses that were reviewed and not listed are in
                etl/reference/medical_campus_reviews.csv. On every build the audit screens DOE's campus names and
                addresses (words such as medical, hospital, health science or clinic) for campuses other than main
                campuses that hold at least {rr?.medicalScreen?.minCount ?? '…'} of an institution's on-campus
                criminal offenses (motor-vehicle theft and residence halls left out) and at least{' '}
                {share(rr?.medicalScreen?.share)} of them in a year with a single-year rate, and reports any such
                campus-year that is in neither file as a warning; it adds nothing to the list itself.{' '}
                {screenSentence(build)} Incidents at a medical center that is not on the list, or that DOE does not
                list as a campus of its own, are not counted apart.
              </Rule>
              <Rule id="rate-hospital-notes" title="Hospital notes">
                A second reviewed list (etl/reference/hospital_unresolved.csv in the open-source pipeline) holds the
                universities with a hospital next to or inside the main campus whose own reports, as read, do not
                establish whether the hospital's incidents are in their figures. Each keeps its rate and its
                places on the lists, and every page that shows one of its rates for those years says that this is not
                established and names the hospital; its school page gives what its reports do say, with the source.
                The annual security reports read for this list and for the reviewed exclusions above were those of
                universities near the top of the ordered lists, not every institution's.
              </Rule>
              <Rule id="rate-shared" title="Shared campuses">
                DOE's files give enrollment per institution, not per campus, so where campuses of two or more
                institutions report the same incidents, the incidents cannot be divided among those institutions'
                students. In each year, campuses of different institutions form a shared site when any of three
                tests joins them: identical figures (the copies described under{' '}
                <a href="#copies" className="underline">Figures reported by more than one campus</a>); a near-copy,
                two campuses in the same state (in different states only when every figure is equal) where the
                campus with the smaller on-campus total over all offenses has at least{' '}
                {rr?.sharedNear ? rr.sharedNear.minNonzero : '…'} nonzero figures, at least{' '}
                {rr?.sharedNear ? `${rr.sharedNear.match[0]} in ${rr.sharedNear.match[1]}` : '…'} of them equal to the
                other campus's, and a total of at least {rr?.sharedNear ? rr.sharedNear.minTotal : '…'}; or a
                reviewed list (etl/reference/shared_campus_overrides.csv in the open-source pipeline). Counts, totals
                and rankings by count do not change; only rates follow these rules. A main campus is the campus whose
                DOE ID ends in 001.
                <ul className="list-disc ml-5 mt-2 space-y-1">
                  <li>
                    <span className="text-gray-900 dark:text-gray-100">One main campus at the site.</span> The
                    institution whose main campus it is keeps the site's incidents, counted once, and is compared and
                    listed as usual; its school page names the other institutions. They are guests: their incidents
                    at the site are in none of their rates.
                  </li>
                  <li>
                    <span className="text-gray-900 dark:text-gray-100">Main campuses of several institutions.</span>{' '}
                    The one with the largest on-campus FTE is the owner. When the others count no campus away from
                    the site that year, or their on-campus FTE together is at most {siteShare} of the owner's, the
                    owner's rate counts the site once and adds their students, and they have no rate that year (
                    {num(iy?.rules.shared_pooled?.institutionYears)} institution-years,{' '}
                    {num(iy?.rules.shared_pooled?.withFte)} of them with a denominator of at least {num(rr?.minFte)}).
                    Otherwise none of them has a rate that year ({num(iy?.rules.shared_campus?.institutionYears)}{' '}
                    institution-years, {num(iy?.rules.shared_campus?.withFte)} with a denominator of at least{' '}
                    {num(rr?.minFte)}): the incidents cannot be given to one institution's students, and a rate for
                    any one of them would overstate it.
                  </li>
                  <li>
                    <span className="text-gray-900 dark:text-gray-100">No main campus.</span> Every institution's
                    incidents at the site are in none of its rates; each is a participant.
                  </li>
                </ul>
                <span className="block mt-2">
                  The school pages give, for each category, the incidents behind these notes. An owner's figure is
                  everything its campuses at the site reported on campus (all of it in its rate), not only the
                  figures a guest repeats; a guest's or participant's figure is what its campuses at the site
                  reported, its own figures or the owner's when it repeated them (none of it in its rates). So the
                  same incidents can be one institution's figure at the site and another's. A site is found anew each
                  year, and the window figures add the window's years.
                </span>
                <span className="block mt-2">
                  An institution whose every campus repeats one other institution's figures counts no campus of its
                  own, and that institution's denominator adds its on-campus FTE. In all,{' '}
                  {num(iy?.pooled.shared)} institution-years are rated with another institution's FTE added for a
                  shared site (this case and the owners above).
                </span>
                <span className="block mt-2">
                  A guest's or participant's on-campus FTE is NCES's figure for the whole institution, so it may
                  include its students at the site, and no file says how many they are. Its rate for a window with
                  such a year leaves out the site's incidents but may count those students, so the rate is shown
                  without comparisons ("{VERDICT_LABELS.withheld}") and is not on a list, in every category. The
                  exception is an institution with a figure for its students at each of those sites in each such
                  year, reviewed in etl/reference/shared_site_enrollment.csv: when those figures add up to at most{' '}
                  {siteShare} of its student-years in the window, it is compared and listed as usual. A figure is a
                  published count, a published upper bound (such as the enrollment of every location of a program
                  together), or an upper bound computed only from published figures by arithmetic the file states:
                  the sum of the published sizes of a program's classes enrolled that fall, or a published cap per
                  class times the number of classes at the site at one time. It is never an estimate or a lower
                  bound. A
                  site-year takes the figure for its own fall term (or the academic year that begins then); when it
                  has none, it takes the largest of the figures whose own year is at most{' '}
                  {rr?.sharedSiteFigureYears !== undefined ? formatNumber(rr.sharedSiteFigureYears) : '…'} years
                  before or after it (on a tie, the nearer, then the earlier), and the school page gives that
                  figure's own year. A figure counts the students of the programs its source covers, and a guest can
                  have other students at the site: the figures for the Texas A&amp;M pharmacy college count PharmD
                  students only, not its PhD students, and those for the Indiana University School of Medicine count
                  MD students only. {siteShare} is well within the difference of up to{' '}
                  {share(rr?.onlineUncertainRatio, true)} between the two estimates of on-campus students that the
                  rates accept (<a href="#rate-denominator" className="underline">On-campus students</a>). Guests
                  and participants stay in the national rate.
                  {w?.violent && (
                    <>
                      {' '}In {latestLabel}, {formatNumber(w.violent.verdicts.withheld ?? 0)} rated institutions have
                      their comparisons withheld for this reason
                      {exemptN > 0 && (
                        <>
                          , and {formatNumber(exemptN)} {exemptN === 1 ? 'is' : 'are'} compared as usual because of
                          such a figure
                        </>
                      )}
                      .
                    </>
                  )}
                  {bigWithheld > 0 && w?.violent && (
                    <>
                      {' '}Of the {formatNumber(w.violent.verdicts.withheld ?? 0)} withheld,{' '}
                      {formatNumber(bigWithheld)} {bigWithheld === 1 ? 'is' : 'are'} large enough for the
                      violent-crime list, so {bigWithheld === 1 ? 'a large institution has' : 'some large institutions have'}{' '}
                      no comparison on this site (
                      <a href="#limitations" className="underline">Limitations</a>).
                    </>
                  )}
                </span>
              </Rule>
              <Rule id="rate-flags" title="Unusual years">
                Every institution in DOE's data, of any size and in every year
                {rr?.skipYears?.length ? ` (${joinAnd(rr.skipYears.map(String))} included)` : ''}, is checked for years
                that stand out from its own other years, for{' '}
                {rr ? joinAnd(rr.flags.offenses.map(offenseName)) : '…'} at each location (
                {rr ? joinAnd(rr.flags.geos.map((g) => g.toLowerCase())) : '…'}). A year is flagged when its count is
                at least {rr?.flags.minCount ?? '…'}, the institution has figures for at least{' '}
                {rr?.flags.minOtherYears ?? '…'} other years (a year without an incident counts as 0), and a negative
                binomial count with the median of those years as its mean (at least {rr?.flags.minMean ?? '…'}) and
                variance μ + {rr?.flags.c ?? '…'}·μ<sup>1.5</sup> would reach that count with a probability below{' '}
                {rr?.flags.p ?? '…'}. A flag never changes a count or a rate. It says only that the year's count is
                far above the institution's other years; DOE counts each incident in the year it is reported, so the
                incidents may have happened earlier, and the figures do not say why the count is high (
                <a href="#year-reported" className="underline">How Institutions Count</a>). An on-campus flag of a
                list category's offenses in a window keeps the institution off that window's order (
                <a href="#rate-lists" className="underline">Ordered lists</a>). When on-campus flags of a
                rate's offenses fall in a window, the comparison with the national rate is also made with each flagged
                year counted at its median, and the school page shows that result when it differs. On the rate
                lists, a flag icon beside an institution's name gives its flagged years.
                {rs?.flags && (
                  <>
                    {' '}This build has {formatNumber(rs.flags.total)} flags (
                    {Object.entries(rs.flags.byGeo).map(([g, n]) => `${g.toLowerCase()} ${formatNumber(n)}`).join(', ')}).
                  </>
                )}
                {w?.violent && (
                  <>
                    {' '}In {latestLabel}, {formatNumber(w.violent.withFlags)} institutions' violent-crime rates contain
                    a flagged year, and for {formatNumber(w.violent.verdictWithoutFlaggedDiffers)} of them the comparison
                    would differ without the excess.
                  </>
                )}
              </Rule>
              <Rule id="rate-single-years" title="Single years">
                School pages also chart each year's rate with a one-year interval (the same model with T = 1, so
                wider), for the years in which the institution meets the rules above
                {rr?.skipYears?.length ? `; ${joinAnd(rr.skipYears.map(String))} has none` : ''}. Single years have no
                comparisons and no positions.
              </Rule>
              <Rule id="rate-codes" title="Categories without a rate">
                These are shown as counts only:{' '}
                {rr ? joinAnd(rr.countsOnly.map((c) => metadata?.offenses.find((o) => o.code === c)?.display ?? c)) : '…'}
                . Arrests and disciplinary referrals count people arrested or referred, a measure of enforcement
                activity, not of incidents, and "All categories" adds them to crimes. "All criminal offenses" is
                replaced by {rateCodePhrase('criminal_xmvt')}, and "Property crimes" (burglary, motor-vehicle theft and
                arson) by burglary. Motor-vehicle theft has no rate and is left out of the criminal-offense rate
                {mvtFirst && mvtLatest && first && latest ? (
                  <>
                    : on campus, at the institutions in the national rate, there were {formatNumber(mvtFirst.mvt)}{' '}
                    motor-vehicle thefts in {windowLabel(first)} ({pct1(mvtFirst.share)} of criminal offenses) and{' '}
                    {formatNumber(mvtLatest.mvt)} in {windowLabel(latest)} ({pct1(mvtLatest.share)}), so they would
                    decide much of the order of a criminal-offense rate
                  </>
                ) : null}
                {rs?.flags?.byOffense?.motor_vehicle_theft !== undefined && (
                  <>
                    ; {formatNumber(rs.flags.byOffense.motor_vehicle_theft)} of the {formatNumber(rs.flags.total)}{' '}
                    unusual-year flags are motor-vehicle thefts
                  </>
                )}
                .{' '}
                {rareCodes.length > 0 && (
                  <>
                    {joinAnd(rareCodes.map((c) => metadata?.offenses.find((o) => o.code === c)?.display ?? c))} are
                    rare, so rates of their own would rest on very few incidents; they are counted in the rate of{' '}
                    {rateCodePhrase('criminal_xmvt')}
                    {rr?.codes?.violent?.includes('murder') ? ', and murder also in violent crimes' : ''}.
                  </>
                )}{' '}
                Rankings by count open on violent crimes.
              </Rule>
              <Rule id="rate-abroad" title="Campuses abroad">
                A campus DOE lists without a state is abroad, and so are the foreign sites DOE lists with a U.S. state
                (etl/reference/campuses_abroad.csv). NCES's fall enrollment excludes "students enrolled in any branch
                campus located in a foreign country" (
                <SourceLink source={SOURCES.ncesFallEnrollment2024}>NCES, Fall Enrollment instructions, Who to Exclude</SourceLink>),
                so an institution's rates leave out the incidents at its campuses abroad; they stay on each such
                campus's own school page, and the institution's school pages say how many there were. Campuses in
                Puerto Rico, Guam and other U.S. territories are not abroad. Campuses abroad that DOE lists under a
                U.S. state appear in the lists of campuses by count, like any campus that reported. Their incidents
                are never in an institution's totals or rates.
                {latestYear && iy?.byYear[latestYear] && (
                  <>
                    {' '}In {latestYear}, {formatNumber(iy.byYear[latestYear].abroad)} institutions in the states covered
                    with a denominator of at least {num(rr?.minFte)} had a campus abroad.
                  </>
                )}
              </Rule>
              <Rule id="count-flag" title="Counts very high for an institution's size">
                Rankings by count rank campuses whatever their size. A count is flagged "very high for its
                institution's size" when it is at least {rr?.countFlag.minCount ?? '…'} and its number per 10,000 of
                the institution's FTE (NCES's FTE of the whole institution) is more than {rr?.countFlag.factor ?? '…'}{' '}
                times a reference: the {rr?.countFlag.percentile ?? '…'}th percentile of that year's institution rates
                of the category, counting every location, per 10,000 of the rate denominator, over the institutions in
                the states covered with a denominator of at least {num(rr?.minFte)}, no population rule and a certain
                on-campus FTE (zeros included). No count is flagged where the reference is 0. The count is shown as
                reported and keeps its place in the ranking; the flag says only that it is high for the
                institution's size, not why (DOE counts each incident in the year it is reported, so some may have
                happened earlier). In a ranking by count, a flag icon beside the campus's name gives the count per
                10,000 of the institution's FTE and the reference; the campus's school page, with that year and
                category selected, gives the note in full.
                {latestYear && rs?.countFlags?.[latestYear] && (
                  <>
                    {' '}In the {latestYear} national rankings by count, the flagged counts are{' '}
                    {joinAnd(['violent', 'criminal', 'property', 'all']
                      .filter((c) => rs.countFlags[latestYear][c] !== undefined)
                      .map((c) => `${formatNumber(rs.countFlags[latestYear][c])} for ${(metadata?.offenses.find((o) => o.code === c)?.display ?? c).toLowerCase()}`))}
                    .
                  </>
                )}
              </Rule>
            </ol>

            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-2">By window</h3>
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Rated institutions, national rate and list members by window</caption>
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Window</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Rated</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">National rate, violent crimes</th>
                    {listCodes.map((c) => (
                      <th key={c} scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">
                        On the list: {rateCodeLabel(c).toLowerCase()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {keys.slice().reverse().map((key) => {
                    const s = rs?.windows?.[key]
                    return (
                      <tr key={key}>
                        <th scope="row" className="px-3 py-2 text-left font-normal text-gray-700 dark:text-gray-300 whitespace-nowrap">{windowLabel(key)}</th>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{num(s?.violent?.rated)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{s?.violent ? fmtRate(s.violent.natl) : '…'}</td>
                        {listCodes.map((c) => (
                          <td key={c} className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{num(s?.[c]?.listed)}</td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {w && latest && (
              <>
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-2">
                  Comparisons in {latestLabel}, by category
                </h3>
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-x-auto">
                  <table className="w-full text-sm">
                    <caption className="sr-only">National rate and comparisons of rated institutions in {latestLabel}</caption>
                    <thead className="bg-gray-50 dark:bg-gray-800">
                      <tr>
                        <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Category</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">National rate</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Above</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Not distinguishable</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Below</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Not determined</th>
                        <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Not compared (shared campus)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                      {codesWithRate.filter((c) => w[c]).map((c) => (
                        <tr key={c}>
                          <th scope="row" className="px-3 py-2 text-left font-normal text-gray-700 dark:text-gray-300">{rateCodeLabel(c)}</th>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{fmtRate(w[c].natl)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(w[c].verdicts.above)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(w[c].verdicts.nd)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(w[c].verdicts.below)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(w[c].verdicts.undetermined)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(w[c].verdicts.withheld ?? 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  Rates per 10,000 on-campus students a year. Each category's columns add up to the{' '}
                  {num(w.violent?.rated)} rated institutions.{' '}
                  {nationalCompositionSentence('violent', facts.violent?.composition, latest, facts.violent?.compositionShare) ?? ''}
                </p>
              </>
            )}

            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-2">By year</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
              The population, merger and shared-campus rules give no rate to {num(ruleTotals?.all)} institution-years in all (
              {num(ruleTotals?.withFte)} in the states covered with a denominator of at least {num(rr?.minFte)}).
            </p>
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Institutions by year: denominator, population rules, single-year rates, uncertain on-campus FTE, campuses abroad</caption>
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Year</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Denominator {num(rr?.minFte)}+</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Population rule</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Single-year rate</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">Uncertain on-campus FTE</th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">With a campus abroad</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {yearRows.map(([y, s]) => (
                    <tr key={y}>
                      <th scope="row" className="px-3 py-2 text-left font-normal text-gray-700 dark:text-gray-300">{y}</th>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.withFte)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.excluded)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.rated)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.fteUncertain)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">{formatNumber(s.abroad)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              Denominator {num(rr?.minFte)}+: institutions in the states covered whose denominator that year is at
              least {num(rr?.minFte)}. Of those, Population rule: no rate under the population, merger or
              shared-campus rules; Single-year rate: the years charted on school pages
              {rr?.skipYears?.length ? ` (none in ${joinAnd(rr.skipYears.map(String))})` : ''}; Uncertain on-campus
              FTE: no population rule and an uncertain on-campus FTE, its own or added with another institution's;
              With a campus abroad: any rule.
            </p>

            <h3 id="calibration" className="scroll-mt-20 text-base font-semibold text-gray-900 dark:text-gray-100 mt-8 mb-2">
              How well the intervals fit
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
              On every build the audit (check Interval Calibration) predicts each year's on-campus count of every
              institution with a rate from its other years, with the intervals' variance (the model's, or the
              other years' own spread when that is larger), and counts how often the year falls inside the central{' '}
              {ci}% of the prediction. The expected share comes from data simulated under the model with the same
              rule, so it is not exactly {ci}%. The audit fails a category and period when the
              two differ, either way, by more than {rr?.calibration ? pctPoints(rr.calibration.tolerance) : '…'} over
              the institutions with at least {calBands[0] ?? '…'} incidents a year. In a group of institutions with
              similar counts it fails when the share inside is below the expected share by more than{' '}
              {rr?.calibration ? pctPoints(rr.calibration.bandToleranceBelow) : '…'}, or above it by more than{' '}
              {rr?.calibration ? pctPoints(rr.calibration.bandToleranceAbove) : '…'}, if the group has at least{' '}
              {rr?.calibration ? formatNumber(rr.calibration.bandMinUnits) : '…'} institutions.
              {rr?.calibration?.topBandCodes && rr.calibration.topBandCodes.length > 0 && rr.calibration.topBandSE !== undefined ? (
                <>
                  {' '}The group with the most incidents a year
                  {calColumns.length > 0 ? ` (${bandLabel(calColumns[calColumns.length - 1])})` : ''} of{' '}
                  {joinAnd(rr.calibration.topBandCodes.map(rateCodePhrase))} is tested whatever its size: with fewer than{' '}
                  {formatNumber(rr.calibration.bandMinUnits)} institutions, each limit is widened by{' '}
                  {formatNumber(rr.calibration.topBandSE)} binomial standard errors of the expected share, √(e(1 −
                  e)/k) for k institution-years. Other smaller groups are reported without a pass rule.
                </>
              ) : ' Smaller groups are reported without a pass rule.'}{' '}
              The two limits differ on purpose: intervals that hold fewer counts than
              the model says are too narrow, so comparisons and rank ranges claim more certainty than the data give;
              intervals that hold more are too wide, which only leaves more rates without a verdict.
            </p>
            {calibration.length > 0 && rr?.calibration && (
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                {calShort.length === 0 ? (
                  <>
                    In this build no group's share inside is below the expected share by more than{' '}
                    {pctPoints(rr.calibration.bandToleranceBelow)}.
                  </>
                ) : (
                  <>
                    In this build, the share inside is below the expected share by more than{' '}
                    {pctPoints(rr.calibration.bandToleranceBelow)} in {formatNumber(calShort.length)}{' '}
                    {calShort.length === 1 ? 'group' : 'groups'}, tested or not; there the intervals may be too
                    narrow:
                    <CalibrationList rows={calShort} />
                  </>
                )}
              </div>
            )}
            {calibration.length > 0 ? (
              <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">
                    Share of yearly counts inside the predicted range, and the share expected, by category, period and
                    group of institutions with similar counts
                  </caption>
                  <thead className="bg-gray-50 dark:bg-gray-800">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Category</th>
                      <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100">Years</th>
                      {calColumns.map((b) => (
                        <th key={b} scope="col" className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-gray-100">
                          {b.startsWith('all') ? 'All with ' : ''}{bandLabel(b)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {calKeys.map(({ code, period }) => (
                      <tr key={`${code}-${period}`}>
                        <th scope="row" className="px-3 py-2 text-left font-normal text-gray-700 dark:text-gray-300">{rateCodeLabel(code)}</th>
                        <td className="px-3 py-2 text-left text-gray-600 dark:text-gray-400 whitespace-nowrap">{periodLabel(period)}</td>
                        {calColumns.map((b) => {
                          const r = calibration.find((x) => x.code === code && x.period === period && x.band === b)
                          if (!r) {
                            return <td key={b} className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">–</td>
                          }
                          const status = r.observed === null || r.expected === null
                            ? null
                            : !r.tested ? 'too few to test' : r.ok === false ? 'fails' : null
                          const isShort = calShort.includes(r)
                          return (
                            <td key={b} className="px-3 py-2 text-right tabular-nums text-gray-600 dark:text-gray-400">
                              {r.observed === null || r.expected === null ? (
                                <span className="whitespace-nowrap">no institutions</span>
                              ) : (
                                <span className={cn('whitespace-nowrap', isShort && 'font-semibold text-gray-900 dark:text-gray-100')}>
                                  {pct1(r.observed)} ({pct1(r.expected)}){isShort ? ' †' : ''}
                                </span>
                              )}
                              {r.observed !== null && (
                                <span className="block text-xs whitespace-nowrap">
                                  {formatNumber(r.units)} {r.units === 1 ? 'institution' : 'institutions'}
                                  {status ? `, ${status}` : ''}
                                </span>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-600 dark:text-gray-400">The audit's figures are not loaded.</p>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              Each cell: the share of yearly counts inside the predicted range, the share expected in brackets, and the
              number of institutions. Columns: institutions by their average incidents a year. † Below the expected
              share by more than {rr?.calibration ? pctPoints(rr.calibration.bandToleranceBelow) : '…'} (a small
              group with the most incidents is tested against its widened limit, and "fails" says when it is
              outside it). Years: the
              first five years and the latest {rr?.calibration?.latestYears ?? '…'}.{' '}
              <a href="/audit.json" className="underline">audit.json</a> has every figure.
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
                figures the institutions reported, and the site does not change them; it flags years that stand out
                from an institution's other years (<a href="#rate-flags" className="underline">Unusual years</a>).
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
                pages and Compare open on; rankings by count open on violent crimes): the 11 criminal offenses above,
                added up. It has no rate; rates use criminal offenses except motor-vehicle theft (see{' '}
                <a href="#rate-codes" className="underline">Categories without a rate</a>).
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
              {limitations(facts).map((item) => (
                <div key={item.title} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                  <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-1">{item.title}</h3>
                  <div className="text-sm text-gray-600 dark:text-gray-400">{item.body}</div>
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
                year. The on-campus part of it that rates divide by is an estimate made from NCES's figures (
                <a href="#rate-denominator" className="underline">On-campus students</a>).
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
          <section id="audit" className="scroll-mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
                <FileText className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Data Quality Audit
              </h2>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Each build runs an audit over {schoolCount !== undefined ? `all ${formatNumber(schoolCount)} campus pages` : 'every campus page'}.
              Most of its checks test that the published files agree with each other and with the pipeline's tables;
              one re-reads NCES's enrollment figures, one recomputes every published rate figure with a separate
              implementation of the rules, one tests the interval model against the data, and one screens for
              medical-center campuses not yet reviewed. It does not show that institutions' figures are accurate;
              they are published as reported to the Department of Education.
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
              <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm mb-1">The checks and this build's results</h3>
              {checks.length > 0 ? (
                <>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    {formatNumber(checks.length)} checks: {formatNumber(statusCount('PASS'))} passed,{' '}
                    {formatNumber(statusCount('FAIL'))} failed, {formatNumber(statusCount('WARNING'))} with a warning.
                    A warning never fails the audit.
                  </p>
                  <ol className="space-y-3 text-sm list-decimal pl-5">
                    {checks.map((c) => (
                      <li key={c.name} className="text-gray-600 dark:text-gray-400">
                        <span className="font-medium text-gray-900 dark:text-gray-100">{c.name}</span>{' '}
                        <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-semibold ${STATUS_STYLES[c.status] ?? 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'}`}>
                          {c.status}
                        </span>
                        {CHECK_DESCRIPTIONS[c.name] && <>: {CHECK_DESCRIPTIONS[c.name]}.</>}
                        {[...c.errors, ...c.warnings].map((t, i) => (
                          <span key={i} className="block mt-1 text-gray-800 dark:text-gray-200">{t}</span>
                        ))}
                      </li>
                    ))}
                  </ol>
                </>
              ) : (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  The audit's results are in <a href="/audit.json" className="underline">audit.json</a>.
                </p>
              )}
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
                  <code>institution_rate_fte</code> (the institution's denominator that year: its on-campus FTE, the
                  larger of the two estimates of <a href="#rate-denominator" className="underline">On-campus students</a>,
                  with any FTE added under <a href="#rate-mergers" className="underline">Mergers</a> or{' '}
                  <a href="#rate-shared" className="underline">Shared campuses</a>),{' '}
                  <code>institution_rate_rule</code> (the rule that gives the institution no rate that year, and none
                  for a window containing it: <code>hospital</code>, <code>medical</code> or <code>listed</code> under
                  Population rules, <code>merger</code> or <code>family</code> under Mergers,{' '}
                  <code>shared_pooled</code> or <code>shared_campus</code> under Shared campuses; empty when none),{' '}
                  <code>institution_oncampus_fte_proportional</code> and{' '}
                  <code>institution_oncampus_fte_part_time_first</code> (the two estimates; the second is empty when
                  it cannot be computed), <code>institution_oncampus_fte_uncertain</code> (True when the on-campus FTE
                  is uncertain: its own estimates, or those of an institution whose FTE its denominator adds; empty
                  when the institution has no on-campus FTE),{' '}
                  <code>institution_oncampus_fte_uncertain_reason</code> (<code>own</code>, or <code>pooled</code>{' '}
                  when only an added institution's estimates are uncertain; empty otherwise) and{' '}
                  <code>medical_center_campus</code> (True when the campus is on the list of{' '}
                  <a href="#rate-medical-campuses" className="underline">Medical-center campuses</a> that year).
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
                <dt className="font-medium text-gray-900 dark:text-gray-100">Rate files</dt>
                <dd>
                  <code>/data/rates/</code>, listed in the build record.{' '}
                  {latest ? (
                    <a href={`/data/rates/${latest}-violent.json`} className="underline font-mono break-all">{`${latest}-violent.json`}</a>
                  ) : (
                    <code>{'{first year}-{last year}-violent.json'}</code>
                  )}{' '}
                  and the other files named by window and category: every rated institution, ordered by rate, with
                  its on-campus count (<code>n</code>), its counts at non-campus locations and on public property
                  (<code>nNoncampus</code>, <code>nPublic</code>), student-years (<code>fteYears</code>), rate and
                  interval (<code>rate</code>, <code>lo</code>, <code>hi</code>; to 4 decimals <code>lo4</code>,{' '}
                  <code>hi4</code>), the variance ratio and whether it is the model's or the institution's own spread
                  (<code>phi</code>, <code>phiFrom</code>), the count expected at the national rate (<code>E</code>),
                  the comparisons (<code>verdict</code>, <code>peerVerdict</code>), the reason it is not on a list
                  (<code>why</code>, or <code>notPlaced</code> for an unusual year), its unusual-year flags, a hospital
                  note (<code>hospitalUnresolved</code>) and, for the list categories, its national, state and type
                  positions and ranges{SHOW_POINT_POSITION ? '' : ' (the pages show only the ranges)'}; the file's header has the national rate and the rates by type, to 2 and 4
                  decimals.{' '}
                  <code>rates/institutions/</code> has one file per institution with its windows and single years,
                  and <code>rates/flags.json</code> every unusual-year flag.
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
                <div>etl/rates.py — Build the 3-year rates, comparisons, lists and flags (used by 05)</div>
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
