"""Factory helpers for the ratings tests."""

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def make_student():
    def _make(username="student", **kwargs):
        kwargs.setdefault("email", f"{username}@farmingdale.edu")
        return get_user_model().objects.create_user(
            username=username, password="pw-12345!", **kwargs
        )

    return _make
