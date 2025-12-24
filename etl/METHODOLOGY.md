# CollegeSafetyData.org - Data Methodology

This document describes the data sources, calculation methods, and methodological choices used in generating the campus safety statistics for CollegeSafetyData.org.

## Data Sources

### Campus Crime Data
- **Source:** U.S. Department of Education Campus Safety and Security Data
- **URL:** https://ope.ed.gov/campussafety/
- **Coverage:** 2015-2023
- **Legal Basis:** Clery Act (20 U.S.C. § 1092(f))

The Clery Act requires all postsecondary institutions participating in federal student aid programs to disclose campus crime statistics and security information annually.

### Enrollment Data
- **Source:** IPEDS (Integrated Postsecondary Education Data System)
- **URL:** https://nces.ed.gov/ipeds/
- **Files Used:**
  - DRVEF (Derived Fall Enrollment) for 2021-2023: Pre-calculated FTE
  - EF (Fall Enrollment) for 2015-2020: Calculated FTE from component data

## FTE (Full-Time Equivalent) Enrollment Calculation

FTE is used as the denominator for calculating per-student crime rates, enabling fair comparisons between institutions of different sizes.

### 2021-2023: Official IPEDS FTE
For these years, we use the pre-calculated FTE values directly from IPEDS DRVEF files. These are the official values computed by NCES.

### 2015-2020: Calculated FTE Using Official IPEDS Factors
For years where pre-calculated FTE is not available in DRVEF files, we calculate FTE from Fall Enrollment (EF) component data using the official IPEDS methodology:

```
FTE = FT_Undergrad + FT_Graduate +
      (PT_Undergrad × 0.403543) +
      (PT_Graduate × 0.361702)
```

#### Official IPEDS Conversion Factors
| Student Type | Factor | Source |
|--------------|--------|--------|
| Full-time Undergraduate | 1.0 | Counts as 1.0 FTE |
| Full-time Graduate | 1.0 | Counts as 1.0 FTE |
| Part-time Undergraduate | 0.403543 | IPEDS official factor |
| Part-time Graduate | 0.361702 | IPEDS official factor |

**Source:** NCES IPEDS Survey Methodology. These factors represent the average course load of part-time students relative to full-time students, as defined by the National Center for Education Statistics.

See: https://nces.ed.gov/ipeds/survey-components/8

#### EFALEVEL Codes Used
| Code | Description |
|------|-------------|
| 22 | Full-time undergraduate |
| 32 | Full-time graduate (including professional) |
| 42 | Part-time undergraduate |
| 52 | Part-time graduate (including professional) |

#### Implementation Reference
The FTE calculation for 2015-2020 is implemented in:
- **Script:** `etl/02b_transform_ef_enrollment.py`
- **Constants:** `PT_FACTOR_UNDERGRAD = 0.403543`, `PT_FACTOR_GRADUATE = 0.361702`

### Why Different Methods for Different Years?
IPEDS DRVEF (Derived Fall Enrollment) files, which contain pre-calculated FTE, are only available starting from 2021. For earlier years, we calculate FTE from the component enrollment data in EF files using the official IPEDS methodology.

This ensures our FTE calculations are directly comparable to Department of Education Campus Safety calculations and align with federal standards.

## Crime Rate Calculation

Crime rates are expressed as incidents per 10,000 FTE students:

```
Rate = (Incident Count / FTE) × 10,000
```

### Rate Display Thresholds
- Rates are only displayed for institutions with FTE ≥ 1,000 to avoid misleading statistics from small sample sizes
- Institutions with FTE < 1,000 or fewer than 10 incidents are marked with an asterisk (*) to indicate statistical caution

## Geographic Classifications

Crime data is reported across multiple geographic categories:

| Geography | Description |
|-----------|-------------|
| On-campus | All property owned or controlled by the institution |
| Residence halls | A subset of on-campus (student housing only) |
| Non-campus | Property owned but not contiguous to campus |
| Public property | Public property adjacent to campus |
| All | Sum of On-campus + Non-campus + Public property |

**Important:** Residence hall incidents are a subset of on-campus incidents and should not be added to on-campus counts.

## Offense Categories

### Criminal Offenses (Clery Act)
- Murder
- Negligent Manslaughter
- Rape
- Fondling
- Incest
- Statutory Rape
- Robbery
- Aggravated Assault
- Burglary
- Motor Vehicle Theft
- Arson

### VAWA Offenses (Violence Against Women Act)
- Domestic Violence
- Dating Violence
- Stalking

### Arrests and Disciplinary Referrals
- Weapons (Arrests and Disciplinary Actions)
- Drug Law (Arrests and Disciplinary Actions)
- Liquor Law (Arrests and Disciplinary Actions)

**Note:** The "All Offenses" category sums criminal offenses, VAWA offenses, AND arrests/disciplinary referrals. High counts in this category may reflect drug/alcohol enforcement rather than violent crime.

## Data Limitations

### Underreporting
Clery data represents only reported incidents. Research indicates significant underreporting:
- ~80% of campus crimes are never reported to authorities (DOJ NCVS)
- Only ~20% of college sexual assaults are reported (RAINN)
- Higher reported numbers may indicate better reporting culture, not more crime

### Institutional Variation
Reporting practices, police staffing, and definitions may vary by institution. Cross-institution comparisons should be made with caution.

### Temporal Lag
There is approximately a 1-year lag between when incidents occur and when data is published by the Department of Education.

### Definition Changes
- 2013: FBI updated rape definition to be gender-neutral
- 2014: VAWA offenses (domestic violence, dating violence, stalking) added to Clery requirements

## Validation

Our data pipeline includes validation steps to ensure accuracy:
1. Cross-reference of UNITID (institution ID) with IPEDS directory
2. Verification that offense counts sum correctly
3. Comparison of calculated FTE against official DRVEF values where available
4. Spot checks against known institutions (Ivy League, major state universities)

## Source Code

The complete ETL (Extract, Transform, Load) pipeline is open source and available for inspection:
- Data download: `01a_download_doe.py`, `01b_download_ipeds.py`
- Enrollment processing: `02a_transform_enrollment.py`, `02b_transform_ef_enrollment.py`
- Crime data processing: `03_transform_crimes.py`
- Aggregation: `04_create_aggregates.py`
- JSON generation: `05_generate_json.py`

## Contact

For questions about methodology or to report data issues, please open an issue on the GitHub repository.

## References

1. U.S. Department of Education. Campus Safety and Security Data Analysis Cutting Tool. https://ope.ed.gov/campussafety/
2. National Center for Education Statistics. IPEDS Survey Components. https://nces.ed.gov/ipeds/survey-components/
3. Clery Center. Summary of the Jeanne Clery Act. https://clerycenter.org/policy/the-clery-act/
4. RAINN. Campus Sexual Violence: Statistics. https://www.rainn.org/statistics/campus-sexual-violence
