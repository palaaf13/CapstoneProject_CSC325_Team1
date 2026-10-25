"""Factory helpers for the community tests."""

import pytest
from django.contrib.auth import get_user_model

from apps.community.models import Post


@pytest.fixture
def make_user():
    def _make(username="student", **kwargs):
        kwargs.setdefault("email", f"{username}@farmingdale.edu")
        return get_user_model().objects.create_user(
            username=username, password="pw-12345!", **kwargs
        )

    return _make


@pytest.fixture
def make_post(make_user):
    def _make(title="Study group for CSC 325?", author=None, **kwargs):
        author = author or make_user(f"author{Post.objects.count()}")
        return Post.objects.create(author=author, title=title, **kwargs)

    return _make
