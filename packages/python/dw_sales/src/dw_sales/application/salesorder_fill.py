"""A customer's SalesOrder filled by DW1's model with the customer's skill and
read-only tools, every cell traced by code (dw_sales ADR 0013 as amended
2026-11-16 under ADR 0014, ticket 41).

ADR 0013's rules were learned from one worked example and broke on the first
PO it did not show. Here the customer's way is words, a skill
(``salesorder-<customer>``, the tenant's approved version, else the
platform's generic one, `SalesOrderSkills`), and the model fills each PO's
rows with it, naming for every cell where its value came from. Code then
traces every cell of every row, and writes only what it traced:

- **The tools** are read-only and bound by code to the PO's customer
  (`SalesOrderTools`): the customer's record, its own convert list, and the
  items that list reaches in the item master. A tool never answers with
  another customer's rows, whatever it is asked: the binding is code's, the
  input only the code to look up. Code calls them for the PO before the turn
  (every code the PO prints, every item those codes reach) and shows each
  call with an id (`prepared_calls`): the PO decides which look-ups exist, so
  no fact is withheld, and the turn has no loop to fall into (measured on
  Strata in ticket 40, a turn left to choose its calls looped). The PO as
  read (`po_rows`: each row of the file, its values by field, each at an
  anchor ``R<row>.<field>``), the calendar and unit factors are the
  computations below, which code redoes.
- **The model's answer** (`ModelSalesOrderFill`, json_schema strict) gives,
  per row and column, a value and its source: a PO value at its anchor, a
  tool's result (``call`` and ``key``), a constant the skill names, or a
  computation from ADR 0013's closed set (a unit factor, a shift by whole
  calendar days, a rounding, a cut, a concat, a multiply) started from one of
  the first two.
- **The trace** (`trace`) redoes every cell: the anchor must be one of the
  row's own and hold the value; the call must be one made for the row and
  give the value again; the computation must give it again; the constant
  must be listed in the skill's ``## Constants`` section, between backticks
  (or be the fixed text the layout holds in that column).
  A price column (the layout's ``unit_price`` or ``amount``) takes only the
  PO's own price, as read or through a computation that reads it (dw_sales
  ADR 0008: never a price from the model). What it writes is code's value,
  never the model's text. A cell code cannot trace is not written: it is
  flagged for the PIC with the reason (`FlagReason`), and so is a column the
  layout fills that the answer left empty. PC's dates are left for the
  person, as in every upload file.

The model's text is never an id, a lookup key or a value written: an anchor
or a call it names is looked up among code's own, and a name code does not
hold is a flag. A PO's words are data in the prompt (contained by the
registry), so an instruction in a PO line can only make the model name a
source that does not trace.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.artifact_content import (
    CASE_ONLY_FIELDS,
    BravoUploadLayout,
    UploadColumn,
    UploadField,
    Value,
)
from dw_sales.application.model_calls import record_model_call
from dw_sales.application.order_artifacts import example_rows
from dw_sales.application.salesorder_rules import (
    STEPS_MAX,
    Concat,
    Cut,
    Letter,
    Lookups,
    Multiply,
    Round,
    ShiftDays,
    StepRefusedError,
    UnitFactor,
    apply_steps,
    canonical,
    column_letter,
    shown,
)
from dw_sales.domain.activity import ModelCall
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.domain.orders import PoDocument

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The prompt a PO is filled with. Its file is
# `configs/prompts/sales/salesorder_fill@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
SALESORDER_FILL: Final = PromptRef("sales.salesorder_fill", "1.0.0")
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 2500
# The rows one call fills: a row of the B41 layout is about fifteen cells,
# each about thirty tokens with its source, so five rows stay under the
# answer's room on the local model's route.
ROWS_PER_CALL: Final = 5
_OUTPUT_TOKENS: Final = 4000
# The longest PO the skill fills: longer, and the rules fill it (the
# fallback), or a person.
MAX_ROWS: Final = 200
# How long one shown value or one model value is.
_VALUE_MAX: Final = 200

# The fields of a row the PO tool shows, each at an anchor: the PO's own
# values as read, the file's own (its row number, the day the PO came in, the
# USD rate), the PRV code the row's item is (the customer's convert list's,
# as ticket 38's replay has it; on a case, the one Sales confirmed) and, on a
# case, DW1's suggested date. Not PC's dates: left for the person.
PO_FIELDS: Final[tuple[UploadField, ...]] = (
    "row_no",
    "customer_code",
    "po_no",
    "revision",
    "po_date",
    "received_date",
    "currency",
    "usd_rate",
    "line_no",
    "customer_item_code",
    "prv_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "amount",
    "requested_date",
    "suggested_delivery_date",
)
# A price, which only the PO gives (dw_sales ADR 0008).
PRICE_FIELDS: Final[frozenset[UploadField]] = frozenset({"unit_price", "amount"})

_ANCHOR: Final = re.compile(r"^R([1-9][0-9]{0,3})\.([a-z_]{1,32})$")
AnchorId = Annotated[str, Field(pattern=_ANCHOR.pattern)]
CallId = Annotated[str, Field(pattern=r"^c[1-9][0-9]{0,3}$")]
ResultKey = Annotated[str, Field(pattern=r"^[a-z_]{1,32}$")]
_Shown = Annotated[str, Field(max_length=_VALUE_MAX)]


# ------------------------------------------------------------- the tools --

ToolName = Literal["customer", "convert", "item"]
# What the customer tool answers: what every sales order of the customer
# carries (`artifact_content.CustomerAttribute`) and its code.
_CUSTOMER_KEYS: Final = (
    "code",
    "order_type",
    "delivery_term",
    "delivery_mode",
    "destination",
    "shipment_type",
)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


@dataclass(frozen=True, slots=True)
class SalesOrderTools:
    """The read-only tools of one fill, bound by code to one customer: its
    record, its own convert list (matched on the code as printed, as the
    catalogue matches a PO line), and the items that list reaches. Built by
    `bound` from the whole master data; what another customer holds is
    dropped there and never reached by any input."""

    customer: Customer
    convert_rows: Mapping[str, str]
    items: Mapping[str, Item]

    @classmethod
    def bound(
        cls, customer: Customer, entries: Sequence[ConvertEntry], items: Sequence[Item]
    ) -> SalesOrderTools:
        own = {
            e.customer_item_code: e.prv_code for e in entries if e.customer_code == customer.code
        }
        reached = set(own.values())
        return cls(
            customer=customer,
            convert_rows=own,
            items={item.prv_code: item for item in items if item.prv_code in reached},
        )

    def answer(self, tool: ToolName, key: str | None) -> dict[str, str | None] | None:
        """One call's result, None where the tool holds nothing for ``key``."""
        match tool:
            case "customer":
                return {name: _text(getattr(self.customer, name)) for name in _CUSTOMER_KEYS}
            case "convert":
                prv = self.convert_rows.get(key or "")
                return None if prv is None else {"prv_code": prv}
            case "item":
                item = self.items.get(key or "")
                if item is None:
                    return None
                return {
                    "name": item.name,
                    "specification": item.specification,
                    "standard_length": _text(item.pack_multiple),
                    "unit": item.unit,
                    "category": item.category,
                    "colour": item.attributes.colour,
                }


