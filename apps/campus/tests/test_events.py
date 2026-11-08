"""RH-28: club events, listed on the club page and /events/, with a Google Calendar link."""

from datetime import UTC, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.campus import services
from apps.campus.forms import ClubEventForm
from apps.campus.models import ClubEvent

pytestmark = pytest.mark.django_db


def make_student(name: str = "Maya Rios") -> User:
    return User.objects.create_user(
        username=f"student-{uuid4().hex[:12]}",
        email=f"{uuid4().hex[:10]}@farmingdale.edu",
        password="FSC-Strong!Password-2026",
        display_name=name,
    )


def make_event(club, *, starts_in=timedelta(days=2), posted_by=None, **fields) -> ClubEvent:
    fields.setdefault("title", "Game night")
    fields.setdefault("location", "Campus Center 110")
    return ClubEvent.objects.create(
        club=club,
        starts_at=timezone.now() + starts_in,
        posted_by=posted_by or make_student(),
        **fields,
    )


def local_input(moment) -> str:
    """How a browser's datetime-local field submits a time."""
    return timezone.localtime(moment).strftime("%Y-%m-%dT%H:%M")


def post_event(client, club, **overrides):
    data = {
        "title": "Intro to chess openings",
        "starts_at": local_input(timezone.now() + timedelta(days=3)),
        "ends_at": "",
        "location": "Lupton Hall 120",
        "details": "Bring a board if you have one.",
        **overrides,
    }
    return client.post(reverse("campus:club_event_new", args=[club.slug]), data)


# -- Acceptance: a student posts an event and others can find it --------------------
def test_student_posts_an_event_that_shows_on_the_club_page_and_events_page(client, make_club):
    club = make_club("Chess Club")
    client.force_login(make_student("Maya Rios"))

    response = post_event(client, club)

    assert response.status_code == 302
    assert response.url == reverse("campus:club_detail", args=[club.slug])
    club_page = client.get(response.url).content.decode()
    events_page = client.get(reverse("campus:events")).content.decode()
    for page in (club_page, events_page):
        assert "Intro to chess openings" in page
        assert "Lupton Hall 120" in page
        assert "Posted by Maya Rios" in page
        assert "Add to Google Calendar" in page
    assert "Chess Club" in events_page


