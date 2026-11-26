"""A write's checks, in the order ticket 63 sets; the first that fails refuses.

1. **The approval token** (`dw_bravo.approval_token`): signed, unexpired,
   for exactly this command (kind and content hash). Everything the write
   needs to know about who and which tenant is read from it, never from the
   request. Then what the token alone decides: the kind is one the gateway
   may run (`WriteKind.pending`), the tenant has it switched on and the watch
   has not paused it, and the approval id was not spent.
2. **Identity is live** (ticket 64): exactly one active Bravo user holds the
   employee code, and it is the user the approval stamped.
3. **Bravo's right**, from Bravo's own routines: the command right, and
   `usp_sys_GetControlPermission` for each column the person would type.
4. **The screen's rules** (`dw_bravo`) on the document as Bravo holds it now:
   the line is as the PIC saw it, blocks refuse, an undecided block refuses,
   a plan made without every rule refuses; warnings go back with the result.
5. **The lock**: `ufn_Prevent_Edit` says the line is not on a CDO.
6. **The write**: the approval id claimed in the ledger, the client's own
   statements under the PIC's context and the rows' rowversions, in one
   transaction, then read back and reconciled column by column.

A Bravo that does not answer at any step is "could not check" and refuses.
"""

from __future__ import annotations

import asyncio
import uuid
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from dw_bravo.approval_token import ApprovalClaims, ApprovalTokenVerifier, TokenRefusedError
from dw_bravo.contract import (
    WRITE_KINDS,
    CancelLine,
    SetConfirmedDate,
    SetQuantity,
    WriteCommand,
    WriteKind,
    content_hash,
)
from dw_bravo.expression import UNKNOWN, RuleRefusedError, UndecidableError, is_empty
from dw_bravo.runner import Document, Row, RuleRunner, SavePlan, _same
from dw_bravo_gateway.ports import (
    Batch,
    BravoUnavailableError,
    BravoUser,
    Directory,
    DocumentNotFoundError,
    Documents,
    Engine,
    Ledger,
    Rights,
    StaleRowError,
    StoredDocument,
    Switches,
    Writer,
)
from dw_bravo_gateway.statements import (
    SCREENS,
    ScreenTables,
    UnmeasuredError,
    context_line,
    process_step,
    render_save,
)

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")

Outcome = Literal["written", "already_written", "refused", "in_doubt", "written_with_differences"]
Check = Literal["token", "kind", "switch", "ledger", "identity", "right", "rules", "lock", "write"]


@dataclass(frozen=True)
class WriteResult:
    outcome: Outcome
    check: Check | None = None
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class Preview:
    """What check 6 would send, and whether checks 1-5 let it: the batch is
    rendered even when a rule refuses, so a person (and the trace replay)
    can see the exact save the gateway is holding back, and why."""

    batch: Batch | None
    check: Check | None
    reason: str | None
    warnings: tuple[str, ...] = ()


class _RefusedError(Exception):
    def __init__(self, check: Check, reason: str, warnings: Sequence[str] = ()) -> None:
        super().__init__(reason)
        self.check, self.reason, self.warnings = check, reason, tuple(warnings)


@dataclass(frozen=True)
class Edit:
    table: str  # the layout's table key
    column: str
    value: object


def typed_edits(command: WriteCommand) -> list[Edit]:
    """What the person types for a command, as the 11-20 trace shows it."""
    if isinstance(command, SetConfirmedDate):
        # Bravo holds dates as datetime at midnight (the trace's values).
        return [
            Edit(
                "Detail", "EstimatedTimeDelivery", datetime.combine(command.confirmed_date, time())
            )
        ]
    if isinstance(command, SetQuantity):
        return [Edit("Detail", "Quantity9", Decimal(command.quantity))]
    if isinstance(command, CancelLine):
        # The order the screen allows (UAT trace 11-25 17:31:50, ticket 71):
        # the quantity opens for typing only once "Order status" is set, and
        # the cancelled price is taken from the unit price before the zero
        # quantity resets it.
        return [
            Edit("Detail", "IsCancel", "Cancel"),
            Edit("Detail", "CancelRemark", command.reason),
            Edit("Detail", "Quantity9", Decimal(0)),
        ]
    raise UnmeasuredError(f"what a person types for {type(command).__name__} is not traced")


