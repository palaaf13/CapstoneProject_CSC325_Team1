"""Factory helpers for the moderation tests: people, and one of each reportable thing."""

import pytest
from django.contrib.auth import get_user_model

from apps.community import services as community
from apps.community.models import Post
from apps.ratings.models import CourseRating, ProfessorRating


@pytest.fixture
def make_user():
    def _make(username="student", **kwargs):
        kwargs.setdefault("email", f"{username}@farmingdale.edu")
        return get_user_model().objects.create_user(
            username=username, password="pw-12345!", **kwargs
        )

    return _make


@pytest.fixture
def author(make_user):
    return make_user("author")


@pytest.fixture
def reporter(make_user):
    return make_user("reporter")


@pytest.fixture
def post(author):
    return Post.objects.create(author=author, title="Selling my old textbooks, DM me")


@pytest.fixture
def comment(post, author):
    return community.add_comment(author, post, "Buy my notes, link in bio.")


@pytest.fixture
def course_rating(author, make_course):
    return CourseRating.objects.create(
        user=author,
        course=make_course(code="CSC 240"),
        difficulty=3,
        workload=3,
        usefulness=3,
        semester="Fall 2026",
        comment="Off-topic rant about parking.",
    )


@pytest.fixture
def professor_rating(author, make_professor):
    return ProfessorRating.objects.create(
        user=author,
        professor=make_professor(),
        clarity=3,
        helpfulness=3,
        fairness=3,
        semester="Fall 2026",
        comment="Something rude.",
    )
