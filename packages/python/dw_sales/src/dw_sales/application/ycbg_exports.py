"""Design's result on a YCBG, read back from Bravo (dw_sales ticket 16).

Design writes its result on the YCBG's lines in Bravo: QUOTE with the BP code,
or DECLINE with a reason, and the line's status goes CLOSE (Box B16). DW1
reads it; it never writes Bravo, and the status is Design's to close.

**Where it is read from** is `BravoYcbgPort`: the vendor's API reading a
request back by number (R13) once it exists; until then the YCBG screen
exported to Excel by a person (`ExportedYcbg`). `DesignChecks.take` matches
what either source says, and does not know which it was.

**Matched by the YCBG number alone**, as a Design reply by mail is
(`QuotationService.awaiting_reply`): the one case of the workspace waiting on
Design under that number, whose lines are exactly the YCBG's lines. Anything
else goes to Sales and onto no case (`no_case`, `lines_differ`, `changed`,
`unreadable`): a number no open request holds is never matched to the
nearest one. A YCBG with a line still PENDING is not Design's answer yet.
What is recorded moves no status (`QuoteCase.record_design_check`).

**The export, queued** (`YcbgExportService.upload`, `sales.quote.prepare`,
refused while DW1 is paused): the bytes are kept until they are read, and one
outbox event, `sales.ycbg_export.uploaded`, asks the worker to read them.
**The API reads no customer or Bravo file** (ticket 25): the worker
(`YcbgExportReading.read`) scans the file (`MalwareScanPort`), has the reader
sandbox turn it into rows (`TableReaderPort`), reads them by the column
titles below, records each result as the uploader (resolved again now: a
person who lost the scope since records nothing), and drops the bytes with
the outcome. An upload drops the workspace's exports older than `KEPT_FOR`
and fails those still queued after `STALE_AFTER` (failure-modes #6).

**The columns are Bravo's own** (`COLUMNS`), as its "RFQ List" export titles
them (Box B16, seen 11-14; spec Q-B13): read by the one reader of Bravo's
exports (`domain.bravo_exports.find_header`), by title, never by position; a
file without one of them is refused naming it. That export leaves the line's
"Số thứ tự" blank on every row, so a request's lines are numbered in the
order the export lists them under its number, and each line's customer item
description must be the request's own for that line: a line Sales entered
in another order, or worded otherwise, goes to Sales (`lines_differ`), never
onto a guessed line.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType, TracebackType
from typing import Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import context_from
from dw_platform.application.malware import MalwareScanPort
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.catalog_imports import OutboxPort, TableReaderPort, TableUnreadableError
from dw_sales.application.ports import SalesScope
from dw_sales.application.processing import RequesterAccessPort
from dw_sales.application.quote_ports import QuoteCaseLookupPort
from dw_sales.application.support import person_event, save_quote
from dw_sales.application.worker_service import require_running
from dw_sales.domain.bravo_exports import (
    CellValue,
    ExportColumn,
    ImportedTable,
    TableRow,
    find_header,
    header_key,
)
from dw_sales.domain.master_data import RejectedRow
from dw_sales.domain.quotes import (
    YCBG_NO_PATTERN,
    DesignCheck,
    DesignCheckLine,
    DesignVerdict,
    QuoteStatus,
    RfqDocument,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_ycbg_export"

# What an upload announces, for the worker to read the file.
YCBG_EXPORT_UPLOADED: Final = "sales.ycbg_export.uploaded"
YCBG_EXPORT_EVENT_SCHEMA: Final = "1.0.0"
# Who the worker's audit rows are written as (`lane_audit_event`).
YCBG_EXPORT_LANE: Final = "sales_ycbg_exports"
# Who the reading acts as: the uploader, cut to this.
_CEILING: Final = frozenset({SalesScopes.QUOTE_PREPARE.value})

MAX_EXPORT_BYTES: Final = 2 * 1024 * 1024
EXPORT_EXTENSIONS: Final = (".xlsx", ".csv")
_FILE_NAME: Final = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")
# How long an export's outcome is kept to look at, and how long one may stay
# queued: the worker reads one in a minute; one queued longer was lost.
KEPT_FOR: Final = timedelta(days=30)
STALE_AFTER: Final = timedelta(hours=1)
# How many exports the list shows, newest first.
LATEST: Final = 10

ExportStatus = Literal["queued", "read", "failed"]
YcbgLineStatus = Literal["pending", "close"]

# Bravo's YCBG lines as its "RFQ List" export titles them (Box B16), and as
# the YCBG screen's own grid does (11-10): one column per field.
COLUMNS: Final[Mapping[str, ExportColumn]] = MappingProxyType(
    {
        "ycbg_no": ExportColumn("RFQ No", aliases=("Số chứng từ",)),
        # Blank in the export; numbered by order then (module docstring).
        "line_no": ExportColumn("Số thứ tự/ No.", aliases=("Số thứ tự", "STT"), required=False),
        "description": ExportColumn(
            "Mô tả của KH/Customer item description",
            aliases=("Customer item description", "Mô tả của KH"),
        ),
        "status": ExportColumn("Status", aliases=("Trạng thái",)),
        "design_check": ExportColumn("Design check"),
        "reason": ExportColumn("Decline reason", aliases=("Lý do",)),
        "bp_code": ExportColumn("Base price code", aliases=("Mã BP", "BP Code")),
    }
)
# Bravo's own values of a line's status and Design Check (Box 11-10, B16),
# compared without case or spacing.
_STATUSES: Final[Mapping[str, YcbgLineStatus]] = MappingProxyType(
    {"pending": "pending", "close": "close"}
)
_VERDICTS: Final[Mapping[str, DesignVerdict]] = MappingProxyType(
    {"quote": "quote", "decline": "decline"}
)

# What became of one YCBG number. The last four go to Sales: no result is put
# on a case for them.
OutcomeKind = Literal[
    "recorded", "unchanged", "pending", "no_case", "lines_differ", "changed", "unreadable"
]
TO_SALES: Final = frozenset({"no_case", "lines_differ", "changed", "unreadable"})
_PRINTED: Final = re.compile(r"^[!-~]{1,64}$")


# ------------------------------------------------------------------ data --


class BravoYcbgLine(BaseModel):
    """One YCBG line as Bravo holds it: what `BravoYcbgPort` answers. The
    number is as Bravo prints it, in any shape: a number no case holds goes
    to Sales, so it need not be one Sales could record."""

    model_config = _FROZEN

    ycbg_no: str = Field(pattern=_PRINTED.pattern)
    line_no: int = Field(ge=1, le=9999)
    status: YcbgLineStatus
    verdict: DesignVerdict | None = None
    bp_code: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=1000)
    # The customer's item description, as Sales entered it from DW1's draft:
    # what tells which of the request's lines it is.
    description: str | None = Field(default=None, max_length=1000)


class YcbgOutcome(BaseModel):
    """What became of one YCBG number of a read: names the number and the
    case, never a value of Design's result."""

    model_config = _FROZEN

    ycbg_no: str = Field(pattern=_PRINTED.pattern)
    outcome: OutcomeKind
    case_id: uuid.UUID | None = None
    # A recorded result that declines a line: Sales decides what the
    # customer is told.
    declined: bool = False


