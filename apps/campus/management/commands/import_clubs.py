"""
Import real Farmingdale State College clubs from RamCentral.

Source: apps/campus/seed_data/farmingdale_clubs.ndjson (one JSON object per
line), exported from RamCentral — the club directory the college runs and that
farmingdale.edu/ramcentral points to. See the .README.md beside it for the field
reference and caveats, and scrape_clubs.py to regenerate it.

The same rules as the other imports, applied to clubs:

1. **It never invents a fact.** RamCentral publishes no meeting times, so
   meeting_info is left alone rather than guessed. A blank field in the export
   is a blank field here.
2. **It never imports people.** RamCentral hides a club's officers behind a
   sign-in, so the export does not carry them and neither does this. The only
   contact stored is the organization's own published email.
3. **It only lists organizations RamCentral marks Active.**

There is one place it adds something of ours. RamCentral has no technology
category, so seed_data/ramhub_categories.json lists, by slug, the clubs RamHub
files under "Technology". That is RamHub's grouping, not the college's, and the
file and both READMEs say so. Keep it small, and keep it the only such place.

Idempotent on `slug`, RamCentral's own key for the organization.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_slug

from apps.campus.models import Club

SEED_DATA = Path(__file__).resolve().parent.parent.parent / "seed_data"
DATA_FILE = SEED_DATA / "farmingdale_clubs.ndjson"
RAMHUB_CATEGORIES_FILE = SEED_DATA / "ramhub_categories.json"


def load_ramhub_categories(path: Path = RAMHUB_CATEGORIES_FILE) -> dict[str, list[str]]:
    """RamHub's own additions: {slug: [category, ...]}. Keys starting with "_" are notes."""
    mapping = json.loads(path.read_text(encoding="utf-8"))
    return {slug: names for slug, names in mapping.items() if not slug.startswith("_")}


RAMHUB_CATEGORIES = load_ramhub_categories()

# RamCentral also lists college offices ("Residence Life") and its own umbrella
# branches beside the student organizations. They are not clubs, so they are
# skipped unless --include-offices asks for them.
OFFICE_TYPES = {"Offices / Departments", "Branch"}

# RamCentral files an organization two ways: under categories, and under one
# organization type. Some types are groupings a student would browse by, and
# RamCentral does not always repeat them as a category — 14 organizations have
# the type "Club Sports" but only 8 carry the category. Folding these types into
# the categories is what makes the directory's filter complete. The three Greek
# types share one entry, as they do under the college's Fraternity & Sorority
# Life office. Types not listed here ("Recognized Student Organizations",
# "Default") say nothing a filter could use.
TYPE_CATEGORY = {
    "Club Sports": "Club Sports",
    "Committees & Programs": "Committees & Programs",
    "Fraternities": "Fraternities & Sororities",
    "Panhellenic Sororities": "Fraternities & Sororities",
    "Sororities": "Fraternities & Sororities",
    "Offices / Departments": "Offices / Departments",
}

# Display order for a club's social links.
LINK_ORDER = ("instagram", "facebook", "linkedin", "youtube", "twitter")

# RamCentral requires a summary, so a club with nothing to say types something
# to get past the form. These are the ones in the export; they are stored as
# blank so a club page says "no description" instead of "PLEASE FILL THIS OUT".
# Matched whole and case-insensitively — this never trims a real description.
PLACEHOLDER_TEXT = {"n/a", "na", "tbd", "xxx", "please fill this out"}
# "**New for Fall 2026**": a marker left in the summary of a newly registered
# club. It says nothing about what the club does.
NEW_CLUB_MARKER = re.compile(r"^\W*new for (fall|spring|summer|winter) \d{4}\W*$", re.IGNORECASE)


def real_text(value: str | None) -> str:
    """A summary or description, or "" when the field only holds a placeholder."""
    text = (value or "").strip()
    has_words = any(char.isalnum() for char in text)
    if not has_words or text.casefold() in PLACEHOLDER_TEXT or NEW_CLUB_MARKER.match(text):
        return ""
    return text


def categories_for(row: dict) -> list[str]:
    """
    Everything a club is filed under, A-Z.

    RamCentral's categories for the row, its organization type where that is a
    grouping, and — the only part that is ours — RamHub's additions for its slug.
    """
    names = {name.strip() for name in row.get("categories") or [] if name and name.strip()}
    if grouping := TYPE_CATEGORY.get((row.get("org_type") or "").strip()):
        names.add(grouping)
    names.update(RAMHUB_CATEGORIES.get((row.get("slug") or "").strip(), []))
    return sorted(names)


