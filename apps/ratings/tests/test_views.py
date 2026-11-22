"""Course rating submission views."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.ratings.models import CourseRating

pytestmark = pytest.mark.django_db


@pytest.fixture
def student(db):
    return get_user_model().objects.create_user(
        username="rating-student",
        email="rating-student@farmingdale.edu",
        password="test-password-not-for-production",
    )


def course_rating_url(course):
    return reverse("ratings:course_rating_create", args=[course.slug])


def test_course_rating_submission_updates_summary(client, student, make_course):
    course = make_course(code="CSC 240")
    client.force_login(student)

    response = client.post(
        course_rating_url(course),
        {
            "difficulty": "4",
            "workload": "3",
            "usefulness": "5",
            "semester": "Fall 2026",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("catalog:course_detail", args=[course.slug])
    rating = CourseRating.objects.get(course=course)
    assert rating.user_id == student.pk
    assert rating.difficulty == 4
    assert rating.workload == 3
    assert rating.usefulness == 5
    assert rating.semester == "Fall 2026"
    course.refresh_from_db()
    assert course.rating_summary.avg_difficulty == 4.0
    assert course.rating_summary.avg_workload == 3.0
    assert course.rating_summary.avg_usefulness == 5.0
    assert course.rating_summary.count == 1


def test_student_can_rate_course_absent_from_courses_taken(client, student, make_course):
    course = make_course(code="CSC 241")
    client.force_login(student)

    response = client.post(
        course_rating_url(course),
        {"difficulty": 2, "workload": 3, "usefulness": 4, "semester": "Spring 2026"},
    )

    assert response.status_code == 302
    assert CourseRating.objects.filter(user=student, course=course).exists()
    assert student.courses_taken == []


def test_course_rating_submission_requires_login(client, make_course):
    course = make_course(code="CSC 242")

    response = client.post(
        course_rating_url(course),
        {"difficulty": 2, "workload": 3, "usefulness": 4, "semester": "Spring 2026"},
    )

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))
    assert "next=" in response["Location"]
    assert CourseRating.objects.count() == 0


def test_invalid_course_rating_renders_form_errors(client, student, make_course):
    course = make_course(code="CSC 243")
    client.force_login(student)

    response = client.post(
        course_rating_url(course),
        {"difficulty": 6, "workload": 3, "usefulness": 4, "semester": "Spring 2026"},
    )

    assert response.status_code == 400
    assert response.context["rating_form"].errors
    assert CourseRating.objects.count() == 0


def test_student_cannot_submit_second_course_rating(client, student, make_course):
    course = make_course(code="CSC 244")
    client.force_login(student)
    payload = {"difficulty": 4, "workload": 3, "usefulness": 5, "semester": "Fall 2026"}

    first = client.post(course_rating_url(course), payload)
    second = client.post(course_rating_url(course), payload)

    assert first.status_code == 302
    assert second.status_code == 302
    assert CourseRating.objects.filter(user=student, course=course).count() == 1


def test_course_detail_shows_rating_form_only_to_eligible_signed_in_user(
    client, student, make_course
):
    course = make_course(code="CSC 245")

    signed_out = client.get(reverse("catalog:course_detail", args=[course.slug]))
    assert b"Sign in" in signed_out.content
    assert b'name="difficulty"' not in signed_out.content

    client.force_login(student)
    signed_in = client.get(reverse("catalog:course_detail", args=[course.slug]))
    assert b'name="difficulty"' in signed_in.content
