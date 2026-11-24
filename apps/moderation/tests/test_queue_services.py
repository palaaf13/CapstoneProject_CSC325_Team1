"""RH-14 rules at the service level: who may moderate, and what hide, restore,
and dismiss do to the content, its reports, and the log."""

import pytest
from bson import ObjectId
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied

from apps.community import services as community
from apps.community.models import Post
from apps.moderation import queue, services
from apps.moderation.models import ModAction, Report
from apps.ratings import services as ratings

pytestmark = pytest.mark.django_db

T = Report.TargetType
A = ModAction.Action


def act(user, action, obj, *, post=None, note=""):
    """Call queue.perform for an object, the way the view does after validating the form."""
    target = services.target_for(obj, post=post)
    return queue.perform(
        user,
        action=action,
        target_type=target.type,
        target_id=target.id,
        parent_id=target.parent_id,
        note=note,
    )


# -- who may moderate ----------------------------------------------------------
def test_only_moderators_and_admins_can_moderate(make_user, moderator, admin_user):
    assert queue.can_moderate(moderator)
    assert queue.can_moderate(admin_user)
    assert not queue.can_moderate(make_user("plain"))
    assert not queue.can_moderate(AnonymousUser())


def test_a_student_cannot_perform_any_action(post, make_report, reporter):
    make_report(post)
    for action in (A.HIDE, A.DISMISS, A.RESTORE):
        with pytest.raises(PermissionDenied):
            act(reporter, action, post)

    post.refresh_from_db()
    assert not post.is_removed
    assert Report.objects.get().status == Report.Status.OPEN
    assert not ModAction.objects.exists()


# -- the queue -----------------------------------------------------------------
def test_open_reports_are_grouped_one_row_per_item(post, comment, make_report):
    make_report(post, reason="spam", note="Selling textbooks.")
    make_report(post, reason="spam")
    make_report(post, reason="off_topic")
    make_report(comment, post=post, reason="harassment")

    items = queue.open_items()

    assert [i.target_type for i in items] == [T.POST, T.COMMENT]  # most reported first
    top = items[0]
    assert top.count == 3
    assert top.reasons == [("Spam or advertising", 2), ("Off-topic", 1)]
    assert top.notes == ["Selling textbooks."]
    assert top.target.obj == post
    assert items[1].target.parent_id == post.pk


def test_closed_reports_leave_the_queue(post, make_report, moderator):
    make_report(post)
    act(moderator, A.DISMISS, post)
    assert queue.open_items() == []


def test_reports_on_deleted_content_can_still_be_dismissed(make_report, post, moderator):
    make_report(post)
    Post.objects.filter(pk=post.pk).delete()

    [item] = queue.open_items()
    assert item.target is None
    queue.perform(moderator, action=A.DISMISS, target_type=T.POST, target_id=post.pk)
    assert Report.objects.get().status == Report.Status.DISMISSED


# -- hide ----------------------------------------------------------------------
def test_hiding_a_post_removes_it_resolves_reports_and_logs(post, make_report, moderator):
    make_report(post)
    make_report(post)

    logged = act(moderator, A.HIDE, post, note="Ad")

    post.refresh_from_db()
    assert post.is_removed
    assert post.title == "Selling my old textbooks, DM me"  # kept, so it can be restored
    assert set(Report.objects.values_list("status", flat=True)) == {Report.Status.RESOLVED}
    assert (logged.actor, logged.action, logged.target_id, logged.note) == (
        moderator,
        A.HIDE,
        post.pk,
        "Ad",
    )


def test_hiding_a_comment_keeps_its_text_and_updates_the_count(post, comment, moderator):
    act(moderator, A.HIDE, comment, post=post)

    post.refresh_from_db()
    stored = post.comments[0]
    assert stored.is_removed
    assert stored.body == "Buy my notes, link in bio."
    assert post.comment_count == 0
    assert ModAction.objects.get().parent_id == post.pk


def test_hiding_something_already_off_the_site_is_refused(post, author, moderator):
    community.remove_post(author, post)
    with pytest.raises(queue.ActionNotAllowed):
        act(moderator, A.HIDE, post)


