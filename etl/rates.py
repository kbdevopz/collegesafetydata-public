"""
Rates (config.py, "Rates"): 3-year window rates of on-campus incidents per
10,000 on-campus FTE-years with their intervals, the comparison with the
national rate and with the peer group's rate, unusual-year flags, the
ordered national, state and peer-type lists with rank ranges, single-year rates (a
school page's trend) and the count flag's reference.

05_generate_json.py writes what build() returns; 07_comprehensive_audit.py
checks every published figure with its own code.

Exact where the rules are exact: rates, national and peer rates, expected
counts, list membership and the order of the lists are computed on integers
and fractions; intervals and z statistics are floating point. Nothing here
is random.
"""

import math
from collections import defaultdict
from fractions import Fraction
from functools import lru_cache

import pandas as pd

from config import (CURATED_DIR, DATA_YEARS, US_STATES, MIN_FTE_FOR_RATE, SUMMARY_FAMILIES, RATE_CODES,
                    RATE_RAMP, RATE_CI_LEVEL, RATE_SPREAD, RATE_SKIP_YEARS, LIST_CODES, LIST_MIN_EXPECTED, LIST_ALPHA,
                    STATE_LIST_MIN_MEMBERS, TYPE_LIST_MIN_MEMBERS, MEDICAL_CAMPUS_SHARE, SHARED_SITE_MAX_SHARE, FLAG_OFFENSES, FLAG_GEOS,
                    FLAG_MIN_COUNT, FLAG_MIN_OTHER_YEARS, FLAG_P, FLAG_C, FLAG_MIN_MEAN, COUNT_FLAG_PERCENTILE,
                    PEER_TYPES, rate_windows, dispersion_c, summary_codes)

ALPHA = 1 - RATE_CI_LEVEL
# The verdicts: the rate's interval wholly above, wholly below, or around the reference rate;
# undetermined (the two on-campus FTE estimates disagree) and withheld (why "shared": no comparison)
ABOVE, BELOW, NOT_DISTINGUISHABLE, UNDETERMINED, WITHHELD = "above", "below", "nd", "undetermined", "withheld"
GEO_KEYS = {"On-campus": "on", "Non-campus": "non", "Public property": "pub"}


def code_of(offense: str) -> str:
    """The site code of an offense ("Aggravated Assault" -> "aggravated_assault")."""
    return offense.lower().replace(" ", "_")


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------

def ramp(m: float) -> float:
    """g(m) = min(cap, max(1, m / start)) of the variance function (config.py, RATE_RAMP)."""
    start, cap = RATE_RAMP
    return min(float(cap), max(1.0, m / start))


def phi(n: float, years: int, c: float) -> float:
    """The variance-to-mean ratio of a window total n over `years` years: 1 + c g(n/T) sqrt(n/T)."""
    m = n / years
    return 1.0 + c * ramp(m) * math.sqrt(m)


def variance(mu: float, years: int, c: float) -> float:
    """The variance of a window total with mean mu over `years` years: T (m + c g(m) m^1.5), m = mu / T."""
    m = mu / years
    return years * (m + c * ramp(m) * m ** 1.5)


def sample_variance(counts) -> Fraction:
    """s^2 of an institution's yearly counts in a window (n - 1 denominator), exactly; 0 for one year."""
    values = [Fraction(v) for v in counts]
    if len(values) < 2:
        return Fraction(0)
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def window_phi(n, years: int, c: float, spread: Fraction = Fraction(0)) -> tuple[float, bool]:
    """
    The variance-to-mean ratio of a window total n (config.py, RATE_SPREAD):
    the larger of the model's phi(n) and T s^2 / n, s^2 = `spread` (the
    sample variance of the window's yearly counts); (phi, whether the yearly
    counts give it). n = 0: the model's.
    """
    model = phi(float(n), years, c)
    if RATE_SPREAD == "max" and n and spread:
        own = float(years * Fraction(spread) / Fraction(n))
        if own > model:
            return own, True
    return model, False


def gamma_p(a: float, x: float) -> float:
    """The regularized lower incomplete gamma function P(a, x), a > 0: series below a + 1, else continued fraction."""
    if x <= 0:
        return 0.0
    log_front = a * math.log(x) - x - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        n = 0
        while True:
            n += 1
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-16 or n > 100000:
                break
        return min(1.0, math.exp(log_front) * total)
    # Lentz's continued fraction for Q(a, x)
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return max(0.0, 1.0 - math.exp(log_front) * h)


def gamma_quantile(a: float, q: float) -> float:
    """The x with P(a, x) = q (shape a, scale 1), by bisection."""
    lo, hi = 0.0, a + 20 * math.sqrt(a + 1) + 20
    while gamma_p(a, hi) < q:
        lo, hi = hi, 2 * hi
    for _ in range(300):
        mid = (lo + hi) / 2
        if gamma_p(a, mid) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-14 * max(1.0, hi):
            break
    return (lo + hi) / 2


