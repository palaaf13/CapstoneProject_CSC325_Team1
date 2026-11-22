from django.urls import path

from . import views

app_name = "ratings"

urlpatterns = [
    path("courses/<str:code>/rate/", views.course_rating_create, name="course_rating_create"),
]
