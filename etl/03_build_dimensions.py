"""
Build dimension tables for institutions and offenses.

This script creates dimension tables that enrich the fact data:
- dim_institution: School metadata with Ivy League flags, for every campus
  that reported at least one year (campus_year_sources.parquet), including
  campuses that never had an incident
- dim_offense: Offense metadata with descriptions and ordering

Usage:
    python 03_build_dimensions.py
"""

import os
import re
import sys
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    CURATED_DIR, IVY_LEAGUE, IVY_BASE_UNITIDS, OFFENSE_ORDER_MAP,
    OFFENSE_DESCRIPTIONS, OFFENSE_FAMILIES, US_STATES, VALID_STATE_CODES,
    PROCESS_ALL_SCHOOLS, DATA_YEARS, GEO_FOR_ALL, SIZE_SETTING_FIELDS
)
import campus_identity
import provenance
from ipeds_files import IPEDS_RAW_DIR

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"
# The campus-years DOE published (02_transform_to_parquet.py): a campus-year
# is reported when its release row has at least one count cell that is not
# blank, so a campus that reported only zeros is in it but not in the facts
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"
# Every release's names and addresses of each campus (02_transform_to_parquet.py)
NAMES_PATH = CURATED_DIR / "dims" / "campus_names.parquet"
# The campus ID changes cross-linked on the site (build_id_links)
LINKS_PATH = CURATED_DIR / "dims" / "campus_id_links.parquet"
# IPEDS hospital and Carnegie fields per institution-year, and the reviewed
# list of other institutions whose campus population students do not
# measure (build_institution_classes; 04's rate rules read it)
CLASS_PATH = CURATED_DIR / "dims" / "dim_institution_class.parquet"
POPULATION_LIST_PATH = Path(__file__).parent / "reference" / "rate_population_exclusions.csv"
MEDICAL_PATH = CURATED_DIR / "dims" / "dim_medical_campus.parquet"
MEDICAL_LIST_PATH = Path(__file__).parent / "reference" / "medical_campuses.csv"
# Campuses reviewed for the medical-center list and not listed (07's screen reads it; checked here)
MEDICAL_REVIEWS_PATH = Path(__file__).parent / "reference" / "medical_campus_reviews.csv"
# Campuses DOE gives a state that are abroad (reviewed; not in the institution's rates)
ABROAD_PATH = CURATED_DIR / "dims" / "dim_campus_abroad.parquet"
ABROAD_LIST_PATH = Path(__file__).parent / "reference" / "campuses_abroad.csv"
# Campuses whose reported figures are another institution's campus figures
# (reviewed; never in their own institution's rates)
OVERRIDE_PATH = CURATED_DIR / "dims" / "dim_shared_campus_override.parquet"
OVERRIDE_LIST_PATH = Path(__file__).parent / "reference" / "shared_campus_overrides.csv"
CARNEGIE_FIELDS = ("C21BASIC", "C18BASIC", "C15BASIC")  # newest classification first


def find_stray_facts() -> list:
    """Parquet data under data/curated/facts other than FACTS_PATH."""
    def fail(err):
        raise err

    stray = []
    for root, dirs, files in os.walk(FACTS_PATH.parent, onerror=fail):
        root = Path(root)
        for name in list(dirs):
            if name.lower() == "incidents" or name.lower().endswith(".parquet"):
                stray.append(root / name)
                dirs.remove(name)
        for name in files:
            if name.lower().endswith(".parquet") and root / name != FACTS_PATH:
                stray.append(root / name)
    return sorted(stray)


def get_facts_path() -> str:
    """FACTS_PATH, after checking that nothing else there could be read as facts."""
    stray = find_stray_facts()
    if stray:
        listing = "\n".join(f"  {p}{' (folder)' if p.is_dir() else ''}" for p in stray)
        raise RuntimeError(
            f"{FACTS_PATH.parent} holds parquet data that 02_transform_to_parquet.py "
            f"did not write:\n{listing}\n"
            f"Only the file {FACTS_PATH.name} belongs there. Delete the items listed above "
            f"(move them outside data/curated to keep them), then run this step again."
        )
    if not FACTS_PATH.is_file():
        raise RuntimeError(f"{FACTS_PATH} not found. Run 02_transform_to_parquet.py first.")
    return str(FACTS_PATH)


