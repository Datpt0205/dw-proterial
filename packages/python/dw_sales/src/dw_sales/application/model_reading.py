"""The description reading that goes through DW1's door to a model.

dw_sales ADR 0005: a model may turn a customer's words into a typed reading;
code verifies the reading, resolves every identifier and decides. The door
itself (`InterpretationPort`, `ModelUnavailableError`, `PromptRef`) is the
runtime's, `dw_agent_runtime.model.interpretation` (docs/adr/0013); what is
DW1's here is:

- `DescriptionReader`: the description lines DW1's own vocabulary could not
  read, sent to the model ten at a time and verified by
  `domain.description_reading` before any candidate is computed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
)
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

# The prompt DW1 reads descriptions with. Its file is
# `configs/prompts/sales/description_attributes@1.0.0.yaml`; a test holds the
# two together, and a new wording is a new version here and a new file there.
DESCRIPTION_ATTRIBUTES: Final = PromptRef("sales.description_attributes", "1.0.0")
# Generous for one line's reading (about 120 tokens measured), and a cap on
# what a confused model can spend.
_OUTPUT_TOKENS_PER_LINE: Final = 300


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
