from django.urls import path

from . import views

app_name = "campus"

urlpatterns = [
    path("clubs/", views.clubs, name="clubs"),
    # RamCentral's own key for the organization: stable across re-imports,
    # readable, and shareable. A malformed slug 404s at the routing layer.
    path("clubs/<slug:slug>/", views.club_detail, name="club_detail"),
    path("jobs/", views.jobs, name="jobs"),
    path("parking/", views.parking, name="parking"),
    path("facilities/", views.facilities, name="facilities"),
]