def web_url(value: str | None) -> str:
    """
    An http(s) URL, or "".

    These end up in an href, and nothing on Club validates them on save. A
    `javascript:` link in a hand-edited export must not reach a template.
    """
    url = (value or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


def links_for(row: dict) -> list[str]:
    links = {key: web_url(url) for key, url in (row.get("links") or {}).items()}
    ordered = [links[key] for key in LINK_ORDER if links.get(key)]
    return ordered + [url for key, url in links.items() if key not in LINK_ORDER and url]


class Command(BaseCommand):
    help = "Import clubs from the RamCentral export. Idempotent."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--file", default=str(DATA_FILE), help="Path to the .ndjson export.")
        parser.add_argument(
            "--include-offices",
            action="store_true",
            help="Also import college offices and RamCentral branches. Off by default.",
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help="DESTRUCTIVE: delete clubs absent from the file. Requires --yes.",
        )
        parser.add_argument("--yes", action="store_true", help="Confirm a destructive --prune.")

    def handle(self, *args: Any, **options: Any) -> None:
        rows, skipped = self._load(
            Path(options["file"]), include_offices=options["include_offices"]
        )
        if not rows:
            raise CommandError("No matching rows in the club export.")

        created, updated = self._upsert(rows)
        pruned = 0
        if options["prune"]:
            pruned = self._prune({row["slug"] for row in rows}, confirmed=options["yes"])

        self._report(created, updated, pruned, len(rows), skipped)

    # -- steps -------------------------------------------------------------

    def _load(self, path: Path, *, include_offices: bool) -> tuple[list[dict], int]:
        if not path.exists():
            raise CommandError(f"Club export not found at {path}")

        rows, seen, skipped = [], set(), 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CommandError(f"{path}:{number} is not valid JSON: {exc}") from exc

            slug = (row.get("slug") or "").strip()
            if not slug:
                raise CommandError(f"{path}:{number} has no slug; it cannot be keyed.")
            if slug in seen:
                raise CommandError(f"{path}:{number} repeats slug {slug!r}.")
            seen.add(slug)
            try:
                # The slug becomes the club's URL; one that cannot be reversed
                # would take the whole directory page down with it.
                validate_slug(slug)
            except ValidationError as exc:
                raise CommandError(f"{path}:{number} slug {slug!r} is not URL-safe.") from exc
            row["slug"] = slug
            if not (row.get("name") or "").strip():
                raise CommandError(f"{path}:{number} ({slug}) has no name.")

            is_office = (row.get("org_type") or "").strip() in OFFICE_TYPES
            if (is_office and not include_offices) or row.get("status") != "Active":
                skipped += 1
                continue
            rows.append(row)
        return rows, skipped

    def _upsert(self, rows: list[dict]) -> tuple[int, int]:
        created = updated = 0
        for row in rows:
            _, was_created = Club.objects.update_or_create(
                slug=row["slug"],
                # meeting_info is absent on purpose: RamCentral does not publish
                # it, so whatever is stored survives a re-import untouched.
                defaults=self._defaults(row),
            )
            created += was_created
            updated += not was_created
        return created, updated

    def _defaults(self, row: dict) -> dict[str, Any]:
        retrieved = row.get("source_retrieved")
        return {
            "name": row["name"].strip(),
            "short_name": (row.get("short_name") or "").strip(),
            "summary": real_text(row.get("summary")),
            "description": real_text(row.get("description")),
            "org_type": (row.get("org_type") or "").strip(),
            "categories": categories_for(row),
            "contact_email": row.get("contact_email") or "",
            "phone": row.get("phone") or "",
            "location": row.get("location") or "",
            "website": web_url(row.get("website")),
            "links": links_for(row),
            "logo_url": web_url(row.get("logo_url")),
            "source_url": web_url(row.get("source_url")),
            "source_retrieved": date.fromisoformat(retrieved) if retrieved else None,
        }

    def _prune(self, keep: set[str], *, confirmed: bool) -> int:
        stale = Club.objects.exclude(slug__in=keep)
        count = stale.count()
        if not count:
            return 0
        if not confirmed:
            raise CommandError(
                f"--prune would delete {count} club(s) not in the export. "
                "Re-run with --yes if that is what you want."
            )
        stale.delete()
        return count

    # -- output ------------------------------------------------------------

    def _report(self, created: int, updated: int, pruned: int, total: int, skipped: int) -> None:
        self.stdout.write("")
        self.stdout.write(f"  Read        {total:>5} organizations from the RamCentral export")
        self.stdout.write(f"  Skipped     {skipped:>5} college offices or inactive records")
        self.stdout.write(f"  Clubs       {created:>5} created  {updated:>5} updated")
        if pruned:
            self.stdout.write(self.style.WARNING(f"  Pruned      {pruned:>5} not in the file"))
        grouped = Club.objects.filter(slug__in=list(RAMHUB_CATEGORIES)).count()
        self.stdout.write("")
        self.stdout.write(f"  Totals      {Club.objects.count()} clubs")
        self.stdout.write(
            f"  RamHub      {grouped:>5} given a category of RamHub's own (Technology)"
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "RamCentral's facts as published; the only thing added is RamHub's own "
                "grouping above. No officers were imported and no meeting times were "
                "written — RamCentral does not publish either."
            )
        )
