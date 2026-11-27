"""What the gateway asks of Bravo and of DW, as ports.

Each port answers one question one check of `pipeline.WritePipeline` asks,
so a test can make exactly that check fail. The live adapter
(`adapters.sqlserver`) answers the Bravo ones through the driver, the
recorded one (`adapters.recorded`) from a trace; the ledger and the switches
are DW's PostgreSQL.

A Bravo that does not answer raises `BravoUnavailableError`: a "could not
check", never a pass (ADR 0026's rule 5, kept by ADR 0027).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from dw_bravo.approval_token import ApprovalClaims
from dw_bravo.contract import CustomerPoRows, SalesOrderState
from dw_bravo.layout import Layout
from dw_bravo.ports import ProcedurePort, ReferencePort, Session
from dw_bravo.sync import SyncPage, SyncQuery


class BravoUnavailableError(Exception):
    """Bravo did not answer; whatever was being checked is not checked."""


class StaleRowError(Exception):
    """A row's rowversion no longer matches: someone saved it since."""


class DocumentNotFoundError(Exception):
    pass


class AmbiguousDocumentError(Exception):
    """More than one document answers to a number: none is chosen."""


@dataclass(frozen=True)
class BravoUser:
    """A `B00UserList` row that is a user (not a group)."""

    id: int
    user_name: str
    employee_code: str | None  # Ma_CbNv
    active: bool  # IsActive, and not past Expire or LockDate


class Directory(Protocol):
    """Who an employee code is in Bravo, read live at each write (ticket 64)."""

    async def users_by_employee_code(self, employee_code: str) -> Sequence[BravoUser]: ...


class SalesOrders(Protocol):
    """An SO as Bravo holds it now, found by its number (ticket 53): what a
    proposed write names. Not found raises `DocumentNotFoundError`, several
    `AmbiguousDocumentError`."""

    async def sales_order(self, so_no: str) -> SalesOrderState: ...

    async def customer_po(self, customer_code: str, po_no: str) -> CustomerPoRows:
        """Every SO line of the PO; none is an empty answer, not an error."""
        ...


class SyncTables(Protocol):
    """Rows of an allowlisted table past a rowversion (ticket 50)."""

    async def changes(self, query: SyncQuery) -> SyncPage: ...


@dataclass(frozen=True)
class ColumnRight:
    """One row of `usp_sys_GetControlPermission(@UserId, @CommandKey)`."""

    table: str
    column: str
    no_add_new: bool
    no_edit: bool


CommandRight = Literal["allowed", "denied", "unknown"]


class Rights(Protocol):
    """Bravo's own answer to "may this user do this", never DW's copy."""

    async def column_rights(self, user_id: int, command_key: str) -> Sequence[ColumnRight]: ...

    async def command_right(
        self, user_id: int, command_key: str, operation: Literal["update", "insert"]
    ) -> CommandRight: ...


@dataclass
class StoredDocument:
    """A document as Bravo holds it now, with what the client's load adds.

    `header`/`lines` are the stored columns (with `Id` and the rowversion as
    `timestamp`, hex); `derived_*` the columns the client's load view joins
    in, `UNKNOWN` where the adapter cannot read them (the runner then refuses
    a rule that needs one). `column_order` is each table's column order, in
    which the client lists a statement's columns. `prevent_edit` is
    `ufn_Prevent_Edit` per line `RowId`: 1 when the line sits on a CDO.

    What an INSERT needs of each table, from `sys.columns`: `no_default`, the
    columns without a default (an INSERT lists them NULL), and `generated`,
    the identity, rowversion and computed columns no statement writes, both
    lower case. A table absent from either was not read, and a new row of it
    is refused.
    """

    header: dict[str, object]
    lines: list[dict[str, object]]
    derived_header: dict[str, object] = field(default_factory=dict)
    derived_lines: list[dict[str, object]] = field(default_factory=list)
    column_order: Mapping[str, Sequence[str]] = field(default_factory=dict)
    prevent_edit: Mapping[str, int | None] = field(default_factory=dict)
    no_default: Mapping[str, frozenset[str]] = field(default_factory=dict)
    generated: Mapping[str, frozenset[str]] = field(default_factory=dict)


class Documents(Protocol):
    async def load(self, screen: str, doc_id: int) -> StoredDocument: ...


class Engine(Protocol):
    """What the rule runner needs from Bravo for one screen and one user."""

    async def layout(self, screen: str) -> Layout: ...

    def procedures(self) -> ProcedurePort: ...

    def references(self) -> ReferencePort: ...

    async def session(self, user: BravoUser, branch: str, now: datetime) -> Session: ...

    async def view_columns(self, view: str) -> Sequence[str]:
        """The columns of the view a layout loads a table from (its `Name`):
        what the client's row of that table holds."""
        ...


@dataclass(frozen=True)
class Statement:
    """One statement the client would send, and its parameter values."""

    table: str
    row_id: object
    sql: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class ProcedureStep:
    """A Bravo procedure the client runs after a save's statements, with the
    parameter values it passes (`statements.process_step`)."""

    name: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class Batch:
    """One save: the context line, then its statements, then the procedures
    the client runs after them, in one transaction."""

    context: str
    statements: Sequence[Statement]
    steps: Sequence[ProcedureStep] = ()


class Writer(Protocol):
    async def execute(self, batch: Batch) -> None:
        """All or nothing; `StaleRowError` when any statement touched no row."""
        ...


LedgerStatus = Literal["claimed", "written", "refused", "in_doubt", "reconcile_failed"]


@dataclass(frozen=True)
class LedgerEntry:
    approval_id: uuid.UUID
    status: LedgerStatus
    kind: str
    content_hash: str
    detail: Mapping[str, object] = field(default_factory=dict)


class Ledger(Protocol):
    """Idempotency by approval id, in DW's PostgreSQL (tenant-scoped)."""

    async def find(self, claims: ApprovalClaims) -> LedgerEntry | None: ...

    async def claim(self, claims: ApprovalClaims) -> bool:
        """True when this call took the approval id; False when it was taken."""
        ...

    async def settle(
        self, claims: ApprovalClaims, status: LedgerStatus, detail: Mapping[str, object]
    ) -> None: ...


SwitchState = Literal["enabled", "off", "paused"]


class Switches(Protocol):
    """Whether a tenant's write kind may run: off until a person with the
    right enables it after UAT (ticket 63 g), paused by the watch (ticket 65)."""

    async def state(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, kind: str
    ) -> SwitchState: ...
