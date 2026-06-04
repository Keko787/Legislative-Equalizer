"""
Web fetch tool for the research sub-agent.

Wraps `httpx` with: per-domain rate limiting (token bucket), robots.txt
honoring, disk cache keyed on URL, body-size and timeout caps, and a
hard-fail-silent contract — all exceptions become `None` returns.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

CACHE_DIR = Path("data/web_cache")
USER_AGENT = "LawAgent-Research/0.1 (+legal-assistant)"
MAX_BODY_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 10.0
ROBOTS_TIMEOUT = 3.0


@dataclass
class FetchResult:
    status: int
    body: str
    final_url: str


class _TokenBucket:
    """Simple per-domain rate limiter."""

    def __init__(self, rate_per_sec: float = 1.0, burst: int = 3):
        self.rate = rate_per_sec
        self.capacity = burst
        self.tokens = float(burst)
        self.last = time.monotonic()

    def acquire(self, max_wait: float = 5.0) -> bool:
        deadline = time.monotonic() + max_wait
        while True:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            remaining = deadline - now
            if remaining <= 0:
                return False
            time.sleep(min(0.5, remaining))


class WebFetchTool:
    """Cache-aware, rate-limited HTTP fetcher. Never raises."""

    def __init__(self, cache_ttl_days: int = 14):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": USER_AGENT},
        )
        self._buckets: Dict[str, _TokenBucket] = {}
        self._robots_cache: Dict[str, RobotFileParser] = {}
        self._cache_ttl_seconds = max(cache_ttl_days, 0) * 86400

    def fetch(self, url: str) -> Optional[FetchResult]:
        try:
            return self._fetch(url)
        except Exception as e:
            log.debug("fetch failed %s: %s", url, e)
            return None

    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> Optional[FetchResult]:
        cached = self._cache_lookup(url)
        if cached is not None:
            return FetchResult(status=200, body=cached, final_url=url)

        if not self._allowed(url):
            log.debug("robots disallow: %s", url)
            return None

        domain = urlparse(url).netloc
        bucket = self._buckets.setdefault(domain, _TokenBucket())
        if not bucket.acquire(max_wait=REQUEST_TIMEOUT):
            log.debug("rate limit timeout: %s", url)
            return None

        try:
            with self._client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    log.debug("http %s for %s", resp.status_code, url)
                    return None
                chunks = []
                total = 0
                truncated = False
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        truncated = True
                        break
                    chunks.append(chunk)
                final_url = str(resp.url)
                status = resp.status_code
            if truncated:
                log.debug("body cap hit for %s (%d bytes)", url, total)
        except Exception as e:
            log.debug("http error %s: %s", url, e)
            return None

        try:
            body = b"".join(chunks).decode("utf-8", errors="replace")
        except Exception:
            return None

        self._cache_store(url, body)
        return FetchResult(status=status, body=body, final_url=final_url)

    # ----- cache --------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{digest}.html"

    def _cache_lookup(self, url: str) -> Optional[str]:
        path = self._cache_path(url)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._cache_ttl_seconds:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _cache_store(self, url: str, body: str) -> None:
        try:
            self._cache_path(url).write_text(body, encoding="utf-8")
        except Exception as e:
            log.debug("cache store failed: %s", e)

    # ----- robots -------------------------------------------------------

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return False
        rp = self._robots_cache.get(domain)
        if rp is None:
            rp = self._load_robots(parsed.scheme, domain)
            self._robots_cache[domain] = rp
        try:
            return rp.can_fetch(USER_AGENT, url)
        except Exception:
            return False

    @staticmethod
    def _load_robots(scheme: str, domain: str) -> RobotFileParser:
        rp = RobotFileParser()
        robots_url = f"{scheme}://{domain}/robots.txt"
        try:
            resp = httpx.get(
                robots_url,
                timeout=ROBOTS_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            if 200 <= resp.status_code < 300:
                rp.parse(resp.text.splitlines())
                return rp
            if resp.status_code in (401, 403):
                # Treat as fully restricted
                rp.disallow_all = True
                return rp
            # 404 / other: assume permissive (no robots)
            rp.parse([])
            return rp
        except Exception:
            # Per design: on fetch failure, default to deny for safety.
            rp.disallow_all = True
            return rp
