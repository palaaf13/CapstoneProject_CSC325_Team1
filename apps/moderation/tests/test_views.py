"""RH-13 acceptance: any signed-in student can flag a post, comment, or rating with a reason."""

import pytest
from bson import ObjectId
from django.urls import reverse

from apps.moderation.models import Report
from apps.moderation.views import ALREADY_REPORTED, THANKS

pytestmark = pytest.mark.django_db


def post_url(post):
    return reverse("moderation:report_post", args=[post.pk])


def comment_url(post, comment):
    return reverse("moderation:report_comment", args=[post.pk, comment.comment_id])


# -- the report page ---------------------------------------------------------
def test_signed_out_visitor_is_sent_to_sign_in(client, post):
    response = client.post(post_url(post), {"reason": "spam"})
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))
    assert not Report.objects.exists()


def test_the_form_shows_what_is_being_reported(client, post, reporter):
    client.force_login(reporter)
    response = client.get(post_url(post))
    assert response.status_code == 200
    assert "Report this post" in response.text
    assert post.title in response.text


def test_reporting_a_post_returns_to_it_with_a_confirmation(client, post, reporter):
    client.force_login(reporter)

    response = client.post(post_url(post), {"reason": "spam", "note": "Selling things."})

    assert response.status_code == 302
    assert response.url == reverse("community:post_detail", args=[post.pk])
    report = Report.objects.get()
    assert (report.reason, report.note, report.reporter) == ("spam", "Selling things.", reporter)
    assert THANKS in client.get(response.url).text


def test_reporting_a_comment_returns_to_that_comment(client, post, comment, reporter):
    client.force_login(reporter)

    response = client.post(comment_url(post, comment), {"reason": "spam"})

    assert response.url.endswith(f"#comment-{comment.comment_id}")
    report = Report.objects.get()
    assert (report.target_type, report.parent_id) == ("comment", post.pk)


def test_reporting_ratings_returns_to_the_course_or_professor(
    client, course_rating, professor_rating, reporter
):
    client.force_login(reporter)
    cases = [
        ("moderation:report_course_rating", course_rating, "catalog:course_detail", "CSC-240"),
        (
            "moderation:report_professor_rating",
            professor_rating,
            "catalog:professor_detail",
            professor_rating.professor.slug,
        ),
    ]
    for url_name, rating, detail_name, key in cases:
        response = client.post(reverse(url_name, args=[rating.pk]), {"reason": "off_topic"})
        assert response.url == reverse(detail_name, args=[key])
    assert Report.objects.count() == 2


def test_other_without_a_note_shows_an_error_and_saves_nothing(client, post, reporter):
    client.force_login(reporter)
    response = client.post(post_url(post), {"reason": "other", "note": ""})
    assert response.status_code == 200
    assert "Tell the moderators what" in response.text
    assert not Report.objects.exists()


def test_reporting_twice_says_so_and_keeps_one_report(client, post, reporter):
    client.force_login(reporter)
    client.post(post_url(post), {"reason": "spam"})

    response = client.post(post_url(post), {"reason": "harassment"}, follow=True)

    assert ALREADY_REPORTED in response.text
    assert Report.objects.get().reason == "spam"


def test_reporting_your_own_content_is_forbidden(client, post, comment, author):
    client.force_login(author)
    assert client.get(post_url(post)).status_code == 403
    assert client.post(comment_url(post, comment), {"reason": "spam"}).status_code == 403
    assert not Report.objects.exists()


def test_unknown_items_are_404(client, post, reporter):
    client.force_login(reporter)
    missing = ObjectId()
    assert client.get(reverse("moderation:report_post", args=[missing])).status_code == 404
    assert client.get(reverse("moderation:report_post", args=["junk"])).status_code == 404
    url = reverse("moderation:report_comment", args=[post.pk, missing])
    assert client.get(url).status_code == 404


# -- the Report buttons on existing pages --------------------------------------
def test_post_page_offers_report_on_the_post_and_its_comments(client, post, comment, reporter):
    client.force_login(reporter)
    page = client.get(reverse("community:post_detail", args=[post.pk])).text
    assert f'href="{post_url(post)}"' in page
    assert f'href="{comment_url(post, comment)}"' in page


def test_signed_out_visitors_see_no_report_buttons(client, post, comment, course_rating):
    page = client.get(reverse("community:post_detail", args=[post.pk])).text
    page += client.get(reverse("catalog:course_detail", args=["CSC-240"])).text
    assert 'data-testid="report-link"' not in page


def test_authors_see_no_report_button_on_their_own_content(
    client, post, comment, course_rating, author
):
    client.force_login(author)
    page = client.get(reverse("community:post_detail", args=[post.pk])).text
    page += client.get(reverse("catalog:course_detail", args=["CSC-240"])).text
    assert 'data-testid="report-link"' not in page


def test_something_already_reported_shows_reported(client, post, comment, reporter):
    client.force_login(reporter)
    client.post(post_url(post), {"reason": "spam"})

    page = client.get(reverse("community:post_detail", args=[post.pk])).text

    assert 'data-testid="reported"' in page
    assert f'href="{post_url(post)}"' not in page
    assert f'href="{comment_url(post, comment)}"' in page  # the comment is still reportable


def test_rating_lists_offer_report_to_other_students(
    client, course_rating, professor_rating, reporter
):
    client.force_login(reporter)
    course_page = client.get(reverse("catalog:course_detail", args=["CSC-240"])).text
    prof = professor_rating.professor
    prof_page = client.get(reverse("catalog:professor_detail", args=[prof.slug])).text
    assert reverse("moderation:report_course_rating", args=[course_rating.pk]) in course_page
    assert reverse("moderation:report_professor_rating", args=[professor_rating.pk]) in prof_page
