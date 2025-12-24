# CollegeSafetyData.org

> Transparent access to campus crime statistics reported under the Jeanne Clery Act.

**Live Site:** [collegesafetydata.org](https://collegesafetydata.org)

This project provides free, public access to campus safety data for over 8,600 U.S. colleges and universities, covering 9 years of crime statistics (2015-2023). Data is sourced from the U.S. Department of Education and processed using an open, reproducible methodology.

## Overview

- **6,000+ Schools** — All U.S. institutions reporting Clery Act data
- **9 Years of Data** — 2015-2023 for consistent comparisons
- **Transparent Methodology** — Full ETL pipeline is open source
- **Rate-Based Rankings** — Per 10,000 FTE students for fair comparisons

## Features

- **Rankings** — Compare schools by offense type, year, and geography
- **School Profiles** — Detailed trends and breakdowns for each institution
- **Compare Tool** — Side-by-side comparisons of multiple schools
- **Data Audit** — Downloadable validation reports for data quality

## Data Sources

| Source | Coverage | URL |
|--------|----------|-----|
| Campus Crime Data | 2015-2023 | [ope.ed.gov/campussafety](https://ope.ed.gov/campussafety) |
| Enrollment (FTE) | 2015-2023 | [nces.ed.gov/ipeds](https://nces.ed.gov/ipedes) |

### Methodology

Our data processing pipeline is fully documented. See [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for:
- FTE calculation using official IPEDS factors
- Crime rate formulas
- Geographic classifications
- Data limitations

## Quick Start

### Frontend Only (Demo Mode)

The frontend includes sample data for immediate preview:

```bash
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173

### Full ETL Pipeline

Requires Python 3.11+:

```bash
cd etl
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the full pipeline
python 01_download_raw_data.py
python 02_transform_to_parquet.py
python 03_build_dimensions.py
python 04_create_aggregates.py
python 05_generate_json.py
```

Generated JSON files are written to `frontend/public/data/`.

## Project Structure

```
├── etl/                          # Data processing pipeline
│   ├── 01_download_raw_data.py   # Download DOE data
│   ├── 02_transform_to_parquet.py # Transform to Parquet
│   ├── 02a_transform_enrollment.py # Process DRVEF (2021-2023)
│   ├── 02b_transform_ef_enrollment.py # Calculate FTE from EF (2015-2020)
│   ├── 03_build_dimensions.py    # Build dimension tables
│   ├── 04_create_aggregates.py   # Create aggregate rankings
│   ├── 05_generate_json.py       # Export to JSON
│   ├── 06_validate.py            # Validate outputs
│   ├── 07_comprehensive_audit.py # Run data quality audit
│   ├── METHODOLOGY.md            # Full methodology documentation
│   └── config.py                 # Configuration
│
├── frontend/                     # React dashboard
│   ├── src/
│   │   ├── pages/               # Rankings, Compare, SchoolProfile, Methodology
│   │   ├── components/          # Reusable components
│   │   └── lib/                 # API, types, utilities
│   └── public/data/             # Generated JSON outputs
│
└── data/                        # Raw and processed data (gitignored)
    ├── raw/                     # Downloaded DOE/IPEDS files
    ├── curated/                 # Parquet fact/dimension tables
    └── qa/                      # Audit reports
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| ETL | Python 3.11+, DuckDB, pandas, pyarrow |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Charts | Recharts 2.x |
| Tables | TanStack Table v8 |
| Hosting | Cloudflare Pages (static) |

## FTE Calculation

Full-Time Equivalent (FTE) enrollment is used as the denominator for crime rate calculations:

- **2021-2023**: Official IPEDS pre-calculated FTE values
- **2015-2020**: Calculated from raw enrollment components using official IPEDS factors:
  ```
  FTE = FT_Undergrad + FT_Graduate
      + (PT_Undergrad × 0.403543)
      + (PT_Graduate × 0.361702)
  ```

See [etl/METHODOLOGY.md](etl/METHODOLOGY.md) for complete documentation.

## Data Quality

Every data run includes a comprehensive audit validating:
- School completeness (all schools have JSON files)
- Incident total accuracy (sums match aggregates)
- FTE coverage by year
- Rate calculation verification
- Ranking order validation

Download the latest audit: [audit.json](https://collegesafetydata.org/audit.json)

## Data Limitations

- **Underreporting**: ~80% of campus crimes are never reported (DOJ NCVS)
- **Reporting Lag**: DOE releases data ~1 year after collection
- **Institutional Variation**: Reporting practices vary by school
- **Higher Numbers ≠ More Crime**: Often indicates better reporting culture

## Development

```bash
# Install dependencies
cd frontend && npm install

# Run dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## License

This project displays publicly available data from the U.S. Department of Education. Built for transparency and public education purposes.

## Data Citation

If you use this data in research or reporting, please cite both sources:

1. U.S. Department of Education. Campus Safety and Security Data Analysis Cutting Tool. https://ope.ed.gov/campussafety/
2. National Center for Education Statistics. IPEDS. https://nces.ed.gov/ipeds/
