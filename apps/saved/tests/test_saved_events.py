"""RH-40: saving club events to the filing cabinet."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.campus.models import Club, ClubEvent
from apps.saved import services
from apps.saved.models import SavedItem

pytestmark = pytest.mark.django_db


def make_student() -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex[:12]}",
        email=f"{uuid4().hex[:10]}@farmingdale.edu",
        password="FSC-Strong!Password-2026",
    )


def make_club(name: str = "Gaming Club") -> Club:
    return Club.objects.create(name=name, slug=uuid4().hex[:10], org_type="Club Sports")


def make_event(club=None, title="Smash tournament", *, starts_in=timedelta(days=3)) -> ClubEvent:
    return ClubEvent.objects.create(
        club=club or make_club(),
        title=title,
        starts_at=timezone.now() + starts_in,
        location="Campus Center Ballroom",
        posted_by=make_student(),
    )


def save(client, event, **headers):
    return client.post(
        reverse("saved:toggle"),
        {"kind": "event", "object_id": str(event.pk), "next": "/events/", "compact": "1"},
        **headers,
    )


# -- Acceptance: save an event, find it in the cabinet, remove it ---------------------
def test_student_saves_an_event_and_finds_it_in_the_cabinet(client):
    student, event = make_student(), make_event(make_club("Gaming Club"))
    client.force_login(student)

    response = save(client, event)

    assert response.status_code == 302
    assert response.url == "/events/"
    cabinet = client.get(reverse("saved:cabinet")).content.decode()
    assert "Upcoming events" in cabinet
    assert "Smash tournament" in cabinet
    assert "Gaming Club" in cabinet
    assert reverse("campus:club_detail", args=[event.club.slug]) in cabinet


def test_removing_from_the_cabinet_unsaves_it(client):
    student, event = make_student(), make_event()
    services.toggle(student, event)
    client.force_login(student)

    client.post(
        reverse("saved:toggle"),
        {"kind": "event", "object_id": str(event.pk), "next": reverse("saved:cabinet")},
    )

    assert not services.is_saved(student, event)
    assert "Nothing saved yet" in client.get(reverse("saved:cabinet")).content.decode()


# -- The button on event lists ------------------------------------------------------
def test_event_lists_show_each_events_saved_state(client):
    student, club = make_student(), make_club()
    saved_event = make_event(club, "Saved one")
    make_event(club, "Other one")
    services.toggle(student, saved_event)
    client.force_login(student)

    for url in (reverse("campus:events"), reverse("campus:club_detail", args=[club.slug])):
        html = client.get(url).content.decode()
        assert html.count('aria-pressed="true"') == 1
        assert html.count('name="kind" value="event"') == 2


def test_htmx_save_swaps_back_the_small_button(client):
    student, event = make_student(), make_event()
    client.force_login(student)

    response = save(client, event, HTTP_HX_REQUEST="true")
    html = response.content.decode()

    assert response.status_code == 200
    assert 'aria-pressed="true"' in html
    assert 'name="compact" value="1"' in html
    assert "btn-primary" not in html


def test_signed_out_visitors_are_invited_to_sign_in(client):
    make_event()

    html = client.get(reverse("campus:events")).content.decode()

    assert "Sign in to save" in html
    assert SavedItem.objects.count() == 0


def test_saving_requires_sign_in(client):
    response = save(client, make_event())

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert SavedItem.objects.count() == 0


# -- What the cabinet keeps ---------------------------------------------------------
def test_finished_and_removed_events_drop_out(client):
    student, club = make_student(), make_club()
    finished = make_event(club, "Last week", starts_in=-timedelta(days=7))
    removed = make_event(club, "Cancelled")
    kept = make_event(club, "Still on")
    for event in (finished, removed, kept):
        services.toggle(student, event)
    removed.delete()

    [section] = services.cabinet(student)

    assert section.kind == "event"
    assert [e.title for e in section.items] == ["Still on"]


def test_saved_events_list_soonest_first(client):
    student, club = make_student(), make_club()
    later = make_event(club, "Later", starts_in=timedelta(days=9))
    sooner = make_event(club, "Sooner", starts_in=timedelta(days=1))
    services.toggle(student, sooner)
    services.toggle(student, later)  # saved most recently

    [section] = services.cabinet(student)

    assert [e.title for e in section.items] == ["Sooner", "Later"]


def test_events_come_first_in_the_cabinet(make_course):
    student = make_student()
    services.toggle(student, make_course())
    services.toggle(student, make_event())

    assert [s.kind for s in services.cabinet(student)] == ["event", "course"]
