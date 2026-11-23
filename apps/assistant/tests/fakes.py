"""A stand-in for anthropic.Anthropic that never touches the network."""

from types import SimpleNamespace

import anthropic
import httpx2

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def text_block(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def tool_use(name, tool_input, id="toolu_1"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=tool_input)


def citation(url, title="FSC page"):
    return SimpleNamespace(type="web_search_result_location", url=url, title=title)


def response(*blocks, stop_reason="end_turn", model="claude-haiku-5-5", searches=0):
    if not blocks:
        blocks = (text_block("BCS 109 is 3 credits. [BCS 109](/courses/BCS-109/)"),)
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        model=model,
        usage=SimpleNamespace(
            input_tokens=900,
            output_tokens=150,
            server_tool_use=SimpleNamespace(web_search_requests=searches),
        ),
    )


def answer(text):
    return response(text_block(text))


def calls_tool(name, tool_input, id="toolu_1"):
    return response(tool_use(name, tool_input, id), stop_reason="tool_use")


def status_error(cls, status):
    return cls(f"HTTP {status}", response=httpx2.Response(status, request=REQUEST), body=None)


TIMEOUT = anthropic.APITimeoutError(request=REQUEST)
CONNECTION = anthropic.APIConnectionError(request=REQUEST)
RATE_LIMIT = status_error(anthropic.RateLimitError, 429)
OVERLOADED = status_error(anthropic.InternalServerError, 529)


class FakeClient:
    """messages.create returns (or raises) the queued results in order; the last repeats."""

    def __init__(self, *results):
        self.results = list(results) or [response()]
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Copy the message list: the caller keeps appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, BaseException):
            raise result
        return result
