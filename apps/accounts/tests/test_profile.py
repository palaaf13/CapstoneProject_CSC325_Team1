"""The signed-in student's own profile page and profile editing."""

from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
from apps.accounts.forms import ProfileForm
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def make_student(**fields) -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex}",
        email=f"{uuid4().hex[:12]}@farmingdale.edu",
        password="FSC-Strong!Password-2026",
        **fields,
    )


def profile_data(**overrides) -> dict:
    data = {
        "display_name": "Ram Student",
        "major": "Computer Science",
        "grad_year": str(timezone.now().year + 2),
        "bio": "Ask me about CSC 325.",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "url_name",
    [
        "profile",
        "profile_posts",
        "profile_edit",
        "profile_privacy",
        "profile_password",
        "profile_account",
    ],
)
def test_profile_pages_send_signed_out_visitors_to_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_profile_shows_the_signed_in_students_details(client):
    student = make_student(display_name="Ram Student", major="Nursing")
    client.force_login(student)

    response = client.get(reverse("profile"))

    assert response.status_code == 200
    assert b"Ram Student" in response.content
    assert b"Nursing" in response.content
    assert student.email.encode() in response.content


def test_empty_profile_shows_prompts_instead_of_blanks(client):
    client.force_login(make_student())

    response = client.get(reverse("profile"))

    assert b"Not added yet" in response.content
    assert b"Add a bio" in response.content


def test_edit_form_no_longer_carries_the_visibility_toggle(client):
    student = make_student(is_profile_public=True)
    client.force_login(student)

    client.post(reverse("profile_edit"), profile_data())

    student.refresh_from_db()
    assert student.is_profile_public, "editing the profile must not reset Privacy"


def test_editing_saves_the_profile_and_returns_to_it(client):
    student = make_student()
    client.force_login(student)

    response = client.post(reverse("profile_edit"), profile_data())

    assert response.status_code == 302
    assert response.url == reverse("profile")
    student.refresh_from_db()
    assert student.display_name == "Ram Student"
    assert student.major == "Computer Science"


def test_editing_cannot_change_email_username_or_role(client):
    student = make_student()
    original = (student.email, student.username, student.role)
    client.force_login(student)

    client.post(
        reverse("profile_edit"),
        profile_data(email="other@farmingdale.edu", username="taken", role=User.Role.ADMIN),
    )

    student.refresh_from_db()
    assert (student.email, student.username, student.role) == original


def test_editing_only_ever_changes_the_signed_in_student(client):
    student = make_student()
    other = make_student(display_name="Someone Else")
    client.force_login(student)

    client.post(reverse("profile_edit"), profile_data(id=str(other.pk), pk=str(other.pk)))

    other.refresh_from_db()
    assert other.display_name == "Someone Else"


def test_invalid_edit_shows_errors_and_saves_nothing(client):
    student = make_student(major="Nursing")
    client.force_login(student)

    response = client.post(reverse("profile_edit"), profile_data(grad_year="20026"))

    assert response.status_code == 200
    assert b"Enter a year between" in response.content
    student.refresh_from_db()
    assert student.major == "Nursing"


@pytest.mark.parametrize("years_from_now", [-81, 11])
def test_grad_year_outside_the_sanity_range_is_rejected(years_from_now):
    form = ProfileForm(data=profile_data(grad_year=str(timezone.now().year + years_from_now)))

    assert not form.is_valid()
    assert "grad_year" in form.errors


def test_blank_grad_year_is_allowed():
    form = ProfileForm(data=profile_data(grad_year=""))

    assert form.is_valid(), form.errors
    assert form.cleaned_data["grad_year"] is None


def test_text_fields_are_trimmed():
    form = ProfileForm(data=profile_data(display_name="  Ram  ", major=" Nursing ", bio=" Hi "))

    assert form.is_valid(), form.errors
    assert (form.cleaned_data["display_name"], form.cleaned_data["major"]) == ("Ram", "Nursing")
    assert form.cleaned_data["bio"] == "Hi"


def test_update_profile_ignores_fields_outside_the_profile():
    student = make_student()

    services.update_profile(
        student, {"major": "Biology", "email": "x@farmingdale.edu", "is_staff": True}
    )

    student.refresh_from_db()
    assert student.major == "Biology"
    assert student.email != "x@farmingdale.edu"
    assert not student.is_staff
