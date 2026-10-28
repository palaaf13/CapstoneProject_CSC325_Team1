"""Forms for creating verified student accounts and editing their profiles."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

# A sanity range, not a policy: it catches typos like 225 or 20026 while
# allowing alumni and students several years from finishing.
GRAD_YEAR_YEARS_BACK = 80
GRAD_YEAR_YEARS_AHEAD = 10


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "display_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "username"}
        )
        self.fields["email"].widget.attrs.update({"class": "field-input", "autocomplete": "email"})
        self.fields["display_name"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "name"}
        )
        self.fields["password1"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "new-password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "new-password"}
        )

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().casefold()


class ProfileForm(forms.ModelForm):
    """The profile fields a student may change about themselves.

    Email, username, and role are deliberately absent: email is the verified
    college identity, and role is set by admins. Fields left out of a ModelForm
    are ignored even if a request posts them.
    """

    class Meta:
        model = get_user_model()
        fields = ("display_name", "major", "grad_year", "bio", "is_profile_public")
        labels = {
            "grad_year": "Graduation year",
            "is_profile_public": "Show my profile to other students",
        }
        help_texts = {
            "display_name": "The name other students see next to your posts.",
            "bio": "Up to 500 characters.",
        }
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("display_name", "major", "grad_year", "bio"):
            self.fields[name].widget.attrs.update({"class": "field-input"})
        self.fields["display_name"].widget.attrs.update({"autocomplete": "name"})

    def clean_display_name(self) -> str:
        return self.cleaned_data["display_name"].strip()

    def clean_major(self) -> str:
        return self.cleaned_data["major"].strip()

    def clean_bio(self) -> str:
        return self.cleaned_data["bio"].strip()

    def clean_grad_year(self) -> int | None:
        grad_year = self.cleaned_data["grad_year"]
        if grad_year is None:
            return None

        this_year = timezone.now().year
        earliest = this_year - GRAD_YEAR_YEARS_BACK
        latest = this_year + GRAD_YEAR_YEARS_AHEAD
        if not earliest <= grad_year <= latest:
            raise forms.ValidationError(f"Enter a year between {earliest} and {latest}.")
        return grad_year
