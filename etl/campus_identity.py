"""
Campus identity: names, search aliases and campuses DOE renumbered.

Used by 03_build_dimensions.py (part of its code fingerprint) and by
07_comprehensive_audit.py, which re-derives the ID-change candidates to check
etl/reference/campus_id_changes.csv.

Inputs (all DOE or NCES files, nothing typed in by hand except the review
decisions in campus_id_changes.csv):
- data/curated/dims/campus_names.parquet (02): every spelling of each campus's
  DOE identity columns (INSTNM, BRANCH, Address, City, State, ZIP, OPEID) in
  each Campus Safety and Security release read
- NCES IPEDS HD (Institutional Characteristics, directory) files of DATA_YEARS
  in data/raw/ipeds: the institution's alias field IALIAS, and INSTNM to
  repair a DOE name that DOE's file spells with an unreadable character

Names
- A release can spell a campus differently in its files (one file has an
  unreadable character, another the right one). The spelling with the fewest
  signs of a broken character set (text_problems) wins, then the one most of
  the release's files use. UTF-8 text read as Windows-1252 is repaired
  (clean_text).
- A campus's names are those of the newest release that lists it.
- campus_name is the campus's own DOE name (BRANCH) when it says more than the
  institution name: not a generic label such as "Main Campus" or "Branch
  Campus" (GENERIC_LABELS) and not already part of the institution name.

Aliases (searchable, not displayed as the name)
- every other name DOE gave the campus in any release (INSTNM and BRANCH:
  former names), and the institution's IPEDS IALIAS values (abbreviations),
  without the ones equal to the current names.

ID changes (detect_id_changes)
- DOE sometimes lists the same campus under a new UNITID_P from one release
  on. A pair of IDs is a candidate when they never appear in the same release,
  one is listed in the release right after one the other is listed in, they
  are in the same state and share a city, and they share an address or a
  campus name or have similar names. Each candidate's evidence is written to
  etl/reference/campus_id_changes.csv with a reviewed decision (link or
  reject); the site cross-links the two pages of each "link" pair. No figures
  are moved between IDs: each ID keeps the years DOE reported under it.
"""

from __future__ import annotations

import csv
import itertools
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

ETL_DIR = Path(__file__).resolve().parent
ID_CHANGES_PATH = ETL_DIR / "reference" / "campus_id_changes.csv"

# BRANCH values (normalized: norm) that name no campus
GENERIC_LABELS = {
    "", "main", "main campus", "main campus branch", "branch", "branch campus", "campus", "main location",
    "main site", "additional location", "na", "n a", "none", "online", "main campus location",
}

# Signs of text read in the wrong character set: the replacement character,
# UTF-8 read as Windows-1252, "=" or "<=" in place of an accented letter, and a
# lone non-ASCII character between spaces (other than a dash)
_PROBLEMS = re.compile(r"�|Ã.|â€|Â|(?<=[A-Za-z])=(?=[a-z])|<=| [^\x00-\x7f–—] ")
_MOJIBAKE = re.compile(r"Ã.|â€|Â")


def clean_text(value) -> str:
    """DOE text with spaces collapsed and UTF-8 that was read as Windows-1252 repaired."""
    s = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)
    s = s.replace(" ", " ")
    if _MOJIBAKE.search(s):
        try:
            s = s.encode("cp1252").decode("utf-8")
        except UnicodeError:
            pass
    return re.sub(r"\s+", " ", s).strip()


def text_problems(s: str) -> int:
    """How many signs of a broken character set the text has (0 for clean text)."""
    return len(_PROBLEMS.findall(s or ""))


