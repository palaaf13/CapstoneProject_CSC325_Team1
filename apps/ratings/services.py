"""Validation and calculation helpers for student-submitted ratings."""

from collections.abc import Iterable, Mapping
from typing import TypedDict

from apps.catalog.models import Course, CourseRatingSummary, Professor, ProfessorRatingSummary

from .models import CourseRating, ProfessorRating

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


# -- writing ratings ---------------------------------------------------------
def rate_course(
    *,
    user,
    course: Course,
    difficulty: int,
    workload: int,
    usefulness: int,
    semester: str,
    comment: str = "",
) -> CourseRating:
    """Save the student's one rating of this course (a second call edits it), then
    refresh the course's stored averages so list pages and sorts see it."""
    for score in (difficulty, workload, usefulness):
        validate_rating_score(score)
    rating, _ = CourseRating.objects.update_or_create(
        user=user,
        course=course,
        defaults={
            "difficulty": difficulty,
            "workload": workload,
            "usefulness": usefulness,
            "semester": semester,
            "comment": comment.strip(),
        },
    )
    refresh_course_summary(course)
    return rating


def refresh_course_summary(course: Course) -> None:
    """Recompute course.rating_summary from every rating of it a moderator hasn't removed."""
    rows = (
        CourseRating.objects.filter(course=course)
        .exclude(is_removed=True)
        .values("difficulty", "workload", "usefulness")
    )
    course.rating_summary = CourseRatingSummary(**summarize_course_ratings(rows))
    course.save(update_fields=["rating_summary"])


def course_rating_by(user, course: Course) -> CourseRating | None:
    if not user.is_authenticated:
        return None
    return CourseRating.objects.filter(user=user, course=course).first()


def course_comments(course: Course, *, limit: int | None = None) -> list[CourseRating]:
    """Ratings of this course that came with written advice, newest first."""
    found = (
        CourseRating.objects.filter(course=course)
        .exclude(comment="")
        .exclude(is_removed=True)
        .order_by("-updated_at")
    )
    return list(found[:limit] if limit else found)


def rate_professor(
    *,
    user,
    professor: Professor,
    clarity: int,
    helpfulness: int,
    fairness: int,
    semester: str,
    course: Course | None = None,
    comment: str = "",
) -> ProfessorRating:
    """Save the student's one rating of this professor (a second call edits it),
    then refresh the professor's stored averages and rank score."""
    for score in (clarity, helpfulness, fairness):
        validate_rating_score(score)
    rating, _ = ProfessorRating.objects.update_or_create(
        user=user,
        professor=professor,
        defaults={
            "clarity": clarity,
            "helpfulness": helpfulness,
            "fairness": fairness,
            "semester": semester,
            "course": course,
            "comment": comment.strip(),
        },
    )
    refresh_professor_summary(professor)
    return rating


def refresh_professor_summary(professor: Professor) -> None:
    """Recompute professor.rating_summary from RamHub ratings.

    Once a student has rated a professor here, the summary is RamHub's own and
    import_rmp leaves it alone. The RateMyProfessors figures stay in the rmp_*
    fields and keep their separately labelled panel.
    """
    rows = (
        ProfessorRating.objects.filter(professor=professor)
        .exclude(is_removed=True)
        .values("clarity", "helpfulness", "fairness")
    )
    professor.rating_summary = ProfessorRatingSummary(
        **summarize_professor_ratings(rows, source=ProfessorRatingSummary.SOURCE_RAMHUB)
    )
    professor.save(update_fields=["rating_summary"])


def professor_rating_by(user, professor: Professor) -> ProfessorRating | None:
    if not user.is_authenticated:
        return None
    return ProfessorRating.objects.filter(user=user, professor=professor).first()


def professor_comments(professor: Professor, *, limit: int | None = None) -> list[ProfessorRating]:
    """Ratings of this professor that came with written advice, newest first."""
    found = (
        ProfessorRating.objects.filter(professor=professor)
        .exclude(comment="")
        .exclude(is_removed=True)
        .order_by("-updated_at")
    )
    return list(found[:limit] if limit else found)