class ToolCall(BaseModel):
    """One call code made for the fill, as the turn is shown it."""

    model_config = _FROZEN

    call: CallId
    tool: ToolName
    input: str | None
    result: dict[str, str | None] | None


@dataclass(frozen=True, slots=True)
class PoRow:
    """One row of the upload file as the PO gives it: its number from 1 and
    its values by field (`PO_FIELDS`), each at the anchor ``R<row>.<field>``."""

    row: int
    values: Mapping[UploadField, Value]

    def anchors(self) -> dict[str, str | None]:
        return {f"R{self.row}.{name}": _shown(self.values.get(name)) for name in PO_FIELDS}


def _shown(value: Value) -> str | None:
    text = shown(value) if not isinstance(value, str) else value.strip()
    return None if not text else text[:_VALUE_MAX]


def po_rows(document: PoDocument, tools: SalesOrderTools, received_on: date) -> list[PoRow]:
    """The PO as read, a row per delivery as the upload file holds it: the
    rows ticket 38's replay composes (`example_rows`), with the PRV code the
    customer's own convert list gives where the item master holds it."""
    lookups = Lookups(convert=tools.convert_rows, items=tools.items)
    rows = example_rows(document, tools.customer.code, received_on, lookups)
    return [
        PoRow(number, {name: row.get(name) for name in PO_FIELDS})
        for number, row in enumerate(rows, start=1)
    ]


