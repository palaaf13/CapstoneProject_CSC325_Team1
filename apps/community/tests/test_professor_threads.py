"""Threads about a professor: starting one, listing them on the page, the feed filter."""

import pytest
from django.urls import reverse

from apps.catalog.models import Professor
from apps.community import services
from apps.community.forms import FeedQueryForm
from apps.community.models import Post

pytestmark = pytest.mark.django_db


@pytest.fixture
def professor():
    return Professor.objects.create(
        slug="marisol-reyes", first_name="Marisol", last_name="Reyes", department="Computer Systems"
    )


def page_url(professor: Professor) -> str:
    return reverse("catalog:professor_detail", args=[professor.slug])


def new_thread_url(professor: Professor) -> str:
    return reverse("community:professor_post_create", args=[professor.slug])


# -- services --------------------------------------------------------------
def test_professor_threads_lists_only_that_professors_visible_threads(make_post, professor):
    other = Professor.objects.create(slug="someone-else", first_name="S", last_name="E")
    mine = make_post("Exams?", professor=professor)
    make_post("General feed post")
    make_post("About someone else", professor=other)
    make_post("Deleted, no replies", professor=professor, is_removed=True)

    threads, count = services.threads_about(professor=professor)

    assert threads == [mine]
    assert count == 1


def test_professor_threads_caps_the_list_but_counts_them_all(make_post, professor):
    for i in range(services.THREADS_SHOWN + 2):
        make_post(f"Thread {i}", professor=professor)

    threads, count = services.threads_about(professor=professor)

    assert len(threads) == services.THREADS_SHOWN
    assert count == services.THREADS_SHOWN + 2


def test_feed_query_narrows_to_one_professor(make_post, professor):
    thread = make_post("Office hours?", professor=professor)
    make_post("Unrelated")
    query = FeedQueryForm({"professor": professor.slug}).to_query()

    assert list(services.feed_posts(query, professor=services.get_professor(query.professor))) == [thread]


# -- views -----------------------------------------------------------------
def test_professor_page_shows_empty_state_with_a_way_to_start(client, professor):
    body = client.get(page_url(professor)).content
    assert b"No threads about Marisol Reyes yet" in body
    assert new_thread_url(professor).encode() in body


def test_professor_page_lists_its_threads(client, make_post, professor):
    make_post("<b>How hard are the labs?</b>", professor=professor)
    body = client.get(page_url(professor)).content
    assert b"&lt;b&gt;How hard are the labs?" in body


def test_starting_a_thread_requires_sign_in(client, professor):
    response = client.post(new_thread_url(professor), {"kind": "question", "title": "Hi"})
    assert response.status_code == 302
    assert Post.objects.count() == 0


def test_signed_in_student_starts_a_thread_linked_to_the_professor(client, make_user, professor):
    client.force_login(make_user("asker"))
    assert client.get(new_thread_url(professor)).status_code == 200

    response = client.post(
        new_thread_url(professor),
        {"kind": "question", "title": "Does she curve?", "body": "", "tags": ""},
    )

    post = Post.objects.get()
    assert post.professor_id == professor.pk
    assert response["Location"] == reverse("community:post_detail", args=[post.pk])
    detail = client.get(response["Location"]).content
    assert page_url(professor).encode() in detail


def test_unknown_professor_cannot_get_a_thread(client, make_user):
    client.force_login(make_user("asker"))
    response = client.post(
        reverse("community:professor_post_create", args=["nobody-at-all"]),
        {"kind": "question", "title": "Hello"},
    )
    assert response.status_code == 404
    assert Post.objects.count() == 0


def test_feed_with_an_unknown_professor_falls_back_to_everything(client, make_post):
    make_post("Still here")
    response = client.get(reverse("community:feed"), {"professor": "nobody-at-all"})
    assert response.status_code == 200
    assert b"Still here" in response.content
