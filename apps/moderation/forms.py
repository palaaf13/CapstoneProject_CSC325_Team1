"""The Report form. Views never read request.POST directly."""

from django import forms

from .models import MAX_NOTE_LENGTH, Report


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
