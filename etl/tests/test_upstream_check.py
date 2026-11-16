"""
Tests of 00_check_for_updates.py --upstream-only, with DOE's listing, its
release downloads and NCES's listings and ZIP member lists replaced by fakes:
no network, no raw files.

    python -m unittest discover -s etl/tests
"""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))

import requests  # noqa: E402

import ipeds_files  # noqa: E402
import ipeds_listing  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location("check_for_updates_under_test", ETL_DIR / "00_check_for_updates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chk = load_checker()
GEOS = ("oncampus", "residencehall", "noncampus", "publicproperty")
CATEGORIES = ("crime", "vawa", "arrest", "discipline")
FIRST, LAST = min(chk.DATA_YEARS), max(chk.DATA_YEARS)
BUILT = list(range(FIRST + 1, LAST + 2))  # the releases that cover DATA_YEARS and exist: Crime2016 .. Crime2025


def suffix(release: int) -> str:
    return "".join(f"{(release - k) % 100:02d}" for k in (3, 2, 1))


def crime_files(release: int) -> dict[str, tuple[int, int]]:
    """The 16 crime files of a release, with made-up CRC-32 and size."""
    return {f"{g}{c}{suffix(release)}.sas7bdat": (release * 100 + i, 1000 + i)
            for i, (g, c) in enumerate((g, c) for g in GEOS for c in CATEGORIES)}


def enrollment_file(year: int) -> str:
    stem = chk.ipeds.pipeline_stem(year)
    return f"{stem}.csv" if year == LAST else f"{stem}_rv.csv"  # the newest year is still provisional


def record() -> dict:
    """A build record of the shape step 05 writes, for every release and year."""
    files = {name: {"crc32": crc, "size": size} for r in BUILT for name, (crc, size) in crime_files(r).items()}
    used = {str(y): {"file": enrollment_file(y), "final": y != LAST, "sha256": "0" * 64} for y in chk.DATA_YEARS}
    return {"aggregates": {"inputs": {"crime": {"files": files}, "enrollment": {"inputs": used}}}}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code, self.payload, self.headers = status_code, payload, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    """NCES's HEAD answers for the IPEDS Access databases: their recorded sizes."""

    def __init__(self):
        self.headers = {"User-Agent": "collegesafetydata-etl"}
        sources = json.loads((ETL_DIR / "reference" / "ipeds_official_sources.json").read_text(encoding="utf-8"))
        self.sizes = {s["url"]: int(s["bytes"]) for s in sources}
        self.asked = []

    def head(self, url, **_kw):
        self.asked.append(url)
        return FakeResponse(200, headers={"Content-Length": str(self.sizes[url])})

    def get(self, url, **_kw):
        raise AssertionError(f"unexpected GET {url}")


class Upstream:
    """What DOE and NCES publish in a test; each test changes what it needs."""

    def __init__(self):
        self.releases = {r: dict(crime_files(r)) for r in BUILT}  # what DOE serves
        self.listing_releases = list(BUILT)
        self.listing_fails = False
        self.nces_members = {y: {enrollment_file(y): (1, 2), f"{chk.ipeds.pipeline_stem(y)}.csv": (3, 4)}
                             for y in chk.DATA_YEARS}
        self.next_year_listed = False
        self.fetched = []

    def doe_listing_rows(self):
        rows = []
        for r in self.listing_releases:
            for fmt, label in (("SAS", "sas"), ("SPSS", "spss"), ("EXCEL", "excel")):
                rows.append({"FileName": f"Crime{r}{fmt}.zip", "Year": r, "Format": label,
                             "LinkName": f"Calendar {r - 3}-{r - 1}"})
        return rows

    def doe_fetch(self, url, consume, attempts=4):
        self.fetched.append(url)
        if url == chk.DOE_FILE_LIST_URL:
            if self.listing_fails:
                raise requests.ConnectionError("connection refused")
            return consume(FakeResponse(200, self.doe_listing_rows()))
        raise AssertionError(f"unexpected DOE request {url}")

    def doe_release(self, name, release, local_sha):
        assert local_sha is None, "the upstream check must not hash local files"
        self.fetched.append(name)
        members = self.releases.get(release)
        if members is None:
            return None
        return "sha", {**members, f"hate{suffix(release)}.sas7bdat": (9, 9)}

    def probe_release(self, name, release):
        self.fetched.append(name)
        return None if release not in self.releases else []

    def read_listing(self, year):
        if year > LAST:
            if not self.next_year_listed:
                return None, {}, None  # NCES has no page for the year yet
            return {f"DRVEF{year}": f"https://nces.example/DRVEF{year}.zip"}, {}, None
        stem = chk.ipeds.pipeline_stem(year).upper()
        links = {stem: f"https://nces.example/{stem}.zip", f"{stem}_DICT": f"https://nces.example/{stem}_Dict.zip",
                 f"HD{year}": f"https://nces.example/HD{year}.zip"}
        return links, {}, None

    def remote_entries(self, url):
        stem = url.rsplit("/", 1)[-1][:-4].lower()
        year = int("".join(ch for ch in stem if ch.isdigit())[:4])
        return dict(self.nces_members[year]), 1000


def run_upstream(up: Upstream) -> tuple[int, str, FakeSession]:
    session = FakeSession()
    out = io.StringIO()
    headers = dict(chk.HEADERS)
    chk.findings.clear()
    chk.UNRECOGNIZED.clear()
    chk.WAITING_YEARS.clear()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(chk.provenance, "read", lambda _path: record()))
        stack.enter_context(mock.patch.object(chk, "doe_fetch", up.doe_fetch))
        stack.enter_context(mock.patch.object(chk, "doe_release", up.doe_release))
        stack.enter_context(mock.patch.object(chk, "probe_release", up.probe_release))
        stack.enter_context(mock.patch.object(chk, "read_listing", up.read_listing))
        stack.enter_context(mock.patch.object(ipeds_listing, "remote_entries", up.remote_entries))
        stack.enter_context(mock.patch.object(ipeds_listing, "listing_mentions", lambda _y, _n: False))
        stack.enter_context(mock.patch.object(ipeds_files, "_session", session))
        stack.enter_context(mock.patch.object(chk.time, "sleep", lambda _s: None))
        stack.enter_context(contextlib.redirect_stdout(out))
        try:
            code = chk.main(["--upstream-only"])
        finally:
            chk.HEADERS.clear()
            chk.HEADERS.update(headers)
    return code, out.getvalue(), session


