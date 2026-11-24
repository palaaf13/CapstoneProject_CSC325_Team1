"""The Report page: pick a reason, add an optional note, go back to the item."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from . import services
from .forms import ReportForm

ALREADY_REPORTED = "You already reported this. The moderators will take a look."
THANKS = "Thanks for the report. The moderators will take a look."


@login_required
def report(
    request: HttpRequest, target_type: str, target_id: str, parent_id: str | None = None
) -> HttpResponse:
    """GET shows the form; POST files the report and returns to the item.

    ``target_type`` comes from urls.py, never from the visitor. The ids come from
    the URL and are looked up, not trusted: an unknown or removed item is a 404.
    """
    target = services.find_target(target_type, target_id, parent_id)
    if target is None:
        raise Http404("Nothing to report with that id.")
    if services.is_own(request.user, target):
        raise PermissionDenied("You can't report your own content.")
    if services.has_reported(request.user, target):
        messages.info(request, ALREADY_REPORTED)
        return redirect(target.back_url)

    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.file_report(request.user, target, **form.cleaned_data)
        except services.AlreadyReported:
            messages.info(request, ALREADY_REPORTED)
        else:
            messages.success(request, THANKS)
        return redirect(target.back_url)

    return render(request, "moderation/report_form.html", {"form": form, "target": target})
