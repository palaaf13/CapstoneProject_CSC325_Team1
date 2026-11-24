"""
Business logic for reports. Views parse the request, call one of these, render.

Every rule about who may report what lives here, not in a template, so a
hand-crafted request cannot skip it:

* the target must exist and must not already be removed,
* nobody reports their own content,
* each student reports each item at most once (also a UniqueConstraint).
"""

from dataclasses import dataclass

from bson import ObjectId
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpRequest
from django.urls import reverse

from apps.community.models import Comment, Post
from apps.ratings.models import CourseRating, ProfessorRating

from .models import Report

TargetType = Report.TargetType


class AlreadyReported(Exception):
    """This student has already reported this item."""


@dataclass(frozen=True)
class Target:
    """Something that can be reported, with everything the pages need to show it."""

    type: str
    id: ObjectId
    owner_id: ObjectId
    is_removed: bool
    noun: str  # "post", "comment", "rating" — for labels like "Report this comment"
    preview: str  # a short reminder of what is being reported
    obj: object  # the Post, Comment, or rating itself
    parent_id: ObjectId | None = None  # the post a comment lives in

    @property
    def back_url(self) -> str:
        """Where the student returns to afterwards.

        A property, not a field, because a rating's page needs its course or
        professor: building it for every Report button would cost a query per
        rating. Only the report page asks for it.
        """
        if self.type == TargetType.POST:
            return reverse("community:post_detail", args=[self.id])
        if self.type == TargetType.COMMENT:
            return reverse("community:post_detail", args=[self.parent_id]) + f"#comment-{self.id}"
        if self.type == TargetType.COURSE_RATING:
            return reverse("catalog:course_detail", args=[self.obj.course.slug])
        return reverse("catalog:professor_detail", args=[self.obj.professor.slug])

    @property
    def report_url(self) -> str:
        if self.type == TargetType.COMMENT:
            return reverse("moderation:report_comment", args=[self.parent_id, self.id])
        name = {
            TargetType.POST: "moderation:report_post",
            TargetType.COURSE_RATING: "moderation:report_course_rating",
            TargetType.PROFESSOR_RATING: "moderation:report_professor_rating",
        }[self.type]
        return reverse(name, args=[self.id])


# -- building a Target from an object (no database queries) ----------------
def target_for(obj, post: Post | None = None) -> Target:
    """Describe a Post, a Comment (pass its ``post``), or a rating as a Target."""
    if isinstance(obj, Post):
        return Target(
            type=TargetType.POST,
            id=obj.pk,
            owner_id=obj.author_id,
            is_removed=obj.is_removed,
            noun="post",
            preview=obj.title,
            obj=obj,
        )
    if isinstance(obj, Comment):
        if post is None:
            raise TypeError("A comment needs its post to be reported.")
        return Target(
            type=TargetType.COMMENT,
            id=obj.comment_id,
            parent_id=post.pk,
            owner_id=obj.author_id,
            is_removed=obj.is_removed,
            noun="comment",
            preview=obj.body,
            obj=obj,
        )
    if isinstance(obj, CourseRating):
        return Target(
            type=TargetType.COURSE_RATING,
            id=obj.pk,
            owner_id=obj.user_id,
            is_removed=obj.is_removed,
            noun="rating",
            preview=obj.comment,
            obj=obj,
        )
    if isinstance(obj, ProfessorRating):
        return Target(
            type=TargetType.PROFESSOR_RATING,
            id=obj.pk,
            owner_id=obj.user_id,
            is_removed=obj.is_removed,
            noun="rating",
            preview=obj.comment,
            obj=obj,
        )
    raise TypeError(f"{type(obj).__name__} can't be reported")


# -- finding a Target from ids in a URL -------------------------------------
def _oid(value) -> ObjectId | None:
    return ObjectId(value) if ObjectId.is_valid(value) else None


def find_target(
    target_type: str,
    target_id: str,
    parent_id: str | None = None,
    *,
    include_removed: bool = False,
) -> Target | None:
    """The live item these ids point at, or None if it is missing, removed, or malformed.

    The moderator queue passes ``include_removed=True``: it has to find hidden
    content in order to restore it.
    """
    oid = _oid(target_id)
    if oid is None:
        return None

    obj, post = None, None
    if target_type == TargetType.POST:
        obj = Post.objects.filter(pk=oid).first()
    elif target_type == TargetType.COMMENT:
        post_oid = _oid(parent_id)
        post = Post.objects.filter(pk=post_oid).first() if post_oid else None
        if post is not None:
            obj = next((c for c in post.comments if c.comment_id == oid), None)
    elif target_type == TargetType.COURSE_RATING:
        obj = CourseRating.objects.select_related("course").filter(pk=oid).first()
    elif target_type == TargetType.PROFESSOR_RATING:
        obj = ProfessorRating.objects.select_related("professor").filter(pk=oid).first()

    if obj is None:
        return None
    target = target_for(obj, post=post)
    return None if target.is_removed and not include_removed else target


# -- the rules --------------------------------------------------------------
def is_own(user, target: Target) -> bool:
    return bool(user.is_authenticated and target.owner_id == user.pk)


def can_report(user, target: Target) -> bool:
    """Whether to offer a Report button: signed in, not your own, not removed."""
    return bool(user.is_authenticated and not target.is_removed and not is_own(user, target))


def has_reported(user, target: Target) -> bool:
    if not user.is_authenticated:
        return False
    return Report.objects.filter(
        reporter=user, target_type=target.type, target_id=target.id
    ).exists()


def reported_keys(request: HttpRequest) -> set[tuple[str, ObjectId]]:
    """(target_type, target_id) for everything the signed-in student has reported.

    One query per request, however many Report buttons the page draws: the
    result is kept on the request for the rest of the render.
    """
    if not request.user.is_authenticated:
        return set()
    if not hasattr(request, "_reported_keys"):
        rows = Report.objects.filter(reporter=request.user).values_list("target_type", "target_id")
        request._reported_keys = set(rows)
    return request._reported_keys


def file_report(user, target: Target, *, reason: str, note: str = "") -> Report:
    """Record one student's report. Raises PermissionDenied or AlreadyReported."""
    if not user.is_authenticated or target.is_removed:
        raise PermissionDenied("This can't be reported.")
    if is_own(user, target):
        raise PermissionDenied("You can't report your own content.")
    if has_reported(user, target):
        raise AlreadyReported
    try:
        return Report.objects.create(
            reporter=user,
            target_type=target.type,
            target_id=target.id,
            parent_id=target.parent_id,
            reason=reason,
            note=note,
        )
    except IntegrityError:
        # A double-click raced past the check above; the constraint caught it.
        raise AlreadyReported from None
