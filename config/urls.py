"""RamHub URL configuration."""

from django.contrib import admin
from django.urls import include, path

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
    path("login/", account_views.sign_in, name="login"),
    path("logout/", account_views.sign_out, name="logout"),
    path("register/", account_views.register, name="register"),
    path(
        "confirm-email/<str:uidb64>/<str:token>/",
        account_views.confirm_email,
        name="confirm_email",
    ),
    # Always the signed-in student's own profile: no id in the URL to tamper with.
    path("profile/", account_views.profile, name="profile"),
    path("profile/edit/", account_views.profile_edit, name="profile_edit"),
]
