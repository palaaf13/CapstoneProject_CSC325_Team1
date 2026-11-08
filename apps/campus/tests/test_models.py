"""Club: the derived values the templates lean on."""

import pytest

from apps.campus.models import MONOGRAM_TONES, Club, link_display, link_label


# -- monogram --------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "short_name", "expected"),
    [
        # The club's own abbreviation wins when it has a short one.
        ("Student Government Association Inc.", "SGA", "SGA"),
        ("Society of Hispanic Professional Engineers", "shpe", "SHPE"),
        # Otherwise initials, skipping the little words.
        ("Society of Hispanic Professional Engineers", "", "SHPE"),
        ("Gaming Club", "Gaming Club", "GC"),
        ("Art & Design Club", "", "ADC"),
        ("Cooks 'N' Crooks", "Cooks", "CC"),
        ("Afro-Caribbean Club", "", "ACC"),
        # Never more than four letters, so it always fits the tile.
        ("Women in Aviation International - FSC Chapter", "", "WAIF"),
        # A name made only of little words still gets something.
        ("The", "", "T"),
        # An abbreviation left over from before a rename is not trusted:
        # RamCentral still has "cs" on the Artificial Intelligence Club.
        ("Artificial Intelligence Club", "cs", "AIC"),
        # Greek letters are, though they never match the spelled-out name.
        ("Kappa Sigma Fraternity", "ΚΣ", "ΚΣ"),
        ("Alpha Sigma Phi Fraternity", "AΣΦ", "AΣΦ"),
    ],
)
def test_monogram(name, short_name, expected):
    assert Club(name=name, short_name=short_name).monogram == expected


def test_monogram_tone_is_stable_and_in_range():
    club = Club(name="Gaming Club", slug="gaming-club")

    assert club.monogram_tone == Club(name="Renamed", slug="gaming-club").monogram_tone
    assert 1 <= club.monogram_tone <= MONOGRAM_TONES


# -- links -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "label", "display"),
    [
        ("https://www.instagram.com/fsc.sga/", "Instagram", "instagram.com/fsc.sga"),
        ("https://web.groupme.com/join_group/1/abc", "GroupMe", "groupme.com/join_group/1/abc"),
        ("https://discord.gg/YuTGvQx", "Discord", "discord.gg/YuTGvQx"),
        # Anything else is just the club's website.
        ("https://www.asme.org", "Website", "asme.org"),
    ],
)
def test_links_are_named_by_where_they_go(url, label, display):
    assert link_label(url) == label
    assert link_display(url) == display


def test_link_items_put_the_website_first():
    club = Club(
        name="Chess Club",
        website="https://chess.example.org",
        links=["https://www.instagram.com/chess/"],
    )

    assert [item["label"] for item in club.link_items] == ["Website", "Instagram"]


def test_channels_list_each_way_to_reach_a_club_once():
    club = Club(
        name="Chess Club",
        contact_email="chess@farmingdale.edu",
        links=["https://www.instagram.com/chess/", "https://www.instagram.com/chess2/"],
    )

    assert club.channels == ["Instagram", "Email"]


def test_a_club_with_no_contact_details_has_no_channels():
    assert Club(name="Chess Club").channels == []


# -- abbreviation ----------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "short_name", "expected"),
    [
        ("Student Government Association Inc.", "SGA", "SGA"),
        ("Cooks 'N' Crooks", "Culinary", "Culinary"),
        # nothing to add when it only repeats the name
        ("Best Buddies", "Best Buddies", ""),
        ("Biology Club", "", ""),
        # left over from before a rename: not shown beside the new name
        ("Artificial Intelligence Club", "cs", ""),
        ("RamChella Committee", "Concert", ""),
        # Greek letters never share a first letter with the spelled-out name
        ("Kappa Sigma Fraternity", "ΚΣ", "ΚΣ"),
    ],
)
def test_abbreviation_is_only_shown_when_it_fits_the_name(name, short_name, expected):
    assert Club(name=name, short_name=short_name).abbreviation == expected


# -- labels ----------------------------------------------------------------
def test_type_label_is_singular_and_hides_ramcentral_housekeeping():
    assert Club(org_type="Fraternities").type_label == "Fraternity"
    assert Club(org_type="Default").type_label == ""
    assert Club(org_type="").type_label == ""


def test_about_falls_back_to_the_summary():
    assert Club(summary="Short.", description="The long version.").about == "The long version."
    assert Club(summary="Short.", description="").about == "Short."


def test_blurb_falls_back_to_the_description():
    """A card still says something about a club whose summary was a placeholder."""
    assert Club(summary="Short.", description="The long version.").blurb == "Short."
    assert Club(summary="", description="The long version.").blurb == "The long version."
    assert Club().blurb == ""


# -- ordering --------------------------------------------------------------
@pytest.mark.django_db
def test_clubs_sort_alphabetically_regardless_of_case(make_club):
    """
    MongoDB orders by code point, so a plain name sort files every capital
    before any lowercase letter: "FSC Music Club" ahead of "Farmingdale Car Club".
    """
    make_club("FSC Music Club")
    make_club("Farmingdale Car Club")
    make_club("art & Design Club")

    assert [club.name for club in Club.objects.all()] == [
        "art & Design Club",
        "Farmingdale Car Club",
        "FSC Music Club",
    ]


@pytest.mark.django_db
def test_renaming_a_club_through_update_or_create_moves_it_in_the_sort(make_club):
    """update_or_create saves only the fields it is given; sort_name must follow name."""
    make_club("Zebra Club", slug="the-club")

    Club.objects.update_or_create(slug="the-club", defaults={"name": "Aardvark Club"})

    assert Club.objects.get(slug="the-club").sort_name == "aardvark club"
