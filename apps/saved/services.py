"""Saving and listing items in a student's filing cabinet."""

from contextlib import suppress
from dataclasses import dataclass

from bson import ObjectId
from bson.errors import InvalidId
from django.db import IntegrityError

from apps.campus.models import Club
from apps.catalog.models import Course, Professor

from .models import SavedItem

Kind = SavedItem.Kind

# What each kind points at, and how the cabinet labels its section.
MODELS = {Kind.COURSE: Course, Kind.PROFESSOR: Professor, Kind.CLUB: Club}
SECTION_ORDER = [(Kind.COURSE, "Courses"), (Kind.PROFESSOR, "Professors"), (Kind.CLUB, "Clubs")]


@dataclass(frozen=True)
class Section:
    kind: str
    label: str
    items: list


def kind_of(obj) -> str:
    for kind, model in MODELS.items():
        if isinstance(obj, model):
            return kind
    raise TypeError(f"{type(obj).__name__} can't be saved")


def find(kind: str, object_id: str):
    """The course, professor, or club with this id, or None if there isn't one."""
    model = MODELS.get(kind)
    if model is None:
        return None
    try:
        oid = ObjectId(object_id)
    except (InvalidId, TypeError):
        return None
    return model.objects.filter(pk=oid).first()


def is_saved(user, obj) -> bool:
    if not user.is_authenticated:
        return False
    return SavedItem.objects.filter(user=user, kind=kind_of(obj), object_id=obj.pk).exists()


def toggle(user, obj) -> bool:
    """Save ``obj`` for ``user``, or unsave it if it's already saved.

    Returns True if it is saved afterwards.
    """
    kind = kind_of(obj)
    existing = SavedItem.objects.filter(user=user, kind=kind, object_id=obj.pk)
    if existing.exists():
        existing.delete()
        return False
    # A double-click may have saved it a moment ago; it is saved either way.
    with suppress(IntegrityError):
        SavedItem.objects.create(user=user, kind=kind, object_id=obj.pk)
    return True


def cabinet(user) -> list[Section]:
    """The student's saved items by kind, newest first. Empty kinds are left out.

    Items whose course, professor, or club no longer exists are skipped.
    """
    saved = list(SavedItem.objects.filter(user=user).order_by("-saved_at"))
    sections = []
    for kind, label in SECTION_ORDER:
        ids = [item.object_id for item in saved if item.kind == kind]
        if not ids:
            continue
        found = {obj.pk: obj for obj in MODELS[kind].objects.filter(pk__in=ids)}
        items = [found[oid] for oid in ids if oid in found]
        if items:
            sections.append(Section(kind=kind, label=label, items=items))
    return sections


def count(user) -> int:
    return SavedItem.objects.filter(user=user).count() if user.is_authenticated else 0
