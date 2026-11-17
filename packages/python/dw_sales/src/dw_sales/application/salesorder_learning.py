"""A customer's SalesOrder rules learned from one worked example and proven
by replaying them on it (dw_sales ADR 0013, ticket 38).

On the customer's screen a person uploads a pair: the customer's original PO
and the SalesOrder file the PIC made from it, with the day the PO came in.
Nothing here writes a rule version until the replay matched and a person
sends it for approval:

- **queued**: uploaded by a holder of `sales.rules.propose` who reads prices
  (`SalesOrderExamples.request`, 202); the bytes are kept until read, and one
  outbox event, `sales.salesorder_example.requested`, asks the worker. **The
  API reads no customer file** (ticket 25). A request also drops the
  workspace's examples older than `KEPT_FOR` that were never sent.
- The worker (`SalesOrderLearning.learn`) scans both files, reads the PO the
  normal way (`CustomerPoReading`, the customer's approved layout) and the
  PIC's file in the reader sandbox, and checks the PIC's file is the
  tenant's upload layout (`header_differs` otherwise). It replays the layout
  alone first: where that already reproduces the file, nothing is asked.
  Otherwise the model (prompt `salesorder_rules_proposal`, versioned) is
  shown the layout's columns, the columns that differ and a few rows of each
  side, and answers per column a source and steps from the closed set
  (`salesorder_rules`). Code then **verifies** it (`verify`): every column is
  the layout's; a `constant` is a column's only step, the value every row of
  the PIC's file holds there, and no value of the PO's own (the model never
  copies a PO's values into a rule). And code **replays** it (`replay`): the
  rules applied to the PO through the same row the file builder composes
  (`salesorder_rules.filled_row`, `order_artifacts.checked_row`), compared
  with the PIC's file cell by cell: numbers by value, dates by day, text
  NFKC (the reader's own form) and trimmed. Each difference names the cell,
  what was expected, what came out and the rule (or the layout) responsible.
  A column neither the layout nor the rules fill is left for the person, as
  in the file a case draws (B41: the PC's dates, the PIC's own code): it is
  asked of the model with the differing ones, and what stays unfilled is
  listed with how many rows the PIC filled, for the head to see, not
  compared.
- **replayed** (the rules and their replay), **refused** (code refused the
  model's answer, or the PIC's file is not the tenant's layout; the replay of
  the layout alone is kept to show what differs), **unavailable** (no
  usable answer: no model on this host, down, or the plan's day spent; the
  same replay kept) or **failed** (no learning at all: a file infected or
  unreadable, the asker no longer permitted).
- **submitted** ("Gửi duyệt", `submit`): only an example whose replay
  matched, against the layout still in force. The version is the tenant's
  version in force with this customer's rules replaced, proposed through
  `LearnedProposalPort` (never applied directly, the head's included: the
  head approves, never the proposer). A replay that differs is refused here
  (409, `replay_differs`), and the general rules door refuses the key
  (`rules.LEARNED_ONLY`), so no other route reaches the approval. The
  approval shows the replay (`for_version`).

From then on code applies the approved rules to every PO of the customer
(`order_artifacts.bravo_upload`), with no model.

**A worked pair** (ticket 41): every example whose PO the normal reading
read and whose PIC's file is the tenant's layout is also kept as one of the
customer's worked pairs (`WorkedPair`), the PO as read and the PIC's rows,
written in the transaction that settles the example. A change to the
customer's SalesOrder skill is replayed on all of them
(`salesorder_pairs.SalesOrderSkillReplayer`).

Every step is audited; the worker's as itself (`lane_audit_event`,
`system:sales_salesorder_examples`): ids, the customer, the status, the
files' hashes, counts and problem codes, never a cell's value.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import TracebackType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import (
    ConflictError,
    DomainError,
    InfrastructureError,
    NotFoundError,
    QuotaExceededError,
)
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import context_from
from dw_platform.application.malware import MalwareScanPort
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import (
    CASE_ONLY_FIELDS,
    BravoUploadLayout,
    UploadField,
    Value,
)
from dw_sales.application.catalog_imports import OutboxPort
from dw_sales.application.order_artifacts import checked_row, example_rows
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.application.processing import RequesterAccessPort
from dw_sales.application.rules import Resolved, RuleKey, RuleVersionView
from dw_sales.application.salesorder_rules import (
    ColumnRule,
    Constant,
    CustomerSalesOrderRules,
    Letter,
    Lookups,
    SalesOrderRules,
    StepProblem,
    StepRefusedError,
    apply_rule,
    canonical,
    column_letter,
    layout_cell,
    shown,
)
from dw_sales.application.source import SheetGrid
from dw_sales.application.template_reading import (
    MAX_SHEETS,
    header_row,
    plain,
    visible,
)
from dw_sales.domain.catalog import ConvertEntry, Customer, CustomerCode, Item
from dw_sales.domain.order_checks import IntakeCaps, OrderRules
from dw_sales.domain.orders import PoDocument, Unreadable

logger = logging.getLogger("dw_sales.salesorder_learning")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_salesorder_example"

EXAMPLE_REQUESTED: Final = "sales.salesorder_example.requested"
EXAMPLE_EVENT_SCHEMA: Final = "1.0.0"
# The worker's lane name for its audit rows (ADR 0011-a-background-lane-audits-as-itself).
EXAMPLE_LANE: Final = "sales_salesorder_examples"
# What learning needs, and so all a context it builds carries: the files
# carry prices, as the key does (`rules.PRICE_BEARING`).
LEARNING_CEILING: Final = frozenset({SalesScopes.RULES_PROPOSE.value, SalesScopes.PRICE_READ.value})
# The prompt a pair is proposed from. Its file is
# `configs/prompts/sales/salesorder_rules_proposal@1.0.0.yaml`; a test holds
# the two together, and a new wording is a new version here and a new file
# there.
SALESORDER_RULES_PROPOSAL: Final = PromptRef("sales.salesorder_rules_proposal", "1.0.0")
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 3000
# Twenty columns of a rule each: about 1,500 tokens.
_OUTPUT_TOKENS: Final = 3000
# How many rows of each side the model is shown.
SAMPLE_ROWS: Final = 5
# How much of one value the model is shown at most.
SHOWN_LIMIT: Final = 64

MAX_EXAMPLE_BYTES: Final = 5 * 1024 * 1024
PO_EXTENSIONS: Final = (".xlsx", ".xls", ".pdf")
SALESORDER_EXTENSIONS: Final = (".xlsx",)
_FILE_NAME: Final = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")
# How long an example that was never sent is kept: a new request drops it.
KEPT_FOR: Final = timedelta(days=30)
# The most rows of the PIC's file compared, and differences listed.
MAX_ROWS: Final = 2000
MAX_DIFFERENCES: Final = 200

ExampleStatus = Literal["queued", "replayed", "refused", "unavailable", "failed", "submitted"]
FileKind = Literal["po", "salesorder"]

ProblemCode = Literal[
    # The PIC's file is not the tenant's upload layout at this column.
    "header_differs",
    # A rule names a column the layout does not have.
    "column_outside_layout",
    # A rule the closed set does not hold (`where`: the path that failed).
    "rule_invalid",
    # A constant that is not a column's only step.
    "constant_not_alone",
    # A constant that is not what every row of the PIC's file holds there.
    "constant_not_in_file",
    # A constant that is a value of the PO itself: never kept in a rule.
    "constant_from_po",
    # No usable answer.
    "model_unavailable",
    "model_not_configured",
    "model_quota",
]


class LearnProblem(BaseModel):
    """Why a proposal was refused: a code, the column, a path. Never a word
    of the model's, never a cell's value."""

    model_config = _FROZEN

    code: ProblemCode
    column: Letter | None = None
    where: str | None = Field(default=None, max_length=200)


DifferenceProblem = Literal[
    # The cell came out other than the PIC's file holds.
    "value_differs",
    # The PIC's file has a row the replay does not, or the other way round.
    "row_missing",
    "row_extra",
    # The file builder refused the row (an amount, a hidden decimal).
    "row_refused",
]


class CellDifference(BaseModel):
    """One cell the replay did not reproduce: where (the PIC's file's cell),
    what was expected and what came out, and what produced it (the
    customer's rule for the column, its step that could not apply, or the
    layout). Carries the cells' values: price-bearing, as the key is."""

    model_config = _FROZEN

    cell: str = Field(max_length=16)
    column: Letter | None = None
    header: str | None = Field(default=None, max_length=200)
    expected: str | None = Field(default=None, max_length=200)
    got: str | None = Field(default=None, max_length=200)
    source: Literal["layout", "rule", "row"]
    problem: DifferenceProblem | StepProblem
    step: int | None = Field(default=None, ge=1)


