"""
Guards on the committed RamCentral export, apps/campus/seed_data/farmingdale_clubs.ndjson.

A refresh of that file is reviewed as a diff of a hundred JSON lines, which is
exactly where a stray field or a broken record slips through. These tests are
the review that always happens.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.validators import validate_slug

from apps.campus import services
from apps.campus.management.commands.import_clubs import (
    DATA_FILE,
    OFFICE_TYPES,
    RAMHUB_CATEGORIES,
    TYPE_CATEGORY,
)
from apps.campus.models import Club
from apps.campus.services import OTHER

# Every key the scraper is allowed to write. RamCentral's raw record holds more
# — notably `primaryContact`, a named student and their email — and none of it
# may reach a committed file.
EXPORT_FIELDS = {
    "slug", "name", "short_name", "summary", "description", "org_type", "categories",
    "status", "contact_email", "phone", "location", "website", "links", "logo_url",
    "ramcentral_id", "source_url", "source_modified", "source", "source_retrieved",
}  # fmt: skip


@pytest.fixture(scope="module")
def records() -> list[dict]:
    assert DATA_FILE.exists(), "the club export should be committed"
    lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_the_export_is_keyed_and_named(records):
    slugs = [record["slug"] for record in records]

    assert len(slugs) == len(set(slugs)), "duplicate slug"
    assert len(slugs) > 100
    for record in records:
        validate_slug(record["slug"])
        assert record["name"].strip(), f"{record['slug']} has no name"


def test_the_export_carries_no_officers(records):
    for record in records:
        assert set(record) <= EXPORT_FIELDS, f"{record['slug']} has an unexpected field"


def test_every_link_in_the_export_is_a_web_link(records):
    """They are rendered as hrefs, so nothing but http(s) may be in the file."""
    for record in records:
        urls = [record["website"], record["logo_url"], record["source_url"]]
        urls += list(record["links"].values())
        for url in filter(None, urls):
            assert url.startswith(("http://", "https://")), f"{record['slug']}: {url!r}"


# -- RamHub's own grouping (ramhub_categories.json) -------------------------
def test_every_club_ramhub_groups_is_a_club_in_the_export(records):
    """A club renamed or dropped on RamCentral must not leave a dead entry behind."""
    clubs = {r["slug"] for r in records if r["org_type"] not in OFFICE_TYPES}

    assert RAMHUB_CATEGORIES, "the grouping file should not be empty"
    assert set(RAMHUB_CATEGORIES) <= clubs, sorted(set(RAMHUB_CATEGORIES) - clubs)


def test_ramhub_never_reuses_one_of_ramcentrals_category_names(records):
    """
    If "Technology" were also a RamCentral category, nobody could tell which
    clubs the college filed there and which ones we did.
    """
    ramcentral = {name for record in records for name in record["categories"]}
    ramcentral |= set(TYPE_CATEGORY.values())
    ours = {name for names in RAMHUB_CATEGORIES.values() for name in names}

    assert ours == {"Technology"}
    assert not ours & ramcentral
    assert OTHER not in ours | ramcentral, '"Other" is the filter for clubs in no category'


# -- the export, imported ---------------------------------------------------
@pytest.mark.django_db
def test_importing_the_export_loads_the_directory():
    out = StringIO()
    call_command("import_clubs", stdout=out)

    assert Club.objects.count() > 100
    assert not Club.objects.filter(org_type="Offices / Departments").exists()
    assert not Club.objects.exclude(meeting_info="").exists()
    assert "No officers were imported" in out.getvalue()


@pytest.mark.django_db
def test_the_real_directory_supports_the_searches_students_try_first():
    """The bug report, against the real data: "ai", "dance" and "SGA" all find their club."""
    call_command("import_clubs", stdout=StringIO())

    def top(q):
        return [club.name for club in services.search_clubs(q=q)][:3]

    assert top("ai")[0] == "Artificial Intelligence Club"
    assert "Farmingdale Dance Team" in top("dance")
    assert top("SGA") == ["Student Government Association Inc."]


@pytest.mark.django_db
def test_the_real_directory_has_a_technology_filter_and_no_unreachable_club():
    call_command("import_clubs", stdout=StringIO())
    categories = dict(services.club_categories())

    technology = [club.name for club in services.search_clubs(category="Technology")]
    assert "Artificial Intelligence Club" in technology
    assert categories["Technology"] == len(technology) == len(RAMHUB_CATEGORIES)
    # every club is under a named category or under Other — never neither
    assert categories[OTHER] == Club.objects.filter(categories=[]).count() > 0
