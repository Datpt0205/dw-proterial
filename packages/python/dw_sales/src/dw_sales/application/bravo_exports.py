"""A Bravo screen exported by a person, uploaded and read by the worker
(dw_sales tickets 16 and 03; ADR 0026).

Until the vendor's API reads Bravo, a person exports a screen to Excel and
uploads it here. **One path for every screen**: the upload
(`BravoExportService.upload`, refused while DW1 is paused) keeps the bytes
and writes one outbox event, `sales.bravo_export.uploaded`, in the same
transaction; the worker (`BravoExportReading.read`) scans the file
(`MalwareScanPort`), has the reader sandbox turn it into rows
(`TableReaderPort`), and hands them to the screen's reader, which reads them
by Bravo's own column titles (`domain.bravo_exports.find_header`) and says
what became of each document in it. The bytes are dropped with the outcome.
**The API reads no customer or Bravo file** (ticket 25).

Each screen has the scope a person needs to upload it and to see what
became of it (`SCREEN_SCOPES`, the one owner of that fact), and a reader
(`ScreenReader`) registered by screen in the worker: the YCBG (Design's
result, `ycbg_exports.YcbgScreen`, `sales.quote.prepare`) and the sales
orders read back after the paste (`bravo_sales_orders.SalesOrderScreen`,
`sales.order.prepare`). A reader records what it reads as the uploader,
resolved again when the file is read (a person who lost the scope since
records nothing), cut to that scope.

An upload drops the workspace's exports older than `KEPT_FOR` and fails
those still queued after `STALE_AFTER` (failure-modes #6).
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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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
from dw_sales.application.worker_service import require_running
from dw_sales.domain.bravo_exports import ImportedTable
from dw_sales.domain.master_data import RejectedRow

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_bravo_export"

# What an upload announces, for the worker to read the file.
BRAVO_EXPORT_UPLOADED: Final = "sales.bravo_export.uploaded"
BRAVO_EXPORT_EVENT_SCHEMA: Final = "1.0.0"
# What ticket 16's YCBG upload announced before every screen took this path:
# the same payload, so an event still queued from then reads the same row.
YCBG_EXPORT_UPLOADED_BEFORE: Final = "sales.ycbg_export.uploaded"
# Who the worker's audit rows are written as (`lane_audit_event`).
BRAVO_EXPORT_LANE: Final = "sales_bravo_exports"

MAX_EXPORT_BYTES: Final = 2 * 1024 * 1024
EXPORT_EXTENSIONS: Final = (".xlsx", ".csv")
_FILE_NAME: Final = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")
# How long an export's outcome is kept to look at, and how long one may stay
# queued: the worker reads one in a minute; one queued longer was lost.
KEPT_FOR: Final = timedelta(days=30)
STALE_AFTER: Final = timedelta(hours=1)
# How many exports the list shows, newest first.
LATEST: Final = 10

# The screens a person may upload. `ck_bravo_exports_screen` holds the same.
BravoScreen = Literal["ycbg", "sales_orders"]
# What a person needs to upload a screen and see what became of it; the
# worker reads it as the uploader cut to this.
SCREEN_SCOPES: Final[Mapping[BravoScreen, SalesScopes]] = MappingProxyType(
    {"ycbg": SalesScopes.QUOTE_PREPARE, "sales_orders": SalesScopes.ORDER_PREPARE}
)
ExportStatus = Literal["queued", "read", "failed"]
# What became of one document of an export. A YCBG: recorded, unchanged,
# pending, or (to Sales) no_case, lines_differ, changed, unreadable. A sales
# order read back: equal, differs, or (to Sales) no_case, several_cases,
# several_sos.
OutcomeKind = Literal[
    "recorded",
    "unchanged",
    "pending",
    "no_case",
    "lines_differ",
    "changed",
    "unreadable",
    "equal",
    "differs",
    "several_cases",
    "several_sos",
]
# A document's number as Bravo prints it: a customer's PO number may hold
# any printable character.
_PRINTED: Final = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")


class ExportOutcome(BaseModel):
    """What became of one document of an export: its number (a YCBG's, a
    customer PO's) and the case, never a value of the file."""

    model_config = _FROZEN

    key: str = Field(pattern=_PRINTED.pattern)
    outcome: OutcomeKind
    case_id: uuid.UUID | None = None
    # A recorded result that declines a line: Sales decides what the
    # customer is told (YCBG).
    declined: bool = False
    # How many differences a sales order read back has.
    differences: int = Field(default=0, ge=0)


class BravoExport(BaseModel):
    """One uploaded export and what became of it (module docstring)."""

    model_config = _FROZEN

    export_id: uuid.UUID
    screen: BravoScreen
    status: ExportStatus
    uploaded_by: uuid.UUID
    uploaded_at: AwareDatetime
    file_name: str = Field(max_length=200)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=1, le=MAX_EXPORT_BYTES)
    outcomes: tuple[ExportOutcome, ...] = ()
    rejected: tuple[RejectedRow, ...] = ()
    error: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------------ ports --


