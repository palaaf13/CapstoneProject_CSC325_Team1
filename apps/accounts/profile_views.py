"""The signed-in student's own profile and account settings.

Every view here acts on request.user. No id is read from the request, so a
student can only ever see or change their own account.
"""

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts import services
from apps.accounts.forms import (
    DeleteAccountForm,
    PrivacyForm,
    ProfileForm,
    RamHubPasswordChangeForm,
)

RECENT_POSTS_ON_OVERVIEW = 5
POSTS_PER_PAGE = 20

# (url name, label, group). The order here is the order in the profile nav.
PROFILE_NAV = (
    ("profile", "Overview", "Profile"),
    ("profile_posts", "Posts", "Profile"),
    ("profile_edit", "Edit profile", "Profile"),
    ("profile_privacy", "Privacy", "Settings"),
    ("profile_password", "Password", "Settings"),
    ("profile_account", "Account", "Settings"),
)


def _profile_nav(active: str) -> list[dict]:
    return [
        {"url": reverse(name), "label": label, "group": group, "is_active": name == active}
        for name, label, group in PROFILE_NAV
    ]


def _render(request: HttpRequest, template: str, active: str, context: dict) -> HttpResponse:
    context = {"profile_user": request.user, "profile_nav": _profile_nav(active), **context}
    return render(request, template, context)


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    """Overview: details, bio, and the latest few posts."""
    posts = services.recent_posts(request.user)
    return _render(
        request,
        "accounts/profile.html",
        "profile",
        {
            "recent_posts": list(posts[:RECENT_POSTS_ON_OVERVIEW]),
            "post_count": posts.count(),
        },
    )


@login_required
def profile_posts(request: HttpRequest) -> HttpResponse:
    """Every post this student has written, newest first."""
    paginator = Paginator(services.recent_posts(request.user), POSTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    return _render(request, "accounts/profile_posts.html", "profile_posts", {"page": page})


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            services.update_profile(request.user, form.cleaned_data)
            messages.success(request, "Your profile is saved.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)
    return _render(request, "accounts/profile_edit.html", "profile_edit", {"form": form})


@login_required
def profile_privacy(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = PrivacyForm(request.POST)
        if form.is_valid():
            services.set_profile_visibility(
                request.user, is_public=form.cleaned_data["is_profile_public"]
            )
            messages.success(request, "Your privacy setting is saved.")
            return redirect("profile_privacy")
    else:
        form = PrivacyForm(initial={"is_profile_public": request.user.is_profile_public})
    return _render(request, "accounts/profile_privacy.html", "profile_privacy", {"form": form})


@login_required
def profile_password(request: HttpRequest) -> HttpResponse:
    """Change the password. This session stays signed in; all others end."""
    if request.method == "POST":
        form = RamHubPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(
                request, "Your password is changed. Other devices have been signed out."
            )
            return redirect("profile_password")
    else:
        form = RamHubPasswordChangeForm(request.user)
    return _render(request, "accounts/profile_password.html", "profile_password", {"form": form})


@login_required
def profile_account(request: HttpRequest) -> HttpResponse:
    return _render(
        request,
        "accounts/profile_account.html",
        "profile_account",
        {"delete_form": DeleteAccountForm(request.user)},
    )


@login_required
@require_POST
def sign_out_other_devices(request: HttpRequest) -> HttpResponse:
    services.sign_out_other_sessions(request, request.user)
    messages.success(request, "Every other device is signed out. This one stays signed in.")
    return redirect("profile_account")


@login_required
@require_POST
def delete_account(request: HttpRequest) -> HttpResponse:
    form = DeleteAccountForm(request.user, request.POST)
    if not form.is_valid():
        return _render(
            request,
            "accounts/profile_account.html",
            "profile_account",
            {"delete_form": form},
        )
    services.delete_account(request.user)
    auth_logout(request)
    messages.success(request, "Your account is deleted.")
    return redirect("home")