class YcbgExport(BaseModel):
    """One uploaded export and what became of it (module docstring)."""

    model_config = _FROZEN

    export_id: uuid.UUID
    status: ExportStatus
    uploaded_by: uuid.UUID
    uploaded_at: AwareDatetime
    file_name: str = Field(max_length=200)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=1, le=MAX_EXPORT_BYTES)
    outcomes: tuple[YcbgOutcome, ...] = ()
    rejected: tuple[RejectedRow, ...] = ()
    error: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------------ ports --


class BravoYcbgPort(Protocol):
    """Bravo's YCBG lines, as Bravo holds them (module docstring). Read only."""

    async def ycbg_lines(self, scope: SalesScope) -> Sequence[BravoYcbgLine]: ...


@dataclass(frozen=True, slots=True)
class ExportedYcbg:
    """`BravoYcbgPort` over one export a person uploaded: its lines as read."""

    lines: tuple[BravoYcbgLine, ...]

    async def ycbg_lines(self, scope: SalesScope) -> Sequence[BravoYcbgLine]:
        return self.lines


class YcbgExportStorePort(Protocol):
    """The workspace's exports inside a unit of work (RLS-bound)."""

    async def add(self, export: YcbgExport, content: bytes) -> None: ...

    async def get(self, export_id: uuid.UUID) -> YcbgExport | None: ...

    async def latest(self, limit: int) -> Sequence[YcbgExport]:
        """The newest exports first."""
        ...

    async def content(self, export_id: uuid.UUID) -> bytes | None:
        """The bytes of a file not read yet; None once read."""
        ...

    async def settle(self, export: YcbgExport) -> bool:
        """Writes ``export``'s outcome where the row is still queued, and drops
        its bytes: False, and nothing written, otherwise."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the exports uploaded before ``before``, with their bytes."""
        ...

    async def queued_before(self, before: datetime) -> Sequence[YcbgExport]: ...


class YcbgExportUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def ycbg_exports(self) -> YcbgExportStorePort: ...

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


class YcbgExportUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> YcbgExportUnitOfWork: ...


# --------------------------------------------------------- reading a table --


class ParsedExport(BaseModel):
    """An export's rows as YCBG lines, and the rows that could not be read."""

    model_config = _FROZEN

    lines: tuple[BravoYcbgLine, ...]
    rejected: tuple[RejectedRow, ...]


def _text(cell: CellValue) -> str | None:
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)
    text = str(cell).strip()
    return text or None


def _line_no(cell: CellValue) -> int | None:
    text = _text(cell)
    if text is None:
        return None
    if not text.isdigit():
        raise ValueError("line_no")
    return int(text)


def _closed(cell: CellValue, values: Mapping[str, str], field: str) -> str | None:
    """One of Bravo's own values of the field, or None for a blank cell."""
    text = _text(cell)
    if text is None:
        return None
    found = values.get(header_key(text))
    if found is None:
        raise ValueError(field)
    return found


def parse_export(table: ImportedTable) -> ParsedExport:
    """The export's YCBG lines, by Bravo's column titles (`COLUMNS`). Raises
    `MissingColumnsError` naming a column the file does not title. A row
    whose values cannot be read is rejected, naming the column and never the
    value; so is every row of a request whose lines are numbered on some rows
    and not on others. A request whose rows are all unnumbered has its lines
    numbered in the order listed (module docstring)."""
    header = find_header(table.rows, tuple(COLUMNS.values()))
    by_number: dict[str, list[tuple[TableRow, dict[str, object]]]] = {}
    rejected: list[RejectedRow] = []
    for row in table.rows[header.index + 1 :]:
        cells = {field: header.cell(row, column) for field, column in COLUMNS.items()}
        number = _text(cells["ycbg_no"])
        if number is None:
            # A row naming no request (Bravo's "Tổng cộng:" under the lines)
            # is not a YCBG line.
            continue
        try:
            fields: dict[str, object] = {
                "ycbg_no": number,
                "line_no": _line_no(cells["line_no"]),
                "status": _closed(cells["status"], _STATUSES, "status") or "",
                "verdict": _closed(cells["design_check"], _VERDICTS, "design_check"),
                "bp_code": _text(cells["bp_code"]),
                "reason": _text(cells["reason"]),
                "description": _text(cells["description"]),
            }
        except ValueError as refused:
            rejected.append(_rejected(row.row, str(refused)))
            continue
        by_number.setdefault(number, []).append((row, fields))
    lines: list[BravoYcbgLine] = []
    for rows in by_number.values():
        numbered = [fields["line_no"] is not None for _, fields in rows]
        if any(numbered) and not all(numbered):
            rejected.extend(_rejected(row.row, "line_no") for row, _ in rows)
            continue
        for order, (row, fields) in enumerate(rows, start=1):
            try:
                lines.append(
                    BravoYcbgLine.model_validate(
                        fields if fields["line_no"] is not None else fields | {"line_no": order}
                    )
                )
            except ValidationError as refused:
                errors = refused.errors()
                rejected.append(_rejected(row.row, str(errors[0]["loc"][0]) if errors else None))
    return ParsedExport(lines=tuple(lines), rejected=tuple(sorted(rejected, key=lambda r: r.row)))


