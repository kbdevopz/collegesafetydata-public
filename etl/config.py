"""
Configuration for Clery data transformation.
Includes field mappings from wide DOE format to tidy schema.

DOE Campus Safety Data: https://ope.ed.gov/campussafety/
Field definitions vary by year - this config handles 2015-2024 data format.
"""

from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CURATED_DIR = PROJECT_ROOT / "data" / "curated"
QA_DIR = PROJECT_ROOT / "data" / "qa"
JSON_DIR = PROJECT_ROOT / "frontend" / "public" / "data"

# =============================================================================
# IVY LEAGUE SCHOOLS (UNITID mapping)
# =============================================================================

IVY_LEAGUE = {
    217156001: {"name": "Brown University", "short": "Brown", "city": "Providence", "state": "RI"},
    166027001: {"name": "Harvard University", "short": "Harvard", "city": "Cambridge", "state": "MA"},
    190150001: {"name": "Columbia University in the City of New York", "short": "Columbia", "city": "New York", "state": "NY"},
    190415001: {"name": "Cornell University", "short": "Cornell", "city": "Ithaca", "state": "NY"},
    182670001: {"name": "Dartmouth College", "short": "Dartmouth", "city": "Hanover", "state": "NH"},
    186131001: {"name": "Princeton University", "short": "Princeton", "city": "Princeton", "state": "NJ"},
    215062001: {"name": "University of Pennsylvania", "short": "Penn", "city": "Philadelphia", "state": "PA"},
    130794001: {"name": "Yale University", "short": "Yale", "city": "New Haven", "state": "CT"},
}

IVY_UNITIDS = set(IVY_LEAGUE.keys())

