"""RH-39: upcoming club events show up in the global search."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.campus import services
from apps.campus.models import ClubEvent

pytestmark = pytest.mark.django_db


def make_event(club, title, *, starts_in=timedelta(days=2), **fields) -> ClubEvent:
    fields.setdefault("location", "Campus Center 110")
    poster = User.objects.create_user(
        username=f"student-{uuid4().hex[:12]}",
        email=f"{uuid4().hex[:10]}@farmingdale.edu",
        password="FSC-Strong!Password-2026",
    )
    return ClubEvent.objects.create(
        club=club, title=title, starts_at=timezone.now() + starts_in, posted_by=poster, **fields
    )


def search_page(client, q: str) -> str:
    return client.get(reverse("search"), {"q": q}).content.decode()


# -- Acceptance: searching finds upcoming events --------------------------------
def test_search_shows_matching_events_in_their_own_section(client, make_club):
    club = make_club("Gaming Club")
    make_event(club, "Smash Bros. tournament", location="Campus Center Ballroom")

    html = search_page(client, "tournament")

    assert "Upcoming events" in html
    assert "Smash Bros. tournament" in html
    assert "Gaming Club" in html
    assert reverse("campus:club_detail", args=[club.slug]) in html


def test_finished_events_never_show_in_search(client, make_club):
    club = make_club("Gaming Club")
    make_event(club, "Old tournament", starts_in=-timedelta(days=3))

    html = search_page(client, "tournament")

    assert "Old tournament" not in html
    assert "Nothing matched that search" in html


# -- What counts as a match -----------------------------------------------------
def test_matches_name_place_details_and_club(make_club):
    gaming, chess = make_club("Gaming Club"), make_club("Chess Club", short_name="FSCC")
    make_event(gaming, "Tournament", location="Ballroom")
    make_event(gaming, "Game night", details="Bring a controller")
    make_event(chess, "Blitz night")

    def titles(q):
        return [e.title for e in services.search_events(q)]

    assert titles("ballroom") == ["Tournament"]
    assert titles("CONTROLLER") == ["Game night"]
    assert titles("chess") == ["Blitz night"]
    assert titles("fscc") == ["Blitz night"]


def test_every_word_has_to_match(make_club):
    club = make_club("Gaming Club")
    make_event(club, "Smash tournament")
    make_event(club, "Chess tournament")

    assert [e.title for e in services.search_events("smash tournament")] == ["Smash tournament"]


def test_results_are_soonest_first(make_club):
    club = make_club("Gaming Club")
    make_event(club, "Later night", starts_in=timedelta(days=9))
    make_event(club, "Sooner night", starts_in=timedelta(days=1))

    assert [e.title for e in services.search_events("night")] == ["Sooner night", "Later night"]


def test_blank_search_finds_no_events(make_club):
    make_event(make_club(), "Anything")

    assert services.search_events("   ") == []


# -- "See all" hands the words to the events page ---------------------------------
def test_see_all_link_filters_the_events_page(client, make_club):
    club = make_club("Gaming Club")
    for day in range(1, 8):
        make_event(club, f"Tournament round {day}", starts_in=timedelta(days=day))
    make_event(club, "Board game night")

    html = search_page(client, "tournament")
    events_page = client.get(reverse("campus:events"), {"q": "tournament"}).content.decode()

    assert "See all 7 upcoming events" in html
    assert f"{reverse('campus:events')}?q=tournament" in html
    assert "Tournament round 7" in events_page
    assert "Board game night" not in events_page
    assert "Show all events" in events_page


def test_events_page_says_when_nothing_matches(client, make_club):
    make_event(make_club(), "Game night")

    html = client.get(reverse("campus:events"), {"q": "zzz"}).content.decode()

    assert "No upcoming events match that" in html
