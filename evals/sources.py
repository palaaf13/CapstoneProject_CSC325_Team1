"""
Fetch the farmingdale.edu pages Rambo linked, so the hallucination check can
confirm that every phone number, email, price and year in an answer is really
on one of them.

Only farmingdale.edu URLs are fetched, each at most once per run, and a
redirect is followed only if it also stays on farmingdale.edu. The raw HTML
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
from urllib.parse import urljoin

from apps.assistant.rambo import is_allowed_url

USER_AGENT = "RamHub-eval/1.0 (student project evaluation suite)"
MAX_BYTES = 3_000_000
TIMEOUT = 20


class _FSCOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only if it stays on farmingdale.edu (same rule as the
    first URL), so a link can't bounce the fetcher to another or internal host."""

    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not is_allowed_url(target):
            raise urllib.error.HTTPError(target, code, "redirect off farmingdale.edu", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, target)


_OPENER = urllib.request.build_opener(_FSCOnlyRedirects)


def fetch(url: str) -> str | None:
    """The page's HTML, unescaped, or None for a PDF, a failure, a redirect off
    farmingdale.edu, or a URL that isn't on farmingdale.edu."""
    if not is_allowed_url(url):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(request, timeout=TIMEOUT) as response:
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