def facts_read_error(err: Exception) -> RuntimeError:
    return RuntimeError(
        f"Could not read {FACTS_PATH}: {err}\n"
        f"If another program (sync, backup or antivirus) has the file open, close it and "
        f"run this step again. Otherwise run 02_transform_to_parquet.py again."
    )


def add_campus_identity(dim: pd.DataFrame) -> pd.DataFrame:
    """
    The campus identity columns (campus_identity.campus_identities, from
    every DOE release's names and the IPEDS directory files):
        campus_name: string          # the campus's own DOE name (BRANCH) when it says
                                     # more than the institution name, else null
        doe_branch: string           # BRANCH as DOE's newest release spells it
        aliases: list<string>        # other names to search by (former DOE names, IPEDS IALIAS)
    A city that is no place name in raw_institutions (a stray value such as
    "2: No") is replaced with the campus's city in another release.
    """
    names = pd.read_parquet(NAMES_PATH)
    hd, _files = campus_identity.ipeds_directory(IPEDS_RAW_DIR, DATA_YEARS)
    ids, repaired = campus_identity.campus_identities(names, hd)
    missing = sorted(set(dim["unitid"].astype(int)) - set(ids["unitid"]))
    if missing:
        raise RuntimeError(f"{len(missing)} reporting campuses are not in {NAMES_PATH.name} (UNITIDs "
                           f"{missing[:10]}). Run 02_transform_to_parquet.py again, then this step.")
    ids = ids.set_index("unitid")
    out = dim.copy()
    out["campus_name"] = [ids.at[u, "campus_name"] for u in out["unitid"]]
    out["doe_branch"] = [ids.at[u, "doe_branch"] or None for u in out["unitid"]]
    out["aliases"] = [list(ids.at[u, "aliases"]) for u in out["unitid"]]
    bad_city = [u for u, c in zip(out["unitid"], out["city"])
                if c is None or pd.isna(c) or not re.search(r"[A-Za-z]", str(c)) or re.search(r"\d|:", str(c))]
    for u in bad_city:
        if ids.at[u, "city"]:
            out.loc[out["unitid"] == u, "city"] = ids.at[u, "city"]
    print(f"  Campus names: {out['campus_name'].notna().sum():,} campuses have their own DOE campus name "
          f"({(out['campus_name'].notna() & ~out['is_main_campus']).sum():,} of them not main campuses); "
          f"{sum(len(a) for a in out['aliases']):,} search aliases; IPEDS directory files read: {len(_files)}")
    print(f"  Repaired text: {', '.join(f'{k} {len(v)}' for k, v in repaired.items())}; "
          f"cities replaced: {len(bad_city)}")
    return out


def build_id_links(dim: pd.DataFrame) -> pd.DataFrame:
    """
    The campus ID changes (campus_identity.detect_id_changes), checked
    against the reviewed list etl/reference/campus_id_changes.csv, and the
    "link" pairs as one row per campus and linked campus:
        unitid: int32, other_unitid: int32
        other_years: string          # the years DOE reported the campus under other_unitid
        relation: string             # "earlier" (other_unitid was used first) or "later"
    The two pages are cross-linked; no figures move between the IDs.
    """
    found = campus_identity.candidates_from_curated(CURATED_DIR, DATA_YEARS, GEO_FOR_ALL)
    if not campus_identity.ID_CHANGES_PATH.is_file():
        raise RuntimeError(f"{campus_identity.ID_CHANGES_PATH} is missing. Restore it from git.")
    reviewed = campus_identity.read_id_changes()
    key = ["old_unitid", "new_unitid"]
    diff = campus_identity.compare_with_review(found, campus_identity.evidence_text(reviewed))
    if any(diff.values()):
        raise RuntimeError(
            f"{campus_identity.ID_CHANGES_PATH.name} no longer matches the DOE files: {len(diff['new'])} new "
            f"candidate pairs, {len(diff['gone'])} pairs no longer found, {len(diff['changed'])} with changed "
            f"evidence (first: {(diff['new'] + diff['gone'] + diff['changed'])[:3]}). Review them: run "
            "`python campus_identity.py` (it keeps the decisions of unchanged pairs and proposes one for the "
            "others), check those rows' decisions, then run this step again.")
    bad = reviewed[~reviewed["decision"].isin(["link", "reject"]) | reviewed["reason"].str.startswith("proposed:")]
    if len(bad):
        raise RuntimeError(f"{campus_identity.ID_CHANGES_PATH.name}: {len(bad)} rows are not reviewed (decision "
                           f"must be link or reject, reason not 'proposed: ...'; first {bad[key].values.tolist()[:3]})")
    links = reviewed[reviewed["decision"] == "link"]
    known = set(dim["unitid"].astype(int))
    rows = []
    for o, n, oy, ny in zip(links["old_unitid"], links["new_unitid"], links["old_years"], links["new_years"]):
        if o not in known or n not in known:
            raise RuntimeError(f"Linked campus {o if o not in known else n} reported no year of DATA_YEARS.")
        rows.append((o, n, ny, "later"))
        rows.append((n, o, oy, "earlier"))
    out = pd.DataFrame(rows, columns=["unitid", "other_unitid", "other_years", "relation"])
    out = out.astype({"unitid": "int32", "other_unitid": "int32"}).sort_values(["unitid", "other_unitid"])
    print(f"  Campus ID changes: {len(reviewed)} reviewed candidate pairs, {len(links)} linked, "
          f"{len(reviewed) - len(links)} rejected")
    return out.reset_index(drop=True)


