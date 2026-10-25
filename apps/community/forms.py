"""
Forms for the feed. Nothing in views.py reads request.GET or request.POST directly.

The feed's query-string form is lenient, like the directories': a bookmarked URL
with a stale sort or a junk page number falls back to the default instead of
returning a 400. The write forms are strict.
"""

import re
from typing import NamedTuple

from django import forms

from .models import MAX_TAG_LENGTH, MAX_TAGS, Comment, Post, PostKind

SORTS = {"new": "Newest", "top": "Top"}
MAX_QUERY_LENGTH = 100


def normalize_tag(raw: str) -> str:
    """'#Study Group!' -> 'study-group'. Lowercase letters, digits and hyphens only."""
    tag = raw.strip().lower().lstrip("#")
    tag = re.sub(r"\s+", "-", tag)
    tag = re.sub(r"[^a-z0-9-]", "", tag)
    return tag.strip("-")[:MAX_TAG_LENGTH]


class FeedQuery(NamedTuple):
    q: str
    kind: str
    tag: str
    sort: str
    page: int


class FeedQueryForm(forms.Form):
    q = forms.CharField(required=False, max_length=MAX_QUERY_LENGTH, strip=True)
    kind = forms.CharField(required=False, max_length=20)
    tag = forms.CharField(required=False, max_length=MAX_TAG_LENGTH + 1)
    sort = forms.CharField(required=False, max_length=10)
    page = forms.IntegerField(required=False, min_value=1, max_value=10_000)

    def to_query(self) -> FeedQuery:
        """Validated values, with anything invalid replaced by its default."""
        # cleaned_data keeps every field that passed, so one bad parameter only
        # resets itself, not the whole query.
        self.is_valid()
        data = self.cleaned_data
        kind = data.get("kind") or ""
        sort = data.get("sort") or "new"
        return FeedQuery(
            q=data.get("q") or "",
            kind=kind if kind in PostKind.values else "",
            tag=normalize_tag(data.get("tag") or ""),
            sort=sort if sort in SORTS else "new",
            page=data.get("page") or 1,
        )


class PostForm(forms.Form):
    kind = forms.ChoiceField(choices=PostKind.choices, initial=PostKind.DISCUSSION)
    title = forms.CharField(max_length=Post._meta.get_field("title").max_length, strip=True)
    body = forms.CharField(
        required=False,
        max_length=Post._meta.get_field("body").max_length,
        widget=forms.Textarea(attrs={"rows": 8}),
    )
    tags = forms.CharField(
        required=False,
        max_length=200,
        help_text=f"Up to {MAX_TAGS}, separated by commas — e.g. csc325, study-group",
    )

    def clean_tags(self) -> list[str]:
        tags: list[str] = []
        for raw in (self.cleaned_data.get("tags") or "").split(","):
            tag = normalize_tag(raw)
            if tag and tag not in tags:
                tags.append(tag)
        if len(tags) > MAX_TAGS:
            raise forms.ValidationError(f"Use at most {MAX_TAGS} tags.")
        return tags


class CommentForm(forms.Form):
    body = forms.CharField(
        max_length=Comment._meta.get_field("body").max_length,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "Write something before posting a comment."},
    )


class VoteForm(forms.Form):
    """+1, -1, or 0 to take a vote back."""

    value = forms.TypedChoiceField(choices=[("1", "Up"), ("-1", "Down"), ("0", "None")], coerce=int)
    # Where a no-JavaScript vote returns to. Checked against the host in the view.
    next = forms.CharField(required=False, max_length=500)
