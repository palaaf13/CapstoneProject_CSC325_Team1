"""Registration form and service validation."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.accounts.forms import RegistrationForm
from apps.accounts.services import register_user

pytestmark = pytest.mark.django_db


def valid_registration_data(email: str) -> dict[str, str]:
    username = f"student-{uuid4().hex}"
    return {
        "username": username,
        "email": email,
        "display_name": "RamHub Student",
        "password1": "FSC-Strong!Password-2026",
        "password2": "FSC-Strong!Password-2026",
    }


def test_registration_form_accepts_and_normalizes_college_email():
    data = valid_registration_data("STUDENT@FARMINGDALE.EDU")
    form = RegistrationForm(data=data)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["email"] == "student@farmingdale.edu"


def test_registration_form_rejects_non_college_email():
    form = RegistrationForm(data=valid_registration_data("student@example.com"))

    assert not form.is_valid()
    assert "email" in form.errors


def test_registration_service_creates_user_with_hashed_password():
    data = valid_registration_data("student@farmingdale.edu")

    user = register_user(
        username=data["username"],
        email=data["email"],
        display_name=data["display_name"],
        password=data["password1"],
    )

    assert user.email == data["email"]
    assert user.role == get_user_model().Role.STUDENT
    assert user.check_password(data["password1"])
    assert user.password != data["password1"]


def test_registration_service_rejects_non_college_email():
    data = valid_registration_data("student@example.com")

    with pytest.raises(ValidationError, match="Farmingdale State College email address"):
        register_user(
            username=data["username"],
            email=data["email"],
            display_name=data["display_name"],
            password=data["password1"],
        )

    assert not get_user_model().objects.filter(username=data["username"]).exists()
