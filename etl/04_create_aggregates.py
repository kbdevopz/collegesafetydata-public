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

import os
import sys
import argparse
import pandas as pd
import duckdb
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import (CURATED_DIR, IVY_LEAGUE, GEO_FOR_ALL, US_STATES, PROCESS_ALL_SCHOOLS, OFFENSE_ORDER,
                    SHARED_MIN_NONZERO)
import provenance

# The one fact table that 02_transform_to_parquet.py writes
FACTS_PATH = CURATED_DIR / "facts" / "incidents.parquet"
# The DOE release each campus-year was taken from (02_transform_to_parquet.py)
SOURCES_PATH = CURATED_DIR / "dims" / "campus_year_sources.parquet"
# Every campus's counts in the older releases campus-years are taken from (02)
OLDER_PATH = CURATED_DIR / "dims" / "older_release_counts.parquet"
# Statistics reported identically by two or more campuses (find_shared_blocks)
SHARED_PATH = CURATED_DIR / "aggs" / "shared_blocks.parquet"

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
SHARED_RULES = ("same_block", "whole_year", "whole_year_older_release", "block_older_release")


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
                       sources: pd.DataFrame, older: pd.DataFrame) -> pd.DataFrame:
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
    shared = find_shared_blocks(base, dim_inst, enrollment, load_campus_year_sources(), load_older_release_counts())
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
    FTE and the share of students enrolled exclusively online (pctdeexc) per
    institution (base UNITID) and year, from dim_enrollment.parquet.
    """
    path = CURATED_DIR / "dims" / "dim_enrollment.parquet"
    df = pd.read_parquet(path)
    if "pctdeexc" not in df.columns:
        raise RuntimeError(f"{path} has no pctdeexc column. Run 02b_transform_ef_enrollment.py and "
                           "02a_transform_enrollment.py again, then this step.")
    return df[["unitid", "year", "fte", "pctdeexc"]]


def create_institution_tables(ranked_agg: pd.DataFrame, shared: pd.DataFrame, dim_inst: pd.DataFrame,
                              enrollment: pd.DataFrame, sources: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    counts are those of all its counting campuses, in any state, without
    shadow blocks and residence halls (the geo "All" of `ranked_agg`). An
    institution is listed for a year when at least one of its campuses
    counts that year, incidents or not.

    Each institution-year has a link campus, whose school page the rate
    rankings link to and whose name and state they show: the main campus
    (UNITID ending in 001) when it counts that year, otherwise the campus
    with the most incidents that year (ties: the lowest UNITID). Only a
    campus with a school file (dim_institution.parquet) can be the link.

    Saves and returns:
      agg_campus_year.parquet: year, unitid, base_unitid, state, count (the
        geo "All" total of every offense, 0 included)
      agg_institution_year.parquet: year, base_unitid, institution_name,
        link_unitid, state, campuses (that count that year), fte, pctdeexc
      agg_institution_year_offense.parquet: year, base_unitid, offense,
        offense_family, count (above 0 only)
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
    rows = []
    for (year, base_id), group in campus_years.groupby(["year", "base_unitid"]):
        candidates = group
        main_campus = int(base_id) * 1000 + 1
        if main_campus in set(candidates["unitid"].tolist()):
            link = main_campus
        else:
            link = int(candidates.sort_values(["count", "unitid"], ascending=[False, True]).iloc[0]["unitid"])
        rows.append({"year": int(year), "base_unitid": int(base_id), "institution_name": name_of[link],
                     "link_unitid": link, "state": opt_value(state_of.get(link)), "campuses": len(group)})
    inst_year = pd.DataFrame(rows, columns=["year", "base_unitid", "institution_name", "link_unitid", "state",
                                            "campuses"])

    # FTE and online share of each institution-year (none when NCES has no figure)
    enroll = enrollment.rename(columns={"unitid": "base_unitid"})
    inst_year = inst_year.merge(enroll, on=["base_unitid", "year"], how="left")
    inst_year = inst_year.astype({"year": "int16", "base_unitid": "int32", "link_unitid": "int32",
                                  "campuses": "int16", "fte": "Int32", "pctdeexc": "Int16"})
    inst_year = inst_year.sort_values(["year", "base_unitid"]).reset_index(drop=True)

    # The counts of every campus of the institution
    inst_offense = counted.assign(base_unitid=counted["unitid"] // 1000).groupby(
        ["year", "base_unitid", "offense", "offense_family"], as_index=False)["count"].sum()
    inst_offense = inst_offense[inst_offense["count"] > 0]
    listed = set(zip(inst_year["year"].astype(int).tolist(), inst_year["base_unitid"].astype(int).tolist()))
    unlisted = [k for k in zip(inst_offense["year"].astype(int).tolist(), inst_offense["base_unitid"].astype(int).tolist())
                if k not in listed]
    if unlisted:
        raise RuntimeError(f"{len(unlisted):,} institution counts belong to no listed institution-year "
                           f"(first: {unlisted[0]}). This is a bug in create_institution_tables.")
    inst_offense = inst_offense.astype({"year": "int16", "base_unitid": "int32", "count": "int32"})
    inst_offense = inst_offense.sort_values(["year", "base_unitid", "offense"]).reset_index(drop=True)

    campus_out.to_parquet(CAMPUS_YEAR_PATH, index=False)
    inst_year.to_parquet(INSTITUTION_YEAR_PATH, index=False)
    inst_offense.to_parquet(INSTITUTION_OFFENSE_PATH, index=False)

    multi = inst_year[inst_year["campuses"] > 1]
    states_per_inst = campus_years.assign(state=campus_years["unitid"].map(state_of)).groupby(
        ["year", "base_unitid"])["state"].nunique()
    no_incident = len(inst_year) - len(set(zip(inst_offense["year"].tolist(), inst_offense["base_unitid"].tolist())))
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
               OLDER_PATH])

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
        ranked_agg, shared, dim_inst, load_institution_enrollment(), load_campus_year_sources())

    aggs = CURATED_DIR / "aggs"
    written = [aggs / "agg_school_year_offense.parquet", SHARED_PATH, aggs / "agg_ivy_rankings.parquet",
               CAMPUS_YEAR_PATH, INSTITUTION_YEAR_PATH, INSTITUTION_OFFENSE_PATH]
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
