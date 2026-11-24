"""One row per question asked of Rambo: for the hourly limit and the cost report.

The question and answer text are deliberately not stored. Conversations live
only in the student's own session.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class RamboQuestion(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rambo_questions"
    )
    asked_at = models.DateTimeField(default=timezone.now)
    # Empty when Rambo answered; otherwise why the fallback was shown.
    fallback_reason = models.CharField(max_length=64, blank=True)
    api_calls = models.PositiveSmallIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    web_searches = models.PositiveSmallIntegerField(default=0)
    model = models.CharField(max_length=64, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "asked_at"], name="assistant_q_user_time_idx")]

    def __str__(self) -> str:
        return f"Rambo question by {self.user_id} at {self.asked_at:%Y-%m-%d %H:%M}"
