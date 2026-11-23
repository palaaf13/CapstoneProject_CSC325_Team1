"""
Django side of the AI review summary: settings, the API client, caching, and
the non-AI fallback text. The prompt, request and validation live in
summarizer.py, shared with the evaluation suite.
"""

import hashlib
import json

import anthropic
from django.conf import settings

from apps.catalog.models import Course, Professor
from apps.ratings import services as ratings

from . import summarizer
from .models import ReviewSummaryCache
from .summarizer import ReviewSummary, SummaryResult


def get_client() -> anthropic.Anthropic | None:
    """The API client, or None when AI summaries are off or no key is configured."""
    if not settings.AI_SUMMARIES_ENABLED or not settings.ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.AI_TIMEOUT_SECONDS,
        max_retries=1,
    )


def cache_key(subject: str, reviews: list[str]) -> str:
    material = json.dumps(
        [summarizer.PROMPT_VERSION, settings.AI_SUMMARY_MODEL, subject, reviews],
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def summarize(subject: str, reviews: list[str]) -> SummaryResult:
    """A summary of these reviews: from the cache if we have one, else from the API."""
    reviews = reviews[: summarizer.MAX_REVIEWS]
    if len(reviews) < summarizer.MIN_REVIEWS:
        return SummaryResult(fallback_reason="not_enough_reviews")

    key = cache_key(subject, reviews)
    cached = ReviewSummaryCache.objects.filter(key=key).first()
    if cached is not None:
        try:
            return SummaryResult(summary=ReviewSummary.from_dict(cached.payload))
        except (KeyError, TypeError, ValueError):
            cached.delete()  # Written by an older shape; regenerate.

    result = summarizer.summarize_reviews(
        subject,
        reviews,
        client=get_client(),
        model=settings.AI_SUMMARY_MODEL,
    )
    if result.ok:
        ReviewSummaryCache.objects.update_or_create(
            key=key, defaults={"payload": result.summary.to_dict()}
        )
    return result


def course_reviews(course: Course) -> list[str]:
    return [r.comment for r in ratings.course_comments(course, limit=summarizer.MAX_REVIEWS)]


def professor_reviews(professor: Professor) -> list[str]:
    return [r.comment for r in ratings.professor_comments(professor, limit=summarizer.MAX_REVIEWS)]


def _fmt(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "?"


def course_fallback(course: Course) -> str:
    """What the box says when the AI cannot: the averages, in words. No AI involved."""
    s = course.rating_summary
    if not s.has_ratings:
        return ""
    return (
        f"From {s.count} student rating{'s' if s.count != 1 else ''}: difficulty "
        f"{_fmt(s.avg_difficulty)}/5, workload {_fmt(s.avg_workload)}/5, "
        f"usefulness {_fmt(s.avg_usefulness)}/5."
    )


def professor_fallback(professor: Professor) -> str:
    s = professor.rating_summary
    if not s.has_ratings or s.is_from_rmp:
        return ""
    return (
        f"From {s.count} student rating{'s' if s.count != 1 else ''}: clarity "
        f"{_fmt(s.avg_clarity)}/5, helpfulness {_fmt(s.avg_helpfulness)}/5, "
        f"fairness {_fmt(s.avg_fairness)}/5."
    )
