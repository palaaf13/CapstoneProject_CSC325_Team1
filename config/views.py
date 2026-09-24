"""
Site-level pages that do not belong to a product app.

Kept here deliberately so INSTALLED_APPS matches the layout in CLAUDE.md
exactly — no extra "core"/"pages" app.
"""

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.catalog import landing as catalog_landing


def home(request: HttpRequest) -> HttpResponse:
    """The front door. Cinematic on purpose; the directories behind it stay dense."""
    return render(request, "pages/home.html", catalog_landing.landing_snapshot())


def styleguide(request: HttpRequest) -> HttpResponse:
    """Every shared UI pattern on one page. Review the visual system here."""
    return render(request, "pages/styleguide.html")


def styleguide_htmx_demo(request: HttpRequest) -> HttpResponse:
    """
    Target of the style guide's HTMX demo.

    Returns an HTML fragment (not JSON) — that is the HTMX contract used
    everywhere in this project for partial page updates.
    """
    return render(
        request,
        "partials/htmx_demo_result.html",
        {"loaded_at": timezone.localtime()},
    )


def about(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/about.html")


def guidelines(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/guidelines.html")


class RamHubAuthenticationForm(AuthenticationForm):
    """Apply the shared form controls to Django's authentication fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "field-input", "autocomplete": "current-password"}
        )


class RamHubLoginView(LoginView):
    """Render the shared sign-in screen and authenticate submitted credentials."""

    template_name = "pages/sign_in.html"
    form_class = RamHubAuthenticationForm
    redirect_authenticated_user = True


sign_in = RamHubLoginView.as_view()
