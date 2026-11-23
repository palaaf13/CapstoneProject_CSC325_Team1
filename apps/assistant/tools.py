"""
The RamHub lookups Rambo can call. Each returns plain dicts (no model objects)
with a RamHub "url" for every record, so Rambo can link what it mentions.

These read the same services the site's own pages and search box use.
"""

from functools import lru_cache
from html import unescape

from django.db.models import Q
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.campus import services as campus
from apps.campus.models import Club
from apps.catalog import services as catalog
from apps.catalog.models import Course, Professor

from .rambo import Tool

RESULTS = 5
GUIDES = {
    "parking": ("campus/parking.html", "campus:parking"),
    "jobs": ("campus/jobs.html", "campus:jobs"),
    "facilities": ("campus/facilities.html", "campus:facilities"),
}


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _query(data: dict, key: str = "query") -> str:
    return _clip(str(data.get(key) or ""), 100)


# -- courses ------------------------------------------------------------------
def course_record(course: Course) -> dict:
    s = course.rating_summary
    return {
        "code": course.code,
        "title": course.title,
        "credits": course.credits,
        "department": course.department,
        "prerequisites": course.prereq_text or "none listed",
        "corequisites": course.coreq_text or "none listed",
        "description": _clip(course.description, 400),
        "ramhub_student_ratings": (
            {
                "difficulty": s.avg_difficulty,
                "workload": s.avg_workload,
                "usefulness": s.avg_usefulness,
                "count": s.count,
            }
            if s.has_ratings
            else None
        ),
        "url": reverse("catalog:course_detail", kwargs={"code": course.slug}),
    }


def search_courses(data: dict) -> dict:
    q = _query(data)
    found = list(catalog.search_courses(q=q)[:RESULTS]) if q else []
    if not found and q:
        # "intro programming": every word somewhere in the title or description.
        words = Q()
        for word in q.split():
            words &= Q(title__icontains=word) | Q(description__icontains=word)
        found = list(Course.objects.filter(words).order_by("code")[:RESULTS])
    return {"query": q, "courses": [course_record(c) for c in found]}


# -- professors ---------------------------------------------------------------
def professor_record(professor: Professor) -> dict:
    s = professor.rating_summary
    ramhub = None
    if s.has_ratings and not s.is_from_rmp:
        ramhub = {
            "clarity": s.avg_clarity,
            "helpfulness": s.avg_helpfulness,
            "fairness": s.avg_fairness,
            "count": s.count,
        }
    rmp = None
    if professor.rmp_num_ratings:
        rmp = {
            "quality": professor.rmp_avg_rating,
            "difficulty": professor.rmp_avg_difficulty,
            "would_take_again_pct": professor.rmp_would_take_again_pct,
            "count": professor.rmp_num_ratings,
            "note": "RateMyProfessors, self-selected opinions",
        }
    return {
        "name": professor.full_name,
        "title": professor.title,
        "department": professor.department,
        "office": professor.office or "not listed",
        "phone": professor.phone or "not listed",
        "courses": [c.code for c in catalog.courses_for_professor(professor)],
        "ramhub_student_ratings": ramhub,
        "ratemyprofessors": rmp,
        "url": reverse("catalog:professor_detail", kwargs={"slug": professor.slug}),
    }


def search_professors(data: dict) -> dict:
    q, department = _query(data), _query(data, "department")
    if not q and not department:
        return {"error": "Give a name or a department."}
    found = catalog.search_professors(q=q)
    if department:
        found = found.filter(department__icontains=department)
    return {"query": q, "professors": [professor_record(p) for p in found[:RESULTS]]}


# -- clubs and events ---------------------------------------------------------
def club_record(club: Club) -> dict:
    return {
        "name": club.name,
        "short_name": club.short_name,
        "summary": _clip(club.summary or club.description, 300),
        "categories": club.categories,
        "meetings": _clip(club.meeting_info, 200) or "not listed",
        "contact_email": club.contact_email or "not listed",
        "url": reverse("campus:club_detail", kwargs={"slug": club.slug}),
    }


