"""The Rambo page, its fallback path and the hourly limit. The AI is always mocked."""

import pytest

from apps.assistant import services
from apps.assistant.models import RamboQuestion
from apps.assistant.models import RamboQuestion as RamboQuestionModel

from .fakes import (
    CONNECTION,
    OVERLOADED,
    RATE_LIMIT,
    TIMEOUT,
    FakeClient,
    answer,
    calls_tool,
    response,
    text_block,
)

pytestmark = pytest.mark.django_db

PAGE = "/rambo/"
ASK = "/rambo/ask/"
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def ai(settings, monkeypatch):
    """Turn Rambo on with a fake client; set ai.results to control replies."""
    settings.ANTHROPIC_API_KEY = "test-key-not-real"
    fake = FakeClient(
        answer(
            "Order it through the **Registrar's Office**. "
            "[Transcripts](https://www.farmingdale.edu/registrar/transcripts/)"
        )
    )
    monkeypatch.setattr(services, "get_client", lambda: fake)
    return fake


@pytest.fixture
def student(client, make_student):
    user = make_student()
    client.force_login(user)
    return user


def test_rambo_requires_sign_in(client):
    assert client.get(PAGE).status_code == 302
    response = client.post(ASK, {"question": "hi"}, **HTMX)
    assert response.status_code == 204 and "/login/" in response["HX-Redirect"]


def test_page_shows_suggestions_and_the_3d_stage(client, student):
    body = client.get(PAGE).content
    assert b"Ask Rambo" in body and b"How do I get a parking permit?" in body
    assert b"data-rambo-3d" in body and b"rambo3d.js" in body
    assert b'data-testid="ask-rambo"' not in body  # no floating button on its own page


def test_floating_button_is_on_other_pages(client):
    assert b'data-testid="ask-rambo"' in client.get("/about/").content


def test_answer_from_a_mocked_ai(client, student, ai):
    response = client.post(ASK, {"question": "How do I order a transcript?"}, **HTMX)

    assert response.status_code == 200
    body = response.content
    assert b'data-testid="rambo-answer"' in body
    assert b"<strong>Registrar&#x27;s Office</strong>" in body
    assert b'href="https://www.farmingdale.edu/registrar/transcripts/"' in body
    assert b'target="_blank"' in body
    # Kept in the session for follow-ups; logged without the question text.
    assert client.session["rambo_chat"][-1]["answer"].startswith("Order it")
    logged = RamboQuestion.objects.get()
    assert logged.user == student and logged.fallback_reason == "" and logged.api_calls == 1
    assert logged.prompt_version == "rambo_v2"
    assert not hasattr(logged, "question")


def test_rambo_only_gets_the_farmingdale_edu_search(client, student, ai):
    client.post(ASK, {"question": "Where is the registrar?"}, **HTMX)
    assert [t["name"] for t in ai.calls[0]["tools"]] == ["web_search"]
    assert ai.calls[0]["tools"][0]["allowed_domains"] == ["farmingdale.edu"]


def test_follow_up_questions_carry_history(client, student, ai):
    client.post(ASK, {"question": "How do I order a transcript?"}, **HTMX)
    client.post(ASK, {"question": "How much does it cost?"}, **HTMX)
    sent = ai.calls[-1]["messages"]
    assert [m["content"] for m in sent if m["role"] == "user"] == [
        "How do I order a transcript?",
        "How much does it cost?",
    ]


def test_fallback_with_no_key_shows_matching_ramhub_pages(client, student, make_course):
    make_course(code="BCS 109", title="Introduction to Programming")
    body = client.post(ASK, {"question": "Where do I park for BCS 109?"}, **HTMX).content

    assert b'data-testid="rambo-fallback"' in body
    assert b'data-reason="ai_disabled"' in body
    assert b'href="/parking/"' in body
    assert b'href="/courses/BCS-109/"' in body
    assert RamboQuestion.objects.get().fallback_reason == "ai_disabled"


def test_fallback_when_the_ai_times_out(client, student, ai):
    ai.results = [TIMEOUT]
    response = client.post(ASK, {"question": "When is the library open?"}, **HTMX)
    assert response.status_code == 200
    assert b'data-reason="timeout"' in response.content
    assert b'href="/facilities/"' in response.content


def test_fallback_with_no_matches_points_to_search(client, student):
    body = client.post(ASK, {"question": "zzzz qqqq"}, **HTMX).content
    assert b"searching RamHub" in body and b"https://www.farmingdale.edu/" in body


def test_hourly_limit_stops_asking_the_ai(client, student, ai, settings):
    settings.RAMBO_HOURLY_LIMIT = 2
    for _ in range(2):
        client.post(ASK, {"question": "hi"}, **HTMX)
    body = client.post(ASK, {"question": "hi again"}, **HTMX).content
    assert b'data-reason="hourly_limit"' in body
    assert len(ai.calls) == 2


