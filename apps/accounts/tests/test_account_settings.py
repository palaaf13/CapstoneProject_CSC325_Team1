"""Profile nav, recent posts, avatars, and the account-settings pages."""

import re
from uuid import uuid4

import pytest
from django.contrib.auth import SESSION_KEY
from django.test import Client
from django.urls import reverse

from apps.accounts import services
from apps.accounts.models import User
from apps.community.models import Post
from apps.saved.models import SavedItem

pytestmark = pytest.mark.django_db

PASSWORD = "FSC-Strong!Password-2026"


def make_student(**fields) -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex}",
        email=f"{uuid4().hex[:12]}@farmingdale.edu",
        password=PASSWORD,
        **fields,
    )


def signed_in(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def is_signed_in(client: Client) -> bool:
    return client.get(reverse("profile")).status_code == 200


# -- avatar ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("display_name", "expected"),
    [("Ram Student", "RS"), ("Mary Jo Smith", "MS"), ("cher", "CH"), ("", "RA")],
)
def test_monogram_comes_from_the_display_name(display_name, expected):
    user = User(username="ramfan", display_name=display_name)

    assert user.monogram == expected


def test_monogram_tone_is_one_of_four():
    assert make_student().monogram_tone in {1, 2, 3, 4}


# -- nav and overview -------------------------------------------------------
def test_profile_nav_links_every_section_and_marks_the_current_one(client):
    client.force_login(make_student())

    html = client.get(reverse("profile_privacy")).content.decode()

    for name in ("profile", "profile_posts", "profile_edit", "profile_password", "profile_account"):
        assert f'href="{reverse(name)}"' in html
    active = re.search(r'<a href="([^"]+)"\s+class="profile-nav-link-active"', html)
    assert active and active.group(1) == reverse("profile_privacy")


def test_overview_shows_only_the_students_own_live_posts(client):
    student = make_student()
    Post.objects.create(author=student, title="Take CSC 325 with a friend")
    Post.objects.create(author=student, title="Removed one", is_removed=True)
    Post.objects.create(author=make_student(), title="Someone else's post")
    client.force_login(student)

    html = client.get(reverse("profile")).content.decode()

    assert "Take CSC 325 with a friend" in html
    assert "Removed one" not in html
    assert "Someone else" not in html


def test_overview_without_posts_shows_an_empty_state(client):
    client.force_login(make_student())

    response = client.get(reverse("profile"))

    assert b"No posts yet" in response.content
    assert reverse("community:post_create").encode() in response.content


def test_overview_links_to_all_posts_only_when_there_are_more(client):
    student = make_student()
    for n in range(6):
        Post.objects.create(author=student, title=f"Post {n}")
    client.force_login(student)

    response = client.get(reverse("profile"))

    assert b"See all 6" in response.content


def test_posts_page_paginates(client):
    student = make_student()
    for n in range(21):
        Post.objects.create(author=student, title=f"Post {n}")
    client.force_login(student)

    response = client.get(reverse("profile_posts"), {"page": 2})

    assert response.status_code == 200
    assert response.context["page"].number == 2
    assert len(response.context["page"].object_list) == 1


# -- privacy ---------------------------------------------------------------
def test_privacy_toggle_saves_both_ways(client):
    student = make_student()
    client.force_login(student)

    client.post(reverse("profile_privacy"), {"is_profile_public": "on"})
    student.refresh_from_db()
    assert student.is_profile_public

    client.post(reverse("profile_privacy"), {})
    student.refresh_from_db()
    assert not student.is_profile_public


# -- password --------------------------------------------------------------
def test_changing_password_keeps_this_session_and_ends_others():
    student = make_student()
    here, elsewhere = signed_in(student), signed_in(student)

    response = here.post(
        reverse("profile_password"),
        {
            "old_password": PASSWORD,
            "new_password1": "Another-Strong!Pass-27",
            "new_password2": "Another-Strong!Pass-27",
        },
    )

    assert response.status_code == 302
    student.refresh_from_db()
    assert student.check_password("Another-Strong!Pass-27")
    assert is_signed_in(here)
    assert not is_signed_in(elsewhere)


def test_wrong_current_password_changes_nothing(client):
    student = make_student()
    client.force_login(student)

    response = client.post(
        reverse("profile_password"),
        {
            "old_password": "not-it",
            "new_password1": "Another-Strong!Pass-27",
            "new_password2": "Another-Strong!Pass-27",
        },
    )

    assert response.status_code == 200
    student.refresh_from_db()
    assert student.check_password(PASSWORD)


# -- sign out other devices ------------------------------------------------
def test_sign_out_others_ends_other_sessions_but_not_this_one():
    student = make_student()
    here, elsewhere = signed_in(student), signed_in(student)

    response = here.post(reverse("sign_out_other_devices"))

    assert response.status_code == 302
    assert is_signed_in(here)
    assert not is_signed_in(elsewhere)


def test_sign_out_others_needs_post(client):
    client.force_login(make_student())

    assert client.get(reverse("sign_out_other_devices")).status_code == 405


def test_session_hash_is_djangos_own_until_the_first_sign_out_others():
    # Guards the _get_session_auth_hash override: adding session_epoch must
    # not have signed anyone out, and a Django upgrade that stops routing
    # through that method should fail here rather than silently.
    student = make_student()
    before = student.get_session_auth_hash()
    student.session_epoch = None  # documents saved before the field existed
    assert student.get_session_auth_hash() == before

    student.session_epoch = 1
    assert student.get_session_auth_hash() != before


# -- delete account --------------------------------------------------------
def test_delete_needs_the_password_and_the_checkbox(client):
    student = make_student()
    client.force_login(student)

    wrong = client.post(reverse("delete_account"), {"password": "nope", "confirm": "on"})
    unticked = client.post(reverse("delete_account"), {"password": PASSWORD})

    assert wrong.status_code == unticked.status_code == 200
    assert "That password isn’t right." in wrong.content.decode()
    assert b"Tick the box to confirm." in unticked.content
    student.refresh_from_db()
    assert student.is_active


def test_delete_anonymizes_keeps_posts_and_signs_out_everywhere():
    student = make_student(display_name="Ram Student", major="Nursing", bio="Hi")
    email = student.email
    post = Post.objects.create(author=student, title="Advice that should outlive me")
    SavedItem.objects.create(user=student, kind=SavedItem.Kind.COURSE, object_id=post.pk)
    here, elsewhere = signed_in(student), signed_in(student)

    response = here.post(reverse("delete_account"), {"password": PASSWORD, "confirm": "on"})

    assert response.status_code == 302
    assert SESSION_KEY not in here.session
    assert not is_signed_in(elsewhere)

    student.refresh_from_db()
    assert not student.is_active
    assert not student.has_usable_password()
    assert (student.display_name, student.major, student.bio) == ("", "", "")
    assert student.get_full_name() == "Former student"
    assert student.email != email
    assert not User.objects.filter(email=email).exists(), "the address can register again"
    assert Post.objects.filter(pk=post.pk).exists()
    assert not SavedItem.objects.filter(user=student).exists()


def test_delete_needs_post(client):
    client.force_login(make_student())

    assert client.get(reverse("delete_account")).status_code == 405


def test_set_profile_visibility_touches_only_visibility():
    student = make_student(major="Nursing")

    services.set_profile_visibility(student, is_public=True)

    student.refresh_from_db()
    assert student.is_profile_public
    assert student.major == "Nursing"
