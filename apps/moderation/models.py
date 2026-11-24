"""
Reports: a student flags a post, a comment, or a rating for the moderators.

A Report points at its target with a type plus an id, like ``saved.SavedItem``,
because one model covers four kinds of content and MongoDB has no generic
relations. ``services.find_target`` turns the pair back into an object.

The moderator queue that reads these (and moves ``status`` off OPEN) is RH-14.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django_mongodb_backend.fields import ObjectIdField

MAX_NOTE_LENGTH = 500


class Report(models.Model):
    class TargetType(models.TextChoices):
        POST = "post", "Post"
        COMMENT = "comment", "Comment"
        COURSE_RATING = "course_rating", "Course rating"
        PROFESSOR_RATING = "professor_rating", "Professor rating"

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam or advertising"
        HARASSMENT = "harassment", "Harassment or hate"
        OFF_TOPIC = "off_topic", "Off-topic"
        OTHER = "other", "Something else"

    class Status(models.TextChoices):
        # Only OPEN is used by RH-13. The other two are defined now so the
        # moderator queue (RH-14) can use them without a migration.
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports"
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = ObjectIdField()
    # Comments live embedded inside their Post and have no collection of their
    # own, so a comment's id alone cannot find it. For a comment this is the
    # post that holds it; for everything else it is empty.
    parent_id = ObjectIdField(null=True, blank=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.TextField(max_length=MAX_NOTE_LENGTH, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "target_type", "target_id"],
                name="moderation_report_once_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reporter} reported {self.target_type} {self.target_id} ({self.reason})"
