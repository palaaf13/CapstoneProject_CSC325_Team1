from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("feed/", views.feed, name="feed"),
    path("feed/new/", views.post_create, name="post_create"),
    # Threads about a professor or course live under that page's own URL.
    path(
        "professors/<slug:slug>/threads/new/",
        views.professor_post_create,
        name="professor_post_create",
    ),
    path(
        "courses/<str:code>/threads/new/",
        views.course_post_create,
        name="course_post_create",
    ),
    path("feed/posts/<str:post_id>/", views.post_detail, name="post_detail"),
    path("feed/posts/<str:post_id>/edit/", views.post_edit, name="post_edit"),
    path("feed/posts/<str:post_id>/remove/", views.post_remove, name="post_remove"),
    path("feed/posts/<str:post_id>/vote/", views.post_vote, name="post_vote"),
    path("feed/posts/<str:post_id>/comments/", views.comment_create, name="comment_create"),
    path(
        "feed/posts/<str:post_id>/comments/<str:comment_id>/remove/",
        views.comment_remove,
        name="comment_remove",
    ),
]