class LeftBlank(BaseModel):
    """A column neither the layout nor the rules fill: left for the person
    who pastes, as in the file a case draws. Not compared; how many rows of
    the PIC's file fill it is shown."""

    model_config = _FROZEN

    column: Letter
    header: str = Field(max_length=200)
    filled_rows: int = Field(ge=0)


class Replay(BaseModel):
    """The rules applied to the example's PO and compared with the PIC's file."""

    model_config = _FROZEN

    layout_ref: str
    rows_expected: int = Field(ge=0)
    rows_got: int = Field(ge=0)
    cells_compared: int = Field(ge=0)
    differences_total: int = Field(ge=0)
    # The first `MAX_DIFFERENCES`, row by row.
    differences: tuple[CellDifference, ...] = Field(default=(), max_length=MAX_DIFFERENCES)
    left_blank: tuple[LeftBlank, ...] = ()

    @property
    def matches(self) -> bool:
        return self.differences_total == 0 and self.rows_expected == self.rows_got > 0

    @property
    def unexplained(self) -> list[str]:
        """The columns the PIC filled that nothing fills here: what is left to
        learn, and, once learned as far as it goes, left for the person."""
        return [blank.column for blank in self.left_blank if blank.filled_rows]


class SalesOrderExample(BaseModel):
    """One worked example and what became of it (module docstring)."""

    model_config = _FROZEN

    example_id: uuid.UUID
    customer_code: CustomerCode
    status: ExampleStatus
    requested_by: uuid.UUID
    requested_at: AwareDatetime
    received_on: date
    po_file_name: str = Field(max_length=200)
    po_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    po_size: int = Field(ge=1, le=MAX_EXAMPLE_BYTES)
    salesorder_file_name: str = Field(max_length=200)
    salesorder_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    salesorder_size: int = Field(ge=1, le=MAX_EXAMPLE_BYTES)
    rules: CustomerSalesOrderRules | None = None
    replay: Replay | None = None
    problems: tuple[LearnProblem, ...] = Field(default=(), max_length=60)
    error: str | None = Field(default=None, max_length=500)
    prompt_ref: str | None = None
    model_profile: str | None = None
    # The rule version it was sent for approval as.
    version_id: uuid.UUID | None = None


