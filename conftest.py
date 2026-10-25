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

import pytest
from django.utils.text import slugify

from apps.catalog.models import (
    Course,
    CourseRatingSummary,
    Professor,
    ProfessorRatingSummary,
)


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
