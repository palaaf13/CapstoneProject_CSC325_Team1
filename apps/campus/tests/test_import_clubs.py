"""
The club import brings in real organizations. The rules it must not break:
never invent a meeting time, never import a person, never duplicate.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.campus.management.commands.import_clubs import (
    RAMHUB_CATEGORIES,
    categories_for,
    load_ramhub_categories,
    real_text,
)
from apps.campus.models import Club

pytestmark = pytest.mark.django_db


def row(slug, name, **extra):
    base = {
        "slug": slug,
        "name": name,
        "short_name": "",
        "summary": "A club for testing.",
        "description": "A club for testing.\n\nIt meets in the test suite.",
        "org_type": "Recognized Student Organizations",
        "categories": ["Academic"],
        "status": "Active",
        "contact_email": "club@farmingdale.edu",
        "phone": "934-420-2000",
        "location": "Quintyne Hall 118",
        "website": "https://example.org",
        "links": {
            "facebook": "https://www.facebook.com/club",
            "instagram": "https://www.instagram.com/club",
        },
        "logo_url": "https://se-images.campuslabs.com/clink/images/abc.png",
        "source_url": f"https://farmingdale.campuslabs.com/engage/organization/{slug}",
        "source_retrieved": "2026-10-06",
    }
    base.update(extra)
    return base


@pytest.fixture
def club_file(tmp_path):
    def _write(rows):
        path = tmp_path / "clubs.ndjson"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return str(path)

    return _write


def run_import(path, *args) -> str:
    out = StringIO()
    call_command("import_clubs", "--file", path, *args, stdout=out)
    return out.getvalue()


# -- the basics ------------------------------------------------------------
def test_import_creates_clubs(club_file):
    run_import(club_file([row("chess-club", "Chess Club", short_name="Chess")]))

    club = Club.objects.get(slug="chess-club")
    assert club.name == "Chess Club"
    assert club.short_name == "Chess"
    assert club.summary == "A club for testing."
    assert club.categories == ["Academic"]
    assert club.contact_email == "club@farmingdale.edu"
    assert club.location == "Quintyne Hall 118"
    assert club.website == "https://example.org"
    assert club.source_url.endswith("/organization/chess-club")
    assert str(club.source_retrieved) == "2026-10-06"


def test_links_are_stored_in_display_order_not_file_order(club_file):
    run_import(club_file([row("chess-club", "Chess Club")]))

    assert Club.objects.get(slug="chess-club").links == [
        "https://www.instagram.com/club",
        "https://www.facebook.com/club",
    ]


def test_import_is_idempotent(club_file):
    path = club_file([row("chess-club", "Chess Club")])

    run_import(path)
    run_import(path)

    assert Club.objects.filter(slug="chess-club").count() == 1


def test_import_updates_changed_facts(club_file):
    run_import(club_file([row("chess-club", "Chess Club")]))

    run_import(club_file([row("chess-club", "Chess & Checkers Club", location="Gleeson Hall")]))

    club = Club.objects.get(slug="chess-club")
    assert club.name == "Chess & Checkers Club"
    assert club.sort_name == "chess & checkers club"
    assert club.location == "Gleeson Hall"


# -- categories ------------------------------------------------------------
def test_a_browsable_type_becomes_a_category():
    """RamCentral types 14 clubs "Club Sports" but only gives 8 the category."""
    assert categories_for({"org_type": "Club Sports", "categories": []}) == ["Club Sports"]
    assert categories_for({"org_type": "Club Sports", "categories": ["Club Sports"]}) == [
        "Club Sports"
    ]


def test_the_three_greek_types_share_one_category():
    for org_type in ("Fraternities", "Sororities", "Panhellenic Sororities"):
        assert categories_for({"org_type": org_type}) == ["Fraternities & Sororities"]


def test_a_generic_type_adds_no_category():
    """A club RamCentral filed nowhere stays uncategorized rather than getting a guess."""
    assert categories_for({"org_type": "Recognized Student Organizations", "categories": []}) == []
    assert categories_for({"org_type": "Default", "categories": ["Academic"]}) == ["Academic"]


# -- RamHub's own grouping -------------------------------------------------
def test_ramhub_adds_technology_by_slug():
    """
    RamCentral has no technology category. ramhub_categories.json is the one
    place RamHub adds a grouping of its own, keyed by the club's slug.
    """
    assert RAMHUB_CATEGORIES["cs"] == ["Technology"]
    # the Artificial Intelligence Club: nothing from RamCentral, Technology from us
    assert categories_for({"slug": "cs", "categories": []}) == ["Technology"]
    # the Cybersecurity Club keeps RamCentral's categories alongside it
    assert categories_for({"slug": "csc", "categories": ["Academic", "Social Awareness"]}) == [
        "Academic",
        "Social Awareness",
        "Technology",
    ]


def test_ramhub_grouping_never_touches_a_club_it_does_not_name():
    assert categories_for({"slug": "chess-club", "categories": []}) == []
    assert categories_for({"slug": "", "categories": ["Academic"]}) == ["Academic"]


def test_the_grouping_file_notes_are_not_read_as_clubs(tmp_path):
    path = tmp_path / "grouping.json"
    path.write_text(
        json.dumps({"_meta": {"whose": "RamHub's"}, "chess-club": ["Games"]}), encoding="utf-8"
    )

    assert load_ramhub_categories(path) == {"chess-club": ["Games"]}


def test_import_stores_ramhub_categories_with_ramcentrals(club_file):
    run_import(club_file([row("ieee", "FSC IEEE Student Branch", categories=["Academic"])]))

    assert Club.objects.get(slug="ieee").categories == ["Academic", "Technology"]


# -- placeholder text ------------------------------------------------------
@pytest.mark.parametrize(
    "junk", ["PLEASE FILL THIS OUT", "xxx", ".", "...", "N/A", "**New for Fall 2026**", "   "]
)
def test_placeholder_text_is_stored_as_blank(club_file, junk):
    """RamCentral requires a summary, so clubs with nothing to say type something."""
    run_import(club_file([row("chess-club", "Chess Club", summary=junk, description=junk)]))

    club = Club.objects.get(slug="chess-club")
    assert club.summary == ""
    assert club.description == ""


@pytest.mark.parametrize(
    "text",
    [
        "New for fall 2026: we now meet twice a week.",
        "TBD Robotics builds combat robots.",
        "We play chess.",
    ],
)
def test_real_text_is_never_trimmed(text):
    """Placeholders are matched whole; a description that contains one is kept as written."""
    assert real_text(text) == text


# -- what is left out ------------------------------------------------------
def test_college_offices_are_skipped_unless_asked_for(club_file):
    path = club_file(
        [
            row("chess-club", "Chess Club"),
            row("res-life", "Residence Life", org_type="Offices / Departments"),
            row("branch", "Fraternities and Sororities", org_type="Branch"),
        ]
    )

    run_import(path)
    assert {c.slug for c in Club.objects.all()} == {"chess-club"}

    run_import(path, "--include-offices")
    assert Club.objects.count() == 3


def test_inactive_organizations_are_skipped(club_file):
    path = club_file(
        [row("chess-club", "Chess Club"), row("old-club", "Old Club", status="Frozen")]
    )

    run_import(path)

    assert {c.slug for c in Club.objects.all()} == {"chess-club"}


# -- the rules that matter most -------------------------------------------
def test_import_never_writes_a_meeting_time(club_file):
    """RamCentral publishes none, so the field stays empty rather than guessed."""
    run_import(club_file([row("chess-club", "Chess Club", meeting_info="Tuesdays at 11")]))

    assert Club.objects.get(slug="chess-club").meeting_info == ""


def test_reimport_preserves_meeting_info_added_elsewhere(club_file):
    path = club_file([row("chess-club", "Chess Club")])
    run_import(path)
    Club.objects.filter(slug="chess-club").update(meeting_info="Tuesdays at 11, Gleeson 104")

    run_import(path)

    assert Club.objects.get(slug="chess-club").meeting_info == "Tuesdays at 11, Gleeson 104"


def test_import_never_stores_a_person(club_file):
    """
    RamCentral's raw record names a student as primary contact, and its public
    page hides that behind a sign-in. Even if a row carried it, nothing on Club
    could hold it.
    """
    officer = {"firstName": "Ada", "lastName": "Lovelace", "primaryEmailAddress": "lovea@x.edu"}
    run_import(club_file([row("chess-club", "Chess Club", primaryContact=officer)]))

    club = Club.objects.get(slug="chess-club")
    stored = json.dumps({f.name: str(getattr(club, f.name)) for f in Club._meta.fields})
    assert "Lovelace" not in stored
    assert "lovea@x.edu" not in stored


def test_only_web_links_are_stored(club_file):
    """
    These values end up in an href and nothing validates them on save, so a
    script URL in a hand-edited export has to be dropped at the door.
    """
    path = club_file(
        [
            row(
                "chess-club",
                "Chess Club",
                website="javascript:alert(1)",
                source_url="data:text/html,<script>alert(1)</script>",
                links={"instagram": "JavaScript:alert(1)", "facebook": "https://facebook.com/c"},
            )
        ]
    )

    run_import(path)

    club = Club.objects.get(slug="chess-club")
    assert club.website == ""
    assert club.source_url == ""
    assert club.links == ["https://facebook.com/c"]


# -- failure modes ---------------------------------------------------------
def test_missing_file_is_a_clean_error():
    with pytest.raises(CommandError, match="not found"):
        run_import("/tmp/does-not-exist.ndjson")


def test_malformed_json_names_the_line(tmp_path):
    path = tmp_path / "bad.ndjson"
    path.write_text(json.dumps(row("ok", "Ok Club")) + "\nnot json\n", encoding="utf-8")

    with pytest.raises(CommandError, match=":2"):
        run_import(str(path))


def test_duplicate_slugs_are_rejected(club_file):
    path = club_file([row("chess-club", "Chess Club"), row("chess-club", "Chess Club")])

    with pytest.raises(CommandError, match="repeats slug"):
        run_import(path)


@pytest.mark.parametrize("slug", ["chess/club", "chess club", "../admin"])
def test_a_slug_that_cannot_be_a_url_is_rejected(club_file, slug):
    """The slug is the club's URL; one that will not reverse would 500 the directory."""
    with pytest.raises(CommandError, match="not URL-safe"):
        run_import(club_file([row(slug, "Chess Club")]))

    assert not Club.objects.exists()


def test_a_row_without_a_name_is_rejected(club_file):
    with pytest.raises(CommandError, match="no name"):
        run_import(club_file([row("chess-club", "")]))


def test_prune_refuses_without_confirmation(club_file, make_club):
    make_club("Old Club")
    path = club_file([row("chess-club", "Chess Club")])

    with pytest.raises(CommandError, match="--yes"):
        run_import(path, "--prune")

    assert Club.objects.filter(slug="old-club").exists()


def test_prune_with_yes_removes_clubs_not_in_the_export(club_file, make_club):
    make_club("Old Club")
    path = club_file([row("chess-club", "Chess Club")])

    run_import(path, "--prune", "--yes")

    assert {c.slug for c in Club.objects.all()} == {"chess-club"}