def build_dim_institution() -> pd.DataFrame:
    """
    Create institution dimension with Ivy League flags.

    Schema:
        unitid: int32                # Primary key
        institution_name: string     # Full name
        short_name: string           # Short name (Ivy only)
        city: string
        state: string (2-char)
        ivy_league: boolean
        sector: string               # Optional, from raw data
    """
    print("Building institution dimension...")

    dims_dir = CURATED_DIR / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()

    # Get unique UNITIDs from facts (a read error stops the build)
    facts_file = get_facts_path()
    try:
        fact_ids = con.execute(f"""
            SELECT DISTINCT unitid
            FROM read_parquet('{facts_file}')
            ORDER BY unitid
        """).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e

    # Every campus that reported a year, incidents or not: a reported year
    # with no incident is a 0, which its school page and the rankings show
    if not SOURCES_PATH.is_file():
        raise RuntimeError(f"{SOURCES_PATH} not found. Run 02_transform_to_parquet.py first.")
    reported_ids = set(pd.read_parquet(SOURCES_PATH, columns=["unitid"])["unitid"].astype(int).tolist())
    fact_set = set(fact_ids["unitid"].astype(int).tolist())
    unreported = sorted(fact_set - reported_ids)
    if unreported:
        raise RuntimeError(f"{len(unreported)} schools have incidents but no reported campus-year in "
                           f"{SOURCES_PATH.name} (UNITIDs {unreported[:10]}). Run 02_transform_to_parquet.py "
                           "again, then this step.")
    unitids_df = pd.DataFrame({"unitid": sorted(reported_ids)})

    print(f"  Found {len(unitids_df)} campuses that reported a year ({len(fact_set)} with incidents, "
          f"{len(reported_ids - fact_set)} that only ever reported zeros)")

    # Names, cities and states come from the institution list that 02 writes
    raw_inst_path = dims_dir / "raw_institutions.parquet"
    if not raw_inst_path.is_file():
        raise RuntimeError(f"{raw_inst_path} not found. Run 02_transform_to_parquet.py first.")
    raw_inst = pd.read_parquet(raw_inst_path)
    raw_inst.columns = raw_inst.columns.str.upper()
    print(f"  Loaded raw institution data: {len(raw_inst)} rows")
    missing_cols = [c for c in ("INSTNM", "CITY") if c not in raw_inst.columns]
    if not {"UNITID", "UNITID_P"} & set(raw_inst.columns):
        missing_cols.append("UNITID_P")
    if not {"STATE", "STABBR"} & set(raw_inst.columns):
        missing_cols.append("STATE")
    if missing_cols:
        raise RuntimeError(
            f"{raw_inst_path} has no {', '.join(missing_cols)} column. "
            f"Run 02_transform_to_parquet.py again and check the DOE file layout."
        )

    # Build dimension
    records = []

    for unitid in unitids_df["unitid"]:
        # Check if this is an Ivy League school (by base unitid)
        base_unitid = int(unitid) // 1000
        is_ivy = base_unitid in IVY_BASE_UNITIDS

        # Determine campus type based on UNITID suffix
        # Main campuses typically end in 001, branches have other suffixes
        branch_suffix = int(unitid) % 1000
        is_main_campus = (branch_suffix == 1)

        record = {
            "unitid": int(unitid),
            "base_unitid": base_unitid,
            "is_main_campus": is_main_campus,
            "institution_name": None,
            "short_name": None,
            "city": None,
            "state": None,
            "ivy_league": is_ivy,
            "sector": None,
        }

        # Add Ivy League info (use main campus info for all branches)
        if is_ivy:
            # Find the main campus unitid (base * 1000 + 1)
            main_campus_uid = base_unitid * 1000 + 1
            if main_campus_uid in IVY_LEAGUE:
                ivy_info = IVY_LEAGUE[main_campus_uid]
                record["institution_name"] = ivy_info["name"]
                record["short_name"] = ivy_info["short"]
                record["city"] = ivy_info["city"]
                record["state"] = ivy_info["state"]

        # Get info from raw institutions
        # Check various possible column names for UNITID
        unitid_col = None
        for col in ["UNITID", "UNITID_P"]:
            if col in raw_inst.columns:
                unitid_col = col
                break

        if unitid_col:
            # Match unitid directly (UNITID_P is same format, just float)
            row = raw_inst[raw_inst[unitid_col].astype(int) == unitid]

            if len(row) > 0:
                row = row.iloc[0]
                if record["institution_name"] is None and "INSTNM" in row.index:
                    record["institution_name"] = row.get("INSTNM")
                if record["city"] is None and "CITY" in row.index:
                    record["city"] = row.get("CITY")
                # Check for STATE or STABBR column
                if record["state"] is None:
                    if "STATE" in row.index:
                        record["state"] = row.get("STATE")
                    elif "STABBR" in row.index:
                        record["state"] = row.get("STABBR")
                if "SECTOR_DESC" in row.index:
                    record["sector"] = row.get("SECTOR_DESC")

        records.append(record)

    dim_institution = pd.DataFrame(records)
    dim_institution = add_campus_identity(dim_institution)

    # A school without a name would drop out of the "All" totals in step 04
    missing = dim_institution.loc[dim_institution["institution_name"].isna(), "unitid"].tolist()
    if missing:
        raise RuntimeError(
            f"{len(missing)} reporting schools have no name in {raw_inst_path.name} "
            f"(UNITIDs {missing[:10]}). Run 02_transform_to_parquet.py again, then this step."
        )

    # Add state_name column from config
    dim_institution["state_name"] = dim_institution["state"].map(
        lambda x: US_STATES.get(x, x) if pd.notna(x) else None
    )

    # Ensure proper types
    dim_institution["unitid"] = dim_institution["unitid"].astype("int32")
    dim_institution["base_unitid"] = dim_institution["base_unitid"].astype("int32")
    dim_institution["is_main_campus"] = dim_institution["is_main_campus"].astype(bool)
    dim_institution["ivy_league"] = dim_institution["ivy_league"].astype(bool)

    # Save
    output_path = dims_dir / "dim_institution.parquet"
    dim_institution.to_parquet(output_path, index=False)

    # Summary
    ivy_count = dim_institution["ivy_league"].sum()
    main_count = dim_institution["is_main_campus"].sum()
    branch_count = len(dim_institution) - main_count
    states_with_data = dim_institution["state"].dropna().nunique()

    print(f"  Total institutions: {len(dim_institution)}")
    print(f"  Main campuses: {main_count}")
    print(f"  Branch campuses: {branch_count}")
    print(f"  Ivy League: {ivy_count}")
    print(f"  States with data: {states_with_data}")

    # Show top states by school count
    if PROCESS_ALL_SCHOOLS and len(dim_institution) > 100:
        state_counts = dim_institution["state"].value_counts().head(10)
        print("\n  Top 10 states by school count:")
        for state, count in state_counts.items():
            state_name = US_STATES.get(state, state)
            print(f"    {state} ({state_name}): {count}")

    print(f"\n  Saved to: {output_path}")

    return dim_institution


