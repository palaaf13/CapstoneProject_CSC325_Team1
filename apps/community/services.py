"""
Business logic for the feed. Views parse the request, call one of these, render.

Every write that touches someone's content checks ownership here, not in the
view, so no future caller can skip it. Moderation uses ``is_staff`` until the
custom User model brings real roles (Phase 2); ``can_moderate`` is the one
place to change when it does.
"""

from collections.abc import Iterable

from bson import ObjectId
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.utils import timezone

from .forms import FeedQuery
from .models import Comment, Post, Vote, VoteTarget

PAGE_SIZE = 20


# -- permissions -----------------------------------------------------------
def can_moderate(user) -> bool:
    return bool(user.is_authenticated and user.is_staff)


def can_edit(user, post: Post) -> bool:
    return bool(user.is_authenticated and post.author_id == user.pk and not post.is_removed)


def can_remove(user, post: Post) -> bool:
    if post.is_removed or not user.is_authenticated:
        return False
    return post.author_id == user.pk or can_moderate(user)


def can_remove_comment(user, comment: Comment) -> bool:
    if comment.is_removed or not user.is_authenticated:
        return False
    return comment.author_id == user.pk or can_moderate(user)


# -- reading ---------------------------------------------------------------
def feed_posts(query: FeedQuery) -> QuerySet[Post]:
    """The feed for one set of filters. A removed post stays only while it has comments."""
    posts = Post.objects.filter(Q(is_removed=False) | Q(comment_count__gt=0)).select_related(
        "author"
    )
    if query.kind:
        posts = posts.filter(kind=query.kind)
    if query.tag:
        posts = posts.filter(tags__contains=[query.tag])
    if query.q:
        posts = posts.filter(
            Q(title__icontains=query.q) | Q(body__icontains=query.q), is_removed=False
        )
    if query.sort == "top":
        return posts.order_by("-score", "-created_at")
    return posts.order_by("-created_at")


def get_post(post_id: str) -> Post | None:
    """The post with this id, or None for a missing or malformed id."""
    if not ObjectId.is_valid(post_id):
        return None
    return Post.objects.select_related("author").filter(pk=ObjectId(post_id)).first()


def votes_by(user, posts: Iterable[Post]) -> dict[ObjectId, int]:
    """{post id: +1/-1} for this user's votes on these posts. One query."""
    if not user.is_authenticated:
        return {}
    ids = [p.pk for p in posts]
    if not ids:
        return {}
    rows = Vote.objects.filter(
        user=user, target_type=VoteTarget.POST, target_id__in=ids
    ).values_list("target_id", "value")
    return dict(rows)


def comment_authors(post: Post) -> dict[ObjectId, object]:
    """{author id: user} for everyone who commented. One query for the whole thread."""
    ids = {c.author_id for c in post.comments}
    if not ids:
        return {}
    return {u.pk: u for u in get_user_model().objects.filter(pk__in=list(ids))}


def display_name(user) -> str:
    """How a person is named in the feed until profiles add display_name."""
    if user is None:
        return "A former student"
    return user.get_full_name() or user.get_username()


# -- writing ---------------------------------------------------------------
def create_post(*, author, kind: str, title: str, body: str, tags: list[str]) -> Post:
    return Post.objects.create(author=author, kind=kind, title=title, body=body, tags=tags)


def edit_post(user, post: Post, *, kind: str, title: str, body: str, tags: list[str]) -> Post:
    if not can_edit(user, post):
        raise PermissionDenied("Only the author can edit a post.")
    post.kind, post.title, post.body, post.tags = kind, title, body, tags
    post.edited_at = timezone.now()
    post.save(update_fields=["kind", "title", "body", "tags", "edited_at"])
    return post


def remove_post(user, post: Post) -> None:
    """Soft-delete: the thread survives, the content does not."""
    if not can_remove(user, post):
        raise PermissionDenied("You can only remove your own posts.")
    post.is_removed = True
    post.body = ""
    post.tags = []
    post.save(update_fields=["is_removed", "body", "tags"])


def add_comment(user, post: Post, body: str) -> Comment:
    if post.is_removed:
        raise PermissionDenied("This post was removed and is closed to new comments.")
    comment = Comment(author_id=user.pk, body=body)
    post.comments.append(comment)
    post.comment_count = len(post.live_comments)
    post.save(update_fields=["comments", "comment_count"])
    return comment


def remove_comment(user, post: Post, comment_id: str) -> None:
    comment = next((c for c in post.comments if str(c.comment_id) == comment_id), None)
    if comment is None:
        raise Comment.DoesNotExist(comment_id)
    if not can_remove_comment(user, comment):
        raise PermissionDenied("You can only remove your own comments.")
    comment.is_removed = True
    comment.body = ""
    post.comment_count = len(post.live_comments)
    post.save(update_fields=["comments", "comment_count"])


def cast_vote(user, post: Post, value: int) -> int:
    """
    Set this user's vote on a post to +1, -1, or 0 (none), and return the new score.

    The score is recounted from Vote rows rather than incremented, so a double
    click, a retried request or a race between two tabs can never drift it.
    """
    if post.is_removed:
        raise PermissionDenied("Removed posts cannot be voted on.")
    lookup = {"user": user, "target_type": VoteTarget.POST, "target_id": post.pk}
    if value == 0:
        Vote.objects.filter(**lookup).delete()
    else:
        Vote.objects.update_or_create(**lookup, defaults={"value": value})

    votes = Vote.objects.filter(target_type=VoteTarget.POST, target_id=post.pk)
    score = votes.filter(value=1).count() - votes.filter(value=-1).count()
    Post.objects.filter(pk=post.pk).update(score=score)
    post.score = score
    return score
