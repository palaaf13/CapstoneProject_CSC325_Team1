"""The club directory and the club page, including the HTMX paths."""

import re

import pytest
from django.urls import reverse

from apps.campus.services import PAGE_SIZE

pytestmark = pytest.mark.django_db

CLUBS_URL = reverse("campus:clubs")


def ticked_categories(response) -> list[bytes]:
    """The value of every checked category radio in a rendered directory page."""
    return re.findall(rb'<input type="radio"[^>]*value="([^"]*)"[^>]*checked', response.content)


@pytest.fixture
def clubs(make_club):
    shpe = make_club(
        "Society of Hispanic Professional Engineers",
        slug="shpe",
        short_name="SHPE",
        summary="Empowering the Hispanic community in STEM.",
        description="We run workshops.\n\nJoin our Discord: https://discord.gg/abc123",
        categories=["Academic"],
        contact_email="shpe@farmingdale.edu",
        location="Lupton Hall 240",
        website="https://shpe.org",
        links=["https://www.instagram.com/shpe.fsc/"],
        source_url="https://farmingdale.campuslabs.com/engage/organization/shpe",
    )
    dance = make_club(
        "Farmingdale Dance Team",
        summary="Performs at games and campus events.",
        org_type="Club Sports",
        categories=["Club Sports", "Performing Arts"],
    )
    return shpe, dance


# -- directory -------------------------------------------------------------
def test_directory_lists_clubs(client, clubs):
    response = client.get(CLUBS_URL)

    assert response.status_code == 200
    assert b"Society of Hispanic Professional Engineers" in response.content
    assert b"Farmingdale Dance Team" in response.content
    assert response.context["club_count"] == 2


def test_directory_renders_an_empty_state_before_the_import(client):
    """A fresh clone must not crash, and must not show a filter with nothing to filter."""
    response = client.get(CLUBS_URL)

    assert response.status_code == 200
    assert b"No clubs listed yet" in response.content
    assert b'id="club-filter"' not in response.content


def test_directory_says_where_the_listings_come_from(client, clubs):
    """This is the college's data, not ours, and RamHub is not where you join."""
    body = client.get(CLUBS_URL).content

    assert b"RamCentral" in body
    assert b"farmingdale.campuslabs.com/engage/organizations" in body


def test_directory_offers_every_category_with_its_count(client, clubs):
    response = client.get(CLUBS_URL)

    assert response.context["categories"] == [
        ("Academic", 1),
        ("Club Sports", 1),
        ("Performing Arts", 1),
    ]
    assert b'value="Performing Arts"' in response.content


def test_search_narrows_the_results(client, clubs):
    response = client.get(CLUBS_URL, {"q": "shpe"})

    assert [c.slug for c in response.context["page_obj"]] == ["shpe"]


def test_category_filter_is_applied_and_ticked(client, clubs):
    response = client.get(CLUBS_URL, {"category": "Performing Arts"})

    assert [c.name for c in response.context["page_obj"]] == ["Farmingdale Dance Team"]
    assert ticked_categories(response) == [b"Performing Arts"]


def test_all_clubs_is_ticked_when_no_category_is_chosen(client, clubs):
    assert ticked_categories(client.get(CLUBS_URL)) == [b""]


def test_other_filter_lists_the_clubs_in_no_category(client, clubs, make_club):
    """Otherwise a club RamCentral filed nowhere would be reachable only by scrolling."""
    make_club("Sociology Club")

    response = client.get(CLUBS_URL, {"category": "Other"})

    assert response.context["categories"][-1] == ("Other", 1)
    assert [c.name for c in response.context["page_obj"]] == ["Sociology Club"]
    assert ticked_categories(response) == [b"Other"]
    assert b"1 club in no category" in response.content


def test_other_is_not_offered_when_every_club_has_a_category(client, clubs):
    response = client.get(CLUBS_URL)

    assert b'value="Other"' not in response.content
    # and asking for it anyway falls back to the whole directory
    assert len(client.get(CLUBS_URL, {"category": "Other"}).context["page_obj"].object_list) == 2


def test_the_demo_path_from_a_category_to_a_club_page(client, make_club):
    """Clubs -> Technology -> Artificial Intelligence Club -> its page."""
    make_club("Artificial Intelligence Club", slug="cs", short_name="cs", categories=["Technology"])
    make_club("Chess Club")

    directory = client.get(CLUBS_URL, {"category": "Technology"})
    detail_url = reverse("campus:club_detail", args=["cs"])

    assert [c.name for c in directory.context["page_obj"]] == ["Artificial Intelligence Club"]
    assert detail_url.encode() in directory.content
    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert b"Artificial Intelligence Club" in detail.content
    assert b"/clubs/?category=Technology" in detail.content


def test_search_ranks_the_best_match_first(client, make_club):
    """ "ai" has to lead with the AI club, not with whatever sorts first."""
    make_club("Accounting Society", summary="Gain insights and training.")
    make_club("Aikido Club")
    make_club("Zeta AI Society", summary="Machine learning.")

    response = client.get(CLUBS_URL, {"q": "ai"})

    assert [c.name for c in response.context["page_obj"]] == ["Zeta AI Society", "Aikido Club"]


def test_search_with_no_matches_renders_the_empty_state(client, clubs):
    response = client.get(CLUBS_URL, {"q": "zzzznomatch"})

    assert response.status_code == 200
    assert b"No clubs match that search" in response.content
    assert b"Clear search and filters" in response.content


def test_categories_that_do_not_exist_are_ignored_rather_than_erroring(client, clubs):
    """A stale bookmark should show the full directory, not a 400."""
    response = client.get(CLUBS_URL, {"category": "Astrology"})

    assert response.status_code == 200
    assert len(response.context["page_obj"].object_list) == 2