def build_dim_offense() -> pd.DataFrame:
    """
    Create offense dimension with metadata.

    Schema:
        offense: string              # Primary key
        offense_family: string       # "Criminal", "VAWA", etc.
        family_display: string       # "Criminal Offenses"
        description: string          # Full description
        display_order: int16         # For consistent UI ordering
        definition_version: string   # "post_2015"
        comparable_from_year: int16  # 2015
    """
    print("\nBuilding offense dimension...")

    dims_dir = CURATED_DIR / "dims"
    dims_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()

    # Get unique offenses from facts (a read error stops the build)
    facts_file = get_facts_path()
    try:
        offenses_df = con.execute(f"""
            SELECT DISTINCT
                offense,
                offense_family
            FROM read_parquet('{facts_file}')
            ORDER BY offense
        """).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e
    offenses_df["definition_version"] = "post_2015"

    print(f"  Found {len(offenses_df)} unique offenses")

    # Enrich with metadata
    records = []

    for _, row in offenses_df.iterrows():
        offense = row["offense"]
        family = row["offense_family"]

        record = {
            "offense": offense,
            "offense_family": family,
            "family_display": OFFENSE_FAMILIES.get(family, {}).get("display", family),
            "description": OFFENSE_DESCRIPTIONS.get(offense, ""),
            "display_order": OFFENSE_ORDER_MAP.get(offense, 999),
            "definition_version": row["definition_version"],
            "comparable_from_year": 2015,
        }

        records.append(record)

    dim_offense = pd.DataFrame(records)

    # Sort by display order
    dim_offense = dim_offense.sort_values("display_order").reset_index(drop=True)

    # Ensure proper types
    dim_offense["display_order"] = dim_offense["display_order"].astype("int16")
    dim_offense["comparable_from_year"] = dim_offense["comparable_from_year"].astype("int16")

    # Save
    output_path = dims_dir / "dim_offense.parquet"
    dim_offense.to_parquet(output_path, index=False)

    # Summary
    print(f"  Total offenses: {len(dim_offense)}")
    print(f"  Families: {dim_offense['offense_family'].nunique()}")
    print(f"  Saved to: {output_path}")

    # Show offense list
    print("\n  Offense order:")
    for _, row in dim_offense.iterrows():
        print(f"    {row['display_order']:2d}. {row['offense']} ({row['offense_family']})")

    return dim_offense


