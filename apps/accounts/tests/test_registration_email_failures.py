"""Sign-up when the confirmation email can't go out, and accounts stuck unconfirmed.

Production broke on 2026-11-23: DEFAULT_FROM_EMAIL was "RamHub ramhub.fsc@gmail.com"
(no angle brackets), Django's SMTP backend raised ValueError, the view only caught
mail-server errors, so sign-up returned a 500 and left an unconfirmed account
holding the student's email and username.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail.backends.smtp import EmailBackend
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
from config.settings.base import sender_address

from .test_registration import valid_registration_data

pytestmark = pytest.mark.django_db
User = get_user_model()


# -- the sender address -------------------------------------------------------
@pytest.mark.parametrize(
    ("configured", "used"),
    [
        ("RamHub ramhub.fsc@gmail.com", "RamHub <ramhub.fsc@gmail.com>"),  # the production typo
        ("RamHub <ramhub.fsc@gmail.com>", "RamHub <ramhub.fsc@gmail.com>"),
        ("ramhub.fsc@gmail.com", "ramhub.fsc@gmail.com"),
        ("  Ram Hub Team   team@example.org ", "Ram Hub Team <team@example.org>"),
    ],
)
def test_sender_address_puts_missing_brackets_back(configured, used):
    assert sender_address(configured) == used


def test_the_repaired_production_address_passes_the_smtp_backends_check():
    # The exact check that raised in production. prep_address uses no instance
    # state, so it is called unbound (creating a backend directly is deprecated).
    check = EmailBackend.prep_address
    assert check(None, sender_address("RamHub ramhub.fsc@gmail.com")) == "ramhub.fsc@gmail.com"
    with pytest.raises(ValueError, match="Invalid address"):
        check(None, "RamHub ramhub.fsc@gmail.com")


# -- a send that fails in any way ---------------------------------------------
@pytest.mark.parametrize(
    "error",
    [
        ValueError("Invalid address 'RamHub ramhub.fsc@gmail.com'"),  # the production failure
        OSError("connection refused"),
        RuntimeError("anything else"),
    ],
)
def test_a_failed_confirmation_email_is_a_friendly_error_not_a_500(client, monkeypatch, error):
    def broken(*args, **kwargs):
        raise error

    monkeypatch.setattr(services, "send_registration_confirmation", broken)
    data = valid_registration_data("someone@gmail.com")

    response = client.post(reverse("register"), data)

    assert response.status_code == 200
    assert b"We couldn&#x27;t send the confirmation email" in response.content
    assert not User.objects.filter(username=data["username"]).exists()


def test_after_a_failed_send_the_student_can_simply_try_again(client, monkeypatch):
    data = valid_registration_data("someone@gmail.com")
    monkeypatch.setattr(
        services,
        "send_registration_confirmation",
        lambda *a, **k: (_ for _ in ()).throw(ValueError()),
    )
    client.post(reverse("register"), data)
    monkeypatch.undo()

    assert client.post(reverse("register"), data).status_code == 302
    assert len(mail.outbox) == 1


def test_the_success_message_doesnt_say_farmingdale(client):
    response = client.post(reverse("register"), valid_registration_data("a@gmail.com"), follow=True)
    assert b"Check your email for a link" in response.content
    assert b"Farmingdale email" not in response.content


# -- accounts stuck unconfirmed -----------------------------------------------
def make_unconfirmed(data, *, age=timedelta(hours=1), **extra):
    extra.setdefault("is_active", False)
    user = User.objects.create_user(
        username=data["username"],
        email=data["email"].casefold(),
        password="whatever-it-was-1",
        **extra,
    )
    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - age)
    return user


def test_a_stale_unconfirmed_account_no_longer_blocks_signing_up_again(client):
    """Exactly what happened in production: the account exists, the email never came."""
    data = valid_registration_data("stuck@gmail.com")
    old = make_unconfirmed(data)

    response = client.post(reverse("register"), data)

    assert response.status_code == 302
    assert not User.objects.filter(pk=old.pk).exists()
    assert User.objects.get(username=data["username"]).email == "stuck@gmail.com"
    assert len(mail.outbox) == 1


def test_a_pending_confirmation_is_not_knocked_out(client):
    """Inside the hold window, someone else can't take over an email that's being confirmed."""
    data = valid_registration_data("pending@gmail.com")
    make_unconfirmed(data, age=timedelta(minutes=2))

    response = client.post(reverse("register"), data)

    assert response.status_code == 200
    assert User.objects.filter(email="pending@gmail.com").count() == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"is_active": True},  # a real, confirmed account
        {"last_login": timezone.now() - timedelta(days=3)},  # signed in once, since deactivated
    ],
)
def test_real_accounts_are_never_released(extra):
    data = valid_registration_data("real@gmail.com")
    user = make_unconfirmed(data, **extra)

    assert services.release_unconfirmed(username=data["username"], email=data["email"]) == 0
    assert User.objects.filter(pk=user.pk).exists()
