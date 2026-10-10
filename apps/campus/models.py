"""
Campus information: clubs today; jobs, parking, and facilities as they are built.

Club records are imported from RamCentral, the college's own club directory —
see management/commands/import_clubs.py and seed_data/farmingdale_clubs.README.md.
They follow the same rule as the course and professor directories: this is the
college's data, not ours. The import overwrites every field it owns on each run
(all but meeting_info), and nothing in the app should edit them.
"""

from urllib.parse import urlsplit

from django.db import models
from django_mongodb_backend.fields import ArrayField

# How a link's host is named on a club page. Anything not listed is simply a
# "Website" — clubs point that field at everything from a national chapter's
# site to a GroupMe invite, and the label should say which.
LINK_LABELS = {
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "linkedin.com": "LinkedIn",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "twitter.com": "X (Twitter)",
    "x.com": "X (Twitter)",
    "groupme.com": "GroupMe",
    "linktr.ee": "Linktree",
    "discord.gg": "Discord",
    "discord.com": "Discord",
}

# RamCentral names its organization types in the plural, as headings. On a single
# club they read better in the singular. Types with no entry ("Default",
# "Branch") are RamCentral housekeeping and are not shown at all.
TYPE_LABELS = {
    "Recognized Student Organizations": "Recognized student organization",
    "Club Sports": "Club sport",
    "Fraternities": "Fraternity",
    "Panhellenic Sororities": "Panhellenic sorority",
    "Sororities": "Sorority",
    "Committees & Programs": "Committee or program",
    "Offices / Departments": "College office",
}

# Words that do not earn a letter in an acronym: "Society of Hispanic
# Professional Engineers" is SHPE, not SOHPE. Used for monograms here and for
# acronym matching in services.search_clubs.
LITTLE_WORDS = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}
MONOGRAM_TONES = 4


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("web.")


def link_label(url: str) -> str:
    """Name a link by where it goes: https://www.instagram.com/x -> "Instagram"."""
    return LINK_LABELS.get(_host(url), "Website")


def link_display(url: str) -> str:
    """A link without its plumbing: https://www.instagram.com/x/ -> "instagram.com/x"."""
    parts = urlsplit(url)
    return (_host(url) + parts.path.rstrip("/")) or url


class Club(models.Model):
    # RamCentral's own key for the organization ("gaming-club"). It is the URL
    # and the import's natural key, stable across re-imports.
    slug = models.SlugField(max_length=120, unique=True)

    name = models.CharField(max_length=200)
    # Lowercased name. MongoDB orders strings by code point, which files
    # "FSC Music Club" ahead of "Farmingdale Car Club"; the directory sorts on
    # this instead. Maintained by save().
    sort_name = models.CharField(max_length=200, editable=False)
    short_name = models.CharField(max_length=64, blank=True, help_text="e.g. SGA.")
    summary = models.TextField(blank=True, help_text="RamCentral's one-paragraph blurb.")
    description = models.TextField(blank=True, help_text="The organization's own About text.")

    # RamCentral's organization type, verbatim ("Club Sports", "Fraternities").
    org_type = models.CharField(max_length=80, blank=True)
    # What the directory filters on: RamCentral's categories, plus the
    # organization type where that is a grouping in its own right, plus the few
    # RamHub adds itself (seed_data/ramhub_categories.json — "Technology"). A
    # club can sit in several, and some sit in none; those are what the
    # directory's "Other" filter shows. See import_clubs.categories_for.
    categories = ArrayField(models.CharField(max_length=80), default=list, blank=True)

    # Not published by RamCentral, so the import leaves it blank. It is in the
    # model because CLAUDE.md's schema has it; it stays empty until there is a
    # real source for it. Do not fill it with a guess.
    meeting_info = models.TextField(blank=True)

    contact_email = models.EmailField(blank=True, help_text="The organization's public contact.")
    phone = models.CharField(max_length=32, blank=True)
    location = models.CharField(max_length=200, blank=True)
    website = models.URLField(max_length=300, blank=True)
    links = ArrayField(models.URLField(max_length=300), default=list, blank=True)
    # Stored, not displayed. Several club logos contain the college's own marks,
    # and CLAUDE.md says to ask before using one.
    logo_url = models.URLField(max_length=300, blank=True)

    source_url = models.URLField(max_length=300, blank=True, help_text="RamCentral page.")
    source_retrieved = models.DateField(
        null=True, blank=True, help_text="When the RamCentral record was last pulled."
    )

    class Meta:
        ordering = ["sort_name"]
        indexes = [
            # The directory's default order.
            models.Index(fields=["sort_name"], name="campus_club_sort_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        self.sort_name = self.name.casefold()
        # update_or_create saves only the fields it was handed; keep the sort
        # key travelling with the name it is derived from.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "sort_name"}
        super().save(*args, **kwargs)

    @property
    def monogram(self) -> str:
        """
        Up to four letters standing in for a logo.

        The club's own abbreviation when it has a short one ("SGA", "IEEE"),
        otherwise the initials of its name.
        """
        short = self.abbreviation
        if short and len(short) <= 4 and " " not in short:
            return short.upper()
        words = [w for w in self.name.replace("-", " ").split() if w[0].isalnum()]
        initials = [w[0] for w in words if w.lower() not in LITTLE_WORDS] or [w[0] for w in words]
        return "".join(initials[:4]).upper()

    @property
    def abbreviation(self) -> str:
        """
        The club's short name, when it is one worth showing beside the full name.

        Blank when it only repeats the name, and blank when it plainly belongs
        to a different name: RamCentral records get renamed without the short
        name following, so the Artificial Intelligence Club still carries "cs",
        and "CS" beside that name reads as a bug. The test is the first letter.
        Greek-letter organizations are exempt from it — "ΚΣ" never shares a
        first letter with "Kappa Sigma".

        Display only. Search still matches the stored short_name, stale or not.
        """
        short, name = self.short_name.strip(), self.name.strip()
        if not short or short.casefold() == name.casefold():
            return ""
        if short.isascii() and short[0].casefold() != name[:1].casefold():
            return ""
        return short

    @property
    def monogram_tone(self) -> int:
        """
        Which of the four monogram colourways this club gets (1-4).

        Decorative only — it varies the grid so 100 tiles do not read as one
        block. Derived from the slug so it is stable across requests, renames
        and re-imports, and says nothing about the club.
        """
        return sum(ord(char) for char in self.slug) % MONOGRAM_TONES + 1

    @property
    def type_label(self) -> str:
        """The organization type as a label for one club, or "" when it says nothing."""
        return TYPE_LABELS.get(self.org_type, "")

    @property
    def about(self) -> str:
        """The club's own description, falling back to RamCentral's shorter summary."""
        return self.description or self.summary

    @property
    def blurb(self) -> str:
        """The few lines a card shows: the summary, or failing that the description."""
        return self.summary or self.description

    @property
    def link_items(self) -> list[dict[str, str]]:
        """Website first, then social links, each labelled for display."""
        urls = [self.website, *self.links] if self.website else list(self.links)
        return [
            {"label": link_label(url), "display": link_display(url), "url": url} for url in urls
        ]

    @property
    def channels(self) -> list[str]:
        """How a student can reach this club, as short labels: ["Instagram", "Email"]."""
        labels = [item["label"] for item in self.link_items]
        if self.contact_email:
            labels.append("Email")
        return list(dict.fromkeys(labels))
