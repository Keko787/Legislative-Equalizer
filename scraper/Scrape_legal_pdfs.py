#!/usr/bin/env python3
"""
scrape_legal_pdfs.py
====================
Polite, modular scraper for collecting legal PDFs (judgments + statutes)
from official government / court portals for Australia, Ireland, Canada,
the United Kingdom, and the United States.

Targets ~500 PDFs per country (~250 judgments + ~250 statutes).

PREREQUISITES
-------------
    pip install requests beautifulsoup4 tqdm lxml

USAGE
-----
    # See available sources
    python scrape_legal_pdfs.py --list

    # Full run (default ~500 per country)
    python scrape_legal_pdfs.py --output ./legal_pdfs

    # Specific countries only
    python scrape_legal_pdfs.py --countries australia,canada

    # Override the per-source cap (default 250)
    python scrape_legal_pdfs.py --max-per-source 50          # quick test

    # Just one source
    python scrape_legal_pdfs.py --sources scc_canada

OUTPUT LAYOUT
-------------
    ./legal_pdfs/
        manifest.jsonl
        australia/
            judgments/
                hca_2024_001.pdf
                ...
            statutes/
                ...
        ireland/
            judgments/
            statutes/
        canada/
            judgments/
            statutes/

"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    from tqdm import tqdm
except ImportError:
    sys.exit(
        "Missing dependencies. Run:\n"
        "    pip install requests beautifulsoup4 tqdm lxml"
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_DELAY_SEC = 1.0
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_PER_SOURCE = 250


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Document:
    """One legal document we plan to download."""
    source: str           # source key, e.g. "scc_canada"
    country: str          # "australia" | "ireland" | "canada"
    doc_type: str         # "judgments" | "statutes"
    title: str
    url: str              # direct URL to the PDF
    citation: str = ""    # neutral citation if known
    year: str = ""
    landing_url: str = "" # the HTML page the PDF was linked from


# ---------------------------------------------------------------------------
# Polite HTTP client
# ---------------------------------------------------------------------------

class PoliteClient:
    """HTTP client with per-domain rate limiting and backoff."""

    def __init__(self, delay: float = DEFAULT_DELAY_SEC):
        self.delay = delay
        self._last_hit: dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host, 0)
        elapsed = time.time() - last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_hit[host] = time.time()

    def get(self, url: str, max_retries: int = 3, **kw) -> requests.Response:
        kw.setdefault("timeout", DEFAULT_TIMEOUT)
        backoff = 2.0
        for attempt in range(max_retries):
            self._wait(url)
            try:
                r = self.session.get(url, **kw)
            except requests.RequestException:
                if attempt == max_retries - 1:
                    raise
                time.sleep(backoff ** attempt)
                continue
            if r.status_code in (429, 503):
                wait = int(r.headers.get("Retry-After", backoff ** attempt))
                time.sleep(wait)
                continue
            return r
        return r

    def head(self, url: str, **kw) -> requests.Response:
        """Lightweight existence check — does not download the body."""
        kw.setdefault("timeout", 5)
        self._wait(url)
        try:
            return self.session.head(url, allow_redirects=True, **kw)
        except requests.RequestException:
            r = requests.Response()
            r.status_code = 0
            return r

    def download(self, url: str, dest: Path) -> bool:
        """Stream-download a file. Returns True on success."""
        if dest.exists() and dest.stat().st_size > 0:
            return True  # already have it
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = self.get(url, stream=True)
            if r.status_code != 200:
                return False
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            tmp.rename(dest)
            return True
        except Exception as e:
            print(f"    ! download failed {url}: {e}", file=sys.stderr)
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INVALID_FN = re.compile(r"[^A-Za-z0-9._-]+")

def safe_filename(s: str, max_len: int = 120) -> str:
    s = _INVALID_FN.sub("_", s).strip("_")
    return s[:max_len] or "doc"


# ---------------------------------------------------------------------------
# Source base class
# ---------------------------------------------------------------------------

class Source:
    """Base class. Each subclass implements discover() yielding Documents."""

    key: str = ""
    country: str = ""
    doc_type: str = ""
    name: str = ""

    def __init__(self, client: PoliteClient, max_docs: int):
        self.client = client
        self.max_docs = max_docs

    def discover(self) -> Iterator[Document]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# AUSTRALIA — High Court of Australia (judgments)
# ---------------------------------------------------------------------------

class HighCourtAustralia(Source):
    """Scrapes recent judgments from the High Court of Australia website.

    The HCA publishes judgments at https://eresources.hcourt.gov.au/ but the
    most reliable PDF source is via AustLII listings of HCA decisions.
    """
    key = "hca_australia"
    country = "australia"
    doc_type = "judgments"
    name = "High Court of Australia (via AustLII)"

    BASE = "https://www.austlii.edu.au"
    INDEX = "/cgi-bin/viewdb/au/cases/cth/HCA/"  # year listings

    def discover(self) -> Iterator[Document]:
        # AustLII PDFs: austlii.edu.au/au/cases/cth/HCA/{year}/{n}.pdf
        # Probe sequentially; HCA issues ~10-60 judgments per year.
        count = 0
        for year in range(2024, 2018, -1):
            if count >= self.max_docs:
                return
            for num in range(1, 80):
                if count >= self.max_docs:
                    return
                pdf_url = f"{self.BASE}/au/cases/cth/HCA/{year}/{num}.pdf"
                r = self.client.head(pdf_url)
                if r.status_code == 404:
                    if num > 5:
                        break  # no more cases this year
                    continue
                if r.status_code not in (200, 301, 302):
                    continue
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=f"HCA {year} [{num}]",
                    url=pdf_url, year=str(year),
                    citation=f"[{year}] HCA {num}",
                    landing_url=f"{self.BASE}/au/cases/cth/HCA/{year}/{num}.html",
                )
                count += 1


# ---------------------------------------------------------------------------
# AUSTRALIA — Federal Register of Legislation (statutes)
# ---------------------------------------------------------------------------

class FederalRegisterAU(Source):
    """Australian Federal Register of Legislation — Acts as PDF.

    legislation.gov.au exposes a sitemap and per-act download endpoints.
    """
    key = "frl_australia"
    country = "australia"
    doc_type = "statutes"
    name = "Federal Register of Legislation (Australia)"

    BASE = "https://www.legislation.gov.au"
    BROWSE = "/Browse/Results/ByTitle/Acts/InForce/Ax/0/principal"

    def discover(self) -> Iterator[Document]:
        # legislation.gov.au is JS-rendered — cannot scrape HTML.
        # Australian Act IDs follow C{year}A{nnnnn:05d}. Generate them
        # directly; download() will skip 404s for gaps in numbering.
        for year in range(2024, 2019, -1):
            for num in range(1, 51):
                reg_id = f"C{year}A{num:05d}"
                pdf_url = f"{self.BASE}/Details/{reg_id}/Download"
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=f"Australian Federal Act {num} of {year}",
                    url=pdf_url, year=str(year), citation=reg_id,
                    landing_url=f"{self.BASE}/Details/{reg_id}",
                )


# ---------------------------------------------------------------------------
# IRELAND — Courts Service (judgments)
# ---------------------------------------------------------------------------

class CourtsServiceIE(Source):
    """Irish Courts Service — judgments published as PDFs.

    https://www.courts.ie/judgments lists recent judgments. Each judgment
    page has a "Download Judgment" PDF link.
    """
    key = "courts_ireland"
    country = "ireland"
    doc_type = "judgments"
    name = "Courts Service of Ireland"

    BASE = "https://www.courts.ie"
    LIST = "/judgments"

    def discover(self) -> Iterator[Document]:
        count = 0
        for page in range(0, 100):
            if count >= self.max_docs:
                return
            r = self.client.get(f"{self.BASE}{self.LIST}?page={page}")
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
            # Try several selectors — courts.ie has changed layout multiple times
            cards = (
                soup.select("a[href*='/acc/alfresco/']") or
                soup.select("a[href*='/judgments/']") or
                soup.select("article a[href]") or
                soup.select(".views-row a[href]")
            )
            found_any = False
            for a in cards:
                href = a.get("href", "")
                if not href or href == self.LIST:
                    continue
                # If already a PDF, use directly
                if href.endswith(".pdf"):
                    pdf_url = urljoin(self.BASE, href)
                    title = a.get_text(strip=True) or "Judgment"
                    yield Document(
                        source=self.key, country=self.country, doc_type=self.doc_type,
                        title=title, url=pdf_url,
                        landing_url=urljoin(self.BASE, href),
                    )
                    count += 1
                    found_any = True
                    if count >= self.max_docs:
                        return
                    continue
                landing = urljoin(self.BASE, href)
                lr = self.client.get(landing)
                if lr.status_code != 200:
                    continue
                lsoup = BeautifulSoup(lr.text, "lxml")
                pdf = lsoup.select_one("a[href$='.pdf']")
                if not pdf:
                    continue
                pdf_url = urljoin(landing, pdf["href"])
                h1 = lsoup.find("h1")
                title = h1.get_text(strip=True) if h1 else a.get_text(strip=True) or "Judgment"
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=title, url=pdf_url, landing_url=landing,
                )
                count += 1
                found_any = True
                if count >= self.max_docs:
                    return
            if not found_any:
                break


# ---------------------------------------------------------------------------
# IRELAND — Irish Statute Book (statutes)
# ---------------------------------------------------------------------------

class IrishStatuteBook(Source):
    """Irish Statute Book — Acts of the Oireachtas as PDFs.

    URLs follow the pattern:
        https://www.irishstatutebook.ie/eli/{year}/act/{n}/enacted/en/pdf
    """
    key = "isb_ireland"
    country = "ireland"
    doc_type = "statutes"
    name = "Irish Statute Book"

    BASE = "https://www.irishstatutebook.ie"

    def discover(self) -> Iterator[Document]:
        # ISB PDF pattern: irishstatutebook.ie/eli/{year}/act/{n}/enacted/en/pdf
        # Probe sequentially — Ireland passes ~30-50 acts per year.
        count = 0
        for year in range(2024, 2010, -1):
            if count >= self.max_docs:
                return
            for num in range(1, 60):
                if count >= self.max_docs:
                    return
                pdf_url = f"{self.BASE}/eli/{year}/act/{num}/enacted/en/pdf"
                r = self.client.head(pdf_url)
                if r.status_code == 404:
                    if num > 5:
                        break  # no more acts this year
                    continue
                if r.status_code not in (200, 301, 302):
                    continue
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=f"Irish Act No. {num} of {year}",
                    url=pdf_url, year=str(year),
                    citation=f"No. {num}/{year}",
                    landing_url=f"{self.BASE}/eli/{year}/act/{num}/enacted/en/html",
                )
                count += 1


# ---------------------------------------------------------------------------
# CANADA — Supreme Court of Canada (judgments)
# ---------------------------------------------------------------------------

class SupremeCourtCanada(Source):
    """Supreme Court of Canada decisions.

    decisions.scc-csc.ca lists decisions by year. Each decision has a PDF
    download link.
    """
    key = "scc_canada"
    country = "canada"
    doc_type = "judgments"
    name = "Supreme Court of Canada"

    BASE = "https://decisions.scc-csc.ca"

    def discover(self) -> Iterator[Document]:
        count = 0
        for year in range(2025, 1990, -1):
            if count >= self.max_docs:
                return
            list_url = f"{self.BASE}/scc-csc/scc-csc/en/nav_date.do?year={year}"
            r = self.client.get(list_url)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.select("a[href*='/scc-csc/scc-csc/en/item/']"):
                href = a.get("href", "")
                landing = urljoin(self.BASE, href)
                lr = self.client.get(landing)
                if lr.status_code != 200:
                    continue
                lsoup = BeautifulSoup(lr.text, "lxml")
                pdf_a = lsoup.select_one("a[href*='.pdf']")
                if not pdf_a:
                    continue
                pdf_url = urljoin(landing, pdf_a["href"])
                title = a.get_text(strip=True) or "SCC decision"
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=title, url=pdf_url, year=str(year),
                    landing_url=landing,
                )
                count += 1
                if count >= self.max_docs:
                    return


# ---------------------------------------------------------------------------
# CANADA — Justice Laws Website (statutes)
# ---------------------------------------------------------------------------

class JusticeLawsCanada(Source):
    """Canadian Justice Laws Website — consolidated Acts as PDFs.

    https://laws-lois.justice.gc.ca/eng/acts/ has a master list of Acts.
    Each Act has a PDF download.
    """
    key = "jl_canada"
    country = "canada"
    doc_type = "statutes"
    name = "Justice Laws Website (Canada)"

    BASE = "https://laws-lois.justice.gc.ca"

    def discover(self) -> Iterator[Document]:
        index_url = f"{self.BASE}/eng/acts/"
        r = self.client.get(index_url)
        if r.status_code != 200:
            return
        soup = BeautifulSoup(r.text, "lxml")
        count = 0
        for a in soup.select("a[href*='/eng/acts/']"):
            href = a.get("href", "")
            m = re.search(r"/eng/acts/([A-Za-z0-9.\-]+)/?", href)
            if not m or m.group(1) in ("index.html",):
                continue
            act_id = m.group(1).rstrip(".html").rstrip("/")
            # PDF download endpoint
            pdf_url = f"{self.BASE}/PDF/{act_id}.pdf"
            title = a.get_text(strip=True)
            if not title:
                continue
            yield Document(
                source=self.key, country=self.country, doc_type=self.doc_type,
                title=title, url=pdf_url, citation=act_id,
                landing_url=urljoin(self.BASE, href),
            )
            count += 1
            if count >= self.max_docs:
                return


# ---------------------------------------------------------------------------
# UK — Find Case Law / National Archives (judgments)
# ---------------------------------------------------------------------------

class FindCaseLawUK(Source):
    """UK Supreme Court judgments via the National Archives Find Case Law portal.

    PDFs follow the pattern:
        https://caselaw.nationalarchives.gov.uk/{court}/{year}/{n}/data.pdf
    The search endpoint returns an HTML page with case links.
    """
    key = "uksc_uk"
    country = "uk"
    doc_type = "judgments"
    name = "UK Supreme Court (Find Case Law)"

    BASE = "https://caselaw.nationalarchives.gov.uk"
    COURTS = ["uksc", "ewca", "ewhc"]  # Supreme Court, Court of Appeal, High Court

    def discover(self) -> Iterator[Document]:
        count = 0
        for court in self.COURTS:
            if count >= self.max_docs:
                return
            for page in range(1, 20):
                if count >= self.max_docs:
                    return
                r = self.client.get(
                    f"{self.BASE}/search?query=&court={court}&order=date&page={page}"
                )
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                pattern = re.compile(rf"^/{re.escape(court)}/\d{{4}}/\d+$")
                loose   = re.compile(r"^/[a-z]+/\d{4}/\d+$")
                links = [
                    a for a in soup.find_all("a", href=True)
                    if pattern.match(a["href"]) or loose.match(a["href"])
                ]
                if not links:
                    break
                for a in links:
                    href = a["href"]
                    m = re.match(r"^/([a-z]+)/(\d{4})/(\d+)$", href)
                    if not m:
                        continue
                    c, year, num = m.group(1), m.group(2), m.group(3)
                    pdf_url = f"{self.BASE}/{c}/{year}/{num}/data.pdf"
                    title = a.get_text(strip=True) or f"{c.upper()} {year}/{num}"
                    yield Document(
                        source=self.key, country=self.country, doc_type=self.doc_type,
                        title=title, url=pdf_url, year=year,
                        citation=f"[{year}] {c.upper()} {num}",
                        landing_url=f"{self.BASE}{href}",
                    )
                    count += 1
                    if count >= self.max_docs:
                        return


# ---------------------------------------------------------------------------
# UK — legislation.gov.uk (statutes)
# ---------------------------------------------------------------------------

class LegislationGovUK(Source):
    """UK Public General Acts via the legislation.gov.uk Atom feed.

    One feed request returns many valid acts — no URL probing needed.
    Feed: https://www.legislation.gov.uk/ukpga/data.feed?page=N
    PDF:  https://www.legislation.gov.uk/ukpga/{year}/{n}/data.pdf
    """
    key = "ukpga_uk"
    country = "uk"
    doc_type = "statutes"
    name = "UK Legislation (legislation.gov.uk)"

    BASE = "https://www.legislation.gov.uk"
    FEED = "https://www.legislation.gov.uk/ukpga/data.feed"

    def discover(self) -> Iterator[Document]:
        # legislation.gov.uk blocks bot scraping (HTTP 437).
        # UK acts are numbered sequentially from 1 each year. Generate
        # candidate URLs directly; download() handles any 404 gaps.
        for year in range(2024, 2019, -1):
            for num in range(1, 61):
                pdf_url = f"{self.BASE}/ukpga/{year}/{num}/data.pdf"
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=f"UK Public General Act {year} c. {num}",
                    url=pdf_url, year=str(year),
                    citation=f"{year} c. {num}",
                    landing_url=f"{self.BASE}/ukpga/{year}/{num}",
                )


# ---------------------------------------------------------------------------
# USA — Supreme Court slip opinions (judgments)
# ---------------------------------------------------------------------------

class USSupremeCourt(Source):
    """US Supreme Court slip opinions from supremecourt.gov.

    Each term's opinion list is at /opinions/slipopinion/{YY} (two-digit year).
    The page has a table where each row has a PDF link.
    """
    key = "scotus_usa"
    country = "usa"
    doc_type = "judgments"
    name = "US Supreme Court (slip opinions)"

    BASE = "https://www.supremecourt.gov"

    def discover(self) -> Iterator[Document]:
        count = 0
        # Terms run from October; use two-digit year of the spring decision date
        for term in range(24, 9, -1):  # 24 = 2024-25 term, back to 2009-10
            if count >= self.max_docs:
                return
            r = self.client.get(f"{self.BASE}/opinions/slipopinion/{term:02d}")
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for row in soup.select("table tr"):
                tds = row.find_all("td")
                if len(tds) < 4:
                    continue
                pdf_a = row.select_one("a[href$='.pdf']")
                if not pdf_a:
                    continue
                pdf_url = urljoin(self.BASE, pdf_a["href"])
                # Skip non-opinion PDFs (reporter guide, media services, etc.)
                if "publicinfo" in pdf_url or "reportersguide" in pdf_url:
                    continue
                title = tds[3].get_text(strip=True) if len(tds) > 3 else pdf_a.get_text(strip=True)
                citation = tds[5].get_text(strip=True) if len(tds) > 5 else ""
                year = str(2000 + term)
                yield Document(
                    source=self.key, country=self.country, doc_type=self.doc_type,
                    title=title, url=pdf_url, year=year,
                    citation=citation,
                    landing_url=f"{self.BASE}/opinions/slipopinion/{term:02d}",
                )
                count += 1
                if count >= self.max_docs:
                    return


# ---------------------------------------------------------------------------
# USA — US Code titles via govinfo.gov (statutes)
# ---------------------------------------------------------------------------

class USCode(Source):
    """United States Code from govinfo.gov — one PDF per Title.

    Direct PDF URLs follow:
        https://www.govinfo.gov/content/pkg/USCODE-{year}-title{n}/pdf/USCODE-{year}-title{n}.pdf
    The US Code has 54 titles (some are reserved/repealed but govinfo returns
    404 for those, which we skip).
    """
    key = "usc_usa"
    country = "usa"
    doc_type = "statutes"
    name = "US Code (govinfo.gov)"

    BASE = "https://www.govinfo.gov"
    EDITION_YEAR = 2023  # most recent published edition

    # Title names for better metadata
    TITLE_NAMES = {
        1: "General Provisions", 2: "The Congress", 3: "The President",
        4: "Flag and Seal, Seat of Government, and the States",
        5: "Government Organization and Employees",
        6: "Domestic Security", 7: "Agriculture", 8: "Aliens and Nationality",
        9: "Arbitration", 10: "Armed Forces", 11: "Bankruptcy",
        12: "Banks and Banking", 13: "Census", 14: "Coast Guard",
        15: "Commerce and Trade", 16: "Conservation",
        17: "Copyrights", 18: "Crimes and Criminal Procedure",
        19: "Customs Duties", 20: "Education",
        21: "Food and Drugs", 22: "Foreign Relations and Intercourse",
        23: "Highways", 24: "Hospitals and Asylums",
        25: "Indians", 26: "Internal Revenue Code",
        27: "Intoxicating Liquors", 28: "Judiciary and Judicial Procedure",
        29: "Labor", 30: "Mineral Lands and Mining",
        31: "Money and Finance", 32: "National Guard",
        33: "Navigation and Navigable Waters", 34: "Navy (repealed)",
        35: "Patents", 36: "Patriotic and National Observances",
        37: "Pay and Allowances of the Uniformed Services",
        38: "Veterans Benefits", 39: "Postal Service",
        40: "Public Buildings, Property, and Works",
        41: "Public Contracts", 42: "The Public Health and Welfare",
        43: "Public Lands", 44: "Public Printing and Documents",
        45: "Railroads", 46: "Shipping",
        47: "Telecommunications", 48: "Territories and Insular Possessions",
        49: "Transportation", 50: "War and National Defense",
        51: "National and Commercial Space Programs",
        52: "Voting and Elections", 53: "Reserved", 54: "National Park Service",
    }

    def discover(self) -> Iterator[Document]:
        count = 0
        year = self.EDITION_YEAR
        for title_num in range(1, 55):
            if count >= self.max_docs:
                return
            pkg = f"USCODE-{year}-title{title_num}"
            pdf_url = f"{self.BASE}/content/pkg/{pkg}/pdf/{pkg}.pdf"
            title_name = self.TITLE_NAMES.get(title_num, f"Title {title_num}")
            yield Document(
                source=self.key, country=self.country, doc_type=self.doc_type,
                title=f"US Code Title {title_num} — {title_name}",
                url=pdf_url, year=str(year),
                citation=f"{year} U.S.C. Title {title_num}",
                landing_url=f"{self.BASE}/app/details/{pkg}",
            )
            count += 1


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

ALL_SOURCES: list[type[Source]] = [
    HighCourtAustralia,
    FederalRegisterAU,
    CourtsServiceIE,
    IrishStatuteBook,
    SupremeCourtCanada,
    JusticeLawsCanada,
    FindCaseLawUK,
    LegislationGovUK,
    USSupremeCourt,
    USCode,
]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(out_dir: Path, sources: list[type[Source]], max_per_source: int,
        delay: float, max_per_country: Optional[int] = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    client = PoliteClient(delay=delay)

    # Resume support: load already-downloaded URLs
    seen_urls: set[str] = set()
    country_counts: dict[str, int] = {}
    if manifest_path.exists():
        with manifest_path.open() as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    seen_urls.add(rec["url"])
                    country_counts[rec["country"]] = country_counts.get(rec["country"], 0) + 1
                except Exception:
                    pass
        print(f"Resume: {len(seen_urls)} URLs already in manifest")

    total_downloaded = 0
    total_failed = 0

    with manifest_path.open("a", encoding="utf-8") as manifest:
        for SourceCls in sources:
            src = SourceCls(client, max_per_source)
            print(f"\n{'='*70}")
            print(f"Source: {src.name}")
            print(f"  country={src.country}  type={src.doc_type}  "
                  f"max={max_per_source}")
            if max_per_country:
                already = country_counts.get(src.country, 0)
                print(f"  country cap={max_per_country}  already={already}")
            print('='*70)

            try:
                docs = list(src.discover())
            except Exception as e:
                print(f"  ! discovery failed: {e}")
                continue

            print(f"  Discovered {len(docs)} candidate documents")

            for doc in tqdm(docs, desc=src.key, unit="pdf"):
                if doc.url in seen_urls:
                    continue
                if max_per_country is not None:
                    if country_counts.get(doc.country, 0) >= max_per_country:
                        break
                fn = safe_filename(f"{src.key}_{doc.year}_{doc.title}") + ".pdf"
                dest = out_dir / doc.country / doc.doc_type / fn
                ok = client.download(doc.url, dest)
                if ok:
                    record = asdict(doc)
                    record["local_path"] = str(dest.relative_to(out_dir))
                    manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
                    manifest.flush()
                    seen_urls.add(doc.url)
                    country_counts[doc.country] = country_counts.get(doc.country, 0) + 1
                    total_downloaded += 1
                else:
                    total_failed += 1

    print(f"\n{'='*70}")
    print(f"Done. Downloaded: {total_downloaded}   Failed: {total_failed}")
    print(f"Manifest: {manifest_path}")
    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--output", type=Path, default=Path("./legal_pdfs"),
                   help="Output directory (default: ./legal_pdfs)")
    p.add_argument("--countries", type=str, default=None,
                   help="Comma-separated: australia,ireland,canada")
    p.add_argument("--sources", type=str, default=None,
                   help="Comma-separated source keys (see --list)")
    p.add_argument("--max-per-source", type=int, default=DEFAULT_MAX_PER_SOURCE,
                   help=f"Max PDFs per source (default: {DEFAULT_MAX_PER_SOURCE})")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC,
                   help=f"Delay between requests in seconds (default: {DEFAULT_DELAY_SEC})")
    p.add_argument("--max-per-country", type=int, default=None,
                   help="Max total PDFs per country across all sources (e.g. 5)")
    p.add_argument("--list", action="store_true",
                   help="List all sources and exit")
    args = p.parse_args()

    if args.list:
        print(f"{'Key':<22}{'Country':<12}{'Type':<12}{'Name'}")
        print("-" * 80)
        for S in ALL_SOURCES:
            print(f"{S.key:<22}{S.country:<12}{S.doc_type:<12}{S.name}")
        return

    sources = ALL_SOURCES
    if args.countries:
        wanted = {c.strip().lower() for c in args.countries.split(",")}
        sources = [S for S in sources if S.country in wanted]
    if args.sources:
        wanted = {s.strip() for s in args.sources.split(",")}
        sources = [S for S in sources if S.key in wanted]

    if not sources:
        sys.exit("No sources matched your filters. Use --list to see options.")

    print(f"Will run {len(sources)} source(s):")
    for S in sources:
        print(f"  - {S.key}  ({S.country}/{S.doc_type})")

    run(args.output, sources, args.max_per_source, args.delay, args.max_per_country)


if __name__ == "__main__":
    main()