def build_institution_classes() -> pd.DataFrame:
    """
    dim_institution_class.parquet, one row per IPEDS HD row of DATA_YEARS
    (UNITID = the base UNITID of the DOE campuses): unitid, year, hospital
    (HD HOSPITAL: 1 yes, 2 no, negative not applicable or not reported),
    carnegie_field and carnegie_basic (the newest Carnegie basic
    classification field that year's HD file has: C21BASIC, C18BASIC or
    C15BASIC), the Carnegie Size & Setting fields that year's file has
    (c21szset, c18szset, c15szset of SIZE_SETTING_FIELDS; none when the file
    lacks the field), and listed_reason and listed_source for the
    institution-years of etl/reference/rate_population_exclusions.csv (a row
    is added for one the HD file lacks).
    """
    print("\nBuilding institution classes (IPEDS HD hospital and Carnegie fields)...")
    frames = []
    for year in DATA_YEARS:
        path = IPEDS_RAW_DIR / str(year) / f"hd{year}.csv"
        if not path.is_file():
            print(f"  {year}: no {path.name}, no classes")
            continue
        try:
            path.read_bytes().decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            encoding = "cp1252"
        df = pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False)
        df.columns = [c.strip().upper() for c in df.columns]
        field = next((f for f in CARNEGIE_FIELDS if f in df.columns), None)
        if "HOSPITAL" not in df.columns or field is None:
            raise RuntimeError(f"{path} has no HOSPITAL or Carnegie basic field ({', '.join(CARNEGIE_FIELDS)}). "
                               "Check the IPEDS HD file layout.")
        frames.append(pd.DataFrame({
            "unitid": pd.to_numeric(df["UNITID"], errors="coerce"),
            "year": year,
            "hospital": pd.to_numeric(df["HOSPITAL"], errors="coerce"),
            "carnegie_field": field,
            "carnegie_basic": pd.to_numeric(df[field], errors="coerce"),
            **{f.lower(): (pd.to_numeric(df[f], errors="coerce") if f in df.columns else None)
               for f in SIZE_SETTING_FIELDS},
        }))
        print(f"  {year}: {len(df):,} institutions, Carnegie field {field}, "
              f"HOSPITAL = 1: {int((pd.to_numeric(df['HOSPITAL'], errors='coerce') == 1).sum()):,}")
    out = pd.concat(frames, ignore_index=True).dropna(subset=["unitid"])
    out["listed_reason"] = None
    out["listed_source"] = None
    listed = pd.read_csv(POPULATION_LIST_PATH, dtype=str, keep_default_na=False)
    need = {"unitid", "first_year", "last_year", "reason", "source"}
    if set(listed.columns) != need:
        raise RuntimeError(f"{POPULATION_LIST_PATH} must have the columns {sorted(need)}")
    extra = []
    for row in listed.to_dict("records"):
        unitid = int(row["unitid"])
        if not row["reason"].strip() or not row["source"].strip():
            raise RuntimeError(f"{POPULATION_LIST_PATH}: {unitid} needs a reason and a source")
        for year in range(int(row["first_year"]), int(row["last_year"]) + 1):
            if year not in DATA_YEARS:
                continue
            hit = (out["unitid"] == unitid) & (out["year"] == year)
            if hit.any():
                out.loc[hit, "listed_reason"] = row["reason"].strip()
                out.loc[hit, "listed_source"] = row["source"].strip()
            else:
                extra.append({"unitid": unitid, "year": year, "hospital": None, "carnegie_field": None,
                              "carnegie_basic": None, **{f.lower(): None for f in SIZE_SETTING_FIELDS},
                              "listed_reason": row["reason"].strip(),
                              "listed_source": row["source"].strip()})
    if extra:
        out = pd.concat([out, pd.DataFrame(extra)], ignore_index=True)
    out = out.astype({"unitid": "int32", "year": "int16", "hospital": "Int16", "carnegie_basic": "Int16",
                      **{f.lower(): "Int16" for f in SIZE_SETTING_FIELDS},
                      "carnegie_field": "string", "listed_reason": "string", "listed_source": "string"})
    out = out.sort_values(["year", "unitid"]).reset_index(drop=True)
    if out.duplicated(["unitid", "year"]).any():
        raise RuntimeError("An IPEDS HD file lists one UNITID twice. Check the HD files.")
    out.to_parquet(CLASS_PATH, index=False)
    print(f"  Listed in {POPULATION_LIST_PATH.name}: {int(out['listed_reason'].notna().sum()):,} institution-years")
    print(f"  Saved to: {CLASS_PATH}")
    return out


