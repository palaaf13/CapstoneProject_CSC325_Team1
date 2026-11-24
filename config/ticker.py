"""
The ticker under the top bar: live RamHub numbers scrolling across the screen
like a stock board.

Items are built once and cached for a few minutes, and only when a template
actually draws the ticker (the context processor hands over a lazy value), so
htmx partials and pages without a ticker never pay for the queries.
"""

from dataclasses import dataclass

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

CACHE_KEY = "ramhub:ticker:v1"
CACHE_SECONDS = 300
PER_SECTION = 6


@dataclass(frozen=True)
class TickerItem:
    symbol: str  # bold, like a stock symbol: "CSC 325", "ABBAS", "EVENT"
    value: str = ""  # the number or detail after it
    trend: str = ""  # "up", "down", "flat", or "" for no arrow
    url: str = ""


def _trend(score: float | None) -> str:
    if score is None:
        return ""
    if score >= 4:
        return "up"
    if score < 3:
        return "down"
    return "flat"


def build_items() -> list[TickerItem]:
    """What the ticker shows right now. Sections with nothing to show are left out."""
    from apps.campus.models import Club
    from apps.campus.services import upcoming_events
    from apps.catalog.models import Course, Professor
    from apps.community.models import Post

    items: list[TickerItem] = []

    professors = (
        Professor.objects.filter(rating_summary__count__gt=0)
        .exclude(rating_summary__rank_score=None)
        .order_by("-rating_summary__rank_score")[:PER_SECTION]
    )
    for p in professors:
        score = p.rating_summary.avg_overall
        items.append(
            TickerItem(
                symbol=p.last_name.upper(),
                value=f"{score:.1f}" if score is not None else "",
                trend=_trend(score),
                url=reverse("catalog:professor_detail", kwargs={"slug": p.slug}),
            )
        )

    courses = Course.objects.filter(rating_summary__count__gt=0).order_by(
        "-rating_summary__count", "code"
    )[:PER_SECTION]
    for c in courses:
        score = c.rating_summary.avg_usefulness
        items.append(
            TickerItem(
                symbol=c.code,
                value=f"useful {score:.1f}" if score is not None else "",
                trend=_trend(score),
                url=reverse("catalog:course_detail", kwargs={"code": c.slug}),
            )
        )

    for event in upcoming_events(limit=4):
        when = timezone.localtime(event.starts_at).strftime("%a %b %-d")
        items.append(
            TickerItem(
                symbol="EVENT",
                value=f"{event.title} · {event.club.name} · {when}",
                url=reverse("campus:club_detail", kwargs={"slug": event.club.slug}),
            )
        )

    for post in Post.objects.filter(is_removed=False).order_by("-created_at")[:3]:
        items.append(
            TickerItem(
                symbol="NEW",
                value=post.title[:60],
                url=reverse("community:post_detail", args=[post.pk]),
            )
        )

    totals = [
        ("COURSES", Course.objects.count(), "catalog:courses"),
        ("PROFESSORS", Professor.objects.count(), "catalog:professors"),
        ("CLUBS", Club.objects.count(), "campus:clubs"),
    ]
    items += [TickerItem(label, f"{n:,}", url=reverse(name)) for label, n, name in totals if n]
    return items


def ticker_items() -> list[TickerItem]:
    items = cache.get(CACHE_KEY)
    if items is None:
        items = build_items()
        cache.set(CACHE_KEY, items, CACHE_SECONDS)
    return items


def ticker(request) -> dict:
    """Context processor: the ticker's items, built only if a template uses them."""
    return {"ticker_items": SimpleLazyObject(ticker_items)}