def search_clubs(data: dict) -> dict:
    q = _query(data)
    found = list(campus.search_clubs(q=q)[:RESULTS]) if q else []
    return {"query": q, "clubs": [club_record(c) for c in found]}


def upcoming_events(data: dict) -> dict:
    q = _query(data)
    events = campus.search_events(q) if q else campus.upcoming_events(limit=RESULTS)
    tz = timezone.get_current_timezone()
    return {
        "query": q,
        "today": timezone.localdate().isoformat(),
        "events": [
            {
                "title": e.title,
                "club": e.club.name,
                "starts": timezone.localtime(e.starts_at, tz).strftime("%a %b %-d, %-I:%M %p"),
                "location": e.location,
                "details": _clip(e.details, 200),
                "url": reverse("campus:club_detail", kwargs={"slug": e.club.slug}),
            }
            for e in events[:RESULTS]
        ],
        "all_events_url": reverse("campus:events"),
    }


# -- campus guides ------------------------------------------------------------
@lru_cache(maxsize=len(GUIDES))
def guide_text(topic: str) -> str:
    """RamHub's own guide page as plain text: the page's <main>, tags stripped."""
    template, _ = GUIDES[topic]
    from apps.campus.views import GUIDES_CHECKED

    html = render_to_string(
        template, {"checked": GUIDES_CHECKED}, request=RequestFactory().get("/")
    )
    start, end = html.find("<main"), html.rfind("</main>")
    if start != -1 and end != -1:
        html = html[start:end]
    lines = (" ".join(line.split()) for line in unescape(strip_tags(html)).splitlines())
    return "\n".join(line for line in lines if line)


def campus_guide(data: dict) -> dict:
    topic = str(data.get("topic") or "").lower()
    if topic not in GUIDES:
        return {"error": f"Unknown topic. Choose one of: {', '.join(GUIDES)}."}
    return {
        "topic": topic,
        "text": guide_text(topic),
        "url": reverse(GUIDES[topic][1]),
    }


def _text_input(description: str, extra: dict | None = None) -> dict:
    properties = {"query": {"type": "string", "description": description}}
    properties.update(extra or {})
    return {"type": "object", "properties": properties, "required": ["query"]}


def ramhub_tools() -> list[Tool]:
    return [
        Tool(
            "search_courses",
            "Search the FSC course catalog by course code (e.g. 'BCS 109') or words in the "
            "title (e.g. 'calculus'). Returns credits, department, prerequisites, a short "
            "description, RamHub student ratings if any, and the RamHub page url.",
            _text_input("A course code or title words."),
            search_courses,
        ),
        Tool(
            "search_professors",
            "Look up FSC faculty by name, optionally within a department. Returns title, "
            "department, office, phone, courses on record, ratings (RamHub students and/or "
            "RateMyProfessors, labelled), and the RamHub page url.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "First and/or last name."},
                    "department": {"type": "string", "description": "Optional department."},
                },
                "required": ["query"],
            },
            search_professors,
        ),
        Tool(
            "search_clubs",
            "Search FSC's student organizations by name, topic or interest (e.g. 'coding', "
            "'soccer', 'nursing'). Returns a summary, categories, meeting info, contact email, "
            "and the RamHub page url.",
            _text_input("Club name or an interest."),
            search_clubs,
        ),
        Tool(
            "upcoming_events",
            "Upcoming club events posted on RamHub, soonest first. Leave query empty for "
            "everything coming up, or filter by words (club, topic, place).",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Optional filter."}},
            },
            upcoming_events,
        ),
        Tool(
            "campus_guide",
            "RamHub's guides, copied from official FSC pages: 'parking' (permits, where to "
            "park, tickets, University Police), 'jobs' (campus jobs, work-study, Nexus Center "
            "career help), 'facilities' (library and fitness center hours, dining, meal blocks).",
            {
                "type": "object",
                "properties": {"topic": {"type": "string", "enum": list(GUIDES)}},
                "required": ["topic"],
            },
            campus_guide,
        ),
    ]
