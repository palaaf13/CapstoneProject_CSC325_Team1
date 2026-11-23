"""Rating pages. A student rates once per course; coming back edits that rating."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.catalog import services as catalog
from apps.catalog.models import Professor

from . import services
from .forms import CourseRatingForm, ProfessorRatingForm


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


@login_required
def rate_professor(request: HttpRequest, slug: str) -> HttpResponse:
    professor = get_object_or_404(Professor, slug=slug)
    existing = services.professor_rating_by(request.user, professor)
    initial = {}
    if existing:
        initial = {
            "clarity": existing.clarity,
            "helpfulness": existing.helpfulness,
            "fairness": existing.fairness,
            "course": str(existing.course_id or ""),
            "semester": existing.semester,
            "comment": existing.comment,
        }
    form = ProfessorRatingForm(
        request.POST or None,
        initial=initial,
        courses=catalog.courses_for_professor(professor),
    )
    if request.method == "POST" and form.is_valid():
        services.rate_professor(user=request.user, professor=professor, **form.cleaned_data)
        messages.success(
            request,
            "Your rating was updated."
            if existing
            else "Thanks! Your rating is now part of the averages.",
        )
        return redirect("catalog:professor_detail", slug=professor.slug)

    return render(
        request,
        "ratings/rate_form.html",
        {
            "form": form,
            "subject_name": professor.full_name,
            "back_url": reverse("catalog:professor_detail", kwargs={"slug": professor.slug}),
            "is_edit": existing is not None,
        },
    )