@lru_cache(maxsize=None)
def count_interval(n, years: int, c: float, spread: Fraction = Fraction(0)) -> tuple[float, float]:
    """
    The RATE_CI_LEVEL interval of a window total n over `years` years
    (config.py): phi = window_phi(n, spread), m = n / phi; lower phi G(alpha/2;
    m), 0 for n = 0; upper phi G(1 - alpha/2; m + 1).
    """
    f, _ = window_phi(n, years, c, spread)
    nf = float(n)
    m = nf / f
    lower = 0.0 if nf == 0 else f * gamma_quantile(m, ALPHA / 2)
    upper = f * gamma_quantile(m + 1, 1 - ALPHA / 2)
    return lower, upper


def half_up(x: Fraction, places: int) -> float:
    """The fraction x rounded half up to `places` decimals."""
    q = 10 ** places
    return math.floor(x * q + Fraction(1, 2)) / q


def rate_value(n: int, fte_years: int) -> float:
    """n per 10,000 of fte_years, half up to 2 decimals, exactly: floor((2 n 10^6 + F) / (2 F)) / 100."""
    return ((2 * n * 10 ** 6 + fte_years) // (2 * fte_years)) / 100


def round2(x: float) -> float:
    """An interval bound half up to 2 decimals: floor(x 100 + 0.5) / 100."""
    return math.floor(x * 100 + 0.5) / 100


def round4(x: float) -> float:
    """An interval bound half up to 4 decimals: floor(x 10^4 + 0.5) / 10^4."""
    return math.floor(x * 10000 + 0.5) / 10000


def normal_quantile(p: float) -> float:
    """The standard normal quantile (Acklam's approximation, refined by one Halley step on erfc)."""
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    if p < 0.02425:
        t = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * t + c[1]) * t + c[2]) * t + c[3]) * t + c[4]) * t + c[5]) / \
            ((((d[0] * t + d[1]) * t + d[2]) * t + d[3]) * t + 1)
    elif p > 1 - 0.02425:
        t = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * t + c[1]) * t + c[2]) * t + c[3]) * t + c[4]) * t + c[5]) / \
            ((((d[0] * t + d[1]) * t + d[2]) * t + d[3]) * t + 1)
    else:
        t = p - 0.5
        r = t * t
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * t / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    e = 0.5 * math.erfc(-x / math.sqrt(2)) - p
    u = e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)
    return x - u / (1 + x * u / 2)


def critical_z(n: int) -> float:
    """The Bonferroni critical value of a list of n members: Phi^-1(1 - LIST_ALPHA / (2 (n - 1)))."""
    return normal_quantile(1 - LIST_ALPHA / (2 * (n - 1)))


def nb_tail(count: int, mu: float, c: float) -> float:
    """P(Y >= count) for a negative binomial Y with mean mu > 0 and variance mu + c mu^1.5."""
    if count <= 0:
        return 1.0
    k = mu * mu / (c * mu ** 1.5)
    log_p = k * math.log(k / (k + mu))
    r = mu / (k + mu)
    below, p = 0.0, math.exp(log_p)
    for y in range(count):
        below += p
        p *= (y + k) / (y + 1) * r
    return max(0.0, 1.0 - below)


def median(values: list) -> float:
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def percentile_linear(values: list[Fraction], q: int) -> Fraction:
    """The q-th percentile of `values` by linear interpolation (numpy's default), exactly."""
    s = sorted(values)
    h = Fraction(q, 100) * (len(s) - 1)
    lo = math.floor(h)
    if lo + 1 >= len(s):
        return s[lo]
    return s[lo] + (h - lo) * (s[lo + 1] - s[lo])


def verdict(n, fte_years: int, years: int, c: float, ref: Fraction, spread: Fraction = Fraction(0)) -> str:
    """
    ABOVE when the interval's lower bound per FTE-year is above the reference
    rate `ref` (incidents per FTE-year, exact), BELOW when the upper bound is
    below it, otherwise NOT_DISTINGUISHABLE. Unrounded.
    """
    lower, upper = count_interval(n, years, c, spread)
    if lower * ref.denominator > ref.numerator * fte_years:
        return ABOVE
    if upper * ref.denominator < ref.numerator * fte_years:
        return BELOW
    return NOT_DISTINGUISHABLE


def z_statistic(ni: int, fi: int, nj: int, fj: int, years: int, c: float, si: Fraction = Fraction(0),
                sj: Fraction = Fraction(0)) -> float:
    """
    The pairwise statistic of members i and j: (ni/fi - nj/fj) / sqrt(Vi / fi^2 + Vj / fj^2),
    Vi = max(V0(r fi), T si) with si member i's yearly s^2 (config.py, RATE_SPREAD), r = (ni + nj) /
    (fi + fj), V0 = variance; 0 when both counts are 0.
    """
    r = (ni + nj) / (fi + fj)
    vi = max(variance(r * fi, years, c), float(years * si))
    vj = max(variance(r * fj, years, c), float(years * sj))
    v = vi / fi ** 2 + vj / fj ** 2
    if v <= 0:
        return 0.0
    return (ni / fi - nj / fj) / math.sqrt(v)


