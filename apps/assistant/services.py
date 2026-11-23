"""
Django side of Rambo: settings, the API client, the hourly limit, and the
non-AI fallback. The prompt, the search loop and the link rules live in
rambo.py, shared with the evaluation suite.
"""

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

import anthropic
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from config.search import site_search

from . import rambo
from .models import RamboQuestion
from .rambo import RamboResult

logger = logging.getLogger(__name__)

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


def _reserve_slot(user) -> RamboQuestion | None:
    """Claim one of the student's hourly questions *before* calling the API.

    Insert first, then count the rows up to and including this one. However
    requests interleave, each slot's place in line is fixed by its timestamp,
    so only the first N in an hour pass; a burst of simultaneous requests
    can't slip extra questions through. Returns None when over the limit."""
    slot = RamboQuestion.objects.create(
        user=user, model=settings.RAMBO_MODEL, prompt_version=rambo.PROMPT_VERSION
    )
    since = timezone.now() - timedelta(hours=1)
    earlier = RamboQuestion.objects.filter(
        user=user, asked_at__gte=since, asked_at__lte=slot.asked_at
    )
    if earlier.count() > settings.RAMBO_HOURLY_LIMIT:
        slot.delete()
        return None
    return slot


def ask(user, question: str, history: list[dict]) -> RamboResult:
    """Ask Rambo on a student's behalf: enforce the hourly limit and record the
    question's cost (never its text). The student always gets an answer or the
    fallback: a database problem here degrades to the fallback, not an error."""
    if not " ".join((question or "").split()):
        return RamboResult(fallback_reason="empty_question")
    try:
        slot = _reserve_slot(user)
    except Exception as exc:
        logger.warning("Rambo could not reserve a question slot: %s", type(exc).__name__)
        return RamboResult(fallback_reason="unavailable")
    if slot is None:
        return RamboResult(fallback_reason="hourly_limit")

    result = rambo.ask(
        question,
        client=get_client(),
        history=history,
        model=settings.RAMBO_MODEL,
    )
    try:
        slot.fallback_reason = result.fallback_reason or ""
        slot.api_calls = result.usage.get("api_calls", 0)
        slot.input_tokens = result.usage.get("input_tokens", 0)
        slot.output_tokens = result.usage.get("output_tokens", 0)
        slot.web_searches = result.usage.get("web_searches", 0)
        slot.save()
    except Exception as exc:  # The answer is still worth showing.
        logger.warning("Rambo could not record a question's usage: %s", type(exc).__name__)
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
    """When Rambo can't answer: RamHub pages that match the question's words,
    from the site's own search and guide pages. No AI involved. (Rambo itself
    answers from farmingdale.edu; this is only the safety net.)"""
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
