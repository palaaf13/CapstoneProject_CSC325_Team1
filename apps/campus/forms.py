"""
Query-string validation for the club directory.

Same contract as apps/catalog/forms.py: nothing reads request.GET directly, and
the form is lenient. A directory URL gets bookmarked and shared, so a category
that no longer exists or a junk page number falls back to the default instead
of returning a 400.
"""

from typing import Any, NamedTuple

from django import forms

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