def norm(s: str) -> str:
    """Lower case ASCII words: for comparing names (accents dropped, "&" read as "and")."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch if ord(ch) < 128 else ("" if unicodedata.combining(ch) else " ") for ch in s)
    s = s.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_STOP = {"the", "of", "at", "and", "in", "campus", "university", "college", "main", "inc", "llc"}
# Words that say what kind of school it is, not which one (for name_containment)
_KIND = _STOP | {"community", "state", "technical", "school", "institute", "center", "centre", "academy",
                 "saint", "education", "learning", "site", "location", "branch", "extension"}


def name_tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in _STOP}


def distinctive_tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in _KIND and len(t) >= 3}


_STREET = {"street": "st", "avenue": "ave", "road": "rd", "boulevard": "blvd", "drive": "dr", "highway": "hwy",
           "parkway": "pkwy", "suite": "ste", "north": "n", "south": "s", "east": "e", "west": "w",
           "lane": "ln", "place": "pl", "court": "ct", "circle": "cir"}


def norm_address(s: str) -> str:
    """An address as comparable words (street words abbreviated); "" for none or a PO box."""
    text = " ".join(_STREET.get(w, w) for w in norm(s).split())
    if not text or re.match(r"^(p ?o )?box\b", text):
        return ""
    return text


def same_address(a: str, b: str) -> bool:
    """Two normalized addresses are the same: equal, or the same street number and mostly the same words."""
    if not a or not b:
        return False
    if a == b:
        return True
    wa, wb = a.split(), b.split()
    if not (wa[0].isdigit() and wa[0] == wb[0]):
        return False
    sa, sb = set(wa[1:]), set(wb[1:])
    return len(sa & sb) / max(1, len(sa | sb)) >= 0.6


def campus_label(instnm: str, branch: str) -> str | None:
    """BRANCH when it names the campus and says more than the institution name, else None."""
    b = norm(branch)
    if b in GENERIC_LABELS:
        return None
    i = norm(instnm)
    if b == i or f" {b} " in f" {i} ":
        return None
    return branch


# ---------------------------------------------------------------------------
# Names by release
# ---------------------------------------------------------------------------

def best_spellings(names: pd.DataFrame) -> pd.DataFrame:
    """
    One identity row per campus and release (campus_names.parquet rows
    cleaned with clean_text): the spelling with the fewest text_problems, then
    the one most files use, then the first in sort order.
    """
    df = names.copy()
    for col in ("instnm", "branch", "address", "city", "state", "zip", "opeid"):
        df[col] = df[col].map(clean_text)
    df["problems"] = (df["instnm"].map(text_problems) + df["branch"].map(text_problems)
                      + df["city"].map(text_problems))
    # The cleaned spellings of two files may now be equal; add up their files
    keys = ["unitid", "release", "instnm", "branch", "address", "city", "state", "zip", "opeid", "problems"]
    df = df.groupby(keys, as_index=False)["files"].sum()
    df = df.sort_values(["unitid", "release", "problems", "files", "instnm", "branch", "address", "city"],
                        ascending=[True, True, True, False, True, True, True, True], kind="mergesort")
    return df.drop_duplicates(["unitid", "release"]).reset_index(drop=True)


def _wildcard(s: str) -> re.Pattern:
    """A pattern for a name with unreadable characters: each one matches any one character (or none)."""
    parts = re.split(r"�", s)
    return re.compile(".?".join(re.escape(p) for p in parts) + r"\Z", re.IGNORECASE)


def ipeds_directory(ipeds_dir: Path, years) -> tuple[pd.DataFrame, list[Path]]:
    """IPEDS HD rows (UNITID, INSTNM, IALIAS, year) of the given years, and the files read."""
    frames, read = [], []
    for year in years:
        path = ipeds_dir / str(year) / f"hd{year}.csv"
        if not path.is_file():
            continue
        try:
            path.read_bytes().decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            encoding = "cp1252"
        df = pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False)
        df.columns = [c.strip().upper() for c in df.columns]
        df = df[["UNITID", "INSTNM", "IALIAS"]].copy()
        df["year"] = int(year)
        frames.append(df)
        read.append(path)
    if not frames:
        return pd.DataFrame(columns=["UNITID", "INSTNM", "IALIAS", "year"]), read
    out = pd.concat(frames, ignore_index=True)
    out["UNITID"] = pd.to_numeric(out["UNITID"], errors="coerce")
    return out.dropna(subset=["UNITID"]).astype({"UNITID": "int64"}), read


def split_alias(value: str) -> list[str]:
    """IPEDS IALIAS holds several aliases in one field, separated by |, comma, semicolon, " / " or " or "."""
    parts = re.split(r"\s*[|;,]\s*|\s+/\s+|\s+or\s+|\s{2,}", clean_text(value))
    return [p.strip() for p in parts if len(norm(p)) >= 2]


def campus_identities(names: pd.DataFrame, hd: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Per campus (unitid): institution_name, campus_name, doe_branch, city,
    state, address (the newest release's best spelling, repaired), aliases
    (list) and releases (sorted release suffixes). Also the UNITIDs of what
    was repaired, by kind.
    """
    best = best_spellings(names)
    hd_names = {}
    for u, n in zip(hd["UNITID"].tolist(), hd["INSTNM"].tolist()):
        n = clean_text(n)
        if n and text_problems(n) == 0:
            hd_names.setdefault(int(u), set()).add(n)
    hd_alias = defaultdict(list)
    for u, a in sorted(zip(hd["UNITID"].tolist(), hd["IALIAS"].tolist()), key=lambda r: r[0]):
        for part in split_alias(a):
            if text_problems(part) == 0 and part not in hd_alias[int(u)]:
                hd_alias[int(u)].append(part)

    repaired = {"instnm_from_other_release": [], "instnm_from_ipeds": [], "branch_from_other_release": [],
                "city_from_other_release": [], "still_unreadable": []}
    records = []
    for unitid, rows in best.groupby("unitid", sort=True):
        rows = rows.sort_values("release")
        cur = rows.iloc[-1]
        instnm, branch, city = cur["instnm"], cur["branch"], cur["city"]

        def from_other(value: str, col: str) -> str | None:
            pat = _wildcard(value)
            for other in reversed(rows[col].tolist()):
                if text_problems(other) == 0 and pat.match(other):
                    return other
            return None

        if text_problems(instnm):
            fixed = from_other(instnm, "instnm")
            if fixed:
                repaired["instnm_from_other_release"].append(int(unitid))
            else:
                pat = _wildcard(instnm)
                matches = sorted(n for n in hd_names.get(int(unitid) // 1000, set()) if pat.match(n))
                if len(matches) == 1:
                    fixed = matches[0]
                    repaired["instnm_from_ipeds"].append(int(unitid))
            instnm = fixed or instnm
        if text_problems(branch):
            fixed = from_other(branch, "branch")
            if fixed:
                repaired["branch_from_other_release"].append(int(unitid))
                branch = fixed
        # A city must be a place name (one release has "2: No" for a city)
        if not re.search(r"[A-Za-z]", city) or re.search(r"\d|:", city) or text_problems(city):
            for other in reversed(rows["city"].tolist()):
                if re.search(r"[A-Za-z]", other) and not re.search(r"\d|:", other) and not text_problems(other):
                    if other != city:
                        repaired["city_from_other_release"].append(int(unitid))
                    city = other
                    break
        if text_problems(instnm) or text_problems(branch):
            repaired["still_unreadable"].append(int(unitid))

        label = campus_label(instnm, branch)
        seen = {norm(instnm)} | ({norm(label)} if label else set())
        candidates = []
        for _r, i_name, b_name in sorted(zip(rows["release"], rows["instnm"], rows["branch"]), reverse=True):
            candidates.append(i_name)
            if campus_label(i_name, b_name):
                candidates.append(b_name)
        if label is None and norm(branch) not in GENERIC_LABELS:
            candidates.append(branch)  # a name inside the institution name
        candidates += hd_alias.get(int(unitid) // 1000, [])
        aliases = []
        for alias in candidates:
            key = norm(alias)
            if not key or key in seen or text_problems(alias):
                continue
            seen.add(key)
            aliases.append(alias)
        records.append({
            "unitid": int(unitid),
            "institution_name": instnm,
            "campus_name": label,
            "doe_branch": branch,
            "city": city or None,
            "state": cur["state"] or None,
            "address": cur["address"] or None,
            "aliases": aliases,
            "releases": sorted(rows["release"].tolist()),
        })
    return pd.DataFrame(records), repaired


# ---------------------------------------------------------------------------
# ID changes
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "old_unitid", "new_unitid", "decision", "reason",
    "old_name", "new_name", "state", "old_city", "new_city", "old_address", "new_address",
    "old_releases", "new_releases", "transitions", "old_years", "new_years", "overlap_years",
    "address_match", "campus_name_match", "name_similarity", "name_containment", "opeid_match",
    "same_ipeds_parent", "old_last_total", "new_first_total", "overlap_totals",
]
EVIDENCE_COLUMNS = [c for c in CSV_COLUMNS if c not in ("decision", "reason")]
BOOL_COLUMNS = ("address_match", "campus_name_match", "opeid_match", "same_ipeds_parent")
NAME_SIMILARITY_MIN = 0.5
NAME_CONTAINMENT_MIN = 0.99  # every distinctive word of one ID's current name is in the other's names
CAMPUS_NAME_SIMILARITY_MIN = 0.8  # with the same campus name, enough without the same address


def _years_text(years) -> str:
    return " ".join(str(y) for y in sorted(years))


def detect_id_changes(names: pd.DataFrame, reported: dict[int, set[int]],
                      totals: dict[tuple[int, int], int], releases: list[str]) -> pd.DataFrame:
    """
    The candidate ID changes and their evidence (EVIDENCE_COLUMNS) from
    campus_names.parquet rows, the years each campus reported
    (campus_year_sources), its incident totals per year (facts, On-campus +
    Non-campus + Public property) and the releases read, oldest first.

    A pair is a candidate when the two IDs are never listed in the same
    release, one is listed in the release right after one the other is listed
    in (a transition), they are in the same state and share a city, and at
    least one of: the same street address, the same campus name (BRANCH, not
    a generic label), or name similarity >= NAME_SIMILARITY_MIN (share of
    name words in common, generic words left out).
    """
    best = best_spellings(names)
    order = {r: i for i, r in enumerate(releases)}
    best = best[best["release"].isin(order)]
    per = {}
    for u, rows in best.groupby("unitid"):
        rows = rows.sort_values("release")
        names_used = []
        for i_name, b_name in zip(rows["instnm"], rows["branch"]):
            names_used.append(i_name)
            if norm(b_name) not in GENERIC_LABELS:
                names_used.append(b_name)
        cur = rows.iloc[-1]
        label = campus_label(cur["instnm"], cur["branch"])
        per[int(u)] = {
            "rel": {order[r] for r in rows["release"]},
            "releases": list(rows["release"]),
            "state": cur["state"],
            "cities": {norm(c) for c in rows["city"] if norm(c)},
            "city": cur["city"],
            "addresses": {norm_address(a) for a in rows["address"]} - {""},
            "address": cur["address"],
            "tokens": set().union(*[name_tokens(n) for n in names_used]),
            "distinct_all": set().union(*[distinctive_tokens(n) for n in names_used]),
            "distinct_now": distinctive_tokens(f"{cur['instnm']} {label or ''}"),
            "branches": {norm(b) for b in rows["branch"]} - GENERIC_LABELS,
            "opeids": {o[:6] for o in rows["opeid"] if re.fullmatch(r"\d{8}", o or "")},
            "name": f"{cur['instnm']} - {label}" if label else cur["instnm"],
        }

    blocks = defaultdict(set)
    for u, p in per.items():
        for c in p["cities"]:
            blocks[(p["state"], c)].add(u)
    pairs = set()
    for members in blocks.values():
        for a, b in itertools.combinations(sorted(members), 2):
            if not (per[a]["rel"] & per[b]["rel"]):
                pairs.add((a, b))

    rows = []
    for a, b in sorted(pairs):
        pa, pb = per[a], per[b]
        trans = [i for i in range(len(releases) - 1)
                 if (i in pa["rel"] and i + 1 in pb["rel"]) or (i in pb["rel"] and i + 1 in pa["rel"])]
        if not trans:
            continue
        address_match = any(same_address(x, y) for x in pa["addresses"] for y in pb["addresses"])
        campus_match = bool(pa["branches"] & pb["branches"])
        union = pa["tokens"] | pb["tokens"]
        similarity = round(len(pa["tokens"] & pb["tokens"]) / len(union), 2) if union else 0.0
        if not (address_match or campus_match or similarity >= NAME_SIMILARITY_MIN):
            continue
        containment = round(max(
            len(pa["distinct_now"] & pb["distinct_all"]) / len(pa["distinct_now"]) if pa["distinct_now"] else 0.0,
            len(pb["distinct_now"] & pa["distinct_all"]) / len(pb["distinct_now"]) if pb["distinct_now"] else 0.0),
            2)
        old, new = (a, b) if min(pa["rel"]) <= min(pb["rel"]) else (b, a)
        po, pn = per[old], per[new]
        yo, yn = reported.get(old, set()), reported.get(new, set())
        rows.append({
            "old_unitid": old, "new_unitid": new,
            "old_name": po["name"], "new_name": pn["name"], "state": po["state"],
            "old_city": po["city"], "new_city": pn["city"],
            "old_address": po["address"], "new_address": pn["address"],
            "old_releases": " ".join(po["releases"]), "new_releases": " ".join(pn["releases"]),
            "transitions": " ".join(f"{releases[i]}>{releases[i + 1]}" for i in trans),
            "old_years": _years_text(yo), "new_years": _years_text(yn), "overlap_years": _years_text(yo & yn),
            "address_match": address_match, "campus_name_match": campus_match, "name_similarity": similarity,
            "name_containment": containment,
            "opeid_match": bool(po["opeids"] & pn["opeids"]), "same_ipeds_parent": old // 1000 == new // 1000,
            "old_last_total": int(totals.get((old, max(yo)), 0)) if yo else "",
            "new_first_total": int(totals.get((new, min(yn)), 0)) if yn else "",
            "overlap_totals": " ".join(f"{y}:{int(totals.get((old, y), 0))}/{int(totals.get((new, y), 0))}"
                                       for y in sorted(yo & yn)),
        })
    return pd.DataFrame(rows, columns=EVIDENCE_COLUMNS)


def auto_decision(cand: pd.DataFrame) -> pd.DataFrame:
    """
    The rule the review starts from (the CSV keeps the reviewed decision):
    link when (a) the address matches and the names agree (same campus name,
    name similarity >= NAME_SIMILARITY_MIN, or every distinctive word of one
    current name is in the other's names), or (b) the campus name is the same
    and name similarity >= CAMPUS_NAME_SIMILARITY_MIN; and neither ID has
    another such candidate. Otherwise reject, with the reason.
    """
    cand = cand.copy()
    yes = lambda col: cand[col].map(lambda v: str(v) in ("True", "yes", "1"))  # noqa: E731
    am, cm = yes("address_match"), yes("campus_name_match")
    sim, cont = cand["name_similarity"].astype(float), cand["name_containment"].astype(float)
    strong = ((am & (cm | (sim >= NAME_SIMILARITY_MIN) | (cont >= NAME_CONTAINMENT_MIN)))
              | (cm & (sim >= CAMPUS_NAME_SIMILARITY_MIN)))
    count = defaultdict(int)
    for o, n, s in zip(cand["old_unitid"], cand["new_unitid"], strong):
        if s:
            count[("old", o)] += 1
            count[("new", n)] += 1
    decisions, reasons = [], []
    for o, n, s, a, c, si in zip(cand["old_unitid"], cand["new_unitid"], strong, am, cm, sim):
        if s and count[("old", o)] == 1 and count[("new", n)] == 1:
            decisions.append("link")
            if a and c:
                reasons.append("same address and same campus name")
            elif a and si >= NAME_SIMILARITY_MIN:
                reasons.append(f"same address and similar names ({si:.2f})")
            elif a:
                reasons.append("same address; one current name's distinctive words are all in the other's names")
            else:
                reasons.append(f"same campus name and similar names ({si:.2f}); address differs")
        elif s:
            decisions.append("reject")
            reasons.append("ambiguous: an ID has more than one matching candidate")
        elif not a:
            decisions.append("reject")
            reasons.append("different address and names not close enough")
        else:
            decisions.append("reject")
            reasons.append(f"same address but different names ({si:.2f})")
    cand.insert(2, "decision", decisions)
    cand.insert(3, "reason", reasons)
    return cand[CSV_COLUMNS]


def evidence_text(df: pd.DataFrame) -> pd.DataFrame:
    """The columns as the CSV writes them, for comparing a re-derived table with the file."""
    out = df.copy()
    for c in CSV_COLUMNS:
        if c not in out.columns:
            continue
        if c in ("old_unitid", "new_unitid"):
            out[c] = out[c].astype("int64")
        elif c in ("name_similarity", "name_containment"):
            out[c] = out[c].map(lambda v: f"{float(v):.2f}")
        elif c in BOOL_COLUMNS:
            out[c] = out[c].map(lambda v: "yes" if str(v) in ("True", "yes", "1") else "no")
        else:
            out[c] = out[c].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    return out


def read_id_changes(path: Path = ID_CHANGES_PATH) -> pd.DataFrame:
    """The reviewed list as text (unitids as int)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [c for c in CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} has no column {', '.join(missing)}")
    df["old_unitid"] = df["old_unitid"].astype("int64")
    df["new_unitid"] = df["new_unitid"].astype("int64")
    return df[CSV_COLUMNS]


def write_id_changes(df: pd.DataFrame, path: Path = ID_CHANGES_PATH) -> None:
    out = evidence_text(df)[CSV_COLUMNS].sort_values(["old_unitid", "new_unitid"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        out.to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")


def candidates_from_curated(curated_dir: Path, years, geos) -> pd.DataFrame:
    """
    detect_id_changes on the curated files (02's campus_names,
    campus_year_sources and facts; totals over `geos`), as the CSV writes
    the evidence (evidence_text).
    """
    names = pd.read_parquet(curated_dir / "dims" / "campus_names.parquet")
    sources = pd.read_parquet(curated_dir / "dims" / "campus_year_sources.parquet", columns=["unitid", "year"])
    sources = sources[sources["year"].isin(list(years))]
    reported = {int(u): set(int(y) for y in g["year"]) for u, g in sources.groupby("unitid")}
    facts = pd.read_parquet(curated_dir / "facts" / "incidents.parquet", columns=["unitid", "year", "geo", "count"])
    facts = facts[facts["geo"].isin(list(geos))]
    totals = {(int(u), int(y)): int(c) for (u, y), c in facts.groupby(["unitid", "year"])["count"].sum().items()}
    releases = sorted(names["release"].unique())
    return evidence_text(detect_id_changes(names, reported, totals, releases))


def compare_with_review(found: pd.DataFrame, reviewed: pd.DataFrame) -> dict[str, list]:
    """The pairs only re-derived (new), only in the CSV (gone), and in both with different evidence (changed)."""
    key = ["old_unitid", "new_unitid"]
    merged = found[EVIDENCE_COLUMNS].merge(reviewed[EVIDENCE_COLUMNS], on=key, how="outer",
                                           suffixes=("", "_csv"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    differs = pd.Series(False, index=both.index)
    for c in EVIDENCE_COLUMNS:
        if c not in key:
            differs |= both[c] != both[f"{c}_csv"]
    return {
        "new": merged.loc[merged["_merge"] == "left_only", key].values.tolist(),
        "gone": merged.loc[merged["_merge"] == "right_only", key].values.tolist(),
        "changed": both.loc[differs, key].values.tolist(),
    }


def main() -> int:
    """
    Refresh etl/reference/campus_id_changes.csv from data/curated (run after
    02): unchanged pairs keep their reviewed decision and reason, new or
    changed pairs get auto_decision's, marked "proposed: ..." for review.
    """
    import sys
    sys.path.insert(0, str(ETL_DIR))
    from config import CURATED_DIR, DATA_YEARS, GEO_FOR_ALL
    found = candidates_from_curated(CURATED_DIR, DATA_YEARS, GEO_FOR_ALL)
    proposed = evidence_text(auto_decision(found))
    if ID_CHANGES_PATH.is_file():
        reviewed = read_id_changes()
        diff = compare_with_review(found, evidence_text(reviewed))
        fresh = {tuple(k) for k in diff["new"] + diff["changed"]}
        keep = reviewed.set_index(["old_unitid", "new_unitid"])[["decision", "reason"]]
        rows = []
        for rec in proposed.to_dict("records"):
            k = (rec["old_unitid"], rec["new_unitid"])
            if k in fresh or k not in keep.index:
                rec["reason"] = f"proposed: {rec['reason']}"
            else:
                rec["decision"], rec["reason"] = keep.loc[k, "decision"], keep.loc[k, "reason"]
            rows.append(rec)
        proposed = pd.DataFrame(rows, columns=CSV_COLUMNS)
        print(f"{len(diff['new'])} new, {len(diff['gone'])} gone, {len(diff['changed'])} changed pairs")
    write_id_changes(proposed)
    counts = proposed["decision"].value_counts().to_dict()
    print(f"Wrote {ID_CHANGES_PATH} ({len(proposed)} pairs: {counts}). Review rows whose reason starts "
          "with 'proposed:', set decision to link or reject, and drop the 'proposed: ' prefix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
