"""
NCES's Complete Data Files listing and remote ZIPs: what the update checker
(00_check_for_updates.py) and the downloader (01b_download_ipeds.py) ask NCES.

- Where NCES publishes each file. NCES's own Complete Data Files listing
  (DataFiles.aspx?year=YYYY) links every file to its real location. That is the
  only source of truth used here: NCES has moved files before, and the legacy
  /ipeds/datacenter/data/ path can still serve an OLDER copy under the same
  name (e.g. DRVEF2023 without the final drvef2023_rv.csv). A page that
  links one file name at two addresses, or that cannot be confirmed to show
  the requested year, is refused.
- How to compare a remote ZIP with a local one without downloading it: read
  the ZIP's central directory with a Range request and compare every member's
  CRC-32 and size. Unlike a size check, this catches a one-digit correction.
- Which years wait for NCES (WAITING): the newest years whose fall enrollment
  file NCES has not published yet. The update checker and the downloader use
  the same rule (waiting_years).
- Which files on a listing might be another version of a pipeline file, such
  as a final version published as its own ZIP (other_versions).

This module is not part of any step's code fingerprint (provenance.STAGE_CODE):
it cannot change which file the enrollment transforms read or what they read
from it. That is decided by ipeds_files.py (pipeline_csv), which is part of it.
Every request goes through ipeds_files.session() with the HTTP settings kept
there. ipeds_files makes these names available too, so 00 and 01b use them as
ipeds_files.<name>.
"""

from __future__ import annotations

import html
import io
import re
import struct
import zipfile
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit

import requests

import ipeds_files


class ListingUnavailable(Exception):
    """NCES's listing could not be read, so file locations cannot be trusted."""


class AmbiguousListing(ListingUnavailable):
    """
    NCES's listing links one file name at two or more different addresses, so
    it cannot tell which copy is current. `conflicts` maps each such file stem
    to its URLs; `links` holds every other stem with its single URL.
    """

    def __init__(self, year: int, conflicts: dict[str, list[str]], links: dict[str, str]):
        self.year = year
        self.conflicts = conflicts
        self.links = links
        detail = "; ".join(f"{stem}.zip at {' and '.join(urls)}" for stem, urls in sorted(conflicts.items()))
        super().__init__(f"NCES listing for {year} links the same file at more than one address "
                         f"({detail}); cannot tell which copy is current")


_listing_cache: dict[int, dict[str, str] | None] = {}
_page_cache: dict[int, str] = {}  # raw HTML of each listing page read


_YEAR_SELECT = re.compile(r'<select[^>]*id=["\']contentPlaceHolder_ddlYears["\'][^>]*>(.*?)</select>', re.I | re.S)
_OPTION = re.compile(r"<option\b([^>]*)>", re.I)
_OPTION_VALUE = re.compile(r"""\bvalue\s*=\s*["']?(-?\d+)""", re.I)
_OPTION_SELECTED = re.compile(r"\bselected\b", re.I)
# Links are read only from live markup: an old link left in a comment or a script is not a listing
_DEAD_MARKUP = re.compile(r"<!--.*?-->|<script\b.*?</script\s*>", re.I | re.S)
_ZIP_HREF = re.compile(r"""href\s*=\s*(?:"([^"]*?\.zip(?:[?#][^"]*)?)"|'([^']*?\.zip(?:[?#][^']*)?)')""", re.I)
_published_years: set[int] | None = None


def _live_markup(page: str) -> str:
    return _DEAD_MARKUP.sub("", page)


def _dropdown_years(page: str) -> tuple[set[int], int | None]:
    """
    Years offered in the listing's year dropdown, and the selected value
    (-1 is "All years"). The selected value is None when the dropdown is not
    found or does not mark exactly one option as selected.
    """
    m = _YEAR_SELECT.search(page)
    if not m:
        return set(), None
    years, selected = set(), []
    for attrs in _OPTION.findall(m.group(1)):
        value = _OPTION_VALUE.search(attrs)
        if not value:
            continue
        v = int(value.group(1))
        if v > 0:
            years.add(v)
        if _OPTION_SELECTED.search(attrs):
            selected.append(v)
    return years, selected[0] if len(selected) == 1 else None


