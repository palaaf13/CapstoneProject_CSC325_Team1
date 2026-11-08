"""Reuse the app-level factories in project-level tests."""

from apps.campus.tests.conftest import make_club  # noqa: F401
from apps.catalog.tests.conftest import make_course, make_professor  # noqa: F401
