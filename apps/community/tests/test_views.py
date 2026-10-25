"""The feed pages, including sign-in gates and the HTMX vote fragment."""

import pytest
from django.urls import reverse

from apps.community.models import Post

pytestmark = pytest.mark.django_db

FEED_URL = reverse("community:feed")


def test_empty_feed_says_how_to_start(client):
    response = client.get(FEED_URL)
    assert response.status_code == 200
    assert b"Nothing in the feed yet" in response.content


def test_feed_lists_posts_and_escapes_them(client, make_post):
    make_post("<script>alert(1)</script>", tags=["csc325"])
    body = client.get(FEED_URL).content
    assert b"&lt;script&gt;" in body and b"<script>alert(1)" not in body
    assert b"#csc325" in body


def test_htmx_filter_returns_only_the_results_region(client, make_post):
    make_post("Exam notes")
    response = client.get(FEED_URL, {"q": "exam"}, HTTP_HX_REQUEST="true")
    assert response.content.lstrip().startswith(b'<div id="feed-results">')


def test_writing_requires_sign_in(client, make_post):
    post = make_post()
    assert client.get(reverse("community:post_create")).status_code == 302
    response = client.post(reverse("community:post_vote", args=[post.pk]), {"value": "1"})
    assert response.status_code == 302
    assert Post.objects.get(pk=post.pk).score == 0


def test_htmx_vote_when_signed_out_redirects_the_page(client, make_post):
    post = make_post()
    response = client.post(
        reverse("community:post_vote", args=[post.pk]), {"value": "1"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 204
    assert "HX-Redirect" in response


def test_create_post_then_comment(client, make_user):
    client.force_login(make_user("poster"))
    response = client.post(
        reverse("community:post_create"),
        {"kind": "question", "title": "Best place to study?", "body": "", "tags": "campus"},
    )
    post = Post.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("community:post_detail", args=[post.pk])
    assert post.tags == ["campus"]

    client.post(reverse("community:comment_create", args=[post.pk]), {"body": "Library 2nd floor"})
    detail = client.get(reverse("community:post_detail", args=[post.pk]))
    assert b"Library 2nd floor" in detail.content


def test_invalid_post_shows_errors(client, make_user):
    client.force_login(make_user("poster"))
    response = client.post(reverse("community:post_create"), {"kind": "discussion", "title": ""})
    assert response.status_code == 200
    assert Post.objects.count() == 0


def test_htmx_vote_returns_the_vote_fragment(client, make_post, make_user):
    post = make_post()
    client.force_login(make_user("voter"))
    response = client.post(
        reverse("community:post_vote", args=[post.pk]), {"value": "1"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    assert b'aria-pressed="true"' in response.content
    assert Post.objects.get(pk=post.pk).score == 1


def test_no_js_vote_ignores_offsite_next(client, make_post, make_user):
    post = make_post()
    client.force_login(make_user("voter"))
    response = client.post(
        reverse("community:post_vote", args=[post.pk]),
        {"value": "1", "next": "https://evil.example/"},
    )
    assert response["Location"] == reverse("community:post_detail", args=[post.pk])


def test_strangers_get_403_on_edit_and_remove(client, make_post, make_user):
    post = make_post()
    client.force_login(make_user("stranger"))
    assert client.get(reverse("community:post_edit", args=[post.pk])).status_code == 403
    assert client.post(reverse("community:post_remove", args=[post.pk])).status_code == 403
    assert not Post.objects.get(pk=post.pk).is_removed


def test_unknown_or_malformed_post_is_404(client):
    assert client.get(reverse("community:post_detail", args=["nope"])).status_code == 404
    url = reverse("community:post_detail", args=["000000000000000000000000"])
    assert client.get(url).status_code == 404
