"""RH-13 rules, tested at the service and form level: who may report what, and once."""

import pytest
from bson import ObjectId
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError

from apps.community import services as community
from apps.moderation import services
from apps.moderation.forms import ReportForm
from apps.moderation.models import Report

pytestmark = pytest.mark.django_db

T = Report.TargetType


def test_a_report_is_filed_as_open(post, reporter):
    target = services.find_target(T.POST, str(post.pk))

    report = services.file_report(reporter, target, reason="spam", note="")

    assert report.status == Report.Status.OPEN
    assert (report.target_type, report.target_id, report.parent_id) == (T.POST, post.pk, None)
    assert report.reporter == reporter


def test_a_comment_report_remembers_the_post_it_lives_in(post, comment, reporter):
    target = services.find_target(T.COMMENT, str(comment.comment_id), str(post.pk))

    report = services.file_report(reporter, target, reason="spam")

    assert report.target_id == comment.comment_id
    assert report.parent_id == post.pk


def test_both_kinds_of_rating_can_be_found_and_reported(course_rating, professor_rating, reporter):
    for kind, rating in ((T.COURSE_RATING, course_rating), (T.PROFESSOR_RATING, professor_rating)):
        target = services.find_target(kind, str(rating.pk))
        assert target.owner_id == rating.user_id
        services.file_report(reporter, target, reason="off_topic")
    assert Report.objects.count() == 2


def test_nobody_can_report_their_own_content(post, comment, course_rating, author):
    targets = [
        services.target_for(post),
        services.target_for(comment, post=post),
        services.target_for(course_rating),
    ]
    for target in targets:
        assert not services.can_report(author, target)
        with pytest.raises(PermissionDenied):
            services.file_report(author, target, reason="spam")
    assert not Report.objects.exists()


def test_a_student_cannot_report_the_same_item_twice(post, reporter):
    target = services.target_for(post)
    services.file_report(reporter, target, reason="spam")

    with pytest.raises(services.AlreadyReported):
        services.file_report(reporter, target, reason="harassment")
    assert Report.objects.count() == 1


def test_the_database_also_refuses_a_duplicate(post, reporter):
    """The UniqueConstraint backs up the service check (e.g. a double-click race)."""
    Report.objects.create(reporter=reporter, target_type=T.POST, target_id=post.pk, reason="spam")
    with pytest.raises(IntegrityError):
        Report.objects.create(
            reporter=reporter, target_type=T.POST, target_id=post.pk, reason="other"
        )


def test_different_students_can_each_report_the_same_item(post, make_user):
    target = services.target_for(post)
    for name in ("amy", "ben"):
        services.file_report(make_user(name), target, reason="spam")
    assert Report.objects.filter(target_id=post.pk).count() == 2


def test_missing_removed_or_malformed_targets_are_not_found(post, comment, author):
    other_post = community.create_post(
        author=author, kind="discussion", title="x", body="", tags=[]
    )

    assert services.find_target(T.POST, "not-an-id") is None
    assert services.find_target(T.POST, str(ObjectId())) is None
    assert services.find_target("unknown", str(post.pk)) is None
    # A comment looked up under the wrong post does not exist there.
    assert services.find_target(T.COMMENT, str(comment.comment_id), str(other_post.pk)) is None
    assert services.find_target(T.COMMENT, str(comment.comment_id), "nope") is None

    community.remove_comment(author, post, str(comment.comment_id))
    assert services.find_target(T.COMMENT, str(comment.comment_id), str(post.pk)) is None
    community.remove_post(author, post)
    assert services.find_target(T.POST, str(post.pk)) is None


def test_signed_out_visitors_cannot_report(post):
    assert not services.can_report(AnonymousUser(), services.target_for(post))


@pytest.mark.parametrize(
    ("data", "valid"),
    [
        ({"reason": "spam"}, True),
        ({"reason": "harassment", "note": "Targets one student."}, True),
        ({"reason": "other", "note": "Wrong course page."}, True),
        ({"reason": "other", "note": "   "}, False),  # a blank note is no note
        ({"reason": "other"}, False),
        ({"reason": ""}, False),
        ({"reason": "made-up"}, False),
        ({"reason": "spam", "note": "x" * 501}, False),
    ],
)
def test_report_form(data, valid):
    form = ReportForm(data)
    assert form.is_valid() is valid
    if data.get("reason") == "other" and not valid:
        assert "note" in form.errors
