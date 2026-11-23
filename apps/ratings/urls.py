from django.urls import path

from . import views

app_name = "ratings"

urlpatterns = [
    path("courses/<str:code>/rate/", views.rate_course, name="rate_course"),
    path("professors/<slug:slug>/rate/", views.rate_professor, name="rate_professor"),
]
