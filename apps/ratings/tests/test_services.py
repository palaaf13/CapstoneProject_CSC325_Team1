import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.catalog.models import ProfessorRatingSummary
from apps.ratings.models import CourseRating
from apps.ratings.services import (
    calculate_average,
    submit_course_rating,
    summarize_course_ratings,
    summarize_professor_ratings,
    validate_rating_score,
)


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_valid_rating_scores_are_accepted(score):
    assert validate_rating_score(score) is None


@pytest.mark.parametrize(
    "score",
    [0, 6, -1, 2.5, 4.75, 5.1, True, False, "5", None],
)
def test_invalid_rating_scores_are_rejected(score):
    with pytest.raises(ValueError):
        validate_rating_score(score)


def test_calculate_average_returns_mean_rounded_to_two_decimals():
    assert calculate_average([4, 5, 3]) == 4.0
    assert calculate_average([4, 5]) == 4.5
    assert calculate_average([1, 2, 2]) == 1.67


def test_calculate_average_returns_none_for_no_scores():
    assert calculate_average([]) is None


def test_calculate_average_rejects_invalid_scores():
    with pytest.raises(ValueError):
        calculate_average([4, 6])


def test_calculate_average_rejects_decimal_scores():
    with pytest.raises(ValueError):
        calculate_average([4, 2.5])


def test_summarize_course_ratings():
    summary = summarize_course_ratings(
        [
            {"difficulty": 4, "workload": 3, "usefulness": 5},
            {"difficulty": 2, "workload": 5, "usefulness": 3},
        ]
    )

    assert summary == {
        "avg_difficulty": 3.0,
        "avg_workload": 4.0,
        "avg_usefulness": 4.0,
        "count": 2,
    }


def test_summarize_empty_course_ratings():
    summary = summarize_course_ratings([])

    assert summary == {
        "avg_difficulty": None,
        "avg_workload": None,
        "avg_usefulness": None,
        "count": 0,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "score"),
    [
        ("difficulty", 0),
        ("difficulty", 6),
        ("workload", 0),
        ("workload", 6),
        ("usefulness", 0),
        ("usefulness", 6),
    ],
)
def test_submit_course_rating_rejects_invalid_scores_before_insert(make_course, field, score):
    user = get_user_model().objects.create_user(
        username="rating-service-student",
        email="rating-service-student@farmingdale.edu",
        password="test-password-not-for-production",
    )
    course = make_course(code="CSC 246")
    values = {
        "difficulty": 4,
        "workload": 3,
        "usefulness": 5,
        "semester": "Fall 2026",
    }
    values[field] = score

    with pytest.raises(ValueError, match="whole numbers from 1 to 5"):
        submit_course_rating(user=user, course=course, **values)

    assert not CourseRating.objects.filter(user=user, course=course).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "score"),
    [
        ("difficulty", True),
        ("difficulty", False),
        ("workload", True),
        ("workload", False),
        ("usefulness", True),
        ("usefulness", False),
    ],
)
def test_submit_course_rating_rejects_boolean_scores_before_insert(make_course, field, score):
    user = get_user_model().objects.create_user(
        username="rating-service-student",
        email="rating-service-student@farmingdale.edu",
        password="test-password-not-for-production",
    )
    course = make_course(code="CSC 249")
    values = {
        "difficulty": 4,
        "workload": 3,
        "usefulness": 5,
        "semester": "Fall 2026",
    }
    values[field] = score

    with pytest.raises(ValueError, match="whole numbers from 1 to 5"):
        submit_course_rating(user=user, course=course, **values)

    assert not CourseRating.objects.filter(user=user, course=course).exists()


@pytest.mark.parametrize("semester", ["", "   ", "x" * 33, None])
def test_submit_course_rating_rejects_invalid_semester_before_insert(make_course, semester):
    user = get_user_model().objects.create_user(
        username="rating-service-student",
        email="rating-service-student@farmingdale.edu",
        password="test-password-not-for-production",
    )
    course = make_course(code="CSC 247")

    with pytest.raises(ValidationError):
        submit_course_rating(
            user=user,
            course=course,
            difficulty=4,
            workload=3,
            usefulness=5,
            semester=semester,
        )

    assert not CourseRating.objects.filter(user=user, course=course).exists()


@pytest.mark.django_db
def test_submit_course_rating_validates_and_saves_direct_service_call(make_course):
    user = get_user_model().objects.create_user(
        username="rating-service-student",
        email="rating-service-student@farmingdale.edu",
        password="test-password-not-for-production",
    )
    course = make_course(code="CSC 248")

    rating = submit_course_rating(
        user=user,
        course=course,
        difficulty=4,
        workload=3,
        usefulness=5,
        semester="  Fall 2026  ",
    )

    assert rating.semester == "Fall 2026"
    assert CourseRating.objects.filter(user=user, course=course).count() == 1
    course.refresh_from_db()
    assert course.rating_summary.avg_difficulty == 4.0
    assert course.rating_summary.avg_workload == 3.0
    assert course.rating_summary.avg_usefulness == 5.0
    assert course.rating_summary.count == 1


def test_summarize_professor_ratings():
    summary = summarize_professor_ratings(
        [
            {"clarity": 5, "helpfulness": 4, "fairness": 5},
            {"clarity": 3, "helpfulness": 4, "fairness": 3},
        ]
    )

    assert summary["avg_clarity"] == 4.0
    assert summary["avg_helpfulness"] == 4.0
    assert summary["avg_fairness"] == 4.0
    assert summary["avg_overall"] == 4.0
    assert summary["count"] == 2
    assert summary["source"] == "ramhub"
    assert summary["rank_score"] == ProfessorRatingSummary.compute_rank_score(4.0, 2)


def test_summarize_empty_professor_ratings():
    summary = summarize_professor_ratings([])

    assert summary["avg_overall"] is None
    assert summary["count"] == 0
    assert summary["source"] == ""
    assert summary["rank_score"] is None
