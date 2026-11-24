"""A customer's SalesOrder skill drafted by DW1's model from the files the
PIC made (ticket 66, dw_sales ADR 0013 addendum of 2026-11-24).

A customer with no SalesOrder skill of its own is filled with the platform's
generic one (`salesorder_skills`). Most customers need nothing more: what
differs between them is data (the convert list, the item master, the upload
layout), which code hands the fill. A few have exceptions a skill says in
words (a group code on every row, a date moved, a PO and line joined), and
nobody in Sales writes skills. So when ticket 38's learning keeps a worked
pair it writes `PAIR_ADDED`, and the worker's `sales_salesorder_skill_draft`
lane drafts the customer's skill:

1. **Fill the customer's newest pairs with the skill in force.** Every pair
   reproduced: nothing to draft (``not_needed``).
2. **One model call** (`SKILL_DRAFT`) is shown the skill in force, the
   layout's columns and, for up to `PAIRS_SHOWN` failing pairs, every cell
   that differs: what the PIC wrote, what DW wrote and why, with the row's
   values and look-ups. It answers the whole skill, never a patch.
3. **Code checks the draft** (`check_draft`). The trace already refuses a
   cell whose source does not hold, so what a skill's words can put into a
   file unchecked is a constant: every constant the draft adds must be a
   text the PIC's files hold, and none may be a value of a PO. A PO's words
   are untrusted (a line can carry an instruction): they cannot become a
   constant written into every SalesOrder of the customer.
4. **Code replays the draft** on the same pairs and proposes it only where
   it `gains`: more pairs reproduced and none lost that the skill in force
   reproduced. Proposed by the lane itself (`system_actor`), never applied:
   the replay lane (`salesorder_pairs`) replays it again on its own, and the
   head approves only where every pair came out as the PIC's file, never
   the lane (`RuleDecisionGuard`).

A version already waiting for the customer stops a draft (``waiting``): the
head has one to read first. A comparison with an unanswered fill proves
nothing and proposes nothing (``unavailable``). Everything is read in the
event's own scope: that tenant's book, that workspace's pairs of that
customer, the tools bound to that customer.

The lane logs ids and counts only, never a cell or the skill's words.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import ConflictError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleVersionEngine
from dw_platform.domain.audit import system_actor
from dw_sales.application.artifact_content import BravoUploadLayout, Value
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import MemberDirectoryPort, SalesScope
from dw_sales.application.rules import ProposerNames, RuleKey, rule_work
from dw_sales.application.salesorder_fill import (
    FLAG_WORDS,
    FillSkill,
    PairCheck,
    PoRow,
    SalesOrderFiller,
    SalesOrderTools,
    TracedFill,
    calls_for_row,
    check_against,
    po_rows,
    prepared_calls,
    shown_columns,
    skill_constants,
)
from dw_sales.application.salesorder_learning import (
    ExampleUnitOfWorkFactory,
    LearningRulesPort,
    WorkedPair,
)
from dw_sales.application.salesorder_pairs import (
    PAIRS_REPLAYED,
    PairCatalogPort,
    fill_pair,
    lane_run,
)
from dw_sales.application.salesorder_rules import canonical
from dw_sales.application.skills import (
    INSTRUCTIONS_LIMIT,
    REGISTRY,
    SkillBook,
    SkillDocument,
    salesorder_key,
)

__all__ = [
    "SKILL_DRAFT",
    "SKILL_DRAFT_LANE",
    "DraftOutcome",
    "DraftResult",
    "ModelSkillDraft",
    "SalesOrderSkillDrafter",
    "as_compared",
    "check_draft",
    "draft_inputs",
    "gains",
]

_LOG = logging.getLogger("dw_sales.salesorder_skill_drafts")

SKILL_DRAFT_LANE: Final = "sales_salesorder_skill_draft"
# The prompt a draft is asked with. Its file is
# `configs/prompts/sales/salesorder_skill_draft@1.0.0.yaml`; a test holds the
# two together, and a new wording is a new version here and a new file there.
SKILL_DRAFT: Final = PromptRef("sales.salesorder_skill_draft", "1.0.0")
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 2000
# The answer is a whole skill: its limit is about 4,000 tokens.
_OUTPUT_TOKENS: Final = 6000
# The failing pairs, and each one's differing cells, a draft is shown at
# most; fewer where they do not fit the route.
PAIRS_SHOWN: Final = 3
# How many times a draft is asked, each round shown the previous draft's own
# differences: on Strata the first draft named KHB's shifted date and wrote
# its price's unit factor backwards (ticket 66). Latency does not matter here.
DRAFT_ROUNDS: Final = 3
CELLS_SHOWN: Final = 40
_CELL: Final = re.compile(r"^([A-Z]{1,3})([0-9]{1,4})$")

DraftOutcome = Literal[
    "proposed",
    "not_needed",
    "waiting",
    "no_customer",
    "no_pairs",
    "unavailable",
    "refused",
    "no_gain",
]
DraftRefusal = Literal["constant_not_in_pic_files", "constant_is_po_value", "unchanged"]


class ModelSkillDraft(BaseModel):
    """The model's answer: the customer's whole skill, as words."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    instructions: str = Field(min_length=1, max_length=INSTRUCTIONS_LIMIT)


