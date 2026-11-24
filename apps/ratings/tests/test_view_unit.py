"""Database-free integration checks for the course rating POST view."""

from types import SimpleNamespace
from unittest.mock import Mock

from django.test import RequestFactory
from django.urls import reverse

from apps.ratings import services, views
from apps.ratings.models import CourseRating


def make_request(*, authenticated=True):
    request = RequestFactory().post(
        "/courses/CSC-240/rate/",
        {
            "difficulty": "4",
            "workload": "3",
            "usefulness": "5",
            "semester": "Fall 2026",
        },
    )
    request.user = SimpleNamespace(is_authenticated=authenticated, pk="user-id")
    return request


def test_unauthenticated_course_rating_submission_redirects_to_login():
    response = views.course_rating_create(make_request(authenticated=False), "CSC-240")

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert "next=" in response.url


def test_valid_course_rating_submission_calls_service_and_redirects(monkeypatch):
    course = SimpleNamespace(slug="CSC-240")
    monkeypatch.setattr(views, "get_course_by_code", Mock(return_value=course))
    manager = Mock()
    manager.filter.return_value.exists.return_value = False
    monkeypatch.setattr(CourseRating, "objects", manager)
    submit = Mock()
    monkeypatch.setattr(views.services, "submit_course_rating_transactional", submit)
    success = Mock()
    monkeypatch.setattr(views.messages, "success", success)

    request = make_request()
    response = views.course_rating_create(request, "CSC-240")

    assert response.status_code == 302
    assert response.url == reverse("catalog:course_detail", args=[course.slug])
    submit.assert_called_once_with(
        user=request.user,
        course=course,
        difficulty=4,
        workload=3,
        usefulness=5,
        semester="Fall 2026",
    )
    success.assert_called_once()


def test_racing_duplicate_submission_shows_duplicate_message(monkeypatch):
    course = SimpleNamespace(slug="CSC-240")
    monkeypatch.setattr(views, "get_course_by_code", Mock(return_value=course))
    manager = Mock()
    manager.filter.return_value.exists.return_value = False
    monkeypatch.setattr(CourseRating, "objects", manager)
    submit = Mock(side_effect=services.CourseRatingAlreadyExists("duplicate"))
    monkeypatch.setattr(views.services, "submit_course_rating_transactional", submit)
    error = Mock()
    monkeypatch.setattr(views.messages, "error", error)

    response = views.course_rating_create(make_request(), "CSC-240")

    assert response.status_code == 302
    assert response.url == reverse("catalog:course_detail", args=[course.slug])
    submit.assert_called_once()
    error.assert_called_once()


def test_existing_rating_is_rejected_without_resubmitting(monkeypatch):
    course = SimpleNamespace(slug="CSC-240")
    monkeypatch.setattr(views, "get_course_by_code", Mock(return_value=course))
    manager = Mock()
    manager.filter.return_value.exists.return_value = True
    monkeypatch.setattr(CourseRating, "objects", manager)
    submit = Mock()
    monkeypatch.setattr(views.services, "submit_course_rating_transactional", submit)
    error = Mock()
    monkeypatch.setattr(views.messages, "error", error)

    response = views.course_rating_create(make_request(), "CSC-240")

    assert response.status_code == 302
    assert response.url == reverse("catalog:course_detail", args=[course.slug])
    submit.assert_not_called()
    error.assert_called_once()
