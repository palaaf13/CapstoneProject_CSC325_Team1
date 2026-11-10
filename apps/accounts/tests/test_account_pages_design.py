"""The account pages use Sara's login design and still work as real forms."""

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

pytestmark = pytest.mark.django_db

ACCOUNT_PAGES = ("login", "register", "password_reset", "password_reset_done")


@pytest.mark.parametrize("name", ACCOUNT_PAGES)
def test_account_pages_use_the_portal_design(client, name):
    html = client.get(reverse(name)).content.decode()

    assert 'class="rh-login-page"' in html
    assert "login-portal.jpg" in html
    assert "css/auth.css" in html
    assert "js/auth.js" in html


def test_the_design_files_ship_with_the_site():
    for path in ("css/auth.css", "js/auth.js", "img/login-portal.jpg"):
        assert finders.find(path), path


# -- Acceptance: the sign-in form posts real fields to the real view --------------
def test_sign_in_form_posts_to_django_with_csrf(client):
    html = client.get(reverse("login"), {"next": "/events/"}).content.decode()

    assert 'method="post"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'name="next" value="/events/"' in html
    assert "Preview" not in html and "preview only" not in html


def test_every_password_field_gets_a_show_button(client):
    register = client.get(reverse("register")).content.decode()
    sign_in = client.get(reverse("login")).content.decode()

    assert register.count("data-toggle-password=") == 2
    assert sign_in.count("data-toggle-password=") == 1


def test_sign_in_links_to_reset_and_register(client):
    html = client.get(reverse("login")).content.decode()

    assert f'href="{reverse("password_reset")}"' in html
    assert f'href="{reverse("register")}"' in html


def test_wrong_password_error_shows_in_the_new_layout(client):
    response = client.post(
        reverse("login"),
        {"email": f"nobody@{settings.COLLEGE_EMAIL_DOMAIN}", "password": "not-it"},
    )
    html = response.content.decode()

    assert 'class="rh-alert" role="alert"' in html
    assert "match an account" in html
