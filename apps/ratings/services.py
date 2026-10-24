"""Validation and calculation helpers for student-submitted ratings."""

from collections.abc import Iterable, Mapping
from typing import TypedDict

from apps.catalog.models import ProfessorRatingSummary

RATING_MIN = 1
RATING_MAX = 5


class CourseRatingSummaryData(TypedDict):
    """Calculated summary data for course ratings."""

    avg_difficulty: float | None
    avg_workload: float | None
    avg_usefulness: float | None
    count: int


class ProfessorRatingSummaryData(TypedDict):
    """Calculated summary data for professor ratings."""

    avg_clarity: float | None
    avg_helpfulness: float | None
    avg_fairness: float | None
    avg_overall: float | None
    count: int
    source: str
    rank_score: float | None


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


def summarize_course_ratings(
    ratings: Iterable[Mapping[str, int]],
) -> CourseRatingSummaryData:
    """Calculate summary fields from individual course-rating records."""
    values = list(ratings)

    for rating in values:
        for field in ("difficulty", "workload", "usefulness"):
            validate_rating_score(rating[field])

    return {
        "avg_difficulty": calculate_average(rating["difficulty"] for rating in values),
        "avg_workload": calculate_average(rating["workload"] for rating in values),
        "avg_usefulness": calculate_average(rating["usefulness"] for rating in values),
        "count": len(values),
    }


def summarize_professor_ratings(
    ratings: Iterable[Mapping[str, int]],
    *,
    source: str = "ramhub",
) -> ProfessorRatingSummaryData:
    """Calculate summary fields from individual professor-rating records."""
    values = list(ratings)

    for rating in values:
        for field in ("clarity", "helpfulness", "fairness"):
            validate_rating_score(rating[field])

    clarity = calculate_average(rating["clarity"] for rating in values)
    helpfulness = calculate_average(rating["helpfulness"] for rating in values)
    fairness = calculate_average(rating["fairness"] for rating in values)

    overall = ProfessorRatingSummary.compute_overall(
        clarity,
        helpfulness,
        fairness,
    )

    return {
        "avg_clarity": clarity,
        "avg_helpfulness": helpfulness,
        "avg_fairness": fairness,
        "avg_overall": overall,
        "count": len(values),
        "source": source if values else "",
        "rank_score": ProfessorRatingSummary.compute_rank_score(overall, len(values)),
    }
