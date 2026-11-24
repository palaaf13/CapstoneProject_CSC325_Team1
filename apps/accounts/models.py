from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django_mongodb_backend.fields import EmbeddedModelArrayField, ObjectIdField
from django_mongodb_backend.models import EmbeddedModel


def validate_college_email(value: str) -> None:
    """Allow any email unless ALLOWED_EMAIL_DOMAINS lists the domains to accept.

    (The name is historical: migration 0001 refers to it, so it stays.)"""
    allowed = settings.ALLOWED_EMAIL_DOMAINS
    if not allowed:
        return
    domain = value.rpartition("@")[2].casefold()
    if domain not in allowed:
        raise ValidationError(
            f"Use an email address at {' or '.join(allowed)}.",
            code="college_email_domain",
        )


class CourseTaken(EmbeddedModel):
    course_id = ObjectIdField()
    semester = models.CharField(max_length=32)


class User(AbstractUser):
    email = models.EmailField(unique=True, validators=[validate_college_email])
    display_name = models.CharField(max_length=100, blank=True)
    major = models.CharField(max_length=100, blank=True)
    grad_year = models.PositiveSmallIntegerField(null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.URLField(blank=True)

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        MODERATOR = "MODERATOR", "Moderator"
        ADMIN = "ADMIN", "Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    is_profile_public = models.BooleanField(default=False)
    courses_taken = EmbeddedModelArrayField(CourseTaken, default=list, blank=True)