class WorkedPair(BaseModel):
    """A PO and the SalesOrder file the PIC made from it, kept for the
    customer (ticket 41): the PO as the normal reading read it, the day it
    came in, and the PIC's rows, each its visible cells' text by column
    letter. Price-bearing, as the files are. A skill change is replayed on
    every pair of its customer (`salesorder_pairs`)."""

    model_config = _FROZEN

    pair_id: uuid.UUID
    # The example it was read from; None once that example was dropped.
    example_id: uuid.UUID | None
    customer_code: CustomerCode
    received_on: date
    layout_ref: str = Field(max_length=200)
    document: PoDocument
    expected: tuple[dict[Letter, str], ...] = Field(min_length=1, max_length=MAX_ROWS)
    added_by: uuid.UUID
    added_at: AwareDatetime


class SalesOrderExampleView(BaseModel):
    """An example as the customer's screen and the approval read it."""

    model_config = ConfigDict(frozen=True)

    example_id: uuid.UUID
    customer_code: str
    status: ExampleStatus
    requested_by: uuid.UUID
    requested_at: datetime
    received_on: date
    po_file_name: str
    salesorder_file_name: str
    rules: CustomerSalesOrderRules | None
    replay: Replay | None
    # Whether "Gửi duyệt" is open: replayed, matched, nothing sent yet.
    submittable: bool
    problems: list[LearnProblem]
    error: str | None
    prompt_ref: str | None
    model_profile: str | None
    version_id: uuid.UUID | None


def example_view(example: SalesOrderExample) -> SalesOrderExampleView:
    return SalesOrderExampleView(
        example_id=example.example_id,
        customer_code=example.customer_code,
        status=example.status,
        requested_by=example.requested_by,
        requested_at=example.requested_at,
        received_on=example.received_on,
        po_file_name=example.po_file_name,
        salesorder_file_name=example.salesorder_file_name,
        rules=example.rules,
        replay=example.replay,
        submittable=_submittable(example),
        problems=list(example.problems),
        error=example.error,
        prompt_ref=example.prompt_ref,
        model_profile=example.model_profile,
        version_id=example.version_id,
    )


def _submittable(example: SalesOrderExample) -> bool:
    return (
        example.status == "replayed"
        and example.rules is not None
        and example.replay is not None
        and example.replay.matches
    )


# ------------------------------------------------------- reading the pair --


@dataclass(frozen=True, slots=True)
class PicRow:
    """One data row of the PIC's file: its row number, and its visible
    cells' text by column (0 is A)."""

    row: int
    cells: Mapping[int, str]


@dataclass(frozen=True, slots=True)
class PicFile:
    """The PIC's SalesOrder file: its sheet, its header row, its rows."""

    sheet: str
    header_row: int
    headers: Mapping[int, str]
    rows: tuple[PicRow, ...]


def pic_file(grid: SheetGrid, layout: BravoUploadLayout) -> PicFile | list[LearnProblem]:
    """The PIC's file read against the tenant's layout: its header row (the
    first with four visible headers, as a template's) must print the
    layout's headers column by column; anything else is `header_differs`."""
    row = header_row(grid)
    if row is None:
        return [LearnProblem(code="header_differs")]
    headers = {h.column - 1: plain(h.text) for h in row.headers}
    width = max(len(layout.columns), max(headers, default=-1) + 1)
    problems = [
        LearnProblem(code="header_differs", column=column_letter(index))
        for index in range(width)
        if headers.get(index, "")
        != (plain(layout.columns[index].header) if index < len(layout.columns) else "")
    ]
    if problems:
        return problems
    found: dict[int, dict[int, str]] = {}
    for cell in grid.cells:
        if cell.row > row.row and visible(cell) and cell.text.strip():
            found.setdefault(cell.row, {})[cell.column - 1] = cell.text
    rows = tuple(PicRow(number, found[number]) for number in sorted(found)[:MAX_ROWS])
    return PicFile(row.sheet, row.row, headers, rows)


def _filled(layout: BravoUploadLayout, rules: CustomerSalesOrderRules | None) -> set[int]:
    named = set(rules.by_index()) if rules is not None else set()
    return {
        i
        for i, column in enumerate(layout.columns)
        # A column reading what only a case holds (PC's dates) is left for
        # the person, as a blank one is: the worked example has none.
        if not column.blank and column.field not in CASE_ONLY_FIELDS
    } | named


