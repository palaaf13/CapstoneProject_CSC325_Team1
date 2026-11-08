"""Feed business logic: filters, votes, comments, and who may change what."""

import pytest
from django.core.exceptions import PermissionDenied

from apps.community import services
from apps.community.forms import FeedQuery
from apps.community.models import Comment, Post, PostKind, Vote

pytestmark = pytest.mark.django_db


def q(**kwargs) -> FeedQuery:
    return FeedQuery(**{"q": "", "kind": "", "tag": "", "sort": "new", "page": 1, **kwargs})


# -- reading ---------------------------------------------------------------
def test_feed_filters_by_kind_tag_and_search(make_post):
    notes = make_post("Exam 1 notes", kind=PostKind.NOTES, tags=["csc325"], body="Chapter 3")
    question = make_post("Where is Lupton Hall?", kind=PostKind.QUESTION, tags=["campus"])

    assert list(services.feed_posts(q(kind="notes"))) == [notes]
    assert list(services.feed_posts(q(tag="campus"))) == [question]
    assert list(services.feed_posts(q(q="chapter"))) == [notes]


def test_top_sorts_by_score(make_post, make_user):
    low, high = make_post("Low"), make_post("High")
    for name in ("a", "b"):
        services.cast_vote(make_user(name), high, 1)

    assert list(services.feed_posts(q(sort="top"))) == [high, low]


def test_removed_post_without_comments_leaves_the_feed(make_post):
    post = make_post()
    services.remove_post(post.author, post)
    assert list(services.feed_posts(q())) == []


def test_removed_post_with_comments_stays_so_the_thread_survives(make_post, make_user):
    post = make_post()
    services.add_comment(make_user("replier"), post, "Count me in")
    services.remove_post(post.author, post)
    assert list(services.feed_posts(q())) == [post]


def test_get_post_handles_malformed_ids():
    assert services.get_post("not-an-object-id") is None


# -- votes -----------------------------------------------------------------
def test_votes_set_change_and_clear_the_score(make_post, make_user):
    post, voter = make_post(), make_user("voter")

    assert services.cast_vote(voter, post, 1) == 1
    assert services.cast_vote(voter, post, 1) == 1  # a double click does not double count
    assert services.cast_vote(voter, post, -1) == -1
    assert services.cast_vote(voter, post, 0) == 0

    assert Vote.objects.count() == 0
    assert Post.objects.get(pk=post.pk).score == 0


def test_votes_by_returns_only_this_users_votes(make_post, make_user):
    post, me, other = make_post(), make_user("me"), make_user("other")
    services.cast_vote(other, post, -1)
    assert services.votes_by(me, [post]) == {}
    services.cast_vote(me, post, 1)
    assert services.votes_by(me, [post]) == {post.pk: 1}


# -- comments --------------------------------------------------------------
def test_comments_are_embedded_and_counted(make_post, make_user):
    post, writer = make_post(), make_user("writer")
    comment = services.add_comment(writer, post, "First")

    stored = Post.objects.get(pk=post.pk)
    assert [c.body for c in stored.comments] == ["First"]
    assert stored.comment_count == 1
    assert services.comment_authors(stored) == {writer.pk: writer}

    services.remove_comment(writer, stored, str(comment.comment_id))
    stored = Post.objects.get(pk=post.pk)
    assert stored.comment_count == 0
    assert stored.comments[0].is_removed and stored.comments[0].body == ""


def test_removing_an_unknown_comment_raises(make_post):
    post = make_post()
    with pytest.raises(Comment.DoesNotExist):
        services.remove_comment(post.author, post, "000000000000000000000000")


# -- permissions -----------------------------------------------------------
def test_only_the_author_can_edit(make_post, make_user):
    post = make_post()
    with pytest.raises(PermissionDenied):
        services.edit_post(
            make_user("stranger"), post, kind="discussion", title="X", body="", tags=[]
        )


def test_strangers_cannot_remove_but_staff_can(make_post, make_user):
    post = make_post()
    with pytest.raises(PermissionDenied):
        services.remove_post(make_user("stranger"), post)

    services.remove_post(make_user("mod", is_staff=True), post)
    assert Post.objects.get(pk=post.pk).is_removed


def test_strangers_cannot_remove_someone_elses_comment(make_post, make_user):
    post = make_post()
    comment = services.add_comment(make_user("writer"), post, "Mine")
    with pytest.raises(PermissionDenied):
        services.remove_comment(make_user("stranger"), post, str(comment.comment_id))
