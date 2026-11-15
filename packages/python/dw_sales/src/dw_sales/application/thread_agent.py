"""The thread agent: a thread message read with read-only tools (dw_sales
ADR 0012 decisions 1 and 4, tickets 30 and 31).

It answers what the one-call reading answers (`reply_intent.ReplyReader`):
the message's thread intents, `ModelThreadIntents`, each standing on sentences
code locates once in the message's newest part (`verified_intents`), so what
it reads is checked exactly as the one-call reading is. What it adds is that,
before it answers, the model may look things up with DW1's read-only tools
(`thread_tools`): the thread's earlier messages, its cases, a case by number,
the conversion list, a lead time, PC's answer. Each tool reads only what code
bound the turn to (`ThreadBinding`: the one customer the thread's cases are
of), never what the message or the model names.

**Bounded.** A turn has a ceiling (`CEILING`) on model calls, input tokens and
seconds. Over one, or with no usable answer, it raises, and the intake falls
back to the one-call reading, or to a person when that one is off too, and
the reading says so (`ReplyReading.fallback`; `OrderIntake._read_thread`).
A run's own budget refusal is not that: it stops the run.

**Proposes only.** The reading is stamped on the reply like the one-call
reading; the step it proposes is code's (`proposed_step`), shown for Sales to
take. Nothing it outputs applies itself, and no tool writes.

**Off until measured.** `sales_order_rules.model_assist.thread_agent`, off in
every platform version, and its live eval's bar (`model_readiness.BARS`):
until both say so, every thread message is read by one call (ADR 0012
decision 5).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.agent_turn import AgentTurnPort, TurnCeiling
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_agent_runtime.model.readiness import StepModelPort
from dw_kernel.errors import NotFoundError
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.model_calls import record_model_call
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import reading_context
from dw_sales.application.thread_tools import ThreadContextPort, bound_to
from dw_sales.application.threads import ThreadedCase
from dw_sales.domain.activity import ModelCall
from dw_sales.domain.reply_intent import (
    AgentFallback,
    Author,
    ModelThreadIntents,
    ReplyReading,
    verified_intents,
)

# The prompt the turn renders. Its file is
# `configs/prompts/sales/thread_agent@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
THREAD_AGENT: Final = PromptRef("sales.thread_agent", "1.0.0")
# What one turn may use. Four calls: up to three rounds of look-ups, then the
# answer; a message that needs more is a person's. 16,000 input tokens over
# them, under the run's 60,000 (`configs/models/onprem.yaml`), so one message
# cannot spend a run that processes many. 90 seconds: a warm call measured
# about 3 s on the local model, and the first call of a cold server about 65 s.
CEILING: Final = TurnCeiling(max_model_calls=4, max_input_tokens=16_000, max_seconds=90.0)
# The body the turn is sent, at most: the route takes 6,000 tokens a call,
# and the prompt, the tools' descriptions and what they return share it.
BODY_TOKENS: Final = 2500


@dataclass(frozen=True)
class ThreadAgent:
    """Reads a thread message's intents in a bounded agent turn."""

    turn: AgentTurnPort
    context: ThreadContextPort
    # The model the tenant's steps run on now, for the timing record.
    models: StepModelPort

    async def read(
        self,
        scope: SalesScope,
        message: InboundMessage,
        *,
        author: Author,
        about: str,
        cases: Sequence[ThreadedCase],
        rules_version: str,
        run: RunContext,
    ) -> ReplyReading:
        """The message's reading as code accepts it. Raises
        `TurnCeilingReachedError` over a ceiling and `ModelUnavailableError`
        for no usable answer, a thread whose cases are not one customer's
        included: the caller falls back (module docstring)."""
        binding = await self.context.binding(scope, message, cases)
        if binding is None:
            raise ModelUnavailableError("the thread's cases are not one customer's")
        part = newest_part(message)
        inputs = {
            "context": reading_context(author, about),
            "subject": part.subject,
            "body": cut_to_tokens(part.body, BODY_TOKENS),
        }
        started = time.perf_counter()
        answered = False
        try:
            with bound_to(binding):
                answer = await self.turn.read(inputs, ModelThreadIntents, run=run)
            answered = True
        finally:
            record_model_call(
                ModelCall(
                    prompt=str(self.turn.prompt),
                    model_profile=self.turn.model_profile,
                    model=self._model(run),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    answered=answered,
                )
            )
        return ReplyReading(
            **self._fields(rules_version),
            outcome="read",
            intents=verified_intents(part.text, answer),
        )

    def unavailable(self, rules_version: str, fallback: AgentFallback) -> ReplyReading:
        """The stamp of a message the turn did not read and no one-call
        reading read either: a person reads it, told why."""
        return ReplyReading(**self._fields(rules_version), outcome="unavailable", fallback=fallback)

    def _fields(self, rules_version: str) -> dict[str, str]:
        return {
            "prompt": str(self.turn.prompt),
            "model_profile": self.turn.model_profile,
            "route": self.turn.route,
            "rules": rules_version,
        }

    def _model(self, run: RunContext) -> str | None:
        try:
            return self.models.model_for(run.tenant_id)
        except NotFoundError:
            return None