def _rejected(row: int, field: str | None) -> RejectedRow:
    column = COLUMNS[field].header if field is not None and field in COLUMNS else None
    return RejectedRow(row=row, column=column, reason="không đọc được giá trị của cột này")


# ------------------------------------------------- matching Design's result --


_YCBG_NO: Final = re.compile(YCBG_NO_PATTERN)


def _check_lines(lines: Sequence[BravoYcbgLine]) -> tuple[DesignCheckLine, ...] | None:
    """Design's result on each line, once every line is closed with one;
    None when a line is not, or states a result that is not a result."""
    try:
        return tuple(
            DesignCheckLine(
                line_no=line.line_no,
                verdict=line.verdict,
                bp_code=line.bp_code if line.verdict == "quote" else None,
                reason=line.reason,
            )
            for line in sorted(lines, key=lambda line: line.line_no)
            if line.verdict is not None
        )
    except ValidationError:
        return None


def _words(text: str) -> str:
    return " ".join(text.split()).casefold()


def _same_lines(lines: Sequence[BravoYcbgLine], document: RfqDocument) -> bool:
    """Bravo's lines are exactly the request's: the same numbers, and each
    line the customer's own words for it (spacing and case aside). A line
    whose description Bravo does not give is not known to be the request's."""
    if {line.line_no for line in lines} != document.line_numbers():
        return False
    return all(
        line.description is not None
        and _words(line.description) == _words(document.item(line.line_no).description.value)
        for line in lines
    )


@dataclass(frozen=True)
class DesignChecks:
    """Design's results, matched to the cases waiting on them (module docstring)."""

    uow: SalesUnitOfWorkFactory
    cases: QuoteCaseLookupPort
    clock: UtcClock
    ids: IdGenerator

    async def take(
        self, context: AccessContext, source: BravoYcbgPort, *, file_sha256: str
    ) -> tuple[YcbgOutcome, ...]:
        """What became of each YCBG number ``source`` holds, in the order it
        first names them; each result recorded as ``context``, the person who
        brought it in, in a transaction of its own."""
        scope = sales_scope(context)
        by_number: dict[str, list[BravoYcbgLine]] = {}
        for line in await source.ycbg_lines(scope):
            by_number.setdefault(line.ycbg_no, []).append(line)
        return tuple(
            [
                await self._one(context, scope, number, lines, file_sha256)
                for number, lines in by_number.items()
            ]
        )

    async def _one(
        self,
        context: AccessContext,
        scope: SalesScope,
        number: str,
        lines: Sequence[BravoYcbgLine],
        file_sha256: str,
    ) -> YcbgOutcome:
        if any(line.status != "close" for line in lines):
            return YcbgOutcome(ycbg_no=number, outcome="pending")
        checked = _check_lines(lines)
        numbers = [line.line_no for line in lines]
        if checked is None or len(checked) != len(lines) or len(set(numbers)) != len(numbers):
            return YcbgOutcome(ycbg_no=number, outcome="unreadable")
        if not _YCBG_NO.fullmatch(number):
            # No case can hold a number of another shape (`record_ycbg`).
            return YcbgOutcome(ycbg_no=number, outcome="no_case")
        found = await self.cases.cases_for_ycbg(scope, number)
        for case in found:
            if case.design_check is not None and case.design_check.lines == checked:
                return YcbgOutcome(
                    ycbg_no=number,
                    outcome="unchanged",
                    case_id=case.case_id,
                    declined=case.design_check.declined,
                )
        waiting = [case for case in found if case.status is QuoteStatus.SENT_TO_DESIGN]
        if len(waiting) != 1:
            return YcbgOutcome(ycbg_no=number, outcome="no_case")
        (case,) = waiting
        if not _same_lines(lines, case.request.document):
            return YcbgOutcome(ycbg_no=number, outcome="lines_differ", case_id=case.case_id)
        if case.design_check is not None:
            return YcbgOutcome(ycbg_no=number, outcome="changed", case_id=case.case_id)
        now = self.clock.now()
        check = DesignCheck(
            ycbg_no=number,
            lines=checked,
            file_sha256=file_sha256,
            read_by=context.principal_id,
            read_at=now,
        )
        async with self.uow(scope) as work:
            await require_running(work)
            stored = await work.quotes.get(case.case_id)
            if stored is None or stored.case.case_version != case.case_version:
                # Moved meanwhile: read again with the next upload.
                return YcbgOutcome(ycbg_no=number, outcome="changed", case_id=case.case_id)
            after = stored.case.record_design_check(check)
            event = person_event("quote.design_checked", context, now)
            await save_quote(work, context, self.ids, stored.case, after, event)
            await work.commit()
        return YcbgOutcome(
            ycbg_no=number, outcome="recorded", case_id=case.case_id, declined=check.declined
        )


