"""Student account registration views."""

import logging
from smtplib import SMTPException

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts import services
from apps.accounts.forms import RegistrationForm
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