def prepared_calls(tools: SalesOrderTools, rows: Sequence[PoRow]) -> list[ToolCall]:
    """Every call the PO's rows lead to, made by code before the turn: the
    customer's record, the convert list for each code the PO prints, and the
    item each found code reaches."""
    calls = [
        ToolCall(call="c1", tool="customer", input=None, result=tools.answer("customer", None))
    ]
    codes = sorted({str(r.values["customer_item_code"]) for r in rows})
    for code in codes:
        found = tools.answer("convert", code)
        calls.append(ToolCall(call=f"c{len(calls) + 1}", tool="convert", input=code, result=found))
        prv = None if found is None else found["prv_code"]
        if prv is not None:
            calls.append(
                ToolCall(
                    call=f"c{len(calls) + 1}",
                    tool="item",
                    input=prv,
                    result=tools.answer("item", prv),
                )
            )
    return calls


def calls_for_row(calls: Sequence[ToolCall], row: PoRow) -> frozenset[str]:
    """The calls a cell of ``row`` may name: the customer's record, the
    convert list for the row's own code, and the item that code reaches."""
    code = str(row.values["customer_item_code"])
    allowed = {c.call for c in calls if c.tool == "customer"}
    for call in calls:
        if call.tool == "convert" and call.input == code:
            allowed.add(call.call)
            prv = None if call.result is None else call.result["prv_code"]
            allowed |= {c.call for c in calls if c.tool == "item" and c.input == prv}
    return frozenset(allowed)


# ---------------------------------------------------------- the answer --


class PoSource(BaseModel):
    """The PO's value at an anchor of the row."""

    model_config = _FROZEN
    kind: Literal["po"] = "po"
    anchor: AnchorId


class ToolSource(BaseModel):
    """A value of a call's result."""

    model_config = _FROZEN
    kind: Literal["tool"] = "tool"
    call: CallId
    key: ResultKey


class ConstantSource(BaseModel):
    """A constant the skill names."""

    model_config = _FROZEN
    kind: Literal["constant"] = "constant"


ComputeStep = Annotated[
    UnitFactor | ShiftDays | Round | Cut | Concat | Multiply, Field(discriminator="step")
]
Start = Annotated[PoSource | ToolSource, Field(discriminator="kind")]


class ComputedSource(BaseModel):
    """A PO value or a call's result, through ADR 0013's closed set."""

    model_config = _FROZEN
    kind: Literal["computation"] = "computation"
    start: Start
    steps: tuple[ComputeStep, ...] = Field(min_length=1, max_length=STEPS_MAX)


Source = Annotated[
    PoSource | ToolSource | ConstantSource | ComputedSource, Field(discriminator="kind")
]


class ModelCell(BaseModel):
    """One cell: its column, the value the model gives, where it came from."""

    model_config = _FROZEN

    column: Letter
    value: _Shown | None = None
    source: Source | None = None


class ModelRow(BaseModel):
    model_config = _FROZEN

    row: int = Field(ge=1, le=MAX_ROWS)
    cells: tuple[ModelCell, ...] = Field(default=(), max_length=120)


