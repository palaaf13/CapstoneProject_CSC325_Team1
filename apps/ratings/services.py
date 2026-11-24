"""Validation and calculation helpers for student-submitted ratings."""

from collections.abc import Iterable, Mapping
from typing import TypedDict

from django.db import IntegrityError, connections, transaction
from pymongo.errors import BulkWriteError, DuplicateKeyError, PyMongoError

from apps.catalog.models import Course, CourseRatingSummary, ProfessorRatingSummary

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


class CourseRatingAlreadyExists(IntegrityError):
    """Raised when the database uniqueness constraint rejects a duplicate rating."""


def _exception_chain(error):
    """Yield an exception and its explicit or implicit causes without looping."""
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _labeled_pymongo_error(error, label: str) -> PyMongoError | None:
    for cause in _exception_chain(error):
        if isinstance(cause, PyMongoError) and cause.has_error_label(label):
            return cause
    return None


_COURSE_RATING_UNIQUE_INDEX = "ratings_course_user_unique"
_COURSE_RATING_UNIQUE_KEY_PATTERN = {"user_id": 1, "course_id": 1}


def _details_match_course_rating_index(details) -> bool:
    if not isinstance(details, Mapping):
        return False
    index_name = details.get("indexName")
    key_pattern = details.get("keyPattern")
    if index_name is not None and index_name != _COURSE_RATING_UNIQUE_INDEX:
        return False
    if key_pattern is not None and key_pattern != _COURSE_RATING_UNIQUE_KEY_PATTERN:
        return False
    if index_name == _COURSE_RATING_UNIQUE_INDEX:
        return True
    if key_pattern == _COURSE_RATING_UNIQUE_KEY_PATTERN:
        return True
    if (
        index_name is None
        and key_pattern is None
        and _COURSE_RATING_UNIQUE_INDEX in str(details.get("errmsg", ""))
    ):
        return True
    return _details_match_course_rating_index(details.get("errInfo"))


def _is_duplicate_key_error(error) -> bool:
    """Match only duplicate-key errors for this service's user/course index."""
    for cause in _exception_chain(error):
        if isinstance(cause, DuplicateKeyError):
            if _details_match_course_rating_index(cause.details):
                return True
        elif isinstance(cause, BulkWriteError):
            details = cause.details or {}
            for item in details.get("writeErrors", ()):
                if item.get("code") == 11000 and _details_match_course_rating_index(item):
                    return True
        elif getattr(cause, "code", None) == 11000 and _details_match_course_rating_index(
            getattr(cause, "details", None)
        ):
            return True
    return False


def submit_course_rating_transactional(
    *,
    user,
    course,
    difficulty: int,
    workload: int,
    usefulness: int,
    semester: str,
    using: str = "default",
) -> CourseRating:
    """Transaction-based variant, kept separate until the ratings index is verified.

    Requires the MongoDB unique index on (user_id, course_id) before production
    use. PyMongo owns retries through ClientSession.with_transaction(); if it
    gives up with an uncertain commit result, this function does not resubmit.
    """
    for score in (difficulty, workload, usefulness):
        validate_rating_score(score)
    semester = _clean_course_rating_semester(semester)

    connection = connections[using]
    connection.ensure_connection()
    if (
        connection.session is not None
        or connection.in_atomic_block_mongo
        or connection.in_atomic_block
    ):
        raise RuntimeError("Course rating transaction cannot be nested.")

    client = connection.connection
    user_id = user.pk
    course_id = course.pk

    def callback(session):
        # The backend ORM reads connection.session for every Mongo operation.
        # Restore it even when a callback attempt fails and PyMongo retries.
        previous_session = connection.session
        connection.session = session
        try:
            try:
                fresh_course = Course.objects.using(using).get(pk=course_id)
                try:
                    rating = CourseRating.objects.using(using).create(
                        user_id=user_id,
                        course_id=course_id,
                        difficulty=difficulty,
                        workload=workload,
                        usefulness=usefulness,
                        semester=semester,
                    )
                except Exception as error:
                    if _is_duplicate_key_error(error):
                        raise CourseRatingAlreadyExists(
                            "This student has already rated this course."
                        ) from error
                    raise
                summary_data = summarize_course_ratings(
                    CourseRating.objects.using(using)
                    .filter(course_id=course_id)
                    .values("difficulty", "workload", "usefulness")
                )
                fresh_course.rating_summary = CourseRatingSummary(**summary_data)
                fresh_course.save(using=using, update_fields=["rating_summary"])
                return rating
            except Exception as error:
                # The backend wraps query-time PyMongo errors in Django errors.
                # Unwrap transient labels so PyMongo's callback API can retry.
                transient = _labeled_pymongo_error(error, "TransientTransactionError")
                if transient is not None:
                    raise transient from None
                raise
        finally:
            connection.session = previous_session

    # Django pre_save/post_save receivers run for these ORM operations. Keep this
    # callback free of app-level external effects because PyMongo may rerun it.
    # In particular, an unresolved UnknownTransactionCommitResult escapes
    # unchanged. Never start a fresh submission after an uncertain commit.
    with client.start_session() as session:
        return session.with_transaction(callback)


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
