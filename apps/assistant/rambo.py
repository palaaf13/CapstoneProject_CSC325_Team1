"""
Rambo: a student asks a question about Farmingdale State College, Claude
answers it using RamHub's own data (through tools) and farmingdale.edu
(through web search).

No Django imports here on purpose. The tools are passed in, so the site
(apps/assistant/services.py) and the evaluation suite (evals/) run exactly the
same prompt, loop, and checks.

``ask`` never raises. Every way the AI can fail (no key, timeout, network
error, rate limit, API error, refusal, truncation, a runaway tool loop, or an
answer we won't show) comes back as a ``RamboResult`` with ``answer=None`` and
a ``fallback_reason``, and the page shows plain search results instead.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

PROMPT_VERSION = "rambo_v1"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.txt"
DEFAULT_MODEL = "claude-haiku-5-5"

MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 4  # earlier question/answer pairs sent along for follow-ups
MAX_API_CALLS = 6  # one question: look things up a few times, then answer
MAX_OUTPUT_TOKENS = 4000
MAX_ANSWER_CHARS = 4000
MAX_TOOL_RESULT_CHARS = 6000

# The basic web search tool: the newer dynamic-filtering version is not
# available on Claude Haiku 5.5. Limited to the college's own site.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 2,
    "allowed_domains": ["farmingdale.edu"],
}

_FSC_URL = re.compile(r"^https?://([a-z0-9-]+\.)*farmingdale\.edu(?:[/?#]|$)", re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BARE_URL = re.compile(r"(?<!\]\()(?<!\()\bhttps?://[^\s)\]]+", re.IGNORECASE)


@dataclass(frozen=True)
class Tool:
    """A RamHub lookup Rambo can call. ``run`` gets the model's input dict."""

    name: str
    description: str
    input_schema: dict
    run: Callable[[dict], object]

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class RamboAnswer:
    text: str
    sources: tuple[Source, ...] = ()
    tools_used: tuple[str, ...] = ()
    links_removed: int = 0
    model: str = ""
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RamboResult:
    answer: RamboAnswer | None = None
    fallback_reason: str | None = None
    usage: dict = field(default_factory=dict)
    # What the tools returned and what web search quoted, for the eval suite's
    # hallucination check. Never shown or stored by the site.
    evidence: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.answer is not None


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def is_allowed_url(url: str) -> bool:
    """RamHub paths ("/courses/BCS-109/") and farmingdale.edu. Nothing else."""
    if url.startswith("/") and not url.startswith("//"):
        return True
    return bool(_FSC_URL.match(url))


def clean_links(text: str, keep: Callable[[str], bool] = is_allowed_url) -> tuple[str, int]:
    """Unlink every link that fails ``keep``: a Markdown link keeps its label,
    a bare URL is dropped. Returns the text and how many links were removed."""
    removed = 0

    def markdown(match: re.Match) -> str:
        nonlocal removed
        label, url = match.group(1), match.group(2)
        if keep(url):
            return match.group(0)
        removed += 1
        return label

    def bare(match: re.Match) -> str:
        nonlocal removed
        if keep(match.group(0)):
            return match.group(0)
        removed += 1
        return ""

    text = _MD_LINK.sub(markdown, text)
    text = _BARE_URL.sub(bare, text)
    return text, removed