@dataclass(frozen=True, slots=True)
class DraftResult:
    """What one draft did, for the lane's log: counts and ids only."""

    outcome: DraftOutcome
    pairs: int = 0
    right_before: int = 0
    right_after: int = 0
    version_ref: str | None = None
    reason: DraftRefusal | None = None


@dataclass(frozen=True, slots=True)
class _Pair:
    """A worked pair as a draft reads it: the PO's rows and look-ups, and the
    fill of the skill in force compared with the PIC's file."""

    pair: WorkedPair
    rows: list[PoRow]
    fill: TracedFill
    check: PairCheck


def gains(before: Sequence[bool], after: Sequence[bool]) -> bool:
    """Whether ``after`` reproduces more pairs than ``before`` and loses none
    ``before`` reproduced: one more right does not buy one lost."""
    lost = any(was and not now for was, now in zip(before, after, strict=True))
    return not lost and sum(after) > sum(before)


def check_draft(drafted: str, current: str, pairs: Sequence[_Pair]) -> DraftRefusal | None:
    """Why the draft's words are refused before any replay, or None (module
    docstring, step 3)."""
    if drafted.strip() == current.strip():
        return "unchanged"
    pic = {
        canonical(text)
        for p in pairs
        for row in p.pair.expected
        for text in row.values()
        if text and text.strip()
    }
    po = {
        canonical(value)
        for p in pairs
        for row in p.rows
        for value in row.anchors().values()
        if value is not None and value.strip()
    }
    for constant in sorted(skill_constants(drafted) - skill_constants(current)):
        shown = canonical(constant)
        if shown in po:
            return "constant_is_po_value"
        if shown not in pic:
            return "constant_not_in_pic_files"
    return None


def _differing(layout: BravoUploadLayout, p: _Pair, tools: SalesOrderTools) -> dict[str, object]:
    """One failing pair as the draft is shown it: each differing cell, the
    rows those cells are on, and the look-ups made for those rows."""
    by_row = {
        traced.row: (traced, expected)
        for traced, expected in zip(p.fill.rows, p.pair.expected, strict=False)
    }
    headers = {c["column"]: c["header"] for c in shown_columns(layout)}
    cells: list[dict[str, object]] = []
    rows: set[int] = set()
    for name in p.check.differing[:CELLS_SHOWN]:
        found = _CELL.match(name)
        if found is None or int(found.group(2)) not in by_row:
            continue
        letter, row = found.group(1), int(found.group(2))
        traced, expected = by_row[row]
        cell = next((c for c in traced.cells if c.column == letter), None)
        rows.add(row)
        cells.append(
            {
                "cell": name,
                "header": headers.get(letter),
                "pic_wrote": as_compared(expected.get(letter)),
                "dw_wrote": None if cell is None else as_compared(cell.value),
                "why": (
                    FLAG_WORDS[cell.flag]
                    if cell is not None and cell.flag is not None
                    else "khác giá trị PIC ghi"
                ),
            }
        )
    calls = prepared_calls(tools, p.rows)
    shown_rows = [r for r in p.rows if r.row in rows]
    wanted = set().union(*(calls_for_row(calls, r) for r in shown_rows)) if shown_rows else set()
    if p.check.rows_expected != p.check.rows_got:
        cells.append(
            {
                "cell": "rows",
                "pic_wrote": str(p.check.rows_expected),
                "dw_wrote": str(p.check.rows_got),
                "why": "số dòng khác",
            }
        )
    return {
        "cells": cells,
        "po_rows": [{"row": r.row, "values": r.anchors()} for r in shown_rows],
        # The PIC's whole row, every column it fills: a skill that names each
        # computed column fills it every time, where one that leaves a
        # column to the generic words fills it some times (ticket 66).
        "pic_rows": [
            {
                "row": r.row,
                "cells": {
                    letter: as_compared(text)
                    for letter, text in by_row[r.row][1].items()
                    if text and text.strip()
                },
            }
            for r in shown_rows
        ],
        "calls": [c.model_dump(mode="json") for c in calls if c.call in wanted],
    }


