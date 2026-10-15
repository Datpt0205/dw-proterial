"""The model in the smoke: answers the live lane recorded, replayed by input.

Tickets 29 and 31 call a model once per message, so an answer is recorded
against the exact inputs it was given (`answer_key`: the prompt and every
input, hashed). The smoke replays it for the same inputs and fails loudly for
inputs it never saw: a change to what a step sends shows up as a fixture to
record again, not as a quietly different score. Ticket 28's per-line answers
keep their own replay (`descriptions.Replayed`); `ByPrompt` puts the two
behind one `InterpretationPort` for a flow that calls both.

In the live lane, `Observed` wraps the model under test, and
`failing_without_live_answers` fails a case in which that model was called
and gave no usable answer: every model step degrades an unavailable answer
to a person, which the guards grade as safe, so a run of timeouts would
otherwise pass every case while reading nothing.
"""

from __future__ import annotations

import functools
import hashlib
import json
import statistics
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_evals.graders import Grader, GraderContext, GradeResult
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef


def answer_key(prompt: PromptRef, inputs: Mapping[str, str]) -> str:
    """What an answer is recorded under: the prompt and its exact inputs."""
    canonical = json.dumps(
        {"prompt": str(prompt), "inputs": dict(inputs)}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


@dataclass
class Recorded:
    """`InterpretationPort` answering from recorded answers, by `answer_key`.

    An answer of None replays a call that gave no usable answer (the live
    model timed out or answered outside the schema). ``failure`` raises
    instead of answering; ``raw`` answers every call with one scripted
    answer, validated as the gateway would. With ``prompts`` each call renders
    the versioned prompt first, so a prompt and its inputs that stopped
    agreeing fail here as on a real model.
    """

    answers: Mapping[str, Mapping[str, Any] | None] = field(default_factory=dict)
    prompts: PromptRegistry | None = None
    failure: Exception | None = None
    raw: Mapping[str, Any] | None = None
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000
    calls: list[tuple[PromptRef, RunContext, dict[str, str]]] = field(default_factory=list)

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        self.calls.append((prompt, run, dict(inputs)))
        if self.prompts is not None:
            self.prompts.render(
                prompt.prompt_id, prompt.version, dict(inputs), tenant_id=run.tenant_id
            )
        if self.failure is not None:
            raise self.failure
        answer = self.raw if self.raw is not None else self.answers[answer_key(prompt, inputs)]
        if answer is None:
            raise ModelUnavailableError("recorded: no usable answer")
        try:
            return schema.model_validate(answer)
        except ValidationError as exc:
            # What the gateway does with an answer outside the schema.
            raise ModelUnavailableError("ModelOutputInvalidError") from exc


@dataclass
class ByPrompt:
    """One `InterpretationPort` over a model per prompt id, for a flow that
    calls several steps; a prompt with no model fails loudly."""

    models: Mapping[str, InterpretationPort]
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        return await self.models[prompt.prompt_id].interpret(
            prompt, inputs, schema, run=run, max_output_tokens=max_output_tokens
        )


def load_answers(path: Path) -> dict[str, Mapping[str, Any] | None]:
    """The answers a recorded file holds (``{"answers": {key: answer}}``)."""
    if not path.exists():
        return {}
    answers: dict[str, Mapping[str, Any] | None] = json.loads(path.read_text(encoding="utf-8"))[
        "answers"
    ]
    return answers


@dataclass
class Observed:
    """Wraps the model under test in a live lane: times every call by prompt
    and keeps each answer, so the lane can report latency and record what the
    smoke replays (`--record`). Ticket 28's description readings are kept per
    line, by description, as its replay reads them; every other step's answer
    by `answer_key`, None where the call gave no usable answer."""

    inner: Any
    seconds: dict[str, list[float]] = field(default_factory=dict)
    # Ticket 28's: description -> the line's answer.
    answers: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    # Every other step's: prompt id -> answer key -> answer.
    recorded: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[PromptRef, RunContext, dict[str, str]]] = field(default_factory=list)
    # The calls that gave an answer in the schema; the rest were unavailable.
    answered: int = 0

    @property
    def model_profile(self) -> str:
        return str(self.inner.model_profile)

    @property
    def route(self) -> str:
        return str(self.inner.route)

    @property
    def max_input_tokens(self) -> int:
        return int(self.inner.max_input_tokens)

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        self.calls.append((prompt, run, dict(inputs)))
        started = time.perf_counter()
        per_line = prompt.prompt_id == "sales.description_attributes"
        key = answer_key(prompt, inputs)
        try:
            answer: OutputT = await self.inner.interpret(
                prompt, inputs, schema, run=run, max_output_tokens=max_output_tokens
            )
        except ModelUnavailableError:
            if not per_line:
                self.recorded.setdefault(prompt.prompt_id, {})[key] = None
            raise
        finally:
            self.seconds.setdefault(prompt.prompt_id, []).append(time.perf_counter() - started)
        self.answered += 1
        if per_line:
            self._lines(inputs, answer)
        else:
            self.recorded.setdefault(prompt.prompt_id, {})[key] = answer.model_dump(mode="json")
        return answer

    def _lines(self, inputs: Mapping[str, str], answer: BaseModel) -> None:
        sent = json.loads(inputs["lines"])
        by_no = {line["line_no"]: line for line in answer.model_dump(mode="json").get("lines", [])}
        for line in sent:
            got = by_no.get(line["line_no"])
            self.answers[line["description"]] = (
                None
                if got is None
                else {k: v for k, v in got.items() if k != "line_no" and v is not None}
            )


def latency(model: Any, prompt_id: str) -> dict[str, float] | None:
    """p50/p95 seconds per call of ``prompt_id`` in a live lane, else None."""
    seconds = getattr(model, "seconds", {}).get(prompt_id)
    if not seconds:
        return None
    ordered = sorted(seconds)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "calls": len(ordered),
        "p50_s": round(statistics.median(ordered), 2),
        "p95_s": round(p95, 2),
        "max_s": round(ordered[-1], 2),
    }


def failing_without_live_answers(grader: Grader) -> Grader:
    """``grader``, failing a live case in which the model under test was
    called and not one call gave a usable answer (ticket 28's live lane
    reported PASS with every call unavailable). Its own verdict stands
    otherwise; the smoke (no live model) is graded as before. A live model
    that does not count its answers fails closed."""

    @functools.wraps(grader)
    def graded(
        ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
    ) -> GradeResult:
        model = ctx.live_model
        if model is None:
            return grader(ctx, input_data, expected)
        if not isinstance(model, Observed):
            return GradeResult.fail("the live model is not observed: its answers are not counted")
        calls, answered = len(model.calls), model.answered
        result = grader(ctx, input_data, expected)
        made = len(model.calls) - calls
        if result.passed and made and model.answered == answered:
            return GradeResult.fail(
                "the live model gave no usable answer", live_calls=made, **result.details
            )
        return result

    return graded
