from django.urls import path

from . import views

app_name = "saved"

urlpatterns = [
    path("saved/", views.cabinet, name="cabinet"),
    path("saved/toggle/", views.toggle, name="toggle"),
]