def build_medical_campuses(dim_institution: pd.DataFrame) -> pd.DataFrame:
    """
    dim_medical_campus.parquet: unitid, year, reason, source for each year of
    DATA_YEARS in the ranges of etl/reference/medical_campuses.csv (campuses
    that are medical centers or hospitals inside an institution, reviewed
    one by one; config.py, MEDICAL_CAMPUS_SHARE). Every listed UNITID must
    be a campus of dim_institution.
    """
    print("\nBuilding the list of medical-center campuses...")
    listed = pd.read_csv(MEDICAL_LIST_PATH, dtype=str, keep_default_na=False)
    need = {"unitid", "first_year", "last_year", "reason", "source"}
    if set(listed.columns) != need:
        raise RuntimeError(f"{MEDICAL_LIST_PATH} must have the columns {sorted(need)}")
    campuses = set(dim_institution["unitid"].astype(int).tolist())
    rows = []
    for row in listed.to_dict("records"):
        unitid = int(row["unitid"])
        if unitid not in campuses:
            raise RuntimeError(f"{MEDICAL_LIST_PATH}: {unitid} is not a campus in DOE's files")
        if not row["reason"].strip() or not row["source"].strip():
            raise RuntimeError(f"{MEDICAL_LIST_PATH}: {unitid} needs a reason and a source")
        for year in range(int(row["first_year"]), int(row["last_year"]) + 1):
            if year in DATA_YEARS:
                rows.append({"unitid": unitid, "year": year, "reason": row["reason"].strip(),
                             "source": row["source"].strip()})
    out = pd.DataFrame(rows, columns=["unitid", "year", "reason", "source"]).astype(
        {"unitid": "int32", "year": "int16", "reason": "string", "source": "string"})
    if out.duplicated(["unitid", "year"]).any():
        raise RuntimeError(f"{MEDICAL_LIST_PATH} lists a campus twice for one year")
    out = out.sort_values(["year", "unitid"]).reset_index(drop=True)
    out.to_parquet(MEDICAL_PATH, index=False)
    print(f"  {listed['unitid'].nunique()} campuses, {len(out):,} campus-years. Saved to: {MEDICAL_PATH}")
    return out


