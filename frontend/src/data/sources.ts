/**
 * Official sources the site cites, and the Clery Act definitions of every
 * category and location it shows, in plain words.
 *
 * Definitions follow 34 CFR 668.46 and Appendix A to Subpart D of Part 668
 * (the regulation's own crime definitions). Keep wording close to the
 * regulation: shortened, never changed in meaning.
 */

export interface Source {
  label: string
  url: string
  // Who publishes it, for citations
  publisher: string
}

export const SOURCES = {
  cssData: {
    label: 'Campus Safety and Security (data and downloads)',
    url: 'https://ope.ed.gov/campussafety/',
    publisher: 'U.S. Department of Education, Office of Postsecondary Education',
  },
  edCampusSecurity: {
    label: 'Campus Security (guidance, Appendix and the 2016 Handbook)',
    url: 'https://www.ed.gov/teaching-and-administration/safe-learning-environments/school-safety-and-security/campus-security',
    publisher: 'U.S. Department of Education',
  },
  reg66846: {
    label: '34 CFR 668.46, Institutional security policies and crime statistics',
    url: 'https://www.ecfr.gov/current/title-34/subtitle-B/chapter-VI/part-668/subpart-D/section-668.46',
    publisher: 'Electronic Code of Federal Regulations',
  },
  regAppendixA: {
    label: 'Appendix A to Subpart D of Part 668, Crime Definitions in Accordance With the FBI\'s UCR Program',
    url: 'https://www.ecfr.gov/current/title-34/subtitle-B/chapter-VI/part-668/appendix-Appendix%20A%20to%20Subpart%20D%20of%20Part%20668',
    publisher: 'Electronic Code of Federal Regulations',
  },
  handbook2016: {
    label: 'The Handbook for Campus Safety and Security Reporting, 2016 Edition (rescinded 2020, kept for historical purposes)',
    url: 'https://www.ed.gov/sites/ed/files/admins/lead/safety/handbookfsa.pdf',
    publisher: 'U.S. Department of Education, Office of Postsecondary Education',
  },
  cleryAppendix2020: {
    label: 'Clery Act Appendix for FSA Handbook (October 2020), which replaced the 2016 Handbook',
    url: 'https://www.ed.gov/sites/ed/files/admins/lead/safety/cleryappendixfinal.pdf',
    publisher: 'U.S. Department of Education',
  },
  rescission2020: {
    label: 'Rescission of and Replacement for the 2016 Handbook for Campus Safety and Security Reporting (Electronic Announcement, October 9, 2020; updated January 19, 2021)',
    url: 'https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2020-10-09/rescission-and-replacement-2016-handbook-campus-safety-and-security-reporting-updated-jan-19-2021',
    publisher: 'U.S. Department of Education, Federal Student Aid',
  },
  vawaRule2014: {
    label: 'Violence Against Women Act final rule, 79 FR 62752 (October 20, 2014), effective July 1, 2015',
    url: 'https://www.govinfo.gov/content/pkg/FR-2014-10-20/pdf/2014-24284.pdf',
    publisher: 'Federal Register',
  },
  covidFlexibilities2020: {
    label: 'Additional regulatory flexibilities related to Coronavirus (COVID-19) (Electronic Announcement, July 10, 2020)',
    url: 'https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2020-07-10/additional-regulatory-flexibilities-related-coronavirus-covid-19',
    publisher: 'U.S. Department of Education, Federal Student Aid',
  },
  ipeds: {
    label: 'Integrated Postsecondary Education Data System (IPEDS)',
    url: 'https://nces.ed.gov/ipeds/',
    publisher: 'National Center for Education Statistics',
  },
  drvefDictionary: {
    label: 'IPEDS DRVEF (Derived Fall Enrollment) data dictionary, 2023 (FTE and PCTDEEXC)',
    url: 'https://nces.ed.gov/ipeds/datacenter/data/DRVEF2023_Dict.zip',
    publisher: 'National Center for Education Statistics',
  },
  ipedsGlossary: {
    label: 'IPEDS Glossary',
    url: 'https://surveys.nces.ed.gov/ipeds/public/glossary',
    publisher: 'National Center for Education Statistics',
  },
  ncesDistance: {
    label: 'Fast Facts: Distance learning',
    url: 'https://nces.ed.gov/fastfacts/display.asp?id=80',
    publisher: 'National Center for Education Statistics',
  },
  bjsCollege2014: {
    label: 'Rape and Sexual Assault Victimization Among College-Age Females, 1995-2013 (NCJ 248471, December 2014)',
    url: 'https://bjs.ojp.gov/content/pub/pdf/rsavcaf9513.pdf',
    publisher: 'Bureau of Justice Statistics',
  },
} satisfies Record<string, Source>

