"""
Scoring for the review-summary eval. Pure functions, no API calls, so the unit
tests can check the grader itself (tests/test_evals.py).

Every check is deterministic: it looks at the summary the model returned and
the reviews it was given, never at another model's opinion. That keeps a run
cheap, repeatable, and easy to argue with.
"""

from __future__ import annotations

import re

from apps.assistant.summarizer import ReviewSummary

# Words too common to show that a point came from a particular review.
STOPWORDS = {
    "about", "also", "always", "been", "being", "class", "classes", "course", "does",
    "every", "from", "have", "into", "just", "like", "makes", "many", "more", "most",
    "much", "only", "other", "really", "review", "reviews", "said", "says", "some",
    "student", "students", "than", "that", "their", "them", "there", "they", "this",
    "very", "were", "what", "when", "which", "while", "will", "with", "would", "your",
    "professor", "overall", "often", "find", "found", "feel", "felt", "describe",
    "described", "mention", "mentioned", "note", "noted", "report", "reported",
}  # fmt: skip


def summary_text(summary: ReviewSummary) -> str:
    parts = [summary.overview, *(p.text for p in summary.pros), *(p.text for p in summary.cons)]
    return " ".join(parts)


def _contains(text: str, term: str) -> bool:
    """Case-insensitive match. A term that starts or ends with a letter must
    match at a word boundary there, so "he" does not match "the" and "grad"
    still matches "grading"."""
    pattern = re.escape(term.lower())
    if term[:1].isalnum():
        pattern = r"\b" + pattern
    if len(term) <= 3 and term[-1:].isalnum():
        pattern += r"\b"
    return re.search(pattern, text.lower()) is not None


def covered_themes(summary: ReviewSummary, themes: list[list[str]]) -> list[bool]:
    """For each expected theme (a list of interchangeable words), whether the summary mentions it."""
    text = summary_text(summary)
    return [any(_contains(text, word) for word in group) for group in themes]


_SUFFIXES = ("ing", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    """Crude: drop one common suffix, keep at most four letters ("taking" -> "tak")."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word[:4]


def _stems(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {_stem(w) for w in words if len(w) >= 4 and w not in STOPWORDS}


def ungrounded_points(summary: ReviewSummary, reviews: list[str]) -> list[str]:
    """Pros and cons that share no content word with any review they cite.

    Rough on purpose (first four letters of each word), so paraphrase like
    "heavy workload" for "tons of homework" still counts as grounded. What it
    catches is a point attached to reviews that say nothing like it.
    """
    bad = []
    for point in (*summary.pros, *summary.cons):
        cited = " ".join(reviews[n - 1] for n in point.reviews if 1 <= n <= len(reviews)).lower()
        if not any(stem in cited for stem in _stems(point.text)):
            bad.append(point.text)
    return bad


def unsupported_numbers(summary: ReviewSummary, reviews: list[str], subject: str = "") -> list[str]:
    """Numbers in the summary that appear in no review (or in the subject, e.g.
    the 240 in "CSC 240"): invented specifics."""
    source = " ".join([subject, *reviews])
    return [n for n in re.findall(r"\d+(?:\.\d+)?", summary_text(summary)) if n not in source]


def hallucination_problems(
    summary: ReviewSummary, reviews: list[str], forbidden: list[str], subject: str = ""
) -> list[str]:
    """Everything in the summary the reviews do not support. Empty means clean.

    Three signals: a forbidden term (a plausible detail no review mentions, or
    something the prompt forbids, like a professor's accent), a number no
    review contains, or a point not grounded in the reviews it cites. Citations
    to reviews that do not exist are already rejected by the app's validator
    and show up as an invalid output instead.
    """
    text = summary_text(summary)
    problems = [f"mentions {term!r}" for term in forbidden if _contains(text, term)]
    problems += [
        f"number {n} is in no review" for n in unsupported_numbers(summary, reviews, subject)
    ]
    problems += [f"ungrounded point: {p!r}" for p in ungrounded_points(summary, reviews)]
    return problems


def same_judgement(a: ReviewSummary, b: ReviewSummary, themes: list[list[str]]) -> tuple[bool, str]:
    """Two summaries reach the same verdict: same tone and the same themes covered."""
    if a.tone != b.tone:
        return False, f"tone {a.tone} vs {b.tone}"
    cov_a, cov_b = covered_themes(a, themes), covered_themes(b, themes)
    if cov_a != cov_b:
        return False, f"themes {cov_a} vs {cov_b}"
    return True, ""