def as_compared(value: Value) -> str | None:
    """A cell as the comparison reads it (`canonical`): a date by its day, a
    number by its value. Shown raw, a PIC's date cell read as
    ``2026-12-10T00:00:00`` beside DW's ``2026-12-20`` and the model wrote a
    rule about the time of day, not the ten days (ticket 66, on Strata)."""
    found = canonical(value)
    if found is None:
        return None
    if isinstance(found, Decimal):
        return format(found.normalize(), "f")
    if isinstance(found, date):
        return found.isoformat()
    return found


def draft_inputs(
    layout: BravoUploadLayout,
    current: str,
    failing: Sequence[_Pair],
    tools: SalesOrderTools,
    room: int,
) -> dict[str, str] | None:
    """What the draft is shown, as code-built JSON beside the skill's words;
    fewer pairs, then fewer cells, until it fits ``room``; None when not even
    one pair's first cell fits."""
    columns = json.dumps(shown_columns(layout), ensure_ascii=False)
    for shown in range(min(PAIRS_SHOWN, len(failing)), 0, -1):
        differing = [_differing(layout, p, tools) for p in failing[:shown]]
        inputs = {
            "skill": current,
            "columns": columns,
            "differing": json.dumps(differing, ensure_ascii=False),
        }
        if estimated_tokens("".join(inputs.values())) <= room:
            return inputs
    return None


