"""
The moderator queue (RH-14): business logic for reviewing reports.

Reading:
    open_items()      open reports, grouped so each reported item is one row
    hidden_items()    content a moderator hid, so it can be restored
    recent_actions()  the moderation log

Writing — one function, ``perform``, for all three actions:
    hide     take the content off the site; its open reports become RESOLVED
    restore  put content a moderator hid back; reports stay closed
    dismiss  close the open reports as DISMISSED; the content is untouched

``perform`` checks ``can_moderate`` itself, so the rule holds whatever view
calls it, and every successful action writes exactly one ModAction.

Hidden content is soft-deleted (``is_removed``), never blanked or deleted, so a
restore brings back exactly what was there.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from bson import ObjectId
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.community.models import Post
from apps.ratings import services as ratings
from apps.ratings.models import CourseRating, ProfessorRating

from .models import ModAction, Report
from .services import Target, TargetType, find_target, target_for

Action = ModAction.Action
Key = tuple[str, ObjectId]  # (target_type, target_id): one reported item

MODERATOR_ROLES = {User.Role.MODERATOR, User.Role.ADMIN}
LOG_LENGTH = 25
# MongoDB stores times to the millisecond, so two quick actions can share one;
# the ObjectId breaks the tie in the order they were written.
NEWEST_FIRST = ("-created_at", "-id")


class ActionNotAllowed(Exception):
    """The action doesn't fit the item's current state. The message is shown to the moderator."""


# -- who may moderate --------------------------------------------------------
def can_moderate(user) -> bool:
    """MODERATOR and ADMIN only. Signed-out visitors have no role."""
    return bool(user.is_authenticated and getattr(user, "role", None) in MODERATOR_ROLES)


def require_moderator(user) -> None:
    if not can_moderate(user):
        raise PermissionDenied("Only moderators can do that.")


# -- what the page shows -----------------------------------------------------
@dataclass
class QueueItem:
    """One reported item and every open report against it."""

    target_type: str
    target_id: ObjectId
    parent_id: ObjectId | None
    target: Target | None  # None when the content no longer exists
    reports: list[Report] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.reports)

    @property
    def reasons(self) -> list[tuple[str, int]]:
        """("Spam or advertising", 2), most common first."""
        counts = Counter(r.get_reason_display() for r in self.reports)
        return counts.most_common()

    @property
    def notes(self) -> list[str]:
        return [r.note for r in self.reports if r.note]

    @property
    def first_reported(self) -> datetime:
        return min(r.created_at for r in self.reports)

    @property
    def label(self) -> str:
        return describe(self.target_type, self.target)

    @property
    def text(self) -> str:
        return full_text(self.target)


@dataclass
class HiddenItem:
    """Content a moderator hid, with the action that hid it."""

    hide: ModAction
    target: Target

    @property
    def label(self) -> str:
        return describe(self.target.type, self.target)

    @property
    def text(self) -> str:
        return full_text(self.target)


@dataclass
class LogEntry:
    action: ModAction
    target: Target | None

    @property
    def label(self) -> str:
        return describe(self.action.target_type, self.target)


def full_text(target: Target | None) -> str:
    """What the moderator reads before deciding: a post's title and body, else the text."""
    if target is None:
        return ""
    if target.type == TargetType.POST and target.obj.body:
        return f"{target.obj.title}\n\n{target.obj.body}"
    return target.preview


def describe(target_type: str, target: Target | None) -> str:
    """A short label saying what and where: "Comment on “Selling textbooks”"."""
    if target is None:
        return f"{TargetType(target_type).label} (no longer exists)"
    if target.type == TargetType.POST:
        return "Post"
    if target.type == TargetType.COMMENT:
        return "Comment on a post"
    if target.type == TargetType.COURSE_RATING:
        return f"Rating of {target.obj.course.code}"
    professor = target.obj.professor
    return f"Rating of {professor.first_name} {professor.last_name}"


def open_items() -> list[QueueItem]:
    """Every item with open reports: most-reported first, then the longest waiting."""
    items: dict[Key, QueueItem] = {}
    for report in Report.objects.filter(status=Report.Status.OPEN).order_by("created_at"):
        key = (report.target_type, report.target_id)
        if key not in items:
            items[key] = QueueItem(report.target_type, report.target_id, report.parent_id, None)
        items[key].reports.append(report)

    targets = load_targets((i.target_type, i.target_id, i.parent_id) for i in items.values())
    for key, item in items.items():
        item.target = targets.get(key)
    return sorted(items.values(), key=lambda i: (-i.count, i.first_reported))


def hidden_items() -> list[HiddenItem]:
    """Content whose most recent hide/restore was a hide, newest hide first.

    The log is the source of truth for "a moderator hid this": a post its author
    deleted is also ``is_removed``, but it was never hidden and can't be restored.
    """
    latest: dict[Key, ModAction] = {}
    toggles = ModAction.objects.filter(action__in=[Action.HIDE, Action.RESTORE])
    for action in toggles.select_related("actor").order_by(*NEWEST_FIRST):
        latest.setdefault((action.target_type, action.target_id), action)

    hides = [a for a in latest.values() if a.action == Action.HIDE]
    targets = load_targets((a.target_type, a.target_id, a.parent_id) for a in hides)
    found = []
    for hide in hides:
        target = targets.get((hide.target_type, hide.target_id))
        if target is not None and target.is_removed:
            found.append(HiddenItem(hide, target))
    return found


