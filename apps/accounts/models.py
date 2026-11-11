from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.crypto import salted_hmac
from django_mongodb_backend.fields import EmbeddedModelArrayField, ObjectIdField
from django_mongodb_backend.models import EmbeddedModel


def validate_college_email(value: str) -> None:
    domain = value.rpartition("@")[2].casefold()
    if domain != settings.COLLEGE_EMAIL_DOMAIN.casefold():
        raise ValidationError(
            "Use your Farmingdale State College email address.",
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

    # Bumped by "Sign out of other devices". It is folded into the session
    # hash below, so every session signed in under the old value stops
    # verifying. 0 (or None, on documents saved before this field existed)
    # leaves Django's hash untouched, so adding the field signed nobody out.
    session_epoch = models.PositiveIntegerField(default=0)

    def _get_session_auth_hash(self, secret=None) -> str:
        # Django's get_session_auth_hash() and its SECRET_KEY_FALLBACKS
        # variant both go through this one method, so overriding it covers
        # both. test_account_settings.py fails if an upgrade changes that.
        if not self.session_epoch:
            return super()._get_session_auth_hash(secret=secret)
        return salted_hmac(
            "apps.accounts.User.session_auth_hash",
            f"{self.password}:{self.session_epoch}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    @property
    def public_name(self) -> str:
        """The name shown at the top of the profile."""
        return self.display_name or self.get_full_name() or self.get_username()

    @property
    def monogram(self) -> str:
        """One or two initials: the profile picture until uploads exist."""
        words = [w for w in self.public_name.replace("-", " ").split() if w[0].isalnum()]
        if len(words) >= 2:
            return (words[0][0] + words[-1][0]).upper()
        return self.public_name[:2].upper() or "?"

    @property
    def monogram_tone(self) -> int:
        """Which of the four avatar colourways this student gets (1-4).

        Decorative only. Derived from the primary key, so it doesn't change
        when the student renames themselves.
        """
        return sum(ord(char) for char in str(self.pk)) % 4 + 1
