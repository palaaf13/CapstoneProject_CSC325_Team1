"""Stored AI summaries, so a page view does not mean an API call."""

from django.db import models


class ReviewSummaryCache(models.Model):
    """One generated summary, keyed on everything that went into it.

    The key hashes the prompt version, the model and the exact review texts, so a
    new or edited review, a new prompt, or a new model all produce a new key and a
    fresh summary. Old rows are simply never read again. Failures are not stored:
    the next page view tries again.
    """

    key = models.CharField(max_length=64, unique=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Summary {self.key[:12]}"
