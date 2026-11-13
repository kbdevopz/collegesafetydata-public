"""
Fall enrollment for 2015-2020: NCES's official FTE, and the share of students
enrolled exclusively in distance education.

NCES publishes its own full-time-equivalent enrollment (FTE) for every fall,
but for falls before 2021 only inside the final IPEDS Access databases
(table DRVEF<year>). 01c_extract_ipeds_official.ps1 reads FTE and PCTDEEXC
(percent of students enrolled exclusively in distance education) from them
into etl/reference/ipeds_official_fte.csv, which is committed, so this step
needs neither Access nor those 430 MB of zips. The sources file next to it
(ipeds_official_sources.json) records each zip's URL, size and SHA-256.

From 2021 on, 02a_transform_enrollment.py reads FTE and PCTDEEXC from the
DRVEF CSVs, which NCES publishes on their own.

The headcounts (enrollment_total, enrollment_ft, enrollment_pt) still come
from the EF fall enrollment files: EFALEVEL 22 + 32 (full-time undergraduate
and graduate) and 42 + 52 (part-time). Each year reads the final revised file
(ef{year}a_rv.csv) when NCES has published it, otherwise the provisional
ef{year}a.csv. The files used, and the checksums of the reference files, are
recorded in data/curated/dims/enrollment_ef_inputs.json.

Earlier builds estimated 2015-2020 FTE from these headcounts with fixed
part-time factors (0.403543 and 0.361702). That matched NCES's FTE exactly
for only about 58% of institutions, so it is no longer used.

Usage:
    python 02b_transform_ef_enrollment.py
"""

import json
import sys
import pandas as pd
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT
import ipeds_files
import provenance

# Input file used for each year, recorded in the build manifest
INPUTS: dict[int, dict] = {}

# Directories
IPEDS_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ipeds"
CURATED_DIR = PROJECT_ROOT / "data" / "curated" / "dims"

# Years whose FTE comes from the Access databases (no DRVEF CSV for them)
EF_YEARS = [2015, 2016, 2017, 2018, 2019, 2020]

# The official FTE and PCTDEEXC, and where they came from (01c_extract_ipeds_official.ps1)
REFERENCE_CSV = provenance.REFERENCE_DIR / "ipeds_official_fte.csv"
REFERENCE_SOURCES = provenance.REFERENCE_DIR / "ipeds_official_sources.json"
REFERENCE_COLUMNS = ["year", "unitid", "fte", "pctdeexc"]
REDO = ("Run etl/01c_extract_ipeds_official.ps1 on Windows to write it again from NCES's Access databases, "
        "or restore it with git.")

# EFALEVEL codes of the EF files (attendance status and student level)
EFALEVEL_FT_UNDERGRAD = 22  # Full-time undergraduate
EFALEVEL_FT_GRADUATE = 32   # Full-time graduate (including professional)
EFALEVEL_PT_UNDERGRAD = 42  # Part-time undergraduate
EFALEVEL_PT_GRADUATE = 52   # Part-time graduate (including professional)