# Base unitids (without branch suffix) for matching any branch
IVY_BASE_UNITIDS = {uid // 1000 for uid in IVY_LEAGUE.keys()}

# =============================================================================
# NATIONWIDE CONFIGURATION
# =============================================================================

# Feature flag: Set to True to process all schools, False for Ivy-only mode
PROCESS_ALL_SCHOOLS = True

# US States (code -> full name)
US_STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "PR": "Puerto Rico",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "VI": "Virgin Islands",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

# All valid state codes
VALID_STATE_CODES = set(US_STATES.keys())

# =============================================================================
# GEOGRAPHY CODES
# =============================================================================

# DOE uses numeric suffix codes for geography:
# 10 = Total (all locations combined - not used to avoid double counting)
# 11 = On-campus (including residential)
# 12 = On-campus residential subset (of 11)
# 13 = Non-campus
# 14 = Public property

GEO_CODES = {
    "11": "On-campus",
    "12": "Residence halls",
    "13": "Non-campus",
    "14": "Public property",
}

# For aggregated "All" geography (excludes residence halls to avoid double counting)
GEO_FOR_ALL = ["On-campus", "Non-campus", "Public property"]

# =============================================================================
# OFFENSE FIELD MAPPING
# =============================================================================

# DOE field naming convention: OFFENSE_CODE + GEO_CODE
# Example: MURD11 = Murder, On-campus; RAPE12 = Rape, Residence halls

# Base offense codes (without geography suffix)
OFFENSE_CODES = {
    # Criminal Offenses
    "MURD": {"offense": "Murder", "family": "Criminal"},
    "NEGMAN": {"offense": "Negligent Manslaughter", "family": "Criminal"},
    "NEG": {"offense": "Negligent Manslaughter", "family": "Criminal"},  # Alternate field name
    "RAPE": {"offense": "Rape", "family": "Criminal"},
    "FONDL": {"offense": "Fondling", "family": "Criminal"},
    "FOND": {"offense": "Fondling", "family": "Criminal"},  # Alternate field name
    "INCEST": {"offense": "Incest", "family": "Criminal"},
    "STATR": {"offense": "Statutory Rape", "family": "Criminal"},
    "STATUTORYRAPE": {"offense": "Statutory Rape", "family": "Criminal"},
    "ROBBE": {"offense": "Robbery", "family": "Criminal"},
    "ROBB": {"offense": "Robbery", "family": "Criminal"},  # Alternate field name
    "AGG": {"offense": "Aggravated Assault", "family": "Criminal"},
    "AGGASSLT": {"offense": "Aggravated Assault", "family": "Criminal"},
    "BURGLA": {"offense": "Burglary", "family": "Criminal"},
    "BURG": {"offense": "Burglary", "family": "Criminal"},  # Alternate field name
    "VEHIC": {"offense": "Motor Vehicle Theft", "family": "Criminal"},
    "MOTOR": {"offense": "Motor Vehicle Theft", "family": "Criminal"},
    "ARSON": {"offense": "Arson", "family": "Criminal"},

    # VAWA Offenses (Violence Against Women Act)
    "DOMEST": {"offense": "Domestic Violence", "family": "VAWA"},
    "DOME": {"offense": "Domestic Violence", "family": "VAWA"},  # Alternate field name
    "DATING": {"offense": "Dating Violence", "family": "VAWA"},
    "DAT": {"offense": "Dating Violence", "family": "VAWA"},  # Alternate field name
    "STALK": {"offense": "Stalking", "family": "VAWA"},

    # Arrests
    "WEAPON": {"offense": "Weapons Arrest", "family": "Arrest"},
    "WEAP": {"offense": "Weapons Arrest", "family": "Arrest"},  # Alternate
    "DRUG": {"offense": "Drug Arrest", "family": "Arrest"},
    "LIQ": {"offense": "Liquor Arrest", "family": "Arrest"},
    "LIQUOR": {"offense": "Liquor Arrest", "family": "Arrest"},

    # Disciplinary Actions
    "WEAPD": {"offense": "Weapons Discipline", "family": "Disciplinary"},
    "DRUGD": {"offense": "Drug Discipline", "family": "Disciplinary"},
    "LIQD": {"offense": "Liquor Discipline", "family": "Disciplinary"},
    "LIQUORD": {"offense": "Liquor Discipline", "family": "Disciplinary"},

    # Hate Crimes (flagged versions)
    "HATEFLAG": {"offense": "Hate Crime Flag", "family": "Hate Crime"},
}

# Build complete field mapping by combining offense codes with geo codes
OFFENSE_FIELDS = {}

for offense_code, offense_info in OFFENSE_CODES.items():
    for geo_code, geo_name in GEO_CODES.items():
        field_name = f"{offense_code}{geo_code}"
        OFFENSE_FIELDS[field_name] = {
            "offense": offense_info["offense"],
            "family": offense_info["family"],
            "geo": geo_name,
        }

# Add some specific field name variations that DOE uses
FIELD_NAME_ALIASES = {
    # Some years use different naming conventions
    "MURDER11": "MURD11",
    "MURDER12": "MURD12",
    "MURDER13": "MURD13",
    "MURDER14": "MURD14",
    "ROBBERY11": "ROBBE11",
    "ROBBERY12": "ROBBE12",
    "ROBBERY13": "ROBBE13",
    "ROBBERY14": "ROBBE14",
    "BURGLARY11": "BURGLA11",
    "BURGLARY12": "BURGLA12",
    "BURGLARY13": "BURGLA13",
    "BURGLARY14": "BURGLA14",
    "VEHICLE11": "VEHIC11",
    "VEHICLE12": "VEHIC12",
    "VEHICLE13": "VEHIC13",
    "VEHICLE14": "VEHIC14",
}

# =============================================================================
# OFFENSE DISPLAY ORDER (for consistent UI rendering)
# =============================================================================

OFFENSE_ORDER = [
    # Criminal Offenses - most serious first
    "Murder",
    "Negligent Manslaughter",
    "Rape",
    "Fondling",
    "Incest",
    "Statutory Rape",
    "Robbery",
    "Aggravated Assault",
    "Burglary",
    "Motor Vehicle Theft",
    "Arson",
    # VAWA Offenses
    "Domestic Violence",
    "Dating Violence",
    "Stalking",
    # Arrests
    "Weapons Arrest",
    "Drug Arrest",
    "Liquor Arrest",
    # Disciplinary Actions
    "Weapons Discipline",
    "Drug Discipline",
    "Liquor Discipline",
]

# Create order mapping for sorting
OFFENSE_ORDER_MAP = {offense: i for i, offense in enumerate(OFFENSE_ORDER)}

# Shared (copied) statistics, found by 04_create_aggregates.py and checked by
# 07_comprehensive_audit.py. A block is one campus's figures for one year and
# one geography of GEO_FOR_ALL: one cell per offense in OFFENSE_ORDER, a blank
# cell counting as 0. Blocks of the same year and geography are copies when
# all cells are equal, at least SHARED_MIN_NONZERO of them are not 0, and the
# campuses are in the same state. Fewer nonzero cells match by chance too
# often to call a copy.
SHARED_MIN_NONZERO = 6

# =============================================================================
# OFFENSE FAMILIES (for grouping in UI)
# =============================================================================

OFFENSE_FAMILIES = {
    "Criminal": {
        "display": "Criminal Offenses",
        "description": "Crimes reported under the Clery Act",
        "order": 1,
    },
    "VAWA": {
        "display": "VAWA Offenses",
        "description": "Violence Against Women Act categories",
        "order": 2,
    },
    "Arrest": {
        "display": "Arrests",
        "description": "Arrests for violations",
        "order": 3,
    },
    "Disciplinary": {
        "display": "Disciplinary Actions",
        "description": "Institutional disciplinary referrals",
        "order": 4,
    },
}

# =============================================================================
# OFFENSE DESCRIPTIONS (for tooltips/info)
# =============================================================================

OFFENSE_DESCRIPTIONS = {
    "Murder": "The willful (non-negligent) killing of one human being by another",
    "Negligent Manslaughter": "The killing of another person through gross negligence",
    "Rape": "Penetration, no matter how slight, of the vagina or anus with any body part or object, or oral penetration by a sex organ of another person, without the consent of the victim",
    "Fondling": "The touching of the private body parts of another person for the purpose of sexual gratification, without the consent of the victim",
    "Incest": "Sexual intercourse between persons who are related to each other within the degrees wherein marriage is prohibited by law",
    "Statutory Rape": "Sexual intercourse with a person who is under the statutory age of consent",
    "Robbery": "The taking or attempting to take anything of value from the care, custody, or control of a person or persons by force or threat of force",
    "Aggravated Assault": "An unlawful attack by one person upon another for the purpose of inflicting severe or aggravated bodily injury",
    "Burglary": "The unlawful entry of a structure to commit a felony or a theft",
    "Motor Vehicle Theft": "The theft or attempted theft of a motor vehicle",
    "Arson": "Any willful or malicious burning or attempt to burn a dwelling house, public building, motor vehicle, or personal property",
    "Domestic Violence": "A felony or misdemeanor crime of violence committed by a current or former spouse or intimate partner",
    "Dating Violence": "Violence committed by a person who is or has been in a social relationship of a romantic or intimate nature with the victim",
    "Stalking": "Engaging in a course of conduct directed at a specific person that would cause a reasonable person to fear for their safety",
    "Weapons Arrest": "Arrests for the violation of laws prohibiting the manufacture, sale, or possession of weapons",
    "Drug Arrest": "Arrests for violations of laws prohibiting the production, distribution, and/or use of controlled substances",
    "Liquor Arrest": "Arrests for the violation of state or local laws prohibiting the manufacture, sale, purchase, transportation, or possession of alcoholic beverages",
    "Weapons Discipline": "Persons referred for disciplinary action for weapons law violations",
    "Drug Discipline": "Persons referred for disciplinary action for drug law violations",
    "Liquor Discipline": "Persons referred for disciplinary action for liquor law violations",
}

# =============================================================================
# DATA YEARS
# =============================================================================

DATA_YEARS = list(range(2015, 2025))  # 2015-2024 (crime from DOE 2025 release; FTE from IPEDS provisional DRVEF2024)

# =============================================================================
# SUMMARY CODES AND RATES
# =============================================================================

# Summary codes of the rankings and school pages, each the sum of a group of
# offenses: a family name (all its offenses), a tuple of offenses, or None
# (every offense). "violent" is the FBI's violent crime (murder and
# nonnegligent manslaughter, rape, robbery, aggravated assault) and
# "property" the FBI's property crime without larceny-theft, which Clery does
# not collect (burglary, motor vehicle theft, arson): FBI, Crime in the United
# States, offense definitions. "violent" is the site's default view. "all"
# mixes kinds of counts (arrests and referrals count people, and a VAWA
# offense can also be counted as a criminal offense), so the site labels it
# as a mix of categories.
VIOLENT_OFFENSES = ("Murder", "Rape", "Robbery", "Aggravated Assault")
PROPERTY_OFFENSES = ("Burglary", "Motor Vehicle Theft", "Arson")
SUMMARY_FAMILIES = {"criminal": "Criminal", "violent": VIOLENT_OFFENSES, "property": PROPERTY_OFFENSES,
                    "all": None}


def summary_codes(offense: str, family: str) -> list[str]:
    """The summary codes (SUMMARY_FAMILIES) an offense of `family` counts in."""
    return [code for code, group in SUMMARY_FAMILIES.items()
            if group is None or group == family or (isinstance(group, tuple) and offense in group)]


# Rates are institution rates: the incidents of all of an institution's
# campuses in the United States (the base UNITID, the first six digits; IPEDS
# fall enrollment leaves out students at branch campuses abroad, so a campus
# DOE lists without a state, or one of etl/reference/campuses_abroad.csv, is
# not in the rate) per 10,000 of the
# institution's on-campus FTE, because NCES publishes FTE per institution,
# not per campus. Campus crime statistics cover the campus, so students
# enrolled exclusively in distance education are taken out of NCES's fall
# FTE. NCES gives their share of the fall headcount (PCTDEEXC), not of FTE,
# so 04 makes two estimates:
#   (a) proportional: FTE x (1 - PCTDEEXC / 100);
#   (b) part-time first: the on-campus headcount H x (1 - PCTDEEXC / 100) is
#       taken to hold all full-time students it can (FT_on = min(FT, on-campus
#       headcount)), the rest part-time, each part-time student counting
#       (FTE - FT) / PT, as in the institution's FTE: FT_on + PT_on x (FTE -
#       FT) / PT. By level (undergraduate and graduate, DRVEF's PCUDEEXC and
#       PCGDEEXC) when the share is the year's own and the DRVEF file has
#       them (2021 on), else from the totals.
# On-campus FTE is the larger of the two, rounded half up to a whole number
# (exclusively online students are mostly part-time, so (a) takes out too
# much FTE; from the totals, (b) is at least (a) whenever 0 <= (FTE - FT) / PT <= 1). When
# the larger is more than ONLINE_UNCERTAIN_RATIO times the smaller, or (b)
# cannot be calculated (headcounts that do not add up), the institution-year's
# on-campus FTE is uncertain: its rate is shown with a note, and compared
# with the national rate only when both estimates give the same verdict
# (rates, below). An institution without PCTDEEXC keeps its full FTE.
# An institution has a rate in a year only when its on-campus FTE (with any
# FTE 04 pools with it) is at least MIN_FTE_FOR_RATE.
MIN_FTE_FOR_RATE = 1000
ONLINE_UNCERTAIN_RATIO = (5, 4)  # larger / smaller above 5/4 (the estimates differ by more than 25%)

# The years whose online share is another year's PCTDEEXC: in fall 2020 and
# 2021 many institutions taught remotely for the pandemic, which does not
# take their students off campus for good, so those years use the
# institution's fall 2019 share. When NCES has no 2019 figure for it, the
# year's own share is used (the build reports how many).
ONLINE_SHARE_YEAR = {2020: 2019, 2021: 2019}

# -----------------------------------------------------------------------------
# Rates: 3-year windows, comparisons with the national rate, ordered lists
# -----------------------------------------------------------------------------
# A rate is published for a window of RATE_WINDOW_YEARS consecutive years
# that contains none of RATE_SKIP_YEARS (rate_windows below): in fall 2020
# NCES's FTE does not measure who was on campus, so 2020 has counts but no
# rate. The rate is the window's on-campus incidents (DOE's "On campus",
# which includes residence halls) of a code per 10,000 on-campus FTE-years
# (the sum over the window's years of the rate's denominator above). Counts
# at non-campus locations and on public property are published beside it,
# not in it. 05 builds the rates (etl/rates.py), 07 checks them.
#
# An institution is in a window when DOE lists it (a counting campus) in
# every year of the window, its denominator is at least MIN_FTE_FOR_RATE in
# every year, and its link campus is in US_STATES (the national scope;
# other territories have counts only). Of those, in this order:
#   excluded        a rule (hospital, medical, listed, merger, family) in any
#                   year: no rate
#   online          an uncertain on-campus FTE in any year: a rate, compared
#                   with the national rate only when the larger and the
#                   smaller estimates give the same verdict; never listed
#   medical_campus  incidents at listed medical-center campuses (on campus,
#                   residence halls taken out: patients, visitors and staff
#                   are not students) are MEDICAL_CAMPUS_SHARE or more of the
#                   window's count: a rate and a verdict, never listed
#   shared          (sharedIn + sharedOut) / (count + sharedOut) above
#                   SHARED_MAX_SHARE, on-campus window sums: as medical_campus
# and the rest are rated with no reason. The national rate of a window and
# code is the sum of the counts over the sum of the FTE-years of the rated
# institutions without a reason and those with medical_campus or shared.
RATE_WINDOW_YEARS = 3
RATE_SKIP_YEARS = (2020,)


def rate_windows(years) -> list[tuple[int, int]]:
    """The rate windows (first, last year) of `years`: RATE_WINDOW_YEARS consecutive years, none in RATE_SKIP_YEARS."""
    have = set(years)
    out = []
    for first in sorted(have):
        span = range(first, first + RATE_WINDOW_YEARS)
        if all(y in have and y not in RATE_SKIP_YEARS for y in span):
            out.append((first, first + RATE_WINDOW_YEARS - 1))
    return out


# The codes with a rate and the offenses each adds up. "criminal_xmvt" is the
# criminal offenses without motor vehicle theft: on-campus vehicle thefts
# rose from 3,534 in 2021 to 12,151 in 2024, concentrated at about 100
# institutions, so they are counts only. Every other code (arrests and
# disciplinary referrals, which measure enforcement; "all", "criminal",
# "property", motor vehicle theft, and the rare offenses) is counts only.
RATE_CODES = {
    "violent": VIOLENT_OFFENSES,
    "criminal_xmvt": ("Murder", "Negligent Manslaughter", "Rape", "Fondling", "Incest", "Statutory Rape",
                      "Robbery", "Aggravated Assault", "Burglary", "Arson"),
    "burglary": ("Burglary",),
    "rape": ("Rape",),
    "fondling": ("Fondling",),
    "robbery": ("Robbery",),
    "aggravated_assault": ("Aggravated Assault",),
    "stalking": ("Stalking",),
    "dating_violence": ("Dating Violence",),
    "domestic_violence": ("Domestic Violence",),
}

# Overdispersion: yearly counts vary more than Poisson counts. For a yearly
# mean m the variance is m + c g(m) m^1.5 (the NB-P variance function with
# exponent 1.5, Greene 2008, Economics Letters 99(3):585-590), g(m) = min(cap,
# max(1, m / start)): RATE_RAMP = (start, cap), so g rises from 1 at 10 a year
# to 2 at 20 a year, where counts vary more than the exponent alone allows.
# For a window total N over T years the variance-to-mean ratio is phi(N) = 1
# + c g(N/T) sqrt(N/T). 07 checks every build that the intervals cover as
# they should (RATE_CALIBRATION).
#
# Where each c comes from. Every value was fitted on the on-campus counts of
# 2015-2019, by one method: institutions with an on-campus FTE of 1,000 or
# more, no rate rule and no uncertain on-campus FTE, that reported all five
# years; each institution's yearly counts compared with its five-year total
# shared out in proportion to FTE times that year's rate over all of them
# (Pearson variance-to-mean ratio); institutions grouped into bands by mean yearly
# count (1-2, 2-5, 5-10, 10-20, 20-50, 50-100, 100+; bands of 15 or more
# institutions with a ratio above 1); c fitted to the bands by least squares
# on the log scale, weighted by institutions, with the exponent fixed at 1.5.
# RATE_DISPERSION holds each code fitted on its own counts this way: violent
# (0.354), criminal_xmvt (0.497), burglary (0.665), rape (0.295), aggravated
# assault (0.585). RATE_DISPERSION_OTHER (0.522) is the same fit pooled over
# the single crime offenses; it is used for the codes without a fit of their
# own: fondling, robbery, stalking, dating violence, domestic violence.
RATE_DISPERSION = {"violent": 0.354, "criminal_xmvt": 0.497, "burglary": 0.665,
                   "rape": 0.295, "aggravated_assault": 0.585}
RATE_DISPERSION_OTHER = 0.522
RATE_RAMP = (10, 2)


def dispersion_c(code: str) -> float:
    """The overdispersion constant c of a rate code (RATE_DISPERSION, else RATE_DISPERSION_OTHER)."""
    return RATE_DISPERSION.get(code, RATE_DISPERSION_OTHER)


# Interval: the gamma interval of the effective count m = N / phi(N), scaled
# by phi (Fay and Feuer 1997, Statistics in Medicine 16(7):791-801; Garwood's
# exact Poisson interval when phi = 1): lower phi G(alpha/2; m) (0 for N =
# 0), upper phi G(1 - alpha/2; m + 1), G the gamma quantile, alpha = 1 -
# RATE_CI_LEVEL; divided by the FTE-years. Verdict against the national rate
# (or the peer group's): "above" when the lower bound is above it, "below"
# when the upper bound is below it, otherwise not distinguishable. Single
# years (each school page's trend) use the same interval with T = 1.
RATE_CI_LEVEL = 0.95

# Peer groups for a second comparison: the institution's type by Carnegie
# Size & Setting (SIZE_SETTING_FIELDS, newest first: the newest IPEDS HD
# file that gives the institution a classified value), the peer rate
# computed like the national rate within the type.
SIZE_SETTING_FIELDS = ("C21SZSET", "C18SZSET", "C15SZSET")
PEER_TYPES = {
    "two_year": ("Two-year", (1, 2, 3, 4, 5)),
    "nonresidential": ("Four-year, primarily nonresidential", (6, 9, 12, 15)),
    "residential": ("Four-year, primarily residential", (7, 10, 13, 16)),
    "highly_residential": ("Four-year, highly residential", (8, 11, 14, 17)),
    "other": ("Other (exclusively graduate, or not classified)", ()),
}


def peer_type(size_setting) -> str:
    """The PEER_TYPES key of a Carnegie Size & Setting value (None or unlisted: "other")."""
    for key, (_label, values) in PEER_TYPES.items():
        if size_setting is not None and int(size_setting) in values:
            return key
    return "other"


# Ordered lists (LIST_CODES only): the rated institutions without a reason
# whose expected count at the national rate (national rate x FTE-years) is
# at least LIST_MIN_EXPECTED. That depends on size only, never on the count;
# 20 is the CDC WONDER / NCHS reliability floor (rates on fewer than 20
# events are flagged unreliable, https://wonder.cdc.gov/wonder/help/ucd.html).
# Order: rate, highest first (exact), then name, then base UNITID; position
# = 1 + the number of members with a higher rate. Each member's range: the
# positions not ruled out by pairwise z-tests at Bonferroni level
# LIST_ALPHA / (2 (n - 1)), widened to hold its position (a marginal 95%
# confidence set for its rank; Mogstad, Romano, Shaikh and Wilhelm 2024,
# Review of Economic Studies 91(1):476-518). A state list is the national
# list's members in one state, with positions and ranges recomputed among
# them; published for every state with at least STATE_LIST_MIN_MEMBERS
# members. STATE_LIST_DISPLAY_MIN is the smallest state list the design
# recommends showing (published for the pages; the data has every list).
LIST_CODES = ("violent", "criminal_xmvt", "burglary")
LIST_MIN_EXPECTED = 20
LIST_ALPHA = 0.05
STATE_LIST_MIN_MEMBERS = 2
STATE_LIST_DISPLAY_MIN = 5

# Incidents at campuses that are medical centers or hospitals inside a
# university (etl/reference/medical_campuses.csv, reviewed per campus), on
# campus but not in residence halls: at MEDICAL_CAMPUS_SHARE or more of a
# window's count the institution is not listed for that code (its rate is
# shown with a note). etl/reference/medical_campus_reviews.csv lists the
# campuses reviewed and not listed; 07 re-runs the name and address screen
# (MEDICAL_SCREEN_*) and reports any campus it finds that is in neither file.
MEDICAL_CAMPUS_SHARE = (1, 4)
MEDICAL_SCREEN_PATTERN = (r"MEDIC|HOSPITAL|HEALTH SCI|HEALTH CENT|MED CENT|MED\.? CTR|CLINIC|SCHOOL OF MED|"
                          r"COLLEGE OF MED|HEALTH CAMPUS|MEDICAL CAMPUS|MED SCHOOL|HEALTH SYSTEM|RBHS|ANSCHUTZ")
MEDICAL_SCREEN_SHARE = (1, 10)
MEDICAL_SCREEN_MIN_COUNT = 5

# Figures DOE published identically for campuses of two institutions (a
# shared campus) count once, under the host, while the students are in each
# institution's own FTE: above SHARED_MAX_SHARE of the window's count (with
# the shared figures added for the institution whose copy is the shadow) the
# rate is shown with a note and not listed. A campus whose figures are another
# institution's campus figures without being identical copies is listed in
# etl/reference/shared_campus_overrides.csv (reviewed one by one): its
# figures stay in its institution's counts, are in none of its rates, and
# count as shared figures (the institution's shared out, the host's shared
# in) in the same test.
SHARED_MAX_SHARE = (1, 20)

# Unusual years. A cell is an institution's count of one offense
# (FLAG_OFFENSES) at one geography (FLAG_GEOS); a cell-year is flagged when
# the count is at least FLAG_MIN_COUNT, the institution is listed in at
# least FLAG_MIN_OTHER_YEARS other years (0 for a year without an incident),
# and P(Y >= count) < FLAG_P for a negative binomial Y with mean mu = max(
# FLAG_MIN_MEAN, the median of the other years) and variance mu + FLAG_C
# mu^1.5. DOE counts incidents in the year they are reported, so one
# investigation can add many to a year. Counts and rates stay as reported;
# a flag on campus in a window's year notes the comparison when taking the
# excess (count - median) out would change it.
FLAG_OFFENSES = ("Aggravated Assault", "Burglary", "Dating Violence", "Domestic Violence", "Fondling",
                 "Motor Vehicle Theft", "Rape", "Robbery", "Stalking")
FLAG_GEOS = ("On-campus", "Non-campus", "Public property")
FLAG_MIN_COUNT = 10
FLAG_MIN_OTHER_YEARS = 3
FLAG_P = 0.001
FLAG_C = 0.52
FLAG_MIN_MEAN = 0.5

# A count in rankings by count is flagged as very high for the institution's
# size when it is at least COUNT_FLAG_MIN_COUNT and the count per 10,000 of
# the institution's (full) FTE is more than COUNT_FLAG_FACTOR times the
# COUNT_FLAG_PERCENTILE-th percentile (linear interpolation, as numpy's
# default) of that year's institution rates of the code: all geographies,
# per 10,000 of the rate's denominator, of the institutions in the national
# scope with a denominator of at least MIN_FTE_FOR_RATE, no rule and a
# certain on-campus FTE, 0 included. No flag where that percentile is 0.
# The count is shown as reported.
COUNT_FLAG_MIN_COUNT = 20
COUNT_FLAG_FACTOR = 3
COUNT_FLAG_PERCENTILE = 99

# 07's calibration check of the intervals: for each code of
# RATE_CALIBRATION["codes"] and each period (the first five years and the
# latest three), every institution with a rate in all the period's years
# and incidents in at least one, each year's count predicted from its other
# years (year effects from the national totals) with the variance above;
# the share of counts inside the central 95% predictive interval against
# the share expected under the model (the mean of "simulations" simulated
# panels, NumPy PCG64 seeded with "seed", the same panels on every run). The
# check fails when they differ, either way, by more than "tolerance" over the
# institutions with a mean of at least 2 a year. In a band of yearly means
# ("bands") with at least "bandMinUnits" institutions it fails when the
# observed share is below the expected one by more than "bandToleranceBelow"
# or above it by more than "bandToleranceAbove". The two band limits differ
# on purpose: intervals that cover less often than the model says are too
# narrow, so verdicts and rank ranges claim more certainty than the data
# give, and that is the error to hold tightly; intervals that cover more
# often are too wide, which only leaves more rates without a verdict, so a
# larger difference is tolerated before the check fails. The dispersion
# constants are not refitted to pass this check.
RATE_CALIBRATION = {"codes": ("violent", "criminal_xmvt", "burglary", "rape", "aggravated_assault", "robbery",
                              "fondling", "stalking"),
                    "periods": ((2015, 2019), "latest"), "latestYears": 3, "simulations": 600, "seed": 11,
                    "bands": (2, 5, 10, 20), "tolerance": 0.02, "bandToleranceBelow": 0.03,
                    "bandToleranceAbove": 0.05, "bandMinUnits": 100}

# Institutions whose campus population students do not measure: no rate in a
# year when IPEDS HD says they have a hospital (HOSPITAL = 1: patients,
# visitors and hospital staff are on campus and not in FTE), or the Carnegie
# basic classification is a special-focus medical school or center
# (C15BASIC and C18BASIC 25, "Special Focus Four-Year: Medical Schools &
# Centers"; C21BASIC 25, the same, and 27, the "Special Focus Research
# Institution" category new in 2021, special-focus institutions that meet
# the research-university criteria: 20 of its 22 institutions in HD2024 were
# 25 in C18BASIC, 2021 Basic Classification,
# https://carnegieclassifications.acenet.edu/2021-basic-classification), or
# they are listed in etl/reference/rate_population_exclusions.csv with a
# sourced reason.
HOSPITAL_CODE = 1
MEDICAL_CARNEGIE = {"C15BASIC": (25,), "C18BASIC": (25,), "C21BASIC": (25, 27)}
MEDICAL_CARNEGIE_LABELS = {("C15BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C18BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C21BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C21BASIC", 27): "Special Focus Research Institution"}

# =============================================================================
# DOE DATA SOURCE URLS
# =============================================================================

# DOE_BASE_URL, DOE_DOWNLOAD_PAGE and get_data_url() are in
# 01_download_raw_data.py: this file is part of every build stage's code
# fingerprint (provenance.STAGE_CODE), so a URL kept here would make the whole
# build out of date whenever it changed.

# =============================================================================
# FIELD NAME RESOLUTION
# =============================================================================

def normalize_field_name(field: str) -> str:
    """Normalize a field name to a standard format."""
    field = field.upper().strip()
    # Apply aliases
    return FIELD_NAME_ALIASES.get(field, field)

def get_offense_info(field: str) -> dict | None:
    """Get offense information for a field name, returns None if not recognized."""
    normalized = normalize_field_name(field)
    return OFFENSE_FIELDS.get(normalized)

# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def is_ivy_league(unitid: int) -> bool:
    """Check if a UNITID belongs to an Ivy League school."""
    return unitid in IVY_UNITIDS

def get_offense_order(offense: str) -> int:
    """Get the display order for an offense (lower = earlier)."""
    return OFFENSE_ORDER_MAP.get(offense, 999)

def get_offense_description(offense: str) -> str:
    """Get the description for an offense."""
    return OFFENSE_DESCRIPTIONS.get(offense, "")

# =============================================================================
# STATE HELPERS
# =============================================================================

def get_state_name(state_code: str) -> str:
    """Get the full state name from a state code."""
    return US_STATES.get(state_code.upper(), state_code)

def is_valid_state(state_code: str) -> bool:
    """Check if a state code is valid."""
    return state_code.upper() in VALID_STATE_CODES

def get_preset_id(state_code: str) -> str:
    """Get the preset ID for a state (lowercase state code)."""
    return state_code.upper()

def get_all_preset_ids() -> list[str]:
    """Get all preset IDs (ivy + all states)."""
    presets = ["ivy"]
    if PROCESS_ALL_SCHOOLS:
        presets.extend(sorted(US_STATES.keys()))
    return presets
