"""
Create pre-aggregated tables for fast UI queries.

This script creates aggregate tables that power the dashboard:
- agg_school_year_offense: Summary by school, year, offense, geography (every
  school's full DOE figures, as its profile shows them)
- shared_blocks: statistics that DOE reports identically for two or more
  campuses (see find_shared_blocks), and the one campus they are counted under
- agg_ivy_rankings, agg_state_rankings, agg_national_rankings: campus rankings
  by count, by year/offense/geography, in which shared statistics are counted once
- agg_campus_year: every campus-year that counts in rankings and rates
  (reported, and not entirely figures counted under another campus), with
  its count, 0 included: such a campus-year is ranked with 0 for every
  offense it had none of
- agg_institution_year, agg_institution_year_offense: the institutions rates
  are calculated for (all campuses of a base UNITID, per its FTE)

Usage:
    python 04_create_aggregates.py
    python 04_create_aggregates.py --ivy-only
"""

from collections import defaultdict
from fractions import Fraction
import math
import os
import sys
import argparse
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, IVY_LEAGUE, GEO_FOR_ALL, US_STATES, PROCESS_ALL_SCHOOLS, OFFENSE_ORDER,
                    SHARED_MIN_NONZERO, MIN_FTE_FOR_RATE, ONLINE_SHARE_YEAR, HOSPITAL_CODE, MEDICAL_CARNEGIE,
                    MEDICAL_CARNEGIE_LABELS, ONLINE_UNCERTAIN_RATIO, SIZE_SETTING_FIELDS, SHARED_SITE_MAX_SHARE,
                    SHARED_NEAR_MIN_NONZERO, SHARED_NEAR_MATCH, SHARED_NEAR_MIN_TOTAL, peer_type)
import provenance

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"
# The DOE release each campus-year was taken from (02_transform_to_parquet.py)
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"
# The pairs of DOE IDs of one campus (03_build_dimensions.py, from etl/reference/campus_id_changes.csv)
LINKS_PATH = CURATED_DIR / "dims" / "campus_id_links.parquet"
# Every campus's counts in the older releases campus-years are taken from (02)
OLDER_PATH = CURATED_DIR / "dims" / "older_release_counts.parquet"
# Statistics reported identically by two or more campuses (find_shared_blocks)
SHARED_PATH = CURATED_DIR / "aggs" / "shared_blocks.parquet"
# IPEDS hospital and Carnegie fields, and the reviewed list (03_build_dimensions.py)
CLASS_PATH = CURATED_DIR / "dims" / "dim_institution_class.parquet"
# Campuses that are medical centers or hospitals (03_build_dimensions.py, etl/reference/medical_campuses.csv)
MEDICAL_PATH = CURATED_DIR / "dims" / "dim_medical_campus.parquet"
# Campuses abroad that DOE gives a state (03's reviewed list)
ABROAD_PATH = CURATED_DIR / "dims" / "dim_campus_abroad.parquet"
# Campuses whose reported figures are another institution's campus figures
# (03's reviewed list, etl/reference/shared_campus_overrides.csv)
OVERRIDE_PATH = CURATED_DIR / "dims" / "dim_shared_campus_override.parquet"
# Reviewed student figures of shared sites (03's list, etl/reference/shared_site_enrollment.csv)
SITE_ENROLLMENT_PATH = CURATED_DIR / "dims" / "dim_shared_site_enrollment.parquet"
# The shared sites of the rates and the near-copies among them (classify_shared_sites, find_near_copies)
SITES_PATH = CURATED_DIR / "aggs" / "shared_sites.parquet"
NEAR_PATH = CURATED_DIR / "aggs" / "near_copies.parquet"

# Shared (copied) statistics. Some DOE rows repeat another campus's numbers:
# a medical school's sites report their university's main campus figures, a
# divinity or law school its university's, several institutions on one
# shared campus the same figures, and a renumbered campus appears under its
# old and new UNITID. Added up, those numbers would be counted twice in state
# and national totals and ranked as separate schools.
#
# A block is one campus's figures for one year and one geography of
# GEO_FOR_ALL (residence halls are a subset of on-campus and are not
# compared): its 20 cells, one per offense in OFFENSE_ORDER (11 criminal, 3
# VAWA, 3 arrest, 3 disciplinary), a blank cell counting as 0. A campus-year's
# whole figures are its three blocks (60 cells). Copies are looked for only
# between campuses in the same state, and need at least SHARED_MIN_NONZERO
# (config.py) cells that are not 0: fewer match by chance too often to call
# a copy. find_shared_blocks lists the rules (SHARED_RULES).
SHARED_RULES = ("same_block", "whole_year", "whole_year_older_release", "block_older_release", "renumbered")


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


def load_school_agg() -> pd.DataFrame:
    """The school-year-offense aggregate this step writes first."""
    agg_path = CURATED_DIR / "aggs" / "agg_school_year_offense.parquet"
    if not agg_path.is_file():
        raise RuntimeError(f"{agg_path} not found. Run 04_create_aggregates.py again.")
    return pd.read_parquet(agg_path)


def load_enrollment_data() -> pd.DataFrame:
    """
    Load enrollment data with FTE for rate calculations.
    Returns DataFrame with unitid, year, fte columns.
    """
    enrollment_path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    if not enrollment_path.is_file():
        raise RuntimeError(
            f"{enrollment_path} not found, so no rates can be calculated. "
            f"Run 01b_download_ipeds.py, 02b_transform_ef_enrollment.py and "
            f"02a_transform_enrollment.py first."
        )

    df = pd.read_parquet(enrollment_path)
    # A repeated school-year would duplicate aggregate rows in the join
    dups = int(df.duplicated(["unitid", "year"]).sum())
    if dups:
        raise RuntimeError(
            f"{enrollment_path} has {dups} repeated school-year rows, which would double counts. "
            f"Run 02a_transform_enrollment.py again."
        )
    # Only need unitid, year, fte for joining
    return df[["unitid", "year", "fte"]]


def load_dim_institution() -> pd.DataFrame:
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")
    return pd.read_parquet(dims_path)