def build_campuses_abroad(dim_institution: pd.DataFrame) -> pd.DataFrame:
    """
    dim_campus_abroad.parquet: unitid, country, reason, source for each row of
    etl/reference/campuses_abroad.csv: campuses DOE gives a U.S. state that are
    abroad (reviewed one by one). 04 treats them as it treats a campus DOE
    lists without a state: their incidents are not in the institution's
    counts for rates (IPEDS fall enrollment leaves out students abroad). Every
    listed UNITID must be a campus of dim_institution with a state.
    """
    print("\nBuilding the list of campuses abroad that DOE gives a state...")
    listed = pd.read_csv(ABROAD_LIST_PATH, dtype=str, keep_default_na=False)
    need = ["unitid", "country", "reason", "source"]
    if list(listed.columns) != need:
        raise RuntimeError(f"{ABROAD_LIST_PATH} must have the columns {need}")
    state_of = dict(zip(dim_institution["unitid"].astype(int).tolist(), dim_institution["state"].tolist()))
    for row in listed.to_dict("records"):
        unitid = int(row["unitid"])
        if unitid not in state_of:
            raise RuntimeError(f"{ABROAD_LIST_PATH}: {unitid} is not a campus in DOE's files")
        if not state_of[unitid] or pd.isna(state_of[unitid]):
            raise RuntimeError(f"{ABROAD_LIST_PATH}: {unitid} has no state in DOE's files, so it is abroad already; "
                               "remove it from the list")
        if not all(row[c].strip() for c in need[1:]):
            raise RuntimeError(f"{ABROAD_LIST_PATH}: {unitid} needs a country, a reason and a source")
    if listed["unitid"].duplicated().any():
        raise RuntimeError(f"{ABROAD_LIST_PATH} lists a campus twice")
    out = listed.assign(unitid=listed["unitid"].astype("int32"))[need].sort_values("unitid").reset_index(drop=True)
    out = out.astype({c: "string" for c in need[1:]})
    out.to_parquet(ABROAD_PATH, index=False)
    print(f"  {len(out)} campuses. Saved to: {ABROAD_PATH}")
    return out


def build_shared_campus_overrides(dim_institution: pd.DataFrame) -> pd.DataFrame:
    """
    dim_shared_campus_override.parquet: unitid, year, host_unitid, reason,
    source for each year of DATA_YEARS in the ranges of
    etl/reference/shared_campus_overrides.csv: campuses whose reported
    figures are another institution's campus figures (the host campus),
    reviewed one by one. 04 never counts them in their own institution's
    rates; DOE's counts are not changed. Each UNITID and host must be a
    campus of dim_institution, of different institutions.
    """
    print("\nBuilding the list of campuses that report another institution's figures...")
    listed = pd.read_csv(OVERRIDE_LIST_PATH, dtype=str, keep_default_na=False)
    need = ["unitid", "host_unitid", "first_year", "last_year", "reason", "source"]
    if list(listed.columns) != need:
        raise RuntimeError(f"{OVERRIDE_LIST_PATH} must have the columns {need}")
    campuses = set(dim_institution["unitid"].astype(int).tolist())
    rows = []
    for row in listed.to_dict("records"):
        unitid, host = int(row["unitid"]), int(row["host_unitid"])
        for u in (unitid, host):
            if u not in campuses:
                raise RuntimeError(f"{OVERRIDE_LIST_PATH}: {u} is not a campus in DOE's files")
        if unitid // 1000 == host // 1000:
            raise RuntimeError(f"{OVERRIDE_LIST_PATH}: {unitid} and its host {host} are campuses of one institution")
        if not row["reason"].strip() or not row["source"].strip():
            raise RuntimeError(f"{OVERRIDE_LIST_PATH}: {unitid} needs a reason and a source")
        for year in range(int(row["first_year"]), int(row["last_year"]) + 1):
            if year in DATA_YEARS:
                rows.append({"unitid": unitid, "year": year, "host_unitid": host, "reason": row["reason"].strip(),
                             "source": row["source"].strip()})
    out = pd.DataFrame(rows, columns=["unitid", "year", "host_unitid", "reason", "source"]).astype(
        {"unitid": "int32", "year": "int16", "host_unitid": "int32", "reason": "string", "source": "string"})
    if out.duplicated(["unitid", "year"]).any():
        raise RuntimeError(f"{OVERRIDE_LIST_PATH} lists a campus twice for one year")
    hosts = set(zip(out["host_unitid"].astype(int).tolist(), out["year"].astype(int).tolist()))
    if any((int(u), int(y)) in hosts for u, y in zip(out["unitid"], out["year"])):
        raise RuntimeError(f"{OVERRIDE_LIST_PATH} lists a campus that is another listed campus's host that year")
    out = out.sort_values(["year", "unitid"]).reset_index(drop=True)
    out.to_parquet(OVERRIDE_PATH, index=False)
    print(f"  {listed['unitid'].nunique()} campuses, {len(out):,} campus-years. Saved to: {OVERRIDE_PATH}")
    return out


