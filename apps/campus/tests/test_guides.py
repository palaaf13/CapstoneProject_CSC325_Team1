"""The Jobs, Parking, and Facilities guides: real facts, each linked to its source."""

import re

import pytest
from django.urls import reverse

from apps.campus.views import GUIDES_CHECKED

pytestmark = pytest.mark.django_db

GUIDES = {
    "campus:parking": [
        "https://farmingdale.t2hosted.com/Account/Portal",
        "https://www.farmingdale.edu/university-police/parking-and-traffic.shtml",
        "https://www.farmingdale.edu/university-police/parking-appeals.shtml",
    ],
    "campus:jobs": [
        "https://farmingdale-csm.symplicity.com/students",
        "https://www.farmingdale.edu/human-resources/student-employment.shtml",
        "https://www.farmingdale.edu/nexus-center/career-development.shtml",
    ],
    "campus:facilities": [
        "https://www.farmingdale.edu/library/hours.shtml",
        "https://farmingdalesports.com/sports/2023/6/8/facilities-hours.aspx",
        "https://www.farmingdale.edu/auxiliary-service-corporation/campus-dining.shtml",
        "https://farmingdale.campusdish.com",
    ],
}


@pytest.mark.parametrize("url_name, sources", GUIDES.items())
def test_each_guide_links_its_official_sources(client, url_name, sources):
    html = client.get(reverse(url_name)).content.decode()

    for source in sources:
        assert f'href="{source}"' in html, source


@pytest.mark.parametrize("url_name", GUIDES)
def test_each_guide_says_when_it_was_checked(client, url_name):
    html = client.get(reverse(url_name)).content.decode()

    assert f"checked {GUIDES_CHECKED:%b} {GUIDES_CHECKED.day}, {GUIDES_CHECKED.year}" in html
    assert "No lots listed yet" not in html and "No job postings yet" not in html


@pytest.mark.parametrize("url_name", GUIDES)
def test_official_links_open_safely_in_a_new_tab(client, url_name):
    html = client.get(reverse(url_name)).content.decode()

    for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', html):
        assert 'rel="noopener"' in tag, tag


def test_parking_states_the_rules_students_get_tickets_for(client):
    html = client.get(reverse("campus:parking")).content.decode()

    for fact in ("$35", "$150", "5 business days", "White lines", "midnight to 6"):
        assert fact in html, fact


def test_jobs_names_both_kinds_of_campus_job_and_the_i9_step(client):
    html = client.get(reverse("campus:jobs")).content.decode()

    for fact in ("Student Assistant", "College Work-Study", "I-9 appointment", "CareerConnect"):
        assert fact in html, fact


def test_facilities_shows_this_semesters_hours(client):
    html = client.get(reverse("campus:facilities")).content.decode()

    assert "Fall 2026 hours" in html
    assert "7:45&nbsp;am&ndash;11:00&nbsp;pm" in html  # library, Monday to Thursday
    assert "7:00&nbsp;am&ndash;10:00&nbsp;pm" in html  # fitness center, weekdays