class ModelSalesOrderFill(BaseModel):
    """The model's answer for some rows of one PO."""

    model_config = _FROZEN

    rows: tuple[ModelRow, ...] = Field(default=(), max_length=ROWS_PER_CALL * 2)


# ----------------------------------------------------------- the trace --

# Why a cell was not written: each the PIC reads beside the cell.
FlagReason = Literal[
    # A column the layout fills that the answer left empty.
    "not_filled",
    # A value with no source.
    "source_missing",
    # The column named twice for one row: neither is written.
    "cell_repeated",
    # An anchor the PO as read does not hold, or another row's.
    "anchor_unknown",
    "anchor_other_row",
    # The value is not the PO's at the anchor.
    "value_not_at_anchor",
    # A call code did not make, or one made for another row.
    "call_unknown",
    "call_other_row",
    # The call, made again, does not give the value.
    "value_not_tool_result",
    # A step that cannot be applied, or a computation that does not give
    # the value when redone.
    "computation_refused",
    "value_not_computed",
    # A constant the skill does not name.
    "constant_not_in_skill",
    # A price that is not the PO's own (dw_sales ADR 0008).
    "price_not_from_po",
]
SourceKind = Literal["po", "tool", "constant", "computation", "blank"]
# Why a cell is left for the PIC, as the file's notes say it.
FLAG_WORDS: Final[Mapping[FlagReason, str]] = {
    "not_filled": "kỹ năng không điền ô này",
    "source_missing": "không nêu nguồn",
    "cell_repeated": "điền hai lần",
    "anchor_unknown": "nguồn không có trong PO",
    "anchor_other_row": "nguồn là dòng khác",
    "value_not_at_anchor": "giá trị khác giá trị PO",
    "call_unknown": "tra cứu không có",
    "call_other_row": "tra cứu của dòng khác",
    "value_not_tool_result": "giá trị khác kết quả tra cứu",
    "computation_refused": "phép tính không áp được",
    "value_not_computed": "phép tính không ra giá trị này",
    "constant_not_in_skill": "hằng số kỹ năng không nêu",
    "price_not_from_po": "giá không lấy từ PO",
}


@dataclass(frozen=True, slots=True)
class TracedCell:
    """One cell as code traced it: the value written (None where flagged or
    left blank), the kind of its source, and why it was flagged."""

    column: str
    value: Value
    source: SourceKind
    flag: FlagReason | None = None


@dataclass(frozen=True, slots=True)
class TracedRow:
    row: int
    cells: tuple[TracedCell, ...]

    def values(self) -> tuple[Value, ...]:
        return tuple(cell.value for cell in self.cells)


@dataclass(frozen=True, slots=True)
class CellFlag:
    """A cell not written, for the PIC: where and why."""

    row: int
    column: str
    reason: FlagReason


@dataclass(frozen=True, slots=True)
class TracedFill:
    """One PO filled with one skill version: every row of the file, every
    column traced, and the prompt and model it was filled with."""

    skill_ref: str
    prompt: str
    model_profile: str
    # The upload layout the rows were traced against: a file drawn in
    # another is not filled from them.
    layout_ref: str
    rows: tuple[TracedRow, ...]

    def notes(self, limit: int = 50) -> tuple[str, ...]:
        """The flagged cells, for the PIC, one line each: where and why."""
        found = self.flags
        lines = [f"{f.column}{f.row}: {FLAG_WORDS[f.reason]}" for f in found[:limit]]
        if len(found) > limit:
            lines.append(f"... và {len(found) - limit} ô khác")
        return tuple(lines)

    @property
    def flags(self) -> list[CellFlag]:
        return [
            CellFlag(row.row, cell.column, cell.flag)
            for row in self.rows
            for cell in row.cells
            if cell.flag is not None
        ]


