"""
Campus pages. Views parse the request, call a service, and render.

The club directory follows the catalog directories: a plain GET form first, so
it works with JavaScript off, with HTMX swapping the same partials on top.

These pages are public for now. Phase 2 puts them behind the college-email gate.
"""

from datetime import date
from urllib.parse import urlencode

from bson import ObjectId
from bson.errors import InvalidId
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.saved import services as saved

from . import services
from .forms import ClubDirectoryForm, ClubEventForm, ClubQuery
from .models import Club, ClubEvent


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
    return render(
        request,
        "campus/club_detail.html",
        {
            "club": club,
            "is_saved": saved.is_saved(request.user, club),
            "events": services.upcoming_events(club=club, limit=5),
        },
    )


# The Jobs, Parking, and Facilities guides copy facts from official FSC pages,
# each linked beside its section. This is the date they were last checked
# against those pages; update it whenever the guides are re-checked.
GUIDES_CHECKED = date(2026, 11, 7)


def jobs(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/jobs.html", {"checked": GUIDES_CHECKED})


def parking(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/parking.html", {"checked": GUIDES_CHECKED})


def facilities(request: HttpRequest) -> HttpResponse:
    return render(request, "campus/facilities.html", {"checked": GUIDES_CHECKED})


def events(request: HttpRequest) -> HttpResponse:
    """Every club's upcoming events, grouped by day."""
    return render(
        request,
        "campus/events.html",
        {"days": services.events_by_day(services.upcoming_events())},
    )


@login_required
def club_event_new(request: HttpRequest, slug: str) -> HttpResponse:
    """A signed-in student posts an upcoming event for one club."""
    club = get_object_or_404(Club, slug=slug)
    form = ClubEventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.club = club
        event.posted_by = request.user
        event.save()
        messages.success(request, f"Posted \u201c{event.title}\u201d to {club.name}.")
        return redirect("campus:club_detail", slug=club.slug)
    return render(request, "campus/event_form.html", {"club": club, "form": form})


@require_POST
@login_required
def club_event_delete(request: HttpRequest, slug: str, event_id: str) -> HttpResponse:
    """The student who posted an event (or staff) takes it down."""
    try:
        pk = ObjectId(event_id)
    except InvalidId as exc:
        raise Http404("No such event") from exc
    club = get_object_or_404(Club, slug=slug)
    event = get_object_or_404(ClubEvent, pk=pk, club=club)
    if event.posted_by_id != request.user.pk and not request.user.is_staff:
        # Same answer as a missing event: no hint that it exists.
        raise Http404("No such event")
    event.delete()
    messages.success(request, f"Removed \u201c{event.title}\u201d.")
    return redirect("campus:club_detail", slug=club.slug)
