"""
Reports: a student flags a post, a comment, or a rating for the moderators.

A Report points at its target with a type plus an id, like ``saved.SavedItem``,
because one model covers four kinds of content and MongoDB has no generic
relations. ``services.find_target`` turns the pair back into an object.

The moderator queue (RH-14) reads open reports and moves ``status`` off OPEN;
every hide, restore, and dismiss it performs is logged as a ModAction.
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


class ModAction(models.Model):
    """One thing a moderator did. Written for every hide, restore, and dismiss.

    The log is append-only: nothing in the app edits or deletes a ModAction.
    It points at its target the same way a Report does.
    """

    class Action(models.TextChoices):
        HIDE = "hide", "Hidden"
        RESTORE = "restore", "Restored"
        DISMISS = "dismiss", "Reports dismissed"

    # SET_NULL, not CASCADE: deleting a moderator's account must not erase the
    # record of what was done. Only an account deletion ever leaves this empty.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="mod_actions"
    )
    target_type = models.CharField(max_length=20, choices=Report.TargetType.choices)
    target_id = ObjectIdField()
    parent_id = ObjectIdField(null=True, blank=True)  # a comment's post, as on Report
    action = models.CharField(max_length=10, choices=Action.choices)
    note = models.TextField(max_length=MAX_NOTE_LENGTH, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target_type", "target_id"])]

    def __str__(self) -> str:
        return f"{self.get_action_display()}: {self.target_type} {self.target_id} by {self.actor}"