def create_school_year_offense_agg(ivy_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Aggregate: (year, unitid, offense, geo) -> count, every school's full
    DOE figures (the school profiles show these). Saved as
    agg_school_year_offense.parquet.

    Returns (the aggregate, the fact rows it was built from).
    """
    print("Creating school-year-offense aggregate...")
    base = load_fact_rows(ivy_only)
    agg = build_school_agg(base, load_dim_institution(), load_enrollment_data())

    # Save
    agg_dir = CURATED_DIR / "aggs"
    agg_dir.mkdir(parents=True, exist_ok=True)

    output_path = agg_dir / "agg_school_year_offense.parquet"
    agg.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    return agg, base


def load_fact_rows(ivy_only: bool = False) -> pd.DataFrame:
    """(year, unitid, offense, offense_family, geo) -> count, from the fact table."""
    con = duckdb.connect()
    facts_file = get_facts_path()

    # Base aggregation query
    query = f"""
    SELECT
        f.year,
        f.unitid,
        f.offense,
        f.offense_family,
        f.geo,
        SUM(f.count) as count
    FROM read_parquet('{facts_file}') f
    """

    if ivy_only:
        ivy_list = ", ".join(str(u) for u in IVY_LEAGUE.keys())
        query += f" WHERE f.unitid IN ({ivy_list})"

    query += """
    GROUP BY f.year, f.unitid, f.offense, f.offense_family, f.geo
    ORDER BY f.year, f.unitid, f.offense, f.geo
    """

    try:
        agg = con.execute(query).df()
    except duckdb.Error as e:
        raise facts_read_error(e) from e
    print(f"  Base aggregation: {len(agg):,} records")
    return agg


def build_school_agg(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame) -> pd.DataFrame:
    """
    The school-year-offense aggregate of the fact rows `base` (load_fact_rows).

    Also creates an "All" geography that sums On-campus + Non-campus + Public property
    (excluding Residence halls to avoid double-counting).

    Schema:
        year: int16
        unitid: int32
        institution_name: string     # Denormalized for convenience
        offense: string
        offense_family: string
        geo: string
        count: int32
        fte: int32                   # FTE enrollment (may be null)
        rate_per_10k: float          # Rate per 10,000 FTE students (may be null)
    """
    agg = base.copy()

    # Add institution names from dimension
    name_map = dim_inst.set_index("unitid")["institution_name"].to_dict()
    agg["institution_name"] = agg["unitid"].map(name_map)

    # Create "All" geography aggregation
    # Sum On-campus + Non-campus + Public property (not Residence halls)
    geo_filter = agg["geo"].isin(GEO_FOR_ALL)
    all_geo = agg[geo_filter].copy()
    all_geo["geo"] = "All"

    # groupby drops rows with an empty key, which would lose their counts
    group_keys = ["year", "unitid", "institution_name", "offense", "offense_family", "geo"]
    no_key = all_geo[all_geo[group_keys].isna().any(axis=1)]
    if len(no_key) > 0:
        cols = [c for c in group_keys if all_geo[c].isna().any()]
        raise RuntimeError(
            f"{len(no_key):,} aggregate rows have no {', '.join(cols)} "
            f"(UNITIDs {sorted(no_key['unitid'].unique().tolist())[:10]}). "
            f"Run 02_transform_to_parquet.py and 03_build_dimensions.py again, then this step."
        )

    all_geo_agg = all_geo.groupby(group_keys, as_index=False)["count"].sum()

    # Combine with original
    agg = pd.concat([agg, all_geo_agg], ignore_index=True)

    # Join enrollment data for FTE and rate calculations
    # Note: Crime data uses extended UNITID format (UNITID * 1000 + branch)
    # IPEDS uses base UNITID, so we need to extract base UNITID for joining
    print(f"  Joining enrollment data ({len(enrollment):,} records)...")
    # Extract base UNITID from extended format
    agg["base_unitid"] = (agg["unitid"] // 1000).astype("int32")
    # Join on base_unitid and year
    agg = agg.merge(enrollment, left_on=["base_unitid", "year"], right_on=["unitid", "year"], how="left", suffixes=("", "_enroll"))
    # Drop the duplicate unitid column from enrollment
    agg = agg.drop(columns=["unitid_enroll"], errors="ignore")
    agg = agg.drop(columns=["base_unitid"])
    # Calculate rate per 10,000 FTE students
    agg["rate_per_10k"] = (agg["count"] / agg["fte"] * 10000).round(2)
    # Handle division by zero or missing FTE
    agg.loc[agg["fte"].isna() | (agg["fte"] == 0), "rate_per_10k"] = None
    matched = agg["fte"].notna().sum()
    print(f"  Matched enrollment: {matched:,} / {len(agg):,} records ({matched/len(agg)*100:.1f}%)")

    # Ensure proper types
    agg["year"] = agg["year"].astype("int16")
    agg["unitid"] = agg["unitid"].astype("int32")
    agg["count"] = agg["count"].astype("int32")
    # FTE may have nulls, so use nullable int
    agg["fte"] = agg["fte"].astype("Int32")

    # Sort
    agg = agg.sort_values(["year", "unitid", "offense", "geo"]).reset_index(drop=True)

    print(f"  With 'All' geography: {len(agg):,} records")

    return agg


def load_campus_year_sources() -> pd.DataFrame:
    if not SOURCES_PATH.is_file():
        raise RuntimeError(f"{SOURCES_PATH} not found. Run 02_transform_to_parquet.py first.")
    return pd.read_parquet(SOURCES_PATH)


def load_id_links() -> list[tuple[int, int]]:
    """The (old, new) UNITID pairs DOE used for one campus (03's campus_id_links, relation "later")."""
    links = pd.read_parquet(LINKS_PATH)
    later = links[links["relation"] == "later"]
    return [(int(u), int(o)) for u, o in zip(later["unitid"].tolist(), later["other_unitid"].tolist())]


def merger_rate_rules(sources: pd.DataFrame, counting: set[tuple[int, int]], fte_of: dict[tuple[int, int], int],
                      active: set[tuple[int, int]]
                      ) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], set[int]]]:
    """
    The rate rules for a campus DOE reported under two institutions in one
    year (a "link" pair of different base UNITIDs that both report the year:
    a merger or renumbering, where DOE's newest release re-reports a
    predecessor's campus under the successor while the predecessor's own rows
    remain). Returns ({(year, base): reason} with no rate,
    {(year, base): {bases whose FTE its rate adds}}).

    `counting` holds the (unitid, year) campus-years that count (not all
    shadow blocks), `fte_of` the IPEDS FTE per (base, year), `active` the
    campus-years DOE published at least one incident for (any category,
    shadow blocks included).

    For each such pair and year, the institution whose IPEDS FTE holds the
    campus's students ("students' institution") is:
      - the only one of the two with an FTE that year;
      - when both have one: the one that reported that year only campuses
        linked to campuses of the other (its FTE is those campuses'
        students); when neither or both did, it cannot be told.
    Neither with an FTE: no rate for either, nothing to decide.

    Then:
      - students' institution unknown: both are left out that year;
      - the other institution counts the campus's figures (its copy is not a
        shadow): when the students' institution counts no campus at all that
        year (all its figures count under the other) and the other has an FTE,
        the other's rate adds the students' institution's FTE (both
        institutions' students over both institutions' incidents); otherwise
        the other is left out (incidents without their students);
      - the students' institution does not count the campus (its copy is a
        shadow) but counts other campuses: it is left out (students without
        their incidents).
    A students' institution whose FTE would be added to two or more
    institutions is split: those are left out instead. Anything else (the
    students' institution counts the campus, the other does not) needs no rule,
    and neither does a campus with no incident under either ID that year: no
    numerator holds an incident of it, so every rate is the same whichever
    FTE holds its students.
    """
    years_of = defaultdict(set)
    reported = defaultdict(set)
    for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist()):
        years_of[int(u)].add(int(y))
        reported[(int(u) // 1000, int(y))].add(int(u))
    listed = {(u // 1000, y) for u, y in counting}
    pairs_by_year = defaultdict(list)
    for o, n in load_id_links():
        if o // 1000 != n // 1000:
            for y in sorted(years_of[o] & years_of[n]):
                pairs_by_year[y].append((o, n))

    excluded: dict[tuple[int, int], str] = {}
    adds: dict[tuple[int, int], set[int]] = defaultdict(set)  # (year, students' base) -> bases it is added to
    for y, pairs in sorted(pairs_by_year.items()):
        linked = defaultdict(set)  # (base, other base) -> its campuses linked to a campus of the other
        for o, n in pairs:
            linked[(o // 1000, n // 1000)].add(o)
            linked[(n // 1000, o // 1000)].add(n)
        for o, n in pairs:
            bo, bn = o // 1000, n // 1000
            has = {bo: (bo, y) in fte_of, bn: (bn, y) in fte_of}
            if not has[bo] and not has[bn]:
                continue
            # No incident under either ID: no numerator holds one of the campus
            quiet = (o, y) not in active and (n, y) not in active
            if has[bo] != has[bn]:
                s = bo if has[bo] else bn
            else:
                mirrored = [b for b, other in ((bo, bn), (bn, bo)) if reported[(b, y)] <= linked[(b, other)]]
                s = mirrored[0] if len(mirrored) == 1 else None
            if s is None:
                if quiet:
                    continue
                for here, there in ((o, n), (n, o)):
                    excluded.setdefault((y, here // 1000), (
                        f"In {y} DOE reported campus {here} of this institution also under ID {there} of "
                        "another institution (a merger or renumbering), and IPEDS has an FTE for both "
                        "institutions, so it cannot be told which FTE holds that campus's students. No rate is "
                        "shown for that year."))
                continue
            t = bn if s == bo else bo
            s_copy, t_copy = (o, n) if s == bo else (n, o)
            s_counts, t_counts = (s_copy, y) in counting, (t_copy, y) in counting
            if t_counts:
                if not s_counts and (s, y) not in listed and has[t]:
                    adds[(y, s)].add(t)
                elif has[t] and not quiet:
                    excluded.setdefault((y, t), (
                        f"In {y} the figures of campus {t_copy} count for this institution, but IPEDS counts "
                        f"that campus's students under institution {s} (DOE also reported it as {s_copy}: a "
                        "merger or renumbering), which counts other campuses of its own that year. No rate is "
                        "shown for that year."))
            if not s_counts and (s, y) in listed and not quiet:
                excluded.setdefault((y, s), (
                    f"In {y} DOE counted the figures of campus {s_copy} of this institution under ID {t_copy} of "
                    "another institution (a merger or renumbering), while IPEDS counts that campus's students in "
                    "this institution's FTE. No rate is shown for that year."))
    pooled: dict[tuple[int, int], set[int]] = defaultdict(set)
    for (y, s), targets in sorted(adds.items()):
        if len(targets) == 1:
            pooled[(y, next(iter(targets)))].add(s)
            continue
        for t in sorted(targets):
            excluded.setdefault((y, t), (
                f"In {y} DOE reported the campuses of institution {s} under this institution and under others "
                "(a merger or renumbering), so its students cannot be divided among them. No rate is shown for "
                "that year."))
    return excluded, {k: v for k, v in pooled.items() if k not in excluded}


def shared_rate_rules(shared: pd.DataFrame, counting: set[tuple[int, int]], fte_of: dict[tuple[int, int], int]
                      ) -> tuple[dict[tuple[int, int], set[int]], list[tuple[int, str, int, int, bool]]]:
    """
    The rate rules for figures DOE published identically for campuses of two
    institutions in one year (a shared campus: a shadow block whose host
    campus has another base UNITID, other than two IDs of one campus, which
    merger_rate_rules handles). The figures count once, under the host, but
    the students on that campus are in each institution's own FTE. Returns
    ({(year, base): {bases whose FTE its rate adds}}, [(year, geo, shadow
    campus, host campus, whether the shadow's institution counts campuses of
    its own that year)] of the shared blocks whose figures are in one
    institution's numerator and whose students are partly in another's FTE).

    Per year and shadow institution (the one whose campus copies the host's
    figures):
      - it counts no campus that year (all its figures count under one host
        institution) and has an FTE: the host institution's rate adds its
        FTE (both institutions' students over the incidents of both);
      - it counts no campus and has no IPEDS FTE: nothing to add, the host
        keeps its rate;
      - otherwise (it counts campuses of its own, or its figures count under
        two or more host institutions): its blocks are listed, for the
        shared figures of all geographies (shared_in, shared_out).
    The rates of institutions that share an on-campus site follow
    classify_shared_sites, which can take a pooled institution back out.
    """
    linked = {frozenset(p) for p in load_id_links()}
    listed = {(u // 1000, y) for u, y in counting}
    shadows = shared[shared["role"] == "shadow"]
    hosts = defaultdict(set)
    blocks = defaultdict(list)
    for y, g, u, h in zip(shadows["year"].tolist(), shadows["geo"].tolist(), shadows["unitid"].tolist(),
                          shadows["host_unitid"].tolist()):
        y, u, h = int(y), int(u), int(h)
        if u // 1000 == h // 1000 or frozenset((u, h)) in linked:
            continue
        hosts[(y, u // 1000)].add(h // 1000)
        blocks[(y, u // 1000)].append((y, str(g), u, h))
    pooled: dict[tuple[int, int], set[int]] = defaultdict(set)
    partial = []
    for (y, a), host_bases in sorted(hosts.items()):
        if (a, y) not in listed and len(host_bases) == 1:
            if (a, y) in fte_of:
                pooled[(y, next(iter(host_bases)))].add(a)
            continue
        partial += [(*block, (a, y) in listed) for block in sorted(blocks[(y, a)])]
    return pooled, partial


def find_near_copies(cells_on: dict, state_of: dict, linked: set) -> list[tuple]:
    """
    Near-copies (config.py, SHARED_NEAR_*): per year, two counting campuses
    in the United States of different institutions (not two IDs of one
    campus) whose on-campus cells (OFFENSE_ORDER, shadow blocks left out)
    nearly agree. The campus with the smaller total (ties: the lower UNITID)
    has at least SHARED_NEAR_MIN_NONZERO nonzero cells and a total of at
    least SHARED_NEAR_MIN_TOTAL, and at least SHARED_NEAR_MATCH of its
    nonzero cells equal the other's; the two campuses are in one state, or
    every cell is equal. cells_on: {(year, unitid): {offense: count above
    0}}. Returns [(year, smaller campus, other campus, cells equal, nonzero
    cells, smaller total, other total)].
    """
    num, den = SHARED_NEAR_MATCH
    holders = defaultdict(set)  # (year, offense, count) -> campuses with that cell
    for (y, u), d in cells_on.items():
        for o, c in d.items():
            holders[(y, o, c)].add(u)
    found = set()
    for (y, a), d in cells_on.items():
        k, ta = len(d), sum(d.values())
        if k < SHARED_NEAR_MIN_NONZERO or ta < SHARED_NEAR_MIN_TOTAL:
            continue
        need = -(-k * num // den)
        # A campus with `need` of a's cells equal has one of any k - need + 1 of them
        probe = sorted(d.items(), key=lambda oc: (len(holders[(y, oc[0], oc[1])]), oc[0]))[:k - need + 1]
        for b in set().union(*(holders[(y, o, c)] for o, c in probe)):
            if b // 1000 == a // 1000 or frozenset((a, b)) in linked:
                continue
            e = cells_on[(y, b)]
            tb = sum(e.values())
            if (ta, a) > (tb, b):
                continue
            equal = sum(1 for o, c in d.items() if e.get(o) == c)
            if equal * den < k * num:
                continue
            same_state = state_of.get(a) is not None and state_of.get(a) == state_of.get(b)
            if not same_state and d != e:
                continue
            found.add((y, a, b, equal, k, ta, tb))
    return sorted(found)


def classify_shared_sites(edges: dict, counting: set, listed: set, oncampus_of: dict, pooled_today: dict,
                          on_cells: dict, on_shadow_host: dict, base_name: dict) -> dict:
    """
    The shared sites of the rates (config.py, "Shared sites"). edges: {year:
    {(campus, campus, kind)}}, kind exact, near or override; counting:
    {(unitid, year)} of the counting campus-years; listed: {(year, base)} of
    the institution-years (a counting campus); oncampus_of: {(base, year):
    on-campus FTE}; pooled_today: shared_rate_rules's {(year, host base):
    {bases}}; on_cells: {(year, unitid): {offense: count above 0}} of the
    counted on-campus figures; on_shadow_host: {(year, unitid): host campus}
    of the on-campus shadow blocks; base_name: {base: name}.

    Per year, a site is a connected group of campuses of two or more
    institutions. Its parties are the institutions listed that year (one
    with no counting campus is pooled with its host by shared_rate_rules, or
    has no rate at all). When two or more parties have their main campus
    (UNITID ending in 001) at the site, the owner is the party with the
    largest on-campus FTE (ties: the lower base): when every other
    institution there counts no campus outside the site that year, or their
    on-campus FTE together is at most SHARED_SITE_MAX_SHARE of the owner's,
    the owner's rate adds their on-campus FTE (those with one) and the other
    parties are left out by rule shared_pooled; otherwise every party is
    left out by rule shared_campus. With one party, the site is pooled as
    before. With one party's main campus, that party owns the site (its
    counted on-campus figures there are its shared in) and the other parties
    are guests; with none, every party is a participant of a shared center.
    A guest's or participant's campuses at the site, and a shared_pooled
    party's, are in none of its rates: their counted figures leave the rate
    geographies (rate_out), and a guest's or participant's on-campus figures
    there (its counted ones, or the host's of a shadow block) are its shared
    out.

    Returns {"rows": [shared_sites rows], "rate_out": {(unitid, year)},
    "excluded": {(year, base): (rule, text)}, "pool_add": {(year, owner):
    {bases}}, "pool_remove": {(year, base)} (taken out of pooled_today),
    "out_sites", "out_with", "in_with", "co_located": {(year, base): set},
    "in_on", "out_on": {(year, base, offense): count}, "warnings": [text]}.
    co_located: the owner of a pooled site with several main campuses gets
    every other institution there; an institution that shared_rate_rules
    pools at a site of another class is co-located with its host.
    """
    num, den = SHARED_SITE_MAX_SHARE
    out = {"rows": [], "rate_out": set(), "excluded": {}, "pool_add": defaultdict(set), "pool_remove": set(),
           "out_sites": defaultdict(set), "out_with": defaultdict(set), "in_with": defaultdict(set),
           "co_located": defaultdict(set), "in_on": defaultdict(int), "out_on": defaultdict(int), "warnings": []}
    counting_of = defaultdict(set)
    for u, y in counting:
        counting_of[(y, u // 1000)].add(u)
    pooled_into = {(y, s): h for (y, h), ss in pooled_today.items() for s in ss}

    def names(bases):
        n = [base_name.get(b, str(b)) for b in sorted(bases, key=lambda b: (base_name.get(b, str(b)), b))]
        return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]

    def site_figures(y, u):
        """A campus's on-campus figures at the site: its counted ones, or its shadow block's host's."""
        if (y, u) in on_shadow_host:
            return on_cells.get((y, on_shadow_host[(y, u)]), {})
        return on_cells.get((y, u), {})

    def leave_rates(y, b, campuses, shared_out):
        for u in campuses:
            if (u, y) in counting:
                out["rate_out"].add((u, y))
            if shared_out:
                for o, c in site_figures(y, u).items():
                    out["out_on"][(y, b, o)] += c

    for y in sorted(edges):
        adj = defaultdict(set)
        kinds = defaultdict(set)
        for a, b, k in edges[y]:
            adj[a].add(b)
            adj[b].add(a)
            kinds[a].add(k)
            kinds[b].add(k)
        seen = set()
        for start in sorted(adj):
            if start in seen:
                continue
            comp, stack = set(), [start]
            while stack:
                x = stack.pop()
                if x not in comp:
                    comp.add(x)
                    stack.extend(adj[x] - comp)
            seen |= comp
            bases = sorted({u // 1000 for u in comp})
            if len(bases) < 2:
                continue
            at = {b: sorted(u for u in comp if u // 1000 == b) for b in bases}
            parties = [b for b in bases if (y, b) in listed]
            role = {b: ("pooled" if pooled_into.get((y, b)) in bases else "no_campus")
                    for b in bases if b not in parties}
            mains = [b for b in parties if b * 1000 + 1 in comp]
            owner = None
            if len(mains) >= 2:
                owner = max(parties, key=lambda b: (oncampus_of.get((b, y), -1), -b))
                others = [b for b in bases if b != owner]
                whole = all(not (counting_of[(y, b)] - comp) for b in others)
                own_fte = oncampus_of.get((owner, y))
                theirs = sum(oncampus_of.get((b, y), 0) for b in others)
                out["pool_remove"] |= {(y, b) for b in bases}
                if not any(u for u in at[owner] if (y, u) in on_cells):
                    out["warnings"].append(f"{y}: owner {owner} of site {sorted(comp)} has no counted on-campus "
                                           "figures there")
                if whole or (own_fte is not None and theirs * den <= own_fte * num):
                    cls = "several_main_pooled"
                    role = {owner: "owner"} | {b: "pooled" for b in others}
                    out["pool_add"][(y, owner)] |= {b for b in others if (b, y) in oncampus_of}
                    out["co_located"][(y, owner)] |= set(others)
                    for b in others:
                        if b in parties:
                            out["excluded"][(y, b)] = ("shared_pooled", (
                                f"Its main campus is shared with {names([owner])}, whose rate includes this "
                                "institution's students and the campus's incidents. No separate rate is shown "
                                "for that year."))
                        leave_rates(y, b, at[b], False)
                else:
                    cls = "several_main_unassigned"
                    role |= {b: "unassigned" for b in parties}
                    for b in parties:
                        out["excluded"][(y, b)] = ("shared_campus", (
                            f"Its main campus is shared with {names([x for x in bases if x != b])}; the reported "
                            "incidents cannot be assigned to one institution's students. No rate is shown for "
                            "that year."))
            elif len(parties) <= 1:
                cls = "pooled"
                owner = parties[0] if parties else None
                if owner is not None:
                    role[owner] = "owner"
            else:
                if mains:
                    cls = "one_main"
                    owner = mains[0]
                    role[owner] = "owner"
                    counted = [u for u in at[owner] if (y, u) in on_cells]
                    if not counted:
                        out["warnings"].append(f"{y}: owner {owner} of site {sorted(comp)} has no counted "
                                               "on-campus figures there")
                    for u in counted:
                        for o, c in on_cells[(y, u)].items():
                            out["in_on"][(y, owner, o)] += c
                    out["in_with"][(y, owner)] |= set(parties) - {owner}
                    sharers = [b for b in parties if b != owner]
                else:
                    cls = "no_main"
                    sharers = list(parties)
                for b in sharers:
                    role[b] = "guest" if owner is not None else "participant"
                    out["out_sites"][(y, b)] |= set(at[b])
                    out["out_with"][(y, b)] |= ({owner} if owner is not None else set(parties) - {b})
                    leave_rates(y, b, at[b], True)
            if cls in ("pooled", "one_main", "no_main"):
                for b, r in role.items():
                    if r == "pooled":
                        out["co_located"][(y, pooled_into[(y, b)])].add(b)
            site = min(comp)
            for u in sorted(comp):
                b = u // 1000
                out["rows"].append({"year": y, "site": site, "unitid": u, "base_unitid": b, "site_class": cls,
                                    "owner_base": owner, "role": role.get(b), "links": " ".join(sorted(kinds[u]))})
    return out


def oncampus_estimates(fte: int, pct: int | None, heads: tuple, level: tuple | None
                       ) -> tuple[Fraction, Fraction | None]:
    """
    The two on-campus FTE estimates of config.py, exactly: (a) fte x (100 -
    pct) / 100 and (b) part-time first, None when the headcounts `heads`
    (total, full-time, part-time) do not add up or put FTE outside [FT,
    total]. `level` is (UG, UG full-time, graduate, graduate full-time, UG
    share, graduate share) for (b) by level, or None for the totals. Without
    a share both are the FTE; with a share of 0 both are the FTE.
    """
    if pct is None or pct == 0:
        return Fraction(fte), Fraction(fte)
    a = Fraction(fte * (100 - pct), 100)
    total, ft, pt = heads
    if total is None or ft is None or pt is None or total <= 0 or ft + pt != total or not ft <= fte <= total:
        return a, None
    factor = Fraction(fte - ft, pt) if pt else Fraction(0)
    if level is None:
        on = Fraction(total * (100 - pct), 100)
        ft_on = min(Fraction(ft), on)
    else:
        ug, ug_ft, grad, grad_ft, pcu, pcg = level
        on_ug, on_grad = Fraction(ug * (100 - pcu), 100), Fraction(grad * (100 - pcg), 100)
        on = on_ug + on_grad
        ft_on = min(Fraction(ug_ft), on_ug) + min(Fraction(grad_ft), on_grad)
    return a, ft_on + (on - ft_on) * factor


def level_figures(rec: dict) -> tuple | None:
    """
    (UG, UG full-time, graduate, graduate full-time, UG share, graduate
    share) of a dim_enrollment row when DRVEF has them and they add up to its
    totals (a level without students counts a share of 0), else None.
    """
    vals = [rec.get(c) for c in ("enrollment_ug", "enrollment_ug_ft", "enrollment_grad", "enrollment_grad_ft")]
    if any(v is None or pd.isna(v) for v in vals):
        return None
    ug, ug_ft, grad, grad_ft = (int(v) for v in vals)
    shares = []
    for heads, col in ((ug, "pcudeexc"), (grad, "pcgdeexc")):
        p = rec.get(col)
        if p is None or pd.isna(p):
            if heads:
                return None
            p = 0
        shares.append(int(p))
    total, ft = rec.get("enrollment_total"), rec.get("enrollment_ft")
    if pd.isna(total) or pd.isna(ft) or ug + grad != int(total) or ug_ft + grad_ft != int(ft) \
            or ug_ft > ug or grad_ft > grad:
        return None
    return ug, ug_ft, grad, grad_ft, shares[0], shares[1]


def half_up(x: Fraction) -> int:
    """x rounded half up to a whole number."""
    return math.floor(x + Fraction(1, 2))


def population_class_rules(classes: pd.DataFrame) -> dict[tuple[int, int], tuple[str, str]]:
    """
    {(year, base): (rule, reason)} for the institution-years whose campus
    population students do not measure (config.py, HOSPITAL_CODE and
    MEDICAL_CARNEGIE; 03's dim_institution_class): IPEDS HD says the
    institution has a hospital, its Carnegie basic classification is a
    special-focus medical school or center or a special-focus research
    institution (MEDICAL_CARNEGIE), or it is listed in
    etl/reference/rate_population_exclusions.csv.
    """
    out = {}
    for rec in classes.to_dict("records"):
        key = (int(rec["year"]), int(rec["unitid"]))
        hospital, field, basic = rec["hospital"], rec["carnegie_field"], rec["carnegie_basic"]
        if pd.notna(hospital) and int(hospital) == HOSPITAL_CODE:
            out[key] = ("hospital", (
                f"IPEDS reports that this institution has a hospital (institutional characteristics, {key[0]}). "
                "Patients, visitors and hospital staff are on its campus but not in its FTE, so a rate per "
                "student would not measure its campus population. It has no rate; its counts are "
                "shown."))
        elif pd.notna(field) and pd.notna(basic) and int(basic) in MEDICAL_CARNEGIE.get(str(field), ()):
            label = MEDICAL_CARNEGIE_LABELS[(str(field), int(basic))]
            out[key] = ("medical", (
                f"Its Carnegie basic classification in IPEDS for {key[0]} is \"{label}\" ({field} {int(basic)}). "
                "Such an institution's campus holds medical or research facilities whose staff, researchers and "
                "patients are not in its FTE, so a rate per student would not measure its campus population. It has "
                "no rate; its counts are shown."))
        elif pd.notna(rec["listed_reason"]):
            out[key] = ("listed", (
                f"{rec['listed_reason']} So a rate per student would not measure its campus population. It has no "
                f"rate; its counts are shown. Source: {rec['listed_source']}"))
    return out


def merger_families() -> dict[int, int]:
    """
    {base UNITID: family} for the institutions joined by "link" pairs of
    different base UNITIDs (mergers and renumberings), family = the lowest
    base UNITID of the connected group.
    """
    parent: dict[int, int] = {}

    def root(b: int) -> int:
        while parent.setdefault(b, b) != b:
            b = parent[b]
        return b

    for o, n in load_id_links():
        if o // 1000 != n // 1000:
            a, b = root(o // 1000), root(n // 1000)
            parent[max(a, b)] = min(a, b)
    return {b: root(b) for b in list(parent)}


def split_family_exclusions(inst_year: pd.DataFrame, sources: pd.DataFrame, counting: set[tuple[int, int]],
                            active: set[tuple[int, int]]) -> dict[tuple[int, int], str]:
    """
    {(year, base_unitid): reason} for the other case where the incidents and
    the FTE may not cover the same campuses: in a year when a merger family's
    campuses count under two or more institutions and one of those has no
    IPEDS FTE (IPEDS reports its students under another UNITID of the
    family) while it counts a campus with at least one incident that year
    (`active`) whose figures are not also counted, under a linked ID
    reporting that year, by a member with an FTE, every institution of the
    family has no rate that year. (A campus counted under
    both IDs is in the numerator of the member whose FTE holds its students,
    and a campus without incidents adds nothing to any numerator, so neither
    needs the rule.)
    """
    family = merger_families()
    years_of = defaultdict(set)
    for u, y in zip(sources["unitid"].tolist(), sources["year"].tolist()):
        years_of[int(u)].add(int(y))
    partners = defaultdict(set)  # (campus, year) -> its linked IDs of another base reporting that year
    for o, n in load_id_links():
        if o // 1000 != n // 1000:
            for y in years_of[o] & years_of[n]:
                partners[(o, y)].add(n)
                partners[(n, y)].add(o)
    by_base = defaultdict(set)
    for u, y in counting:
        by_base[(u // 1000, y)].add(u)
    rows = inst_year[inst_year["base_unitid"].isin(family)]
    out: dict[tuple[int, int], str] = {}
    for (fam, y), g in rows.groupby([rows["base_unitid"].map(family), "year"]):
        if len(g) < 2 or not g["fte"].isna().any():
            continue
        with_fte = set(g.loc[g["fte"].notna(), "base_unitid"].astype(int).tolist())
        loose = [c for b in g.loc[g["fte"].isna(), "base_unitid"].astype(int).tolist() for c in by_base[(b, int(y))]
                 if (c, int(y)) in active
                 and not any(p // 1000 in with_fte and (p, int(y)) in counting for p in partners[(c, int(y))])]
        if not loose:
            continue
        without = ", ".join(str(int(b)) for b in sorted(g.loc[g["fte"].isna(), "base_unitid"]))
        for b in g["base_unitid"]:
            out[(int(y), int(b))] = (
                f"In {int(y)} DOE reported campuses of this institution and of related institutions (a merger "
                f"or renumbering) under separate IDs, while IPEDS has no enrollment for {without}, so that "
                "year's incidents and enrollment may not cover the same campuses. No rate is shown for it.")
    return out


def load_older_release_counts() -> pd.DataFrame:
    if not OLDER_PATH.is_file():
        raise RuntimeError(f"{OLDER_PATH} not found. Run 02_transform_to_parquet.py first.")
    return pd.read_parquet(OLDER_PATH)


def block_cells(rows: pd.DataFrame, keys: list) -> dict:
    """{(*keys, geo): its 20 cells in OFFENSE_ORDER} for count rows of GEO_FOR_ALL (a blank cell is 0)."""
    unknown = sorted(set(rows["offense"]) - set(OFFENSE_ORDER))
    if unknown:
        raise RuntimeError(f"Counts of offenses not in OFFENSE_ORDER ({', '.join(unknown)}) cannot be compared "
                           "cell by cell. Add them to OFFENSE_ORDER in config.py, then run 04 again.")
    cell_of = {o: i for i, o in enumerate(OFFENSE_ORDER)}
    rows = rows[rows["geo"].isin(GEO_FOR_ALL)]
    cells = {}
    columns = [rows[k].tolist() for k in keys] + [rows["geo"].tolist(), rows["offense"].tolist(),
                                                   rows["count"].tolist()]
    for *key, offense, count in zip(*columns):
        cells.setdefault(tuple(key), [0] * len(OFFENSE_ORDER))[cell_of[offense]] += int(count)
    return {key: tuple(v) for key, v in cells.items()}


def nonzero(cells: tuple) -> int:
    return sum(1 for c in cells if c != 0)


def find_shared_blocks(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame,
                       sources: pd.DataFrame, older: pd.DataFrame,
                       links: list[tuple[int, int]] = ()) -> pd.DataFrame:
    """
    The blocks counted under another campus (shadows), and the campuses they
    are counted under (hosts). Copies are looked for only between campuses
    in the same state of US_STATES (the campuses state and national rankings
    count; nothing of any other campus is counted twice), and each test needs
    at least SHARED_MIN_NONZERO cells that are not 0. The rules, in order; a
    block a rule makes a shadow keeps that host, and the blocks of a
    same_block group keep the role that rule gives them:

      same_block: two or more campuses' blocks of the same year and
        geography, all 20 cells equal. One is the host (first by the order
        below), the others are its shadows.
      whole_year: two or more campus-years of the same year whose whole
        figures (60 cells) are equal. One is the host (same order); every
        block of the others is a shadow of it, also blocks with fewer than
        SHARED_MIN_NONZERO nonzero cells.
      whole_year_older_release: a campus-year taken from an older release
        (campus_year_sources: restored) whose whole figures in that release
        equal another campus's there, a campus whose own figures for the
        year now come from a newer release. Every block of it is a shadow of
        that campus (the first by the order below if there are several).
      block_older_release: the same for one block of such a campus-year.
      renumbered: one campus that DOE lists under two IDs (`links`: the
        "link" pairs of etl/reference/campus_id_changes.csv, from 03's
        campus_id_links), both reporting the same year with equal whole
        figures (60 cells; any number of nonzero cells, at least one): the
        campus-year taken from the older release is a shadow of the other.
        The two IDs are never in the same release, so no rule above can
        compare them.

    The first campus by this order is the host:
      1. its campus-year is taken from the newest DOE release that covers
         the year, not restored from an older one (campus_year_sources),
      2. it is a main campus (UNITID_P ending in 001),
      3. larger FTE that year (the FTE rates use; no FTE sorts last),
      4. larger total for the campus-year over GEO_FOR_ALL,
      5. lower UNITID_P.
    A host whose own block of that year and geography is itself a shadow
    passes its shadows on to its own host.

    Schema (one row per shadow block, and one per host block that is in the
    facts):
        year: int16, geo: string, state: string   # the block
        group: int32                 # one host's blocks of one year and geography
        unitid: int32
        role: string                 # "host" or "shadow"
        host_unitid: int32           # the campus the block is counted under
        rule: string                 # for a shadow, the rule above; null for a host
        group_size: int16            # rows in the group
        nonzero_cells: int16         # cells of the block that are not 0
        block_count: int32           # sum of the block's 20 cells
    """
    state = {int(u): s for u, s in zip(dim_inst["unitid"].tolist(), dim_inst["state"].tolist())}
    selected = block_cells(base, ["year", "unitid"])            # (year, unitid, geo) -> cells
    in_release = block_cells(older, ["release", "year", "unitid"])  # (release, year, unitid, geo) -> cells
    zero = (0,) * len(OFFENSE_ORDER)

    def whole(cells: dict, *campus_year) -> tuple:
        return sum((cells.get((*campus_year, g), zero) for g in GEO_FOR_ALL), ())

    def ranked(unitid: int) -> bool:
        return state.get(unitid) in US_STATES

    # What chooses the host
    release_of = {(int(u), int(y)): r for u, y, r in zip(sources["unitid"].tolist(), sources["year"].tolist(),
                                                         sources["release"].tolist())}
    restored = {(int(u), int(y)): bool(r) for u, y, r in zip(sources["unitid"].tolist(), sources["year"].tolist(),
                                                             sources["restored"].tolist())}
    fte = {(int(u), int(y)): float(f) for u, y, f in zip(enrollment["unitid"].tolist(), enrollment["year"].tolist(),
                                                         enrollment["fte"].tolist()) if pd.notna(f)}
    totals = {}
    for (y, u, _g), cells in selected.items():
        totals[(u, y)] = totals.get((u, y), 0) + sum(cells)

    def order(unitid: int, year: int) -> tuple:
        if (unitid, year) not in restored:
            raise RuntimeError(f"{SOURCES_PATH.name} has no release for campus {unitid} in {year}, which has "
                               "data. Run 02_transform_to_parquet.py again, then 03 and this step.")
        f = fte.get((unitid // 1000, year))
        return (restored[(unitid, year)], unitid % 1000 != 1, -f if f is not None else float("inf"),
                -totals.get((unitid, year), 0), unitid)

    def first(campuses, year: int) -> int:
        return min(campuses, key=lambda u: order(u, year))

    shadows = {}  # (year, geo, unitid) -> (host, rule)
    same_block = set()  # blocks of same_block groups, host or shadow: their roles are final

    def shadow_campus_year(year: int, unitid: int, host: int, rule: str) -> None:
        for g in GEO_FOR_ALL:
            block = (year, g, unitid)
            if (year, unitid, g) in selected and block not in same_block and block not in shadows:
                shadows[block] = (host, rule)

    # same_block (the selected figures)
    groups = {}
    for (y, u, g), cells in selected.items():
        if ranked(u) and nonzero(cells) >= SHARED_MIN_NONZERO:
            groups.setdefault((y, g, state[u], cells), []).append(u)
    for (y, g, _state, _cells), members in sorted(groups.items()):
        if len(members) >= 2:
            host = first(members, y)
            same_block.update((y, g, u) for u in members)
            shadows.update({(y, g, u): (host, "same_block") for u in members if u != host})

    # whole_year (the selected figures)
    groups = {}
    for y, u in sorted({(y, u) for (y, u, _g) in selected}):
        vector = whole(selected, y, u)
        if ranked(u) and nonzero(vector) >= SHARED_MIN_NONZERO:
            groups.setdefault((y, state[u], vector), []).append(u)
    for (y, _state, _vector), members in sorted(groups.items()):
        if len(members) >= 2:
            host = first(members, y)
            for u in members:
                if u != host:
                    shadow_campus_year(y, u, host, "whole_year")

    # The older releases, by whole figures and by block, for the two rules
    # below. Only campuses whose figures for the year now come from a newer
    # release are candidates: one whose figures come from the same release
    # has the same figures in the selected data, where the rules above
    # already compared them.
    whole_index, block_index = {}, {}
    for r, y, u in sorted({(r, y, u) for (r, y, u, _g) in in_release}):
        if not ranked(u) or int(release_of.get((u, y), r)) <= int(r):  # suffixes such as 212223 grow with time
            continue
        vector = whole(in_release, r, y, u)
        if nonzero(vector) >= SHARED_MIN_NONZERO:
            whole_index.setdefault((r, y, state[u], vector), []).append(u)
        for g in GEO_FOR_ALL:
            cells = in_release.get((r, y, u, g), zero)
            if nonzero(cells) >= SHARED_MIN_NONZERO:
                block_index.setdefault((r, y, g, state[u], cells), []).append(u)

    taken_older = sorted((y, u, r) for (u, y), r in release_of.items() if restored[(u, y)] and ranked(u))
    for y, u, r in taken_older:  # whole_year_older_release
        vector = whole(in_release, r, y, u)
        if vector != whole(selected, y, u):
            raise RuntimeError(f"Campus {u}'s {y} figures differ between the facts and {OLDER_PATH.name}, "
                               f"which should both hold release {r}'s. Run 02_transform_to_parquet.py again.")
        copied = whole_index.get((r, y, state[u], vector), []) if nonzero(vector) >= SHARED_MIN_NONZERO else []
        if copied:
            shadow_campus_year(y, u, first(copied, y), "whole_year_older_release")
    for y, u, r in taken_older:  # block_older_release
        for g in GEO_FOR_ALL:
            block = (y, g, u)
            cells = in_release.get((r, y, u, g), zero)
            if block in same_block or block in shadows or nonzero(cells) < SHARED_MIN_NONZERO:
                continue
            copied = block_index.get((r, y, g, state[u], cells), [])
            if copied:
                shadows[block] = (first(copied, y), "block_older_release")

    # renumbered (the selected figures of the two IDs of one campus)
    years_of = defaultdict(set)
    for (y, u, _g) in selected:
        years_of[u].add(y)
    for o, n in sorted(links):
        for y in sorted(years_of[o] & years_of[n]):
            if not (ranked(o) and ranked(n)) or state[o] != state[n]:
                continue
            vector = whole(selected, y, o)
            if vector != whole(selected, y, n) or nonzero(vector) < 1:
                continue
            ro, rn = int(release_of[(o, y)]), int(release_of[(n, y)])
            if ro == rn:
                continue
            older_id, newer_id = (o, n) if ro < rn else (n, o)
            shadow_campus_year(y, older_id, newer_id, "renumbered")

    # A host whose own block is a shadow passes its shadows on to its host
    def final_host(year: int, geo: str, host: int, unitid: int) -> int:
        seen = {unitid}
        while (year, geo, host) in shadows:
            if host in seen:
                raise RuntimeError(f"The shared-statistics rules make campuses {sorted(seen)} each other's shadows "
                                   f"for {year} {geo}. Check their figures and settle the case in "
                                   "find_shared_blocks in 04_create_aggregates.py.")
            seen.add(host)
            host = shadows[(year, geo, host)][0]
        return host

    rows = []
    for (y, g, u), (host, rule) in shadows.items():
        rows.append((y, g, u, "shadow", final_host(y, g, host, u), rule))
    hosts = {(y, g, h) for (y, g, _u, _role, h, _rule) in rows}
    hosts |= {(y, g, u) for (y, g, u) in same_block if (y, g, u) not in shadows}
    rows += [(y, g, h, "host", h, None) for (y, g, h) in sorted(hosts) if (y, h, g) in selected]

    shared = pd.DataFrame(rows, columns=["year", "geo", "unitid", "role", "host_unitid", "rule"])
    shared["state"] = shared["unitid"].map(state)
    cells = [selected[(y, u, g)] for y, g, u in zip(shared["year"], shared["geo"], shared["unitid"])]
    shared["nonzero_cells"] = [nonzero(c) for c in cells]
    shared["block_count"] = [sum(c) for c in cells]
    shared = shared.sort_values(["year", "geo", "host_unitid", "role", "unitid"]).reset_index(drop=True)
    shared["group"] = shared.groupby(["year", "geo", "host_unitid"], sort=False).ngroup()
    shared["group_size"] = shared.groupby("group")["unitid"].transform("size")
    shared = shared[["year", "geo", "state", "group", "unitid", "role", "host_unitid", "rule", "group_size",
                     "nonzero_cells", "block_count"]]
    return shared.astype({"year": "int16", "group": "int32", "unitid": "int32", "host_unitid": "int32",
                          "group_size": "int16", "nonzero_cells": "int16", "block_count": "int32"})


def create_shared_blocks(base: pd.DataFrame, dim_inst: pd.DataFrame, enrollment: pd.DataFrame) -> pd.DataFrame:
    """Find the shared blocks (find_shared_blocks), save them and print what they take out of the rankings."""
    print("\nFinding statistics reported identically by two or more campuses...")
    shared = find_shared_blocks(base, dim_inst, enrollment, load_campus_year_sources(), load_older_release_counts(),
                                load_id_links())
    shared.to_parquet(SHARED_PATH, index=False)
    shadows = shared[shared["role"] == "shadow"]
    print(f"  Hosts' groups: {shared['group'].nunique():,}; shadow blocks (counted once, under the host): "
          f"{len(shadows):,}; counts not added again: {int(shadows['block_count'].sum()):,}")
    for rule in SHARED_RULES:
        part = shadows[shadows["rule"] == rule]
        print(f"    by rule {rule}: {len(part):,} shadow blocks, {int(part['block_count'].sum()):,} counts")
    for year, part in shared.groupby("year"):
        s = part[part["role"] == "shadow"]
        print(f"    {year}: {part['group'].nunique():,} groups, {len(s):,} shadow blocks, "
              f"{int(s['block_count'].sum()):,} counts")
    print(f"  Saved to: {SHARED_PATH}")
    return shared


def without_shadows(base: pd.DataFrame, shared: pd.DataFrame) -> pd.DataFrame:
    """The fact rows `base` without the shadow blocks: what totals and rankings count."""
    shadows = shared[shared["role"] == "shadow"]
    drop = set(zip(shadows["year"].astype(int).tolist(), shadows["geo"].tolist(), shadows["unitid"].astype(int).tolist()))
    keep = [(y, g, u) not in drop for y, g, u in zip(base["year"].astype(int).tolist(), base["geo"].tolist(),
                                                       base["unitid"].astype(int).tolist())]
    kept = base[keep].reset_index(drop=True)
    print(f"  Fact rows counted in totals and rankings: {len(kept):,} of {len(base):,}")
    return kept


def ranked(group: pd.DataFrame, column: str) -> tuple[pd.DataFrame, list[int]]:
    """
    The rows of `group` that have a value in `column`, largest first, and
    their ranks. Every ranking uses this order and rank: ties (equal values)
    are listed by institution name, then UNITID, and share standard
    competition ranks: 1, 2, 2, 4 (the rank after a tie skips the places
    the tie takes). 05_generate_json.py ranks its summary codes the same way.
    """
    rows = group[group[column].notna()].sort_values(
        [column, "institution_name", "unitid"], ascending=[False, True, True], kind="mergesort"
    ).reset_index(drop=True)
    values = rows[column].tolist()
    ranks: list[int] = []
    for i, value in enumerate(values):
        ranks.append(ranks[-1] if i and value == values[i - 1] else i + 1)
    return rows, ranks


def create_ivy_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute Ivy League rankings for all year/offense/geo combinations.

    Schema:
        year: int16
        offense: string
        geo: string
        rank: int8                   # 1-8 for Ivy League
        unitid: int32
        institution_name: string
        short_name: string
        count: int32
        pct_of_ivy_total: float      # Percent of total Ivy incidents
        fte: int32                   # FTE enrollment (may be null)
    """
    print("\nCreating Ivy League rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Filter to Ivy League only
    ivy_unitids = set(IVY_LEAGUE.keys())
    ivy_data = school_agg[school_agg["unitid"].isin(ivy_unitids)].copy()

    if len(ivy_data) == 0:
        raise RuntimeError("No Ivy League schools in the aggregate. Check the facts from 02_transform_to_parquet.py.")

    print(f"  Ivy League records: {len(ivy_data):,}")

    # Add short names
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    ivy_data["short_name"] = ivy_data["unitid"].map(short_map)

    # Calculate rankings within each (year, offense, geo) group
    rankings = []

    groups = ivy_data.groupby(["year", "offense", "geo"])

    for (year, offense, geo), group in groups:
        # By count, largest first; ties by name, then UNITID, ranked 1, 2, 2, 4
        # (ranked). Rates are per institution (create_institution_tables).
        sorted_group, ranks = ranked(group, "count")

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        for rank, (_, row) in zip(ranks, sorted_group.iterrows()):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row["short_name"],
                "count": row["count"],
                "pct_of_ivy_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int8")
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_ivy_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  Rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    Offenses: {rankings_df['offense'].nunique()}")
    print(f"    Schools: {rankings_df['unitid'].nunique()}")

    # Show sample ranking for most recent year
    latest_year = rankings_df["year"].max()
    sample = rankings_df[
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Rape") &
        (rankings_df["geo"] == "All")
    ].head(8)

    if not sample.empty:
        print(f"\n  Sample: Rape rankings ({latest_year}, All locations):")
        for _, row in sample.iterrows():
            print(f"    {row['rank']}. {row['short_name']}: {row['count']} ({row['pct_of_ivy_total']:.1f}%)")

    return rankings_df


def create_state_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute state-based rankings for all year/offense/geo/state combinations.

    Schema:
        state: string                # State code (CA, NY, etc.)
        year: int16
        offense: string
        geo: string
        rank: int16                  # Rank within state
        unitid: int32
        institution_name: string
        short_name: string           # May be null for non-Ivy
        count: int32
        pct_of_state_total: float    # Percent of state's total incidents
        fte: int32                   # FTE enrollment (may be null)
    """
    print("\nCreating state-based rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only (schools with a blank state or a code not in US_STATES are not ranked)
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        raise RuntimeError(f"No school in the aggregate has a U.S. state code. Check {dims_path.name}.")

    states_in_data = valid_data["state"].nunique()
    print(f"  Records with valid states: {len(valid_data):,}")
    print(f"  States represented: {states_in_data}")

    # Add short names (only for Ivy League schools)
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    valid_data["short_name"] = valid_data["unitid"].map(short_map)

    # Calculate rankings within each (state, year, offense, geo) group
    rankings = []

    groups = valid_data.groupby(["state", "year", "offense", "geo"])
    total_groups = len(groups)

    for i, ((state, year, offense, geo), group) in enumerate(groups):
        if i % 10000 == 0 and i > 0:
            print(f"  Processed {i:,}/{total_groups:,} groups...")

        # By count, largest first; ties by name, then UNITID, ranked 1, 2, 2, 4
        # (ranked). Rates are per institution (create_institution_tables).
        sorted_group, ranks = ranked(group, "count")

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        for rank, (_, row) in zip(ranks, sorted_group.iterrows()):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "state": state,
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row.get("short_name"),
                "count": row["count"],
                "pct_of_state_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    if len(rankings_df) == 0:
        raise RuntimeError("No rankings were generated from the aggregate.")

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int16")
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["state", "year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Total ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_state_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  State rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    States: {rankings_df['state'].nunique()}")
    print(f"    Total schools: {rankings_df['unitid'].nunique()}")

    # Show sample for California
    latest_year = rankings_df["year"].max()
    ca_sample = rankings_df[
        (rankings_df["state"] == "CA") &
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Burglary") &
        (rankings_df["geo"] == "All")
    ].head(5)

    if not ca_sample.empty:
        print(f"\n  Sample: CA Burglary rankings ({latest_year}, All locations, top 5):")
        for _, row in ca_sample.iterrows():
            name = row["short_name"] or row["institution_name"][:30]
            print(f"    {row['rank']}. {name}: {row['count']} ({row['pct_of_state_total']:.1f}%)")

    return rankings_df


def create_national_rankings(school_agg: pd.DataFrame = None) -> pd.DataFrame:
    """
    Pre-compute national rankings for all schools across all year/offense/geo combinations.

    Schema:
        year: int16
        offense: string
        geo: string
        rank: int16                  # Rank nationally (by count)
        unitid: int32
        institution_name: string
        short_name: string           # May be null for non-Ivy
        state: string
        count: int32
        pct_of_national_total: float # Percent of national total incidents
        fte: int32                   # FTE enrollment (may be null)
    """
    print("\nCreating national rankings...")

    # Load school aggregate if not provided
    if school_agg is None:
        school_agg = load_school_agg()

    # Load institution dimension to get state info
    dims_path = CURATED_DIR / "dims" / "dim_institution.parquet"
    if not dims_path.is_file():
        raise RuntimeError(f"{dims_path} not found. Run 03_build_dimensions.py first.")

    dim_inst = pd.read_parquet(dims_path)

    # Add state to school_agg
    state_map = dim_inst.set_index("unitid")["state"].to_dict()
    school_agg = school_agg.copy()
    school_agg["state"] = school_agg["unitid"].map(state_map)

    # Filter to valid states only (schools with a blank state or a code not in US_STATES are not ranked)
    valid_data = school_agg[school_agg["state"].isin(US_STATES.keys())].copy()

    if len(valid_data) == 0:
        raise RuntimeError(f"No school in the aggregate has a U.S. state code. Check {dims_path.name}.")

    print(f"  Records with valid states: {len(valid_data):,}")
    print(f"  Total unique schools: {valid_data['unitid'].nunique()}")

    # Add short names (only for Ivy League schools)
    short_map = {uid: info["short"] for uid, info in IVY_LEAGUE.items()}
    valid_data["short_name"] = valid_data["unitid"].map(short_map)

    # Calculate rankings within each (year, offense, geo) group
    rankings = []

    groups = valid_data.groupby(["year", "offense", "geo"])
    total_groups = len(groups)

    for i, ((year, offense, geo), group) in enumerate(groups):
        if i % 1000 == 0 and i > 0:
            print(f"  Processed {i:,}/{total_groups:,} groups...")

        # By count, largest first; ties by name, then UNITID, ranked 1, 2, 2, 4
        # (ranked). Rates are per institution (create_institution_tables).
        sorted_group, ranks = ranked(group, "count")

        # Calculate total for percentage
        total_count = sorted_group["count"].sum()

        for rank, (_, row) in zip(ranks, sorted_group.iterrows()):
            pct = (row["count"] / total_count * 100) if total_count > 0 else 0

            rankings.append({
                "year": year,
                "offense": offense,
                "offense_family": row["offense_family"],
                "geo": geo,
                "rank": rank,
                "unitid": row["unitid"],
                "institution_name": row["institution_name"],
                "short_name": row.get("short_name"),
                "state": row["state"],
                "count": row["count"],
                "pct_of_national_total": round(pct, 2),
                "fte": row.get("fte") if pd.notna(row.get("fte")) else None,
            })

    rankings_df = pd.DataFrame(rankings)

    if len(rankings_df) == 0:
        raise RuntimeError("No rankings were generated from the aggregate.")

    # Ensure proper types
    rankings_df["year"] = rankings_df["year"].astype("int16")
    rankings_df["rank"] = rankings_df["rank"].astype("int16")
    rankings_df["unitid"] = rankings_df["unitid"].astype("int32")
    rankings_df["count"] = rankings_df["count"].astype("int32")
    rankings_df["fte"] = rankings_df["fte"].astype("Int32")  # Nullable

    # Sort
    rankings_df = rankings_df.sort_values(
        ["year", "offense", "geo", "rank"]
    ).reset_index(drop=True)

    print(f"  Total ranking records: {len(rankings_df):,}")

    # Save
    agg_dir = CURATED_DIR / "aggs"
    output_path = agg_dir / "agg_national_rankings.parquet"
    rankings_df.to_parquet(output_path, index=False)

    print(f"  Saved to: {output_path}")

    # Summary stats
    print(f"\n  National rankings summary:")
    print(f"    Years: {rankings_df['year'].min()}-{rankings_df['year'].max()}")
    print(f"    Total schools: {rankings_df['unitid'].nunique()}")
    schools_with_fte = rankings_df["fte"].notna().sum()
    print(f"    Records with FTE: {schools_with_fte:,} ({schools_with_fte/len(rankings_df)*100:.1f}%)")

    # Show sample for Burglary
    latest_year = rankings_df["year"].max()
    sample = rankings_df[
        (rankings_df["year"] == latest_year) &
        (rankings_df["offense"] == "Burglary") &
        (rankings_df["geo"] == "All")
    ].head(5)

    if not sample.empty:
        print(f"\n  Sample: National Burglary rankings ({latest_year}, All locations, top 5):")
        for _, row in sample.iterrows():
            name = row["short_name"] if pd.notna(row["short_name"]) else row["institution_name"][:30]
            print(f"    {row['rank']}. {name} ({row['state']}): {row['count']}")

    return rankings_df


CAMPUS_YEAR_PATH = CURATED_DIR / "aggs" / "agg_campus_year.parquet"
INSTITUTION_YEAR_PATH = CURATED_DIR / "aggs" / "agg_institution_year.parquet"
INSTITUTION_OFFENSE_PATH = CURATED_DIR / "aggs" / "agg_institution_year_offense.parquet"


def load_institution_enrollment() -> pd.DataFrame:
    """
    FTE, the share of students enrolled exclusively online (pctdeexc), the
    fall headcounts (total, full-time, part-time) and, from DRVEF, the
    headcounts and shares by level per institution (base UNITID) and year,
    from dim_enrollment.parquet.
    """
    path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    df = pd.read_parquet(path)
    need = ["unitid", "year", "fte", "pctdeexc", "enrollment_total", "enrollment_ft", "enrollment_pt",
            "enrollment_ug", "enrollment_ug_ft", "enrollment_grad", "enrollment_grad_ft", "pcudeexc", "pcgdeexc"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise RuntimeError(f"{path} has no column {', '.join(missing)}. Run 02b_transform_ef_enrollment.py and "
                           "02a_transform_enrollment.py again, then this step.")
    return df[need]


def abroad_campuses(dim_inst: pd.DataFrame) -> set[int]:
    """
    The campuses abroad (config.py: not in the rate): those DOE lists without
    a state, and those of 03's reviewed list (dim_campus_abroad.parquet) that
    DOE gives a state.
    """
    listed = set(pd.read_parquet(ABROAD_PATH)["unitid"].astype(int).tolist())
    return {int(u) for u, s in zip(dim_inst["unitid"].tolist(), dim_inst["state"].tolist())
            if s is None or pd.isna(s) or not str(s).strip()} | listed


def peer_types(classes: pd.DataFrame) -> dict[int, str]:
    """
    {base UNITID: peer type} (config.py, PEER_TYPES): the Carnegie Size &
    Setting value of the first of SIZE_SETTING_FIELDS (newest first) that an
    IPEDS HD file gives the institution a classified value (above 0) in, from
    the newest such file; "other" without one. One type per institution, so
    its peer group does not change between windows.
    """
    out = {}
    for b, rows in classes.groupby("unitid"):
        value = None
        for field in SIZE_SETTING_FIELDS:
            col = rows[["year", field.lower()]].dropna()
            col = col[col[field.lower()] > 0]
            if len(col):
                value = int(col.sort_values("year").iloc[-1][field.lower()])
                break
        out[int(b)] = peer_type(value)
    return out


def create_institution_tables(ranked_agg: pd.DataFrame, shared: pd.DataFrame, dim_inst: pd.DataFrame,
                              enrollment: pd.DataFrame, sources: pd.DataFrame, school_agg: pd.DataFrame
                              ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    The campus-years that count in rankings and the institutions that rates
    are calculated for (config.py, "SUMMARY CODES AND RATES"): an
    institution is a base UNITID (the first six digits, which NCES's FTE is
    for), and its campuses are the campuses with that base UNITID.

    A campus-year counts when the campus reported that year
    (campus_year_sources.parquet: at least one count cell not blank) and its
    figures are not all counted under another campus (a campus-year whose
    every block with counts is a shadow block is left out). It is ranked
    with its count, 0 for an offense it had none of. The institution's
    counts are those of all its counting campuses in the United States
    (campuses DOE lists without a state, campuses abroad, are counted
    separately: IPEDS fall enrollment leaves out their students), without
    shadow blocks and residence halls (the geo "All" of `ranked_agg`). An
    institution is listed for a year when at least one of its campuses
    counts that year, incidents or not.

    Each institution-year has a link campus, whose school page the rate
    rankings link to and whose name and state they show: the main campus
    (UNITID ending in 001) when it counts that year, otherwise the campus
    with the most incidents that year (ties: the lowest UNITID), of its
    counting campuses in the United States when it has one. Only a campus
    with a school file (dim_institution.parquet) can be the link.

    Saves and returns:
      agg_campus_year.parquet: year, unitid, base_unitid, state, count (the
        geo "All" total of every offense, 0 included)
      agg_institution_year.parquet: year, base_unitid, institution_name,
        link_unitid, state, campuses (that count that year, in the United
        States), abroad_campuses (that count, abroad), fte, pctdeexc (that
        year's share of exclusively online students), online_pct and
        online_year (the share the rate rules use and the fall it is from:
        ONLINE_SHARE_YEAR), fte_share and fte_part_time_first (config.py's
        estimates (a) and (b), rounded half up; (b) none when it cannot be
        calculated), fte_by_level (whether (b) is by level), oncampus_fte
        (the larger, rounded half up; fte without a share), online_uncertain
        (config.py, ONLINE_UNCERTAIN_RATIO, for the institution or one pooled
        with it), online_uncertain_own (for the institution itself; when
        online_uncertain is true and this false, only a pooled institution's
        is), oncampus_fte_smaller (the smaller estimate, rounded half up;
        none without a second estimate: (b) cannot be calculated),
        rate_fte_smaller (the rate's denominator from the smaller estimates
        of the institution and those pooled with it; none when one of them
        has no second estimate), peer_type (config.py, PEER_TYPES; one per
        institution), rate_rule and rate_excluded (the first rule that gives
        it no rate: hospital, medical, listed
        (population_class_rules), merger (merger_rate_rules), family
        (split_family_exclusions), shared_pooled, shared_campus
        (classify_shared_sites), and why; none when no rule does),
        pooled_with ("base:on-campus FTE" of each institution whose FTE its
        rate adds, space separated, or none), pooled_rule (the rules that
        add them, merger and/or shared, space separated, or none),
        rate_fte (the rate's denominator: oncampus_fte plus those),
        co_located_with (the institutions whose students its rate adds, or
        would add with an FTE, because their campuses at a shared site copy
        its own: bases, space separated, or none), shared_in_with (the
        guests at the shared sites it owns), shared_out_sites (its campuses
        at shared sites it is a guest or participant of: UNITIDs) and
        shared_out_with (the owners, or the other participants, of those
        sites), shared_site_students (the sum of the reviewed student
        figures that cover those campuses that year, dim_shared_site_enrollment:
        the year's own, or one within config.py's SHARED_SITE_FIGURE_YEARS;
        none when one has no figure or there is no such campus) and
        shared_site_upper (whether one of those figures is an upper bound)
      agg_institution_year_offense.parquet: year, base_unitid, offense,
        offense_family, count (its counting campuses in the United States,
        all geographies), count_on, count_res, count_non and count_pub (the
        same at each geography for the rates: on campus, of which in
        residence halls, non-campus, public property; without the campuses
        of dim_shared_campus_override that year and the campuses that
        classify_shared_sites takes out of its rates), shared_site_count
        (the count of those campuses: in count, in no rate; count = count_on
        + count_non + count_pub + shared_site_count), medical_on (of
        count_on, at campuses of dim_medical_campus that year, residence
        halls taken out: each such campus's on-campus count less its
        residence-hall count, at least 0), shared_in (of the count, figures
        that a campus of another institution also reported:
        shared_rate_rules, and the host campus's figures of a
        dim_shared_campus_override campus), shared_out (figures of its
        campuses that count under another institution's campus, not in the
        count; and the figures of its dim_shared_campus_override campuses,
        in the count but in no rate), shared_in_on (of count_on, its
        figures at the shared sites it owns, classify_shared_sites),
        shared_out_on (its on-campus figures at the shared sites it is a
        guest or participant of, in none of its rates), abroad_count (its
        counting campuses abroad, not in the count); rows with any of them
        above 0

      shared_sites.parquet: year, site (its lowest UNITID), unitid,
        base_unitid, site_class (one_main, no_main, several_main_pooled,
        several_main_unassigned, pooled), owner_base, role (owner, guest,
        participant, pooled, unassigned, no_campus) and links (exact, near,
        override: how the campus is joined to the site)
      near_copies.parquet: find_near_copies's pairs
    """
    print("\nCreating institution tables (rates are per institution)...")
    counted = ranked_agg[ranked_agg["geo"] == "All"]
    campus_totals = counted.groupby(["year", "unitid"], as_index=False)["count"].sum()

    # Campus-years that count: reported, and not entirely shadow blocks
    reported = sources[["unitid", "year"]].drop_duplicates()
    stray = campus_totals.merge(reported, on=["unitid", "year"], how="left", indicator=True)
    stray = stray[stray["_merge"] == "left_only"]
    if len(stray):
        first = stray.iloc[0]
        raise RuntimeError(f"{len(stray):,} campus-years have counts but no release in {SOURCES_PATH.name} "
                           f"(first: {int(first['unitid'])} {int(first['year'])}). "
                           "Run 02_transform_to_parquet.py and 03 again, then this step.")
    shadowed = shared[shared["role"] == "shadow"][["unitid", "year"]].drop_duplicates()
    with_counts = set(zip(campus_totals["unitid"].tolist(), campus_totals["year"].tolist()))
    left_out = {(int(u), int(y)) for u, y in zip(shadowed["unitid"].tolist(), shadowed["year"].tolist())
                if (int(u), int(y)) not in with_counts}
    campus_years = reported[[(int(u), int(y)) not in left_out
                             for u, y in zip(reported["unitid"].tolist(), reported["year"].tolist())]].copy()
    campus_years = campus_years.merge(campus_totals, on=["unitid", "year"], how="left")
    campus_years["count"] = campus_years["count"].fillna(0).astype("int64")
    campus_years["base_unitid"] = (campus_years["unitid"] // 1000).astype("int64")
    print(f"  Campus-years that count for their institution: {len(campus_years):,} "
          f"(left out, all figures counted under another campus: {len(left_out):,})")

    # Every counting campus-year has a school file (03 lists every campus that reported)
    has_file = set(dim_inst["unitid"].astype("int64").tolist())
    name_of = dim_inst.set_index("unitid")["institution_name"].to_dict()
    state_of = dim_inst.set_index("unitid")["state"].to_dict()
    abroad = abroad_campuses(dim_inst)
    no_file = campus_years[~campus_years["unitid"].isin(has_file)]
    if len(no_file):
        first = no_file.iloc[0]
        raise RuntimeError(f"{len(no_file):,} reported campus-years have no campus in dim_institution.parquet "
                           f"(first: {int(first['unitid'])} {int(first['year'])}). Run 03_build_dimensions.py "
                           "again, then this step.")
    campus_out = campus_years.assign(state=campus_years["unitid"].map(state_of))[
        ["year", "unitid", "base_unitid", "state", "count"]].astype(
        {"year": "int16", "unitid": "int32", "base_unitid": "int32", "count": "int32"})
    campus_out = campus_out.sort_values(["year", "unitid"]).reset_index(drop=True)
    print(f"  Of these without an incident (ranked with 0): {int((campus_out['count'] == 0).sum()):,}")

    # Institution-years (a counting campus, incidents or not), their campuses and link campus
    # (a campus in the United States when the institution counts one that year)
    rows = []
    for (year, base_id), group in campus_years.groupby(["year", "base_unitid"]):
        home = group[~group["unitid"].isin(abroad)]
        candidates = home if len(home) else group
        main_campus = int(base_id) * 1000 + 1
        if main_campus in set(candidates["unitid"].tolist()):
            link = main_campus
        else:
            link = int(candidates.sort_values(["count", "unitid"], ascending=[False, True]).iloc[0]["unitid"])
        n_abroad = sum(1 for u in group["unitid"].tolist() if int(u) in abroad)
        rows.append({"year": int(year), "base_unitid": int(base_id), "institution_name": name_of[link],
                     "link_unitid": link, "state": opt_value(state_of.get(link)), "campuses": len(group) - n_abroad,
                     "abroad_campuses": n_abroad})
    inst_year = pd.DataFrame(rows, columns=["year", "base_unitid", "institution_name", "link_unitid", "state",
                                            "campuses", "abroad_campuses"])
    print(f"  Institution-years with a counting campus abroad (its incidents not in the rate): "
          f"{int((inst_year['abroad_campuses'] > 0).sum()):,}")

    # FTE and online share of each institution-year (none when NCES has no figure)
    enroll = enrollment.rename(columns={"unitid": "base_unitid"})
    inst_year = inst_year.merge(enroll[["base_unitid", "year", "fte", "pctdeexc"]], on=["base_unitid", "year"],
                                how="left", validate="many_to_one")

    # The online share the rate rules use (online_pct) and the fall it is
    # from (online_year): the year's own, except in the years of
    # ONLINE_SHARE_YEAR (config.py: the pandemic's remote teaching), which
    # use that other year's share, or their own when NCES has none for it
    inst_year["online_src"] = [ONLINE_SHARE_YEAR.get(int(y), int(y)) for y in inst_year["year"].tolist()]
    src_share = enroll[["base_unitid", "year", "pctdeexc"]].rename(
        columns={"year": "online_src", "pctdeexc": "src_pct"})
    inst_year = inst_year.merge(src_share, on=["base_unitid", "online_src"], how="left", validate="many_to_one")
    other_year = inst_year["online_src"] != inst_year["year"]
    use_src = other_year & inst_year["src_pct"].notna()
    inst_year["online_pct"] = inst_year["src_pct"].where(use_src, inst_year["pctdeexc"])
    inst_year["online_year"] = inst_year["online_src"].where(use_src, inst_year["year"]).where(
        inst_year["online_pct"].notna())
    for year, src in sorted(ONLINE_SHARE_YEAR.items()):
        in_year = inst_year["year"] == year
        own_used = in_year & ~use_src & inst_year["pctdeexc"].notna()
        big = inst_year["fte"].fillna(0) >= MIN_FTE_FOR_RATE
        print(f"  {year}: online share from {src} for {int((in_year & use_src).sum()):,} institutions; "
              f"no {src} share, own year's used: {int(own_used.sum()):,} ({int((own_used & big).sum()):,} with "
              f"{MIN_FTE_FOR_RATE:,}+ FTE); no share at all: {int((in_year & inst_year['online_pct'].isna()).sum()):,}")
    inst_year = inst_year.drop(columns=["online_src", "src_pct"])
    # A campus reported under this and another institution that year (merger_rate_rules): left out
    # of rate rankings, or rated with the other institution's FTE added
    counting = set(zip(campus_years["unitid"].astype(int).tolist(), campus_years["year"].astype(int).tolist()))
    fte_of = {(int(b), int(y)): int(f) for b, y, f in
              zip(enroll["base_unitid"].tolist(), enroll["year"].tolist(), enroll["fte"].tolist()) if pd.notna(f)}
    keys = list(zip(inst_year["year"].astype(int).tolist(), inst_year["base_unitid"].astype(int).tolist()))
    key_set = set(keys)

    # On-campus FTE (config.py): the larger of (a) proportional and (b)
    # part-time first, rounded half up; the full FTE without a share. Of every
    # institution with an FTE that year, listed or not (a pooled one is not listed)
    enroll_rec = {(int(r["base_unitid"]), int(r["year"])): r for r in enroll.to_dict("records")}
    estimates = {}  # (base, year) -> (a, b, by level, uncertain)
    for (b, y), f in fte_of.items():
        rec = enroll_rec[(b, y)]
        src = ONLINE_SHARE_YEAR.get(y, y)
        src_pct = enroll_rec.get((b, src), {}).get("pctdeexc")
        own_pct = rec.get("pctdeexc")
        if src != y and src_pct is not None and pd.notna(src_pct):
            p, own = int(src_pct), False
        else:
            p, own = (None if own_pct is None or pd.isna(own_pct) else int(own_pct)), True
        heads = tuple(None if pd.isna(rec.get(c)) else int(rec.get(c))
                      for c in ("enrollment_total", "enrollment_ft", "enrollment_pt"))
        level = level_figures(rec) if own else None
        a, b_est = oncampus_estimates(f, p, heads, level)
        hi, lo = (a, a) if b_est is None else (max(a, b_est), min(a, b_est))
        num, den = ONLINE_UNCERTAIN_RATIO
        uncertain = p is not None and p > 0 and (b_est is None or hi * den > lo * num)
        estimates[(b, y)] = (a, b_est, level is not None and b_est is not None and bool(p), uncertain)
    oncampus_of = {k: half_up(a if b_est is None else max(a, b_est)) for k, (a, b_est, _l, _u) in estimates.items()}
    # The smaller estimate, for the comparison of an institution with an
    # uncertain on-campus FTE (config.py); none without a second estimate
    smaller_of = {k: (half_up(min(a, b_est)) if b_est is not None else (half_up(a) if not u else None))
                  for k, (a, b_est, _l, u) in estimates.items()}
    inst_year["fte_share"] = [half_up(estimates[(b, y)][0]) if (b, y) in estimates else None for y, b in keys]
    inst_year["fte_part_time_first"] = [half_up(estimates[(b, y)][1])
                                        if (b, y) in estimates and estimates[(b, y)][1] is not None else None
                                        for y, b in keys]
    inst_year["fte_by_level"] = [bool(estimates[(b, y)][2]) if (b, y) in estimates else False for y, b in keys]
    inst_year["oncampus_fte"] = [oncampus_of.get((b, y)) for y, b in keys]

    # Who is left out of rate rankings, first rule first: the campus
    # population (population_class_rules), a merger or renumbering
    # (merger_rate_rules, split_family_exclusions); and whose rate adds
    # another institution's FTE (those and a shared campus, shared_rate_rules)
    classes = population_class_rules(pd.read_parquet(CLASS_PATH))
    # Campus-years with at least one incident in DOE's figures (shadow blocks included)
    published = school_agg[(school_agg["geo"] == "All") & (school_agg["count"] > 0)]
    active = set(zip(published["unitid"].astype(int).tolist(), published["year"].astype(int).tolist()))
    merger_out, merger_pool = merger_rate_rules(sources, counting, fte_of, active)
    family_out = split_family_exclusions(inst_year, sources, counting, active)
    shared_pool, shared_partial = shared_rate_rules(shared, counting, fte_of)

    # Shared sites (classify_shared_sites): campuses of two or more
    # institutions joined by identical on-campus figures (shadow blocks, not
    # two IDs of one campus), near-copies (find_near_copies) or the reviewed
    # list (dim_shared_campus_override)
    linked = {frozenset(p) for p in load_id_links()}
    on_rows = ranked_agg[(ranked_agg["geo"] == "On-campus") & ranked_agg["offense"].isin(OFFENSE_ORDER)]
    on_cells = defaultdict(dict)
    for y, u, o, c in zip(on_rows["year"].tolist(), on_rows["unitid"].tolist(), on_rows["offense"].tolist(),
                          on_rows["count"].tolist()):
        if c and (int(u), int(y)) in counting and int(u) not in abroad:
            on_cells[(int(y), int(u))][str(o)] = int(c)
    on_shadows = shared[(shared["role"] == "shadow") & (shared["geo"] == "On-campus")]
    on_shadow_host = {(int(y), int(u)): int(h) for y, u, h in zip(
        on_shadows["year"].tolist(), on_shadows["unitid"].tolist(), on_shadows["host_unitid"].tolist())}
    edges = defaultdict(set)
    for (y, u), h in on_shadow_host.items():
        if u // 1000 != h // 1000 and frozenset((u, h)) not in linked:
            edges[y].add((u, h, "exact"))
    near = find_near_copies(on_cells, state_of, linked)
    for y, a, b, *_rest in near:
        edges[y].add((a, b, "near"))
    overrides = pd.read_parquet(OVERRIDE_PATH)
    host_of = {(int(u), int(y)): int(h) for u, y, h in zip(overrides["unitid"], overrides["year"],
                                                          overrides["host_unitid"])}
    for (u, y), h in host_of.items():
        if (u, y) in counting or (y, u) in on_shadow_host:
            edges[y].add((u, h, "override"))
    base_name = {}
    for u, name in sorted(zip(dim_inst["unitid"].astype(int).tolist(), dim_inst["institution_name"].tolist())):
        if u % 1000 == 1 or u // 1000 not in base_name:
            base_name[u // 1000] = name
    sites = classify_shared_sites(edges, counting, key_set, oncampus_of, shared_pool, on_cells, on_shadow_host,
                                  base_name)
    for w in sites["warnings"]:
        print(f"  Warning: {w}")
    shared_pool = {k: {s for s in v if (k[0], s) not in sites["pool_remove"]} for k, v in shared_pool.items()}
    for k, v in sites["pool_add"].items():
        shared_pool[k] = shared_pool.get(k, set()) | v
    shared_pool = {k: v for k, v in shared_pool.items() if v}
    excluded, rule_of = {}, {}
    for rule, found in (("hospital", {k: t for k, (r, t) in classes.items() if r == "hospital"}),
                        ("medical", {k: t for k, (r, t) in classes.items() if r == "medical"}),
                        ("listed", {k: t for k, (r, t) in classes.items() if r == "listed"}),
                        ("merger", merger_out), ("family", family_out),
                        ("shared_pooled", {k: t for k, (r, t) in sites["excluded"].items() if r == "shared_pooled"}),
                        ("shared_campus", {k: t for k, (r, t) in sites["excluded"].items() if r == "shared_campus"})):
        for key, text in found.items():
            if key in key_set and key not in excluded:
                excluded[key], rule_of[key] = text, rule
        n_rule = sum(1 for k in found if k in key_set)
        n_big = sum(1 for k in found if k in key_set and (oncampus_of.get((k[1], k[0])) or 0) >= MIN_FTE_FOR_RATE)
        print(f"  Rate rule {rule}: {n_rule:,} institution-years ({n_big:,} with {MIN_FTE_FOR_RATE:,}+ on-campus "
              f"FTE; first rule for {sum(1 for r in rule_of.values() if r == rule):,})")
    pooled = defaultdict(set)
    pooled_by = defaultdict(set)
    for rule, found in (("merger", merger_pool), ("shared", shared_pool)):
        for key, adds in found.items():
            if key in key_set and key not in excluded and (key[1], key[0]) in fte_of:
                pooled[key] |= adds
                pooled_by[key].add(rule)
    inst_year["rate_rule"] = [rule_of.get(k) for k in keys]
    inst_year["pooled_rule"] = [" ".join(sorted(pooled_by[k])) if pooled_by.get(k) else None for k in keys]
    inst_year["rate_excluded"] = [excluded.get(k) for k in keys]
    # pooled_with: "base:on-campus FTE" of each institution whose FTE the rate adds
    inst_year["pooled_with"] = [" ".join(f"{s}:{oncampus_of[(s, k[0])]}" for s in sorted(pooled[k]))
                                if pooled.get(k) else None for k in keys]
    inst_year["rate_fte"] = [None if (b, y) not in oncampus_of else
                             oncampus_of[(b, y)] + sum(oncampus_of[(s, y)] for s in pooled.get((y, b), ()))
                             for y, b in keys]
    inst_year["online_uncertain"] = [(b, y) in estimates and (
        estimates[(b, y)][3] or any(estimates[(s, y)][3] for s in pooled.get((y, b), ()))) for y, b in keys]
    inst_year["online_uncertain_own"] = [(b, y) in estimates and bool(estimates[(b, y)][3]) for y, b in keys]
    inst_year["oncampus_fte_smaller"] = [smaller_of.get((b, y)) for y, b in keys]
    inst_year["rate_fte_smaller"] = [
        None if (b, y) not in smaller_of or any(smaller_of.get((s, y)) is None for s in (b, *pooled.get((y, b), ())))
        else sum(smaller_of[(s, y)] for s in (b, *pooled.get((y, b), ()))) for y, b in keys]
    peer_of = peer_types(pd.read_parquet(CLASS_PATH))
    inst_year["peer_type"] = [peer_of.get(b, "other") for _y, b in keys]

    # Shared sites: who else is there, and the reviewed student figures of
    # the campuses it is a guest or participant with
    def joined(values):
        return " ".join(str(v) for v in sorted(values)) if values else None
    inst_year["co_located_with"] = [joined(sites["co_located"].get(k)) for k in keys]
    inst_year["shared_in_with"] = [joined(sites["in_with"].get(k)) for k in keys]
    inst_year["shared_out_sites"] = [joined(sites["out_sites"].get(k)) for k in keys]
    inst_year["shared_out_with"] = [joined(sites["out_with"].get(k)) for k in keys]
    site_enrollment = pd.read_parquet(SITE_ENROLLMENT_PATH)
    figure_of = {(int(u), int(y)): (int(n), str(kind)) for u, y, n, kind in zip(
        site_enrollment["unitid"], site_enrollment["year"], site_enrollment["students"], site_enrollment["kind"])}
    students, upper = [], []
    for y, b in keys:
        campuses = sites["out_sites"].get((y, b))
        figures = [figure_of.get((u, y)) for u in sorted(campuses or ())]
        if not campuses or any(f is None for f in figures):
            students.append(None)
            upper.append(False)
        else:
            students.append(sum(f[0] for f in figures))
            upper.append(any(f[1] == "upper bound" for f in figures))
    inst_year["shared_site_students"] = students
    inst_year["shared_site_upper"] = upper
    pooled_only = inst_year["online_uncertain"] & ~inst_year["online_uncertain_own"]
    print(f"  Uncertain on-campus FTE only through a pooled institution: {int(pooled_only.sum()):,} institution-years; "
          f"uncertain without a second estimate: {int((inst_year['online_uncertain'] & inst_year['rate_fte_smaller'].isna() & inst_year['rate_fte'].notna()).sum()):,}")
    print(f"  Rated with the on-campus FTE of institutions whose figures they count (merger or renumbering: "
          f"{sum(1 for k in merger_pool if k in pooled):,}; shared campus: "
          f"{sum(1 for k in shared_pool if k in pooled):,}): {len(pooled):,} institution-years")
    inst_year = inst_year.astype({"year": "int16", "base_unitid": "int32", "link_unitid": "int32",
                                  "campuses": "int16", "abroad_campuses": "int16", "fte": "Int32",
                                  "pctdeexc": "Int16", "online_pct": "Int16", "online_year": "Int16",
                                  "fte_share": "Int32", "fte_part_time_first": "Int32", "fte_by_level": "bool",
                                  "oncampus_fte": "Int32", "rate_fte": "Int32", "online_uncertain": "bool",
                                  "online_uncertain_own": "bool", "oncampus_fte_smaller": "Int32",
                                  "rate_fte_smaller": "Int32", "peer_type": "string", "co_located_with": "string",
                                  "shared_in_with": "string", "shared_out_sites": "string",
                                  "shared_out_with": "string", "shared_site_students": "Int32",
                                  "shared_site_upper": "bool"})
    for year in sorted(set(inst_year["year"].astype(int))):
        g = inst_year[inst_year["year"] == year]
        ok = (g["rate_fte"].fillna(0) >= MIN_FTE_FOR_RATE) & g["rate_excluded"].isna()
        print(f"  {year}: {len(g):,} institutions, {int(ok.sum()):,} with a rate (on-campus FTE "
              f"{MIN_FTE_FOR_RATE:,}+, no rule), of which {int((ok & g['online_uncertain']).sum()):,} with an "
              f"uncertain on-campus FTE and {int((ok & g['fte_by_level']).sum()):,} with (b) by level")
    inst_year = inst_year.sort_values(["year", "base_unitid"]).reset_index(drop=True)

    # The counts of every campus of the institution: in the United States
    # (count, and per geography) and abroad (abroad_count); of the on-campus
    # count, those at listed medical-center campuses outside residence halls
    # (medical_on: patients, visitors and staff are not students; a campus's
    # residence halls house students)
    medical = pd.read_parquet(MEDICAL_PATH)
    medical_set = set(zip(medical["unitid"].astype(int).tolist(), medical["year"].astype(int).tolist()))
    keys4 = ["year", "unitid", "offense", "offense_family"]
    geo_cols = {"All": "us", "On-campus": "count_on", "Residence halls": "count_res", "Non-campus": "count_non",
                "Public property": "count_pub"}
    wide = ranked_agg[ranked_agg["geo"].isin(list(geo_cols))].pivot_table(
        index=keys4, columns="geo", values="count", aggfunc="sum", fill_value=0).reset_index()
    for g in geo_cols:
        if g not in wide.columns:
            wide[g] = 0
    wide = wide.rename(columns=geo_cols)
    # Only campus-years that count (a campus-year whose figures all count under
    # another campus keeps DOE's residence-hall rows, which are no geography of "All")
    wide = wide[[(int(u), int(y)) in counting for u, y in zip(wide["unitid"].tolist(), wide["year"].tolist())]]
    rows = wide.assign(base_unitid=wide["unitid"] // 1000)
    is_abroad = rows["unitid"].isin(abroad)
    is_medical = pd.Series([(int(u), int(y)) in medical_set for u, y in zip(rows["unitid"], rows["year"])],
                           index=rows.index)
    # A campus whose reported figures are another institution's campus
    # figures (dim_shared_campus_override), and a campus that
    # classify_shared_sites takes out of its institution's rates: in the
    # institution's count, never in its rates (no geography, no medical figure)
    site_out = sites["rate_out"] | set(host_of)
    is_site = pd.Series([(int(u), int(y)) in site_out for u, y in zip(rows["unitid"], rows["year"])],
                        index=rows.index) & ~is_abroad
    rows = rows.assign(abroad_count=rows["us"].where(is_abroad, 0),
                       shared_site_count=rows["us"].where(is_site, 0),
                       medical_on=(rows["count_on"] - rows["count_res"]).clip(lower=0).where(
                           is_medical & ~is_abroad & ~is_site, 0))
    for c in ("us", "count_on", "count_res", "count_non", "count_pub"):
        rows[c] = rows[c].where(~is_abroad, 0)
    for c in ("count_on", "count_res", "count_non", "count_pub"):
        rows[c] = rows[c].where(~is_site, 0)
    inst_offense = rows.groupby(["year", "base_unitid", "offense", "offense_family"], as_index=False)[
        ["us", "count_on", "count_res", "count_non", "count_pub", "shared_site_count", "medical_on",
         "abroad_count"]].sum().rename(columns={"us": "count"})
    if (inst_offense["count"] != inst_offense["count_on"] + inst_offense["count_non"] + inst_offense["count_pub"]
            + inst_offense["shared_site_count"]).any():
        raise RuntimeError("An institution's count is not the sum of its geographies. This is a bug in "
                           "create_institution_tables.")

    # Shared figures (shared_rate_rules), all geographies: a host block's
    # figures per offense, once per host block for the host's institution
    # (shared_in), once per shadow block for a shadow institution that counts
    # campuses of its own (shared_out); not for a campus abroad (not in any
    # rate). On campus (shared_in_on, shared_out_on): classify_shared_sites
    by_geo = ranked_agg[ranked_agg["geo"].isin(GEO_FOR_ALL)]
    cells = defaultdict(dict)
    for y, u, g, o, c in zip(by_geo["year"].tolist(), by_geo["unitid"].tolist(), by_geo["geo"].tolist(),
                             by_geo["offense"].tolist(), by_geo["count"].tolist()):
        if c:
            cells[(int(y), int(u), str(g))][o] = int(c)
    shared_in, shared_out = defaultdict(int), defaultdict(int)
    shared_in_on, shared_out_on = sites["in_on"], sites["out_on"]
    host_blocks = set()
    for y, g, u, h, shadow_listed in shared_partial:
        for o, c in cells.get((y, h, g), {}).items():
            if h not in abroad and (y, h, g) not in host_blocks:
                shared_in[(y, h // 1000, o)] += c
            if shadow_listed and u not in abroad:
                shared_out[(y, u // 1000, o)] += c
        host_blocks.add((y, h, g))
    # A dim_shared_campus_override campus's blocks that count (its shadow
    # blocks are above): its own figures for its institution (shared_out, in
    # the count, in no rate), the host block's once for the host's institution
    # (shared_in)
    n_override = 0
    for (u, y), h in sorted(host_of.items()):
        if u in abroad or (u, y) not in counting:
            continue
        for g in GEO_FOR_ALL:
            own = cells.get((y, u, g), {})
            if not own:
                continue
            for o, c in own.items():
                n_override += c
                shared_out[(y, u // 1000, o)] += c
            if h not in abroad and (y, h, g) not in host_blocks:
                for o, c in cells.get((y, h, g), {}).items():
                    shared_in[(y, h // 1000, o)] += c
                host_blocks.add((y, h, g))
    print(f"  Campuses reporting another institution's figures (dim_shared_campus_override): {len(host_of):,} "
          f"campus-years listed, {n_override:,} counts kept in counts and out of rates")
    family = dict(zip(rows["offense"], rows["offense_family"]))
    extra = pd.DataFrame([{"year": y, "base_unitid": b, "offense": o, "offense_family": family[o],
                           "shared_in": shared_in.get((y, b, o), 0), "shared_out": shared_out.get((y, b, o), 0),
                           "shared_in_on": shared_in_on.get((y, b, o), 0),
                           "shared_out_on": shared_out_on.get((y, b, o), 0)}
                          for (y, b, o) in sorted(set(shared_in) | set(shared_out) | set(shared_in_on)
                                                  | set(shared_out_on))],
                         columns=["year", "base_unitid", "offense", "offense_family", "shared_in", "shared_out",
                                  "shared_in_on", "shared_out_on"])
    inst_offense = inst_offense.merge(extra, on=["year", "base_unitid", "offense", "offense_family"], how="outer")
    value_cols = ["count", "count_on", "count_res", "count_non", "count_pub", "shared_site_count", "medical_on",
                  "shared_in", "shared_out", "shared_in_on", "shared_out_on", "abroad_count"]
    inst_offense[value_cols] = inst_offense[value_cols].fillna(0).astype("int64")
    if (inst_offense["shared_in"] > inst_offense["count"]).any() or (
            inst_offense["shared_in_on"] > inst_offense["count_on"]).any():
        raise RuntimeError("Shared figures exceed an institution's count. This is a bug in create_institution_tables.")
    inst_offense = inst_offense[(inst_offense[value_cols] > 0).any(axis=1)]
    listed = set(zip(inst_year["year"].astype(int).tolist(), inst_year["base_unitid"].astype(int).tolist()))
    unlisted = [k for k in zip(inst_offense["year"].astype(int).tolist(), inst_offense["base_unitid"].astype(int).tolist())
                if k not in listed]
    if unlisted:
        raise RuntimeError(f"{len(unlisted):,} institution counts belong to no listed institution-year "
                           f"(first: {unlisted[0]}). This is a bug in create_institution_tables.")
    inst_offense = inst_offense.astype({"year": "int16", "base_unitid": "int32",
                                        **{c: "int32" for c in value_cols}})
    inst_offense = inst_offense.sort_values(["year", "base_unitid", "offense"]).reset_index(drop=True)
    print(f"  Incidents at listed medical-center campuses (on campus, not in residence halls): "
          f"{int(inst_offense['medical_on'].sum()):,}; abroad "
          f"(not in rates): {int(inst_offense['abroad_count'].sum()):,}; shared with another institution's "
          f"campus: {int(inst_offense['shared_in'].sum()):,} in hosts' counts, "
          f"{int(inst_offense['shared_out'].sum()):,} under another institution")

    site_rows = pd.DataFrame(sites["rows"], columns=["year", "site", "unitid", "base_unitid", "site_class",
                                                     "owner_base", "role", "links"]).astype(
        {"year": "int16", "site": "int32", "unitid": "int32", "base_unitid": "int32", "site_class": "string",
         "owner_base": "Int32", "role": "string", "links": "string"})
    near_rows = pd.DataFrame(near, columns=["year", "unitid", "other_unitid", "cells_equal", "cells_nonzero",
                                            "total", "other_total"]).astype(
        {"year": "int16", "unitid": "int32", "other_unitid": "int32", "cells_equal": "int16",
         "cells_nonzero": "int16", "total": "int32", "other_total": "int32"})
    print(f"  Near-copies (find_near_copies): {len(near_rows):,} campus pairs")
    for cls_name, part in site_rows.drop_duplicates(["year", "site"]).groupby("site_class"):
        print(f"  Shared sites, {cls_name}: {len(part):,} site-years "
              f"({', '.join(f'{y}: {n}' for y, n in part.groupby('year').size().items())})")
    print(f"  Out of rates at shared sites (and listed campuses): {int(inst_offense['shared_site_count'].sum()):,} "
          f"counts; left out by rule shared_pooled: {sum(1 for r in rule_of.values() if r == 'shared_pooled'):,}, "
          f"shared_campus: {sum(1 for r in rule_of.values() if r == 'shared_campus'):,} institution-years")
    campus_out.to_parquet(CAMPUS_YEAR_PATH, index=False)
    inst_year.to_parquet(INSTITUTION_YEAR_PATH, index=False)
    inst_offense.to_parquet(INSTITUTION_OFFENSE_PATH, index=False)
    site_rows.to_parquet(SITES_PATH, index=False)
    near_rows.to_parquet(NEAR_PATH, index=False)

    multi = inst_year[inst_year["campuses"] > 1]
    states_per_inst = campus_years.assign(state=campus_years["unitid"].map(state_of)).groupby(
        ["year", "base_unitid"])["state"].nunique()
    no_incident = len(inst_year) - len(set(zip(inst_offense.loc[inst_offense["count"] > 0, "year"].tolist(),
                                               inst_offense.loc[inst_offense["count"] > 0, "base_unitid"].tolist())))
    print(f"  Institution-years: {len(inst_year):,} (without an incident: {no_incident:,}); with more than one "
          f"campus: {len(multi):,}; with campuses in more than one state: {int((states_per_inst > 1).sum()):,}")
    no_fte = int(inst_year["fte"].isna().sum())
    print(f"  Without an FTE (no rate): {no_fte:,}")
    print(f"  Saved to: {CAMPUS_YEAR_PATH}, {INSTITUTION_YEAR_PATH.name} and {INSTITUTION_OFFENSE_PATH.name}")
    return inst_year, inst_offense


def opt_value(value):
    """None for a missing value (None, NaN, NA), otherwise the value."""
    return None if value is None or pd.isna(value) else value


def main():
    parser = argparse.ArgumentParser(
        description="Create aggregate tables for dashboard"
    )
    parser.add_argument(
        "--ivy-only",
        action="store_true",
        help="Only aggregate Ivy League schools (overrides config)"
    )
    parser.add_argument(
        "--all-schools",
        action="store_true",
        help="Aggregate all schools (overrides config)"
    )

    args = parser.parse_args()

    # Determine processing mode: CLI args override config
    if args.all_schools:
        ivy_only = False
    elif args.ivy_only:
        ivy_only = True
    else:
        # Use config setting (PROCESS_ALL_SCHOOLS=True means ivy_only=False)
        ivy_only = not PROCESS_ALL_SCHOOLS

    print("=" * 60)
    print("Creating Aggregate Tables")
    print("=" * 60)
    print(f"Processing mode: {'Ivy League only' if ivy_only else 'ALL SCHOOLS (nationwide)'}")

    # The files this step reads, checked against their steps' records before reading
    dims = CURATED_DIR / "dims"
    inputs_before = provenance.Snapshot(
        "04", [FACTS_PATH, dims / "dim_institution.parquet", dims / "dim_enrollment.parquet", SOURCES_PATH,
               OLDER_PATH, LINKS_PATH, CLASS_PATH, MEDICAL_PATH, ABROAD_PATH, OVERRIDE_PATH,
               SITE_ENROLLMENT_PATH])

    # The old build record no longer describes the files about to be written
    provenance.invalidate(provenance.AGGS_MANIFEST)

    # Create aggregates: every school's full figures, for its profile
    school_agg, base = create_school_year_offense_agg(ivy_only=ivy_only)

    # Rankings and their totals count statistics that several campuses report
    # identically once, under the host campus
    dim_inst, enrollment = load_dim_institution(), load_enrollment_data()
    shared = create_shared_blocks(base, dim_inst, enrollment)
    print("\nCreating the aggregate that rankings count (shadow blocks removed)...")
    ranked_agg = build_school_agg(without_shadows(base, shared), dim_inst, enrollment)
    ivy_rankings = create_ivy_rankings(ranked_agg)

    # Create state and national rankings if processing all schools
    state_rankings = None
    national_rankings = None
    if not ivy_only:
        state_rankings = create_state_rankings(ranked_agg)
        national_rankings = create_national_rankings(ranked_agg)

    # Rates are per institution: all its campuses' counts per its FTE
    inst_year, _inst_offense = create_institution_tables(
        ranked_agg, shared, dim_inst, load_institution_enrollment(), load_campus_year_sources(), school_agg)

    aggs = CURATED_DIR / "aggs"
    written = [aggs / "agg_school_year_offense.parquet", SHARED_PATH, aggs / "agg_ivy_rankings.parquet",
               CAMPUS_YEAR_PATH, INSTITUTION_YEAR_PATH, INSTITUTION_OFFENSE_PATH, SITES_PATH, NEAR_PATH]
    if not ivy_only:
        written += [aggs / "agg_state_rankings.parquet", aggs / "agg_national_rankings.parquet"]
    provenance.write_aggs_manifest(all_schools=not ivy_only, snapshot=inputs_before, outputs=written)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"School-year-offense records: {len(school_agg):,}")
    print(f"Institution-years (rates): {len(inst_year):,}")
    if ivy_rankings is not None:
        print(f"Ivy rankings records: {len(ivy_rankings):,}")
    if state_rankings is not None:
        print(f"State rankings records: {len(state_rankings):,}")
    if national_rankings is not None:
        print(f"National rankings records: {len(national_rankings):,}")

    print("\n" + "-" * 60)
    print("Next steps:")
    print("1. Run: python 05_generate_json.py")


if __name__ == "__main__":
    sys.exit(provenance.run_locked("04", main))