@pytest.mark.parametrize("params", [{"page": "abc"}, {"page": "-5"}, {"q": "x" * 500}])
def test_bad_query_parameters_degrade_instead_of_failing(client, clubs, params):
    assert client.get(CLUBS_URL, params).status_code == 200


def test_club_text_is_escaped(client, make_club):
    """Names and blurbs are free text typed by students on another site."""
    make_club("<script>alert(1)</script>", slug="x", summary="<img src=x onerror=alert(1)>")

    body = client.get(CLUBS_URL).content

    assert b"<script>alert(1)</script>" not in body
    assert b"<img src=x" not in body


# -- HTMX ------------------------------------------------------------------
def test_htmx_search_returns_only_the_results_region(client, clubs):
    response = client.get(CLUBS_URL, {"q": "dance"}, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert b"<html" not in response.content
    assert b'id="club-results"' in response.content
    assert b"Farmingdale Dance Team" in response.content
    assert b'id="club-filter"' not in response.content


def test_htmx_append_returns_only_cards(client, clubs):
    """ "Load more" must not send the results wrapper, or it would nest."""
    response = client.get(CLUBS_URL, {"page": "1", "append": "1"}, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert b'id="club-results"' not in response.content
    assert b"Farmingdale Dance Team" in response.content


def test_a_plain_request_still_returns_the_whole_page(client, clubs):
    """The directory has to work with JavaScript off."""
    response = client.get(CLUBS_URL, {"q": "dance"})

    assert b"<html" in response.content
    assert b'id="club-results"' in response.content
    assert b"<noscript>" in response.content


def test_a_history_restore_gets_the_whole_page_not_a_fragment(client, clubs):
    """
    When the back button lands on a URL htmx holds no snapshot for, it re-requests
    it with HX-Request set and swaps the response into <body>. A fragment there
    would replace the entire page with a list of cards.
    """
    response = client.get(
        CLUBS_URL,
        {"category": "Academic"},
        headers={"HX-Request": "true", "HX-History-Restore-Request": "true"},
    )

    assert b"<html" in response.content
    assert b'id="club-filter"' in response.content


def test_pagination_splits_at_the_page_size(client, make_club):
    for i in range(PAGE_SIZE + 5):
        make_club(f"Club {i:02d}")

    first = client.get(CLUBS_URL)
    assert first.context["total"] == PAGE_SIZE + 5
    assert len(first.context["page_obj"].object_list) == PAGE_SIZE
    assert first.context["next_page_url"] is not None

    second = client.get(CLUBS_URL, {"page": "2"})
    assert len(second.context["page_obj"].object_list) == 5
    assert second.context["next_page_url"] is None


def test_next_page_url_keeps_the_current_search_and_category(client, make_club):
    for i in range(PAGE_SIZE + 5):
        make_club(f"Robotics Club {i:02d}", categories=["Academic"])

    response = client.get(CLUBS_URL, {"q": "robotics", "category": "Academic"})

    next_url = response.context["next_page_url"]
    assert "q=robotics" in next_url
    assert "category=Academic" in next_url
    assert "page=2" in next_url


# -- club page -------------------------------------------------------------
def test_club_page_shows_what_ramcentral_publishes(client, clubs):
    response = client.get(reverse("campus:club_detail", args=["shpe"]))
    body = response.content

    assert response.status_code == 200
    assert b"Society of Hispanic Professional Engineers" in body
    assert b"We run workshops." in body
    assert b"mailto:shpe@farmingdale.edu" in body
    assert b"Lupton Hall 240" in body
    assert b"instagram.com/shpe.fsc" in body
    # and links back to the source, which is where a student actually joins
    assert b"https://farmingdale.campuslabs.com/engage/organization/shpe" in body
    assert b"View on RamCentral" in body


def test_club_page_links_urls_inside_the_description(client, clubs):
    body = client.get(reverse("campus:club_detail", args=["shpe"])).content

    assert b'<a href="https://discord.gg/abc123"' in body


def test_club_page_escapes_the_description_before_linking_it(client, make_club):
    make_club("Chess Club", description='<script>alert(1)</script> see "https://x.org"')

    body = client.get(reverse("campus:club_detail", args=["chess-club"])).content

    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;" in body


def test_club_page_does_not_invent_a_meeting_time(client, clubs):
    """RamCentral publishes none; the page says so and points at the source."""
    body = client.get(reverse("campus:club_detail", args=["shpe"])).content

    assert b"does not list a regular meeting time" in body


def test_club_page_category_links_filter_the_directory(client, clubs):
    body = client.get(reverse("campus:club_detail", args=["farmingdale-dance-team"])).content

    assert b"/clubs/?category=Performing%20Arts" in body
    assert b"Club sport" in body


def test_club_page_copes_with_a_club_that_published_nothing(client, make_club):
    make_club("Quiet Club", org_type="Default")

    body = client.get(reverse("campus:club_detail", args=["quiet-club"])).content

    assert b"Quiet Club" in body
    assert b"has not written a description" in body
    assert b"lists no contact details" in body


def test_unknown_club_404s(client, clubs):
    assert client.get("/clubs/no-such-club/").status_code == 404


def test_club_page_keeps_the_clubs_tab_active(client, clubs):
    response = client.get(reverse("campus:club_detail", args=["shpe"]))

    tabs = {t["label"]: t["is_active"] for t in response.context["nav_tabs"]}
    assert tabs["Clubs"] is True
    assert sum(tabs.values()) == 1


def test_club_pages_stay_on_htmx_and_vanilla_js(client, clubs):
    """The landing page's motion libraries must not leak into the directories."""
    for url in (CLUBS_URL, reverse("campus:club_detail", args=["shpe"])):
        body = client.get(url).content
        assert b"gsap" not in body and b"lenis" not in body, url
