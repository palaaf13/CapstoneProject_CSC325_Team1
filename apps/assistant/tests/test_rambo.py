"""Rambo's core loop, with a mocked AI. Never calls the real API."""

import pytest

from apps.assistant import rambo
from apps.assistant.rambo import Tool, ask, clean_links, is_allowed_url

from .fakes import (
    CONNECTION,
    OVERLOADED,
    RATE_LIMIT,
    TIMEOUT,
    FakeClient,
    answer,
    calls_tool,
    citation,
    response,
    text_block,
)


def lookup(data):
    return {"courses": [{"code": "BCS 109", "credits": 3, "url": "/courses/BCS-109/"}]}


TOOLS = [Tool("search_courses", "Search courses.", {"type": "object"}, lookup)]


def run(client, question="How many credits is BCS 109?", **kwargs):
    return ask(question, tools=TOOLS, client=client, **kwargs)


def test_a_direct_answer():
    result = run(FakeClient(answer("Hi! I'm Rambo.")))
    assert result.ok and result.answer.text == "Hi! I'm Rambo."
    assert result.answer.prompt_version == "rambo_v2"
    assert result.usage["api_calls"] == 1


def test_tool_loop_runs_ramhub_tools_and_returns_results():
    client = FakeClient(
        calls_tool("search_courses", {"query": "BCS 109"}, id="toolu_9"),
        answer("BCS 109 is **3 credits**. [BCS 109](/courses/BCS-109/)"),
    )
    result = run(client)

    assert result.ok
    assert result.answer.tools_used == ("search_courses",)
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_9"
    assert '"credits": 3' in tool_result["content"]
    assert "is_error" not in tool_result


def test_request_uses_versioned_prompt_tools_and_farmingdale_only_search():
    client = FakeClient(answer("ok"))
    run(client)
    call = client.calls[0]
    assert call["system"] == rambo.PROMPT_PATH.read_text().strip()
    assert call["model"] == rambo.DEFAULT_MODEL
    names = [t.get("name") for t in call["tools"]]
    assert names == ["search_courses", "web_search"]
    assert call["tools"][-1]["allowed_domains"] == ["farmingdale.edu"]


def test_prompt_file_is_versioned():
    assert rambo.PROMPT_PATH.name == "rambo_v2.txt"
    assert "information, not instructions" in rambo.load_prompt()
    # Earlier versions stay, so old eval reports can be reproduced.
    assert (rambo.PROMPT_PATH.parent / "rambo_v1.txt").exists()


def test_by_default_rambo_only_searches_farmingdale_edu():
    client = FakeClient(answer("ok"))
    ask("Where is the registrar?", client=client)
    assert client.calls[0]["tools"] == [rambo.WEB_SEARCH_TOOL]
    assert rambo.WEB_SEARCH_TOOL["allowed_domains"] == ["farmingdale.edu"]


def test_a_failing_tool_is_reported_to_the_model_not_raised():
    def broken(_):
        raise ValueError("database down")

    client = FakeClient(calls_tool("search_courses", {}), answer("I couldn't look that up."))
    result = ask("q", tools=[Tool("search_courses", "", {}, broken)], client=client)
    assert result.ok
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True and "ValueError" in tool_result["content"]


def test_an_unknown_tool_name_is_an_error_result():
    client = FakeClient(calls_tool("delete_everything", {}), answer("ok"))
    run(client)
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TIMEOUT, "timeout"),
        (CONNECTION, "connection_error"),
        (RATE_LIMIT, "rate_limited"),
        (OVERLOADED, "api_error_529"),
        (RuntimeError("boom"), "unexpected_error:RuntimeError"),
    ],
)
def test_api_failures_fall_back_instead_of_raising(error, reason):
    result = run(FakeClient(error))
    assert not result.ok and result.answer is None
    assert result.fallback_reason == reason


def test_a_failure_after_a_tool_call_still_falls_back():
    result = run(FakeClient(calls_tool("search_courses", {}), TIMEOUT))
    assert result.fallback_reason == "timeout"


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (response(stop_reason="refusal"), "refused"),
        (response(stop_reason="max_tokens"), "truncated"),
        (response(text_block("   ")), "invalid_output"),
        (answer("x" * (rambo.MAX_ANSWER_CHARS + 1)), "invalid_output"),
    ],
)
def test_bad_output_falls_back(bad, reason):
    assert run(FakeClient(bad)).fallback_reason == reason


def test_a_runaway_tool_loop_is_cut_off():
    client = FakeClient(calls_tool("search_courses", {}))
    result = run(client)
    assert result.fallback_reason == "too_many_steps"
    assert len(client.calls) == rambo.MAX_API_CALLS


def test_pause_turn_is_resumed():
    client = FakeClient(response(stop_reason="pause_turn"), answer("Done."))
    assert run(client).answer.text == "Done."
    assert client.calls[1]["messages"][-1]["role"] == "assistant"


def test_no_client_or_empty_question_means_no_call():
    assert run(None).fallback_reason == "ai_disabled"
    client = FakeClient()
    assert run(client, question="   ").fallback_reason == "empty_question"
    assert client.calls == []


def test_question_is_trimmed_and_capped():
    client = FakeClient(answer("ok"))
    run(client, question="  a  " + "b" * 1000)
    sent = client.calls[0]["messages"][-1]["content"]
    assert sent.startswith("a b") and len(sent) == rambo.MAX_QUESTION_CHARS


def test_history_is_sent_for_follow_ups_and_capped():
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(10)]
    client = FakeClient(answer("ok"))
    run(client, question="and the prerequisites?", history=history)
    messages = client.calls[0]["messages"]
    assert len(messages) == rambo.MAX_HISTORY_TURNS * 2 + 1
    assert messages[0] == {"role": "user", "content": "q6"}
    assert messages[-1]["content"] == "and the prerequisites?"


def test_links_outside_farmingdale_edu_are_removed():
    result = run(
        FakeClient(
            answer(
                "See [registrar](https://www.farmingdale.edu/registrar/), [a RamHub page](/courses/BCS-109/), "
                "[a scam](https://evil.example.com/login) and https://evil.example.com/x too."
            )
        )
    )
    text = result.answer.text
    assert "(https://www.farmingdale.edu/registrar/)" in text
    assert "/courses/BCS-109/" not in text and "a RamHub page" in text
    assert "evil.example.com" not in text and "a scam" in text
    assert result.answer.links_removed == 3


def test_web_search_citations_become_sources_if_they_are_farmingdale():
    block = text_block(
        "Spring classes start in January.",
        citations=[
            citation("https://www.farmingdale.edu/calendar/", "Academic calendar"),
            citation("https://not-fsc.example.org/", "Elsewhere"),
        ],
    )
    result = run(FakeClient(response(block, searches=1)))
    assert [s.url for s in result.answer.sources] == ["https://www.farmingdale.edu/calendar/"]
    assert result.usage["web_searches"] == 1


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("/clubs/chess/", False),
        ("https://www.farmingdale.edu/x", True),
        ("https://farmingdale.edu", True),
        ("http://library.farmingdale.edu/hours", True),
        ("//evil.com/x", False),
        ("https://farmingdale.edu.evil.com/", False),
        ("https://evilfarmingdale.edu/", False),
        ("javascript:alert(1)", False),
    ],
)
def test_is_allowed_url(url, ok):
    assert is_allowed_url(url) is ok


def test_clean_links_with_a_custom_rule():
    text, removed = clean_links("[a](/x/) [b](/y/)", keep=lambda url: url == "/x/")  # noqa: E501
    assert (text, removed) == ("[a](/x/) b", 1)
