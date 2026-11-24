from django.urls import path

from . import views
from .parking_weather import parking_weather

app_name = "campus"

urlpatterns = [
    path("clubs/", views.clubs, name="clubs"),
    path("jobs/", views.jobs, name="jobs"),
    path("parking/", views.parking, name="parking"),
    path("parking/weather/", parking_weather, name="parking_weather"),
    path("facilities/", views.facilities, name="facilities"),
]