# -- ratings: hidden means gone from the page and from the average --------------
def test_a_hidden_course_rating_leaves_the_comments_and_the_average(
    course_rating, make_user, moderator
):
    course = course_rating.course
    ratings.rate_course(
        user=make_user("other"),
        course=course,
        difficulty=5,
        workload=5,
        usefulness=5,
        semester="Fall 2026",
        comment="Great class.",
    )
    course.refresh_from_db()
    assert (course.rating_summary.count, course.rating_summary.avg_difficulty) == (2, 4.0)

    act(moderator, A.HIDE, course_rating)

    course.refresh_from_db()
    assert (course.rating_summary.count, course.rating_summary.avg_difficulty) == (1, 5.0)
    assert course_rating not in ratings.course_comments(course)

    act(moderator, A.RESTORE, course_rating)

    course.refresh_from_db()
    assert (course.rating_summary.count, course.rating_summary.avg_difficulty) == (2, 4.0)
    assert course_rating in ratings.course_comments(course)


def test_a_hidden_professor_rating_leaves_the_comments_and_the_average(professor_rating, moderator):
    professor = professor_rating.professor
    ratings.refresh_professor_summary(professor)
    professor.refresh_from_db()
    assert professor.rating_summary.count == 1

    act(moderator, A.HIDE, professor_rating)

    professor.refresh_from_db()
    assert professor.rating_summary.count == 0
    assert professor.rating_summary.avg_overall is None
    assert ratings.professor_comments(professor) == []


def test_a_hidden_rating_cannot_be_reported(course_rating, moderator):
    act(moderator, A.HIDE, course_rating)
    assert services.find_target(T.COURSE_RATING, str(course_rating.pk)) is None


def test_editing_a_hidden_rating_does_not_unhide_it(course_rating, author, moderator):
    act(moderator, A.HIDE, course_rating)
    ratings.rate_course(
        user=author,
        course=course_rating.course,
        difficulty=1,
        workload=1,
        usefulness=1,
        semester="Fall 2026",
        comment="Edited.",
    )
    course_rating.refresh_from_db()
    assert course_rating.is_removed
    course_rating.course.refresh_from_db()
    assert course_rating.course.rating_summary.count == 0


# -- restore -------------------------------------------------------------------
def test_restoring_brings_hidden_content_back(post, comment, moderator):
    act(moderator, A.HIDE, post)
    act(moderator, A.HIDE, comment, post=post)
    assert len(queue.hidden_items()) == 2

    act(moderator, A.RESTORE, Post.objects.get(pk=post.pk))
    fresh = Post.objects.get(pk=post.pk)
    act(moderator, A.RESTORE, fresh.comments[0], post=fresh)

    fresh = Post.objects.get(pk=post.pk)
    assert not fresh.is_removed
    assert not fresh.comments[0].is_removed
    assert fresh.comment_count == 1
    assert queue.hidden_items() == []
    assert list(
        ModAction.objects.order_by("created_at", "id").values_list("action", flat=True)
    ) == [
        A.HIDE,
        A.HIDE,
        A.RESTORE,
        A.RESTORE,
    ]


def test_only_content_a_moderator_hid_can_be_restored(post, author, moderator):
    with pytest.raises(queue.ActionNotAllowed):  # live content
        act(moderator, A.RESTORE, post)

    community.remove_post(author, post)  # the author deleted it themselves
    post.refresh_from_db()
    with pytest.raises(queue.ActionNotAllowed):
        act(moderator, A.RESTORE, post)
    assert queue.hidden_items() == []
    assert not ModAction.objects.exists()


# -- dismiss -------------------------------------------------------------------
def test_dismissing_closes_reports_and_leaves_the_content(post, make_report, admin_user):
    make_report(post)
    make_report(post)

    logged = act(admin_user, A.DISMISS, post)

    post.refresh_from_db()
    assert not post.is_removed
    assert set(Report.objects.values_list("status", flat=True)) == {Report.Status.DISMISSED}
    assert logged.action == A.DISMISS


def test_dismissing_with_no_open_reports_is_refused(post, moderator):
    with pytest.raises(queue.ActionNotAllowed):
        act(moderator, A.DISMISS, post)


def test_an_unknown_id_is_refused(moderator):
    with pytest.raises(queue.ActionNotAllowed):
        queue.perform(moderator, action=A.HIDE, target_type=T.POST, target_id=ObjectId())


# -- the log -------------------------------------------------------------------
def test_recent_actions_are_newest_first(post, course_rating, make_report, moderator):
    make_report(post)
    act(moderator, A.DISMISS, post)
    act(moderator, A.HIDE, course_rating)

    log = queue.recent_actions()

    assert [e.action.action for e in log] == [A.HIDE, A.DISMISS]
    assert log[0].label == "Rating of CSC 240"