def check_medical_reviews(dim_institution: pd.DataFrame) -> None:
    """
    Check etl/reference/medical_campus_reviews.csv, the campuses reviewed for
    the medical-center list and not listed (decision "not listed", or
    "undecided" when the review could not settle it), with the years
    reviewed: each a campus of dim_institution, once, and none for a year
    that medical_campuses.csv lists. 07's name and address screen reads it.
    """
    reviews = pd.read_csv(MEDICAL_REVIEWS_PATH, dtype=str, keep_default_na=False)
    need = ["unitid", "first_year", "last_year", "decision", "reason", "source"]
    if list(reviews.columns) != need:
        raise RuntimeError(f"{MEDICAL_REVIEWS_PATH} must have the columns {need}")
    campuses = set(dim_institution["unitid"].astype(int).tolist())
    listed = pd.read_csv(MEDICAL_LIST_PATH, dtype=str, keep_default_na=False)
    listed_years = {(int(u), y) for u, a, b in zip(listed["unitid"], listed["first_year"], listed["last_year"])
                    for y in range(int(a), int(b) + 1)}
    for row in reviews.to_dict("records"):
        unitid = int(row["unitid"])
        if unitid not in campuses:
            raise RuntimeError(f"{MEDICAL_REVIEWS_PATH}: {unitid} is not a campus in DOE's files")
        if row["decision"] not in ("not listed", "undecided") or not row["reason"].strip() or not row["source"].strip():
            raise RuntimeError(f"{MEDICAL_REVIEWS_PATH}: {unitid} needs a decision (not listed, undecided), a reason "
                               "and a source")
        if any((unitid, y) in listed_years for y in range(int(row["first_year"]), int(row["last_year"]) + 1)):
            raise RuntimeError(f"{MEDICAL_REVIEWS_PATH}: {unitid} is reviewed as not listed for a year that "
                               f"{MEDICAL_LIST_PATH.name} lists")
    if reviews["unitid"].duplicated().any():
        raise RuntimeError(f"{MEDICAL_REVIEWS_PATH} lists a campus twice")
    print(f"  Medical-center campus reviews (not listed): {len(reviews)} campuses checked")


def main():
    print("=" * 60)
    print("Building Dimension Tables")
    print("=" * 60)

    # The files this step reads, checked against 02's record before reading
    dims = CURATED_DIR / "dims"
    inputs_before = provenance.Snapshot("03", [FACTS_PATH, dims / "raw_institutions.parquet", SOURCES_PATH,
                                               NAMES_PATH])
    # The other files it reads: the IPEDS directory files and the reviewed ID changes
    _hd, hd_files = campus_identity.ipeds_directory(IPEDS_RAW_DIR, DATA_YEARS)
    other_inputs = provenance.other_input_records(hd_files + [campus_identity.ID_CHANGES_PATH,
                                                              POPULATION_LIST_PATH, MEDICAL_LIST_PATH,
                                                              MEDICAL_REVIEWS_PATH, ABROAD_LIST_PATH,
                                                              OVERRIDE_LIST_PATH])
    provenance.invalidate(provenance.INSTITUTION_MANIFEST)
    dim_institution = build_dim_institution()
    links = build_id_links(dim_institution)
    links.to_parquet(LINKS_PATH, index=False)
    print(f"  Saved to: {LINKS_PATH}")
    dim_offense = build_dim_offense()
    build_institution_classes()
    build_medical_campuses(dim_institution)
    check_medical_reviews(dim_institution)
    build_campuses_abroad(dim_institution)
    build_shared_campus_overrides(dim_institution)
    provenance.write_institution_manifest(
        inputs_before, outputs=[dims / "dim_institution.parquet", dims / "dim_offense.parquet", LINKS_PATH,
                                CLASS_PATH, MEDICAL_PATH, ABROAD_PATH, OVERRIDE_PATH],
        other_inputs=other_inputs)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Institutions: {len(dim_institution)}")
    print(f"Offenses: {len(dim_offense)}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 04_create_aggregates.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("03", main))
