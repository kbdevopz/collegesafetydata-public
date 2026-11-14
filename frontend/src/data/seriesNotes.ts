/**
 * Changes in definitions, reporting or circumstances that affect comparing
 * years, 2015-2024. Each note names the years it applies to and its
 * sources; the site shows `short` wherever one of those years is on screen
 * (trend charts, a selected year, rankings for that year) and `detail` on
 * the Methodology page (#series-breaks).
 *
 * Only changes that can be sourced belong here. Add a note by appending an
 * entry; nothing else needs to change.
 */
import { SOURCES, type Source } from './sources'

export interface SeriesNote {
  id: string
  // Calendar years of Clery statistics it applies to
  years: number[]
  // Label for the year range, e.g. "2020-2021"
  label: string
  title: string
  // One sentence for annotations
  short: string
  // Paragraph for the Methodology page
  detail: string
  sources: Source[]
}

export const SERIES_NOTES: SeriesNote[] = [
  {
    id: 'pandemic-2020-2021',
    years: [2020, 2021],
    label: '2020-2021',
    title: 'COVID-19 pandemic: fewer people on campus',
    short:
      'Many campuses closed or taught remotely during the COVID-19 pandemic, so fewer people were on campus; compare these years with others with care.',
    detail:
      'During the pandemic many institutions closed their campuses or taught remotely. NCES reports that the share of undergraduates taking only distance education courses was 15% in fall 2019, 44% in fall 2020 and 28% in fall 2021. Fewer students, staff and visitors on campus means fewer chances for on-campus incidents to happen and be reported, so lower 2020 and 2021 counts do not by themselves show that campuses became safer. ED changed only deadlines for that cycle (the Annual Security Report could be distributed as late as December 31, 2020, and the statistics survey ran from November 18, 2020 to January 14, 2021), not what is counted or how. Rate rankings judge the "mostly online" rule for 2020 and 2021 by each institution\'s fall 2019 share (see Who Rate Rankings Leave Out).',
    sources: [SOURCES.ncesDistance, SOURCES.covidFlexibilities2020],
  },
]

// Context that does not mark particular years on charts but matters for
// any comparison over time; shown on the Methodology page only
export const SERIES_CONTEXT: { id: string; title: string; detail: string; sources: Source[] }[] = [
  {
    id: 'year-reported',
    title: 'Counts are by the year a crime was reported',
    detail:
      'A year\'s figure counts crimes reported that year, including crimes that happened earlier. A jump in one year can be many reports of past incidents at one institution (see How Institutions Count), not a change in how often crimes happen.',
    sources: [SOURCES.handbook2016],
  },
  {
    id: 'vawa-2015',
    title: 'VAWA final rule, effective July 1, 2015',
    detail:
      'ED\'s final rule implementing the Violence Against Women Reauthorization Act of 2013 added dating violence, domestic violence and stalking, and replaced the old forcible and nonforcible sex offense categories with rape, fondling, incest and statutory rape, using the FBI\'s updated definition of rape. It took effect on July 1, 2015, and ED did not require institutions to revise their 2013 or 2014 statistics to it. This site starts with 2015, so it shows no year under the old categories; do not join its series with figures from before 2015.',
    sources: [SOURCES.vawaRule2014],
  },
  {
    id: 'guidance-2020',
    title: 'ED guidance replaced in October 2020',
    detail:
      'ED rescinded the 2016 Handbook on October 9, 2020 and replaced it with the Clery Act Appendix for the FSA Handbook, "effective for the reporting year following publication". ED said no statutory or regulatory requirement had changed, and the crime definitions in the regulation did not change. The Appendix says ED does not apply a measurable distance to a campus\'s "reasonably contiguous geographic area" and will accept an institution\'s reasonable interpretation of terms it defines clearly. We found no ED statement or data showing that this changed reported figures; it is one more reason institutions may draw their Clery geography differently.',
    sources: [SOURCES.rescission2020, SOURCES.cleryAppendix2020],
  },
  {
    id: 'nibrs-2021',
    title: 'FBI moved to NIBRS only in January 2021',
    detail:
      'The FBI retired its Summary Reporting System (SRS) in January 2021, which ED\'s 2020 Appendix notes. The Clery regulation still defines murder, rape, robbery, aggravated assault, burglary, motor vehicle theft, arson and the three law violations by the SRS manual (34 CFR 668.46(c)(9) and Appendix A), so the definitions used for this data did not change.',
    sources: [SOURCES.cleryAppendix2020, SOURCES.reg66846],
  },
]

export function notesForYears(years: Iterable<number>): SeriesNote[] {
  const set = new Set(years)
  return SERIES_NOTES.filter((n) => n.years.some((y) => set.has(y)))
}
