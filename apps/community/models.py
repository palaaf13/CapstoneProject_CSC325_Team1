"""
The community feed: posts, the comments embedded inside them, and votes.

Three MongoDB decisions shape this file (see CLAUDE.md):

1. Comments are EMBEDDED in their Post (``EmbeddedModelArrayField``), not a
   collection of their own. A thread is always read together with its post, so
   one document read renders the whole page. The cost is that embedded fields
   cannot be filtered on, and two comments saved at the same instant can race
   (last writer wins) — acceptable at campus scale, revisit if it bites.
2. ``score`` and ``comment_count`` are denormalized onto the Post so the feed
   can sort and render rows without touching Vote or unpacking every thread.
   ``services`` keeps them in step; nothing else should write them.
3. Votes are their own collection keyed on (user, target_type, target_id), as
   in CLAUDE.md's data model, so the same table can carry comment votes later.

User content is soft-deleted (``is_removed``) so thread structure survives.
"""

from bson import ObjectId
from django.conf import settings
from django.db import models
from django.utils import timezone
from django_mongodb_backend.fields import ArrayField, EmbeddedModelArrayField, ObjectIdField
from django_mongodb_backend.models import EmbeddedModel

MAX_TAGS = 5
MAX_TAG_LENGTH = 24


class PostKind(models.TextChoices):
    DISCUSSION = "discussion", "Discussion"
    QUESTION = "question", "Question"
    NOTES = "notes", "Notes"


class Comment(EmbeddedModel):
    """One comment, stored inside its Post. Flat for now — no replies."""

    # Embedded models have no primary key, so each comment carries its own id
    # for links (#comment-<id>) and for deleting one comment out of the array.
    # Not named `id`: Django reserves that name for primary keys (models.E004).
    comment_id = ObjectIdField(default=ObjectId)
    # An id rather than a ForeignKey: embedded models cannot hold one. The
    # service resolves ids to users in a single query when rendering a thread.
    author_id = ObjectIdField()
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(default=timezone.now)
    is_removed = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Comment {self.comment_id}"


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    kind = models.CharField(max_length=20, choices=PostKind.choices, default=PostKind.DISCUSSION)
    title = models.CharField(max_length=200)
    body = models.TextField(max_length=5000, blank=True)
    tags = ArrayField(models.CharField(max_length=MAX_TAG_LENGTH), default=list, blank=True)
    comments = EmbeddedModelArrayField(Comment, default=list, blank=True)

    # Denormalized — written only by services.py.
    score = models.IntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_removed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"], name="community_post_new_idx"),
            models.Index(fields=["-score", "-created_at"], name="community_post_top_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def live_comments(self) -> list[Comment]:
        return [c for c in self.comments if not c.is_removed]


class VoteTarget(models.TextChoices):
    POST = "post", "Post"


class Vote(models.Model):
    """One person's up (+1) or down (-1) vote on one thing. No row means no vote."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    target_type = models.CharField(max_length=20, choices=VoteTarget.choices)
    target_id = ObjectIdField()
    value = models.SmallIntegerField(choices=[(1, "Up"), (-1, "Down")])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "target_type", "target_id"], name="community_vote_once"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.value:+d} {self.target_type}:{self.target_id}"
