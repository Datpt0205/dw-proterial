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

**DW1's agent with skills** (dw_sales ADR 0014, ticket 40) is this reader with
skills (`skills`). Code resolves the skills the run's tenant holds
(`skills.SkillBook`), one scored call picks the one that fits
(`skill_pick.SkillPicker`, ADR 0015 decision 5), and the turn under
`DW1_AGENT` reads the message with DW1's conduct and that skill's words in its
prompt: no catalogue and no loading tool, so no loop for choosing (measured
on Strata, a turn left to load its own skill looped, 0.183). The look-up
tools stay, for what the skill says a message leans on. No skill picked, or
one less sure than the tenant's floor: no reading of the step's own, and the
message is read as if the step were off. A reading is checked exactly as
above and stamps the skill version it read with (`ReplyReading.skills`). Its
own switch, `model_assist.skill_intents`, and its own bar: off and below it,
nothing of this runs.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.agent_turn import AgentTurnPort, TurnCeiling
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_agent_runtime.model.readiness import StepModelPort
from dw_agent_runtime.model.skills import SkillSet
from dw_kernel.errors import NotFoundError
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.model_calls import record_model_call
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import reading_context
from dw_sales.application.skill_pick import SkillPicker
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
# DW1's agent with skills (ticket 40): its prompt (`configs/prompts/sales/
# dw1_agent@1.1.0.yaml`, the picked skill's words in it), and its ceiling,
# unchanged since 1.0.0: one call more than the thread agent's, and the
# tokens for DW1's conduct and the skill's instructions, which every call of
# the turn carries: about 1,700 tokens for the first skill. 120 seconds.
DW1_AGENT: Final = PromptRef("sales.dw1_agent", "1.1.0")
SKILL_CEILING: Final = TurnCeiling(max_model_calls=5, max_input_tokens=24_000, max_seconds=120.0)


class SkillSetPort(Protocol):
    """The skills a run's tenant holds now: each platform skill, the
    tenant's approved version of it where it has one."""

    async def skill_set(self, run: RunContext) -> SkillSet: ...


@dataclass(frozen=True)
class TurnSkillChoice:
    """What DW1's agent with skills reads with (ticket 40): the skills the
    run's tenant holds, the scored call that picks one, and DW1's conduct
    (`AGENT.md`, the platform's text) that every turn's prompt carries."""

    book: SkillSetPort
    picker: SkillPicker
    agent: str


@dataclass(frozen=True)
class ThreadAgent:
    """Reads a thread message's intents in a bounded agent turn."""

    turn: AgentTurnPort
    context: ThreadContextPort
    # The model the tenant's steps run on now, for the timing record.
    models: StepModelPort
    # The skill picked for each turn, from those resolved for its run
    # (ticket 40). None: the thread agent of tickets 30 and 31, which reads
    # with none.
    skills: TurnSkillChoice | None = None

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
        pick_floor: float = 1.0,
    ) -> ReplyReading | None:
        """The message's reading as code accepts it; None where this reader
        has skills and none was picked at ``pick_floor`` or above (the
        tenant's `skill_pick_confidence`): the caller reads it as if the step
        were off. Raises `TurnCeilingReachedError` over a ceiling and
        `ModelUnavailableError` for no usable answer, a thread whose cases
        are not one customer's included: the caller falls back (module
        docstring)."""
        binding = await self.context.binding(scope, message, cases)
        if binding is None:
            raise ModelUnavailableError("the thread's cases are not one customer's")
        part = newest_part(message)
        inputs = {
            "context": reading_context(author, about),
            "subject": part.subject,
            "body": cut_to_tokens(part.body, BODY_TOKENS),
        }
        used: tuple[str, ...] = ()
        if self.skills is not None:
            # Resolved for the run's tenant, never the message's.
            held = await self.skills.book.skill_set(run)
            picked = await self.skills.picker.pick(held, inputs, floor=pick_floor, run=run)
            if picked.skill is None:
                return None
            inputs = {**inputs, "agent": self.skills.agent, "skill": picked.skill.body}
            used = (picked.skill.ref,)
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
            skills=used,
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