class UpstreamOnlyTest(unittest.TestCase):
    def test_nothing_new(self):
        up = Upstream()
        code, out, session = run_upstream(up)
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: DOE and NCES list nothing newer", out)
        for kind in ("[NEW", "[CHANGED", "[ERROR"):
            self.assertNotIn(kind, out)
        self.assertIn(f"Crime{LAST + 2}SAS.zip does not exist yet (404)", out)
        self.assertIn(f"Crime{LAST + 1}SAS.zip: the 16 crime files the transform reads are the ones the build read",
                      out)
        # Every release the build read was asked for; the Access databases were asked with HEAD only
        for r in BUILT:
            self.assertIn(f"Crime{r}SAS.zip", up.fetched)
        self.assertTrue(session.asked)
        # No project name in the User-Agent of this mode
        self.assertNotIn("collegesafetydata", session.headers["User-Agent"].lower())

    def test_newer_doe_release(self):
        up = Upstream()
        new = LAST + 2
        up.releases[new] = crime_files(new)
        up.listing_releases.append(new)
        code, out, _ = run_upstream(up)
        self.assertEqual(code, 1, out)
        self.assertIn(f"[NEW    ] DOE lists Crime{new}SAS.zip", out)
        self.assertIn(f"Crime{new}SAS.zip is offered by DOE, and the build did not read it", out)
        self.assertIn("RESULT: 3 new and 0 changed item(s) upstream", out)

    def test_reissued_doe_release(self):
        up = Upstream()
        member = f"oncampuscrime{suffix(LAST + 1)}.sas7bdat"
        crc, size = up.releases[LAST + 1][member]
        up.releases[LAST + 1][member] = (crc + 1, size)
        code, out, _ = run_upstream(up)
        self.assertEqual(code, 1, out)
        self.assertIn(f"[CHANGED] Crime{LAST + 1}SAS.zip was re-issued", out)
        self.assertIn(f"content changed in {member}", out)

    def test_final_nces_file_and_next_year(self):
        up = Upstream()
        stem = chk.ipeds.pipeline_stem(LAST)
        up.nces_members[LAST][f"{stem}_rv.csv"] = (5, 6)
        up.next_year_listed = True
        code, out, _ = run_upstream(up)
        self.assertEqual(code, 1, out)
        self.assertIn(f"{stem.upper()}.zip now has the final {stem}_rv.csv", out)
        self.assertIn(f"DRVEF{LAST + 1}.zip (fall {LAST + 1} enrollment) is published", out)

    def test_listing_unreadable_is_unknown(self):
        up = Upstream()
        up.listing_fails = True
        code, out, _ = run_upstream(up)
        self.assertEqual(code, 2, out)
        self.assertIn("[ERROR  ] Could not read DOE's file listing", out)
        self.assertIn("is UNKNOWN", out)

    def test_modes_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            chk.main(["--upstream-only", "--local-only"])


if __name__ == "__main__":
    unittest.main()
