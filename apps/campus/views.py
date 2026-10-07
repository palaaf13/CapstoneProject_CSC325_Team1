"""
Campus pages. Views parse the request, call a service, and render.

The club directory follows the catalog directories: a plain GET form first, so
it works with JavaScript off, with HTMX swapping the same partials on top.

These pages are public for now. Phase 2 puts them behind the college-email gate.
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from . import services
from .forms import ClubDirectoryForm, ClubQuery
from .models import Club


def _page_url(query: ClubQuery, page_number: int) -> str:
    """Query string for the next page, preserving the current search and category."""
    params: dict[str, str | int] = {"page": page_number, "append": 1}
    if query.q:
        params["q"] = query.q
    if query.category:
        params["category"] = query.category
    return "?" + urlencode(params)


def _club_template(request: HttpRequest, query: ClubQuery) -> str:
    """
    Pick the right slice of the page for the request.

    append  -> just the next cards, swapped in after the current ones
    HTMX    -> the whole results region (a new search or category)
    plain   -> the full page

    A history restore is the exception: when the back button lands on a URL
    htmx has no snapshot for, it re-requests it with HX-Request set *and* swaps
    the response into <body>. Answering that with a fragment would replace the
    whole page with a list of cards.
    """
    is_htmx = request.headers.get("HX-Request") == "true"
    is_restore = request.headers.get("HX-History-Restore-Request") == "true"
    if not is_htmx or is_restore:
        return "campus/clubs.html"
    return (
        "campus/partials/club_cards.html" if query.append else "campus/partials/club_results.html"
    )


def clubs(request: HttpRequest) -> HttpResponse:
    """The club directory: search, filter by category, paginate."""
    categories = services.club_categories()
    form = ClubDirectoryForm(request.GET, categories=[name for name, _ in categories])
    query = form.to_query()

    results = services.search_clubs(q=query.q, category=query.category)
    page = Paginator(results, services.PAGE_SIZE).get_page(query.page)

    context = {
        "query": query,
        "page_obj": page,
        "total": page.paginator.count,
        "club_count": Club.objects.count(),
        "categories": categories,
        "next_page_url": _page_url(query, page.next_page_number()) if page.has_next() else None,
        "is_filtered": bool(query.q or query.category),
        # "Other" is the clubs in no category; the results line words it that way.
        "is_other": query.category == services.OTHER,
        # Where the empty state's "clear" button goes — the unfiltered directory.
        "clear_url": reverse("campus:clubs"),
        "retrieved": services.last_retrieved(),
    }
    return render(request, _club_template(request, query), context)


def club_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One club, keyed on its RamCentral slug."""
    club = get_object_or_404(Club, slug=slug)
    return render(request, "campus/club_detail.html", {"club": club})


def jobs(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/jobs.html")


def parking(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/parking.html")


def facilities(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/facilities.html")