@dataclass
class WritePace:
    """One write at a time per document; spaced during Bravo's busy hours.

    The 11-19 survey measured documents being made 8-18h Vietnam time; a
    write then waits `busy_gap` after the last one, so DW never adds a burst
    to the PICs' own load.
    """

    busy_gap: timedelta = timedelta(seconds=2)
    busy_hours: tuple[int, int] = (8, 18)
    # Weak: a document's lock lives while a write holds it, then goes, so
    # the map never grows past the writes in flight.
    _locks: weakref.WeakValueDictionary[tuple[str, int], asyncio.Lock] = field(
        default_factory=weakref.WeakValueDictionary
    )
    _last: datetime | None = None

    def lock(self, screen: str, doc_id: int) -> asyncio.Lock:
        lock = self._locks.get((screen, doc_id))
        if lock is None:
            lock = self._locks[(screen, doc_id)] = asyncio.Lock()
        return lock

    def wait_for(self, now: datetime) -> timedelta:
        local = now.astimezone(VIETNAM)
        if self._last is None or not self.busy_hours[0] <= local.hour < self.busy_hours[1]:
            return timedelta(0)
        return max(timedelta(0), self._last + self.busy_gap - now)

    def wrote(self, now: datetime) -> None:
        self._last = now


@dataclass
class WritePipeline:
    verifier: ApprovalTokenVerifier
    switches: Switches
    ledger: Ledger
    directory: Directory
    rights: Rights
    documents: Documents
    engine: Engine
    writer: Writer
    now: Callable[[], datetime]
    # The one DW tenant whose Bravo this gateway reaches: a token another
    # tenant's approval signed is refused, whatever its switches say.
    tenant_id: uuid.UUID
    screens: Mapping[str, ScreenTables] = field(default_factory=lambda: dict(SCREENS))
    pace: WritePace = field(default_factory=WritePace)

    async def execute(self, command: WriteCommand, token: str) -> WriteResult:
        try:
            claims, kind = self._token(command, token)
            await self._kind(claims, kind)
            existing = await self.ledger.find(claims)
            if existing is not None:
                if existing.status == "written" and existing.content_hash == claims.content_hash:
                    return WriteResult("already_written", "ledger", "approval_already_written")
                raise _RefusedError("ledger", f"approval_already_{existing.status}")
            user = await self._identity(claims)
            await self._right(user, kind, command)
            async with self.pace.lock(kind.screen, _doc_id(command)):
                return await self._write(claims, kind, command, user)
        except _RefusedError as refused:
            return WriteResult("refused", refused.check, refused.reason, refused.warnings)
        except BravoUnavailableError:
            return WriteResult("refused", None, "bravo_unreachable_could_not_check")

    async def preview(self, command: WriteCommand, token: str) -> Preview:
        """Checks 1-5 without the ledger's claim or the write."""
        try:
            claims, kind = self._token(command, token)
            await self._kind(claims, kind)
            user = await self._identity(claims)
            await self._right(user, kind, command)
            stored = await self._load(kind, command)
            plan, warnings, refusal = await self._plan(kind, command, stored, user)
            batch = self._batch(kind, plan, stored, user)
            if refusal is None:
                self._lock(plan, stored, warnings)
        except _RefusedError as refused:
            return Preview(None, refused.check, refused.reason, refused.warnings)
        if refusal is not None:
            return Preview(batch, refusal.check, refusal.reason, refusal.warnings)
        return Preview(batch, None, None, warnings)

    # ------------------------------------------------------------ 1: token

    def _token(self, command: WriteCommand, token: str) -> tuple[ApprovalClaims, WriteKind]:
        try:
            claims = self.verifier.verify(token, now=self.now())
        except TokenRefusedError as refused:
            raise _RefusedError("token", refused.reason) from None
        key = f"{type(command).kind}@{type(command).version}"
        if claims.tenant_id != self.tenant_id:
            raise _RefusedError("token", "another_tenants_approval")
        if claims.kind != key:
            raise _RefusedError("token", "kind_not_approved")
        if claims.content_hash != content_hash(command):
            raise _RefusedError("token", "content_changed_since_approval")
        return claims, WRITE_KINDS[key]

    async def _kind(self, claims: ApprovalClaims, kind: WriteKind) -> None:
        if kind.pending is not None:
            raise _RefusedError("kind", f"pending: {kind.pending}")
        state = await self.switches.state(claims.tenant_id, claims.workspace_id, claims.kind)
        if state != "enabled":
            raise _RefusedError("switch", f"write_kind_{state}")

    # --------------------------------------------------------- 2: identity

    async def _identity(self, claims: ApprovalClaims) -> BravoUser:
        users = await self.directory.users_by_employee_code(claims.employee_code)
        active = [u for u in users if u.active]
        if not active:
            raise _RefusedError("identity", "no_active_bravo_user_for_employee_code")
        if len(active) > 1:
            raise _RefusedError("identity", "several_active_bravo_users_for_employee_code")
        if active[0].id != claims.bravo_user_id:
            raise _RefusedError("identity", "bravo_user_changed_since_approval")
        return active[0]

    # ------------------------------------------------------------ 3: right

    async def _right(self, user: BravoUser, kind: WriteKind, command: WriteCommand) -> None:
        answer = await self.rights.command_right(user.id, kind.screen, kind.operation)
        if answer != "allowed":
            raise _RefusedError("right", f"command_right_{answer}")
        rights = await self.rights.column_rights(user.id, kind.screen)
        tables = self.screens[kind.screen]
        for edit in typed_edits(command):
            table = tables.table_for(edit.table)
            for right in rights:
                barred = right.no_edit if kind.operation == "update" else right.no_add_new
                if (
                    barred
                    and right.table.lower() == table.lower()
                    and right.column.lower() == edit.column.lower()
                ):
                    raise _RefusedError("right", f"no_right_on_{edit.column}")

    # ------------------------------------------------- 4, 5, 6: under lock

    async def _write(
        self, claims: ApprovalClaims, kind: WriteKind, command: WriteCommand, user: BravoUser
    ) -> WriteResult:
        line_ref = command.line  # type: ignore[union-attr]
        stored = await self._load(kind, command)
        plan, warnings, refusal = await self._plan(kind, command, stored, user)
        if refusal is not None:
            raise refusal
        self._lock(plan, stored, warnings)
        batch = self._batch(kind, plan, stored, user)
        await self._paced()
        if not await self.ledger.claim(claims):
            raise _RefusedError("ledger", "approval_already_claimed", warnings)
        try:
            await self.writer.execute(batch)
        except StaleRowError:
            await self.ledger.settle(claims, "refused", {"reason": "stale_row"})
            raise _RefusedError("write", "row_changed_before_write", warnings) from None
        except Exception as failed:
            # Sent, and no answer: whether Bravo holds it is unknown. The
            # approval id stays spent until a person reads Bravo.
            await self.ledger.settle(claims, "in_doubt", {"error": type(failed).__name__})
            return WriteResult("in_doubt", "write", "no_answer_after_send", warnings)
        self.pace.wrote(self.now())
        differences = await self._reconcile(kind, line_ref.so_id, plan, stored)
        if differences:
            await self.ledger.settle(claims, "reconcile_failed", {"differences": list(differences)})
            return WriteResult("written_with_differences", "write", None, warnings, differences)
        await self.ledger.settle(claims, "written", {"statements": len(batch.statements)})
        return WriteResult("written", None, None, warnings)

    async def _load(self, kind: WriteKind, command: WriteCommand) -> StoredDocument:
        line_ref = command.line  # type: ignore[union-attr]
        try:
            stored = await self.documents.load(kind.screen, line_ref.so_id)
        except DocumentNotFoundError:
            raise _RefusedError("rules", "document_not_found") from None
        line_index = _line_index(stored, line_ref.line_id)
        if stored.lines[line_index].get("timestamp") != line_ref.line_rowversion:
            raise _RefusedError("rules", "line_changed_since_approval")
        return stored

    def _lock(self, plan: SavePlan, stored: StoredDocument, warnings: Sequence[str]) -> None:
        """5: Bravo's own `ufn_Prevent_Edit`, per line written; no answer locks."""
        for written in plan.commands:
            if written.table != "Parent":
                row_key = str(stored.lines[written.row].get("RowId"))
                if stored.prevent_edit.get(row_key) != 0:
                    raise _RefusedError("lock", "line_locked_or_could_not_check", warnings)

    async def _plan(
        self, kind: WriteKind, command: WriteCommand, stored: StoredDocument, user: BravoUser
    ) -> tuple[SavePlan, tuple[str, ...], _RefusedError | None]:
        """4: the plan, and the rules' refusal of it if any (raised by the caller)."""
        try:
            layout = await self.engine.layout(kind.screen)
        except (RuleRefusedError, UndecidableError) as refused:
            raise _RefusedError("rules", f"layout_could_not_be_read: {refused}") from None
        if isinstance(command, CancelLine):
            line = stored.lines[_line_index(stored, command.line.line_id)]
            if not is_empty(line.get("Divide")):
                # The traced cancel of a split group's first line also cleared
                # `Divide` by hand; what a person does there is not measured.
                raise _RefusedError("rules", "unmeasured: a cancel of a split line")
        branch = str(stored.header.get("BranchCode") or "")
        session = await self.engine.session(user, branch, self.now())
        runner = RuleRunner(layout, self.engine.procedures(), self.engine.references(), session)
        doc = document_of(stored)
        try:
            runner.load(doc)
            for edit in typed_edits(command):
                index = _line_index(stored, command.line.line_id) if edit.table != "Parent" else 0  # type: ignore[union-attr]
                runner.edit(doc, edit.table, index, edit.column, edit.value)
            # A stored document, opened and saved: the template's guards on
            # those two commands (ticket 59).
            plan = runner.save(doc, commands=("Edit", "Save"))
        except (RuleRefusedError, UndecidableError) as refused:
            raise _RefusedError("rules", f"rules_could_not_decide: {refused}") from None
        # A warning that fired, or one that could not be decided, goes back to
        # the PIC; an undecided block refuses like a block (`Check.may_save`).
        warnings = [f.rule for f in plan.check.warnings]
        warnings += [
            f"{f.rule} (could not check)" for f in plan.check.undecided if f.level == "warning"
        ]
        undecided = [f.rule for f in plan.check.undecided if f.level == "block"]
        refusal = None
        if plan.check.blocking:
            refusal = _RefusedError(
                "rules", "blocked: " + ", ".join(f.rule for f in plan.check.blocking), warnings
            )
        elif undecided:
            refusal = _RefusedError("rules", "undecided: " + ", ".join(undecided), warnings)
        elif not plan.may_write:
            refusal = _RefusedError(
                "rules", "provisional: " + "; ".join(plan.provisional), warnings
            )
        return plan, tuple(warnings), refusal

    def _batch(
        self, kind: WriteKind, plan: SavePlan, stored: StoredDocument, user: BravoUser
    ) -> Batch:
        tables = self.screens[kind.screen]
        event = tables.context_event.get(kind.operation)
        if event is None:
            raise _RefusedError("write", "unmeasured: the client's context for this save")
        today = self.now().astimezone(VIETNAM)
        doc_date = stored.header.get("DocDate")
        if not isinstance(doc_date, datetime) or doc_date.year != today.year:
            raise _RefusedError(
                "write", "unmeasured: the context's year for a document of another year"
            )
        context = context_line(
            kind.screen, event, user.id, str(stored.header["BranchCode"]), today.year
        )
        rows: dict[tuple[str, int], tuple[object, str]] = {
            ("Parent", 0): (stored.header["Id"], str(stored.header["timestamp"]))
        }
        for key in tables.lines:
            for i, line in enumerate(stored.lines):
                rows[(key, i)] = (line["Id"], str(line["timestamp"]))
        try:
            batch = render_save(
                kind.screen, plan.commands, rows, stored.column_order, context=context
            )
            return replace(batch, steps=(process_step(kind.screen, stored.header),))
        except UnmeasuredError as unmeasured:
            raise _RefusedError("write", f"unmeasured: {unmeasured}") from None

    async def _paced(self) -> None:
        wait = self.pace.wait_for(self.now())
        if wait > timedelta(0):
            await asyncio.sleep(wait.total_seconds())

    async def _reconcile(
        self, kind: WriteKind, doc_id: int, plan: SavePlan, before: StoredDocument
    ) -> tuple[str, ...]:
        """Every column written, read back: what Bravo holds must be what was planned."""
        try:
            after = await self.documents.load(kind.screen, doc_id)
        except (BravoUnavailableError, DocumentNotFoundError):
            return ("read_back_failed",)
        differences: list[str] = []
        for written in plan.commands:
            row = (
                after.header
                if written.table == "Parent"
                else _row_by_id(after, before.lines[written.row]["Id"])
            )
            if row is None:
                differences.append(f"{written.table}#{written.row}: row gone")
                continue
            lowered = {k.lower(): v for k, v in row.items()}
            for column, value in written.columns.items():
                if column.lower() == "modifiedby":
                    continue
                if value is None:
                    # Written as DEFAULT, as the client does: the column's own
                    # default decides what Bravo holds (statements.render_update).
                    continue
                if not _same(_normal(lowered.get(column.lower())), _normal(value)):
                    differences.append(f"{written.table}#{written.row}.{column}")
        return tuple(differences)


def document_of(stored: StoredDocument) -> Document:
    """A stored document as the runner's: stored columns plus the load's."""
    parent = Row({**stored.derived_header, **stored.header}, stored=stored.header.keys())
    lines = [
        Row(
            {**(stored.derived_lines[i] if i < len(stored.derived_lines) else {}), **line},
            stored=line.keys(),
        )
        for i, line in enumerate(stored.lines)
    ]
    return Document(parent=parent, children={"Detail": lines})


def _doc_id(command: WriteCommand) -> int:
    return int(command.line.so_id)  # type: ignore[union-attr]


def _line_index(stored: StoredDocument, line_id: int) -> int:
    for i, line in enumerate(stored.lines):
        if line.get("Id") == line_id:
            return i
    raise _RefusedError("rules", "line_not_in_document")


def _row_by_id(stored: StoredDocument, row_id: object) -> dict[str, object] | None:
    return next((line for line in stored.lines if line.get("Id") == row_id), None)


def _normal(value: object) -> object:
    if value is UNKNOWN:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    return value
