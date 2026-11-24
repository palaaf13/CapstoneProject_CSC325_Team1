"""RH-14 acceptance: moderators review reports and hide or restore content; every
action is logged. Everyone else is kept out, by the server and not just the nav."""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

from apps.community.models import Post
from apps.moderation.models import ModAction, Report
from apps.moderation.views import BAD_REQUEST, DONE

pytestmark = pytest.mark.django_db

QUEUE = reverse("moderation:queue")
ACT = reverse("moderation:queue_action")


def hide_post(post, **extra):
    return {"action": "hide", "target_type": "post", "target_id": str(post.pk), **extra}


# -- who gets in ---------------------------------------------------------------
def test_signed_out_visitors_are_sent_to_sign_in(client, post, make_report):
    make_report(post)
    for response in (client.get(QUEUE), client.post(ACT, hide_post(post))):
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))
    assert not Post.objects.get(pk=post.pk).is_removed


def test_students_get_403_on_the_page_and_the_action(client, post, make_report, reporter):
    make_report(post)
    client.force_login(reporter)

    assert client.get(QUEUE).status_code == 403
    assert client.post(ACT, hide_post(post)).status_code == 403

    assert not Post.objects.get(pk=post.pk).is_removed
    assert not ModAction.objects.exists()


@pytest.mark.parametrize("who", ["moderator", "admin_user"])
def test_moderators_and_admins_see_the_queue(client, post, make_report, who, request):
    make_report(post, note="Selling stuff")
    client.force_login(request.getfixturevalue(who))

    response = client.get(QUEUE)

    assert response.status_code == 200
    assert post.title in response.text
    assert "Selling stuff" in response.text
    assert "Spam or advertising" in response.text


def test_the_nav_link_shows_only_for_moderators(client, reporter, moderator):
    client.force_login(reporter)
    assert QUEUE not in client.get(reverse("community:feed")).text

    client.force_login(moderator)
    assert QUEUE in client.get(reverse("community:feed")).text


# -- POST only, CSRF protected ------------------------------------------------
def test_the_action_url_refuses_get(client, moderator):
    client.force_login(moderator)
    assert client.get(ACT).status_code == 405


def test_an_action_without_a_csrf_token_is_rejected(post, make_report, moderator):
    make_report(post)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(moderator)

    assert strict.post(ACT, hide_post(post)).status_code == 403
    assert not Post.objects.get(pk=post.pk).is_removed


def test_the_queue_page_includes_csrf_tokens_in_its_forms(client, post, make_report, moderator):
    make_report(post)
    client.force_login(moderator)
    assert 'name="csrfmiddlewaretoken"' in client.get(QUEUE).text


# -- doing things -------------------------------------------------------------
def test_hide_from_the_queue_then_restore(client, post, make_report, moderator):
    make_report(post)
    client.force_login(moderator)

    response = client.post(ACT, hide_post(post, note="Ad"), follow=True)

    assert escape(DONE[ModAction.Action.HIDE]) in response.text
    assert Post.objects.get(pk=post.pk).is_removed
    assert Report.objects.get().status == Report.Status.RESOLVED
    assert 'data-testid="queue-empty"' in response.text  # off the open list
    assert 'data-testid="hidden-item"' in response.text  # and restorable
    page = client.get(reverse("community:post_detail", args=[post.pk])).text
    assert post.title not in page

    restore = {**hide_post(post), "action": "restore"}
    response = client.post(ACT, restore, follow=True)

    assert escape(DONE[ModAction.Action.RESTORE]) in response.text
    assert not Post.objects.get(pk=post.pk).is_removed
    assert ModAction.objects.count() == 2


def test_dismiss_from_the_queue(client, comment, post, make_report, moderator):
    make_report(comment, post=post)
    client.force_login(moderator)
    data = {
        "action": "dismiss",
        "target_type": "comment",
        "target_id": str(comment.comment_id),
        "parent_id": str(post.pk),
    }

    response = client.post(ACT, data, follow=True)

    assert escape(DONE[ModAction.Action.DISMISS]) in response.text
    assert Report.objects.get().status == Report.Status.DISMISSED
    assert not Post.objects.get(pk=post.pk).comments[0].is_removed


def test_a_hidden_course_rating_disappears_from_the_course_page(
    client, course_rating, make_report, moderator
):
    make_report(course_rating)
    page = reverse("catalog:course_detail", args=[course_rating.course.slug])
    assert course_rating.comment in client.get(page).text

    client.force_login(moderator)
    data = {"action": "hide", "target_type": "course_rating", "target_id": str(course_rating.pk)}
    client.post(ACT, data)

    assert course_rating.comment not in client.get(page).text


@pytest.mark.parametrize(
    "data",
    [
        {"action": "delete", "target_type": "post", "target_id": "x"},
        {"action": "hide", "target_type": "user", "target_id": "64b000000000000000000000"},
        {"action": "hide", "target_type": "post", "target_id": "not-an-id"},
        {"action": "hide", "target_type": "comment", "target_id": "64b000000000000000000000"},
    ],
)
def test_malformed_actions_change_nothing(client, moderator, data):
    client.force_login(moderator)
    response = client.post(ACT, data, follow=True)
    assert escape(BAD_REQUEST) in response.text
    assert not ModAction.objects.exists()


def test_an_action_that_does_not_fit_shows_why(client, post, moderator):
    client.force_login(moderator)
    response = client.post(ACT, {**hide_post(post), "action": "dismiss"}, follow=True)
    assert "no open reports" in response.text
    assert not ModAction.objects.exists()


def test_empty_states(client, moderator):
    client.force_login(moderator)
    page = client.get(QUEUE).text
    for testid in ("queue-empty", "hidden-empty", "log-empty"):
        assert f'data-testid="{testid}"' in page
