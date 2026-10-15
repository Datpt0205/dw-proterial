"""DW1's one door to a model, and the description reading that goes through it.

dw_sales ADR 0005: a model may turn a customer's words into a typed reading;
code verifies the reading, resolves every identifier and decides. This module
holds both halves of DW1's side of that rule:

- `InterpretationPort`, declared here by its consumer and satisfied at the
  composition root by the platform's model gateway
  (`dw_sales.adapters.model_interpretation`). It is the narrowest thing DW1
  asks of a model: "interpret these inputs into this schema", under a
  versioned prompt, attributed to the run that asked (`RunContext`: tenant,
  worker, release), with no tool offered
  (ADR 0007-document-content-turns-cannot-call-outbound-tools). A model that is down, too slow or
  answers outside the schema is `ModelUnavailableError`, which a step turns into "DW1 did not
  understand" for a person. A budget or quota refusal is not that error: it stops the run, and is
  reported as a stop.
- `DescriptionReader`: the description lines DW1's own vocabulary could not
  read, sent to the model ten at a time and verified by
  `domain.description_reading` before any candidate is computed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_sales.domain.catalog import Item
from dw_sales.domain.description_reading import (
    MAX_LINES_PER_READING,
    DescriptionReading,
    ModelDescriptionLine,
    ModelDescriptionReading,
    Verified,
    verify_reading,
    vocabulary,
)
from dw_sales.domain.order_checks import MappedLine, map_read_line


@dataclass(frozen=True, slots=True)
class PromptRef:
    """A versioned prompt in ``configs/prompts``, pinned by the release manifest."""

    prompt_id: str
    version: str

    def __str__(self) -> str:
        return f"{self.prompt_id}@{self.version}"


# The prompt DW1 reads descriptions with. Its file is
# `configs/prompts/sales/description_attributes@1.0.0.yaml`; a test holds the
# two together, and a new wording is a new version here and a new file there.
DESCRIPTION_ATTRIBUTES: Final = PromptRef("sales.description_attributes", "1.0.0")
# Generous for one line's reading (about 120 tokens measured), and a cap on
# what a confused model can spend.
_OUTPUT_TOKENS_PER_LINE: Final = 300


def estimated_tokens(text: str) -> int:
    """An upper estimate of the tokens ``text`` costs a local model: a wide
    character (CJK, kana) or any other non-ASCII letter as one token, ASCII
    as one per three characters. Generous on purpose: a step that sends less
    than it could costs one more call; one that sends more than fits is
    refused by the server."""
    wide = sum(1 for char in text if not char.isascii())
    return wide + (len(text) - wide + 2) // 3


def cut_to_tokens(text: str, room: int) -> str:
    """``text`` cut from its end until `estimated_tokens` says it fits in
    ``room``: what a step reads is in a message's first lines, and the rest is
    not sent rather than refused by the server."""
    cut = text
    while cut and estimated_tokens(cut) > room:
        cut = cut[: len(cut) * 3 // 4]
    return cut


class ModelUnavailableError(Exception):
    """No usable answer: the model is down or timed out, its output did not
    validate against the schema, or no model is configured for the profile.
    The step degrades to a person; it never guesses."""


class InterpretationPort(Protocol):
    """Interpret ``inputs`` into ``schema`` under ``prompt``, for ``run``.

    ``inputs`` are untrusted: the prompt registry contains each one in an
    escaped block. The answer is validated into ``schema`` before it is
    returned. Raises `ModelUnavailableError` when there is no usable answer;
    a budget or quota refusal propagates as itself.
    """

    @property
    def model_profile(self) -> str:
        """The profile every call runs on: what a reading is stamped with."""
        ...

    @property
    def route(self) -> str:
        """The profile's route every call runs on."""
        ...

    @property
    def max_input_tokens(self) -> int:
        """The most input one call on the route is sent, as the route declares
        it (`ModelRoute.max_input_tokens`). A step cuts or splits what it sends
        under this: an input the server refuses as too long is not retried
        into success, it only costs the retries."""
        ...

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT: ...


class Described(Protocol):
    """A line with the customer's description of its item: a PO line, or an
    item a request for quotation lists (ticket 29)."""

    @property
    def line_no(self) -> int: ...

    @property
    def description(self) -> str: ...


@dataclass(frozen=True)
class DescriptionReader:
    """Reads the descriptions DW1's vocabulary could not, through a model, and
    maps each line by what code accepts of the reading."""

    model: InterpretationPort

    async def read(
        self, lines: Sequence[Described], items: Sequence[Item], *, run: RunContext
    ) -> dict[int, MappedLine]:
        """Each line's mapping by its reading: a candidate or an ambiguous set
        where the verified attributes fit, unmapped otherwise, and never
        exact. Every line sent comes back, with what the reading did stamped."""
        mapped: dict[int, MappedLine] = {}
        for start in range(0, len(lines), MAX_LINES_PER_READING):
            batch = lines[start : start + MAX_LINES_PER_READING]
            mapped |= await self._batch(batch, items, run)
        return mapped

    async def _batch(
        self, batch: Sequence[Described], items: Sequence[Item], run: RunContext
    ) -> dict[int, MappedLine]:
        inputs = {
            # Code-built JSON inside the untrusted block: a description cannot
            # close its string and pose as another line.
            "lines": json.dumps(
                [{"line_no": line.line_no, "description": line.description} for line in batch],
                ensure_ascii=False,
            ),
            "vocabulary": json.dumps(vocabulary(), ensure_ascii=False),
        }
        try:
            answer = await self.model.interpret(
                DESCRIPTION_ATTRIBUTES,
                inputs,
                ModelDescriptionReading,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS_PER_LINE * len(batch) + 100,
            )
        except ModelUnavailableError:
            answer = None
        readings = _by_line(answer, {line.line_no for line in batch})
        if readings is None:
            unavailable = self._stamp("unavailable")
            return {line.line_no: map_read_line(None, unavailable, items) for line in batch}
        result: dict[int, MappedLine] = {}
        for line in batch:
            verdict = verify_reading(line.description, readings.get(line.line_no))
            if isinstance(verdict, Verified):
                read = self._stamp("read", spans=verdict)
                result[line.line_no] = map_read_line(verdict, read, items)
            else:
                refused = self._stamp("not_understood", reason=verdict)
                result[line.line_no] = map_read_line(None, refused, items)
        return result

    def _stamp(
        self,
        outcome: str,
        *,
        spans: Verified | None = None,
        reason: str | None = None,
    ) -> DescriptionReading:
        return DescriptionReading.model_validate(
            {
                "prompt": str(DESCRIPTION_ATTRIBUTES),
                "model_profile": self.model.model_profile,
                "route": self.model.route,
                "outcome": outcome,
                "reason": reason,
                "spans": spans.spans if spans is not None else (),
            }
        )


def _by_line(
    answer: ModelDescriptionReading | None, sent: set[int]
) -> dict[int, ModelDescriptionLine] | None:
    """The answer by line number, or None when it is no answer at all: none
    came, or it names a line that was not sent, or one line twice. A line
    the answer leaves out is that line's `line_missing`, not the batch's."""
    if answer is None:
        return None
    numbers = [line.line_no for line in answer.lines]
    if len(numbers) != len(set(numbers)) or not set(numbers) <= sent:
        return None
    return {line.line_no: line for line in answer.lines}
