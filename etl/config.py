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
# campuses (the base UNITID, the first six digits) per 10,000 of the
# institution's on-campus FTE, because NCES publishes FTE per institution,
# not per campus. On-campus FTE = FTE x (1 - PCTDEEXC / 100), rounded half
# up to a whole number: NCES's share of students enrolled exclusively in
# distance education (a fall headcount share, applied to the 12-month FTE,
# so it is an approximation) is taken out, because campus crime statistics
# cover the campus. An institution without PCTDEEXC keeps its full FTE.
# Rate rankings list an institution only when that year its on-campus FTE
# (with any FTE 04 pools with it) is at least MIN_FTE_FOR_RATE.
MIN_FTE_FOR_RATE = 1000

# The years whose online share is another year's PCTDEEXC: in fall 2020 and
# 2021 many institutions taught remotely for the pandemic, which does not
# take their students off campus for good, so those years use the
# institution's fall 2019 share. When NCES has no 2019 figure for it, the
# year's own share is used (the build reports how many).
ONLINE_SHARE_YEAR = {2020: 2019, 2021: 2019}

# Rate rankings rank by rate only an institution with at least
# MIN_COUNT_FOR_RATE_RANK incidents of the code: a count n has a Poisson
# relative standard error of 1/sqrt(n), 22.4% at 20, and CDC WONDER flags
# death rates on fewer than 20 deaths as unreliable (relative standard error
# 23% or more; https://wonder.cdc.gov/wonder/help/ucd.html). Below it the institution is listed
# as too few incidents to rank by rate, with its rate.
MIN_COUNT_FOR_RATE_RANK = 20

# Offenses too rare nationally for a rate ranking (counts only): on average
# fewer than RATE_RANK_MIN_NATIONAL incidents a year over DATA_YEARS (all
# institutions). 07 checks that this list is exactly those offenses.
RATE_RANK_MIN_NATIONAL = 1000
RATE_COUNTS_ONLY = ("Murder", "Negligent Manslaughter", "Incest", "Statutory Rape", "Arson")

# Each rate's 95% interval: the exact Poisson (Garwood) interval of the count,
# divided by the denominator.
RATE_CI_LEVEL = 0.95

# Institutions whose campus population students do not measure: left out of
# rate rankings (counts only) in a year when IPEDS HD says they have a
# hospital (HOSPITAL = 1: patients, visitors and hospital staff are on
# campus and not in FTE), or the Carnegie basic classification is a
# special-focus medical school or center (C15BASIC and C18BASIC 25, "Special
# Focus Four-Year: Medical Schools & Centers"; C21BASIC 25, the same, and 27,
# the "Special Focus Research Institution" category new in 2021, special-focus
# institutions that meet the research-university criteria: 20 of its 22
# institutions in HD2024 were 25 in C18BASIC, 2021 Basic Classification,
# https://carnegieclassifications.acenet.edu/2021-basic-classification), or
# they are listed in etl/reference/rate_population_exclusions.csv with a
# sourced reason.
HOSPITAL_CODE = 1
MEDICAL_CARNEGIE = {"C15BASIC": (25,), "C18BASIC": (25,), "C21BASIC": (25, 27)}
MEDICAL_CARNEGIE_LABELS = {("C15BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C18BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C21BASIC", 25): "Special Focus Four-Year: Medical Schools & Centers",
                           ("C21BASIC", 27): "Special Focus Research Institution"}

# An institution-year is flagged as unusually high for a code when its count
# is at least SPIKE_MIN_COUNT and more than SPIKE_FACTOR times the median of
# its counts of that code in its other listed years (0 for a year without
# one), with at least SPIKE_MIN_OTHER_YEARS other listed years. It stays
# ranked: DOE counts crimes in the year they are reported, so one report of
# many past incidents raises one year.
SPIKE_MIN_COUNT = 20
SPIKE_FACTOR = 3
SPIKE_MIN_OTHER_YEARS = 3

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
