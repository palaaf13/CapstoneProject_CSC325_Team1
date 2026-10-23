"""Validation and calculation helpers for student-submitted ratings."""

from collections.abc import Iterable

RATING_MIN = 1
RATING_MAX = 5


def validate_rating_score(score: int) -> None:
    """Raise ValueError unless score is a whole number from 1 through 5."""
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("Rating scores must be whole numbers from 1 to 5.")

    if not RATING_MIN <= score <= RATING_MAX:
        raise ValueError("Rating scores must be whole numbers from 1 to 5.")


def calculate_average(scores: Iterable[int]) -> float | None:
    """Return the mean of validated scores, rounded to two decimals."""
    values = list(scores)

    if not values:
        return None

    for score in values:
        validate_rating_score(score)

    return round(sum(values) / len(values), 2)