def test_empty_question_is_a_form_error_not_a_call(client, student, ai):
    response = client.post(ASK, {"question": "   "}, **HTMX)
    assert response["HX-Retarget"] == "#rambo-form-error"
    assert b"Type a question first." in response.content
    assert ai.calls == [] and not RamboQuestion.objects.exists()


def test_without_javascript_the_form_still_works(client, student, ai):
    response = client.post(ASK, {"question": "How do I order a transcript?"})
    assert response.status_code == 302
    assert b"Registrar" in client.get(PAGE).content


def test_links_off_farmingdale_edu_never_reach_the_page(client, student, ai):
    ai.results = [answer("Try [this](https://evil.example.com/) or [RamHub](/parking/).")]
    body = client.post(ASK, {"question": "q"}, **HTMX).content
    assert b"evil.example.com" not in body and b'href="/parking/"' not in body


def test_model_html_is_escaped(client, student, ai):
    ai.results = [answer("<script>alert(1)</script> [x](javascript:alert(1))")]
    body = client.post(ASK, {"question": "q"}, **HTMX).content
    assert b"<script>alert(1)" not in body and b"&lt;script&gt;" in body
    assert b"javascript:" not in body


def test_start_over_clears_the_conversation(client, student, ai):
    client.post(ASK, {"question": "hi"}, **HTMX)
    client.post("/rambo/clear/")
    assert "rambo_chat" not in client.session


def test_unit_tests_cannot_build_a_real_client(settings):
    settings.ANTHROPIC_API_KEY = "would-be-real"
    with pytest.raises(AssertionError, match="mocked AI response"):
        services.get_client()


def test_get_client_is_none_without_a_key_or_when_disabled(settings):
    settings.ANTHROPIC_API_KEY = ""
    assert services.get_client() is None
    settings.ANTHROPIC_API_KEY = "x"
    settings.RAMBO_ENABLED = False
    assert services.get_client() is None


# -- every fallback reason, rendered end to end ------------------------------
FAILURES = {
    "timeout": [TIMEOUT],
    "connection_error": [CONNECTION],
    "rate_limited": [RATE_LIMIT],
    "api_error_529": [OVERLOADED],
    "unexpected_error:RuntimeError": [RuntimeError("boom")],
    "refused": [response(stop_reason="refusal")],
    "truncated": [response(stop_reason="max_tokens")],
    "invalid_output": [response(text_block("   "))],
    "too_many_steps": [calls_tool("nope", {})],
}


@pytest.mark.parametrize("reason", [*FAILURES, "ai_disabled", "hourly_limit", "unavailable"])
def test_every_fallback_reason_renders_a_working_page(
    client, student, ai, settings, monkeypatch, reason, caplog
):
    question = "How do I get a parking permit?"
    if reason in FAILURES:
        ai.results = list(FAILURES[reason])
    elif reason == "ai_disabled":
        monkeypatch.setattr(services, "get_client", lambda: None)
    elif reason == "hourly_limit":
        settings.RAMBO_HOURLY_LIMIT = 0
    elif reason == "unavailable":

        def broken(*args, **kwargs):
            raise RuntimeError("database down")

        monkeypatch.setattr(services, "_reserve_slot", broken)

    with caplog.at_level("WARNING"):
        response_ = client.post(ASK, {"question": question}, **HTMX)

    assert response_.status_code == 200
    body = response_.content.decode()
    assert 'data-testid="rambo-fallback"' in body
    assert f'data-reason="{reason}"' in body
    if reason == "hourly_limit":
        assert "Rambo needs a breather" in body
    else:
        assert "answer right now." in body
    assert 'href="/parking/"' in body  # the non-AI links still help
    assert 'data-testid="rambo-answer"' not in body
    assert question not in caplog.text  # never logged


def test_a_database_failure_after_answering_still_shows_the_answer(
    client, student, ai, monkeypatch
):
    def broken_save(self, *args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(RamboQuestionModel, "save", broken_save)
    monkeypatch.setattr(services, "_reserve_slot", lambda user: RamboQuestionModel(user=user))
    body = client.post(ASK, {"question": "How do I order a transcript?"}, **HTMX).content
    assert b'data-testid="rambo-answer"' in body


def test_the_hourly_limit_holds_however_requests_arrive(student, settings):
    settings.RAMBO_HOURLY_LIMIT = 2
    slots = [services._reserve_slot(student) for _ in range(4)]
    assert [slot is not None for slot in slots] == [True, True, False, False]
    assert RamboQuestion.objects.filter(user=student).count() == 2


def test_the_rambo_page_pins_three_js_with_integrity_hashes(client, student):
    body = client.get(PAGE).content.decode()
    assert '"integrity"' in body
    assert body.count("sha384-") == 3
