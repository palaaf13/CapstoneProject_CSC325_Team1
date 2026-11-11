"""RamHub URL configuration."""

from django.contrib import admin
from django.urls import include, path

from apps.accounts import profile_views
from apps.accounts import views as account_views

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # The feed is the front page.
    path("", views.home, name="home"),
    path("", include("apps.community.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.campus.urls")),
    path("", include("apps.saved.urls")),
    # Site-level pages
    path("styleguide/", views.styleguide, name="styleguide"),
    path("styleguide/htmx-demo/", views.styleguide_htmx_demo, name="styleguide_htmx_demo"),
    path("about/", views.about, name="about"),
    path("guidelines/", views.guidelines, name="guidelines"),
    path("search/", views.search, name="search"),
    path("login/", account_views.sign_in, name="login"),
    path("logout/", account_views.sign_out, name="logout"),
    path("register/", account_views.register, name="register"),
    path(
        "confirm-email/<str:uidb64>/<str:token>/",
        account_views.confirm_email,
        name="confirm_email",
    ),
    # Password reset (Django's own token views, RamHub templates).
    path(
        "password-reset/", account_views.PasswordResetRequestView.as_view(), name="password_reset"
    ),
    path(
        "password-reset/sent/",
        account_views.PasswordResetSentView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<str:uidb64>/<str:token>/",
        account_views.PasswordResetSetView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/done/",
        account_views.PasswordResetFinishedView.as_view(),
        name="password_reset_complete",
    ),
    # Always the signed-in student's own profile: no id in the URL to tamper with.
    path("profile/", profile_views.profile, name="profile"),
    path("profile/posts/", profile_views.profile_posts, name="profile_posts"),
    path("profile/edit/", profile_views.profile_edit, name="profile_edit"),
    path("profile/settings/privacy/", profile_views.profile_privacy, name="profile_privacy"),
    path("profile/settings/password/", profile_views.profile_password, name="profile_password"),
    path("profile/settings/account/", profile_views.profile_account, name="profile_account"),
    path(
        "profile/settings/account/sign-out-others/",
        profile_views.sign_out_other_devices,
        name="sign_out_other_devices",
    ),
    path(
        "profile/settings/account/delete/",
        profile_views.delete_account,
        name="delete_account",
    ),
]