def _fetch_listing_page(year: int) -> requests.Response:
    try:
        r = ipeds_files.session().get(ipeds_files.DATAFILES_PAGE.format(year=year), timeout=ipeds_files.TIMEOUT)
    except requests.RequestException as e:
        raise ListingUnavailable(f"NCES listing for {year}: {e}") from e
    if r.status_code != 200:
        raise ListingUnavailable(f"NCES listing for {year}: HTTP {r.status_code}")
    return r


def published_years(reference_year: int) -> set[int]:
    """Years NCES's Complete Data Files dropdown offers, read from a page that renders."""
    global _published_years
    if _published_years is None:
        r = _fetch_listing_page(reference_year)
        years, _ = _dropdown_years(_live_markup(r.text))
        if not years:
            raise ListingUnavailable("could not read NCES's list of data years; page format may have changed")
        _published_years = years
    return _published_years


def listed_files(year: int, reference_year: int = 2020) -> dict[str, str] | None:
    """
    Map each file stem on NCES's Complete Data Files page for `year`
    (upper-case, e.g. 'DRVEF2023') to its absolute download URL.

    Returns None only when NCES provably has no page for that year: the
    request lands on Error.aspx AND the year is absent from the year dropdown
    of a page that does render (Error.aspx is also NCES's generic error page,
    so on its own it proves nothing). Raises ListingUnavailable when the page
    cannot be read or does not look like the listing, including when it cannot
    be confirmed to show `year`, so callers never mistake a broken page for
    "nothing published". Raises AmbiguousListing (a ListingUnavailable) when
    one file name is linked at two different addresses.
    """
    if year in _listing_cache:
        return _listing_cache[year]
    _page_cache.pop(year, None)
    r = _fetch_listing_page(year)
    if "error.aspx" in r.url.lower():
        if year in published_years(reference_year):
            raise ListingUnavailable(f"NCES listing for {year} returned its error page although "
                                     f"{year} is offered; try again later")
        _listing_cache[year] = None
        return None
    if "datafiles.aspx" not in r.url.lower():
        raise ListingUnavailable(f"NCES listing for {year} redirected to {r.url}")
    _page_cache[year] = r.text
    page = _live_markup(r.text)
    _, selected = _dropdown_years(page)
    if selected is None:
        raise ListingUnavailable(f"could not tell which year NCES's listing for {year} shows (its year "
                                 "dropdown was not found or has no selected year); page format may have changed")
    if selected != year:
        shown = "all years" if selected == -1 else f"year {selected}"
        raise ListingUnavailable(f"NCES listing for {year} rendered {shown} instead")

    found: dict[str, list[str]] = {}
    for double_quoted, single_quoted in _ZIP_HREF.findall(page):
        href = html.unescape(double_quoted or single_quoted).strip()
        file_name = urlsplit(href).path.rsplit("/", 1)[-1]
        if not file_name.lower().endswith(".zip"):
            continue
        urls = found.setdefault(file_name[:-4].upper(), [])
        url = urljoin(r.url, href)
        if url.lower() not in (u.lower() for u in urls):  # NCES's server ignores case in paths
            urls.append(url)
    if not found:
        raise ListingUnavailable(f"NCES listing for {year} has no .zip links; page format may have changed")
    if not any(str(year) in stem for stem in found):
        raise ListingUnavailable(f"NCES listing for {year} links no {year} files; it may show another year")
    links = {stem: urls[0] for stem, urls in found.items() if len(urls) == 1}
    conflicts = {stem: urls for stem, urls in found.items() if len(urls) > 1}
    if conflicts:
        raise AmbiguousListing(year, conflicts, links)
    _listing_cache[year] = links
    return links


