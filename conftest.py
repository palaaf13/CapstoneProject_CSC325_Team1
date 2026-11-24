"""
Project-wide pytest configuration.

## How pytest-django behaves against django-mongodb-backend

Verified in Phase 1 against MongoDB 8.3.9, so nobody has to rediscover it:

* A separate test database really is created and used. Tests run against
  ``test_<MONGODB_NAME>`` (e.g. ``test_ramhub``), never your development data.
* **The plain ``@pytest.mark.django_db`` mark works.** Rows created in one test
  are gone by the next — the usual transaction-and-rollback isolation behaves
  as it does on SQL backends. You do *not* need ``transaction=True`` just
  because this is MongoDB.
* ``@pytest.mark.django_db(transaction=True)`` also works, and cleans up
  correctly. Reach for it only when a test genuinely needs committed data
  (say, something asserting on real transaction behaviour) — it truncates
  collections instead of rolling back and is slower.

The one caveat: rollback isolation depends on MongoDB transactions, which
require a replica set. Locally and on Atlas that is satisfied. A bare
standalone ``mongod`` has no transactions, and Django then quietly degrades
``TestCase`` to truncate-between-tests — still correct, just slower. This is why
CI starts its MongoDB service as a single-node replica set rather than a plain
one; see .github/workflows/ci.yml.

Any test that touches the database needs the mark. Note that this now includes
view tests for pages that only *read* — the catalog directories query on every
request.
"""

import anthropic
import pytest
from django.utils.text import slugify

from apps.catalog.models import (
    Course,
    CourseRatingSummary,
    Professor,
    ProfessorRatingSummary,
)


class _NoRealAnthropicClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError(
            "A unit test tried to create a real Anthropic client. Unit tests must use a "
            "mocked AI response; the real API is only called by the eval suite (evals/)."
        )


@pytest.fixture(autouse=True)
def fresh_cache():
    """Django's cache is in-process memory: clear it so one test's cached ticker
    or sign-in lockout can't leak into the next."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def no_real_ai(settings, monkeypatch):
    """Every test runs with AI calls impossible: no key, and constructing a real
    client fails the test. Tests that exercise the AI pass in a fake client."""
    settings.ANTHROPIC_API_KEY = ""
    monkeypatch.setattr(anthropic, "Anthropic", _NoRealAnthropicClient)


@pytest.fixture
def make_course():
    def _make(code="TST 101", title="Test Course", department="Testing", credits=3, **kwargs):
        summary = kwargs.pop("rating_summary", None)
        if summary is None:
            summary = CourseRatingSummary(
                avg_difficulty=kwargs.pop("difficulty", None),
                avg_workload=kwargs.pop("workload", None),
                avg_usefulness=kwargs.pop("usefulness", None),
                count=kwargs.pop("count", 0),
            )
        return Course.objects.create(
            code=code,
            title=title,
            department=department,
            credits=credits,
            rating_summary=summary,
            **kwargs,
        )

    return _make


@pytest.fixture
def make_professor():
    def _make(first_name="Ada", last_name="Lovelace", department="Testing", **kwargs):
        kwargs.setdefault("slug", slugify(f"{first_name} {last_name}"))
        summary = kwargs.pop("rating_summary", None)
        if summary is None:
            clarity = kwargs.pop("clarity", None)
            helpfulness = kwargs.pop("helpfulness", None)
            fairness = kwargs.pop("fairness", None)
            count = kwargs.pop("count", 0)
            overall = ProfessorRatingSummary.compute_overall(clarity, helpfulness, fairness)
            summary = ProfessorRatingSummary(
                avg_clarity=clarity,
                avg_helpfulness=helpfulness,
                avg_fairness=fairness,
                avg_overall=overall,
                count=count,
                source=kwargs.pop(
                    "source",
                    ProfessorRatingSummary.SOURCE_RAMHUB if count else "",
                ),
                rank_score=ProfessorRatingSummary.compute_rank_score(overall, count),
            )
        return Professor.objects.create(
            first_name=first_name,
            last_name=last_name,
            department=department,
            rating_summary=summary,
            **kwargs,
        )

    return _make