def replay(
    layout: BravoUploadLayout,
    rules: CustomerSalesOrderRules | None,
    values_rows: Sequence[Mapping[UploadField, Value]],
    customer: Customer,
    lookups: Lookups,
    pic: PicFile,
) -> Replay:
    """``rules`` applied to the example's rows and compared with the PIC's
    file, row by row and cell by cell (module docstring)."""
    named = rules.by_index() if rules is not None else {}
    compared = sorted(_filled(layout, rules))
    differences: list[CellDifference] = []
    cells = 0
    for position, values in enumerate(values_rows):
        if position >= len(pic.rows):
            differences.append(
                CellDifference(cell=f"#{position + 1}", source="row", problem="row_extra")
            )
            continue
        expected = pic.rows[position]
        got: list[Value] = []
        refused: dict[int, StepRefusedError] = {}
        for index, column in enumerate(layout.columns):
            if index in named:
                try:
                    got.append(apply_rule(named[index], values, customer, lookups))
                except StepRefusedError as error:
                    refused[index] = error
                    got.append(None)
            else:
                got.append(layout_cell(column, values, customer))
        if not refused:
            try:
                checked_row(layout, values, tuple(got))
            except ConflictError as builder:
                differences.append(
                    CellDifference(
                        cell=f"#{expected.row}",
                        header=str(builder.details.get("column") or "")[:200] or None,
                        source="row",
                        problem="row_refused",
                    )
                )
        for index in compared:
            cells += 1
            want, have = expected.cells.get(index), got[index]
            if index not in refused and canonical(want) == canonical(have):
                continue
            letter = column_letter(index)
            step = refused.get(index)
            differences.append(
                CellDifference(
                    cell=f"{letter}{expected.row}",
                    column=letter,
                    header=layout.columns[index].header[:200],
                    expected=shown(want),
                    got=shown(have),
                    source="rule" if index in named else "layout",
                    problem=step.problem if step is not None else "value_differs",
                    step=step.step if step is not None else None,
                )
            )
    for missing in pic.rows[len(values_rows) :]:
        differences.append(
            CellDifference(cell=f"#{missing.row}", source="row", problem="row_missing")
        )
    blank = [i for i in range(len(layout.columns)) if i not in set(compared)]
    return Replay(
        layout_ref=layout.ref,
        rows_expected=len(pic.rows),
        rows_got=len(values_rows),
        cells_compared=cells,
        differences_total=len(differences),
        differences=tuple(differences[:MAX_DIFFERENCES]),
        left_blank=tuple(
            LeftBlank(
                column=column_letter(i),
                header=layout.columns[i].header[:200],
                filled_rows=sum(1 for row in pic.rows if row.cells.get(i, "").strip()),
            )
            for i in blank
        ),
    )


# --------------------------------------------------------------- the model --


class ModelSalesOrderRules(BaseModel):
    """The model's answer: per column it explains, by letter, a source and
    the steps from the closed set (`salesorder_rules.ColumnRule`)."""

    model_config = _FROZEN

    columns: tuple[ColumnRule, ...] = Field(default=(), max_length=120)


def _layout_source(layout: BravoUploadLayout, index: int) -> str:
    column = layout.columns[index]
    if column.field is not None:
        return f"field {column.field}"
    if column.customer is not None:
        return f"customer {column.customer}"
    return "fixed" if column.constant is not None else "blank"


def _cut(text: str | None, width: int) -> str:
    return "" if text is None else text[:width]


def proposal_inputs(
    layout: BravoUploadLayout,
    values_rows: Sequence[Mapping[UploadField, Value]],
    pic: PicFile,
    baseline: Replay,
    room: int,
) -> dict[str, str]:
    """What the model is shown, as code-built JSON: the layout's columns with
    their own source, the columns the layout alone does not reproduce, and
    the first `SAMPLE_ROWS` rows of each side (the PO's values by field, the
    PIC's cells of those columns by letter), each text cut to fit ``room``
    tokens (at most `SHOWN_LIMIT` characters)."""
    differing = sorted(
        {d.column for d in baseline.differences if d.column is not None}
        | set(baseline.unexplained),
        key=lambda letter: (len(letter), letter),
    )
    indexes = [i for i in range(len(layout.columns)) if column_letter(i) in differing]
    width = SHOWN_LIMIT
    while True:
        inputs = {
            "columns": json.dumps(
                [
                    {
                        "column": column_letter(i),
                        "header": plain(c.header)[:width],
                        "layout": _layout_source(layout, i),
                    }
                    for i, c in enumerate(layout.columns)
                ],
                ensure_ascii=False,
            ),
            "differing": json.dumps(differing),
            "po_rows": json.dumps(
                [
                    {name: _cut(shown(value), width) for name, value in row.items()}
                    for row in values_rows[:SAMPLE_ROWS]
                ],
                ensure_ascii=False,
            ),
            "file_rows": json.dumps(
                [
                    {column_letter(i): _cut(row.cells.get(i), width) for i in indexes}
                    for row in pic.rows[:SAMPLE_ROWS]
                ],
                ensure_ascii=False,
            ),
        }
        if estimated_tokens("".join(inputs.values())) <= room or width <= 16:
            return inputs
        width //= 2


# What a constant may not be: a value that belongs to one PO, not to every PO
# of the customer.
_PO_OWN: Final[tuple[UploadField, ...]] = (
    "po_no",
    "po_date",
    "line_no",
    "customer_item_code",
    "description",
    "quantity",
    "unit_price",
    "amount",
    "requested_date",
)


