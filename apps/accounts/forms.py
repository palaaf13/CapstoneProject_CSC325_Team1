"""Forms for creating verified student accounts."""

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


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
