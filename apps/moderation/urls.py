"""One view serves every kind of report. The kind is fixed here, per URL."""

from django.urls import path

from . import views
from .models import Report

app_name = "moderation"

T = Report.TargetType

urlpatterns = [
    path(
        "report/post/<str:target_id>/",
        views.report,
        {"target_type": T.POST},
        name="report_post",
    ),
    # A comment lives inside its post, so its URL carries both ids.
    path(
        "report/comment/<str:parent_id>/<str:target_id>/",
        views.report,
        {"target_type": T.COMMENT},
        name="report_comment",
    ),
    path(
        "report/course-rating/<str:target_id>/",
        views.report,
        {"target_type": T.COURSE_RATING},
        name="report_course_rating",
    ),
    path(
        "report/professor-rating/<str:target_id>/",
        views.report,
        {"target_type": T.PROFESSOR_RATING},
        name="report_professor_rating",
    ),
]
