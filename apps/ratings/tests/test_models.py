"""Database tests for student-submitted ratings."""

import pytest
from bson import ObjectId
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.ratings.models import CourseRating, ProfessorRating

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_user():
    def _make(username="student1", **kwargs):
        User = get_user_model()
        return User.objects.create_user(
            username=username,
            password="test-password-not-for-production",
            **kwargs,
        )

    return _make


def test_course_rating_round_trips(make_user, make_course):
    user = make_user()
    course = make_course(code="CSC 240")

    rating = CourseRating.objects.create(
        user=user,
        course=course,
        difficulty=4,
        workload=3,
        usefulness=5,
        semester="Fall 2026",
    )

    stored = CourseRating.objects.get(pk=rating.pk)

    assert isinstance(stored.pk, ObjectId)
    assert stored.user_id == user.pk
    assert stored.course_id == course.pk
    assert stored.difficulty == 4
    assert stored.workload == 3
    assert stored.usefulness == 5


def test_professor_rating_round_trips(make_user, make_professor):
    user = make_user()
    professor = make_professor()

    rating = ProfessorRating.objects.create(
        user=user,
        professor=professor,
        clarity=5,
        helpfulness=4,
        fairness=3,
        semester="Fall 2026",
    )

    stored = ProfessorRating.objects.get(pk=rating.pk)

    assert isinstance(stored.pk, ObjectId)
    assert stored.professor_id == professor.pk
    assert stored.course_id is None
    assert stored.clarity == 5
    assert stored.helpfulness == 4
    assert stored.fairness == 3


@pytest.mark.parametrize("score", [0, 6, -1])
def test_course_rating_rejects_out_of_range_scores(make_user, make_course, score):
    rating = CourseRating(
        user=make_user(),
        course=make_course(),
        difficulty=score,
        workload=3,
        usefulness=4,
        semester="Fall 2026",
    )

    with pytest.raises(ValidationError):
        rating.full_clean()


@pytest.mark.parametrize("score", [0, 6, -1])
def test_professor_rating_rejects_out_of_range_scores(make_user, make_professor, score):
    rating = ProfessorRating(
        user=make_user(),
        professor=make_professor(),
        clarity=score,
        helpfulness=4,
        fairness=3,
        semester="Fall 2026",
    )

    with pytest.raises(ValidationError):
        rating.full_clean()


def test_student_cannot_rate_same_course_twice(make_user, make_course):
    user = make_user()
    course = make_course()

    CourseRating.objects.create(
        user=user,
        course=course,
        difficulty=4,
        workload=3,
        usefulness=5,
        semester="Fall 2026",
    )

    with pytest.raises(IntegrityError):
        CourseRating.objects.create(
            user=user,
            course=course,
            difficulty=2,
            workload=4,
            usefulness=3,
            semester="Fall 2026",
        )


def test_student_cannot_rate_same_professor_twice(make_user, make_professor):
    user = make_user()
    professor = make_professor()

    ProfessorRating.objects.create(
        user=user,
        professor=professor,
        clarity=5,
        helpfulness=4,
        fairness=3,
        semester="Fall 2026",
    )

    with pytest.raises(IntegrityError):
        ProfessorRating.objects.create(
            user=user,
            professor=professor,
            clarity=3,
            helpfulness=2,
            fairness=4,
            semester="Spring 2027",
        )
