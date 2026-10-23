"""How long each model call of a message took, and on which model (slice 3).

The platform times a call and sends it to telemetry only (`dw.model.call`);
nothing a running process can read back holds it, and a step's stamp names
the profile, not the model the profile routed to. The activity record needs
both, so DW1's one door to a model is wrapped once at the composition root:
`TimedInterpretation` times every call made while a message is processed and
appends what it saw to that message's list.

**One list per message, by context.** `InboxProcessing` opens the list
(`recording_model_calls`) around one message and reads it back where the
disposition is written (`model_calls`). The readers are built once and shared
by every message, so the list cannot be a field of theirs; a `ContextVar` is
the one place that is per message, and it is per asyncio task, so two
messages processed at once never share one. Outside such a block (an eval, a
rule draft) nothing is recorded and the wrapper only passes the call on.

Ids, a prompt reference, a model name and a duration: no input, no answer.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import NotFoundError
from dw_sales.application.model_readiness import StepModelPort
from dw_sales.application.model_reading import InterpretationPort, PromptRef
from dw_sales.domain.activity import ModelCall

_LOG = logging.getLogger("dw_sales.model")

_CALLS: ContextVar[list[ModelCall] | None] = ContextVar("dw_sales_model_calls", default=None)


@contextmanager
def recording_model_calls() -> Iterator[list[ModelCall]]:
    """Record the model calls made inside the block, for one message."""
    calls: list[ModelCall] = []
    token = _CALLS.set(calls)
    try:
        yield calls
    finally:
        _CALLS.reset(token)


def model_calls() -> tuple[ModelCall, ...]:
    """The calls recorded so far for the message being processed; none
    outside `recording_model_calls`."""
    return tuple(_CALLS.get() or ())


@dataclass(frozen=True)
class TimedInterpretation:
    """Implements `InterpretationPort` over another one, timing each call."""

    inner: InterpretationPort
    # The model a tenant's steps run on now (the gateway's own resolution).
    models: StepModelPort

    @property
    def model_profile(self) -> str:
        return self.inner.model_profile

    @property
    def route(self) -> str:
        return self.inner.route

    @property
    def max_input_tokens(self) -> int:
        return self.inner.max_input_tokens

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        calls = _CALLS.get()
        if calls is None:
            return await self.inner.interpret(
                prompt, inputs, schema, run=run, max_output_tokens=max_output_tokens
            )
        started = time.perf_counter()
        answered = False
        try:
            answer = await self.inner.interpret(
                prompt, inputs, schema, run=run, max_output_tokens=max_output_tokens
            )
            answered = True
            return answer
        finally:
            calls.append(
                ModelCall(
                    prompt=str(prompt),
                    model_profile=self.inner.model_profile,
                    model=self._model(run),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    answered=answered,
                )
            )

    def _model(self, run: RunContext) -> str | None:
        try:
            return self.models.model_for(run.tenant_id)
        except NotFoundError:
            _LOG.warning("no model resolved for run %s's profile", run.run_id)
            return None
