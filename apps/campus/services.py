"""
Campus business logic. Views parse the request, call these, and render.

The club directory is small — about a hundred records — and that shapes two
decisions here:

* A club's categories are an ArrayField of strings rather than a join table, so
  "clubs in this category" is a single ``categories__contains`` and the category
  counts come from one query.
* Search is ranked in Python, not in MongoDB. A plain ``icontains`` cannot tell
  "AI" the club from the "ai" inside "training", and ordering by relevance would
  need an aggregation pipeline. Reading a hundred clubs and scoring them is
  simpler and fast. Revisit this if the directory ever grows into the thousands.
"""

import re
from collections import Counter
from datetime import date

from django.db.models import F, QuerySet

from .models import LITTLE_WORDS, Club

# Divisible by 2 and by 3, the grid's two column counts, so a page of results
# never ends on a ragged row.
PAGE_SIZE = 24

# The filter for clubs that sit in no category at all. It is not a category and
# is never stored on a club — it is the absence of one.
OTHER = "Other"

# Letters and digits; everything else separates words. "Afro-Caribbean" is two.
_WORD_RE = re.compile(r"[^\W_]+")
# What a club's name ends with when it is not part of what people call it: the
# "AI Club" is the Artificial Intelligence Club, not the "AIC".
_GENERIC_ENDINGS = {"club", "society", "association", "organization", "team", "chapter", "inc"}
# Below this length a term has to be a whole word to match prose. Two letters
# turn up inside too many other words to mean anything as a prefix.
_MIN_PREFIX_LENGTH = 3


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
def club_categories() -> list[tuple[str, int]]:
    """
    Every category in use with the number of clubs in it, A-Z, then "Other".

    Counted in Python from one query. A club in three categories is counted in
    all three, so the counts add up to more than the number of clubs. "Other"
    counts the clubs in none, and is left out when there are no such clubs.
    """
    counts: Counter[str] = Counter()
    uncategorized = 0
    for categories in Club.objects.order_by().values_list("categories", flat=True):
        counts.update(categories or [])
        uncategorized += not categories
    return sorted(counts.items()) + ([(OTHER, uncategorized)] if uncategorized else [])


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.casefold())


def _acronyms(words: list[str]) -> set[str]:
    """
    What a name might be shortened to: its initials, with and without a generic
    last word. "Artificial Intelligence Club" gives {"aic", "ai"}.
    """
    significant = [word for word in words if word not in LITTLE_WORDS] or words
    trimmed = significant[:-1] if significant[-1:] and significant[-1] in _GENERIC_ENDINGS else []
    return {"".join(word[0] for word in group) for group in (significant, trimmed) if group}


def _in_prose(term: str, words: set[str]) -> bool:
    """A whole word, or the start of one when the term is long enough to mean something."""
    if term in words:
        return True
    return len(term) >= _MIN_PREFIX_LENGTH and any(word.startswith(term) for word in words)


def _term_rank(term: str, club: Club) -> int | None:
    """
    How well one search term matches a club. 0 is best; None is no match.

    0  the club's abbreviation, its acronym, or a whole word of its name
    1  the start of a word in its name
    2  somewhere inside its name
    3  its summary
    4  its description
    """
    name_words = _words(club.name)
    short_name = club.short_name.casefold()
    if term == short_name or term in name_words or term in _acronyms(name_words):
        return 0
    if any(word.startswith(term) for word in name_words):
        return 1
    if len(term) >= _MIN_PREFIX_LENGTH and (term in club.name.casefold() or term in short_name):
        return 2
    if _in_prose(term, set(_words(club.summary))):
        return 3
    if _in_prose(term, set(_words(club.description))):
        return 4
    return None


def _rank(terms: list[str], club: Club) -> int | None:
    """Total rank across every term, or None if any one of them matches nothing."""
    ranks = [_term_rank(term, club) for term in terms]
    return None if None in ranks else sum(ranks)


def search_clubs(*, q: str = "", category: str = "") -> QuerySet[Club] | list[Club]:
    """
    Filter the club directory.

    With no search terms: the category's clubs, A-Z, as a queryset.

    With search terms: a list, best match first and A-Z within a tie. Every
    whitespace-separated term has to match somewhere, so "hispanic engineers"
    finds the Society of Hispanic Professional Engineers and "dance engineers"
    finds nothing. See _term_rank for what counts as a better match — it is why
    "ai" leads with the Artificial Intelligence Club instead of every club whose
    summary happens to contain "training".
    """
    queryset = Club.objects.order_by("sort_name")

    if category == OTHER:
        queryset = queryset.filter(categories=[])
    elif category:
        queryset = queryset.filter(categories__contains=[category])

    terms = _words(q)
    if not terms:
        return queryset

    ranked = [(rank, club) for club in queryset if (rank := _rank(terms, club)) is not None]
    # sorted() is stable, so clubs with the same rank keep the queryset's A-Z order.
    return [club for _, club in sorted(ranked, key=lambda pair: pair[0])]


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------
def last_retrieved() -> date | None:
    """When the club data was last pulled from RamCentral, for the source note."""
    return (
        Club.objects.order_by(F("source_retrieved").desc(nulls_last=True))
        .values_list("source_retrieved", flat=True)
        .first()
    )
