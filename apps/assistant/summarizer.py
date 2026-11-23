"""
The AI review summary: student reviews in, a short "What students say" out.

This module has no Django imports on purpose. The site calls it through
``apps.assistant.services`` (which adds settings, caching and the API client),
and the evaluation suite in ``evals/`` calls it directly, so both exercise the
exact same prompt, request and validation.

``summarize_reviews`` never raises. Every way the AI call can go wrong (no key,
timeout, network error, rate limit, API error, refusal, truncated or invalid
output) comes back as a ``SummaryResult`` with ``summary=None`` and a
``fallback_reason``, and the page shows its non-AI fallback instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

PROMPT_VERSION = "review_summary_v1"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.txt"
DEFAULT_MODEL = "claude-haiku-5-5"

# Fewer reviews than this and there is nothing to summarize; the page just lists them.
MIN_REVIEWS = 3
# The newest reviews are sent. Keeps the request small and the cost predictable.
MAX_REVIEWS = 40
MAX_REVIEW_CHARS = 1000

MAX_OUTPUT_TOKENS = 2000
TONES = ("positive", "mixed", "negative")
MAX_POINTS = 3
MAX_OVERVIEW_CHARS = 600
MAX_POINT_CHARS = 200

_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "reviews": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["text", "reviews"],
    "additionalProperties": False,
}

# Structured outputs: the API guarantees JSON of this shape. Limits the schema
# cannot express (lengths, counts, citation ranges) are checked in parse_summary.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "tone": {"type": "string", "enum": list(TONES)},
        "pros": {"type": "array", "items": _POINT_SCHEMA},
        "cons": {"type": "array", "items": _POINT_SCHEMA},
    },
    "required": ["overview", "tone", "pros", "cons"],
    "additionalProperties": False,
}


class InvalidSummary(ValueError):
    """The model answered, but not with something we are willing to show."""


@dataclass(frozen=True)
class Point:
    text: str
    reviews: tuple[int, ...]


@dataclass(frozen=True)
class ReviewSummary:
    overview: str
    tone: str
    pros: tuple[Point, ...]
    cons: tuple[Point, ...]
    review_count: int
    model: str = ""
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ReviewSummary:
        return cls(
            overview=data["overview"],
            tone=data["tone"],
            pros=tuple(Point(p["text"], tuple(p["reviews"])) for p in data["pros"]),
            cons=tuple(Point(p["text"], tuple(p["reviews"])) for p in data["cons"]),
            review_count=data["review_count"],
            model=data.get("model", ""),
            prompt_version=data.get("prompt_version", PROMPT_VERSION),
        )


@dataclass(frozen=True)
class SummaryResult:
    summary: ReviewSummary | None = None
    fallback_reason: str | None = None
    # What the API reported back, for the eval report. Empty when no call was made.
    usage: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.summary is not None


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_user_message(subject: str, reviews: list[str]) -> str:
    """The subject and the numbered reviews, delimited so the prompt can call them data."""
    lines = [f"Subject: {subject}", f"Number of reviews: {len(reviews)}", "", "<reviews>"]
    for number, review in enumerate(reviews, start=1):
        text = " ".join(review.split())[:MAX_REVIEW_CHARS]
        lines.append(f'<review number="{number}">{text}</review>')
    lines.append("</reviews>")
    return "\n".join(lines)


def _clean_point(raw: dict, review_count: int, where: str) -> Point:
    text = raw.get("text", "").strip()
    if not text:
        raise InvalidSummary(f"{where}: empty point")
    if len(text) > MAX_POINT_CHARS:
        raise InvalidSummary(f"{where}: point is {len(text)} characters")
    cited = raw.get("reviews") or []
    if not cited:
        raise InvalidSummary(f"{where}: point cites no reviews")
    for number in cited:
        if isinstance(number, bool) or not isinstance(number, int):
            raise InvalidSummary(f"{where}: citation {number!r} is not a review number")
        if not 1 <= number <= review_count:
            # Citing review 7 of 5 means the model made the point up.
            raise InvalidSummary(f"{where}: cites review {number} of {review_count}")
    return Point(text=text, reviews=tuple(sorted(set(cited))))


def parse_summary(text: str, review_count: int, *, model: str = "") -> ReviewSummary:
    """Validate the model's JSON. Raises InvalidSummary for anything unshowable."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InvalidSummary(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidSummary("not a JSON object")

    overview = data.get("overview")
    if not isinstance(overview, str) or not overview.strip():
        raise InvalidSummary("missing overview")
    if len(overview) > MAX_OVERVIEW_CHARS:
        raise InvalidSummary(f"overview is {len(overview)} characters")
    tone = data.get("tone")
    if tone not in TONES:
        raise InvalidSummary(f"unknown tone {tone!r}")

    points = {}
    for side in ("pros", "cons"):
        raw = data.get(side)
        if not isinstance(raw, list):
            raise InvalidSummary(f"{side} is not a list")
        if len(raw) > MAX_POINTS:
            raise InvalidSummary(f"{len(raw)} {side}, at most {MAX_POINTS}")
        if not all(isinstance(item, dict) for item in raw):
            raise InvalidSummary(f"{side} has a non-object item")
        points[side] = tuple(
            _clean_point(item, review_count, f"{side}[{i}]") for i, item in enumerate(raw)
        )
    if not points["pros"] and not points["cons"]:
        raise InvalidSummary("no pros and no cons")

    return ReviewSummary(
        overview=overview.strip(),
        tone=tone,
        pros=points["pros"],
        cons=points["cons"],
        review_count=review_count,
        model=model,
    )


