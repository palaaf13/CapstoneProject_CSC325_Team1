"""Global search: the nav's search box, across courses, professors, and clubs."""

import pytest
from django.urls import reverse
from django.utils.text import slugify

from apps.campus.models import Club
from config.search import PREVIEW, site_search

pytestmark = pytest.mark.django_db


def make_club(name: str, **kwargs) -> Club:
    kwargs.setdefault("slug", slugify(name))
    kwargs.setdefault("org_type", "Recognized Student Organizations")
    return Club.objects.create(name=name, **kwargs)


def search(client, q: str):
    return client.get(reverse("search"), {"q": q})


# -- The service ---------------------------------------------------------------
def test_empty_query_searches_nothing(make_course):
    make_course(code="CSC 325", title="Software Engineering")
    assert site_search("") == []
    assert site_search("   ") == []


def test_matches_each_directory_with_its_own_rules(make_course, make_professor):
    make_course(code="CSC 240", title="Data Structures")
    make_professor(first_name="Marisol", last_name="Reyes")
    make_club("Computer Science Club")

    # "csc240" only matches because the course directory normalises codes.
    assert [s.key for s in site_search("csc240")] == ["courses"]
    assert [s.key for s in site_search("reyes")] == ["professors"]
    assert [s.key for s in site_search("computer science club")] == ["clubs"]


def test_sections_preview_a_few_and_link_to_the_full_directory(make_course):
    for number in range(PREVIEW + 3):
        make_course(code=f"BIO {100 + number}", title=f"Biology Topic {number}")

    (courses,) = site_search("biology")

    assert courses.total == PREVIEW + 3
    assert len(courses.results) == PREVIEW
    assert courses.see_all_url == f"{reverse('catalog:courses')}?q=biology"


# -- The page ------------------------------------------------------------------
def test_page_without_a_query_invites_a_search(client):
    response = client.get(reverse("search"))

    assert response.status_code == 200
    assert b"Search RamHub" in response.content
    assert b'name="q"' in response.content


def test_results_link_to_each_detail_page(client, make_course, make_professor):
    course = make_course(code="CSC 325", title="Software Engineering")
    professor = make_professor(first_name="Ada", last_name="Softworth")
    club = make_club("Software Engineering Society")

    html = search(client, "software").content.decode()

    assert reverse("catalog:course_detail", args=[course.slug]) in html
    assert reverse("campus:club_detail", args=[club.slug]) in html
    assert reverse("catalog:professor_detail", args=[professor.slug]) not in html  # no name match
    assert "Results for &ldquo;software&rdquo;" in html


def test_see_all_appears_only_when_there_are_more(client, make_course):
    for number in range(PREVIEW + 1):
        make_course(code=f"MTH {200 + number}", title=f"Calculus Part {number}")

    html = search(client, "calculus").content.decode()

    assert f"See all {PREVIEW + 1} courses" in html
    assert f"{reverse('catalog:courses')}?q=calculus" in html


def test_no_matches_shows_an_empty_state_not_a_blank_page(client, make_course):
    make_course(code="CSC 325", title="Software Engineering")

    html = search(client, "zzzz-nothing").content.decode()

    assert "Nothing matched that search" in html
    assert "No matches" in html


def test_an_overlong_query_is_ignored_safely(client):
    response = search(client, "x" * 500)

    assert response.status_code == 200
    assert b"Search RamHub" in response.content


def test_the_query_is_escaped(client):
    html = search(client, "<script>alert(1)</script>").content.decode()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# -- The nav -------------------------------------------------------------------
def test_every_nav_search_box_submits_to_the_search_page(client):
    html = client.get(reverse("about")).content.decode()

    assert html.count(f'action="{reverse("search")}"') == 2  # desktop and mobile
    assert 'action="#"' not in html


def test_nav_search_box_keeps_the_query_on_the_results_page(client):
    html = search(client, "biology").content.decode()

    assert 'value="biology"' in html


def test_courses_are_ranked_by_relevance_not_code(make_course):
    make_course(code="AET 150", title="Automotive Computer Applications")
    make_course(code="CSC 101", title="Computer Science I")
    make_course(code="BCS 102", title="Concepts of Computers")  # no whole-word match

    (courses,) = site_search("computer science")
    assert [c.code for c in courses.results] == ["CSC 101"]

    (courses,) = site_search("computer")
    assert [c.code for c in courses.results] == ["CSC 101", "AET 150", "BCS 102"]


def test_an_exact_course_code_comes_first(make_course):
    make_course(code="CSC 325", title="Software Engineering")
    make_course(code="CSC 101", title="Computer Science I")

    (courses,) = site_search("csc 325")
    assert courses.results[0].code == "CSC 325"


def test_a_longer_word_is_not_a_whole_word_match(make_course):
    make_course(code="AET 255", title="Computerized Engine Controls")
    make_course(code="BCS 102", title="Computer Concepts and Applications")

    (courses,) = site_search("computer")
    assert [c.code for c in courses.results] == ["BCS 102", "AET 255"]
