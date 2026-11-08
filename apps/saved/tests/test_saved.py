"""The filing cabinet: saving courses, professors, and clubs."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.models import User
from apps.campus.models import Club
from apps.saved import services
from apps.saved.models import SavedItem

pytestmark = pytest.mark.django_db


def make_student() -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex[:12]}",
        email=f"{uuid4().hex[:10]}@farmingdale.edu",
        password="FSC-Strong!Password-2026",
    )


def make_club(name: str = "Chess Club") -> Club:
    return Club.objects.create(
        name=name, slug=uuid4().hex[:10], org_type="Recognized Student Organizations"
    )


def toggle(client, kind: str, obj, data=None, **headers):
    payload = {"kind": kind, "object_id": str(obj.pk), **(data or {})}
    return client.post(reverse("saved:toggle"), payload, **headers)


# -- Services ------------------------------------------------------------------
def test_toggle_saves_then_unsaves(make_course):
    student, course = make_student(), make_course()

    assert services.toggle(student, course) is True
    assert services.is_saved(student, course)
    assert services.toggle(student, course) is False
    assert not services.is_saved(student, course)


def test_an_item_can_only_be_saved_once_per_student(make_course):
    student, course = make_student(), make_course()
    SavedItem.objects.create(user=student, kind="course", object_id=course.pk)

    with pytest.raises(IntegrityError):
        SavedItem.objects.create(user=student, kind="course", object_id=course.pk)


def test_cabinet_groups_by_kind_newest_first(make_course, make_professor):
    student = make_student()
    first = make_course(code="CSC 101", title="Computer Science I")
    second = make_course(code="CSC 102", title="Computer Science II")
    professor = make_professor(first_name="Ada", last_name="Lovelace")
    club = make_club()
    for obj in (first, professor, second, club):
        services.toggle(student, obj)

    sections = services.cabinet(student)

    assert [s.kind for s in sections] == ["course", "professor", "club"]
    assert [c.code for c in sections[0].items] == ["CSC 102", "CSC 101"]


def test_cabinet_skips_things_that_no_longer_exist(make_course):
    student, course = make_student(), make_course()
    services.toggle(student, course)
    course.delete()

    assert services.cabinet(student) == []


def test_students_only_see_their_own_items(make_course):
    mine, theirs = make_student(), make_student()
    services.toggle(theirs, make_course())

    assert services.cabinet(mine) == []


def test_anonymous_visitors_have_nothing_saved(make_course):
    assert services.is_saved(AnonymousUser(), make_course()) is False


# -- The toggle endpoint ---------------------------------------------------------
def test_toggle_requires_sign_in(client, make_course):
    response = toggle(client, "course", make_course())

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert SavedItem.objects.count() == 0


def test_toggle_requires_post(client, make_course):
    client.force_login(make_student())

    assert client.get(reverse("saved:toggle")).status_code == 405


def test_plain_form_post_saves_and_returns_to_the_page(client, make_course):
    student, course = make_student(), make_course()
    client.force_login(student)
    page = reverse("catalog:course_detail", args=[course.slug])

    response = toggle(client, "course", course, data={"next": page})

    assert response.status_code == 302
    assert response.url == page
    assert services.is_saved(student, course)


def test_offsite_next_is_ignored(client, make_course):
    client.force_login(make_student())

    response = toggle(client, "course", make_course(), data={"next": "https://evil.example/"})

    assert response.url == reverse("saved:cabinet")


def test_htmx_gets_the_button_back_in_its_new_state(client, make_professor):
    student, professor = make_student(), make_professor()
    client.force_login(student)

    response = toggle(client, "professor", professor, HTTP_HX_REQUEST="true")
    html = response.content.decode()

    assert response.status_code == 200
    assert "<html" not in html  # a fragment, not a page
    assert 'aria-pressed="true"' in html
    assert "Saved" in html


@pytest.mark.parametrize(
    "kind, object_id",
    [
        ("course", "not-an-id"),
        ("textbook", "64b7f0f0f0f0f0f0f0f0f0f0"),
        ("club", "64b7f0f0f0f0f0f0f0f0f0f0"),
    ],
)
def test_bad_or_missing_targets_are_404(client, kind, object_id):
    client.force_login(make_student())

    response = client.post(reverse("saved:toggle"), {"kind": kind, "object_id": object_id})

    assert response.status_code == 404
    assert SavedItem.objects.count() == 0


# -- Pages -----------------------------------------------------------------------
def test_detail_pages_show_the_save_button_state(client, make_course, make_professor):
    student = make_student()
    course, professor, club = make_course(), make_professor(), make_club()
    services.toggle(student, course)
    client.force_login(student)

    course_page = client.get(reverse("catalog:course_detail", args=[course.slug])).content.decode()
    professor_page = client.get(
        reverse("catalog:professor_detail", args=[professor.slug])
    ).content.decode()
    club_page = client.get(reverse("campus:club_detail", args=[club.slug])).content.decode()

    assert 'aria-pressed="true"' in course_page
    assert 'aria-pressed="false"' in professor_page
    assert 'aria-pressed="false"' in club_page


def test_signed_out_visitors_are_invited_to_sign_in(client, make_course):
    course = make_course()
    page = reverse("catalog:course_detail", args=[course.slug])

    html = client.get(page).content.decode()

    assert "Sign in to save" in html
    assert f"{reverse('login')}?next={page}" in html  # comes straight back after sign-in


def test_cabinet_requires_sign_in(client):
    response = client.get(reverse("saved:cabinet"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_cabinet_lists_saved_items_with_remove_buttons(client, make_course):
    student, course = make_student(), make_course(code="CSC 325", title="Software Engineering")
    services.toggle(student, course)
    client.force_login(student)

    html = client.get(reverse("saved:cabinet")).content.decode()

    assert "Software Engineering" in html
    assert "Remove" in html


def test_empty_cabinet_says_how_to_fill_it(client):
    client.force_login(make_student())

    html = client.get(reverse("saved:cabinet")).content.decode()

    assert "Nothing saved yet" in html


def test_profile_links_to_the_cabinet(client):
    client.force_login(make_student())

    assert reverse("saved:cabinet").encode() in client.get(reverse("profile")).content
