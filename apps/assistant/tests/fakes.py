"""A stand-in for anthropic.Anthropic that never touches the network."""

import json
from types import SimpleNamespace

import anthropic
import httpx2

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

GOOD_OUTPUT = {
    "overview": "Students say the workload is heavy but the course is worth it.",
    "tone": "mixed",
    "pros": [{"text": "Very useful for later courses", "reviews": [1, 2]}],
    "cons": [{"text": "Heavy weekly workload", "reviews": [2, 3]}],
}


def response(output=None, *, text=None, stop_reason="end_turn", model="claude-haiku-5-5"):
    body = text if text is not None else json.dumps(output if output is not None else GOOD_OUTPUT)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=body)],
        stop_reason=stop_reason,
        model=model,
        usage=SimpleNamespace(input_tokens=500, output_tokens=120),
    )


def status_error(cls, status):
    return cls(
        f"HTTP {status}",
        response=httpx2.Response(status, request=REQUEST),
        body=None,
    )


TIMEOUT = anthropic.APITimeoutError(request=REQUEST)
CONNECTION = anthropic.APIConnectionError(request=REQUEST)
RATE_LIMIT = status_error(anthropic.RateLimitError, 429)
OVERLOADED = status_error(anthropic.InternalServerError, 529)


class FakeClient:
    """messages.create returns (or raises) the queued results, in order."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, BaseException):
            raise result
        return result
