"""Which skill reads a message: one constrained, scored call (dw_sales ADR
0015 decision 5, amending ADR 0014 decision 1; ticket 40).

Measured on Strata (ticket 40), a turn left to choose and load a skill by
itself looped: it loaded the skill, then looked things up again and again
until 63 of 80 turns hit their ceiling (0.183 on the bar's set). So the
choice is taken out of the loop: ONE structured call, answered against a JSON
schema whose only field is an enum of the skills served to the run's tenant
plus ``none``, picks the skill; the probability the model gave the tokens of
that name (`dw_agent_runtime.model.scoring`) is how sure it was.

**Code decides what the pick means.** The model's answer is a word, never an
identifier code trusts: a name the served set does not hold is ``none``
whatever the schema allowed (a gateway that did not enforce it, a skill
withdrawn between the call and the answer), and so is a pick less sure than
the tenant's ``model_assist.skill_pick_confidence`` or one with no
confidence at all (a server that returns no token probabilities). No pick
means the step gives no reading of its own: the message is read as if the
step were off (the thread agent where that is on, the one call, a person).

**What the model sees** is each served skill's name and description, as
code wrote them into a JSON list, the conversation's context, the subject
and the newest part; every one of them contained by the registry, since a
description is the tenant's words and the rest is a sender's.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, create_model

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    ScoredInterpretationPort,
)
from dw_agent_runtime.model.readiness import StepModelPort
from dw_agent_runtime.model.skills import Skill, SkillSet
from dw_kernel.errors import NotFoundError
from dw_sales.application.model_calls import record_model_call
from dw_sales.domain.activity import ModelCall

__all__ = ["NO_SKILL", "SKILL_PICK", "PickModelPort", "SkillPick", "SkillPicker", "pick_schema"]

# The prompt the pick renders (`configs/prompts/sales/skill_pick@1.0.0.yaml`).
SKILL_PICK: Final = PromptRef("sales.skill_pick", "1.0.0")
# The answer that names no skill.
NO_SKILL: Final = "none"
# The field the schema has, and the path its confidence is keyed by.
_FIELD: Final = "skill"
# A skill's name is at most 64 characters, about 20 tokens; JSON around it.
_OUTPUT_TOKENS: Final = 48


class PickModelPort(ScoredInterpretationPort, Protocol):
    """A scored one-call door, and the profile it runs on (for the record)."""

    @property
    def model_profile(self) -> str: ...


def pick_schema(names: tuple[str, ...]) -> type[BaseModel]:
    """The answer's schema: ``skill``, one of ``names`` or `NO_SKILL`. Built
    per call because the served set is the tenant's; the gateway sends it as
    the server's JSON schema, so decoding cannot write another word."""
    allowed: Any = Literal.__getitem__((*names, NO_SKILL))
    return create_model(
        "SkillPickAnswer",
        __config__=ConfigDict(frozen=True, extra="forbid"),
        skill=(allowed, ...),
    )


@dataclass(frozen=True, slots=True)
class SkillPick:
    """What the pick call said, and what code made of it."""

    # The skill that reads the message; None: no reading of the step's own.
    skill: Skill | None
    # The name the model answered, as validated (`NO_SKILL` included); None
    # when the call gave no usable answer.
    answered: str | None
    # How sure the model was of that name; None without token probabilities.
    confidence: float | None


@dataclass(frozen=True)
class SkillPicker:
    """Picks the served skill that fits a message (module docstring)."""

    model: PickModelPort
    # The model the tenant's steps run on now, for the timing record.
    models: StepModelPort

    async def pick(
        self, skills: SkillSet, inputs: Mapping[str, str], *, floor: float, run: RunContext
    ) -> SkillPick:
        """The skill for ``inputs`` (``context``, ``subject``, ``body``),
        held to ``floor`` (module docstring)."""
        names = tuple(s.name for s in skills.skills)
        catalogue = json.dumps(
            [{"name": s.name, "description": s.description} for s in skills.skills],
            ensure_ascii=False,
        )
        started = time.perf_counter()
        answered = False
        try:
            scored = await self.model.interpret_scored(
                SKILL_PICK,
                {"skills": catalogue, **inputs},
                pick_schema(names),
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
            answered = True
        except ModelUnavailableError:
            return SkillPick(None, None, None)
        finally:
            record_model_call(
                ModelCall(
                    prompt=str(SKILL_PICK),
                    model_profile=self.model.model_profile,
                    model=self._model(run),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    answered=answered,
                )
            )
        name = str(getattr(scored.answer, _FIELD))
        confidence = (scored.confidences or {}).get(_FIELD)
        # Code's reading of the word: a name the set does not serve is no
        # skill, whatever the decoder let through.
        skill = skills.named(name) if name != NO_SKILL else None
        if skill is None or confidence is None or confidence < floor:
            return SkillPick(None, name, confidence)
        return SkillPick(skill, name, confidence)

    def _model(self, run: RunContext) -> str | None:
        try:
            return self.models.model_for(run.tenant_id)
        except NotFoundError:
            return None