@dataclass(frozen=True)
class SalesOrderSkillDrafter:
    """The `sales_salesorder_skill_draft` lane's work for one customer of one
    scope (module docstring)."""

    uow: SalesUnitOfWorkFactory
    pairs: ExampleUnitOfWorkFactory
    book: SkillBook
    rules: LearningRulesPort
    catalog: PairCatalogPort
    model: InterpretationPort
    directory: MemberDirectoryPort
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def draft(self, scope: SalesScope, customer_code: str) -> DraftResult:
        key = salesorder_key(customer_code)
        context = _lane_context(scope)
        engine = self._engine()
        versions = await engine.list_all(context, keys=(key,))
        if any(v.status == "proposed" for v in versions):
            return DraftResult("waiting")
        customer = (await self.catalog.customer_by_code(scope, customer_code)).data
        if customer is None:
            return DraftResult("no_customer")
        async with self.pairs(scope) as work:
            kept = list(await work.pairs.for_customer(customer_code, PAIRS_REPLAYED))
        if not kept:
            return DraftResult("no_pairs")
        layout = (await self.rules.current(scope, RuleKey.BRAVO_UPLOAD)).policy
        assert isinstance(layout, BravoUploadLayout)
        current = (await self.book.current(scope, key)).policy
        assert isinstance(current, SkillDocument)
        tools = SalesOrderTools.bound(
            customer,
            (await self.catalog.convert_list(scope)).data,
            (await self.catalog.items(scope)).data,
        )
        filler = SalesOrderFiller(self.model)
        read: list[_Pair] = []
        for pair in kept:
            fill = await fill_pair(
                filler,
                layout,
                tools,
                pair,
                _skill(current.ref, current.instructions),
                self._run(scope),
            )
            if fill is None:
                return DraftResult("unavailable", pairs=len(kept))
            rows = po_rows(pair.document, tools, pair.received_on)
            read.append(_Pair(pair, rows, fill, check_against(layout, fill, pair.expected)))
        before = [p.check.reproduced for p in read]
        if all(before):
            return DraftResult("not_needed", pairs=len(read), right_before=len(read))
        n, right = len(read), sum(before)
        room = self.model.max_input_tokens - PROMPT_TOKENS
        words, state = current.instructions, read
        best: tuple[str, list[bool]] | None = None
        for _ in range(DRAFT_ROUNDS):
            inputs = draft_inputs(
                layout, words, [p for p in state if not p.check.reproduced], tools, room
            )
            if inputs is None:
                break
            try:
                answer = await self.model.interpret(
                    SKILL_DRAFT,
                    inputs,
                    ModelSkillDraft,
                    run=self._run(scope),
                    max_output_tokens=_OUTPUT_TOKENS,
                )
            except (ModelUnavailableError, QuotaExceededError):
                break
            # Checked against the skill in force, every round: a constant
            # one round added is no proof for the next.
            refused = check_draft(answer.instructions, current.instructions, read)
            if refused is not None:
                return self._logged(scope, key, DraftResult("refused", n, right, reason=refused))
            replayed = await self._replayed(scope, layout, tools, read, key, answer.instructions)
            if replayed is None:
                break
            after = [p.check.reproduced for p in replayed]
            if gains(before, after) and (best is None or sum(after) > sum(best[1])):
                best = (answer.instructions, after)
            if all(after):
                break
            # The next round reads this draft's own differences.
            words, state = answer.instructions, replayed
        if best is None:
            outcome: DraftOutcome = "no_gain" if words != current.instructions else "unavailable"
            return self._logged(scope, key, DraftResult(outcome, n, right))
        drafted_words, after = best
        document = SkillDocument(
            policy_id=key,
            policy_version=_next_version(current.policy_version, [v.version for v in versions]),
            description=(
                f"Customer {customer_code}'s PO into Bravo's SalesOrder file, drafted by DW1"
                " from the PIC's files."
            ),
            instructions=drafted_words,
        )
        try:
            version = await engine.propose(
                context, key, document.model_dump(mode="json"), applies_directly=False
            )
        except ConflictError:
            # Another proposal arrived meanwhile: the head reads that one first.
            return DraftResult("waiting", n, right, sum(after))
        return self._logged(scope, key, DraftResult("proposed", n, right, sum(after), version.ref))

    async def _replayed(
        self,
        scope: SalesScope,
        layout: BravoUploadLayout,
        tools: SalesOrderTools,
        read: Sequence[_Pair],
        key: str,
        words: str,
    ) -> list[_Pair] | None:
        """Every pair filled again with ``words``; None where a fill got no
        usable answer: a comparison with a gap proves nothing."""
        filler = SalesOrderFiller(self.model)
        replayed = []
        for p in read:
            fill = await fill_pair(
                filler, layout, tools, p.pair, _skill(f"{key}@draft", words), self._run(scope)
            )
            if fill is None:
                return None
            replayed.append(
                _Pair(p.pair, p.rows, fill, check_against(layout, fill, p.pair.expected))
            )
        return replayed

    def _logged(self, scope: SalesScope, key: str, result: DraftResult) -> DraftResult:
        # Ids and counts only: never a cell or the skill's words.
        _LOG.info(
            "SalesOrder skill draft for %s in tenant %s: %s (%s), %s/%s pairs before, %s after",
            key,
            scope.tenant_id.value,
            result.outcome,
            result.reason or result.version_ref or "-",
            result.right_before,
            result.pairs,
            result.right_after,
        )
        return result

    def _engine(self) -> RuleVersionEngine:
        return RuleVersionEngine(
            REGISTRY,
            rule_work(self.uow),
            self.book,
            self.clock,
            self.ids,
            ProposerNames(self.directory),
        )

    def _run(self, scope: SalesScope) -> RunContext:
        return lane_run(
            SKILL_DRAFT_LANE, scope, self.ids.new_uuid(), self.worker_id, self.worker_version
        )


def _skill(ref: str, instructions: str) -> FillSkill:
    return FillSkill(ref=ref, instructions=instructions)


def _next_version(current: str, taken: Sequence[str]) -> str:
    """The next minor version above the one in force and every number the
    tenant has used, so a rejected proposal's number is never reused."""
    major, minor = max(tuple(int(p) for p in n.split(".")[:2]) for n in (current, *taken))
    return f"{major}.{minor + 1}.0"


def _lane_context(scope: SalesScope) -> AccessContext:
    """The lane proposing in ``scope``: its own actor, no scope at all. It
    proposes; it may decide nothing (`RuleDecisionGuard`)."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SKILL_DRAFT_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
