"""RH-19 acceptance: a signed-in student rates difficulty, workload, and
usefulness once per course, and the averages update."""

import pytest
from django.urls import reverse

from apps.catalog.models import Course
from apps.ratings import services
from apps.ratings.forms import recent_semesters
from apps.ratings.models import CourseRating

pytestmark = pytest.mark.django_db

SEMESTER = recent_semesters()[0]


def rate_url(course):
    return reverse("ratings:rate_course", kwargs={"code": course.slug})


def post_rating(client, course, **overrides):
    data = {
        "difficulty": 4,
        "workload": 3,
        "usefulness": 5,
        "semester": SEMESTER,
        "comment": "Start the projects early.",
    }
    data.update(overrides)
    return client.post(rate_url(course), data)


def test_signed_out_visitor_is_sent_to_sign_in(client, make_course):
    course = make_course(code="CSC 240")
    response = client.get(rate_url(course))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert not CourseRating.objects.exists()


def test_student_rates_a_course_and_the_averages_update(client, make_course, make_student):
    course = make_course(code="CSC 240")
    client.force_login(make_student())

    response = post_rating(client, course)

    assert response.status_code == 302
    assert response.url == reverse("catalog:course_detail", kwargs={"code": "CSC-240"})
    rating = CourseRating.objects.get()
    assert (rating.difficulty, rating.workload, rating.usefulness) == (4, 3, 5)
    summary = Course.objects.get(pk=course.pk).rating_summary
    assert summary.count == 1
    assert (summary.avg_difficulty, summary.avg_workload, summary.avg_usefulness) == (4, 3, 5)


def test_averages_combine_every_students_rating(client, make_course, make_student):
    course = make_course(code="CSC 240")
    for name, difficulty in (("amy", 2), ("ben", 5)):
        client.force_login(make_student(name))
        post_rating(client, course, difficulty=difficulty)

    summary = Course.objects.get(pk=course.pk).rating_summary
    assert summary.count == 2
    assert summary.avg_difficulty == 3.5


def test_rating_again_edits_instead_of_adding_a_second(client, make_course, make_student):
    course = make_course(code="CSC 240")
    client.force_login(make_student())
    post_rating(client, course, difficulty=5)

    response = client.get(rate_url(course))
    assert b"Edit your rating" in response.content
    post_rating(client, course, difficulty=1, comment="Easier than people say.")

    assert CourseRating.objects.count() == 1
    assert CourseRating.objects.get().difficulty == 1
    summary = Course.objects.get(pk=course.pk).rating_summary
    assert (summary.count, summary.avg_difficulty) == (1, 1)


@pytest.mark.parametrize("bad", ["0", "6", "two", ""])
def test_scores_outside_one_to_five_are_rejected(client, make_course, make_student, bad):
    course = make_course(code="CSC 240")
    client.force_login(make_student())

    response = post_rating(client, course, workload=bad)

    assert response.status_code == 200
    assert b"field-error" in response.content
    assert not CourseRating.objects.exists()
    assert Course.objects.get(pk=course.pk).rating_summary.count == 0


def test_comment_is_optional_and_capped(client, make_course, make_student):
    course = make_course(code="CSC 240")
    client.force_login(make_student())

    assert post_rating(client, course, comment="").status_code == 302
    assert post_rating(client, course, comment="x" * 1001).status_code == 200
    assert CourseRating.objects.get().comment == ""


def test_course_page_shows_advice_and_the_right_button(client, make_course, make_student):
    course = make_course(code="CSC 240")
    page = reverse("catalog:course_detail", kwargs={"code": "CSC-240"})

    assert b"Sign in to rate" in client.get(page).content

    client.force_login(make_student())
    assert b"Rate this course" in client.get(page).content

    post_rating(client, course, comment="Office hours saved my grade.")
    body = client.get(page).content
    assert b"Edit your rating" in body
    assert b"Office hours saved my grade." in body
    assert b"Averaged from 1 student rating" in body


def test_comments_are_escaped(client, make_course, make_student):
    course = make_course(code="CSC 240")
    client.force_login(make_student())
    post_rating(client, course, comment="<script>alert(1)</script>")

    body = client.get(reverse("catalog:course_detail", kwargs={"code": "CSC-240"})).content
    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;" in body


def test_unknown_course_is_404(client, make_student):
    client.force_login(make_student())
    assert client.get("/courses/NOPE-999/rate/").status_code == 404


def test_service_rejects_bad_scores_directly(make_course, make_student):
    with pytest.raises(ValueError):
        services.rate_course(
            user=make_student(),
            course=make_course(),
            difficulty=9,
            workload=3,
            usefulness=3,
            semester=SEMESTER,
        )


def test_recent_semesters_newest_first():
    from datetime import date

    assert recent_semesters(date(2026, 11, 22))[:4] == [
        "Fall 2026",
        "Summer 2026",
        "Spring 2026",
        "Fall 2025",
    ]
    assert recent_semesters(date(2026, 2, 1))[0] == "Spring 2026"
