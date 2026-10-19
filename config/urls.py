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
    # Site-level pages
    path("styleguide/", views.styleguide, name="styleguide"),
    path("styleguide/htmx-demo/", views.styleguide_htmx_demo, name="styleguide_htmx_demo"),
    path("about/", views.about, name="about"),
    path("guidelines/", views.guidelines, name="guidelines"),
    path("login/", views.login, name="login"),
    path("register/", account_views.register, name="register"),
    path(
        "confirm-email/<str:uidb64>/<str:token>/",
        account_views.confirm_email,
        name="confirm_email",
    ),
]