def test_google_calendar_link_carries_the_event_in_utc(make_club):
    club = make_club("Chess Club")
    event = make_event(club, title="Blitz tournament", location="Lupton Hall 120")
    event.starts_at = event.starts_at.replace(year=2027, month=1, day=15, hour=23, minute=0)
    event.ends_at = None

    url = urlsplit(event.google_calendar_url)
    query = parse_qs(url.query)

    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://calendar.google.com/calendar/render"
    assert query["action"] == ["TEMPLATE"]
    assert query["text"] == ["Blitz tournament"]
    assert query["location"] == ["Lupton Hall 120"]
    assert query["details"][0].startswith("Chess Club")
    # No end given: one hour long, both ends in UTC.
    start, end = query["dates"][0].split("/")
    assert start == event.starts_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    assert end == (event.starts_at + timedelta(hours=1)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


# -- Who can post and remove -------------------------------------------------------
def test_posting_requires_sign_in(client, make_club):
    club = make_club()

    response = client.get(reverse("campus:club_event_new", args=[club.slug]))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_signed_out_club_page_invites_sign_in_and_comes_back(client, make_club):
    club = make_club()
    new_url = reverse("campus:club_event_new", args=[club.slug])

    html = client.get(reverse("campus:club_detail", args=[club.slug])).content.decode()

    assert "Sign in to post an event" in html
    assert f'{reverse("login")}?next={new_url}"' in html


def test_poster_can_remove_their_event(client, make_club):
    club, student = make_club(), make_student()
    event = make_event(club, posted_by=student)
    client.force_login(student)

    response = client.post(reverse("campus:club_event_delete", args=[club.slug, event.pk]))

    assert response.status_code == 302
    assert not ClubEvent.objects.filter(pk=event.pk).exists()


def test_other_students_cannot_remove_it(client, make_club):
    club = make_club()
    event = make_event(club, posted_by=make_student())
    client.force_login(make_student())

    response = client.post(reverse("campus:club_event_delete", args=[club.slug, event.pk]))

    assert response.status_code == 404
    assert ClubEvent.objects.filter(pk=event.pk).exists()


def test_remove_button_only_shows_to_the_poster(client, make_club):
    club, poster = make_club(), make_student()
    make_event(club, posted_by=poster)
    page = reverse("campus:club_detail", args=[club.slug])

    client.force_login(make_student())
    assert ">Remove<" not in client.get(page).content.decode()
    client.force_login(poster)
    assert ">Remove<" in client.get(page).content.decode()


def test_removing_requires_post_and_a_real_id(client, make_club):
    club = make_club()
    client.force_login(make_student())
    event = make_event(club)

    get = client.get(reverse("campus:club_event_delete", args=[club.slug, event.pk]))
    junk = client.post(reverse("campus:club_event_delete", args=[club.slug, "not-an-id"]))

    assert get.status_code == 405
    assert junk.status_code == 404


# -- Validation ---------------------------------------------------------------------
def test_events_in_the_past_are_rejected():
    form = ClubEventForm(
        data={
            "title": "Too late",
            "starts_at": local_input(timezone.now() - timedelta(hours=2)),
            "location": "Library",
        }
    )

    assert not form.is_valid()
    assert form.errors["starts_at"] == ["That time has already passed."]


def test_an_end_before_the_start_is_rejected():
    start = timezone.now() + timedelta(days=1)
    form = ClubEventForm(
        data={
            "title": "Backwards",
            "starts_at": local_input(start),
            "ends_at": local_input(start - timedelta(hours=1)),
            "location": "Library",
        }
    )

    assert not form.is_valid()
    assert form.errors["ends_at"] == ["The end has to be after the start."]


def test_events_more_than_a_year_out_are_rejected():
    form = ClubEventForm(
        data={
            "title": "Typo in the year",
            "starts_at": local_input(timezone.now() + timedelta(days=400)),
            "location": "Library",
        }
    )

    assert not form.is_valid()
    assert "up to a year ahead" in form.errors["starts_at"][0]


def test_a_rejected_post_saves_nothing(client, make_club):
    club = make_club()
    client.force_login(make_student())

    response = post_event(client, club, title="", location="")

    assert response.status_code == 200
    assert ClubEvent.objects.count() == 0


# -- Listing ------------------------------------------------------------------------
def test_finished_events_drop_off_and_running_ones_stay(make_club):
    club = make_club()
    make_event(club, title="Last week", starts_in=-timedelta(days=7))
    make_event(club, title="Ended an hour ago", starts_in=-timedelta(hours=3))
    make_event(
        club,
        title="Happening now",
        starts_in=-timedelta(minutes=30),
        ends_at=timezone.now() + timedelta(hours=1),
    )
    make_event(club, title="Next week", starts_in=timedelta(days=7))

    titles = [e.title for e in services.upcoming_events()]

    assert titles == ["Happening now", "Next week"]


def test_club_page_shows_only_that_clubs_events(client, make_club):
    chess, robotics = make_club("Chess Club"), make_club("Robotics Club")
    make_event(chess, title="Chess night")
    make_event(robotics, title="Robot build day")

    html = client.get(reverse("campus:club_detail", args=[chess.slug])).content.decode()

    assert "Chess night" in html
    assert "Robot build day" not in html


def test_events_page_groups_by_local_day_soonest_first(client, make_club):
    club = make_club()
    make_event(club, title="Later", starts_in=timedelta(days=5))
    make_event(club, title="Sooner", starts_in=timedelta(days=1))

    days = services.events_by_day(services.upcoming_events())

    assert [[e.title for e in events] for _, events in days] == [["Sooner"], ["Later"]]


def test_empty_events_page_says_how_to_add_one(client):
    html = client.get(reverse("campus:events")).content.decode()

    assert "No upcoming events yet" in html
    assert reverse("campus:clubs") in html