class ScreenReader(Protocol):
    """One screen's reading of an export's rows (module docstring)."""

    async def take(
        self, context: AccessContext, table: ImportedTable, *, file_sha256: str
    ) -> tuple[tuple[ExportOutcome, ...], tuple[RejectedRow, ...]]:
        """What became of each document the rows hold, and the rows that
        could not be read. Raises ValueError for a file the screen cannot read
        at all (a column missing), whose sentence names what it lacks."""
        ...


class BravoExportStorePort(Protocol):
    """The workspace's exports inside a unit of work (RLS-bound)."""

    async def add(self, export: BravoExport, content: bytes) -> None: ...

    async def get(self, export_id: uuid.UUID) -> BravoExport | None: ...

    async def latest(self, screen: BravoScreen, limit: int) -> Sequence[BravoExport]:
        """The screen's newest exports first."""
        ...

    async def content(self, export_id: uuid.UUID) -> bytes | None:
        """The bytes of a file not read yet; None once read."""
        ...

    async def settle(self, export: BravoExport) -> bool:
        """Writes ``export``'s outcome where the row is still queued, and drops
        its bytes: False, and nothing written, otherwise."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the exports uploaded before ``before``, with their bytes."""
        ...

    async def queued_before(self, before: datetime) -> Sequence[BravoExport]: ...


class BravoExportUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def bravo_exports(self) -> BravoExportStorePort: ...

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


class BravoExportUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> BravoExportUnitOfWork: ...


# ----------------------------------------------------------- the upload --


def _details(export: BravoExport) -> dict[str, object]:
    """Ids, counts and the file's hash: never a number or a value of the file."""
    counts: dict[str, int] = {}
    for outcome in export.outcomes:
        counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
    return {
        "screen": export.screen,
        "status": export.status,
        "file_sha256": export.file_sha256,
        "outcomes": counts,
        "rejected": len(export.rejected),
    }


def _failed(export: BravoExport, reason: str) -> BravoExport:
    return export.model_copy(update={"status": "failed", "error": reason[:500]})


_STALE_REASON: Final = "DW1 không đọc xong tệp trong 1 giờ: hãy tải lại tệp xuất từ Bravo"


@dataclass(frozen=True)
class BravoExportService:
    """Sales' side: upload an export, see what became of the latest."""

    uow: BravoExportUnitOfWorkFactory
    sales: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator

    async def upload(
        self, context: AccessContext, screen: BravoScreen, file_name: str, data: bytes
    ) -> BravoExport:
        """An export to read: kept, queued for the worker (202)."""
        await self.gate.require(context, SCREEN_SCOPES[screen], resource_type=_RESOURCE)
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
        export = BravoExport(
            export_id=self.ids.new_uuid(),
            screen=screen,
            status="queued",
            uploaded_by=context.principal_id,
            uploaded_at=now,
            file_name=name,
            file_sha256=hashlib.sha256(data).hexdigest(),
            file_size=len(data),
        )
        async with self.uow(scope) as work:
            await work.bravo_exports.prune(now - KEPT_FOR)
            for stale in await work.bravo_exports.queued_before(now - STALE_AFTER):
                await work.bravo_exports.settle(_failed(stale, _STALE_REASON))
            await work.bravo_exports.add(export, data)
            await work.outbox.add(
                OutboxEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    event_type=BRAVO_EXPORT_UPLOADED,
                    schema_version=BRAVO_EXPORT_EVENT_SCHEMA,
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
                    action="sales.bravo_export.uploaded",
                    resource_type=_RESOURCE,
                    resource_id=str(export.export_id),
                    occurred_at=now,
                    details=_details(export) | {"file_size": len(data)},
                )
            )
            await work.commit()
        return export

    async def latest(self, context: AccessContext, screen: BravoScreen) -> list[BravoExport]:
        """The workspace's latest exports of ``screen``, newest first.
        Another workspace's are not found: RLS leaves them out of every read."""
        await self.gate.require(context, SCREEN_SCOPES[screen], resource_type=_RESOURCE)
        async with self.uow(sales_scope(context)) as work:
            return list(await work.bravo_exports.latest(screen, LATEST))