export interface Definition {
  name: string
  // Name the DOE data uses when it differs
  doeName?: string
  text: string
}

// Criminal offenses (34 CFR 668.46(c)(1)(i)); definitions from Appendix A
export const CRIMINAL_DEFINITIONS: Definition[] = [
  { name: 'Murder', doeName: 'Murder and nonnegligent manslaughter', text: 'The willful (nonnegligent) killing of one human being by another.' },
  { name: 'Negligent manslaughter', doeName: 'Manslaughter by negligence', text: 'The killing of another person through gross negligence.' },
  { name: 'Rape', text: 'Penetration, no matter how slight, of the vagina or anus with any body part or object, or oral penetration by a sex organ of another person, without the consent of the victim.' },
  { name: 'Fondling', text: 'Touching the private body parts of another person for the purpose of sexual gratification, without the consent of the victim, including when the victim cannot consent because of age or mental incapacity.' },
  { name: 'Incest', text: 'Sexual intercourse between persons related to each other within the degrees wherein marriage is prohibited by law.' },
  { name: 'Statutory rape', text: 'Sexual intercourse with a person who is under the statutory age of consent.' },
  { name: 'Robbery', text: 'Taking or attempting to take anything of value from the care, custody or control of a person by force or threat of force or violence, or by putting the victim in fear.' },
  { name: 'Aggravated assault', text: 'An unlawful attack by one person upon another to inflict severe or aggravated bodily injury, usually with a weapon or by means likely to produce death or great bodily harm.' },
  { name: 'Burglary', text: 'The unlawful entry of a structure to commit a felony or a theft, including attempts.' },
  { name: 'Motor vehicle theft', text: 'The theft or attempted theft of a motor vehicle, including joyriding (vehicles taken by people without lawful access, even if later abandoned).' },
  { name: 'Arson', text: 'Any willful or malicious burning or attempt to burn a dwelling house, public building, motor vehicle or aircraft, personal property of another, and so on.' },
]

// VAWA offenses (34 CFR 668.46(a))
export const VAWA_DEFINITIONS: Definition[] = [
  { name: 'Domestic violence', text: 'A felony or misdemeanor crime of violence committed by a current or former spouse or intimate partner of the victim, a person who shares a child with the victim, a person who lives or has lived with the victim as a spouse or intimate partner, or others the regulation lists under the domestic or family violence laws of the jurisdiction.' },
  { name: 'Dating violence', text: 'Violence committed by a person who is or has been in a social relationship of a romantic or intimate nature with the victim.' },
  { name: 'Stalking', text: 'A course of conduct (two or more acts) directed at a specific person that would cause a reasonable person to fear for their safety or the safety of others, or to suffer substantial emotional distress.' },
]

// Arrests and disciplinary referrals (34 CFR 668.46(c)(1)(ii)); law
// definitions from Appendix A
export const LAW_VIOLATION_DEFINITIONS: Definition[] = [
  { name: 'Weapons law violations', doeName: 'Illegal weapons possession', text: 'Violations of laws or ordinances prohibiting the manufacture, sale, purchase, transportation, possession, concealment or use of firearms, cutting instruments, explosives, incendiary devices or other deadly weapons.' },
  { name: 'Drug law violations', doeName: 'Drug abuse violations', text: 'Violations of laws prohibiting the production, distribution and/or use of certain controlled substances and the equipment or devices used to prepare or use them.' },
  { name: 'Liquor law violations', text: 'Violations of state or local laws or ordinances prohibiting the manufacture, sale, purchase, transportation, possession or use of alcoholic beverages, not including driving under the influence and drunkenness.' },
]

// Clery geography (34 CFR 668.46(a) and (c)(5))
export const GEOGRAPHY_DEFINITIONS: Definition[] = [
  { name: 'On-campus', text: 'Any building or property the institution owns or controls within the same reasonably contiguous geographic area and uses for its educational purposes, including residence halls; and property within or next to that area that the institution owns, another party controls, is frequently used by students and supports institutional purposes (such as a food or retail vendor).' },
  { name: 'Residence halls', doeName: 'On-campus student housing facilities', text: 'Of the on-campus crimes, those that took place in dormitories or other residential facilities for students on campus. A subset of on-campus, not a separate location.' },
  { name: 'Non-campus', doeName: 'Noncampus building or property', text: 'Any building or property owned or controlled by an officially recognized student organization, or owned or controlled by the institution, used for its educational purposes, frequently used by students, and not within the same reasonably contiguous geographic area as the campus.' },
  { name: 'Public property', text: 'All public property, including thoroughfares, streets, sidewalks and parking facilities, that is within the campus, or immediately adjacent to and accessible from the campus.' },
]
