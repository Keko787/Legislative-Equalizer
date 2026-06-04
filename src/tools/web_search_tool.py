"""
Search backend abstraction and the WebSearchTool that wraps it.

Two backends are supported:
- TavilyBackend (preferred): JSON API tuned for LLM agents. Selected when
  TAVILY_API_KEY is present in env and the tavily-python package imports.
- DDGHTMLBackend (fallback): scrape DuckDuckGo's HTML results page. No
  API key needed. Brittle — DDG can change layout or rate-limit.

Both share the SearchBackend interface so callers don't change.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence
from urllib.parse import parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_TIMEOUT = 10.0
DDG_USER_AGENT = (
    "Mozilla/5.0 (compatible; LawAgent-Research/0.1) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str


class SearchBackend(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        include_domains: Sequence[str] = (),
        max_results: int = 5,
    ) -> List[SearchHit]:
        ...


class DDGHTMLBackend(SearchBackend):
    """Best-effort DuckDuckGo HTML scrape. No API key required, brittle."""

    def search(
        self,
        query: str,
        include_domains: Sequence[str] = (),
        max_results: int = 5,
    ) -> List[SearchHit]:
        if include_domains:
            sites = " OR ".join(f"site:{d}" for d in include_domains)
            full_query = f"({sites}) {query}"
        else:
            full_query = query

        try:
            resp = httpx.post(
                DDG_URL,
                data={"q": full_query},
                timeout=DDG_TIMEOUT,
                headers={"User-Agent": DDG_USER_AGENT},
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                log.warning("DDG returned http %s for query=%r", resp.status_code, full_query)
                return []
        except Exception as e:
            log.warning("DDG search failed: %s", e)
            return []

        return self._parse(resp.text, max_results)

    @staticmethod
    def _parse(html: str, max_results: int) -> List[SearchHit]:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []

        hits: List[SearchHit] = []
        for result in soup.select("div.result"):
            link = result.select_one("a.result__a")
            snippet = result.select_one(".result__snippet")
            if not link:
                continue
            url = DDGHTMLBackend._unwrap_url(link.get("href", ""))
            if not url:
                continue
            hits.append(SearchHit(
                url=url,
                title=link.get_text(strip=True),
                snippet=snippet.get_text(strip=True) if snippet else "",
            ))
            if len(hits) >= max_results:
                break

        if not hits:
            log.warning("DDG returned 0 hits — parser may be broken or rate-limited")
        return hits

    @staticmethod
    def _unwrap_url(url: str) -> str:
        if not url:
            return ""
        if url.startswith("//"):
            url = "https:" + url
        # DDG often wraps results in /l/?uddg=ENCODED
        if "duckduckgo.com/l/" in url and "uddg=" in url:
            try:
                qs = url.split("?", 1)[1]
                params = parse_qs(qs)
                target = params.get("uddg", [""])[0]
                return unquote(target)
            except Exception:
                return ""
        return url


class TavilyBackend(SearchBackend):
    """Tavily search API. Native include_domains, JSON output, AI-tuned ranking."""

    def __init__(self, api_key: str):
        # Imported lazily so the package is only required when this backend is used.
        from tavily import TavilyClient
        self._client = TavilyClient(api_key=api_key)

    def search(
        self,
        query: str,
        include_domains: Sequence[str] = (),
        max_results: int = 5,
    ) -> List[SearchHit]:
        try:
            kwargs = {
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
            }
            if include_domains:
                kwargs["include_domains"] = list(include_domains)
            resp = self._client.search(**kwargs)
        except Exception as e:
            log.warning("Tavily search failed: %s", e)
            return []

        results = (resp or {}).get("results", []) or []
        hits: List[SearchHit] = []
        for r in results:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            hits.append(SearchHit(
                url=url,
                title=(r.get("title") or "").strip(),
                snippet=(r.get("content") or "").strip(),
            ))
            if len(hits) >= max_results:
                break
        if not hits:
            log.info("Tavily returned 0 hits for query=%r", query)
        return hits


class WebSearchTool:
    """Thin facade that selects a SearchBackend at construction time."""

    def __init__(self, backend: Optional[SearchBackend] = None):
        self._backend = backend or self._default_backend()

    @staticmethod
    def _default_backend() -> SearchBackend:
        api_key = os.getenv("TAVILY_API_KEY")
        if api_key:
            try:
                backend = TavilyBackend(api_key=api_key)
                log.info("WebSearchTool using TavilyBackend")
                return backend
            except ImportError:
                log.warning(
                    "TAVILY_API_KEY set but tavily-python not installed; "
                    "falling back to DDGHTMLBackend."
                )
            except Exception as e:
                log.warning("TavilyBackend init failed (%s); falling back to DDG.", e)
        log.warning(
            "WebSearchTool using DDGHTMLBackend (no TAVILY_API_KEY) — "
            "results may be lower quality and the parser is brittle."
        )
        return DDGHTMLBackend()

    def search(
        self,
        query: str,
        include_domains: Sequence[str] = (),
        max_results: int = 5,
    ) -> List[SearchHit]:
        return self._backend.search(query, include_domains, max_results)