def listing_mentions(year: int, name: str) -> bool:
    """
    Whether NCES's listing page for `year` mentions `name` (e.g. 'DRVEF2025')
    anywhere, even where no link to it could be read. Uses the page read by
    the last listed_files(year) call; False when there was no listing page.
    """
    page = _page_cache.get(year)
    if page is None:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", page, re.I) is not None


def read_listing(year: int) -> tuple[dict[str, str] | None, dict[str, list[str]], str | None]:
    """
    NCES's listing for `year` as (links, conflicts, problem). links maps each
    file stem to its URL, or is None when NCES provably has no page for the
    year or the page could not be read; conflicts maps each stem linked at
    more than one address to its URLs; problem says why the page could not
    be read (None when it was read).
    """
    try:
        return listed_files(year), {}, None
    except AmbiguousListing as e:
        return e.links, e.conflicts, None
    except ListingUnavailable as e:
        return None, {}, str(e)


def waiting_years(years: Iterable[int], stem_for: Callable[[int], str],
                  listing: Callable[[int], tuple] = read_listing) -> tuple[set[int], set[int]]:
    """
    The WAITING rule, shared by the update checker and the downloader: the
    newest years of `years` whose fall enrollment file (stem_for(year), e.g.
    'drvef2025' or 'ef2020a') NCES has not published yet. A year qualifies
    when the file was never held here (no {STEM}.zip and no CSV the
    transforms would read) and NCES's listing for the year was read and
    neither links nor mentions the file, or NCES has no page for the year at
    all. Years are taken newest first and the scan stops at the first year
    that is held or whose listing has the file, so a file NCES removes from
    an older year is still an error.

    Returns (waiting, unconfirmed). unconfirmed holds the years that are not
    held but whose listing could not be read on this run: whether NCES has
    published them is unknown, and the scan goes on past them. listing(year)
    returns what read_listing does; it is called only for years not held.
    """
    waiting: set[int] = set()
    unconfirmed: set[int] = set()
    for year in sorted(years, reverse=True):
        stem = stem_for(year)
        name = stem.upper()
        if ((ipeds_files.IPEDS_RAW_DIR / str(year) / f"{name}.zip").exists()
                or ipeds_files.pipeline_csv(year, stem) is not None):
            break
        links, conflicts, problem = listing(year)
        if problem is not None:
            unconfirmed.add(year)
            continue
        if links is not None and (name in links or name in conflicts or listing_mentions(year, name)):
            break
        waiting.add(year)
    return waiting, unconfirmed


# Files NCES lists next to a pipeline file under a longer name (the same table
# in other formats, its dictionary, and the distance-education table), as on
# NCES's 2015-2025 listings: EF2015A_DIST.zip, DRVEF2023_DICT.zip, ...
KNOWN_SIBLING_SUFFIXES = frozenset([
    "_DATA_STATA", "_DICT", "_SAS", "_SPS", "_STATA",
    "_DIST", "_DIST_DATA_STATA", "_DIST_DICT", "_DIST_SAS", "_DIST_SPS", "_DIST_STATA",
])


def other_versions(stem: str, listed: Iterable[str]) -> list[str]:
    """
    Stems in `listed` (a year's listing) that begin with the pipeline file's
    stem but are neither the stem itself nor a file NCES already publishes
    next to it, e.g. DRVEF2024_RV or DRVEF2024F next to DRVEF2024. Such a
    file may hold a final or corrected version published as its own ZIP,
    which the pipeline does not read. A known sibling of one of them
    (DRVEF2024_RV_DICT next to DRVEF2024_RV) is not returned separately.
    """
    stem = stem.upper()
    found = sorted({s.upper() for s in listed} - {stem})
    found = [s for s in found if s.startswith(stem) and s[len(stem):] not in KNOWN_SIBLING_SUFFIXES]
    return [s for s in found
            if not any(o != s and s.startswith(o) and s[len(o):] in KNOWN_SIBLING_SUFFIXES for o in found)]


