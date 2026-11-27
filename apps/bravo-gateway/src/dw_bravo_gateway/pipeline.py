"""A write's checks, in the order ticket 63 sets; the first that fails refuses.

1. **The approval token** (`dw_bravo.approval_token`): signed, unexpired,
   for exactly this command (kind and content hash). Everything the write
   needs to know about who and which tenant is read from it, never from the
   request. Then the target (ticket 85): the Bravo the token was stamped
   with is the tenant's target now, and the one this pipeline reaches. Then
   what the token alone decides: the kind is one the gateway may run
   (`WriteKind.pending`), the tenant has it switched on and the watch has
   not paused it, and the approval id was not spent.
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
    BravoTarget,
    CancelLine,
    SetConfirmedDate,
    SetQuantity,
    SplitLine,
    WriteCommand,
    WriteKind,
    content_hash,
)
from dw_bravo.expression import UNKNOWN, RuleRefusedError, UndecidableError, is_empty
from dw_bravo.layout import Layout
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
    WriteRejectedError,
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
Check = Literal[
    "token", "target", "kind", "switch", "ledger", "identity", "right", "rules", "lock", "write"
]


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
    # The k-th line the command adds (`AddRow`), or None: the command's line.
    new_row: int | None = None


@dataclass(frozen=True)
class AddRow:
    """A line added to the grid, as a person adds one."""

    table: str


def typed_edits(command: WriteCommand, *, group: str = "") -> list[Edit | AddRow]:
    """What the person types for a command, as the UAT traces show it.
    `group` is a split's group label (`group_label`)."""
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
    if isinstance(command, SplitLine):
        # The order the layout allows (ticket 73; UAT trace 11-25 17:28:58):
        # "Divide" first, so `Eval_QuantityGroup_GetVaule` takes the line's
        # whole quantity as the group's, and the line is the group's head
        # before its label is typed (`Eval_Detail_Divi_GetData` copies a
        # head's columns onto a labelled line without "Divide": onto the
        # head itself, NULLs). Then the label, then the first part. Each
        # further part is a new line: its label copies the head's item, PO
        # line, price and the rest (the same rule), then its quantity
        # (`OriginalQuantity` follows on a line with `Id < 0`).
        edits: list[Edit | AddRow] = [
            Edit("Detail", "Divide", Decimal(1)),
            Edit("Detail", "GroupDivi", group),
            Edit("Detail", "Quantity9", Decimal(command.parts[0].quantity)),
        ]
        for k, part in enumerate(command.parts[1:]):
            edits += [
                AddRow("Detail"),
                Edit("Detail", "GroupDivi", group, new_row=k),
                Edit("Detail", "Quantity9", Decimal(part.quantity), new_row=k),
            ]
        return edits
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
    # Which of the tenant's Bravos the ports above reach (ticket 85).
    target: BravoTarget
    screens: Mapping[str, ScreenTables] = field(default_factory=lambda: dict(SCREENS))
    pace: WritePace = field(default_factory=WritePace)

    async def execute(self, command: WriteCommand, token: str) -> WriteResult:
        try:
            claims, kind = self._token(command, token)
            await self._target(claims)
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
            await self._target(claims)
            await self._kind(claims, kind)
            user = await self._identity(claims)
            await self._right(user, kind, command)
            stored = await self._load(kind, command)
            plan, warnings, refusal, insertable = await self._plan(kind, command, stored, user)
            batch = self._batch(kind, plan, stored, user, insertable)
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

    async def _target(self, claims: ApprovalClaims) -> None:
        """The Bravo the proposal was read from (the token's stamp) is the
        tenant's target now, and the one this pipeline reaches: a proposal
        read from UAT never writes production, nor the reverse, and a switch
        made after the write was routed here refuses it."""
        current = await self.switches.target(claims.tenant_id)
        if current is None:
            raise _RefusedError("target", "target_unreadable")
        if claims.target != current or current != self.target:
            raise _RefusedError("target", "target_changed")

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
        edits = typed_edits(command)
        operations: list[Literal["update", "insert"]] = [kind.operation]
        if any(isinstance(e, AddRow) for e in edits) and "insert" not in operations:
            # A line added to a stored SO's grid: whether Bravo asks the
            # Edit right, the New right or both is not measured (ticket 75,
            # script 10), so both are asked and either refusal refuses.
            operations.append("insert")
        for operation in operations:
            answer = await self.rights.command_right(user.id, kind.screen, operation)
            if answer != "allowed":
                raise _RefusedError("right", f"command_right_{answer}")
        rights = await self.rights.column_rights(user.id, kind.screen)
        tables = self.screens[kind.screen]
        for edit in edits:
            if isinstance(edit, AddRow):
                continue
            table = tables.table_for(edit.table)
            new = edit.new_row is not None or kind.operation == "insert"
            for right in rights:
                barred = right.no_add_new if new else right.no_edit
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
        plan, warnings, refusal, insertable = await self._plan(kind, command, stored, user)
        if refusal is not None:
            raise refusal
        self._lock(plan, stored, warnings)
        batch = self._batch(kind, plan, stored, user, insertable)
        await self._paced()
        if not await self.ledger.claim(claims):
            raise _RefusedError("ledger", "approval_already_claimed", warnings)
        try:
            await self.writer.execute(batch)
        except StaleRowError:
            await self.ledger.settle(claims, "refused", {"reason": "stale_row"})
            raise _RefusedError("write", "row_changed_before_write", warnings) from None
        except WriteRejectedError as rejected:
            # Bravo answered and the batch was rolled back: nothing is written.
            await self.ledger.settle(claims, "refused", {"reason": str(rejected)[:200]})
            raise _RefusedError("write", "rejected_and_rolled_back", warnings) from None
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
        """5: Bravo's own `ufn_Prevent_Edit`, per stored line written; no
        answer locks. A new line is on no CDO; the line it splits is checked."""
        for written in plan.commands:
            if written.table != "Parent" and written.kind == "update":
                row_key = str(stored.lines[written.row].get("RowId"))
                if stored.prevent_edit.get(row_key) != 0:
                    raise _RefusedError("lock", "line_locked_or_could_not_check", warnings)

    async def _plan(
        self, kind: WriteKind, command: WriteCommand, stored: StoredDocument, user: BravoUser
    ) -> tuple[SavePlan, tuple[str, ...], _RefusedError | None, Mapping[str, Sequence[str]]]:
        """4: the plan, the rules' refusal of it if any (raised by the caller),
        and the columns each table's new line may be inserted with."""
        try:
            layout = await self.engine.layout(kind.screen)
        except (RuleRefusedError, UndecidableError) as refused:
            raise _RefusedError("rules", f"layout_could_not_be_read: {refused}") from None
        line_index = _line_index(stored, command.line.line_id)  # type: ignore[union-attr]
        line = stored.lines[line_index]
        if not is_empty(line.get("IsCancel")):
            # "Order status" set: no trace shows a person typing into a line
            # Bravo already holds cancelled (a second cancel would recompute
            # the first one's cancelled quantity, price and amount from 0).
            raise _RefusedError("rules", "unmeasured: a write on a line Bravo holds cancelled")
        if isinstance(command, CancelLine) and not is_empty(line.get("Divide")):
            # The traced cancel of a split group's first line also cleared
            # `Divide` by hand; what a person does there is not measured.
            raise _RefusedError("rules", "unmeasured: a cancel of a split line")
        group = ""
        if isinstance(command, SplitLine):
            _refuse_unmeasured_split(command, stored, line_index)
            group = group_label(stored, line_index)
        edits = typed_edits(command, group=group)
        insertable: Mapping[str, Sequence[str]] = {}
        new_line: dict[str, object] = {}
        if any(isinstance(e, AddRow) for e in edits):
            insertable, new_line = await self._new_line(kind, layout, stored)
        branch = str(stored.header.get("BranchCode") or "")
        session = await self.engine.session(user, branch, self.now())
        runner = RuleRunner(layout, self.engine.procedures(), self.engine.references(), session)
        doc = document_of(stored)
        tables = self.screens[kind.screen]
        try:
            runner.load(doc)
            added: list[int] = []
            for edit in edits:
                if isinstance(edit, AddRow):
                    columns = insertable[tables.table_for(edit.table)]
                    added.append(runner.add_row(doc, edit.table, new_line, stored=columns))
                    continue
                if edit.table == "Parent":
                    index = 0
                else:
                    index = line_index if edit.new_row is None else added[edit.new_row]
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
        return plan, tuple(warnings), refusal, insertable

    async def _new_line(
        self, kind: WriteKind, layout: Layout, stored: StoredDocument
    ) -> tuple[dict[str, Sequence[str]], dict[str, object]]:
        """What a line added to this screen's grid holds: every column of
        the view the layout loads it from, NULL but for the screen's traced
        `new_line` values; and the columns an INSERT of it may list (the
        view's that the table stores, less what the table generates)."""
        tables = self.screens[kind.screen]
        insertable: dict[str, Sequence[str]] = {}
        values: dict[str, object] = {}
        for key, table in tables.lines.items():
            spec = layout.tables.get(key)
            generated = stored.generated.get(table)
            unread = f"unmeasured: the columns a new line of {table} holds"
            try:
                view = list(await self.engine.view_columns(spec.name)) if spec is not None else []
            except UndecidableError as refused:
                # A layout `Name` the engine will not quote (`dbo.`, brackets).
                raise _RefusedError("rules", f"{unread}: {refused}") from None
            if not view or generated is None or table not in stored.column_order:
                raise _RefusedError("rules", unread)
            viewed = {c.lower() for c in view}
            insertable[table] = [
                c
                for c in stored.column_order[table]
                if c.lower() in viewed and c.lower() not in generated
            ]
            values = dict.fromkeys((c for c in view if c.lower() != "id"), None)
            values |= dict(tables.new_line)
        return insertable, values

    def _batch(
        self,
        kind: WriteKind,
        plan: SavePlan,
        stored: StoredDocument,
        user: BravoUser,
        insertable: Mapping[str, Sequence[str]],
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
                kind.screen,
                plan.commands,
                rows,
                stored.column_order,
                context=context,
                insertable=insertable,
                no_default=stored.no_default,
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
        """Every column written, read back: what Bravo holds must be what was
        planned. The new lines are the lines Bravo holds now and did not
        before, in the client's order. Bravo's trigger fills a new line's
        key column (`RowId`, written ''); one left '' would refuse every
        later line of every SO (`IX_B30BizDocDetailSO_RowId_Unique`), so it
        must read back filled."""
        try:
            after = await self.documents.load(kind.screen, doc_id)
        except (BravoUnavailableError, DocumentNotFoundError):
            return ("read_back_failed",)
        tables = self.screens[kind.screen]
        known = {line.get("Id") for line in before.lines}
        added = iter([line for line in after.lines if line.get("Id") not in known])
        differences: list[str] = []
        for written in plan.commands:
            key = ""
            if written.table == "Parent":
                row: dict[str, object] | None = after.header
            elif written.kind == "insert":
                row = next(added, None)
                key = tables.read_back_key[tables.table_for(written.table)]
                if row is not None and is_empty(row.get(key)):
                    differences.append(f"{written.table}#{written.row}.{key}: not filled")
            else:
                row = _row_by_id(after, before.lines[written.row]["Id"])
            if row is None:
                differences.append(f"{written.table}#{written.row}: row gone")
                continue
            lowered = {k.lower(): v for k, v in row.items()}
            for column, value in written.columns.items():
                if column.lower() in ("modifiedby", key.lower()):
                    continue
                if value is None:
                    # Written as DEFAULT, as the client does: the column's own
                    # default decides what Bravo holds (statements.render_update).
                    continue
                if not _same(_normal(lowered.get(column.lower())), _normal(value)):
                    differences.append(f"{written.table}#{written.row}.{column}")
        differences += [f"a line not planned: Id {line.get('Id')}" for line in added]
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


def group_label(stored: StoredDocument, line_index: int) -> str:
    """The label a split gives its group: the smallest positive number no
    other line uses as `GroupDivi`. The line's own label is not kept: a label
    left on a line that is not split marks no group (UAT trace 11-25: line 1
    held '2' with `Divide` 0, and the PIC's split labelled it '1'). PICs typed
    'A' (11-20) and '1' (11-25); Proterial's own convention is not known."""
    used = {
        str(line.get("GroupDivi")).strip()
        for i, line in enumerate(stored.lines)
        if i != line_index and not is_empty(line.get("GroupDivi"))
    }
    n = 1
    while str(n) in used:
        n += 1
    return str(n)


def _refuse_unmeasured_split(command: SplitLine, stored: StoredDocument, line_index: int) -> None:
    """A split no trace shows a person making is refused, before the approval
    is spent: of a line already in a group (it, or a line sharing its label,
    holds `Divide`); of a line other lines follow (where Bravo puts the new
    line, and whether it renumbers the rest, is not traced); with a
    confirmed date on a part (no traced split typed one: ticket 52's UAT
    split is to)."""
    line = stored.lines[line_index]
    label = str(line.get("GroupDivi") or "").strip()
    if not is_empty(line.get("Divide")) or any(
        label and not is_empty(other.get("Divide")) and str(other.get("GroupDivi")).strip() == label
        for other in stored.lines
    ):
        raise _RefusedError("rules", "unmeasured: a split of a line already in a split group")
    if line_index != len(stored.lines) - 1:
        raise _RefusedError("rules", "unmeasured: a split of a line other lines follow")
    if any(part.confirmed_date is not None for part in command.parts):
        raise _RefusedError("rules", "unmeasured: a confirmed date on a split part")


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
