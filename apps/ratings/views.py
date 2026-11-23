"""Rating pages. A student rates once per course; coming back edits that rating."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.catalog import services as catalog

from . import services
from .forms import CourseRatingForm


@login_required
def rate_course(request: HttpRequest, code: str) -> HttpResponse:
    course = catalog.get_course_by_code(code)
    if course is None:
        raise Http404(f"No course with code {code!r}")

    existing = services.course_rating_by(request.user, course)
    initial = {}
    if existing:
        initial = {
            "difficulty": existing.difficulty,
            "workload": existing.workload,
            "usefulness": existing.usefulness,
            "semester": existing.semester,
            "comment": existing.comment,
        }
    form = CourseRatingForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        services.rate_course(user=request.user, course=course, **form.cleaned_data)
        messages.success(
            request,
            "Your rating was updated."
            if existing
            else "Thanks! Your rating is now part of the averages.",
        )
        return redirect("catalog:course_detail", code=course.slug)

    return render(
        request,
        "ratings/rate_form.html",
        {
            "form": form,
            "subject_name": f"{course.code} {course.title}",
            "back_url": reverse("catalog:course_detail", kwargs={"code": course.slug}),
            "is_edit": existing is not None,
        },
    )
