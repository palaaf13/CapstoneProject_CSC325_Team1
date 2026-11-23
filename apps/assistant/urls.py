from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("rambo/", views.rambo_page, name="rambo"),
    path("rambo/ask/", views.rambo_ask, name="ask"),
    path("rambo/clear/", views.rambo_clear, name="clear"),
]
