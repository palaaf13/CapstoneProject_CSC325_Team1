"""
Global search: one box in the nav that looks across every directory.

It does no searching of its own. Each section reuses its directory's search
service, so a query matches exactly the same courses, professors, and clubs
here as it does on that directory's page, and "See all" hands the query over.

Kept at site level (like config/views.py) because it spans several apps.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlencode

from django import forms
from django.urls import reverse

from apps.campus import services as campus
from apps.catalog import services as catalog
from apps.catalog.forms import MAX_QUERY_LENGTH

# How many results each section shows before "See all".
PREVIEW = 5


class SiteSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=MAX_QUERY_LENGTH, strip=True)


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    results: list
    total: int
    see_all_url: str


def _count(found) -> int:
    # search_clubs returns a ranked list when there are search terms.
    return len(found) if isinstance(found, list) else found.count()


def _course_rank(q: str, course) -> tuple:
    """Lower is better: the code itself, then titles that lead with the words.

    The course directory sorts by code, which is right for browsing but buries
    "Computer Science I" under "Automotive Computer Applications" for a search.
    """
    code = course.code.casefold()
    title = course.title.casefold()
    query = q.casefold()
    normalized = (catalog.normalize_course_code(q) or "").casefold()
    if query == code or normalized == code:
        tier = 0
    elif code.startswith(query) or (normalized and code.startswith(normalized)):
        tier = 1
    elif re.match(rf"{re.escape(query)}\b", title):
        tier = 2  # the title opens with the whole word(s)
    elif re.search(rf"\b{re.escape(query)}\b", title):
        tier = 3
    else:
        tier = 4
    return (tier, code)


def _directory_url(url_name: str, q: str) -> str:
    return f"{reverse(url_name)}?{urlencode({'q': q})}"


def site_search(q: str, *, limit: int = PREVIEW) -> list[Section]:
    """Courses, professors, and clubs matching ``q``, best matches first.

    Sections with no matches are left out. An empty query searches nothing.
    """
    q = q.strip()
    if not q:
        return []

    # The catalog is small (under 2,000 courses), so ranking every match is cheap.
    courses = sorted(catalog.search_courses(q=q), key=lambda course: _course_rank(q, course))
    candidates = [
        ("courses", "Courses", courses, "catalog:courses"),
        ("professors", "Professors", catalog.search_professors(q=q), "catalog:professors"),
        ("clubs", "Clubs", campus.search_clubs(q=q), "campus:clubs"),
    ]
    sections = []
    for key, label, found, url_name in candidates:
        total = _count(found)
        if total:
            sections.append(
                Section(
                    key=key,
                    label=label,
                    results=list(found[:limit]),
                    total=total,
                    see_all_url=_directory_url(url_name, q),
                )
            )
    return sections