# ---------------------------------------------------------- the reading --


@dataclass(frozen=True)
class BravoExportReading:
    """The worker's side of an upload: `BRAVO_EXPORT_UPLOADED`, carried out."""

    uow: BravoExportUnitOfWorkFactory
    tables: TableReaderPort
    scanner: MalwareScanPort
    access: RequesterAccessPort
    readers: Mapping[BravoScreen, ScreenReader]
    clock: UtcClock
    ids: IdGenerator

    async def read(self, scope: SalesScope, export_id: uuid.UUID) -> str:
        """Reads one queued export; what it did, for the log. Idempotent: an
        export no longer queued is left alone, and what a reader already
        recorded it reads as unchanged. Raises `InfrastructureError` when the
        scanner or the reader sandbox did not answer, so the outbox delivers
        it again."""
        async with self.uow(scope) as work:
            export = await work.bravo_exports.get(export_id)
            content = None if export is None else await work.bravo_exports.content(export_id)
        if export is None or export.status != "queued":
            return "export not queued"
        settled = (
            _failed(export, "tệp không còn để đọc")
            if content is None
            else await self._settle(scope, export, content)
        )
        async with self.uow(scope) as work:
            if not await work.bravo_exports.settle(settled):
                return "export changed meanwhile"
            await work.audit.append(
                lane_audit_event(
                    lane=BRAVO_EXPORT_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=f"sales.bravo_export.{settled.status}",
                    resource_type=_RESOURCE,
                    resource_id=str(export_id),
                    occurred_at=self.clock.now(),
                    details=_details(settled) | {"uploaded_by": str(export.uploaded_by)},
                )
            )
            await work.commit()
        return f"export {settled.status}"

    async def _settle(self, scope: SalesScope, export: BravoExport, content: bytes) -> BravoExport:
        reader = self.readers.get(export.screen)
        if reader is None:
            return _failed(export, "màn Bravo này chưa đọc được")
        verdict = await self.scanner.scan(content)
        if verdict.outcome == "unavailable":
            raise InfrastructureError(
                "chưa quét được tệp, thử lại", details={"reason_code": "scanner_unavailable"}
            )
        if verdict.outcome == "infected":
            return _failed(export, "tệp bị trình quét mã độc chặn")
        context = await self._uploader(scope, export, SCREEN_SCOPES[export.screen])
        if context is None:
            return _failed(export, "người tải tệp không còn quyền đọc màn Bravo này")
        try:
            table = await self.tables.read(content, export.file_name)
        except TableUnreadableError as refused:
            return _failed(export, refused.reason)
        try:
            outcomes, rejected = await reader.take(context, table, file_sha256=export.file_sha256)
        except ConflictError as refused:
            if refused.details.get("rule") == "worker_paused":
                return _failed(export, refused.message)
            raise
        except ValueError as refused:
            # A column missing (`MissingColumnsError` names each), or one
            # titled twice.
            return _failed(export, str(refused))
        return export.model_copy(
            update={"status": "read", "outcomes": outcomes, "rejected": rejected}
        )

    async def _uploader(
        self, scope: SalesScope, export: BravoExport, needed: SalesScopes
    ) -> AccessContext | None:
        """Who uploaded, as the platform resolves them now, cut to what the
        screen needs; None when they may no longer read it here."""
        ceiling = frozenset({needed.value})
        access = await self.access.find_linked_access(
            export.uploaded_by, scope.tenant_id.value, scope.workspace_id.value, ceiling
        )
        if access is None:
            return None
        context = context_from(access)
        if sales_scope(context) != scope or not context.scopes >= ceiling:
            return None
        return context
