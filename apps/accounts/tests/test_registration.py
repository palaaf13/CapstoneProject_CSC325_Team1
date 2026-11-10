"""Registration, email confirmation, resending the link, and abandoned sign-ups."""

import re
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
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
    # The resend limit lives in the cache, which outlives a test's DB rollback.
    cache.clear()
    with override_settings(MAILERS=test_mailers):
        if hasattr(mail, "outbox"):
            mail.outbox.clear()
        yield
        if hasattr(mail, "outbox"):
            mail.outbox.clear()
    cache.clear()


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
    def fail_delivery(user, confirmation_url):
        raise services.EmailDeliveryError("Email backend rejected the message")

    monkeypatch.setattr(services, "send_registration_confirmation", fail_delivery)
    data = valid_registration_data("student@farmingdale.edu")

    response = client.post(reverse("register"), data)

    assert response.status_code == 200
    assert b"confirmation email" in response.content
    assert not get_user_model().objects.filter(username=data["username"]).exists()


# --------------------------------------------------------------------------
# Resending the confirmation link
# --------------------------------------------------------------------------
def confirmation_path(message) -> str:
    return urlsplit(re.search(r"https?://\S+", message.body).group()).path


def register_unconfirmed(client, email: str = "student@farmingdale.edu"):
    data = valid_registration_data(email)
    client.post(reverse("register"), data)
    mail.outbox.clear()
    return get_user_model().objects.get(username=data["username"])


def age_signup(user, *, seconds: int) -> None:
    user.date_joined = timezone.now() - timedelta(seconds=seconds)
    user.save(update_fields=["date_joined"])


def test_resend_emails_a_link_that_activates_the_account(client):
    user = register_unconfirmed(client)

    response = client.post(reverse("resend_confirmation"), {"email": "Student@Farmingdale.edu"})

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["student@farmingdale.edu"]
    client.get(confirmation_path(mail.outbox[0]))
    user.refresh_from_db()
    assert user.is_active


def test_resend_answers_the_same_for_unknown_and_confirmed_emails(client):
    register_unconfirmed(client)
    client.post(reverse("resend_confirmation"), {"email": "student@farmingdale.edu"})
    unconfirmed = client.get(reverse("login")).content
    get_user_model().objects.filter(email="student@farmingdale.edu").update(is_active=True)
    mail.outbox.clear()

    client.post(reverse("resend_confirmation"), {"email": "student@farmingdale.edu"})
    confirmed = client.get(reverse("login")).content
    client.post(reverse("resend_confirmation"), {"email": "nobody@farmingdale.edu"})
    unknown = client.get(reverse("login")).content

    assert mail.outbox == []
    assert b"new confirmation link" in unconfirmed
    assert b"new confirmation link" in confirmed
    assert b"new confirmation link" in unknown


def test_resend_is_limited_per_email(client):
    register_unconfirmed(client)

    for _ in range(services.RESEND_MAX_REQUESTS + 2):
        response = client.post(reverse("resend_confirmation"), {"email": "student@farmingdale.edu"})
        assert response.status_code == 302

    assert len(mail.outbox) == services.RESEND_MAX_REQUESTS


def test_resend_restarts_an_expired_signup(client):
    user = register_unconfirmed(client)
    age_signup(user, seconds=settings.PASSWORD_RESET_TIMEOUT + 60)

    client.post(reverse("resend_confirmation"), {"email": "student@farmingdale.edu"})

    assert services.delete_expired_signups() == 0
    client.get(confirmation_path(mail.outbox[0]))
    user.refresh_from_db()
    assert user.is_active


def test_resend_page_redirects_signed_in_students(client):
    user = register_unconfirmed(client)
    get_user_model().objects.filter(pk=user.pk).update(is_active=True)
    client.force_login(user)

    assert client.get(reverse("resend_confirmation")).status_code == 302


# --------------------------------------------------------------------------
# Abandoned sign-ups
# --------------------------------------------------------------------------
def test_pending_signup_keeps_its_email_and_points_to_resend(client):
    register_unconfirmed(client)

    response = client.post(reverse("register"), valid_registration_data("student@farmingdale.edu"))

    assert response.status_code == 200
    assert b"resend the confirmation email" in response.content
    assert get_user_model().objects.filter(email="student@farmingdale.edu").count() == 1


def test_expired_signup_frees_its_email_and_username(client):
    old = register_unconfirmed(client)
    age_signup(old, seconds=settings.PASSWORD_RESET_TIMEOUT + 60)
    data = valid_registration_data("student@farmingdale.edu")
    data["username"] = old.username

    response = client.post(reverse("register"), data)

    assert response.status_code == 302
    assert not get_user_model().objects.filter(pk=old.pk).exists()
    new = get_user_model().objects.get(email="student@farmingdale.edu")
    assert new.username == old.username
    assert not new.is_active
    assert len(mail.outbox) == 1


def test_expiry_cleanup_never_deletes_confirmed_or_signed_in_accounts():
    long_ago = settings.PASSWORD_RESET_TIMEOUT + 60
    active = get_user_model().objects.create_user(
        username="active", email="active@farmingdale.edu", password="x", is_active=True
    )
    signed_in_once = get_user_model().objects.create_user(
        username="was-active", email="was-active@farmingdale.edu", password="x", is_active=False
    )
    signed_in_once.last_login = timezone.now()
    signed_in_once.save(update_fields=["last_login"])
    abandoned = get_user_model().objects.create_user(
        username="abandoned", email="abandoned@farmingdale.edu", password="x", is_active=False
    )
    for user in (active, signed_in_once, abandoned):
        age_signup(user, seconds=long_ago)

    assert services.delete_expired_signups() == 1
    remaining = set(get_user_model().objects.values_list("username", flat=True))
    assert {"active", "was-active"} <= remaining
    assert "abandoned" not in remaining
