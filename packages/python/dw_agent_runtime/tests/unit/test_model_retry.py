"""A provider hiccup is survived; an approval interrupt is not mistaken for one.

The second is the reason this file is worth reading. `GraphBubbleUp` subclasses
`Exception`, so the obvious retry loop swallows the interrupt a gated tool
raises and the run continues as though a person had approved it. That failure is
silent, and it is an approval bypass.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents.middleware import ModelRequest
from langgraph.errors import GraphBubbleUp

from dw_agent_runtime.adapters.model_retry import ModelRetryMiddleware, is_transient

pytestmark = pytest.mark.unit


class _BoomError(Exception):
    def __init__(self, status: int | None = None) -> None:
        super().__init__(f"status={status}")
        if status is not None:
            self.status_code = status


def _mw(**overrides: Any) -> ModelRetryMiddleware:
    slept: list[float] = []

    async def _sleep(seconds: float) -> None:
        slept.append(seconds)

    fields: dict[str, Any] = {"backoff_seconds": 0.5, "sleep": _sleep}
    fields.update(overrides)
    middleware = ModelRetryMiddleware(**fields)
    middleware.slept = slept  # type: ignore[attr-defined]
    return middleware


def _handler(errors: list[BaseException | None]) -> Any:
    calls: list[int] = []

    async def handler(request: ModelRequest[Any]) -> str:
        calls.append(len(calls))
        error = errors[len(calls) - 1] if len(calls) <= len(errors) else None
        if error is not None:
            raise error
        return "ok"

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


REQUEST = object()


async def test_an_approval_interrupt_is_never_retried() -> None:
    """The bypass this guards. `GraphBubbleUp` is an Exception, so a retry loop
    that catches Exception treats a person being asked as a provider failure —
    and the second attempt runs the gated call without them."""
    handler = _handler([GraphBubbleUp("cần duyệt")])

    with pytest.raises(GraphBubbleUp):
        await _mw().awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert handler.calls == [0], "the interrupt must pass through on the first attempt"


async def test_a_transient_failure_is_survived() -> None:
    handler = _handler([TimeoutError("chậm"), None])

    result = await _mw().awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert result == "ok"
    assert len(handler.calls) == 2


async def test_a_permanent_failure_is_not_retried() -> None:
    """A rejected key answers the same way every time; retrying only makes the
    person wait longer to hear it."""
    handler = _handler([_BoomError(401)])

    with pytest.raises(_BoomError):
        await _mw().awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert len(handler.calls) == 1


async def test_an_unrecognised_error_is_not_retried() -> None:
    """Fail closed on the classification too: a run that stops with a real error
    is visible, one that quietly retries a permanent failure looks like slowness."""
    handler = _handler([ValueError("gì đó lạ")])

    with pytest.raises(ValueError):
        await _mw().awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert len(handler.calls) == 1


async def test_attempts_are_bounded_and_the_last_error_reaches_the_caller() -> None:
    handler = _handler([TimeoutError("1"), TimeoutError("2"), TimeoutError("3")])

    with pytest.raises(TimeoutError):
        await _mw(attempts=3).awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert len(handler.calls) == 3, "three attempts, not an unbounded loop"


async def test_the_wait_grows_between_attempts() -> None:
    """A rate limit that is still a rate limit half a second later is usually not
    one a second later either."""
    middleware = _mw(attempts=3)
    handler = _handler([TimeoutError("1"), TimeoutError("2"), None])

    await middleware.awrap_model_call(REQUEST, handler)  # type: ignore[arg-type]

    assert middleware.slept == [0.5, 1.0]  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504])
def test_the_statuses_worth_another_attempt(status: int) -> None:
    assert is_transient(_BoomError(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_the_statuses_that_describe_the_request_itself(status: int) -> None:
    assert not is_transient(_BoomError(status))
