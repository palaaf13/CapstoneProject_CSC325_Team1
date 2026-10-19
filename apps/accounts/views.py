"""Student account registration views."""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.accounts import services
from apps.accounts.forms import RegistrationForm


def register(request: HttpRequest) -> HttpResponse:
    """Create and sign in a student whose email matches the college domain."""
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
                auth_login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                messages.success(request, "Your RamHub student account is ready.")
                return redirect("home")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})