# ----------------------------------------------------------- the upload --


def _details(export: YcbgExport) -> dict[str, object]:
    """Ids, counts and the file's hash: never a number or a value of the file."""
    counts: dict[str, int] = {}
    for outcome in export.outcomes:
        counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
    return {
        "status": export.status,
        "file_sha256": export.file_sha256,
        "outcomes": counts,
        "rejected": len(export.rejected),
    }


def _failed(export: YcbgExport, reason: str) -> YcbgExport:
    return export.model_copy(update={"status": "failed", "error": reason[:500]})


_STALE_REASON: Final = "DW1 không đọc xong tệp trong 1 giờ: hãy tải lại tệp xuất từ Bravo"


@dataclass(frozen=True)
class YcbgExportService:
    """Sales' side: upload an export, see what became of the latest."""

    uow: YcbgExportUnitOfWorkFactory
    sales: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator

    async def upload(self, context: AccessContext, file_name: str, data: bytes) -> YcbgExport:
        """An export to read: kept, queued for the worker (202)."""
        await self.gate.require(context, SalesScopes.QUOTE_PREPARE, resource_type=_RESOURCE)
        name = file_name.strip()
        if not _FILE_NAME.match(name):
            raise DomainError("tên tệp không hợp lệ", details={"rule": "file_name"})
        if not name.casefold().endswith(EXPORT_EXTENSIONS):
            raise DomainError("chỉ nhận tệp .xlsx hoặc .csv", details={"rule": "file_type"})
        if not data:
            raise DomainError("tệp rỗng", details={"rule": "file_empty"})
        if len(data) > MAX_EXPORT_BYTES:
            raise DomainError(
                f"tệp lớn hơn {MAX_EXPORT_BYTES // (1024 * 1024)} MB", details={"rule": "file_size"}
            )
        scope = sales_scope(context)
        async with self.sales(scope) as work:
            await require_running(work)
        now = self.clock.now()
        export = YcbgExport(
            export_id=self.ids.new_uuid(),
            status="queued",
            uploaded_by=context.principal_id,
            uploaded_at=now,
            file_name=name,
            file_sha256=hashlib.sha256(data).hexdigest(),
            file_size=len(data),
        )
        async with self.uow(scope) as work:
            await work.ycbg_exports.prune(now - KEPT_FOR)
            for stale in await work.ycbg_exports.queued_before(now - STALE_AFTER):
                await work.ycbg_exports.settle(_failed(stale, _STALE_REASON))
            await work.ycbg_exports.add(export, data)
            await work.outbox.add(
                OutboxEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    event_type=YCBG_EXPORT_UPLOADED,
                    schema_version=YCBG_EXPORT_EVENT_SCHEMA,
                    aggregate_id=export.export_id,
                    occurred_at=now,
                    payload={"export_id": str(export.export_id)},
                    actor_id=context.principal_id,
                )
            )
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.ycbg_export.uploaded",
                    resource_type=_RESOURCE,
                    resource_id=str(export.export_id),
                    occurred_at=now,
                    details=_details(export) | {"file_size": len(data)},
                )
            )
            await work.commit()
        return export

    async def latest(self, context: AccessContext) -> list[YcbgExport]:
        """The workspace's latest exports, newest first. Another workspace's
        are not found: RLS leaves them out of every read here."""
        await self.gate.require(context, SalesScopes.QUOTE_PREPARE, resource_type=_RESOURCE)
        async with self.uow(sales_scope(context)) as work:
            return list(await work.ycbg_exports.latest(LATEST))


