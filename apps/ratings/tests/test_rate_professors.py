"""RH-20 acceptance: a signed-in student rates clarity, helpfulness, and
fairness once per professor."""

import pytest
from django.urls import reverse

from apps.catalog.models import Professor, ProfessorRatingSummary
from apps.catalog.services import link_course_and_professor
from apps.ratings.forms import recent_semesters
from apps.ratings.models import ProfessorRating

pytestmark = pytest.mark.django_db

SEMESTER = recent_semesters()[0]


def rate_url(professor):
    return reverse("ratings:rate_professor", kwargs={"slug": professor.slug})


def page_url(professor):
    return reverse("catalog:professor_detail", kwargs={"slug": professor.slug})


def post_rating(client, professor, **overrides):
    data = {
        "clarity": 5,
        "helpfulness": 4,
        "fairness": 3,
        "semester": SEMESTER,
        "comment": "Explains things twice if you ask.",
    }
    data.update(overrides)
    return client.post(rate_url(professor), data)


def stored(professor):
    return Professor.objects.get(pk=professor.pk).rating_summary


def test_signed_out_visitor_is_sent_to_sign_in(client, make_professor):
    professor = make_professor()
    response = client.get(rate_url(professor))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_student_rates_a_professor_and_the_summary_updates(client, make_professor, make_student):
    professor = make_professor()
    client.force_login(make_student())

    response = post_rating(client, professor)

    assert response.status_code == 302
    assert response.url == page_url(professor)
    summary = stored(professor)
    assert summary.count == 1
    assert (summary.avg_clarity, summary.avg_helpfulness, summary.avg_fairness) == (5, 4, 3)
    assert summary.avg_overall == 4
    assert summary.source == ProfessorRatingSummary.SOURCE_RAMHUB
    assert summary.rank_score is not None


def test_once_per_professor_second_submit_edits(client, make_professor, make_student):
    professor = make_professor()
    client.force_login(make_student())
    post_rating(client, professor, clarity=1)
    post_rating(client, professor, clarity=5)

    assert ProfessorRating.objects.count() == 1
    assert stored(professor).avg_clarity == 5


def test_a_ramhub_rating_replaces_an_imported_rmp_headline(client, make_professor, make_student):
    professor = make_professor(
        rating_summary=ProfessorRatingSummary(
            avg_overall=2.1, count=40, source=ProfessorRatingSummary.SOURCE_RMP
        ),
        rmp_num_ratings=40,
        rmp_avg_rating=2.1,
    )
    client.force_login(make_student())
    post_rating(client, professor)

    refreshed = Professor.objects.get(pk=professor.pk)
    assert refreshed.rating_summary.source == ProfessorRatingSummary.SOURCE_RAMHUB
    assert refreshed.rating_summary.count == 1
    # The RMP figures are kept, still labelled as RMP's.
    assert (refreshed.rmp_num_ratings, refreshed.rmp_avg_rating) == (40, 2.1)


def test_course_choice_is_limited_to_what_they_teach(
    client, make_professor, make_course, make_student
):
    professor = make_professor()
    taught = make_course(code="CSC 240")
    other = make_course(code="ART 101")
    link_course_and_professor(taught, professor)
    client.force_login(make_student())

    assert post_rating(client, professor, course=str(other.pk)).status_code == 200
    assert not ProfessorRating.objects.exists()

    assert post_rating(client, professor, course=str(taught.pk)).status_code == 302
    assert ProfessorRating.objects.get().course_id == taught.pk


def test_no_course_dropdown_when_none_are_on_record(client, make_professor, make_student):
    professor = make_professor()
    client.force_login(make_student())
    body = client.get(rate_url(professor)).content
    assert b'name="course"' not in body
    assert post_rating(client, professor).status_code == 302


@pytest.mark.parametrize("field", ["clarity", "helpfulness", "fairness"])
def test_each_score_is_required_and_bounded(client, make_professor, make_student, field):
    professor = make_professor()
    client.force_login(make_student())
    assert post_rating(client, professor, **{field: "7"}).status_code == 200
    assert post_rating(client, professor, **{field: ""}).status_code == 200
    assert not ProfessorRating.objects.exists()


def test_professor_page_shows_reviews_and_button(client, make_professor, make_student):
    professor = make_professor()
    assert b"Sign in to rate" in client.get(page_url(professor)).content

    client.force_login(make_student())
    assert b"Rate this professor" in client.get(page_url(professor)).content
    post_rating(client, professor, comment="Posts all slides before class.")

    body = client.get(page_url(professor)).content
    assert b"Edit your rating" in body
    assert b"Posts all slides before class." in body
    assert b"averaged from" in body
