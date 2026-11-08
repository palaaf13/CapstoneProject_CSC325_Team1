"""Signing in with a college email, signing out, and the per-IP lockout."""

from uuid import uuid4

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts import services
from apps.accounts.forms import SignInForm
from apps.accounts.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "FSC-Strong!Password-2026"
MISMATCH = "That email and password don&#x27;t match an account."
LOCKED = "Too many sign-in attempts."


@pytest.fixture(autouse=True)
def clear_lockouts():
    # Failure counts live in the cache, which outlives a test's DB rollback.
    cache.clear()
    yield
    cache.clear()


def make_student(**fields) -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex}",
        email=f"{uuid4().hex[:12]}@farmingdale.edu",
        password=PASSWORD,
        **fields,
    )


def sign_in(client, email: str, password: str = PASSWORD, **extra):
    return client.post(reverse("login"), {"email": email, "password": password}, **extra)


def signed_in_user_id(client) -> str | None:
    return client.session.get("_auth_user_id")


def test_student_signs_in_with_email_and_lands_on_profile(client):
    student = make_student()

    response = sign_in(client, student.email)

    assert response.status_code == 302
    assert response.url == reverse("profile")
    assert signed_in_user_id(client) == str(student.pk)


def test_email_match_ignores_case_and_surrounding_spaces(client):
    student = make_student()

    response = sign_in(client, f"  {student.email.upper()}  ")

    assert response.status_code == 302
    assert signed_in_user_id(client) == str(student.pk)


def test_wrong_password_and_unknown_email_get_the_same_error(client):
    student = make_student()

    wrong_password = sign_in(client, student.email, "not-the-password")
    unknown_email = sign_in(client, "nobody@farmingdale.edu")

    for response in (wrong_password, unknown_email):
        assert response.status_code == 200
        assert MISMATCH.encode() in response.content
    assert signed_in_user_id(client) is None


def test_unconfirmed_account_is_told_to_confirm_its_email(client):
    student = make_student(is_active=False)

    response = sign_in(client, student.email)

    assert response.status_code == 200
    assert b"Confirm your email before signing in." in response.content
    assert signed_in_user_id(client) is None


def test_unconfirmed_account_with_wrong_password_gets_the_generic_error(client):
    student = make_student(is_active=False)

    response = sign_in(client, student.email, "not-the-password")

    assert MISMATCH.encode() in response.content
    assert b"Confirm your email" not in response.content


def test_sign_in_returns_to_a_same_site_next_page(client):
    student = make_student()

    response = client.post(
        reverse("login"),
        {"email": student.email, "password": PASSWORD, "next": reverse("profile_edit")},
    )

    assert response.url == reverse("profile_edit")


def test_sign_in_ignores_a_next_page_on_another_site(client):
    student = make_student()

    response = client.post(
        reverse("login"),
        {"email": student.email, "password": PASSWORD, "next": "https://evil.example/"},
    )

    assert response.url == reverse("profile")


def test_signed_in_student_visiting_sign_in_goes_to_profile(client):
    client.force_login(make_student())

    response = client.get(reverse("login"))

    assert response.status_code == 302
    assert response.url == reverse("profile")


def test_nav_shows_profile_and_sign_out_only_when_signed_in(client):
    signed_out = client.get(reverse("about")).content
    client.force_login(make_student())
    signed_in = client.get(reverse("about")).content

    assert f'action="{reverse("logout")}"'.encode() not in signed_out
    assert f'href="{reverse("register")}"'.encode() in signed_out
    assert f'action="{reverse("logout")}"'.encode() in signed_in
    assert f'href="{reverse("profile")}"'.encode() in signed_in


def test_sign_out_requires_post(client):
    client.force_login(make_student())

    response = client.get(reverse("logout"))

    assert response.status_code == 405
    assert signed_in_user_id(client) is not None


def test_sign_out_ends_the_session(client):
    client.force_login(make_student())

    response = client.post(reverse("logout"))

    assert response.url == reverse("home")
    assert signed_in_user_id(client) is None


def test_fifth_failure_locks_the_ip_out(client):
    student = make_student()

    for _ in range(services.SIGN_IN_MAX_FAILURES - 1):
        response = sign_in(client, student.email, "not-the-password")
        assert response.status_code == 200
        assert LOCKED.encode() not in response.content

    response = sign_in(client, student.email, "not-the-password")

    assert response.status_code == 429
    assert LOCKED.encode() in response.content
    assert MISMATCH.encode() not in response.content


def test_locked_out_ip_is_refused_even_with_the_right_password(client):
    student = make_student()
    for _ in range(services.SIGN_IN_MAX_FAILURES):
        sign_in(client, student.email, "not-the-password")

    response = sign_in(client, student.email)

    assert response.status_code == 429
    assert signed_in_user_id(client) is None


def test_lockout_applies_only_to_the_ip_that_failed(client):
    student = make_student()
    for _ in range(services.SIGN_IN_MAX_FAILURES):
        sign_in(client, student.email, "not-the-password", REMOTE_ADDR="10.0.0.1")

    response = sign_in(client, student.email, REMOTE_ADDR="10.0.0.2")

    assert response.status_code == 302
    assert signed_in_user_id(client) == str(student.pk)


def test_successful_sign_in_resets_the_failure_count(client):
    student = make_student()
    for _ in range(services.SIGN_IN_MAX_FAILURES - 1):
        sign_in(client, student.email, "not-the-password")
    sign_in(client, student.email)
    client.post(reverse("logout"))

    response = sign_in(client, student.email, "not-the-password")

    assert response.status_code == 200
    assert not services.is_sign_in_locked("127.0.0.1")


def test_locked_out_form_never_checks_the_password(rf, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("authenticate_by_email ran while locked out")

    monkeypatch.setattr(services, "authenticate_by_email", fail_if_called)
    form = SignInForm(
        rf.post(reverse("login")),
        data={"email": "student@farmingdale.edu", "password": PASSWORD},
        locked_out=True,
    )

    assert not form.is_valid()
    assert LOCKED in form.non_field_errors()[0]