# ---------------------------------------------------------- the reading --


@dataclass(frozen=True)
class YcbgExportReading:
    """The worker's side of an upload: `YCBG_EXPORT_UPLOADED`, carried out."""

    uow: YcbgExportUnitOfWorkFactory
    tables: TableReaderPort
    scanner: MalwareScanPort
    access: RequesterAccessPort
    checks: DesignChecks
    clock: UtcClock
    ids: IdGenerator

    async def read(self, scope: SalesScope, export_id: uuid.UUID) -> str:
        """Reads one queued export; what it did, for the log. Idempotent: an
        export no longer queued is left alone, and a result already on its
        case is `unchanged`. Raises `InfrastructureError` when the scanner or
        the reader did not answer, so the outbox delivers it again."""
        async with self.uow(scope) as work:
            export = await work.ycbg_exports.get(export_id)
            content = None if export is None else await work.ycbg_exports.content(export_id)
        if export is None or export.status != "queued":
            return "export not queued"
        settled = (
            _failed(export, "tệp không còn để đọc")
            if content is None
            else await self._settle(scope, export, content)
        )
        async with self.uow(scope) as work:
            if not await work.ycbg_exports.settle(settled):
                return "export changed meanwhile"
            await work.audit.append(
                lane_audit_event(
                    lane=YCBG_EXPORT_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=f"sales.ycbg_export.{settled.status}",
                    resource_type=_RESOURCE,
                    resource_id=str(export_id),
                    occurred_at=self.clock.now(),
                    details=_details(settled) | {"uploaded_by": str(export.uploaded_by)},
                )
            )
            await work.commit()
        return f"export {settled.status}"

    async def _settle(self, scope: SalesScope, export: YcbgExport, content: bytes) -> YcbgExport:
        verdict = await self.scanner.scan(content)
        if verdict.outcome == "unavailable":
            raise InfrastructureError(
                "chưa quét được tệp, thử lại", details={"reason_code": "scanner_unavailable"}
            )
        if verdict.outcome == "infected":
            return _failed(export, "tệp bị trình quét mã độc chặn")
        context = await self._uploader(scope, export)
        if context is None:
            return _failed(export, "người tải tệp không còn quyền chuẩn bị báo giá")
        try:
            table = await self.tables.read(content, export.file_name)
        except TableUnreadableError as refused:
            return _failed(export, refused.reason)
        try:
            parsed = parse_export(table)
        except ValueError as refused:
            # `MissingColumnsError` names each column; a column titled twice.
            return _failed(export, str(refused))
        try:
            outcomes = await self.checks.take(
                context, ExportedYcbg(parsed.lines), file_sha256=export.file_sha256
            )
        except ConflictError as refused:
            if refused.details.get("rule") == "worker_paused":
                return _failed(export, refused.message)
            raise
        return export.model_copy(
            update={"status": "read", "outcomes": outcomes, "rejected": parsed.rejected}
        )

    async def _uploader(self, scope: SalesScope, export: YcbgExport) -> AccessContext | None:
        """Who uploaded, as the platform resolves them now, cut to the
        ceiling; None when they may no longer prepare quotations here."""
        access = await self.access.find_linked_access(
            export.uploaded_by, scope.tenant_id.value, scope.workspace_id.value, _CEILING
        )
        if access is None:
            return None
        context = context_from(access)
        if sales_scope(context) != scope or not context.scopes >= _CEILING:
            return None
        return context