def _zip64_size(extra: bytes, name: str) -> int:
    """
    A member's real uncompressed size from its ZIP64 extra field (0x0001),
    for an entry whose 32-bit size field is 0xFFFFFFFF. The size is the
    field's first value, as Python's zipfile reads it.
    """
    pos = 0
    while pos + 4 <= len(extra):
        tag, length = struct.unpack("<HH", extra[pos:pos + 4])
        if tag == 0x0001:
            if length < 8 or pos + 4 + 8 > len(extra):
                break
            return struct.unpack("<Q", extra[pos + 4:pos + 12])[0]
        pos += 4 + length
    raise ValueError(f"ZIP member {name} has a ZIP64 size but no readable ZIP64 extra field")


def _parse_central_directory(cd: bytes) -> ipeds_files.ZipEntries:
    entries: ipeds_files.ZipEntries = {}
    pos = 0
    while pos + 46 <= len(cd) and cd[pos:pos + 4] == b"PK\x01\x02":
        flags, = struct.unpack("<H", cd[pos + 8:pos + 10])
        crc, _csize, usize, nlen, xlen, clen = struct.unpack("<IIIHHH", cd[pos + 16:pos + 34])
        raw = cd[pos + 46:pos + 46 + nlen]
        name = raw.decode("utf-8" if flags & 0x800 else "cp437")
        if usize == 0xFFFFFFFF:  # the real size is in the ZIP64 extra field
            usize = _zip64_size(cd[pos + 46 + nlen:pos + 46 + nlen + xlen], name)
        if not name.endswith("/"):
            entries[name.lower()] = (crc, usize)
        pos += 46 + nlen + xlen + clen
    return entries


def remote_entries(url: str) -> tuple[ipeds_files.ZipEntries, int] | None:
    """
    Read a remote ZIP's member list (CRC-32 and size of every member) and its
    total size, without downloading the whole file when the server supports
    Range requests. Returns None if the URL returns 404.

    Raises requests.RequestException on network errors and ValueError when the
    response is not a readable ZIP.
    """
    r = ipeds_files.session().get(url, headers={"Range": f"bytes=-{ipeds_files.TAIL_BYTES}"},
                                  timeout=ipeds_files.TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.content

    if r.status_code == 200:  # Range ignored: this is the whole file
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return {i.filename.lower(): (i.CRC, i.file_size) for i in zf.infolist() if not i.is_dir()}, len(data)
        except zipfile.BadZipFile as e:
            raise ValueError(f"{url} did not return a ZIP file") from e

    m = re.match(r"bytes (\d+)-(\d+)/(\d+)", r.headers.get("Content-Range", ""))
    if not m:
        raise ValueError(f"{url}: unexpected Content-Range {r.headers.get('Content-Range')!r}")
    start, total = int(m.group(1)), int(m.group(3))

    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0 or eocd + 22 > len(data):
        raise ValueError(f"{url}: no end-of-central-directory record; not a ZIP file")
    cd_size, cd_offset = struct.unpack("<II", data[eocd + 12:eocd + 20])
    if cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ValueError(f"{url}: ZIP64 archives are not supported")
    if cd_offset >= start:
        cd = data[cd_offset - start:cd_offset - start + cd_size]
    else:
        r2 = ipeds_files.session().get(url, headers={"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"},
                                       timeout=ipeds_files.TIMEOUT)
        r2.raise_for_status()
        cd = r2.content
    entries = _parse_central_directory(cd)
    if not entries:
        raise ValueError(f"{url}: could not read the ZIP's member list")
    return entries, total


def describe_difference(local: ipeds_files.ZipEntries, remote: ipeds_files.ZipEntries) -> str:
    added = sorted(set(remote) - set(local))
    removed = sorted(set(local) - set(remote))
    changed = sorted(k for k in set(local) & set(remote) if local[k] != remote[k])
    parts = []
    if added:
        parts.append("new members " + ", ".join(added))
    if removed:
        parts.append("members gone " + ", ".join(removed))
    if changed:
        parts.append("content changed in " + ", ".join(changed))
    return "; ".join(parts) or "no difference"
