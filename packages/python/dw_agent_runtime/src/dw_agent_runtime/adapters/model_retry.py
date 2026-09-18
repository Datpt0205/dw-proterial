"""A provider hiccup should not end a run that could have carried on.

Measured before writing: a single `TimeoutError` raised by the chat model kills
the whole turn, the model is called exactly once, and the caller sees a stack
trace. For one customer that is an annoyance. Across many it is the difference
between a platform and a demo — providers rate-limit, drop connections and
return 503s as ordinary weather.

**Provider FALLBACK is deliberately not here.** `OpenAICompatibleChatModelFactory`
points at a LiteLLM proxy, where provider selection, keys and failover are
configuration the application never sees. Re-implementing that in the agent loop
would be a second answer to the same question, and the copy nobody edits would
be the one that kept routing to a decommissioned model. What the proxy cannot do
is decide whether THIS run should try again; that is what this does.

**The trap, and the reason this file is careful.** `GraphBubbleUp` — the
exception an approval interrupt is raised as — subclasses `Exception`. A bare
`except Exception: retry` would swallow it, and the run would carry on as if a
person had said yes to a gated tool. It is re-raised first, before any other
branch, and a test asserts it.

**What counts as transient is a closed list.** Retrying a rejected API key, a
malformed request or a content-policy refusal burns the clock and changes
nothing; only errors that a later attempt could plausibly survive are retried.
Anything unrecognised is NOT retried, which is the fail-closed direction: a run
that stops with a real error is visible, a run that silently retries a permanent
failure three times looks like slowness.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langgraph.errors import GraphBubbleUp

logger = logging.getLogger("dw_agent_runtime.model_retry")

__all__ = ["DEFAULT_ATTEMPTS", "ModelRetryMiddleware", "is_transient"]

# Three: the first attempt plus two. A provider blip is usually over within a
# second; a fourth attempt mostly serves to keep a person waiting longer before
# they are told the same thing.
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5

# HTTP statuses a later attempt could plausibly survive. 408 and 504 are
# timeouts, 409 a lost race, 429 a rate limit, 500/502/503 a provider having a
# bad minute. Everything else — 400, 401, 403, 404, 422 — describes the request
# itself and will describe it identically next time.
_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


def is_transient(error: BaseException) -> bool:
    """Whether trying again could plausibly give a different answer.

    Duck-typed on `status_code` rather than importing a provider SDK: the
    runtime talks to an OpenAI-compatible endpoint through a proxy and should
    not grow a dependency on whichever client happens to be installed.
    """
    if isinstance(error, TimeoutError | ConnectionError):
        return True
    status = getattr(error, "status_code", None)
    return isinstance(status, int) and status in _RETRYABLE_STATUS


class ModelRetryMiddleware(AgentMiddleware[Any, Any]):
    """Retries a model call that failed in a way a retry could fix."""

    def __init__(
        self,
        *,
        attempts: int = DEFAULT_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__()
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._attempts = attempts
        self._backoff = backoff_seconds
        # Injected so a test proves the backoff without spending it.
        self._sleep = sleep

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[Any]],
    ) -> Any:
        for attempt in range(1, self._attempts + 1):
            try:
                return await handler(request)
            except GraphBubbleUp:
                # An approval interrupt, not a failure. First, and unconditional:
                # it subclasses Exception, so every branch below would catch it.
                raise
            except Exception as exc:
                if not is_transient(exc) or attempt == self._attempts:
                    raise
                logger.warning(
                    "model call failed transiently; retrying",
                    extra={"attempt": attempt, "of": self._attempts, "error": type(exc).__name__},
                )
                # Exponential, from the first retry: a rate limit that is still
                # a rate limit 0.5s later is usually not one 1s later either.
                await self._sleep(self._backoff * (2 ** (attempt - 1)))
        # Unreachable: the loop either returns or raises on its last attempt.
        raise AssertionError("retry loop ended without returning or raising")
