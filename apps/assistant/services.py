"""
Django side of Rambo: settings, the API client, the hourly limit, checking the
links in an answer, and the non-AI fallback. The prompt and the tool loop live
in rambo.py, shared with the evaluation suite.
"""

import re
from dataclasses import dataclass, replace
from datetime import timedelta

import anthropic
from django.conf import settings
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone

from apps.campus.models import Club
from apps.catalog import services as catalog
from apps.catalog.models import Professor
from config.search import site_search

from . import rambo
from .models import RamboQuestion
from .rambo import RamboResult
from .tools import ramhub_tools

STOPWORDS = {
    "about", "anyone", "best", "campus", "class", "classes", "could", "does", "farmingdale",
    "find", "good", "have", "help", "know", "like", "looking", "need", "rambo", "should",
    "some", "tell", "that", "there", "they", "what", "when", "where", "which", "with",
    "would", "your", "college", "state", "take", "want", "this", "from", "will", "much",
}  # fmt: skip
GUIDE_WORDS = {
    "campus:parking": {"park", "parking", "permit", "ticket", "tickets", "car", "lot"},
    "campus:jobs": {"job", "jobs", "work", "hiring", "internship", "career", "resume"},
    "campus:facilities": {
        "library", "gym", "fitness", "dining", "food", "eat", "meal", "hours", "starbucks",
    },
}  # fmt: skip


def get_client() -> anthropic.Anthropic | None:
    """The API client, or None when Rambo is switched off or no key is configured."""
    if not settings.RAMBO_ENABLED or not settings.ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.AI_TIMEOUT_SECONDS,
        max_retries=1,
    )


def questions_this_hour(user) -> int:
    since = timezone.now() - timedelta(hours=1)
    return RamboQuestion.objects.filter(user=user, asked_at__gte=since).count()


def ramhub_link_exists(url: str) -> bool:
    """A RamHub path in an answer must lead somewhere real: the page resolves,
    and a course, professor or club it names exists."""
    if not url.startswith("/") or url.startswith("//"):
        return rambo.is_allowed_url(url)
    try:
        match = resolve(url.split("?")[0].split("#")[0])
    except Resolver404:
        return False
    name, kwargs = match.view_name, match.kwargs
    if name == "catalog:course_detail":
        return catalog.get_course_by_code(kwargs["code"]) is not None
    if name == "catalog:professor_detail":
        return Professor.objects.filter(slug=kwargs["slug"]).exists()
    if name == "campus:club_detail":
        return Club.objects.filter(slug=kwargs["slug"]).exists()
    return True


def ask(user, question: str, history: list[dict]) -> RamboResult:
    """Ask Rambo on a student's behalf: enforce the hourly limit, check the
    answer's links, and record the question (not its text) for cost tracking."""
    if questions_this_hour(user) >= settings.RAMBO_HOURLY_LIMIT:
        return RamboResult(fallback_reason="hourly_limit")

    result = rambo.ask(
        question,
        tools=ramhub_tools(),
        client=get_client(),
        history=history,
        model=settings.RAMBO_MODEL,
    )
    if result.ok:
        text, removed = rambo.clean_links(result.answer.text, keep=ramhub_link_exists)
        if removed:
            answer = replace(
                result.answer, text=text, links_removed=result.answer.links_removed + removed
            )
            result = replace(result, answer=answer)

    if result.fallback_reason != "empty_question":
        RamboQuestion.objects.create(
            user=user,
            fallback_reason=result.fallback_reason or "",
            api_calls=result.usage.get("api_calls", 0),
            input_tokens=result.usage.get("input_tokens", 0),
            output_tokens=result.usage.get("output_tokens", 0),
            web_searches=result.usage.get("web_searches", 0),
            model=settings.RAMBO_MODEL,
            prompt_version=rambo.PROMPT_VERSION,
        )
    return result


@dataclass(frozen=True)
class Link:
    label: str
    url: str


def _result_link(key: str, obj) -> Link:
    if key == "courses":
        return Link(f"{obj.code} {obj.title}", reverse("catalog:course_detail", args=[obj.slug]))
    if key == "professors":
        return Link(obj.full_name, reverse("catalog:professor_detail", args=[obj.slug]))
    if key == "clubs":
        return Link(obj.name, reverse("campus:club_detail", args=[obj.slug]))
    return Link(
        f"{obj.title} ({obj.club.name})", reverse("campus:club_detail", args=[obj.club.slug])
    )


def fallback_links(question: str, *, limit: int = 6) -> list[Link]:
    """When Rambo can't answer: RamHub pages that match the question's words.
    No AI involved, just the site's own search and guide pages."""
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2]
    links: dict[str, Link] = {}
    labels = {"campus:parking": "Parking guide", "campus:jobs": "Jobs guide",
              "campus:facilities": "Library, gym and dining guide"}  # fmt: skip
    for url_name, triggers in GUIDE_WORDS.items():
        if triggers & set(words):
            url = reverse(url_name)
            links[url] = Link(labels[url_name], url)

    # Course codes first ("bcs 109"), then each meaningful word on its own.
    terms = [f"{a} {b}" for a, b in re.findall(r"\b([a-z]{2,4})\s?(\d{3})\b", question.lower())]
    terms += [w for w in words if len(w) >= 4 and w not in STOPWORDS]
    for term in terms[:4]:
        for section in site_search(term, limit=2):
            for obj in section.results:
                link = _result_link(section.key, obj)
                links.setdefault(link.url, link)
        if len(links) >= limit:
            break
    return list(links.values())[:limit]
