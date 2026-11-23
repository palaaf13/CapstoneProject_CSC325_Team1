"""Render Rambo's answers: a small, safe subset of Markdown.

Everything is HTML-escaped first. Then only these come back: [label](url)
links to RamHub paths or farmingdale.edu, **bold**, "- " bullet lists, and
paragraphs. No raw HTML from the model ever reaches the page.
"""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.assistant.rambo import is_allowed_url

register = template.Library()

_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")


def _inline(text: str) -> str:
    def link(match: re.Match) -> str:
        label, url = match.group(1), match.group(2).replace("&amp;", "&")
        if not is_allowed_url(url):
            return label
        external = not url.startswith("/")
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return f'<a href="{escape(url)}" class="text-accent-700 underline"{attrs}>{label}</a>'

    text = _LINK.sub(link, text)
    return _BOLD.sub(r"<strong>\1</strong>", text)


@register.filter
def rambo_markdown(text: str) -> str:
    html, bullets = [], []

    def flush() -> None:
        if bullets:
            items = "".join(f"<li>{_inline(b)}</li>" for b in bullets)
            html.append(f'<ul class="ml-5 list-disc space-y-1">{items}</ul>')
            bullets.clear()

    for line in escape(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            bullets.append(stripped[2:])
            continue
        flush()
        if stripped:
            html.append(f"<p>{_inline(stripped)}</p>")
    flush()
    return mark_safe("".join(html))
