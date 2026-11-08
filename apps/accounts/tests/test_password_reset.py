"""Password reset by email, end to end, plus the per-IP email limit."""

import re
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts import services
from apps.accounts.models import User

pytestmark = pytest.mark.django_db

OLD_PASSWORD = "FSC-Strong!Password-2026"
NEW_PASSWORD = "Brand-New!Password-2027"


@pytest.fixture(autouse=True)
def clean_slate():
    # The email limit lives in the cache, which outlives a test's DB rollback.
    cache.clear()
    test_mailers = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
    with override_settings(MAILERS=test_mailers):
        if hasattr(mail, "outbox"):
            mail.outbox.clear()
        yield
    cache.clear()


def make_student(*, active: bool = True) -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex[:12]}",
        email=f"{uuid4().hex[:10]}@farmingdale.edu",
        password=OLD_PASSWORD,
        display_name="Maya Rios",
        is_active=active,
    )


def request_reset(client, email: str):
    return client.post(reverse("password_reset"), {"email": email})


def link_from_email(message) -> str:
    match = re.search(r"https?://\S+/password-reset/\S+/\S+/", message.body)
    assert match, message.body
    return urlsplit(match.group(0)).path


def choose_new_password(client, path: str, password: str = NEW_PASSWORD):
    # Django swaps the token for a session marker on the first visit.
    page = client.get(path, follow=True)
    return client.post(
        page.redirect_chain[-1][0], {"new_password1": password, "new_password2": password}
    )


def test_sign_in_page_links_to_password_reset(client):
    response = client.get(reverse("login"))

    assert f'href="{reverse("password_reset")}"'.encode() in response.content


def test_request_page_renders(client):
    response = client.get(reverse("password_reset"))

    assert response.status_code == 200
    assert b'name="email"' in response.content


def test_full_reset_flow_sets_a_new_password_and_signs_in(client):
    student = make_student()

    response = request_reset(client, student.email)
    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [student.email]
    assert message.subject == "Reset your RamHub password"
    assert "Hi Maya Rios," in message.body

    response = choose_new_password(client, link_from_email(message))
    assert response.status_code == 302
    assert response.url == reverse("password_reset_complete")

    student.refresh_from_db()
    assert student.check_password(NEW_PASSWORD)
    assert not student.check_password(OLD_PASSWORD)

    response = client.post(reverse("login"), {"email": student.email, "password": NEW_PASSWORD})
    assert response.status_code == 302


def test_reset_link_works_only_once(client):
    student = make_student()
    request_reset(client, student.email)
    path = link_from_email(mail.outbox[0])
    choose_new_password(client, path)

    response = client.get(path, follow=True)

    assert b"This link has expired" in response.content
    assert b'name="new_password1"' not in response.content


def test_unknown_email_sends_nothing_but_looks_the_same(client):
    response = request_reset(client, "nobody@farmingdale.edu")

    assert response.status_code == 302
    assert response.url == reverse("password_reset_done")
    assert len(mail.outbox) == 0


def test_unconfirmed_account_gets_no_reset_email(client):
    student = make_student(active=False)

    request_reset(client, student.email)

    assert len(mail.outbox) == 0


def test_reset_emails_are_limited_per_ip_without_revealing_it(client):
    student = make_student()

    for _ in range(services.RESET_MAX_REQUESTS + 2):
        response = request_reset(client, student.email)
        assert response.status_code == 302
        assert response.url == reverse("password_reset_done")

    assert len(mail.outbox) == services.RESET_MAX_REQUESTS


def test_resetting_signs_out_other_sessions(client):
    student = make_student()
    other_device = Client()
    other_device.force_login(student)
    assert other_device.get(reverse("profile")).status_code == 200

    request_reset(client, student.email)
    choose_new_password(client, link_from_email(mail.outbox[0]))

    # The old session's password hash no longer matches, so it is signed out.
    assert other_device.get(reverse("profile")).status_code == 302


def test_sent_and_complete_pages_render(client):
    assert client.get(reverse("password_reset_done")).status_code == 200
    assert client.get(reverse("password_reset_complete")).status_code == 200
