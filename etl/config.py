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

DATA_YEARS = list(range(2015, 2024))  # 2015-2023 (FTE data only available through 2023)

# =============================================================================
# DOE DATA SOURCE URLS
# =============================================================================

DOE_BASE_URL = "https://ope.ed.gov/campussafety/datafiles"
DOE_DOWNLOAD_PAGE = "https://ope.ed.gov/campussafety/#/datafile/list"

def get_data_url(year: int, file_type: str = "sas") -> str:
    """Get the download URL for a given year's data file."""
    if file_type == "sas":
        return f"{DOE_BASE_URL}/{year}/Crime{year}.sas7bdat"
    elif file_type == "csv":
        return f"{DOE_BASE_URL}/{year}/Crime{year}.csv"
    else:
        raise ValueError(f"Unknown file type: {file_type}")

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