def verify(
    answer: ModelSalesOrderRules,
    layout: BravoUploadLayout,
    values_rows: Sequence[Mapping[UploadField, Value]],
    pic: PicFile,
) -> CustomerSalesOrderRules | list[LearnProblem] | None:
    """The model's answer as rules code accepts, None for an answer naming no
    column, or what is wrong with it (module docstring)."""
    problems: list[LearnProblem] = []
    po_values = {canonical(row.get(name)) for row in values_rows for name in _PO_OWN} - {None}
    for rule in answer.columns:
        if rule.index >= len(layout.columns):
            problems.append(LearnProblem(code="column_outside_layout", column=rule.column))
            continue
        constants = [step for step in rule.steps if isinstance(step, Constant)]
        if not constants:
            continue
        if len(rule.steps) > 1:
            problems.append(LearnProblem(code="constant_not_alone", column=rule.column))
            continue
        fixed = canonical(constants[0].value)
        held = [canonical(row.cells.get(rule.index)) for row in pic.rows]
        if not held or any(value != fixed for value in held):
            problems.append(LearnProblem(code="constant_not_in_file", column=rule.column))
        elif fixed in po_values:
            problems.append(LearnProblem(code="constant_from_po", column=rule.column))
    if problems:
        return problems
    if not answer.columns:
        return None
    try:
        return CustomerSalesOrderRules(columns=answer.columns)
    except ValidationError as invalid:
        return [
            LearnProblem(code="rule_invalid", where=".".join(str(p) for p in e["loc"])[:200])
            for e in invalid.errors()[:20]
        ]


# ------------------------------------------------------------------ ports --


class ExampleStorePort(Protocol):
    """The workspace's examples inside a unit of work (RLS-bound)."""

    async def add(self, example: SalesOrderExample, po: bytes, salesorder: bytes) -> None: ...

    async def get(self, example_id: uuid.UUID) -> SalesOrderExample | None: ...

    async def files(self, example_id: uuid.UUID) -> tuple[bytes, bytes] | None:
        """The PO's bytes and the PIC's file's, until read; None once read."""
        ...

    async def settle(self, example: SalesOrderExample) -> bool:
        """Writes ``example``'s outcome where the row is still queued, and
        drops its files: False, and nothing written, otherwise."""
        ...

    async def submit(self, example_id: uuid.UUID, version_id: uuid.UUID) -> bool:
        """Marks a replayed example sent as ``version_id``: False, and nothing
        written, where it is not replayed any more."""
        ...

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[SalesOrderExample]:
        """The customer's examples, newest first."""
        ...

    async def for_version(self, version_id: uuid.UUID) -> SalesOrderExample | None: ...

    async def prune(self, before: datetime) -> int:
        """Drops the examples requested before ``before`` that were never sent,
        with their files."""
        ...


class WorkedPairStorePort(Protocol):
    """The workspace's worked pairs inside a unit of work (RLS-bound)."""

    async def add(self, pair: WorkedPair) -> None: ...

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[WorkedPair]:
        """The customer's pairs, newest first."""
        ...

    async def withdraw(self, pair_id: uuid.UUID) -> WorkedPair | None:
        """Drops the pair (ticket 41's leftovers): the pair it was, or None
        where the scope holds no such pair."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the pairs added before ``before``; how many."""
        ...


class ExampleUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def examples(self) -> ExampleStorePort: ...

    @property
    def pairs(self) -> WorkedPairStorePort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    @property
    def outbox(self) -> OutboxPort: ...

    async def commit(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class ExampleUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> ExampleUnitOfWork: ...


class LearningCatalogPort(Protocol):
    """The master data learning reads: the customer, its convert list and
    the item master (`SalesCatalogPort`'s own methods)."""

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]: ...

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]: ...

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]: ...


class LearningRulesPort(Protocol):
    """The tenant's rule in force for a key (`TenantRuleBook.current`)."""

    async def current(self, scope: SalesScope, key: RuleKey) -> Resolved: ...


