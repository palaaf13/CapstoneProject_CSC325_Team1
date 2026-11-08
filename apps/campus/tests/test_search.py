"""
Club search: what matches, and what comes first.

The ranking exists because of two-letter searches. "ai" is the obvious thing to
type for the Artificial Intelligence Club, and as a plain substring it is also
inside "gain", "training" and "maintain" — which is most of the directory.
"""

import pytest

from apps.campus import services

pytestmark = pytest.mark.django_db


@pytest.fixture
def directory(make_club):
    make_club(
        "Artificial Intelligence Club",
        slug="cs",
        short_name="cs",
        summary="A club for students interested in CS and tech adjacent careers.",
    )
    make_club(
        "American Association of Airport Executives",
        short_name="AAAE",
        summary="A national professional organization for aviation administrators.",
    )
    make_club(
        "Accounting Society",
        summary="Gain industry insights, with training from professionals.",
    )
    make_club(
        "Cybersecurity Club",
        short_name="CSC",
        summary="Present and future computer security technologies.",
        description="We run workshops on AI safety and capture-the-flag events.",
    )
    make_club("Farmingdale Dance Team", summary="Knowledge and experience through dance.")
    make_club("Afro-Caribbean Dance Team", short_name="ACDT", summary="Performing at events.")
    make_club("Farmingdale Fusion", summary="Do you love to DANCE? Learn different styles.")
    make_club("Club Basketball", summary="One of Long Island's elite programs.")
    make_club(
        "Student Government Association Inc.",
        short_name="SGA",
        summary="The unified voice of the student body.",
    )
    make_club(
        "Society of Hispanic Professional Engineers",
        summary="Empowering the Hispanic community in STEM.",
    )


def search(q, **kwargs):
    return [club.name for club in services.search_clubs(q=q, **kwargs)]


# -- the searches from the bug report --------------------------------------
def test_ai_finds_the_ai_club_first_and_not_every_club_that_says_training(directory):
    assert search("ai") == [
        # "AI" is what the name shortens to once "Club" is dropped
        "Artificial Intelligence Club",
        # a word of the name starts with it
        "American Association of Airport Executives",
        # the whole word "AI" in its description
        "Cybersecurity Club",
    ]
    # "gain" and "training" contain "ai" and are not what anyone meant
    assert "Accounting Society" not in search("ai")


def test_dance_lists_the_dance_teams_before_a_club_that_only_mentions_dancing(directory):
    assert search("dance") == [
        "Afro-Caribbean Dance Team",
        "Farmingdale Dance Team",
        "Farmingdale Fusion",
    ]


@pytest.mark.parametrize("q", ["SGA", "sga", " sga "])
def test_an_abbreviation_finds_its_club(directory, q):
    assert search(q) == ["Student Government Association Inc."]


# -- what counts as a match ------------------------------------------------
def test_an_acronym_works_even_when_the_club_never_wrote_one_down(directory):
    """SHPE has no short name in this fixture; the initials skip the "of"."""
    assert search("shpe") == ["Society of Hispanic Professional Engineers"]


def test_a_stale_abbreviation_still_finds_its_club(directory):
    """RamCentral still has "cs" on the AI club. Wrong as a label, fine as a way in."""
    assert search("cs")[0] == "Artificial Intelligence Club"


def test_the_start_of_a_word_matches(directory):
    assert search("danc") == [
        "Afro-Caribbean Dance Team",
        "Farmingdale Dance Team",
        "Farmingdale Fusion",
    ]
    assert search("cyber") == ["Cybersecurity Club"]


def test_three_letters_or_more_can_match_inside_a_name(directory):
    assert search("ball") == ["Club Basketball"]


def test_two_letters_never_match_inside_a_word(directory):
    """ "an" is in "Dance", "Farmingdale", "American" and "organization"."""
    assert search("an") == []


def test_every_term_has_to_match(directory):
    assert search("hispanic engineers") == ["Society of Hispanic Professional Engineers"]
    assert search("dance engineers") == []


def test_punctuation_separates_words_on_both_sides(directory):
    assert search("afro-caribbean") == ["Afro-Caribbean Dance Team"]
    assert search("afro caribbean") == ["Afro-Caribbean Dance Team"]


def test_a_search_with_no_words_in_it_is_no_search(directory):
    assert len(search("  &  ")) == 10


# -- ranking ---------------------------------------------------------------
def test_a_name_match_outranks_a_summary_match_outranks_a_description_match(make_club):
    make_club("Zebra Robotics", summary="We build things.")
    make_club("Maker Club", summary="Robotics, electronics and 3D printing.")
    make_club("Alpha Club", summary="We meet weekly.", description="Sometimes we do robotics.")

    assert search("robotics") == ["Zebra Robotics", "Maker Club", "Alpha Club"]


def test_equal_matches_stay_alphabetical(make_club):
    for name in ("Chess Club", "Anime Club", "Book Club"):
        make_club(name)

    assert search("club") == ["Anime Club", "Book Club", "Chess Club"]


def test_search_respects_the_category(directory, make_club):
    make_club("Dance Marathon", categories=["Community Service"])

    assert search("dance", category="Community Service") == ["Dance Marathon"]
