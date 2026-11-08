"""
Forms for the campus app: the club directory's query string, and posting a
club event.

The directory form has the same contract as apps/catalog/forms.py: nothing reads request.GET directly, and
the form is lenient. A directory URL gets bookmarked and shared, so a category
that no longer exists or a junk page number falls back to the default instead
of returning a 400.
"""

from datetime import timedelta
from typing import Any, NamedTuple

from django import forms
from django.utils import timezone

from .models import ClubEvent

MAX_QUERY_LENGTH = 100


class ClubQuery(NamedTuple):
    """Validated, defaulted directory parameters."""

    q: str
    category: str
    page: int
    append: bool


class ClubDirectoryForm(forms.Form):
    q = forms.CharField(required=False, max_length=MAX_QUERY_LENGTH, strip=True)
    category = forms.CharField(required=False, max_length=80, strip=True)
    page = forms.IntegerField(required=False, min_value=1, max_value=10_000)
    append = forms.BooleanField(required=False)

    def __init__(self, *args: Any, categories: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.allowed_categories = set(categories or [])

    def clean_category(self) -> str:
        """Silently drop a category that no longer exists."""
        value = self.cleaned_data.get("category", "")
        return value if value in self.allowed_categories else ""

    def to_query(self) -> ClubQuery:
        """Return usable parameters whether or not the form validated."""
        self.is_valid()
        data = self.cleaned_data
        return ClubQuery(
            q=(data.get("q") or "").strip(),
            category=data.get("category") or "",
            page=data.get("page") or 1,
            append=bool(data.get("append")),
        )


# How far ahead an event can be posted. Further out than this is almost always
# a typo in the year.
EVENT_HORIZON = timedelta(days=365)
DATETIME_INPUT_FORMAT = "%Y-%m-%dT%H:%M"


class ClubEventForm(forms.ModelForm):
    """A student posting an upcoming event for one club."""

    class Meta:
        model = ClubEvent
        fields = ["title", "starts_at", "ends_at", "location", "details"]
        labels = {
            "title": "Event name",
            "starts_at": "Starts",
            "ends_at": "Ends (optional)",
            "location": "Where",
            "details": "Details (optional)",
        }
        help_texts = {
            "location": "A room and building, e.g. Lupton Hall 120.",
            "details": "What to expect, what to bring, who it is for.",
        }
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_INPUT_FORMAT
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_INPUT_FORMAT
            ),
            "details": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "field-input")

    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        now = timezone.now()
        if starts_at < now:
            raise forms.ValidationError("That time has already passed.")
        if starts_at > now + EVENT_HORIZON:
            raise forms.ValidationError("Events can be posted up to a year ahead.")
        return starts_at

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        starts_at, ends_at = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "The end has to be after the start.")
        return cleaned