class PoReadingPort(Protocol):
    """The normal reading of a customer's PO (`order_intake.CustomerPoReading`)."""

    async def read(
        self, scope: SalesScope, content: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable: ...


class SalesOrderSheetsPort(Protocol):
    """A workbook's sheets, opened in the reader sandbox (`TemplateSheetsPort`)."""

    def kind(self, data: bytes) -> Literal["pdf", "xlsx"] | None: ...

    async def sheet_names(self, data: bytes) -> list[str]: ...

    async def sheet_grid(self, data: bytes, sheet: str) -> SheetGrid | None: ...


class LearnedProposalPort(Protocol):
    """Proposes a version of the customers' SalesOrder rules that a replay
    proved, never applied directly (`SalesRulesService.propose_learned`)."""

    async def propose_learned(
        self, context: AccessContext, document: Mapping[str, Any]
    ) -> RuleVersionView: ...


# ---------------------------------------------------------------- service --


def _details(example: SalesOrderExample) -> dict[str, object]:
    replayed = example.replay
    return {
        "customer_code": example.customer_code,
        "status": example.status,
        "po_sha256": example.po_sha256,
        "salesorder_sha256": example.salesorder_sha256,
        "problems": sorted({p.code for p in example.problems}),
        **(
            {}
            if replayed is None
            else {
                "cells_compared": replayed.cells_compared,
                "differences": replayed.differences_total,
            }
        ),
    }


def _named(file_name: str, extensions: tuple[str, ...], data: bytes, which: str) -> str:
    name = file_name.strip()
    if not _FILE_NAME.match(name):
        raise DomainError("tên tệp không hợp lệ", details={"rule": "file_name", "file": which})
    if not name.casefold().endswith(extensions):
        raise DomainError(
            f"tệp {which} phải là {' hoặc '.join(extensions)}",
            details={"rule": "file_type", "file": which},
        )
    if not data:
        raise DomainError("tệp rỗng", details={"rule": "file_empty", "file": which})
    if len(data) > MAX_EXAMPLE_BYTES:
        raise DomainError(
            f"tệp lớn hơn {MAX_EXAMPLE_BYTES // (1024 * 1024)} MB",
            details={"rule": "file_size", "file": which},
        )
    return name


@dataclass(frozen=True)
class SalesOrderExamples:
    """The customer's screen's side: upload a pair, read it, send it."""

    uow: ExampleUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    catalog: LearningCatalogPort
    rules: LearningRulesPort
    proposer: LearnedProposalPort

    async def _require(self, context: AccessContext, example_id: uuid.UUID | None = None) -> None:
        await self.gate.require(
            context,
            SalesScopes.RULES_PROPOSE,
            SalesScopes.PRICE_READ,
            resource_type=_RESOURCE,
            resource_id=None if example_id is None else str(example_id),
        )

    async def request(
        self,
        context: AccessContext,
        customer_code: str,
        received_on: date,
        po: tuple[str, bytes],
        salesorder: tuple[str, bytes],
    ) -> SalesOrderExampleView:
        """A pair to learn from: kept, queued for the worker (202). The
        customer is the tenant's own, from its master data."""
        await self._require(context)
        scope = sales_scope(context)
        if (await self.catalog.customer_by_code(scope, customer_code)).data is None:
            raise NotFoundError("no such customer", details={"customer_code": customer_code})
        po_name = _named(po[0], PO_EXTENSIONS, po[1], "PO")
        so_name = _named(salesorder[0], SALESORDER_EXTENSIONS, salesorder[1], "SalesOrder")
        now = self.clock.now()
        example = SalesOrderExample(
            example_id=self.ids.new_uuid(),
            customer_code=customer_code,
            status="queued",
            requested_by=context.principal_id,
            requested_at=now,
            received_on=received_on,
            po_file_name=po_name,
            po_sha256=hashlib.sha256(po[1]).hexdigest(),
            po_size=len(po[1]),
            salesorder_file_name=so_name,
            salesorder_sha256=hashlib.sha256(salesorder[1]).hexdigest(),
            salesorder_size=len(salesorder[1]),
        )
        async with self.uow(scope) as work:
            await work.examples.prune(now - KEPT_FOR)
            await work.examples.add(example, po[1], salesorder[1])
            await work.outbox.add(
                OutboxEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    event_type=EXAMPLE_REQUESTED,
                    schema_version=EXAMPLE_EVENT_SCHEMA,
                    aggregate_id=example.example_id,
                    occurred_at=now,
                    payload={"example_id": str(example.example_id)},
                    actor_id=context.principal_id,
                )
            )
            await work.audit.append(self._audit(context, example, "requested", now))
            await work.commit()
        return example_view(example)

    async def get(self, context: AccessContext, example_id: uuid.UUID) -> SalesOrderExampleView:
        """The example, to whoever may propose and read prices. Another
        workspace's is not found: RLS leaves it out of every read here."""
        await self._require(context, example_id)
        async with self.uow(sales_scope(context)) as work:
            example = await work.examples.get(example_id)
        if example is None:
            raise NotFoundError("no such example", details={"example_id": str(example_id)})
        return example_view(example)

    async def for_customer(
        self, context: AccessContext, customer_code: str
    ) -> list[SalesOrderExampleView]:
        await self._require(context)
        async with self.uow(sales_scope(context)) as work:
            found = await work.examples.for_customer(customer_code, 10)
        return [example_view(example) for example in found]

    async def for_version(
        self, context: AccessContext, version_id: uuid.UUID
    ) -> SalesOrderExampleView:
        """The example a rule version was sent from: what its approval shows."""
        await self._require(context)
        async with self.uow(sales_scope(context)) as work:
            example = await work.examples.for_version(version_id)
        if example is None:
            raise NotFoundError(
                "no example for this version", details={"version_id": str(version_id)}
            )
        return example_view(example)

    async def submit(
        self, context: AccessContext, example_id: uuid.UUID, version: str
    ) -> RuleVersionView:
        """ "Gửi duyệt": the example's rules, proposed as the tenant's next
        version of the key, only where the replay matched against the layout
        still in force. Enforced here, whatever screen asked."""
        await self._require(context, example_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            example = await work.examples.get(example_id)
        if example is None:
            raise NotFoundError("no such example", details={"example_id": str(example_id)})
        if example.status == "submitted":
            raise ConflictError(
                "ví dụ này đã được gửi duyệt",
                details={"rule": "already_submitted", "version_id": str(example.version_id)},
            )
        if example.status != "replayed" or example.rules is None or example.replay is None:
            raise ConflictError(
                "chưa có quy tắc nào chạy lại được để gửi duyệt",
                details={"rule": "nothing_to_submit", "status": example.status},
            )
        if not example.replay.matches:
            raise ConflictError(
                "chạy lại chưa khớp tệp của PIC: sửa ví dụ rồi học lại trước khi gửi duyệt",
                details={
                    "rule": "replay_differs",
                    "differences": example.replay.differences_total,
                },
            )
        layout = (await self.rules.current(scope, RuleKey.BRAVO_UPLOAD)).policy
        if layout.ref != example.replay.layout_ref:
            raise ConflictError(
                "mẫu tệp nhập Bravo đã đổi từ khi chạy lại: học lại ví dụ",
                details={"rule": "layout_changed", "replayed": example.replay.layout_ref},
            )
        in_force = (await self.rules.current(scope, RuleKey.SALESORDER_RULES)).policy
        assert isinstance(in_force, SalesOrderRules)
        document = in_force.model_dump(mode="json", by_alias=True) | {
            "policy_version": version,
            "mock": False,
            "description": "",
            "customers": {
                **in_force.model_dump(mode="json", by_alias=True)["customers"],
                example.customer_code: example.rules.model_dump(mode="json", by_alias=True),
            },
        }
        proposed = await self.proposer.propose_learned(context, document)
        async with self.uow(scope) as work:
            if not await work.examples.submit(example_id, proposed.version_id):
                raise ConflictError(
                    "ví dụ này đã đổi trong lúc gửi duyệt",
                    details={"rule": "example_changed", "example_id": str(example_id)},
                )
            sent = example.model_copy(
                update={"status": "submitted", "version_id": proposed.version_id}
            )
            await work.audit.append(
                self._audit(
                    context,
                    sent,
                    "submitted",
                    self.clock.now(),
                    version_id=str(proposed.version_id),
                )
            )
            await work.commit()
        return proposed

    def _audit(
        self,
        context: AccessContext,
        example: SalesOrderExample,
        action: str,
        at: datetime,
        **extra: str,
    ) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=f"sales.salesorder_example.{action}",
            resource_type=_RESOURCE,
            resource_id=str(example.example_id),
            occurred_at=at,
            details=_details(example) | extra,
        )


