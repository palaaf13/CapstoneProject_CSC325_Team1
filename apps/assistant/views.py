"""
The "What students say" box. Loaded by htmx after the course or professor page
has rendered, so a slow or failed AI call never holds up or breaks the page.
"""

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.catalog import services as catalog
from apps.catalog.models import Professor

from . import services


def _render(request, result, fallback_text: str) -> HttpResponse:
    return render(
        request,
        "assistant/partials/review_summary.html",
        {"result": result, "summary": result.summary, "fallback_text": fallback_text},
    )


@require_GET
def course_summary(request: HttpRequest, code: str) -> HttpResponse:
    course = catalog.get_course_by_code(code)
    if course is None:
        raise Http404(f"No course with code {code!r}")
    result = services.summarize(f"{course.code} {course.title}", services.course_reviews(course))
    return _render(request, result, services.course_fallback(course))


@require_GET
def professor_summary(request: HttpRequest, slug: str) -> HttpResponse:
    professor = get_object_or_404(Professor, slug=slug)
    result = services.summarize(professor.full_name, services.professor_reviews(professor))
    return _render(request, result, services.professor_fallback(professor))
