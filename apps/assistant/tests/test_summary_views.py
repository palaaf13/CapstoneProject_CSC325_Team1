"""The summary box on course and professor pages, including the fallback path.
The AI is always mocked."""

import pytest
from django.urls import reverse

from apps.assistant import services
from apps.assistant.models import ReviewSummaryCache
from apps.ratings import services as ratings
from apps.ratings.forms import recent_semesters

from .fakes import TIMEOUT, FakeClient, response

pytestmark = pytest.mark.django_db

SEMESTER = recent_semesters()[0]
COMMENTS = [
    "Super useful for later CS classes.",
    "Useful, but the weekly labs take forever.",
    "Workload is heavy every single week.",
]


@pytest.fixture
def ai(settings, monkeypatch):
    """Turn the AI on with a fake client. ai.client.results controls what it returns."""
    settings.ANTHROPIC_API_KEY = "test-key-not-real"
    holder = FakeClient(response())
    monkeypatch.setattr(services, "get_client", lambda: holder)
    return holder


@pytest.fixture
def rated_course(make_course, make_student):
    course = make_course(code="CSC 240", title="Data Structures")
    for i, comment in enumerate(COMMENTS):
        ratings.rate_course(
            user=make_student(f"s{i}"),
            course=course,
            difficulty=4,
            workload=5,
            usefulness=5,
            semester=SEMESTER,
            comment=comment,
        )
    course.refresh_from_db()
    return course


def summary_url(course):
    return reverse("assistant:course_summary", kwargs={"code": course.slug})


def test_course_page_has_the_summary_slot_once_there_are_enough_reviews(client, rated_course):
    page = client.get(reverse("catalog:course_detail", kwargs={"code": "CSC-240"}))
    assert b'data-testid="ai-summary-slot"' in page.content
    assert summary_url(rated_course).encode() in page.content


def test_no_slot_with_fewer_than_three_reviews(client, make_course, make_student):
    course = make_course(code="CSC 240")
    ratings.rate_course(
        user=make_student(),
        course=course,
        difficulty=1,
        workload=1,
        usefulness=1,
        semester=SEMESTER,
        comment="Only one review so far.",
    )
    page = client.get(reverse("catalog:course_detail", kwargs={"code": "CSC-240"}))
    assert b"ai-summary-slot" not in page.content


def test_summary_renders_from_a_mocked_ai_response(client, ai, rated_course):
    body = client.get(summary_url(rated_course)).content
    assert b'data-testid="ai-summary"' in body
    assert b"Students say the workload is heavy but the course is worth it." in body
    assert b"Very useful for later courses" in body
    assert b"AI summary of 3 reviews" in body
    # The reviews went to the (fake) model as data, newest first.
    sent = ai.calls[0]["messages"][0]["content"]
    assert all(comment in sent for comment in COMMENTS)


def test_summary_is_cached_until_the_reviews_change(client, ai, rated_course, make_student):
    client.get(summary_url(rated_course))
    client.get(summary_url(rated_course))
    assert len(ai.calls) == 1
    assert ReviewSummaryCache.objects.count() == 1

    ratings.rate_course(
        user=make_student("late"),
        course=rated_course,
        difficulty=2,
        workload=2,
        usefulness=5,
        semester=SEMESTER,
        comment="Easier once you get recursion.",
    )
    client.get(summary_url(rated_course))
    assert len(ai.calls) == 2


def test_fallback_when_the_ai_times_out(client, ai, rated_course):
    ai.results = [TIMEOUT]
    response_ = client.get(summary_url(rated_course))

    assert response_.status_code == 200
    body = response_.content
    assert b'data-testid="ai-summary-fallback"' in body
    assert b'data-reason="timeout"' in body
    assert b"Summary unavailable right now" in body
    # The non-AI fallback: the real averages, in words.
    assert b"From 3 student ratings: difficulty 4.0/5, workload 5.0/5, usefulness 5.0/5." in body
    assert not ReviewSummaryCache.objects.exists()  # failures are not cached


def test_fallback_when_the_ai_returns_invalid_output(client, ai, rated_course):
    ai.results = [response(text="I think students mostly like it!")]
    body = client.get(summary_url(rated_course)).content
    assert b'data-reason="invalid_output"' in body
    assert b"I think students mostly like it" not in body


def test_fallback_when_no_api_key_is_configured(client, rated_course):
    body = client.get(summary_url(rated_course)).content
    assert b'data-reason="ai_disabled"' in body


def test_course_page_itself_never_calls_the_ai(client, ai, rated_course):
    client.get(reverse("catalog:course_detail", kwargs={"code": "CSC-240"}))
    assert ai.calls == []


def test_professor_summary_and_fallback(client, ai, make_professor, make_student):
    professor = make_professor()
    for i, comment in enumerate(COMMENTS):
        ratings.rate_professor(
            user=make_student(f"p{i}"),
            professor=professor,
            clarity=5,
            helpfulness=4,
            fairness=3,
            semester=SEMESTER,
            comment=comment,
        )
    url = reverse("assistant:professor_summary", kwargs={"slug": professor.slug})
    assert b'data-testid="ai-summary"' in client.get(url).content

    ReviewSummaryCache.objects.all().delete()
    ai.results = [TIMEOUT]
    body = client.get(url).content
    assert b"clarity 5.0/5, helpfulness 4.0/5, fairness 3.0/5" in body


def test_unit_tests_cannot_build_a_real_client(settings):
    settings.ANTHROPIC_API_KEY = "would-be-real"
    with pytest.raises(AssertionError, match="mocked AI response"):
        services.get_client()


def test_get_client_is_none_without_a_key_or_when_disabled(settings):
    settings.ANTHROPIC_API_KEY = ""
    assert services.get_client() is None
    settings.ANTHROPIC_API_KEY = "x"
    settings.AI_SUMMARIES_ENABLED = False
    assert services.get_client() is None
