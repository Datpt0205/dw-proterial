"""The description reading that goes through DW1's door to a model.

dw_sales ADR 0005: a model may turn a customer's words into a typed reading;
code verifies the reading, resolves every identifier and decides. The door
itself (`InterpretationPort`, `ModelUnavailableError`, `PromptRef`) is the
runtime's, `dw_agent_runtime.model.interpretation` (docs/adr/0013); what is
DW1's here is:

- `DescriptionReader`: the description lines DW1's own vocabulary could not
  read, sent to the model ten at a time and verified by
  `domain.description_reading` before any candidate is computed; shown, as
  untrusted input like the lines themselves, the tenant's decided lines most
  like them (ticket 43: `application.examples`) and the demonstrations of the
  tenant's approved prompt version (`application.prompt_versions`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    ScoredInterpretationPort,
)
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.application.examples import MAX_SHOWN, DescriptionExample, ExampleFinder, Lookup
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Item
from dw_sales.domain.description_reading import (
    MAX_LINES_PER_READING,
    DescriptionReading,
    ModelDescriptionLine,
    ModelDescriptionReading,
    SpanRead,
    Verified,
    answer_of,
    stated_of,
    verify_reading,
    vocabulary,
)
from dw_sales.domain.descriptions import candidates
from dw_sales.domain.order_checks import MappedLine, map_read_line

# The prompt DW1 reads descriptions with. Its file is
# `configs/prompts/sales/description_attributes@1.2.0.yaml`; a test holds the
# two together, and a new wording is a new version here and a new file there.
# 1.1.0 (ticket 43) adds `examples`: decided lines shown beside the lines read;
# 1.2.0 shows a decided line's confirmed reading as the answer it was.
DESCRIPTION_ATTRIBUTES: Final = PromptRef("sales.description_attributes", "1.2.0")
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


class Shown(Protocol):
    """A decided line a reading is shown: what the customer wrote and the
    item a person kept for it (a `DescriptionExample`, or a demonstration of
    the tenant's prompt version)."""

    @property
    def description(self) -> str: ...

    @property
    def prv_code(self) -> str: ...

    @property
    def spans(self) -> Sequence[SpanRead]: ...


@dataclass(frozen=True, slots=True)
class Demonstrations:
    """The demonstrations a tenant's prompt version shows every reading, and
    the version they belong to (None: the platform's, which shows none)."""

    version: str | None
    shown: tuple[Shown, ...] = ()


class DemonstrationsPort(Protocol):
    """The demonstrations in force for the run's tenant
    (`application.prompt_versions.PromptBook`)."""

    async def demonstrations(self, scope: SalesScope) -> Demonstrations: ...


def prompt_stamp(version: str | None) -> str:
    """What a reading is stamped with: the prompt, and the tenant's prompt
    version where one is in force. The prompt version stays the file's; the
    tenant's version joins the id, so a threshold set on readings with one
    set of demonstrations never gates readings with another (ADR 0015: a new
    prompt or example set applies nothing by itself until re-measured)."""
    if version is None:
        return str(DESCRIPTION_ATTRIBUTES)
    tenant = version.replace(".", "_")
    return f"{DESCRIPTION_ATTRIBUTES.prompt_id}.tenant_{tenant}@{DESCRIPTION_ATTRIBUTES.version}"


@dataclass(frozen=True, slots=True)
class Stamp:
    """What every reading of one call is stamped with: the prompt (and the
    tenant's version) and the decided lines the call showed."""

    prompt: str
    examples: tuple[uuid.UUID, ...]


def shown_lines(shown: Sequence[Shown], items: Sequence[Item]) -> list[dict[str, Any]]:
    """The examples as the prompt shows them, never with a product code.

    - ``read``: the line's own reading, in the answer's shape
      (`answer_of`), where code accepted one and the item a person kept fits
      what it states: a right answer word by word (ticket 43, 2026-11-22).
    - ``item``: otherwise, the attributes of the item a person kept, from the
      item master, most of which the description never says.

    Only the lines `kept_lines` keeps."""
    return [_shown(line, items) for line in kept_lines(shown, items)]


def kept_lines[S: Shown](shown: Sequence[S], items: Sequence[Item]) -> list[S]:
    """The decided lines a prompt shows, in order, at most `MAX_SHOWN`: a
    line whose item is not in the list any more is left out (its answer no
    longer passes code's own check), and so is a description shown already."""
    codes = {item.prv_code for item in items}
    seen: set[str] = set()
    kept: list[S] = []
    for line in shown:
        key = line.description.strip().casefold()
        if line.prv_code not in codes or key in seen:
            continue
        seen.add(key)
        kept.append(line)
        if len(kept) == MAX_SHOWN:
            break
    return kept


def _shown(line: Shown, items: Sequence[Item]) -> dict[str, Any]:
    item = next(item for item in items if item.prv_code == line.prv_code)
    if _fits(line.spans, item):
        return {"description": line.description, "read": answer_of(line.spans)}
    return {"description": line.description, "item": _attributes(item)}


def _fits(spans: Sequence[SpanRead], item: Item) -> bool:
    stated = stated_of(spans) if spans else None
    return stated is not None and bool(candidates(stated, [item]))


def _attributes(item: Item) -> dict[str, Any]:
    stated = item.attributes.model_dump(mode="json", exclude={"standard"}, exclude_none=True)
    if item.family is not None:
        stated = {"family": item.family, **stated}
    return stated


@dataclass(frozen=True, slots=True)
class Showing:
    """What one `DescriptionReader.read` shows beside the lines: where to
    look for decided lines, and, for a replay, the demonstrations to show in
    place of the tenant's (`prompt_optimiser`)."""

    lookup: Lookup
    demonstrations: Demonstrations | None = None


@dataclass(frozen=True)
class DescriptionReader:
    """Reads the descriptions DW1's vocabulary could not, through a model, and
    maps each line by what code accepts of the reading."""

    model: InterpretationPort
    # The tenant's decided lines most like the ones read (ticket 43); None:
    # none shown.
    examples: ExampleFinder | None = None
    # The tenant's approved prompt version's demonstrations; None: the
    # platform's, which shows none.
    prompts: DemonstrationsPort | None = None

    async def read(
        self,
        lines: Sequence[Described],
        items: Sequence[Item],
        *,
        run: RunContext,
        showing: Showing | None = None,
    ) -> dict[int, MappedLine]:
        """Each line's mapping by its reading: a candidate or an ambiguous set
        where the verified attributes fit, unmapped otherwise, and never
        exact. Every line sent comes back, with what the reading did stamped.

        Examples are looked for in the run's scope, never a caller's."""
        scope = SalesScope(TenantId(run.tenant_id), WorkspaceId(run.workspace_id))
        demonstrations = await self._demonstrations(scope, showing)
        mapped: dict[int, MappedLine] = {}
        for start in range(0, len(lines), MAX_LINES_PER_READING):
            batch = lines[start : start + MAX_LINES_PER_READING]
            found: list[DescriptionExample] = []
            if self.examples is not None and showing is not None:
                found = await self.examples.find(
                    scope, [line.description for line in batch], showing.lookup
                )
            kept = kept_lines([*demonstrations.shown, *found], items)
            # The stamp names what the search found and the prompt showed;
            # the demonstrations are the version's, named by `prompt`.
            seen = tuple(e.label_id for e in found if any(e is line for line in kept))
            mapped |= await self._batch(
                batch,
                items,
                run,
                [_shown(line, items) for line in kept],
                Stamp(prompt_stamp(demonstrations.version), seen),
            )
        return mapped

    async def _demonstrations(self, scope: SalesScope, showing: Showing | None) -> Demonstrations:
        if showing is not None and showing.demonstrations is not None:
            return showing.demonstrations
        if self.prompts is None:
            return Demonstrations(None)
        return await self.prompts.demonstrations(scope)

    async def _batch(
        self,
        batch: Sequence[Described],
        items: Sequence[Item],
        run: RunContext,
        examples: list[dict[str, Any]],
        stamp: Stamp,
    ) -> dict[int, MappedLine]:
        inputs = {
            # Code-built JSON inside the untrusted block: a description cannot
            # close its string and pose as another line.
            "lines": json.dumps(
                [{"line_no": line.line_no, "description": line.description} for line in batch],
                ensure_ascii=False,
            ),
            "vocabulary": json.dumps(vocabulary(), ensure_ascii=False),
            # Decided lines, as untrusted as the lines: a customer wrote each
            # description, and a person's choice is shown as attributes only.
            "examples": json.dumps(examples, ensure_ascii=False),
        }
        budget = _OUTPUT_TOKENS_PER_LINE * len(batch) + 100
        scores: Mapping[str, float] | None = None
        try:
            # Scored where the door can score (dw_sales ADR 0015): the same
            # call, with each label's probability from its tokens.
            if isinstance(self.model, ScoredInterpretationPort):
                scored = await self.model.interpret_scored(
                    DESCRIPTION_ATTRIBUTES,
                    inputs,
                    ModelDescriptionReading,
                    run=run,
                    max_output_tokens=budget,
                )
                answer: ModelDescriptionReading | None = scored.answer
                scores = scored.confidences
            else:
                answer = await self.model.interpret(
                    DESCRIPTION_ATTRIBUTES,
                    inputs,
                    ModelDescriptionReading,
                    run=run,
                    max_output_tokens=budget,
                )
        except ModelUnavailableError:
            answer = None
        readings = _by_line(answer, {line.line_no for line in batch})
        if readings is None:
            unavailable = self._stamp(stamp, "unavailable")
            return {line.line_no: map_read_line(None, unavailable, items) for line in batch}
        result: dict[int, MappedLine] = {}
        for line in batch:
            verdict = verify_reading(line.description, readings.get(line.line_no))
            if isinstance(verdict, Verified):
                assert answer is not None  # a verdict comes from an answer
                confidence = _confidence(answer, line.line_no, verdict, scores)
                read = self._stamp(stamp, "read", spans=verdict, confidence=confidence)
                result[line.line_no] = map_read_line(verdict, read, items)
            else:
                refused = self._stamp(stamp, "not_understood", reason=verdict)
                result[line.line_no] = map_read_line(None, refused, items)
        return result

    def _stamp(
        self,
        stamp: Stamp,
        outcome: str,
        *,
        spans: Verified | None = None,
        reason: str | None = None,
        confidence: float | None = None,
    ) -> DescriptionReading:
        return DescriptionReading.model_validate(
            {
                "prompt": stamp.prompt,
                "examples": stamp.examples,
                "model_profile": self.model.model_profile,
                "route": self.model.route,
                "outcome": outcome,
                "reason": reason,
                "spans": spans.spans if spans is not None else (),
                "confidence": confidence,
            }
        )


def _confidence(
    answer: ModelDescriptionReading,
    line_no: int,
    verified: Verified,
    scores: Mapping[str, float] | None,
) -> float | None:
    """How sure the model was of the line's reading: the least probable of
    the labels code took from it (check 5: the one judgement left to the
    model; every span is located and every number parsed by code). None with
    no scores, no label taken, or a label the scores do not cover: a result
    with no confidence never applies itself."""
    if scores is None:
        return None
    index = next(i for i, line in enumerate(answer.lines) if line.line_no == line_no)
    labels = [s.attribute for s in verified.spans if s.read_by == "model"]
    found = [scores.get(f"lines.{index}.{attribute}") for attribute in labels]
    if not found or any(score is None for score in found):
        return None
    return min(score for score in found if score is not None)


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
