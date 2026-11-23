"""Validation and calculation helpers for student-submitted ratings."""

from collections.abc import Iterable, Mapping
from typing import TypedDict

from django.db import transaction

from apps.catalog.models import CourseRatingSummary, ProfessorRatingSummary

from .models import CourseRating

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


def _clean_course_rating_semester(semester: str | None) -> str:
    """Apply the CourseRating semester field's rules before any database write."""
    field = CourseRating._meta.get_field("semester")
    value = field.to_python(semester)
    if isinstance(value, str):
        value = value.strip()
    return field.clean(value, None)


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


def submit_course_rating(
    *, user, course, difficulty: int, workload: int, usefulness: int, semester: str
) -> CourseRating:
    """Save one student rating and refresh the course's embedded summary."""
    for score in (difficulty, workload, usefulness):
        validate_rating_score(score)
    semester = _clean_course_rating_semester(semester)

    with transaction.atomic():
        rating = CourseRating.objects.create(
            user=user,
            course=course,
            difficulty=difficulty,
            workload=workload,
            usefulness=usefulness,
            semester=semester,
        )
        summary_data = summarize_course_ratings(
            CourseRating.objects.filter(course=course).values(
                "difficulty", "workload", "usefulness"
            )
        )
        course.rating_summary = CourseRatingSummary(**summary_data)
        course.save(update_fields=["rating_summary"])
    return rating


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
