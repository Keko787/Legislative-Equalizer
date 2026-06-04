"""
Content extractor for fetched HTML pages.

Strips boilerplate (nav, ads, scripts), returns main article text. Primary
backend is `trafilatura`; falls back to a bs4 tag-denylist if trafilatura
returns too little. Rejects pages that look like paywalls or login walls.
"""

import logging
from typing import Optional

import trafilatura
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

PAYWALL_PATTERNS = (
    "subscribe to read",
    "subscribe to continue",
    "sign in to continue",
    "log in to read",
    "premium content",
    "create a free account to",
    "this article is for subscribers",
    "members only",
)
MAX_EXTRACT_BYTES = 4096
MIN_EXTRACT_LENGTH = 200


def extract(html: str, url: str = "") -> Optional[str]:
    """
    Extract main text from HTML. Returns None if the page is empty,
    paywalled, or yields too little content to be useful.
    """
    if not html:
        return None

    text = None
    try:
        text = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
        )
    except Exception as e:
        log.debug("trafilatura extract failed for %s: %s", url, e)

    if not text or len(text) < MIN_EXTRACT_LENGTH:
        text = _bs4_fallback(html)

    if not text or len(text) < MIN_EXTRACT_LENGTH:
        return None

    text_low = text.lower()
    if any(p in text_low for p in PAYWALL_PATTERNS):
        log.debug("paywall keyword detected, dropping: %s", url)
        return None

    if len(text) > MAX_EXTRACT_BYTES:
        text = text[:MAX_EXTRACT_BYTES]
    return text


def _bs4_fallback(html: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside", "form", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text or None
    except Exception:
        return None