_CONSTANTS_HEADING: Final = re.compile(r"^##\s+Constants\s*$", re.IGNORECASE | re.MULTILINE)
_NEXT_HEADING: Final = re.compile(r"^##\s", re.MULTILINE)
_BACKTICKED: Final = re.compile(r"`([^`\n]{1,200})`")


def skill_constants(instructions: str) -> frozenset[str]:
    """The constants a skill names: each text between backticks in its
    ``## Constants`` section. Nothing elsewhere in the skill counts, so a
    worked pair's values or a field's name are never a constant."""
    heading = _CONSTANTS_HEADING.search(instructions)
    if heading is None:
        return frozenset()
    rest = instructions[heading.end() :]
    end = _NEXT_HEADING.search(rest)
    section = rest if end is None else rest[: end.start()]
    return frozenset(match.strip() for match in _BACKTICKED.findall(section) if match.strip())


class _UntracedError(Exception):
    def __init__(self, reason: FlagReason) -> None:
        self.reason = reason


@dataclass(frozen=True)
class _Tracer:
    rows: Mapping[int, PoRow]
    calls: Mapping[str, ToolCall]
    tools: SalesOrderTools
    constants: frozenset[str]

    def start(self, source: PoSource | ToolSource, row: PoRow) -> tuple[Value, set[str]]:
        """The value a source gives for ``row``, and the PO fields it read."""
        if isinstance(source, PoSource):
            match = _ANCHOR.match(source.anchor)
            assert match is not None  # the schema's pattern
            number, name = int(match.group(1)), match.group(2)
            if number not in self.rows or name not in PO_FIELDS:
                raise _UntracedError("anchor_unknown")
            if number != row.row:
                raise _UntracedError("anchor_other_row")
            return row.values.get(name), {name}
        call = self.calls.get(source.call)
        if call is None:
            raise _UntracedError("call_unknown")
        if call.call not in calls_for_row(list(self.calls.values()), row):
            raise _UntracedError("call_other_row")
        # Made again, by code, with code's own input: never the model's.
        result = self.tools.answer(call.tool, call.input)
        if result is None or result.get(source.key) is None:
            raise _UntracedError("value_not_tool_result")
        return result[source.key], set()

    def cell(
        self, column: UploadColumn, letter: str, answer: ModelCell, row: PoRow
    ) -> tuple[Value, SourceKind]:
        source = answer.source
        if source is None:
            raise _UntracedError("source_missing")
        if column.field in PRICE_FIELDS and not isinstance(source, PoSource | ComputedSource):
            raise _UntracedError("price_not_from_po")
        if isinstance(source, ConstantSource):
            # The skill's constants, and the fixed text the layout itself
            # holds in this column (approved with the layout).
            named = (*self.constants, *(() if column.constant is None else (column.constant,)))
            held = {canonical(c): c for c in named}
            fixed = held.get(canonical(answer.value))
            if fixed is None:
                raise _UntracedError("constant_not_in_skill")
            return fixed, "constant"
        if isinstance(source, PoSource | ToolSource):
            value, read = self.start(source, row)
            self._price(column, read)
            if canonical(value) != canonical(answer.value):
                raise _UntracedError(
                    "value_not_at_anchor"
                    if isinstance(source, PoSource)
                    else "value_not_tool_result"
                )
            return value, "po" if isinstance(source, PoSource) else "tool"
        value, read = self.start(source.start, row)
        read |= {
            name
            for step in source.steps
            for name in (
                step.sources
                if isinstance(step, Concat)
                else (step.source,)
                if isinstance(step, Multiply)
                else ()
            )
        }
        self._price(column, read)
        try:
            value = apply_steps(letter, value, source.steps, row.values, Lookups())
        except StepRefusedError:
            raise _UntracedError("computation_refused") from None
        if canonical(value) != canonical(answer.value):
            raise _UntracedError("value_not_computed")
        return value, "computation"

    @staticmethod
    def _price(column: UploadColumn, read: set[str]) -> None:
        if column.field in PRICE_FIELDS and not read & PRICE_FIELDS:
            raise _UntracedError("price_not_from_po")


