"""A turn's own ceiling on model calls and input tokens (`TurnCeiling`).

`RunBudgetMiddleware` bounds a RUN: everything every step of it spends, and a
run over it stops. A reading done as an agent turn (`AgentTurnPort`) needs a
second, smaller bound of its own: a turn that loops on its tools must stop long
before the run's ceiling, and stopping it is not the run failing, it is the
step falling back to its one-call reading (dw_sales ADR 0012 decision 4).

Counted from the conversation itself, not on the instance: an agent is compiled
once per process and serves every turn, so a counter on the middleware would
carry one turn's calls into the next. Every assistant message in the request is
a call this turn already made, with the tokens its provider reported.

Checked before the call, like the run's ceiling: a ceiling checked afterwards
is a report on what was spent, not a limit. Time is the caller's
(`asyncio.wait_for` around the turn): a middleware cannot interrupt a call that
hangs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from dw_agent_runtime.model.agent_turn import TurnCeiling, TurnCeilingReachedError

__all__ = ["TurnCeilingMiddleware"]


class TurnCeilingMiddleware(AgentMiddleware[Any, Any]):
    """Refuses a turn's next model call once it has made its last allowed one
    or read its input-token allowance."""

    def __init__(self, ceiling: TurnCeiling) -> None:
        super().__init__()
        self._ceiling = ceiling

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        made = [m for m in request.messages if isinstance(m, AIMessage)]
        if len(made) >= self._ceiling.max_model_calls:
            raise TurnCeilingReachedError("calls")
        spent = sum(m.usage_metadata["input_tokens"] for m in made if m.usage_metadata)
        if spent >= self._ceiling.max_input_tokens:
            raise TurnCeilingReachedError("spend")
        return await handler(request)
