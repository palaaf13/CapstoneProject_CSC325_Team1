"""The filing cabinet: courses, professors, clubs, and club events a student saved."""

from django.conf import settings
from django.db import models
from django_mongodb_backend.fields import ObjectIdField


class SavedItem(models.Model):
    """One thing a student saved.

    A kind plus an id rather than a foreign key, because one model covers four
    collections and MongoDB has no generic relations. services.py resolves the
    ids back to objects, one query per kind.
    """

    class Kind(models.TextChoices):
        COURSE = "course", "Course"
        PROFESSOR = "professor", "Professor"
        CLUB = "club", "Club"
        EVENT = "event", "Event"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_items",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    object_id = ObjectIdField()
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-saved_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "object_id"],
                name="saved_item_once_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} saved {self.kind} {self.object_id}"
