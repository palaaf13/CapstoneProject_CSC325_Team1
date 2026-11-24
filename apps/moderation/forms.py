"""The Report form and the moderator queue's action form.

Views never read request.POST directly.
"""

from bson import ObjectId
from django import forms

from .models import MAX_NOTE_LENGTH, ModAction, Report


class ReportForm(forms.Form):
    reason = forms.ChoiceField(
        label="What's wrong with it?",
        choices=Report.Reason.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Pick a reason.", "invalid_choice": "Pick a reason."},
    )
    note = forms.CharField(
        label="Anything the moderators should know?",
        required=False,
        max_length=MAX_NOTE_LENGTH,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional, unless you chose “Something else”.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("reason") == Report.Reason.OTHER and not cleaned.get("note"):
            self.add_error(
                "note", "Tell the moderators what's wrong when you choose “Something else”."
            )
        return cleaned


class ModerationActionForm(forms.Form):
    """One button press on the moderator queue: hide, restore, or dismiss one item.

    The ids are only checked for shape here. ``queue.perform`` looks them up and
    decides whether the action fits.
    """

    action = forms.ChoiceField(choices=ModAction.Action.choices)
    target_type = forms.ChoiceField(choices=Report.TargetType.choices)
    target_id = forms.CharField(max_length=24)
    parent_id = forms.CharField(max_length=24, required=False)
    note = forms.CharField(max_length=MAX_NOTE_LENGTH, required=False, strip=True)

    def clean_target_id(self) -> ObjectId:
        return _object_id(self.cleaned_data["target_id"])

    def clean_parent_id(self) -> ObjectId | None:
        value = self.cleaned_data["parent_id"]
        return _object_id(value) if value else None

    def clean(self):
        cleaned = super().clean()
        is_comment = cleaned.get("target_type") == Report.TargetType.COMMENT
        if is_comment and not cleaned.get("parent_id"):
            self.add_error("parent_id", "A comment needs the post it belongs to.")
        return cleaned


def _object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise forms.ValidationError("Not a valid id.")
    return ObjectId(value)
