"""Student account views: registration, sign-in, and profiles."""

import logging
from smtplib import SMTPException

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    url_has_allowed_host_and_scheme,
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)
from django.views.decorators.http import require_POST

from apps.accounts import services
from apps.accounts.forms import ProfileForm, RegistrationForm, SignInForm
from apps.accounts.models import User

logger = logging.getLogger(__name__)


def register(request: HttpRequest) -> HttpResponse:
    """Create an inactive student account and email its confirmation link."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = services.register_user(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    display_name=form.cleaned_data["display_name"],
                    password=form.cleaned_data["password1"],
                )
            except ValidationError as error:
                form.add_error("email", error)
            else:
                token = services.email_confirmation_token.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                confirmation_path = reverse(
                    "confirm_email",
                    kwargs={"uidb64": uidb64, "token": token},
                )
                confirmation_url = request.build_absolute_uri(confirmation_path)
                try:
                    services.send_registration_confirmation(user, confirmation_url)
                except (OSError, SMTPException, services.EmailDeliveryError):
                    logger.exception("Could not send confirmation email for user %s", user.pk)
                    user.delete()
                    form.add_error(
                        None,
                        "We couldn't send the confirmation email. Please try again later.",
                    )
                else:
                    messages.success(
                        request,
                        "Check your Farmingdale email for a link to confirm your account.",
                    )
                    return redirect("login")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def confirm_email(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Activate an account only when its confirmation token is valid."""
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        user_id = ""

    try:
        user = User.objects.filter(pk=user_id).first() if user_id else None
    except (TypeError, ValueError, ValidationError):
        user = None

    if user is not None and services.activate_user(user, token):
        messages.success(request, "Your email is confirmed. You can now sign in.")
    else:
        messages.error(
            request,
            "This confirmation link is invalid or expired. You may sign in if your email "
            "was already confirmed.",
        )
    return redirect("login")


def _safe_next_url(request: HttpRequest) -> str | None:
    """The ?next= page to return to, only if it points back into RamHub."""
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def sign_in(request: HttpRequest) -> HttpResponse:
    """Sign a confirmed student in with their college email and password."""
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request) or "profile")

    if request.method == "POST":
        form = SignInForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect(_safe_next_url(request) or "profile")
    else:
        form = SignInForm(request)

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": _safe_next_url(request) or ""},
    )


@require_POST
def sign_out(request: HttpRequest) -> HttpResponse:
    """Sign out. POST-only so a link or image on another site can't sign you out."""
    auth_logout(request)
    return redirect("home")


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    """Show the signed-in student their own profile."""
    return render(request, "accounts/profile.html", {"profile_user": request.user})


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    """Let the signed-in student edit their own profile.

    The account edited is always request.user; no id is read from the request,
    so a student cannot edit anyone else.
    """
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            services.update_profile(request.user, form.cleaned_data)
            messages.success(request, "Your profile is saved.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "accounts/profile_edit.html", {"form": form})
