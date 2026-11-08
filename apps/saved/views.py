"""The filing cabinet page and the Save button's endpoint."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from . import services


def _safe_next(request: HttpRequest) -> str | None:
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return None


@login_required
def cabinet(request: HttpRequest) -> HttpResponse:
    """Everything the signed-in student has saved."""
    return render(request, "saved/cabinet.html", {"sections": services.cabinet(request.user)})


@require_POST
def toggle(request: HttpRequest) -> HttpResponse:
    """Save or unsave one course, professor, or club.

    HTMX gets the button back in its new state; a plain form post goes back to
    the page it came from.
    """
    if not request.user.is_authenticated:
        # Usually a session that expired while the page was open. Send the
        # whole page to sign-in (and back), rather than letting HTMX swap the
        # sign-in page into the button.
        login_url = f"{reverse('login')}?{urlencode({'next': _safe_next(request) or reverse('saved:cabinet')})}"
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = login_url
            return response
        return redirect(login_url)

    obj = services.find(request.POST.get("kind", ""), request.POST.get("object_id", ""))
    if obj is None:
        raise Http404("Nothing to save with that id")
    saved = services.toggle(request.user, obj)
    next_url = _safe_next(request)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "saved/partials/save_button.html",
            {"item": obj, "kind": services.kind_of(obj), "is_saved": saved, "next": next_url or ""},
        )
    return redirect(next_url or "saved:cabinet")