def _run_tool(tool: Tool | None, name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool call. A failing tool is reported to the model, not raised."""
    if tool is None:
        return f"There is no tool called {name!r}.", True
    try:
        result = tool.run(tool_input if isinstance(tool_input, dict) else {})
    except Exception as exc:  # A broken lookup should not end the conversation.
        logger.exception("Rambo tool %s failed", name)
        return f"The {name} lookup failed ({type(exc).__name__}). Answer without it.", True
    body = json.dumps(result, ensure_ascii=False, default=str)
    if len(body) > MAX_TOOL_RESULT_CHARS:
        body = body[:MAX_TOOL_RESULT_CHARS] + " …(truncated)"
    return body, False


def _fallback(reason: str, usage: dict, detail: object = "") -> RamboResult:
    logger.warning("Rambo fell back (%s) %s", reason, detail)
    return RamboResult(fallback_reason=reason, usage=usage)


def ask(
    question: str,
    *,
    tools: list[Tool],
    client: anthropic.Anthropic | None,
    history: list[dict] | None = None,
    model: str = DEFAULT_MODEL,
    web_search: bool = True,
) -> RamboResult:
    """Answer one question, or explain why not. Never raises.

    ``history`` is earlier turns as {"question": ..., "answer": ...} dicts.
    """
    question = " ".join((question or "").split())[:MAX_QUESTION_CHARS]
    if not question:
        return RamboResult(fallback_reason="empty_question")
    if client is None:
        return RamboResult(fallback_reason="ai_disabled")

    messages: list[dict] = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})

    by_name = {tool.name: tool for tool in tools}
    definitions = [tool.definition() for tool in tools]
    if web_search:
        definitions.append(WEB_SEARCH_TOOL)

    usage = {"api_calls": 0, "input_tokens": 0, "output_tokens": 0, "web_searches": 0}
    tools_used: list[str] = []
    sources: dict[str, Source] = {}
    evidence: list[str] = []
    served_by = model

    for _ in range(MAX_API_CALLS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=load_prompt(),
                tools=definitions,
                messages=messages,
                output_config={"effort": "low"},
            )
        except anthropic.APITimeoutError as exc:
            return _fallback("timeout", usage, exc)
        except anthropic.APIConnectionError as exc:
            return _fallback("connection_error", usage, exc)
        except anthropic.RateLimitError as exc:
            return _fallback("rate_limited", usage, exc)
        except anthropic.APIStatusError as exc:
            return _fallback(f"api_error_{exc.status_code}", usage, exc)
        except Exception as exc:  # The page must never break because of the AI.
            logger.exception("Unexpected error calling Rambo")
            return _fallback(f"unexpected_error:{type(exc).__name__}", usage)

        usage["api_calls"] += 1
        served_by = getattr(response, "model", "") or served_by
        if (u := getattr(response, "usage", None)) is not None:
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
            server = getattr(u, "server_tool_use", None)
            usage["web_searches"] += getattr(server, "web_search_requests", 0) or 0

        for block in response.content:
            kind = getattr(block, "type", "")
            if kind == "server_tool_use":
                tools_used.append("web_search")
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", "")
                if quoted := getattr(citation, "cited_text", ""):
                    evidence.append(quoted)
                if url and is_allowed_url(url):
                    sources.setdefault(url, Source(getattr(citation, "title", "") or url, url))

        stop = response.stop_reason
        if stop == "refusal":
            return _fallback("refused", usage)
        if stop == "max_tokens":
            return _fallback("truncated", usage)
        if stop == "pause_turn":
            # The server paused its own web-search loop; send it back to resume.
            messages.append({"role": "assistant", "content": response.content})
            continue
        if stop == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                tools_used.append(block.name)
                body, is_error = _run_tool(by_name.get(block.name), block.name, block.input)
                evidence.append(body)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": body,
                        **({"is_error": True} if is_error else {}),
                    }
                )
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
        ).strip()
        if not text:
            return _fallback("invalid_output", usage, "empty answer")
        if len(text) > MAX_ANSWER_CHARS:
            return _fallback("invalid_output", usage, f"answer is {len(text)} characters")
        text, removed = clean_links(text)
        answer = RamboAnswer(
            text=text,
            sources=tuple(sources.values()),
            tools_used=tuple(dict.fromkeys(tools_used)),
            links_removed=removed,
            model=served_by,
        )
        return RamboResult(answer=answer, usage=usage, evidence=tuple(evidence))

    return _fallback("too_many_steps", usage)