def recent_actions(limit: int = LOG_LENGTH) -> list[LogEntry]:
    actions = list(ModAction.objects.select_related("actor").order_by(*NEWEST_FIRST)[:limit])
    targets = load_targets((a.target_type, a.target_id, a.parent_id) for a in actions)
    return [LogEntry(a, targets.get((a.target_type, a.target_id))) for a in actions]


def load_targets(keys: Iterable[tuple[str, ObjectId, ObjectId | None]]) -> dict[Key, Target]:
    """Look up many items at once, removed ones included: one query per kind of content.

    Missing items are simply absent from the result.
    """
    keys = list(keys)
    post_ids = {i for t, i, _ in keys if t == TargetType.POST}
    post_ids |= {p for t, _, p in keys if t == TargetType.COMMENT and p}
    course_rating_ids = {i for t, i, _ in keys if t == TargetType.COURSE_RATING}
    professor_rating_ids = {i for t, i, _ in keys if t == TargetType.PROFESSOR_RATING}

    posts = {p.pk: p for p in Post.objects.filter(pk__in=post_ids)} if post_ids else {}
    found: dict[Key, Target] = {}
    for target_type, target_id, parent_id in keys:
        if target_type == TargetType.POST and target_id in posts:
            found[(target_type, target_id)] = target_for(posts[target_id])
        elif target_type == TargetType.COMMENT and parent_id in posts:
            post = posts[parent_id]
            comment = next((c for c in post.comments if c.comment_id == target_id), None)
            if comment is not None:
                found[(target_type, target_id)] = target_for(comment, post=post)

    if course_rating_ids:
        rows = CourseRating.objects.filter(pk__in=course_rating_ids).select_related("course")
        found |= {(TargetType.COURSE_RATING, r.pk): target_for(r) for r in rows}
    if professor_rating_ids:
        rows = ProfessorRating.objects.filter(pk__in=professor_rating_ids).select_related(
            "professor"
        )
        found |= {(TargetType.PROFESSOR_RATING, r.pk): target_for(r) for r in rows}
    return found


# -- doing something about it ------------------------------------------------
def perform(
    user,
    *,
    action: str,
    target_type: str,
    target_id: ObjectId,
    parent_id: ObjectId | None = None,
    note: str = "",
) -> ModAction:
    """Hide, restore, or dismiss one item, and log it.

    Raises PermissionDenied for non-moderators and ActionNotAllowed when the
    action doesn't fit the item (hiding something already hidden, and so on).
    The ids are looked up here, never trusted.
    """
    require_moderator(user)
    target = find_target(target_type, str(target_id), _str(parent_id), include_removed=True)
    open_reports = Report.objects.filter(
        target_type=target_type, target_id=target_id, status=Report.Status.OPEN
    )

    if action == Action.HIDE:
        if target is None:
            raise ActionNotAllowed("That content no longer exists. Dismiss its reports instead.")
        if target.is_removed:
            raise ActionNotAllowed("That content is already off the site.")
        _set_removed(target, True)
        open_reports.update(status=Report.Status.RESOLVED)
    elif action == Action.RESTORE:
        if target is None or not target.is_removed or not was_hidden_by_moderator(target):
            raise ActionNotAllowed("Only content a moderator hid can be restored.")
        _set_removed(target, False)
    elif action == Action.DISMISS:
        if not open_reports.exists():
            raise ActionNotAllowed("There are no open reports on that to dismiss.")
        open_reports.update(status=Report.Status.DISMISSED)
    else:
        raise ActionNotAllowed("Unknown action.")

    return ModAction.objects.create(
        actor=user,
        target_type=target_type,
        target_id=target_id,
        parent_id=parent_id if target_type == TargetType.COMMENT else None,
        action=action,
        note=note,
    )


def was_hidden_by_moderator(target: Target) -> bool:
    last = (
        ModAction.objects.filter(
            target_type=target.type,
            target_id=target.id,
            action__in=[Action.HIDE, Action.RESTORE],
        )
        .order_by(*NEWEST_FIRST)
        .first()
    )
    return last is not None and last.action == Action.HIDE


def _set_removed(target: Target, removed: bool) -> None:
    """Flip ``is_removed`` on the content, and keep the counts that depend on it right."""
    if target.type == TargetType.POST:
        target.obj.is_removed = removed
        target.obj.save(update_fields=["is_removed"])
    elif target.type == TargetType.COMMENT:
        # A comment is embedded, so the whole post is saved with it.
        post = Post.objects.get(pk=target.parent_id)
        comment = next(c for c in post.comments if c.comment_id == target.id)
        comment.is_removed = removed
        post.comment_count = len(post.live_comments)
        post.save(update_fields=["comments", "comment_count"])
    elif target.type == TargetType.COURSE_RATING:
        target.obj.is_removed = removed
        target.obj.save(update_fields=["is_removed"])
        ratings.refresh_course_summary(target.obj.course)
    else:
        target.obj.is_removed = removed
        target.obj.save(update_fields=["is_removed"])
        ratings.refresh_professor_summary(target.obj.professor)


def _str(value: ObjectId | None) -> str | None:
    return str(value) if value is not None else None
