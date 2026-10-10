"""Factory helpers for the campus tests."""

import pytest
from django.utils.text import slugify

from apps.campus.models import Club


@pytest.fixture
def make_club():
    def _make(name="Chess Club", **kwargs):
        kwargs.setdefault("slug", slugify(name))
        kwargs.setdefault("org_type", "Recognized Student Organizations")
        return Club.objects.create(name=name, **kwargs)

    return _make
