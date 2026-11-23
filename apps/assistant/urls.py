from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("courses/<str:code>/summary/", views.course_summary, name="course_summary"),
    path("professors/<slug:slug>/summary/", views.professor_summary, name="professor_summary"),
]