def load_official() -> pd.DataFrame:
    """
    etl/reference/ipeds_official_fte.csv, checked: one row per year of
    EF_YEARS and institution, the row counts the sources file records, FTE
    a whole number of at least 0 or blank, PCTDEEXC 0-100 or blank.
    Returns unitid, year, fte, pctdeexc (both nullable).
    """
    for path in (REFERENCE_CSV, REFERENCE_SOURCES):
        if not path.is_file():
            raise RuntimeError(f"{path} not found. {REDO}")
    sources = json.loads(REFERENCE_SOURCES.read_text(encoding="utf-8"))
    rows_recorded = {int(s["fall_year"]): int(s["rows"]) for s in sources}
    ref = pd.read_csv(REFERENCE_CSV, dtype=str, keep_default_na=False)
    if list(ref.columns) != REFERENCE_COLUMNS:
        raise RuntimeError(f"{REFERENCE_CSV.name} has columns {list(ref.columns)}, not {REFERENCE_COLUMNS}. {REDO}")

    def numbers(column: str) -> pd.Series:
        text = ref[column].str.strip()
        values = pd.to_numeric(text.where(text != ""), errors="coerce")
        bad = ref.loc[(text != "") & (values.isna() | (values % 1 != 0) | (values < 0)), column]
        if len(bad):
            raise RuntimeError(f"{REFERENCE_CSV.name}: {column} holds {bad.iloc[0]!r}, which is not a whole "
                               f"number of at least 0. {REDO}")
        return values.astype("Int64")

    out = pd.DataFrame({name: numbers(name) for name in REFERENCE_COLUMNS})
    if out["year"].isna().any() or out["unitid"].isna().any():
        raise RuntimeError(f"{REFERENCE_CSV.name} has a row without a year or UNITID. {REDO}")
    if out.duplicated(["year", "unitid"]).any():
        first = out[out.duplicated(["year", "unitid"])].iloc[0]
        raise RuntimeError(f"{REFERENCE_CSV.name} lists {first['unitid']} twice for {first['year']}. {REDO}")
    if (out["pctdeexc"] > 100).any():
        raise RuntimeError(f"{REFERENCE_CSV.name}: a pctdeexc above 100. {REDO}")
    counts = out.groupby("year").size().to_dict()
    for year in EF_YEARS:
        if counts.get(year, 0) != rows_recorded.get(year):
            raise RuntimeError(f"{REFERENCE_CSV.name} has {counts.get(year, 0):,} rows for {year}; "
                               f"{REFERENCE_SOURCES.name} says DRVEF{year} has {rows_recorded.get(year)}. {REDO}")
    extra = sorted(set(counts) - set(EF_YEARS))
    if extra:
        raise RuntimeError(f"{REFERENCE_CSV.name} has rows for {extra}, which this step does not build. {REDO}")
    out = out.astype({"year": "int16", "unitid": "int32"})
    out["fte"] = out["fte"].astype("Int32")
    out["pctdeexc"] = out["pctdeexc"].astype("Int16")
    return out


def load_ef_headcounts(year: int) -> pd.DataFrame:
    """
    Headcounts from the EF file of one fall year: unitid, enrollment_total,
    enrollment_ft, enrollment_pt (an institution without a level counts 0
    there).
    """
    # Final revised file (ef{year}a_rv.csv) when NCES has published it
    file_path = ipeds_files.pipeline_csv(year, f"ef{year}a")
    if file_path is None:
        raise RuntimeError(f"No ef{year}a.csv in {IPEDS_RAW_DIR / str(year)}. Run 01b_download_ipeds.py first.")

    INPUTS[year] = ipeds_files.input_record(file_path)
    print(f"  Reading {file_path.name} ({'final' if INPUTS[year]['final'] else 'provisional'})")
    df = pd.read_csv(file_path, usecols=["UNITID", "EFALEVEL", "EFTOTLT"])

    levels = {"ft_undergrad": EFALEVEL_FT_UNDERGRAD, "ft_graduate": EFALEVEL_FT_GRADUATE,
              "pt_undergrad": EFALEVEL_PT_UNDERGRAD, "pt_graduate": EFALEVEL_PT_GRADUATE}
    merged = None
    for column, level in levels.items():
        part = df[df["EFALEVEL"] == level][["UNITID", "EFTOTLT"]].rename(columns={"EFTOTLT": column})
        merged = part if merged is None else merged.merge(part, on="UNITID", how="outer")
    merged = merged.fillna(0)
    merged["enrollment_ft"] = merged["ft_undergrad"] + merged["ft_graduate"]
    merged["enrollment_pt"] = merged["pt_undergrad"] + merged["pt_graduate"]
    merged["enrollment_total"] = merged["enrollment_ft"] + merged["enrollment_pt"]
    merged = merged.rename(columns={"UNITID": "unitid"})
    merged = merged.astype({"unitid": "int32", "enrollment_total": "int32", "enrollment_ft": "int32",
                            "enrollment_pt": "int32"})
    return merged[["unitid", "enrollment_total", "enrollment_ft", "enrollment_pt"]]


