"""POST handlers for student-submitted ratings."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.services import get_course_by_code, professors_for_course
from apps.saved import services as saved

from . import services
from .forms import CourseRatingForm
from .models import CourseRating


@require_POST
@login_required
def course_rating_create(request, code: str) -> HttpResponse:
    course = get_course_by_code(code)
    if course is None:
        raise Http404(f"No course with code {code!r}")

    if CourseRating.objects.filter(user=request.user, course=course).exists():
        messages.error(request, "You have already rated this course.")
        return redirect("catalog:course_detail", code=course.slug)

    form = CourseRatingForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "catalog/course_detail.html",
            {
                "course": course,
                "professors": professors_for_course(course),
                "is_saved": saved.is_saved(request.user, course),
                "has_rated": False,
                "rating_form": form,
            },
            status=400,
        )

    try:
        services.submit_course_rating(
            user=request.user,
            course=course,
            **form.cleaned_data,
        )
    except IntegrityError:
        # The unique constraint handles two requests racing past the check above.
        messages.error(request, "You have already rated this course.")
    else:
        messages.success(request, "Your course rating has been submitted.")
    return redirect("catalog:course_detail", code=course.slug)