def _fallback(reason: str, detail: object = "") -> SummaryResult:
    logger.warning("AI review summary fell back (%s) %s", reason, detail)
    return SummaryResult(fallback_reason=reason)


def summarize_reviews(
    subject: str,
    reviews: list[str],
    *,
    client: anthropic.Anthropic | None,
    model: str = DEFAULT_MODEL,
    timeout: float | None = None,
) -> SummaryResult:
    """Summarize the reviews, or explain why not. Never raises."""
    reviews = [r.strip() for r in reviews if r and r.strip()][:MAX_REVIEWS]
    if len(reviews) < MIN_REVIEWS:
        return SummaryResult(fallback_reason="not_enough_reviews")
    if client is None:
        return SummaryResult(fallback_reason="ai_disabled")

    options = {"timeout": timeout} if timeout is not None else {}
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=load_prompt(),
            messages=[{"role": "user", "content": build_user_message(subject, reviews)}],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            **options,
        )
    except anthropic.APITimeoutError as exc:
        return _fallback("timeout", exc)
    except anthropic.APIConnectionError as exc:
        return _fallback("connection_error", exc)
    except anthropic.RateLimitError as exc:
        return _fallback("rate_limited", exc)
    except anthropic.APIStatusError as exc:
        return _fallback(f"api_error_{exc.status_code}", exc)
    except Exception as exc:  # The page must never break because of the AI.
        logger.exception("Unexpected error calling the AI review summary")
        return SummaryResult(fallback_reason=f"unexpected_error:{type(exc).__name__}")

    usage = {}
    if getattr(response, "usage", None) is not None:
        usage = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }
    served_by = getattr(response, "model", "") or model

    if response.stop_reason == "refusal":
        return SummaryResult(fallback_reason="refused", usage=usage)
    if response.stop_reason == "max_tokens":
        return SummaryResult(fallback_reason="truncated", usage=usage)

    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
    if text is None:
        return SummaryResult(fallback_reason="invalid_output", usage=usage)
    try:
        summary = parse_summary(text, len(reviews), model=served_by)
    except InvalidSummary as exc:
        logger.warning("AI review summary was invalid: %s", exc)
        return SummaryResult(fallback_reason="invalid_output", usage=usage)
    return SummaryResult(summary=summary, usage=usage)
