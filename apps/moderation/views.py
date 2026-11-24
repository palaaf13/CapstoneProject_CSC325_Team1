"""
The Report page (RH-13): pick a reason, add an optional note, go back to the item.
The moderator queue (RH-14): review reports, then hide, restore, or dismiss.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import queue, services
from .forms import ModerationActionForm, ReportForm
from .models import MAX_NOTE_LENGTH, ModAction

ALREADY_REPORTED = "You already reported this. The moderators will take a look."
THANKS = "Thanks for the report. The moderators will take a look."

DONE = {
    ModAction.Action.HIDE: "Hidden. It's off the site and its reports are resolved.",
    ModAction.Action.RESTORE: "Restored. It's back on the site.",
    ModAction.Action.DISMISS: "Reports dismissed. The content stays up.",
}
BAD_REQUEST = "That action couldn't be read. Reload the queue and try again."


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


# -- the moderator queue (RH-14) ----------------------------------------------
# login_required sends signed-out visitors to sign in. The role check is then
# made here AND again inside queue.perform, so neither a hidden link nor a
# hand-written POST is the only thing standing in the way.
@login_required
@require_GET
def queue_page(request: HttpRequest) -> HttpResponse:
    if not queue.can_moderate(request.user):
        raise PermissionDenied("Only moderators can see the queue.")
    return render(
        request,
        "moderation/queue.html",
        {
            "items": queue.open_items(),
            "hidden": queue.hidden_items(),
            "log": queue.recent_actions(),
            "note_max": MAX_NOTE_LENGTH,
        },
    )


@login_required
@require_POST
def queue_action(request: HttpRequest) -> HttpResponse:
    """Hide, restore, or dismiss one item, then go back to the queue (POST only, CSRF-checked)."""
    if not queue.can_moderate(request.user):
        raise PermissionDenied("Only moderators can do that.")
    form = ModerationActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, BAD_REQUEST)
        return redirect("moderation:queue")
    try:
        done = queue.perform(request.user, **form.cleaned_data)
    except queue.ActionNotAllowed as problem:
        messages.error(request, str(problem))
    else:
        messages.success(request, DONE[done.action])
    return redirect("moderation:queue")
