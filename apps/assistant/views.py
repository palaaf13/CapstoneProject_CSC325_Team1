"""
/rambo/: chat with Rambo. The conversation lives in the student's session only.

The page works without JavaScript (the form posts and the page re-renders);
with htmx, each question swaps in just the new exchange. Every response is a
200, because htmx does not swap 4xx/5xx responses into the page.
"""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .forms import QuestionForm

SESSION_KEY = "rambo_chat"
KEEP_EXCHANGES = 10

SUGGESTIONS = [
    "How do I order an official transcript?",
    "How do I get a parking permit?",
    "Where is the Tutoring Center?",
    "When does the next semester start?",
]


def _chat(request: HttpRequest) -> list[dict]:
    return request.session.get(SESSION_KEY, [])


def _history(chat: list[dict]) -> list[dict]:
    """Earlier exchanges Rambo actually answered, for follow-up questions."""
    return [{"question": e["question"], "answer": e["answer"]} for e in chat if e.get("answer")]


@login_required
def rambo_page(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "assistant/rambo.html",
        {"chat": _chat(request), "form": QuestionForm(), "suggestions": SUGGESTIONS},
    )


@require_POST
def rambo_ask(request: HttpRequest) -> HttpResponse:
    is_htmx = request.headers.get("HX-Request") == "true"
    if not request.user.is_authenticated:
        if is_htmx:
            response = HttpResponse(status=204)
            response["HX-Redirect"] = f"{reverse('login')}?next={reverse('assistant:rambo')}"
            return response
        return redirect_to_login(reverse("assistant:rambo"))

    form = QuestionForm(request.POST)
    if not form.is_valid():
        if is_htmx:
            response = render(request, "assistant/partials/form_error.html", {"form": form})
            response["HX-Retarget"] = "#rambo-form-error"
            response["HX-Reswap"] = "innerHTML"
            return response
        return render(
            request,
            "assistant/rambo.html",
            {"chat": _chat(request), "form": form, "suggestions": SUGGESTIONS},
        )

    question = form.cleaned_data["question"]
    chat = _chat(request)
    result = services.ask(request.user, question, _history(chat))
    exchange = {"question": question, "answer": None, "sources": [], "reason": None, "links": []}
    if result.ok:
        exchange["answer"] = result.answer.text
        exchange["sources"] = [{"title": s.title, "url": s.url} for s in result.answer.sources]
    else:
        exchange["reason"] = result.fallback_reason
        exchange["links"] = [
            {"label": link.label, "url": link.url} for link in services.fallback_links(question)
        ]
    request.session[SESSION_KEY] = [*chat, exchange][-KEEP_EXCHANGES:]

    if is_htmx:
        return render(request, "assistant/partials/exchange.html", {"exchange": exchange})
    return redirect("assistant:rambo")


@require_POST
def rambo_clear(request: HttpRequest) -> HttpResponse:
    request.session.pop(SESSION_KEY, None)
    return redirect("assistant:rambo")
