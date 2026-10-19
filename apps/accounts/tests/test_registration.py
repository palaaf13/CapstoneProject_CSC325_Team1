"""Registration form and service validation."""

import re
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.accounts.forms import RegistrationForm
from apps.accounts.services import register_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def use_in_memory_email_backend():
    test_mailers = {
        "default": {
            "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
        }
    }
    with override_settings(MAILERS=test_mailers):
        if hasattr(mail, "outbox"):
            mail.outbox.clear()
        yield
        if hasattr(mail, "outbox"):
            mail.outbox.clear()


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


def test_login_page_links_to_registration(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert f'href="{reverse("register")}"'.encode() in response.content


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
    assert not user.is_active


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


def test_registration_view_emails_confirmation_and_keeps_account_inactive(client):
    data = valid_registration_data("student@farmingdale.edu")

    response = client.post(reverse("register"), data)

    assert response.status_code == 302
    assert response.url == reverse("login")
    user = get_user_model().objects.get(username=data["username"])
    assert not user.is_active
    assert "_auth_user_id" not in client.session
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    assert mail.outbox[0].subject == "Confirm your RamHub account"
    assert re.search(r"https?://\S+/confirm-email/[^/]+/[^/\s]+/", mail.outbox[0].body)


def test_registration_view_shows_error_for_non_college_email(client):
    data = valid_registration_data("student@example.com")

    response = client.post(reverse("register"), data)

    assert response.status_code == 200
    assert b"Use your Farmingdale State College email address." in response.content
    assert not get_user_model().objects.filter(username=data["username"]).exists()


def test_confirmation_link_activates_account(client):
    data = valid_registration_data("student@farmingdale.edu")
    client.post(reverse("register"), data)
    user = get_user_model().objects.get(username=data["username"])
    confirmation_url = re.search(r"https?://\S+", mail.outbox[0].body).group()

    response = client.get(urlsplit(confirmation_url).path)

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.is_active
    assert response.url == reverse("login")


def test_invalid_confirmation_token_does_not_activate_account(client):
    data = valid_registration_data("student@farmingdale.edu")
    client.post(reverse("register"), data)
    user = get_user_model().objects.get(username=data["username"])
    confirmation_url = re.search(r"https?://\S+", mail.outbox[0].body).group()
    path_parts = urlsplit(confirmation_url).path.strip("/").split("/")
    path_parts[-1] = "invalid-token"

    response = client.get("/" + "/".join(path_parts) + "/", follow=True)

    assert response.status_code == 200
    user.refresh_from_db()
    assert not user.is_active
    assert b"invalid or expired" in response.content


def test_expired_confirmation_token_does_not_activate_account(client):
    data = valid_registration_data("student@farmingdale.edu")
    client.post(reverse("register"), data)
    user = get_user_model().objects.get(username=data["username"])
    confirmation_url = re.search(r"https?://\S+", mail.outbox[0].body).group()

    with override_settings(PASSWORD_RESET_TIMEOUT=-1):
        response = client.get(urlsplit(confirmation_url).path)

    assert response.status_code == 302
    user.refresh_from_db()
    assert not user.is_active


def test_email_delivery_failure_removes_unverified_account(client, monkeypatch):
    from apps.accounts import services

    def fail_delivery(user, confirmation_url):
        raise services.EmailDeliveryError("Email backend rejected the message")

    monkeypatch.setattr(services, "send_registration_confirmation", fail_delivery)
    data = valid_registration_data("student@farmingdale.edu")

    response = client.post(reverse("register"), data)

    assert response.status_code == 200
    assert b"confirmation email" in response.content
    assert not get_user_model().objects.filter(username=data["username"]).exists()