def rank_ranges(members: list[tuple], years: int, c: float) -> list[tuple[int, int]]:
    """
    For members [(n, FTE-years, position[, s^2 of its yearly counts])] (one
    list, any order), each one's rank range: lo = 1 + the members
    significantly above it, hi = n - the members significantly below it (z
    beyond critical_z(n)), widened to hold its position.
    """
    n = len(members)
    if n == 1:
        return [(1, 1)]
    zc = critical_z(n)
    above = [0] * n
    below = [0] * n
    spread = [Fraction(m[3]) if RATE_SPREAD == "max" and len(m) > 3 else Fraction(0) for m in members]
    for i in range(n):
        ni, fi = members[i][0], members[i][1]
        for j in range(i + 1, n):
            nj, fj = members[j][0], members[j][1]
            z = z_statistic(ni, fi, nj, fj, years, c, spread[i], spread[j])
            if z > zc:
                below[i] += 1
                above[j] += 1
            elif -z > zc:
                below[j] += 1
                above[i] += 1
    return [(min(1 + above[i], members[i][2]), max(n - below[i], members[i][2])) for i in range(n)]


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

class RateInputs:
    """
    04's institution tables: per institution-year (agg_institution_year) its
    record, and per institution-year and offense (agg_institution_year_offense)
    its counts by geography, medical-center and shared figures; and each
    institution's name (base_name: its 001 campus's in dim_institution, else
    its lowest campus's).
    """

    VALUES = ("count", "count_on", "count_non", "count_pub", "medical_on", "shared_in_on", "shared_out_on")

    def __init__(self):
        aggs = CURATED_DIR / "aggs"
        years = pd.read_parquet(aggs / "agg_institution_year.parquet")
        self.rec = {(int(r["year"]), int(r["base_unitid"])): r for r in years.to_dict("records")}
        offenses = pd.read_parquet(aggs / "agg_institution_year_offense.parquet")
        self.offense_values: dict[tuple[int, int], dict[str, tuple]] = defaultdict(dict)
        for row in offenses[["year", "base_unitid", "offense", *self.VALUES]].itertuples(index=False):
            self.offense_values[(int(row[0]), int(row[1]))][row[2]] = tuple(int(v) for v in row[3:])
        self.family = dict(zip(offenses["offense"], offenses["offense_family"]))
        self.years_of: dict[int, list[int]] = defaultdict(list)
        for y, b in sorted(self.rec):
            self.years_of[b].append(y)
        self.data_years = sorted({y for y, _b in self.rec if y in DATA_YEARS})
        # The reviewed student figure that covers a shared-site campus in a year (03's table):
        # {(campus, year): (students, kind, figure_year, derived)}
        site = pd.read_parquet(CURATED_DIR / "dims" / "dim_shared_site_enrollment.parquet")
        self.site_figure: dict[tuple[int, int], tuple[int, str, int, bool]] = {
            (int(u), int(y)): (int(n), str(k), int(fy), bool(d)) for u, y, n, k, fy, d in zip(
                site["unitid"], site["year"], site["students"], site["kind"], site["figure_year"], site["derived"])}
        dim_inst = pd.read_parquet(CURATED_DIR / "dims" / "dim_institution.parquet",
                                   columns=["unitid", "institution_name", "campus_name"])
        self.base_name: dict[int, str] = {}
        for u, name in sorted(zip(dim_inst["unitid"].astype(int).tolist(), dim_inst["institution_name"].tolist())):
            if u % 1000 == 1 or u // 1000 not in self.base_name:
                self.base_name[u // 1000] = str(name)
        # A campus's name in the shared-site notes: its DOE campus name, else its institution's name
        self.campus_name: dict[int, str] = {
            int(u): str(c) if isinstance(c, str) and c.strip() else str(i)
            for u, i, c in zip(dim_inst["unitid"], dim_inst["institution_name"], dim_inst["campus_name"])}
        # Hospitals at a main campus whose place in the reported figures is not established (03's list,
        # etl/reference/hospital_unresolved.csv): {base: {name, firstYear, lastYear, known, source}}
        hosp = pd.read_parquet(CURATED_DIR / "dims" / "dim_hospital_unresolved.parquet")
        self.hospital_unresolved: dict[int, dict] = {
            int(u): {"name": str(h), "firstYear": int(a), "lastYear": int(b), "known": str(k), "source": str(s)}
            for u, a, b, h, k, s in zip(hosp["unitid"], hosp["first_year"], hosp["last_year"], hosp["hospital"],
                                        hosp["known"], hosp["source"])}

    def values(self, code: str, year: int, base: int) -> tuple:
        """The VALUES of a rate code (RATE_CODES: the sum over its offenses) in an institution-year."""
        mine = self.offense_values.get((year, base), {})
        out = [0] * len(self.VALUES)
        for offense in RATE_CODES[code]:
            for i, v in enumerate(mine.get(offense, ())):
                out[i] += v
        return tuple(out)

    def offense_count(self, offense: str, year: int, base: int, geo: str) -> int:
        """An offense's count at one geography (GEO_KEYS) of an institution-year."""
        v = self.offense_values.get((year, base), {}).get(offense)
        return 0 if v is None else v[{"on": 1, "non": 2, "pub": 3}[geo]]

    def count_codes(self, year: int, base: int) -> dict[str, int]:
        """{code: count, all geographies} for the summary codes and offenses, as the count views add them up."""
        out: dict[str, int] = defaultdict(int)
        for offense, v in self.offense_values.get((year, base), {}).items():
            out[code_of(offense)] += v[0]
            for code in summary_codes(offense, self.family[offense]):
                out[code] += v[0]
        return out


def opt(value):
    return None if value is None or (not isinstance(value, str) and pd.isna(value)) else value


def rated_year(rec: dict) -> bool:
    """Whether an institution-year has a denominator of at least MIN_FTE_FOR_RATE, no rule and a state in US_STATES."""
    fte = opt(rec.get("rate_fte"))
    return (fte is not None and int(fte) >= MIN_FTE_FOR_RATE and opt(rec.get("rate_excluded")) is None
            and opt(rec.get("state")) in US_STATES)


def year_status(rec: dict | None, year: int) -> str:
    """Why an institution-year has no single-year rate ("" when it has one)."""
    if rec is None:
        return "missingYears"
    if opt(rec.get("state")) not in US_STATES:
        return "scope"
    fte = opt(rec.get("rate_fte"))
    if fte is None or int(fte) < MIN_FTE_FOR_RATE:
        return "size"
    if opt(rec.get("rate_excluded")) is not None:
        return "excluded"
    if year in RATE_SKIP_YEARS:
        return "skippedYear"
    return ""


def uncertain_reason(rec: dict) -> str | None:
    """"own" when the institution's on-campus FTE is uncertain, "pooled" when only a pooled institution's is."""
    if not bool(rec.get("online_uncertain")):
        return None
    return "own" if bool(rec.get("online_uncertain_own")) else "pooled"


# --------------------------------------------------------------------------
# Unusual years
# --------------------------------------------------------------------------

def unusual_years(inp: RateInputs) -> dict[int, list[dict]]:
    """
    {base: [{year, offense, geo, count, usual}]} (config.py, FLAG_*): every
    institution, every offense of FLAG_OFFENSES at every geography of
    FLAG_GEOS, every year it is listed (agg_institution_year); usual is the
    median of its other listed years (0 for a year without an incident).
    """
    out = {}
    for base, years in sorted(inp.years_of.items()):
        years = [y for y in years if y in DATA_YEARS]
        flags = []
        for offense in FLAG_OFFENSES:
            for geo in FLAG_GEOS:
                key = GEO_KEYS[geo]
                counts = {y: inp.offense_count(offense, y, base, key) for y in years}
                for y in years:
                    n = counts[y]
                    others = [counts[o] for o in years if o != y]
                    if n < FLAG_MIN_COUNT or len(others) < FLAG_MIN_OTHER_YEARS:
                        continue
                    usual = median(others)
                    if nb_tail(n, max(FLAG_MIN_MEAN, usual), FLAG_C) < FLAG_P:
                        flags.append({"year": y, "offense": code_of(offense), "geo": geo, "count": n,
                                      "usual": usual})
        if flags:
            out[base] = sorted(flags, key=lambda f: (f["year"], f["offense"], FLAG_GEOS.index(f["geo"])))
    return out


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------

def named(inp: RateInputs, recs: list[dict], column: str) -> list[dict]:
    """[{id, name}] of the bases 04 lists in `column` (space separated) in any of `recs`, by base."""
    ids = sorted({int(x) for r in recs for x in str(opt(r.get(column)) or "").split()})
    return [{"id": i, "name": inp.base_name.get(i)} for i in ids]


def shared_site(inp: RateInputs, recs: list[dict], years: range) -> dict | None:
    """
    A guest's or participant's shared sites in a window (04's
    shared_out_sites; config.py, SHARED_SITE_MAX_SHARE), or None: years (the
    window's years it has such a campus), students (the sum of 04's
    shared_site_students over those years; None when a year has no reviewed
    figure), upperBound (any of its figures is an upper bound, whether or not
    every year has one), exempt (students at most SHARED_SITE_MAX_SHARE of
    the window's FTE-years, the sum of rate_fte: compared and listed as
    usual) and figures (each such campus and year, by year and campus:
    {year, unitid, name (the campus's DOE name, else its institution's),
    students, figureYear (the figure's own year: the year itself, or one
    within SHARED_SITE_FIGURE_YEARS), upperBound, derived}; students and
    figureYear None without a figure).
    """
    site_years = [(y, r) for y, r in zip(years, recs) if opt(r.get("shared_out_sites")) is not None]
    if not site_years:
        return None
    figures = [opt(r.get("shared_site_students")) for _y, r in site_years]
    students = None if any(f is None for f in figures) else sum(int(f) for f in figures)
    num, den = SHARED_SITE_MAX_SHARE
    fte_years = sum(int(r["rate_fte"]) for r in recs)
    each = []
    for y, r in site_years:
        for u in sorted(int(x) for x in str(r["shared_out_sites"]).split()):
            f = inp.site_figure.get((u, y))
            each.append({"year": y, "unitid": u, "name": inp.campus_name.get(u),
                         "students": None if f is None else f[0], "figureYear": None if f is None else f[2],
                         "upperBound": f is not None and f[1] == "upper bound", "derived": f is not None and f[3]})
    return {"years": [y for y, _r in site_years], "students": students,
            "upperBound": any(f["upperBound"] for f in each),
            "exempt": students is not None and students * den <= fte_years * num, "figures": each}


def window_status(inp: RateInputs, base: int, window: tuple[int, int]) -> dict:
    """
    An institution's status in a window: {"status": "rated", "why": "",
    "shared" or "online", and the shared-site notes} for one in the window's
    population, else "missingYears" (not in DOE's data every year of the
    window; years = the ones it is in), "scope" (link campus not in
    US_STATES), "size" (denominator under MIN_FTE_FOR_RATE in a year) or
    "excluded" (a rule in a year: rules {year: rule}).

    why is "shared" for a guest or participant at a shared site in a year of
    the window (shared_site) that is not exempt, else "online" for an
    uncertain on-campus FTE in a year, else "". The notes, each when not
    empty: sharedInWith (the guests at the shared sites it owns),
    sharedOutWith (the owners or other participants of the sites it is a
    guest or participant of), sharedSite (shared_site) and coLocated (the
    institutions whose students its rate adds, or would add with an FTE,
    because their campuses at a shared site copy its own): [{id, name}];
    hospitalUnresolved {name, years}: a hospital at its main campus whose
    place in the reported figures is not established, in those years of the
    window (etl/reference/hospital_unresolved.csv). The rate is as usual.
    """
    years = range(window[0], window[1] + 1)
    recs = [inp.rec.get((y, base)) for y in years]
    if any(r is None for r in recs):
        return {"status": "missingYears", "years": [y for y, r in zip(years, recs) if r is not None]}
    if opt(recs[-1].get("state")) not in US_STATES:
        return {"status": "scope"}
    if any(opt(r.get("rate_fte")) is None or int(r["rate_fte"]) < MIN_FTE_FOR_RATE for r in recs):
        return {"status": "size", "fteByYear": {str(y): opt(r.get("rate_fte")) for y, r in zip(years, recs)}}
    rules = {str(y): str(r["rate_rule"]) for y, r in zip(years, recs) if opt(r.get("rate_excluded")) is not None}
    if rules:
        return {"status": "excluded", "rules": rules}
    site = shared_site(inp, recs, years)
    if site is not None and not site["exempt"]:
        why = "shared"
    else:
        why = "online" if any(bool(r.get("online_uncertain")) for r in recs) else ""
    out = {"status": "rated", "why": why}
    for key, column in (("sharedInWith", "shared_in_with"), ("sharedOutWith", "shared_out_with")):
        found = named(inp, recs, column)
        if found:
            out[key] = found
    if site is not None:
        out["sharedSite"] = site
    co_located = named(inp, recs, "co_located_with")
    if co_located:
        out["coLocated"] = co_located
    hospital = inp.hospital_unresolved.get(base)
    if hospital is not None:
        in_window = [y for y in years if hospital["firstYear"] <= y <= hospital["lastYear"]]
        if in_window:
            out["hospitalUnresolved"] = {"name": hospital["name"], "years": in_window}
    return out


# The notes of a window status that the window files repeat in each entry: the shared-site notes and the
# unresolved-hospital note
SHARED_NOTES = ("sharedInWith", "sharedOutWith", "sharedSite", "coLocated", "hospitalUnresolved")


class WindowCode:
    """One window and rate code: every rated institution's figures, the national and peer rates, the lists."""

    def __init__(self, inp: RateInputs, window: tuple[int, int], code: str, members: dict[int, dict],
                 flags: dict[int, list[dict]]):
        self.window, self.code = window, code
        self.years = list(range(window[0], window[1] + 1))
        self.T = len(self.years)
        self.c = dispersion_c(code)
        self.rows: dict[int, dict] = {}
        offenses = {code_of(o) for o in RATE_CODES[code]}
        for base, status in members.items():
            recs = [inp.rec[(y, base)] for y in self.years]
            vals = [inp.values(code, y, base) for y in self.years]
            n = sum(v[1] for v in vals)
            smaller = [opt(r.get("rate_fte_smaller")) for r in recs]
            row = {
                "base": base, "unitid": int(recs[-1]["link_unitid"]), "name": str(recs[-1]["institution_name"]),
                "state": str(recs[-1]["state"]), "peerType": str(recs[-1]["peer_type"]),
                "n": n, "nByYear": [v[1] for v in vals],
                "nNoncampus": sum(v[2] for v in vals), "nPublic": sum(v[3] for v in vals),
                "F": sum(int(r["rate_fte"]) for r in recs), "fteByYear": [int(r["rate_fte"]) for r in recs],
                "Fsmall": None if any(s is None for s in smaller) else sum(int(s) for s in smaller),
                "medical": sum(v[4] for v in vals), "sharedIn": sum(v[5] for v in vals),
                "sharedOut": sum(v[6] for v in vals),
                "uncertain": {str(y): uncertain_reason(r) for y, r in zip(self.years, recs) if uncertain_reason(r)},
            }
            num, den = MEDICAL_CAMPUS_SHARE
            if status["why"] in ("shared", "online"):
                row["why"] = status["why"]
            elif n and row["medical"] * den >= n * num:
                row["why"] = "medical_campus"
            else:
                row["why"] = ""
            row["notes"] = {k: status[k] for k in SHARED_NOTES if k in status}
            row["flags"] = [f for f in flags.get(base, []) if f["geo"] == "On-campus" and f["offense"] in offenses
                            and window[0] <= f["year"] <= window[1]]
            # s^2 of the yearly counts (config.py, RATE_SPREAD)
            row["spread"] = sample_variance(row["nByYear"])
            if code in ("violent", "criminal_xmvt"):
                parts = RATE_CODES["violent"] if code == "violent" else ("Motor Vehicle Theft",)
                row["composition"] = {code_of(o): sum(inp.offense_count(o, y, base, "on") for y in self.years)
                                      for o in parts}
            self.rows[base] = row
        # The national rate and the peer rates: rated institutions without a reason, medical_campus or shared
        ref = [r for r in self.rows.values() if r["why"] in ("", "medical_campus", "shared")]
        self.natl_n, self.natl_f = sum(r["n"] for r in ref), sum(r["F"] for r in ref)
        self.natl = Fraction(self.natl_n, self.natl_f)
        self.peer = {}
        for key in PEER_TYPES:
            part = [r for r in ref if r["peerType"] == key]
            pf = sum(r["F"] for r in part)
            if pf:
                self.peer[key] = (sum(r["n"] for r in part), pf, len(part))
        self.composition = None
        if code in ("violent", "criminal_xmvt"):
            parts = RATE_CODES["violent"] if code == "violent" else ("Motor Vehicle Theft",)
            self.composition = {code_of(o): sum(r["composition"][code_of(o)] for r in ref) for o in parts}
        for r in self.rows.values():
            self._compare(r)
        self.list_members: list[int] = []
        self.not_placed: list[int] = []
        self.zc = None
        self.state_lists: dict[str, int] = {}
        self.type_lists: dict[str, int] = {}
        if code in LIST_CODES:
            self._lists()

    def _verdicts(self, n, r: dict, ref: Fraction, spread: Fraction) -> tuple[str, dict]:
        """The verdict of count n against `ref`; for an uncertain on-campus FTE, both estimates (config.py)."""
        larger = verdict(n, r["F"], self.T, self.c, ref, spread)
        if r["why"] != "online":
            return larger, {}
        if r["Fsmall"] is None:
            return UNDETERMINED, {"verdictLargerFte": larger, "undeterminedReason": "noSecondEstimate"}
        smaller = verdict(n, r["Fsmall"], self.T, self.c, ref, spread)
        extra = {"verdictLargerFte": larger, "verdictSmallerFte": smaller}
        if larger == smaller:
            return larger, extra
        return UNDETERMINED, extra | {"undeterminedReason": "estimates"}

    def _compare(self, r: dict) -> None:
        lower, upper = count_interval(r["n"], self.T, self.c, r["spread"])
        r["phi"], r["phiFromYears"] = window_phi(r["n"], self.T, self.c, r["spread"])
        r["lo"], r["hi"] = round2(lower / r["F"] * 10000), round2(upper / r["F"] * 10000)
        r["lo4"], r["hi4"] = round4(lower / r["F"] * 10000), round4(upper / r["F"] * 10000)
        r["rate"] = rate_value(r["n"], r["F"])
        r["E"] = half_up(self.natl * r["F"], 1)
        peer = self.peer.get(r["peerType"])
        if r["why"] == "shared":
            # Students at a shared site the rate cannot place: no comparison (config.py)
            r["verdict"], r["dual"] = WITHHELD, {}
            r["peerVerdict"], r["peerDual"] = (WITHHELD if peer else None), {}
            r["verdictWithoutFlagged"] = None
            return
        r["verdict"], r["dual"] = self._verdicts(r["n"], r, self.natl, r["spread"])
        if peer:
            r["peerVerdict"], r["peerDual"] = self._verdicts(r["n"], r, Fraction(peer[0], peer[1]), r["spread"])
        else:
            r["peerVerdict"], r["peerDual"] = None, {}
        r["verdictWithoutFlagged"] = None
        if r["flags"]:
            # Each flagged year less its excess over the usual count; s^2 of those yearly counts
            by_year = [Fraction(v) for v in r["nByYear"]]
            for f in r["flags"]:
                by_year[self.years.index(f["year"])] -= Fraction(f["count"]) - Fraction(f["usual"])
            reduced = sum(by_year)
            without, _ = self._verdicts(reduced, r, self.natl, sample_variance(by_year))
            r["nWithoutFlagged"] = reduced
            if without != r["verdict"]:
                r["verdictWithoutFlagged"] = without

    def _lists(self) -> None:
        """
        The national list (LIST_CODES): eligible are the rated institutions
        without a reason whose expected count is at least LIST_MIN_EXPECTED;
        an eligible one with an on-campus unusual-year flag of the code in the
        window is not placed (notPlaced "unusual_year"); the others are the
        members: positions, ranges. The state and type lists: the members of
        one state, of one peer type.
        """
        eligible = [r for r in self.rows.values() if r["why"] == ""
                    and self.natl_n * r["F"] >= LIST_MIN_EXPECTED * self.natl_f]
        for r in self.rows.values():
            r["listed"] = False
        for r in eligible:
            if r["flags"]:
                r["notPlaced"] = "unusual_year"
        members = [r for r in eligible if not r["flags"]]
        members.sort(key=lambda r: (-Fraction(r["n"], r["F"]), r["name"], r["base"]))
        self.not_placed = sorted(r["base"] for r in eligible if r["flags"])
        self._positions(members, "position")
        n = len(members)
        if n:
            ranges = rank_ranges([(r["n"], r["F"], r["position"], r["spread"]) for r in members], self.T, self.c)
            for r, (lo, hi) in zip(members, ranges):
                r["rankLo"], r["rankHi"] = lo, hi
            self.zc = critical_z(n) if n > 1 else None
        for r in members:
            r["listed"] = True
        self.list_members = [r["base"] for r in members]
        for key, lists, field, least in (("state", self.state_lists, "state", STATE_LIST_MIN_MEMBERS),
                                         ("type", self.type_lists, "peerType", TYPE_LIST_MIN_MEMBERS)):
            groups = defaultdict(list)
            for r in members:
                groups[r[field]].append(r)
            for value, part in sorted(groups.items()):
                lists[value] = len(part)
                if len(part) < least:
                    continue
                self._positions(part, f"{key}Position")
                ranges = rank_ranges([(r["n"], r["F"], r[f"{key}Position"], r["spread"]) for r in part],
                                     self.T, self.c)
                for r, (lo, hi) in zip(part, ranges):
                    r[f"{key}RankLo"], r[f"{key}RankHi"], r[f"{key}N"] = lo, hi, len(part)

    @staticmethod
    def _positions(ordered: list[dict], key: str) -> None:
        """position = 1 + the number of members with a higher rate (equal rates share one)."""
        for i, r in enumerate(ordered):
            if i and Fraction(r["n"], r["F"]) == Fraction(ordered[i - 1]["n"], ordered[i - 1]["F"]):
                r[key] = ordered[i - 1][key]
            else:
                r[key] = i + 1

    def natl_rate(self, places: int = 2) -> float:
        return half_up(self.natl * 10000, places)

    def peer_rate(self, key: str, places: int = 2) -> float | None:
        p = self.peer.get(key)
        return None if p is None else half_up(Fraction(p[0], p[1]) * 10000, places)

    def composition_share(self) -> dict[str, float] | None:
        """violent: each offense's share of the national rate's on-campus count, half up to 4 decimals."""
        if self.code != "violent" or not self.natl_n:
            return None
        return {k: half_up(Fraction(v, self.natl_n), 4) for k, v in self.composition.items()}

    def entry(self, r: dict, detail: bool) -> dict:
        """The published entry of a rated institution; with `detail` (its institution file) the yearly figures."""
        e = {}
        if not detail:
            e |= {"id": r["base"], "unitid": r["unitid"], "name": r["name"], "state": r["state"],
                  "peerType": r["peerType"]}
        e |= {"n": r["n"], "nNoncampus": r["nNoncampus"], "nPublic": r["nPublic"], "fteYears": r["F"],
              "rate": r["rate"], "lo": r["lo"], "hi": r["hi"], "lo4": r["lo4"], "hi4": r["hi4"],
              "phi": round(r["phi"], 6), "phiFrom": "years" if r["phiFromYears"] else "model", "E": r["E"],
              "verdict": r["verdict"]}
        if r["why"]:
            e["why"] = r["why"]
        e |= r["dual"]
        if r["why"] == "online":
            e["fteYearsSmaller"] = r["Fsmall"]
            e["fteUncertain"] = r["uncertain"]
        e["peerVerdict"] = r["peerVerdict"]
        if r["peerDual"]:
            e["peerVerdictLargerFte"] = r["peerDual"].get("verdictLargerFte")
            if "verdictSmallerFte" in r["peerDual"]:
                e["peerVerdictSmallerFte"] = r["peerDual"]["verdictSmallerFte"]
        for key in ("medical", "sharedIn", "sharedOut"):
            if r[key]:
                e[key] = r[key]
        if not detail:
            e |= r["notes"]
        if r["flags"]:
            e["flags"] = [{"year": f["year"], "offense": f["offense"], "count": f["count"], "usual": f["usual"]}
                          for f in r["flags"]]
            if r["verdictWithoutFlagged"]:
                e["verdictWithoutFlagged"] = r["verdictWithoutFlagged"]
        if self.code in LIST_CODES:
            e["listed"] = r["listed"]
            if "notPlaced" in r:
                e["notPlaced"] = r["notPlaced"]
            if r["listed"]:
                e |= {"position": r["position"], "rankLo": r["rankLo"], "rankHi": r["rankHi"]}
                for key in ("state", "type"):
                    if f"{key}N" in r:
                        e |= {f"{key}Position": r[f"{key}Position"], f"{key}RankLo": r[f"{key}RankLo"],
                              f"{key}RankHi": r[f"{key}RankHi"], f"{key}N": r[f"{key}N"]}
                if "composition" in r:
                    e["composition"] = r["composition"]
        if detail:
            e |= {"nByYear": dict(zip(map(str, self.years), r["nByYear"])), "natl": self.natl_rate(),
                  "natl4": self.natl_rate(4), "peerRate": self.peer_rate(r["peerType"]),
                  "peerRate4": self.peer_rate(r["peerType"], 4)}
            if "composition" in r:
                e["composition"] = r["composition"]
        return e

    def ordered_rows(self) -> list[dict]:
        """The rated institutions by rate, highest first (exact), then name, then base UNITID."""
        return sorted(self.rows.values(), key=lambda r: (-Fraction(r["n"], r["F"]), r["name"], r["base"]))

    def summary(self) -> dict:
        """Counts of the window file's header: rated institutions by reason and verdict, list size."""
        rows = list(self.rows.values())
        out = {"rated": len(rows),
               "byWhy": {w or "none": sum(1 for r in rows if r["why"] == w)
                         for w in ("", "online", "medical_campus", "shared")},
               "verdicts": {v: sum(1 for r in rows if r["verdict"] == v)
                            for v in (ABOVE, BELOW, NOT_DISTINGUISHABLE, UNDETERMINED, WITHHELD)},
               "verdictsNoReason": {v: sum(1 for r in rows if r["verdict"] == v and r["why"] == "")
                                    for v in (ABOVE, BELOW, NOT_DISTINGUISHABLE)},
               "peerVerdicts": {v: sum(1 for r in rows if r["peerVerdict"] == v)
                                for v in (ABOVE, BELOW, NOT_DISTINGUISHABLE, UNDETERMINED, WITHHELD)},
               "withFlags": sum(1 for r in rows if r["flags"]),
               "verdictWithoutFlaggedDiffers": sum(1 for r in rows if r["verdictWithoutFlagged"])}
        return out


def build_windows(inp: RateInputs, flags: dict[int, list[dict]]) -> tuple[dict, dict]:
    """
    ({window: {code: WindowCode}}, {window: {base: status}}) for every rate
    window of the data years (config.py, rate_windows) and every rate code.
    """
    results, statuses = {}, {}
    bases = sorted(inp.years_of)
    for window in rate_windows(inp.data_years):
        statuses[window] = {}
        for base in bases:
            if not any(window[0] <= y <= window[1] for y in inp.years_of[base]):
                continue
            statuses[window][base] = window_status(inp, base, window)
        members = {b: s for b, s in statuses[window].items() if s["status"] == "rated"}
        results[window] = {code: WindowCode(inp, window, code, members, flags) for code in RATE_CODES}
    return results, statuses


# --------------------------------------------------------------------------
# Single years and the count flag
# --------------------------------------------------------------------------

def single_year(inp: RateInputs) -> dict[int, dict[str, dict]]:
    """
    {base: {year: entry}} for every institution-year of DATA_YEARS: rated
    (rated_year, not RATE_SKIP_YEARS) {"fte", "rates": {code: [n, rate, lo,
    hi]}, "fteUncertain"?, "medical"?, "sharedIn"?, "sharedOut"?}, with the
    T = 1 interval; otherwise {"notRated": year_status}.
    """
    out: dict[int, dict[str, dict]] = defaultdict(dict)
    for (y, base), rec in sorted(inp.rec.items()):
        if y not in DATA_YEARS:
            continue
        why = year_status(rec, y)
        if why:
            out[base][str(y)] = {"notRated": why}
            continue
        fte = int(rec["rate_fte"])
        entry = {"fte": fte, "rates": {}}
        reason = uncertain_reason(rec)
        if reason:
            entry["fteUncertain"] = reason
        notes = {"medical": {}, "sharedIn": {}, "sharedOut": {}}
        for code in RATE_CODES:
            v = inp.values(code, y, base)
            n = v[1]
            lower, upper = count_interval(n, 1, dispersion_c(code))
            entry["rates"][code] = [n, rate_value(n, fte), round2(lower / fte * 10000), round2(upper / fte * 10000)]
            for key, i in (("medical", 4), ("sharedIn", 5), ("sharedOut", 6)):
                if v[i]:
                    notes[key][code] = v[i]
        entry |= {k: v for k, v in notes.items() if v}
        out[base][str(y)] = entry
    return out


def count_flag_reference(inp: RateInputs) -> dict[int, dict[str, Fraction]]:
    """
    {year: {code: the COUNT_FLAG_PERCENTILE-th percentile}} (config.py,
    COUNT_FLAG_*): of the year's institution rates of each count code (all
    geographies, per 10,000 of the denominator) of the institutions in the
    national scope with a denominator of at least MIN_FTE_FOR_RATE, no rule
    and a certain on-campus FTE, 0 included; exact fractions.
    """
    codes = list(SUMMARY_FAMILIES) + sorted({code_of(o) for v in inp.offense_values.values() for o in v})
    out = {}
    for year in inp.data_years:
        pop = [(b, r) for (y, b), r in inp.rec.items() if y == year and rated_year(r)
               and not bool(r.get("online_uncertain"))]
        per_code = {code: [] for code in codes}
        for b, r in pop:
            counts = inp.count_codes(year, b)
            fte = int(r["rate_fte"])
            for code in codes:
                per_code[code].append(Fraction(counts.get(code, 0) * 10000, fte))
        out[year] = {code: percentile_linear(vals, COUNT_FLAG_PERCENTILE) for code, vals in per_code.items() if vals}
    return out


def build() -> dict:
    """Everything 05 publishes about rates."""
    inp = RateInputs()
    flags = unusual_years(inp)
    windows, statuses = build_windows(inp, flags)
    return {"inputs": inp, "flags": flags, "windows": windows, "statuses": statuses,
            "singleYear": single_year(inp), "countFlagReference": count_flag_reference(inp)}