def trace(
    layout: BravoUploadLayout,
    rows: Sequence[PoRow],
    calls: Sequence[ToolCall],
    tools: SalesOrderTools,
    instructions: str,
    answers: Sequence[ModelRow],
) -> tuple[TracedRow, ...]:
    """Every cell of every row of the PO, traced (module docstring). A row
    the answers do not hold is a row of empty cells, each flagged where the
    layout fills its column; an answer for a row the PO does not have, or a
    column the layout does not have, is never written."""
    tracer = _Tracer(
        {r.row: r for r in rows},
        {c.call: c for c in calls},
        tools,
        skill_constants(instructions),
    )
    by_row: dict[int, ModelRow] = {}
    for answer in answers:
        by_row.setdefault(answer.row, answer)
    traced = []
    for row in rows:
        named: dict[str, list[ModelCell]] = {}
        for answer_cell in by_row[row.row].cells if row.row in by_row else ():
            named.setdefault(answer_cell.column, []).append(answer_cell)
        cells = []
        for index, column in enumerate(layout.columns):
            letter = column_letter(index)
            cells.append(_traced_cell(tracer, column, letter, named.get(letter, []), row))
        traced.append(TracedRow(row.row, tuple(cells)))
    return tuple(traced)


def _traced_cell(
    tracer: _Tracer, column: UploadColumn, letter: str, answers: list[ModelCell], row: PoRow
) -> TracedCell:
    if column.field in CASE_ONLY_FIELDS:
        # PC's dates: a case's, left for the person as in every upload file.
        return TracedCell(letter, None, "blank")
    given = [a for a in answers if a.value is not None and a.value.strip()]
    if len(given) > 1:
        return TracedCell(letter, None, "blank", "cell_repeated")
    if not given:
        return TracedCell(letter, None, "blank", None if column.blank else "not_filled")
    try:
        value, kind = tracer.cell(column, letter, given[0], row)
    except _UntracedError as untraced:
        return TracedCell(letter, None, "blank", untraced.reason)
    return TracedCell(letter, value, kind)


# ------------------------------------------------------------- the turn --


def fill_inputs(
    layout: BravoUploadLayout,
    rows: Sequence[PoRow],
    calls: Sequence[ToolCall],
    instructions: str,
) -> dict[str, str]:
    """What one call is shown, as code-built JSON beside the skill's words:
    the layout's columns (letter, header, what the layout reads; PC's dates
    left out), the rows' values at their anchors, and the calls."""
    columns = [
        {
            "column": column_letter(i),
            "header": c.header,
            "layout": (
                f"field {c.field}"
                if c.field is not None
                else f"customer {c.customer}"
                if c.customer is not None
                else "fixed"
                if c.constant is not None
                else "blank"
            ),
            **({"price": True} if c.field in PRICE_FIELDS else {}),
        }
        for i, c in enumerate(layout.columns)
        if c.field not in CASE_ONLY_FIELDS
    ]
    return {
        "skill": instructions,
        "columns": json.dumps(columns, ensure_ascii=False),
        "po_rows": json.dumps(
            [{"row": r.row, "values": r.anchors()} for r in rows], ensure_ascii=False
        ),
        "calls": json.dumps([c.model_dump(mode="json") for c in calls], ensure_ascii=False),
    }


@dataclass(frozen=True, slots=True)
class FillSkill:
    """The skill a fill reads with: its words and the version it stamps."""

    ref: str
    instructions: str


