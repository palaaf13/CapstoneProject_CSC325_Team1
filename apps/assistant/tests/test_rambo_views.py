"""The Rambo page, its fallback path, the hourly limit and the RamHub tools.
The AI is always mocked."""

import pytest

from apps.assistant import services, tools
from apps.assistant.models import RamboQuestion

from .fakes import TIMEOUT, FakeClient, answer, calls_tool

pytestmark = pytest.mark.django_db

PAGE = "/rambo/"
ASK = "/rambo/ask/"
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def ai(settings, monkeypatch):
    """Turn Rambo on with a fake client; set ai.results to control replies."""
    settings.ANTHROPIC_API_KEY = "test-key-not-real"
    fake = FakeClient(answer("BCS 109 is **3 credits**. [BCS 109](/courses/BCS-109/)"))
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


def test_page_shows_suggestions(client, student):
    body = client.get(PAGE).content
    assert b"Ask Rambo" in body and b"How much is a parking ticket?" in body
    assert b'data-testid="ask-rambo"' not in body  # no floating button on its own page


def test_floating_button_is_on_other_pages(client):
    assert b'data-testid="ask-rambo"' in client.get("/about/").content


def test_answer_from_a_mocked_ai(client, student, ai, make_course):
    make_course(code="BCS 109", title="Introduction to Programming")
    response = client.post(ASK, {"question": "How many credits is BCS 109?"}, **HTMX)

    assert response.status_code == 200
    body = response.content
    assert b'data-testid="rambo-answer"' in body
    assert b"<strong>3 credits</strong>" in body
    assert b'href="/courses/BCS-109/"' in body
    # Kept in the session for follow-ups; logged without the question text.
    assert client.session["rambo_chat"][-1]["answer"].startswith("BCS 109 is")
    logged = RamboQuestion.objects.get()
    assert logged.user == student and logged.fallback_reason == "" and logged.api_calls == 1
    assert not hasattr(logged, "question")


def test_follow_up_questions_carry_history(client, student, ai, make_course):
    make_course(code="BCS 109")
    client.post(ASK, {"question": "How many credits is BCS 109?"}, **HTMX)
    client.post(ASK, {"question": "And prerequisites?"}, **HTMX)
    sent = ai.calls[-1]["messages"]
    assert [m["content"] for m in sent if m["role"] == "user"] == [
        "How many credits is BCS 109?",
        "And prerequisites?",
    ]


def test_fallback_with_no_key_shows_matching_ramhub_pages(client, student, make_course):
    make_course(code="BCS 109", title="Introduction to Programming")
    body = client.post(ASK, {"question": "Where do I park for BCS 109?"}, **HTMX).content

    assert b'data-testid="rambo-fallback"' in body
    assert b'data-reason="ai_disabled"' in body
    assert b"Rambo can&#x27;t answer right now." in body or b"Rambo can't answer right now." in body
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


def test_without_javascript_the_form_still_works(client, student, ai, make_course):
    make_course(code="BCS 109")
    response = client.post(ASK, {"question": "How many credits is BCS 109?"})
    assert response.status_code == 302
    assert b"3 credits" in client.get(PAGE).content


def test_links_to_ramhub_pages_that_do_not_exist_are_unlinked(client, student, ai):
    ai.results = [answer("Try [CSC 999](/courses/CSC-999/) or [parking](/parking/).")]
    body = client.post(ASK, {"question": "q"}, **HTMX).content
    assert b'href="/courses/CSC-999/"' not in body and b"CSC 999" in body
    assert b'href="/parking/"' in body


def test_model_html_is_escaped(client, student, ai):
    ai.results = [answer("<script>alert(1)</script> [x](javascript:alert(1))")]
    body = client.post(ASK, {"question": "q"}, **HTMX).content
    assert b"<script>alert(1)" not in body and b"&lt;script&gt;" in body
    assert b"javascript:" not in body


def test_start_over_clears_the_conversation(client, student, ai):
    client.post(ASK, {"question": "hi"}, **HTMX)
    client.post("/rambo/clear/")
    assert "rambo_chat" not in client.session


def test_tool_loop_end_to_end_with_real_ramhub_data(client, student, ai, make_course):
    make_course(code="BCS 230", title="Foundations II", prereq_text="BCS 120 or CSC 111")
    ai.results = [
        calls_tool("search_courses", {"query": "BCS 230"}),
        answer("You need BCS 120 or CSC 111."),
    ]
    client.post(ASK, {"question": "Prereqs for BCS 230?"}, **HTMX)
    tool_result = ai.calls[1]["messages"][-1]["content"][0]["content"]
    assert "BCS 120 or CSC 111" in tool_result and "/courses/BCS-230/" in tool_result


# -- the tools on their own ---------------------------------------------------
def test_search_courses_by_code_and_by_words(make_course):
    make_course(
        code="MTH 150", title="Calculus I", credits=4, description="Limits and derivatives."
    )
    by_code = tools.search_courses({"query": "MTH 150"})["courses"][0]
    assert (by_code["credits"], by_code["url"]) == (4, "/courses/MTH-150/")
    assert tools.search_courses({"query": "limits derivatives"})["courses"][0]["code"] == "MTH 150"


def test_search_professors_labels_rmp_ratings(make_professor):
    make_professor(first_name="Ada", last_name="Lovelace", rmp_num_ratings=12, rmp_avg_rating=4.5)
    found = tools.search_professors({"query": "lovelace"})["professors"][0]
    assert found["url"] == "/professors/ada-lovelace/"
    assert found["ratemyprofessors"]["count"] == 12 and found["ramhub_student_ratings"] is None


def test_search_clubs(make_club):
    make_club("Cybersecurity Club", summary="Capture the flag practice.")
    found = tools.search_clubs({"query": "cyber"})["clubs"][0]
    assert found["name"] == "Cybersecurity Club" and found["url"] == "/clubs/cybersecurity-club/"


def test_campus_guides_are_plain_text_of_the_real_pages():
    parking = tools.campus_guide({"topic": "parking"})
    assert "$35" in parking["text"] and "<" not in parking["text"]
    assert parking["url"] == "/parking/"
    assert "7:45" in tools.campus_guide({"topic": "facilities"})["text"]
    assert "error" in tools.campus_guide({"topic": "weather"})


def test_upcoming_events_is_empty_safe():
    result = tools.upcoming_events({})
    assert result["events"] == [] and result["all_events_url"] == "/events/"


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