def main():
    ipeds_files.EF_BUILD_MANIFEST_PATH.unlink(missing_ok=True)  # old record; rewritten only if this run completes
    print("=" * 60)
    print("IPEDS fall enrollment 2015-2020 (NCES's official FTE)")
    print("=" * 60)

    # The reference files' checksums, taken before they are read
    reference = {provenance.reference_name(p): provenance.reference_sha256(p)
                 for p in (REFERENCE_CSV, REFERENCE_SOURCES) if p.is_file()}
    official = load_official()
    print(f"Official FTE and PCTDEEXC: {REFERENCE_CSV.name} ({len(official):,} rows)")

    all_data = []
    for year in EF_YEARS:
        print(f"\n{year}:")
        heads = load_ef_headcounts(year)
        drvef = official[official["year"] == year]
        no_fte = drvef[drvef["fte"].isna()]
        with_fte = drvef[drvef["fte"].notna()]
        merged = with_fte.merge(heads, on="unitid", how="left", indicator=True)
        no_heads = int((merged["_merge"] == "left_only").sum())
        not_in_drvef = int((~heads["unitid"].isin(drvef["unitid"])).sum())
        merged = merged.drop(columns="_merge")
        for column in ("enrollment_total", "enrollment_ft", "enrollment_pt"):
            merged[column] = merged[column].fillna(0).astype("int32")
        print(f"  DRVEF{year}: {len(drvef):,} institutions, {len(with_fte):,} with an FTE "
              f"(range {int(with_fte['fte'].min()):,} - {int(with_fte['fte'].max()):,})")
        if len(no_fte):
            print(f"  Left out, no rate that year: {len(no_fte):,} institutions whose FTE NCES left blank "
                  f"({', '.join(str(u) for u in no_fte['unitid'].head(5))}{', ...' if len(no_fte) > 5 else ''})")
        if no_heads:
            print(f"  {no_heads:,} institutions with an FTE are not in the EF file; their headcounts are 0")
        if not_in_drvef:
            print(f"  {not_in_drvef:,} institutions of the EF file are not in DRVEF{year}; they have no FTE "
                  "that year (no rate)")
        online = merged["pctdeexc"]
        print(f"  Exclusively online (PCTDEEXC): 50% or more at {int((online >= 50).sum()):,} institutions, "
              f"blank for {int(online.isna().sum()):,}")
        all_data.append(merged)

    combined = pd.concat(all_data, ignore_index=True)
    combined = combined[["unitid", "year", "fte", "enrollment_total", "enrollment_ft", "enrollment_pt",
                         "pctdeexc"]]
    combined["fte"] = combined["fte"].astype("int32")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total records: {len(combined):,}")
    print(f"Unique institutions: {combined['unitid'].nunique():,}")
    print(f"Years covered: {sorted(combined['year'].unique().tolist())}")
    for unitid, name in ((130794, "Yale"), (166027, "Harvard"), (215062, "UPenn")):
        spot = combined[combined["unitid"] == unitid]
        if len(spot):
            print(f"\nSpot check - {name} ({unitid}):")
            print(spot.to_string(index=False))

    # Save to parquet
    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CURATED_DIR / "dim_enrollment_ef.parquet"
    combined.to_parquet(output_path, index=False)
    provenance.write_ef_manifest(INPUTS, outputs=[output_path], reference=reference)

    print(f"\nSaved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"Input record: {ipeds_files.EF_BUILD_MANIFEST_PATH}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 02a_transform_enrollment.py (to combine with DRVEF)")
    print("2. Run: python 04_create_aggregates.py")
    print("3. Run: python 05_generate_json.py")

    return 0


if __name__ == "__main__":
    sys.exit(provenance.run_locked("02b", main))