@dataclass(frozen=True)
class SalesOrderFiller:
    """Fills one PO's SalesOrder with a skill and its tools, and traces it.

    Raises `ModelUnavailableError` where there is no usable answer, a PO too
    long for the skill, or one whose shown inputs do not fit the route: the
    caller falls back to the customer's learned rules (ADR 0013), or a
    person. A budget or quota refusal propagates as itself."""

    model: InterpretationPort

    async def fill(
        self,
        *,
        layout: BravoUploadLayout,
        rows: Sequence[PoRow],
        tools: SalesOrderTools,
        skill: FillSkill,
        run: RunContext,
    ) -> TracedFill:
        if not rows or len(rows) > MAX_ROWS:
            raise ModelUnavailableError("the PO is empty or longer than the skill fills")
        calls = prepared_calls(tools, rows)
        answers: list[ModelRow] = []
        for first in range(0, len(rows), ROWS_PER_CALL):
            chunk = rows[first : first + ROWS_PER_CALL]
            inputs = fill_inputs(layout, chunk, calls, skill.instructions)
            if estimated_tokens("".join(inputs.values())) > (
                self.model.max_input_tokens - PROMPT_TOKENS
            ):
                raise ModelUnavailableError("the PO's rows do not fit the route")
            answers += await self._call(inputs, run)
        return TracedFill(
            skill_ref=skill.ref,
            prompt=str(SALESORDER_FILL),
            model_profile=self.model.model_profile,
            layout_ref=layout.ref,
            rows=trace(layout, rows, calls, tools, skill.instructions, answers),
        )

    async def _call(self, inputs: Mapping[str, str], run: RunContext) -> list[ModelRow]:
        started = time.perf_counter()
        answered = False
        try:
            answer = await self.model.interpret(
                SALESORDER_FILL,
                inputs,
                ModelSalesOrderFill,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
            answered = True
        finally:
            record_model_call(
                ModelCall(
                    prompt=str(SALESORDER_FILL),
                    model_profile=self.model.model_profile,
                    model=None,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    answered=answered,
                )
            )
        return list(answer.rows)


# --------------------------------------------------------- the comparison --


@dataclass(frozen=True, slots=True)
class PairCheck:
    """A fill compared with the file the PIC made from the same PO: the
    cells compared, those that differ (a flagged cell is one), and whether
    the rows' count is the file's."""

    rows_expected: int
    rows_got: int
    cells_compared: int
    differing: tuple[str, ...] = field(default=())

    @property
    def reproduced(self) -> bool:
        return self.rows_expected == self.rows_got > 0 and not self.differing


def check_against(
    layout: BravoUploadLayout,
    fill: TracedFill,
    expected: Sequence[Mapping[str, str]],
) -> PairCheck:
    """``fill`` against the PIC's file (rows of cells by letter), compared
    as ticket 38's replay compares (`salesorder_learning.canonical`): every
    column the layout fills, and every column the fill wrote; a column both
    leave blank is the person's, not compared. A flagged cell differs."""
    differing: list[str] = []
    compared = 0
    for traced, cells in zip(fill.rows, expected, strict=False):
        for index, (column, cell) in enumerate(zip(layout.columns, traced.cells, strict=True)):
            letter = column_letter(index)
            if column.field in CASE_ONLY_FIELDS:
                continue
            if column.blank and cell.value is None and cell.flag is None:
                continue
            compared += 1
            if cell.flag is not None or canonical(cell.value) != canonical(cells.get(letter)):
                differing.append(f"{letter}{traced.row}")
    return PairCheck(
        rows_expected=len(expected),
        rows_got=len(fill.rows),
        cells_compared=compared,
        differing=tuple(differing[:200]),
    )


__all__ = [
    "PO_FIELDS",
    "PRICE_FIELDS",
    "ROWS_PER_CALL",
    "SALESORDER_FILL",
    "CellFlag",
    "FillSkill",
    "FlagReason",
    "ModelCell",
    "ModelRow",
    "ModelSalesOrderFill",
    "PairCheck",
    "PoRow",
    "SalesOrderFiller",
    "SalesOrderTools",
    "ToolCall",
    "TracedCell",
    "TracedFill",
    "TracedRow",
    "check_against",
    "po_rows",
    "prepared_calls",
    "skill_constants",
    "trace",
]
