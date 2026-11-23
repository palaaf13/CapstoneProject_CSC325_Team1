"""Threads about a course: starting one, listing them on the page, the feed filter."""

import pytest
from django.urls import reverse

from apps.catalog.models import Course, Professor
from apps.community import services
from apps.community.forms import FeedQueryForm
from apps.community.models import Post

pytestmark = pytest.mark.django_db


@pytest.fixture
def course():
    return Course.objects.create(code="CSC 240", title="Data Structures", department="Computing")


def page_url(course: Course) -> str:
    return reverse("catalog:course_detail", args=[course.slug])


def new_thread_url(course: Course) -> str:
    return reverse("community:course_post_create", args=[course.slug])


# -- services --------------------------------------------------------------
def test_threads_about_a_course_lists_only_its_visible_threads(make_post, course):
    other = Course.objects.create(code="CSC 101", title="Intro", department="Computing")
    mine = make_post("Is the final cumulative?", course=course)
    make_post("General feed post")
    make_post("About another course", course=other)
    make_post("Deleted, no replies", course=course, is_removed=True)

    threads, count = services.threads_about(course=course)

    assert threads == [mine]
    assert count == 1


def test_threads_about_needs_exactly_one_subject(course):
    with pytest.raises(ValueError):
        services.threads_about()
    professor = Professor.objects.create(slug="ada-l", first_name="Ada", last_name="L")
    with pytest.raises(ValueError):
        services.threads_about(professor=professor, course=course)


def test_a_post_cannot_be_about_a_professor_and_a_course(make_user, course):
    professor = Professor.objects.create(slug="ada-l", first_name="Ada", last_name="L")
    with pytest.raises(ValueError):
        services.create_post(
            author=make_user(),
            kind="question",
            title="Both?",
            body="",
            tags=[],
            professor=professor,
            course=course,
        )
    assert Post.objects.count() == 0


def test_feed_query_narrows_to_one_course(make_post, course):
    thread = make_post("Study group?", course=course)
    make_post("Unrelated")
    query = FeedQueryForm({"course": "csc-240"}).to_query()

    assert list(services.feed_posts(query, course=services.get_course(query.course))) == [thread]


# -- views -----------------------------------------------------------------
def test_course_page_shows_empty_state_with_a_way_to_start(client, course):
    body = client.get(page_url(course)).content
    assert b"No threads about CSC 240 yet" in body
    assert new_thread_url(course).encode() in body


def test_course_page_lists_its_threads(client, make_post, course):
    make_post("<i>Which section is best?</i>", course=course)
    body = client.get(page_url(course)).content
    assert b"&lt;i&gt;Which section is best?" in body


def test_starting_a_course_thread_requires_sign_in(client, course):
    response = client.post(new_thread_url(course), {"kind": "question", "title": "Hi"})
    assert response.status_code == 302
    assert Post.objects.count() == 0


def test_signed_in_student_starts_a_thread_linked_to_the_course(client, make_user, course):
    client.force_login(make_user("asker"))
    assert b"Start a thread about CSC 240" in client.get(new_thread_url(course)).content

    response = client.post(
        new_thread_url(course),
        {"kind": "question", "title": "How heavy are the labs?", "body": "", "tags": ""},
    )

    post = Post.objects.get()
    assert post.course_id == course.pk and post.professor_id is None
    assert response["Location"] == reverse("community:post_detail", args=[post.pk])
    detail = client.get(response["Location"]).content
    assert page_url(course).encode() in detail


def test_unknown_course_cannot_get_a_thread(client, make_user):
    client.force_login(make_user("asker"))
    response = client.post(
        reverse("community:course_post_create", args=["NOPE-999"]),
        {"kind": "question", "title": "Hello"},
    )
    assert response.status_code == 404
    assert Post.objects.count() == 0


def test_feed_filtered_to_a_course_names_it(client, make_post, course):
    make_post("Exam tips", course=course)
    body = client.get(reverse("community:feed"), {"course": course.slug}).content
    assert b"Threads about" in body and b"CSC 240" in body
