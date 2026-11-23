"""
Fetch the farmingdale.edu pages Rambo linked, so the hallucination check can
confirm that every phone number, email, price and year in an answer is really
on one of them.

Only farmingdale.edu URLs are fetched, each at most once per run. The raw HTML
is kept (not just visible text), so a mailto: link or a number in an
attribute still counts. PDFs and pages that fail to load come back as None,
and the check reports what they leave unverified instead of guessing.
"""

from __future__ import annotations

import html
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from apps.assistant.rambo import is_allowed_url

USER_AGENT = "RamHub-eval/1.0 (student project evaluation suite)"
MAX_BYTES = 3_000_000
TIMEOUT = 20


def fetch(url: str) -> str | None:
    """The page's HTML, unescaped, or None for a PDF, a failure, or a non-FSC URL."""
    if not is_allowed_url(url):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            kind = response.headers.get("Content-Type", "")
            if "html" not in kind and "text" not in kind:
                return None
            raw = response.read(MAX_BYTES)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return html.unescape(raw.decode("utf-8", errors="ignore"))


def fetch_all(urls: Iterable[str], workers: int = 8) -> dict[str, str | None]:
    unique = sorted(set(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(unique, pool.map(fetch, unique), strict=True))
