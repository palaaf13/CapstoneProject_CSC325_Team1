from django.urls import path

from . import views

app_name = "campus"

urlpatterns = [
    path("clubs/", views.clubs, name="clubs"),
    # RamCentral's own key for the organization: stable across re-imports,
    # readable, and shareable. A malformed slug 404s at the routing layer.
    path("clubs/<slug:slug>/", views.club_detail, name="club_detail"),
    path("clubs/<slug:slug>/events/new/", views.club_event_new, name="club_event_new"),
    path(
        "clubs/<slug:slug>/events/<str:event_id>/delete/",
        views.club_event_delete,
        name="club_event_delete",
    ),
    path("events/", views.events, name="events"),
    path("jobs/", views.jobs, name="jobs"),
    path("parking/", views.parking, name="parking"),
    path("facilities/", views.facilities, name="facilities"),
]