# ------------------------------------------------------------ the learning --


def _failed(example: SalesOrderExample, reason: str) -> SalesOrderExample:
    return example.model_copy(update={"status": "failed", "error": reason[:500]})


def _content(name: str, data: bytes, attachment_id: str) -> AttachmentContent:
    media = "application/pdf" if name.casefold().endswith(".pdf") else "application/octet-stream"
    return AttachmentContent(
        attachment=Attachment(
            attachment_id=attachment_id,
            name=name,
            media_type=media,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


@dataclass(frozen=True, slots=True)
class Pair:
    """What learning reads from an example before the model is asked: the
    layout in force, the customer, its lookups, the PO's rows, the PIC's
    file, and the replay of the layout alone."""

    layout: BravoUploadLayout
    customer: Customer
    lookups: Lookups
    rows: list[dict[UploadField, Value]]
    pic: PicFile
    baseline: Replay
    # The PO as read, kept with the PIC's rows as a worked pair (ticket 41).
    document: PoDocument | None = None


@dataclass(frozen=True)
class SalesOrderLearning:
    """The worker's side of a request: `EXAMPLE_REQUESTED`, carried out.

    ``model`` is the one-call door to DW1's model; None on a host with no
    model server for DW1's profile, where an example the layout alone does
    not reproduce is `unavailable`. ``worker_id`` and ``worker_version`` are
    DW1's: what the call is recorded under."""

    uow: ExampleUnitOfWorkFactory
    po_reading: PoReadingPort
    sheets: SalesOrderSheetsPort
    scanner: MalwareScanPort
    catalog: LearningCatalogPort
    rules: LearningRulesPort
    access: RequesterAccessPort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def learn(self, scope: SalesScope, example_id: uuid.UUID) -> str:
        """Learns from one queued example; what it did, for the log.
        Idempotent: an example no longer queued is left alone. Raises
        `InfrastructureError` when the scanner or the reader did not answer,
        so the outbox delivers it again."""
        async with self.uow(scope) as work:
            example = await work.examples.get(example_id)
            files = None if example is None else await work.examples.files(example_id)
        if example is None or example.status != "queued":
            return "example not queued"
        settled, pair = (
            (_failed(example, "tệp không còn để đọc"), None)
            if files is None
            else await self._settle(scope, example, *files)
        )
        async with self.uow(scope) as work:
            if not await work.examples.settle(settled):
                return "example changed meanwhile"
            if pair is not None:
                await work.pairs.add(pair)
            await work.audit.append(
                lane_audit_event(
                    lane=EXAMPLE_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=f"sales.salesorder_example.{settled.status}",
                    resource_type=_RESOURCE,
                    resource_id=str(example_id),
                    occurred_at=self.clock.now(),
                    details=_details(settled) | {"requested_by": str(example.requested_by)},
                )
            )
            await work.commit()
        return f"example {settled.status}"

    async def _settle(
        self, scope: SalesScope, example: SalesOrderExample, po: bytes, salesorder: bytes
    ) -> tuple[SalesOrderExample, WorkedPair | None]:
        """What the example settles as, and the worked pair it is once both
        files were read (ticket 41)."""
        for data in (po, salesorder):
            verdict = await self.scanner.scan(data)
            if verdict.outcome == "unavailable":
                raise InfrastructureError(
                    "chưa quét được tệp, thử lại", details={"reason_code": "scanner_unavailable"}
                )
            if verdict.outcome == "infected":
                return _failed(example, "tệp bị trình quét mã độc chặn"), None
        context = await self._asker(scope, example)
        if context is None:
            return _failed(example, "người tải tệp không còn quyền học quy tắc của khách"), None
        read = await self._pair(scope, example, po, salesorder)
        if isinstance(read, str):
            return _failed(example, read), None
        if isinstance(read, list):
            return example.model_copy(update={"status": "refused", "problems": tuple(read)}), None
        return await self._learned(example, read, context), self._worked(example, read)

    def _worked(self, example: SalesOrderExample, pair: Pair) -> WorkedPair | None:
        """The pair as the customer's worked pair: the PO as read, the PIC's
        rows by letter."""
        if pair.document is None or not pair.pic.rows:
            return None
        return WorkedPair(
            pair_id=self.ids.new_uuid(),
            example_id=example.example_id,
            customer_code=example.customer_code,
            received_on=example.received_on,
            layout_ref=pair.layout.ref,
            document=pair.document,
            expected=tuple(
                {column_letter(i): text for i, text in row.cells.items()} for row in pair.pic.rows
            ),
            added_by=example.requested_by,
            added_at=self.clock.now(),
        )

    async def _learned(
        self, example: SalesOrderExample, pair: Pair, context: AccessContext
    ) -> SalesOrderExample:
        kept = example.model_copy(update={"replay": pair.baseline})
        if pair.baseline.matches and not pair.baseline.unexplained:
            # The layout alone reproduces the file: nothing to ask, nothing to learn.
            return kept.model_copy(update={"status": "replayed"})
        if self.model is None:
            return self._without(kept, "model_not_configured")
        stamped = kept.model_copy(
            update={
                "prompt_ref": str(SALESORDER_RULES_PROPOSAL),
                "model_profile": self.model.model_profile,
            }
        )
        try:
            answer = await self.model.interpret(
                SALESORDER_RULES_PROPOSAL,
                proposal_inputs(
                    pair.layout,
                    pair.rows,
                    pair.pic,
                    pair.baseline,
                    self.model.max_input_tokens - PROMPT_TOKENS,
                ),
                ModelSalesOrderRules,
                run=self._run(context, example),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return self._without(stamped, "model_unavailable")
        except QuotaExceededError:
            return self._without(stamped, "model_quota")
        return settled_with(stamped, answer, pair)

    def _without(
        self,
        example: SalesOrderExample,
        why: Literal["model_unavailable", "model_not_configured", "model_quota"],
    ) -> SalesOrderExample:
        return example.model_copy(
            update={"status": "unavailable", "problems": (LearnProblem(code=why),)}
        )

    async def _pair(
        self, scope: SalesScope, example: SalesOrderExample, po: bytes, salesorder: bytes
    ) -> Pair | list[LearnProblem] | str:
        """The pair read, or why not: problems a person reads beside the
        files, or the reason the learning failed."""
        customer = (await self.catalog.customer_by_code(scope, example.customer_code)).data
        if customer is None:
            return "khách hàng không còn trong dữ liệu gốc"
        if self.sheets.kind(salesorder) != "xlsx":
            return "tệp SalesOrder không phải bảng tính Excel"
        order_rules = (await self.rules.current(scope, RuleKey.ORDER_RULES)).policy
        layout = (await self.rules.current(scope, RuleKey.BRAVO_UPLOAD)).policy
        assert isinstance(order_rules, OrderRules) and isinstance(layout, BravoUploadLayout)
        try:
            document = await self.po_reading.read(
                scope,
                _content(example.po_file_name, po, f"{example.example_id}-po"),
                customer.code,
                order_rules.intake,
            )
            grid = await self._grid(salesorder)
        except DomainError:
            return "không mở được một trong hai tệp"
        if isinstance(document, Unreadable):
            return "không đọc được PO: cần mẫu PO của khách đã duyệt"
        if grid is None:
            return "không tìm thấy hàng tiêu đề trong tệp SalesOrder"
        pic = pic_file(grid, layout)
        if isinstance(pic, list):
            return pic
        lookups = Lookups.of(
            customer.code,
            (await self.catalog.convert_list(scope)).data,
            (await self.catalog.items(scope)).data,
        )
        rows = example_rows(document, customer.code, example.received_on, lookups)
        baseline = replay(layout, None, rows, customer, lookups, pic)
        return Pair(layout, customer, lookups, rows, pic, baseline, document)

    async def _grid(self, data: bytes) -> SheetGrid | None:
        """The first sheet with a header row."""
        for name in (await self.sheets.sheet_names(data))[:MAX_SHEETS]:
            grid = await self.sheets.sheet_grid(data, name)
            if grid is not None and header_row(grid) is not None:
                return grid
        return None

    async def _asker(self, scope: SalesScope, example: SalesOrderExample) -> AccessContext | None:
        """Who asked, as the platform resolves them now, cut to the ceiling;
        None when they may no longer propose or read prices, or the context
        is another workspace's."""
        access = await self.access.find_linked_access(
            example.requested_by, scope.tenant_id.value, scope.workspace_id.value, LEARNING_CEILING
        )
        if access is None:
            return None
        context = context_from(access)
        if sales_scope(context) != scope or not context.scopes >= LEARNING_CEILING:
            return None
        return context

    def _run(self, context: AccessContext, example: SalesOrderExample) -> RunContext:
        """The one call's run, as the asker (`caller_run`)."""
        return caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            trace="sales-salesorder-example",
            subject_ref=f"{_RESOURCE}:{example.example_id}",
        )


def settled_with(
    example: SalesOrderExample, answer: ModelSalesOrderRules, pair: Pair
) -> SalesOrderExample:
    """The model's answer, verified and replayed: what an example settles
    as once the model answered. Shared with the eval of the step."""
    checked = verify(answer, pair.layout, pair.rows, pair.pic)
    if isinstance(checked, list):
        return example.model_copy(update={"status": "refused", "problems": tuple(checked)})
    proven = replay(pair.layout, checked, pair.rows, pair.customer, pair.lookups, pair.pic)
    return example.model_copy(update={"status": "replayed", "rules": checked, "replay": proven})
