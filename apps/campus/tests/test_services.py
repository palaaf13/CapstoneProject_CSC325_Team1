"""Club directory queries: the category filter, the category counts, and provenance."""

from datetime import date

import pytest

from apps.campus import services

pytestmark = pytest.mark.django_db


@pytest.fixture
def clubs(make_club):
    make_club(
        "Society of Hispanic Professional Engineers",
        short_name="SHPE",
        summary="Empowering the Hispanic community in STEM.",
        categories=["Academic", "Technology"],
    )
    make_club(
        "Farmingdale Dance Team",
        summary="Performs at games and campus events.",
        categories=["Club Sports", "Performing Arts"],
    )
    make_club("Gaming Club", summary="Video games and board games after class.")
    make_club("Sociology Club", summary="Talks about society and real life issues.")


def names(clubs):
    return [club.name for club in clubs]


# -- the directory with no search ------------------------------------------
def test_with_no_terms_everything_comes_back_in_order(clubs):
    assert names(services.search_clubs()) == [
        "Farmingdale Dance Team",
        "Gaming Club",
        "Society of Hispanic Professional Engineers",
        "Sociology Club",
    ]


# -- categories ------------------------------------------------------------
def test_category_filter_finds_clubs_filed_under_several(clubs):
    assert names(services.search_clubs(category="Performing Arts")) == ["Farmingdale Dance Team"]
    assert names(services.search_clubs(category="Club Sports")) == ["Farmingdale Dance Team"]


def test_category_filter_matches_whole_names_only(clubs):
    """ "Arts" is not a category, and must not match "Performing Arts"."""
    assert names(services.search_clubs(category="Arts")) == []


def test_search_and_category_combine(clubs):
    assert names(services.search_clubs(q="team", category="Performing Arts")) == [
        "Farmingdale Dance Team"
    ]
    assert names(services.search_clubs(q="gaming", category="Performing Arts")) == []


def test_category_counts_count_a_club_once_per_category(clubs):
    assert services.club_categories() == [
        ("Academic", 1),
        ("Club Sports", 1),
        ("Performing Arts", 1),
        ("Technology", 1),
        (services.OTHER, 2),
    ]


def test_category_counts_are_empty_without_clubs():
    assert services.club_categories() == []


# -- "Other": the clubs in no category --------------------------------------
def test_other_lists_exactly_the_clubs_with_no_category(clubs):
    """Without it a club RamCentral filed nowhere would appear under no filter at all."""
    assert names(services.search_clubs(category=services.OTHER)) == [
        "Gaming Club",
        "Sociology Club",
    ]


def test_other_combines_with_search(clubs):
    assert names(services.search_clubs(q="games", category=services.OTHER)) == ["Gaming Club"]
    assert names(services.search_clubs(q="dance", category=services.OTHER)) == []


def test_other_comes_last_and_only_when_some_club_needs_it(make_club):
    make_club("Zebra Club", categories=["Zoology"])
    assert services.club_categories() == [("Zoology", 1)]

    make_club("Quiet Club")
    assert services.club_categories() == [("Zoology", 1), (services.OTHER, 1)]


def test_every_club_is_reachable_through_some_filter(clubs):
    """Each club is in at least one named category, or it is in Other. Never neither."""
    reachable = set()
    for category, _ in services.club_categories():
        reachable.update(names(services.search_clubs(category=category)))

    assert reachable == set(names(services.search_clubs()))


# -- provenance ------------------------------------------------------------
def test_last_retrieved_is_the_newest_pull(make_club):
    make_club("Old Pull", source_retrieved=date(2026, 9, 1))
    make_club("New Pull", source_retrieved=date(2026, 10, 6))
    make_club("Never Pulled")

    assert services.last_retrieved() == date(2026, 10, 6)


def test_last_retrieved_is_none_without_clubs():
    assert services.last_retrieved() is None
