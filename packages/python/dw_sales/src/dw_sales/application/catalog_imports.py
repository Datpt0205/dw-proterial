"""Sales' master data, imported from a file, previewed and approved (ticket 41).

Proterial keeps its customers, items, convert list, quotation master list and
monthly LME price in spreadsheets; DW1 read fictional copies of them
(`adapters/mock`). Business users now load and update these lists
themselves, and an approved import replaces the mock for that list, in that
workspace (`SnapshotSalesCatalog`). Nothing the file says is applied until a
second person approves it.

**Each import is a versioned snapshot** of one list (`CatalogSnapshot`): who
imported it and when (its ``as_of``), its ``source`` (``file`` now; ``erp``
when the same lists are synced from Bravo through another adapter, which
writes the same snapshot and walks the same approval), the file's name and
sha256, and what became of it:

- **queued**: uploaded (`CatalogImportService.upload`, `sales.master_data.import`;
  the quotation list also needs both price scopes, the LME list
  `sales.price.read`, since the preview shows them). The bytes are kept until
  they are read, and one outbox event, `sales.catalog.imported`, asks the
  worker to read them. **The API reads no customer file** (ticket 25): the
  worker scans the file (`MalwareScanPort`) and has the reader sandbox turn it
  into rows (`TableReaderPort`); `CatalogParsing.parse` then reads the rows as
  records (`dw_sales.domain.master_data.parse_rows`), checks what each names
  against the lists in force (a convert entry's customer and item), drops the
  bytes and writes the records. A new upload of the same list discards an
  open one that was not submitted yet.
- **parsed** (records to apply, rows rejected with row number and reason) or
  **failed** (nothing to apply, and why, in Vietnamese).
- **submitted**: a person holding the import scope sends it to be approved
  (`submit`), which opens a run-less platform approval, `sales.catalog`,
  stamped `sales.master_data.approve`, naming the importer and the submitter
  as its makers, the list, the file's name and sha256, the counts and the
  snapshot it was compared with: never a value of a row. Only one import of
  a list waits at a time.
- **approved** or **rejected** on the platform's approvals by the head, who is
  neither maker (the platform's strict `sales.` rule; `CatalogDecisions`, the
  decision guard, refuses a maker, a stamp other than the list's, a snapshot
  no longer waiting, and one compared with a list that has since changed; and
  `ck_catalog_snapshots_checker_not_maker` whatever writes the row). The
  worker carries out `sales.catalog.decided` (`CatalogSettlement`): an
  approved snapshot becomes the list in force and the one before it
  **superseded**, still readable.

Every step is audited in its transaction; the worker's read as itself
(`lane_audit_event`, `system:sales_catalog_import`).
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType, TracebackType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import (
    ConflictError,
    DomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    decided_event_type,
)
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import RunLessApprovalsPort
from dw_sales.application.malware import MalwareScanPort
from dw_sales.application.ports import SalesCatalogPort, SalesScope, Snapshot
from dw_sales.domain.catalog import ConvertEntry, LmeMonth, Quotation, month_key
from dw_sales.domain.master_data import (
    MAX_REJECTED_KEPT,
    SPECS,
    CatalogList,
    CatalogRecord,
    ChangedRow,
    DiffRow,
    ImportedTable,
    ListSpec,
    ParsedRecord,
    RejectedRow,
    diff,
    parse_rows,
    records_of,
)

logger = logging.getLogger("dw_sales.catalog_imports")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_catalog_snapshot"

# The platform approval a submission opens, and the event its decision is
# announced by. Under `sales.`, so the strict rule holds as for every Sales one.
CATALOG_APPROVAL: Final = "sales.catalog"
CATALOG_DECIDED: Final = decided_event_type(CATALOG_APPROVAL)
# What the upload announces, for the worker to read the file.
CATALOG_IMPORTED: Final = "sales.catalog.imported"
CATALOG_EVENT_SCHEMA: Final = "1.0.0"
# The worker's lane name for its audit rows (ADR 0011-a-background-lane-audits-as-itself).
CATALOG_IMPORT_LANE: Final = "sales_catalog_import"

# What one upload may be: far above a master list, small enough to keep in a
# row until the worker reads it.
MAX_IMPORT_BYTES: Final = 2 * 1024 * 1024
IMPORT_EXTENSIONS: Final = (".xlsx", ".xls", ".csv")
_FILE_NAME: Final = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")

ImportStatus = Literal[
    "queued", "parsed", "failed", "submitted", "approved", "rejected", "superseded", "discarded"
]
ImportSource = Literal["file", "erp"]
# What may still change: one of these per list per workspace at a time.
OPEN: Final = frozenset({"queued", "parsed", "submitted"})

# The scopes a list's preview also needs: its rows show prices.
_PRICED: Final[Mapping[CatalogList, tuple[SalesScopes, ...]]] = MappingProxyType(
    {
        CatalogList.QUOTATIONS: (SalesScopes.PRICE_READ, SalesScopes.PRICE_OTHER_CUSTOMERS_READ),
        CatalogList.LME: (SalesScopes.PRICE_READ,),
    }
)


class CatalogSnapshot(BaseModel):
    """One import of one list and what became of it (module docstring)."""

    model_config = _FROZEN

    snapshot_id: uuid.UUID
    catalog_list: CatalogList
    status: ImportStatus
    source: ImportSource
    file_name: str | None = Field(default=None, max_length=200)
    file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    file_size: int | None = Field(default=None, ge=1)
    imported_by: uuid.UUID
    imported_at: AwareDatetime
    # When the data holds: the moment it was imported.
    as_of: AwareDatetime
    error: str | None = Field(default=None, max_length=500)
    row_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    rejected: tuple[RejectedRow, ...] = ()
    unknown_headers: tuple[str, ...] = ()
    submitted_by: uuid.UUID | None = None
    submitted_at: AwareDatetime | None = None
    approval_id: uuid.UUID | None = None
    # The approved snapshot it was compared with when submitted; None: the mock.
    base_snapshot_id: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: AwareDatetime | None = None
    comment: str | None = Field(default=None, max_length=500)

    @property
    def makers(self) -> frozenset[uuid.UUID]:
        return frozenset(m for m in (self.imported_by, self.submitted_by) if m is not None)


# ------------------------------------------------------------------ ports --


class CatalogSnapshotStorePort(Protocol):
    """The workspace's snapshots inside a unit of work (RLS-bound)."""

    async def add(self, snapshot: CatalogSnapshot, content: bytes | None) -> None:
        """A new import, with the file's bytes to read. Refused with a
        conflict when the list already has an open one (`OPEN`)."""
        ...

    async def get(self, snapshot_id: uuid.UUID) -> CatalogSnapshot | None: ...

    async def open_for(self, catalog_list: CatalogList) -> CatalogSnapshot | None: ...

    async def approved(self, catalog_list: CatalogList) -> CatalogSnapshot | None: ...

    async def recent(self, catalog_list: CatalogList, limit: int) -> Sequence[CatalogSnapshot]:
        """The list's snapshots, newest imported first."""
        ...

    async def content(self, snapshot_id: uuid.UUID) -> bytes | None:
        """The bytes of a file not read yet; None once read or discarded."""
        ...

    async def update(self, snapshot: CatalogSnapshot, *, expected: ImportStatus) -> bool:
        """Writes ``snapshot``'s status and what goes with it, where the row
        is still ``expected``: False, and nothing written, otherwise."""
        ...

    async def write_records(
        self, snapshot_id: uuid.UUID, records: Sequence[tuple[str, Mapping[str, Any]]]
    ) -> None:
        """The parsed records, by key, in file order, and the bytes dropped."""
        ...

    async def records(self, snapshot_id: uuid.UUID) -> Sequence[Mapping[str, Any]]:
        """The snapshot's records, in file order."""
        ...


class OutboxPort(Protocol):
    """The platform's outbox, written in the unit of work's transaction."""

    async def add(self, event: OutboxEvent) -> None: ...


class CatalogUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def snapshots(self) -> CatalogSnapshotStorePort: ...

    @property
    def approvals(self) -> RunLessApprovalsPort: ...

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


class CatalogUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> CatalogUnitOfWork: ...


class TableUnreadableError(DomainError):
    """The reader read the file and found no table in it: the import's outcome."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason[:300], details={"reason_code": "table_unreadable"})
        self.reason = reason[:300]


class TableReaderPort(Protocol):
    """A file as rows of cells, read in the reader sandbox. Raises
    `TableUnreadableError` for a file that is not a table it reads, and an
    `InfrastructureError` when the sandbox does not answer."""

    async def read(self, data: bytes, file_name: str) -> ImportedTable: ...


class CatalogTemplatePort(Protocol):
    """A list's template: its columns, Vietnamese headers, and a guidance sheet."""

    def workbook(self, spec: ListSpec) -> bytes: ...


# ------------------------------------------------------------------ views --


class CatalogImportView(BaseModel):
    """An import as the page shows it: who, when, which file, how far."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: uuid.UUID
    catalog_list: CatalogList
    status: ImportStatus
    source: ImportSource
    file_name: str | None
    file_sha256: str | None
    imported_by: uuid.UUID
    imported_at: datetime
    as_of: datetime
    error: str | None
    row_count: int
    rejected_count: int
    submitted_by: uuid.UUID | None
    submitted_at: datetime | None
    # The platform approval it is decided on (`/approvals/{id}`).
    approval_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    comment: str | None


class CatalogInForceView(BaseModel):
    """Where a list's rows come from now: an approved snapshot, or the mock."""

    model_config = ConfigDict(frozen=True)

    source: Literal["mock", "file", "erp"]
    as_of: datetime
    snapshot: CatalogImportView | None


class CatalogListStateView(BaseModel):
    model_config = ConfigDict(frozen=True)

    catalog_list: CatalogList
    label: str
    in_force: CatalogInForceView
    # The one import that may still change (queued, parsed or submitted).
    open: CatalogImportView | None
    history: list[CatalogImportView]
    # Whether the caller may import this list and read its preview.
    can_import: bool


class CatalogStateView(BaseModel):
    model_config = ConfigDict(frozen=True)

    lists: list[CatalogListStateView]


class CatalogPreviewView(BaseModel):
    """A proposed snapshot against the list in force now: rows added,
    changed (old to new) and removed, and the rows the file had that will
    not be applied."""

    model_config = ConfigDict(frozen=True)

    snapshot: CatalogImportView
    compared_with: CatalogInForceView
    columns: list[str]
    added: list[DiffRow]
    changed: list[ChangedRow]
    removed: list[DiffRow]
    unchanged: int
    rejected: list[RejectedRow]
    rejected_count: int
    unknown_headers: list[str]


def import_view(snapshot: CatalogSnapshot) -> CatalogImportView:
    return CatalogImportView(
        snapshot_id=snapshot.snapshot_id,
        catalog_list=snapshot.catalog_list,
        status=snapshot.status,
        source=snapshot.source,
        file_name=snapshot.file_name,
        file_sha256=snapshot.file_sha256,
        imported_by=snapshot.imported_by,
        imported_at=snapshot.imported_at,
        as_of=snapshot.as_of,
        error=snapshot.error,
        row_count=snapshot.row_count,
        rejected_count=snapshot.rejected_count,
        submitted_by=snapshot.submitted_by,
        submitted_at=snapshot.submitted_at,
        approval_id=snapshot.approval_id,
        decided_by=snapshot.decided_by,
        decided_at=snapshot.decided_at,
        comment=snapshot.comment,
    )


class CatalogApprovalAsked(BaseModel):
    """The approval's payload: ids, the list, the file and the counts, never
    a row (the inbox serves the payload whole to whoever may decide it)."""

    model_config = _FROZEN

    approval_type: Literal["sales.catalog"]
    required_scope: str
    snapshot_id: uuid.UUID
    catalog_list: CatalogList
    label: str
    file_name: str | None
    file_sha256: str | None
    base_snapshot_id: uuid.UUID | None
    added: int = Field(ge=0)
    changed: int = Field(ge=0)
    removed: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    rejected: int = Field(ge=0)
    makers: tuple[uuid.UUID, ...]


async def current_records(
    catalog: SalesCatalogPort, scope: SalesScope, catalog_list: CatalogList
) -> Snapshot[Sequence[CatalogRecord]]:
    """One list whole, as DW1 reads it now: what a proposal is compared with."""
    found: Snapshot[Sequence[CatalogRecord]]
    match catalog_list:
        case CatalogList.CUSTOMERS:
            customers = await catalog.customers(scope)
            found = Snapshot(tuple(customers.data), customers.as_of)
        case CatalogList.ITEMS:
            items = await catalog.items(scope)
            found = Snapshot(tuple(items.data), items.as_of)
        case CatalogList.CONVERT_LIST:
            entries = await catalog.convert_list(scope)
            found = Snapshot(tuple(entries.data), entries.as_of)
        case CatalogList.QUOTATIONS:
            quotations = await catalog.quotations(scope)
            found = Snapshot(tuple(quotations.data), quotations.as_of)
        case CatalogList.LME:
            months = await catalog.lme_months(scope)
            found = Snapshot(tuple(months.data), months.as_of)
    return found


def _audit(
    ids: IdGenerator,
    clock: UtcClock,
    context: AccessContext,
    action: str,
    snapshot: CatalogSnapshot,
    **extra: object,
) -> AuditEvent:
    """The list, the snapshot's status, its file and counts: never a row."""
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type=_RESOURCE,
        resource_id=str(snapshot.snapshot_id),
        occurred_at=clock.now(),
        details=_details(snapshot) | extra,
    )


def _details(snapshot: CatalogSnapshot) -> dict[str, object]:
    details: dict[str, object] = {
        "catalog_list": snapshot.catalog_list.value,
        "status": snapshot.status,
        "source": snapshot.source,
        "rows": snapshot.row_count,
        "rejected": snapshot.rejected_count,
    }
    if snapshot.file_sha256 is not None:
        details["file_sha256"] = snapshot.file_sha256
    if snapshot.approval_id is not None:
        details["approval_id"] = str(snapshot.approval_id)
    return details


# ---------------------------------------------------------------- service --


@dataclass(frozen=True)
class CatalogImportService:
    """The page's side: state, templates, uploads, previews, submissions."""

    uow: CatalogUnitOfWorkFactory
    gate: Gate
    catalog: SalesCatalogPort
    templates: CatalogTemplatePort
    clock: UtcClock
    ids: IdGenerator

    async def _may_import(self, context: AccessContext, catalog_list: CatalogList) -> None:
        await self.gate.require(
            context,
            SalesScopes.MASTER_DATA_IMPORT,
            *_PRICED.get(catalog_list, ()),
            resource_type=_RESOURCE,
            resource_id=catalog_list.value,
        )

    def _can_import(self, context: AccessContext, catalog_list: CatalogList) -> bool:
        needed = (SalesScopes.MASTER_DATA_IMPORT, *_PRICED.get(catalog_list, ()))
        return all(self.gate.allows(context, scope) for scope in needed)

    async def state(self, context: AccessContext) -> CatalogStateView:
        """Where each list comes from now, its open import and its history.
        Counts and names only, so `sales.case.read` reads it."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        scope = sales_scope(context)
        lists: list[CatalogListStateView] = []
        for catalog_list, spec in SPECS.items():
            async with self.uow(scope) as work:
                approved = await work.snapshots.approved(catalog_list)
                opened = await work.snapshots.open_for(catalog_list)
                history = await work.snapshots.recent(catalog_list, 10)
            lists.append(
                CatalogListStateView(
                    catalog_list=catalog_list,
                    label=spec.label,
                    in_force=await self._in_force(scope, catalog_list, approved),
                    open=None if opened is None else import_view(opened),
                    history=[import_view(s) for s in history],
                    can_import=self._can_import(context, catalog_list),
                )
            )
        return CatalogStateView(lists=lists)

    async def _in_force(
        self, scope: SalesScope, catalog_list: CatalogList, approved: CatalogSnapshot | None
    ) -> CatalogInForceView:
        if approved is not None:
            return CatalogInForceView(
                source=approved.source, as_of=approved.as_of, snapshot=import_view(approved)
            )
        found = await current_records(self.catalog, scope, catalog_list)
        return CatalogInForceView(source="mock", as_of=found.as_of, snapshot=None)

    async def template(
        self, context: AccessContext, catalog_list: CatalogList
    ) -> tuple[bytes, str]:
        """The list's template workbook and the name to save it under."""
        await self._may_import(context, catalog_list)
        return self.templates.workbook(SPECS[catalog_list]), f"mau-{catalog_list.value}.xlsx"

    async def upload(
        self, context: AccessContext, catalog_list: CatalogList, file_name: str, data: bytes
    ) -> CatalogImportView:
        """A file to import: kept, queued for the worker to read (202)."""
        await self._may_import(context, catalog_list)
        name = file_name.strip()
        if not _FILE_NAME.match(name):
            raise DomainError("tên tệp không hợp lệ", details={"rule": "file_name"})
        if not name.casefold().endswith(IMPORT_EXTENSIONS):
            raise DomainError("chỉ nhận tệp .xlsx, .xls hoặc .csv", details={"rule": "file_type"})
        if not data:
            raise DomainError("tệp rỗng", details={"rule": "file_empty"})
        if len(data) > MAX_IMPORT_BYTES:
            raise DomainError(
                f"tệp lớn hơn {MAX_IMPORT_BYTES // (1024 * 1024)} MB", details={"rule": "file_size"}
            )
        now = self.clock.now()
        snapshot = CatalogSnapshot(
            snapshot_id=self.ids.new_uuid(),
            catalog_list=catalog_list,
            status="queued",
            source="file",
            file_name=name,
            file_sha256=hashlib.sha256(data).hexdigest(),
            file_size=len(data),
            imported_by=context.principal_id,
            imported_at=now,
            as_of=now,
        )
        async with self.uow(sales_scope(context)) as work:
            opened = await work.snapshots.open_for(catalog_list)
            if opened is not None:
                if opened.status == "submitted":
                    raise ConflictError(
                        "danh mục này đang có bản nhập chờ duyệt: chờ quyết định rồi nhập lại",
                        details={"snapshot_id": str(opened.snapshot_id), "rule": "import_waiting"},
                    )
                discarded = opened.model_copy(update={"status": "discarded"})
                if not await work.snapshots.update(discarded, expected=opened.status):
                    raise ConflictError(
                        "bản nhập trước vừa thay đổi, thử lại",
                        details={"snapshot_id": str(opened.snapshot_id)},
                    )
                await work.audit.append(
                    _audit(self.ids, self.clock, context, "sales.catalog.discarded", discarded)
                )
            await work.snapshots.add(snapshot, data)
            await work.outbox.add(
                OutboxEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    event_type=CATALOG_IMPORTED,
                    schema_version=CATALOG_EVENT_SCHEMA,
                    aggregate_id=snapshot.snapshot_id,
                    occurred_at=now,
                    payload={"snapshot_id": str(snapshot.snapshot_id)},
                    actor_id=context.principal_id,
                )
            )
            await work.audit.append(
                _audit(
                    self.ids,
                    self.clock,
                    context,
                    "sales.catalog.imported",
                    snapshot,
                    file_size=len(data),
                )
            )
            await work.commit()
        return import_view(snapshot)

    async def _readable(self, context: AccessContext, snapshot_id: uuid.UUID) -> CatalogSnapshot:
        """The snapshot, for a caller who may read its list's rows. Another
        workspace's is not found: RLS leaves it out of every read here."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        async with self.uow(sales_scope(context)) as work:
            snapshot = await work.snapshots.get(snapshot_id)
        if snapshot is None:
            raise NotFoundError("no such import", details={"snapshot_id": str(snapshot_id)})
        await self.gate.require(
            context,
            *_PRICED.get(snapshot.catalog_list, ()),
            resource_type=_RESOURCE,
            resource_id=str(snapshot_id),
        )
        return snapshot

    async def preview(self, context: AccessContext, snapshot_id: uuid.UUID) -> CatalogPreviewView:
        """The snapshot against the list in force now (module docstring)."""
        snapshot = await self._readable(context, snapshot_id)
        scope = sales_scope(context)
        catalog_list = snapshot.catalog_list
        async with self.uow(scope) as work:
            approved = await work.snapshots.approved(catalog_list)
            proposed = records_of(catalog_list, await work.snapshots.records(snapshot_id))
        current = await current_records(self.catalog, scope, catalog_list)
        in_force = await self._in_force(scope, catalog_list, approved)
        changes = (
            diff(catalog_list, (), ())
            if snapshot.status in ("queued", "failed", "discarded")
            else diff(catalog_list, current.data, proposed)
        )
        return CatalogPreviewView(
            snapshot=import_view(snapshot),
            compared_with=in_force,
            columns=[c.header for c in SPECS[catalog_list].columns],
            added=changes.added,
            changed=changes.changed,
            removed=changes.removed,
            unchanged=changes.unchanged,
            rejected=list(snapshot.rejected),
            rejected_count=snapshot.rejected_count,
            unknown_headers=list(snapshot.unknown_headers),
        )

    async def submit(self, context: AccessContext, snapshot_id: uuid.UUID) -> CatalogImportView:
        """Sends a parsed import to be approved (module docstring)."""
        async with self.uow(sales_scope(context)) as work:
            snapshot = await work.snapshots.get(snapshot_id)
        if snapshot is None:
            await self.gate.require(
                context, SalesScopes.MASTER_DATA_IMPORT, resource_type=_RESOURCE
            )
            raise NotFoundError("no such import", details={"snapshot_id": str(snapshot_id)})
        await self._may_import(context, snapshot.catalog_list)
        if snapshot.status != "parsed" or snapshot.row_count == 0:
            raise ConflictError(
                "chỉ gửi duyệt được bản nhập đã đọc xong và có dòng hợp lệ",
                details={
                    "snapshot_id": str(snapshot_id),
                    "status": snapshot.status,
                    "rule": "not_parsed",
                },
            )
        scope = sales_scope(context)
        catalog_list = snapshot.catalog_list
        current = await current_records(self.catalog, scope, catalog_list)
        now = self.clock.now()
        approval_id = self.ids.new_uuid()
        async with self.uow(scope) as work:
            approved = await work.snapshots.approved(catalog_list)
            proposed = records_of(catalog_list, await work.snapshots.records(snapshot_id))
            changes = diff(catalog_list, current.data, proposed)
            submitted = snapshot.model_copy(
                update={
                    "status": "submitted",
                    "submitted_by": context.principal_id,
                    "submitted_at": now,
                    "approval_id": approval_id,
                    "base_snapshot_id": None if approved is None else approved.snapshot_id,
                }
            )
            asked = CatalogApprovalAsked(
                approval_type="sales.catalog",
                required_scope=SalesScopes.MASTER_DATA_APPROVE.value,
                snapshot_id=snapshot_id,
                catalog_list=catalog_list,
                label=SPECS[catalog_list].label,
                file_name=snapshot.file_name,
                file_sha256=snapshot.file_sha256,
                base_snapshot_id=submitted.base_snapshot_id,
                rejected=snapshot.rejected_count,
                makers=tuple(sorted(submitted.makers, key=str)),
                **changes.counts,
            )
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=CATALOG_APPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=f"Danh mục {SPECS[catalog_list].label}: bản nhập chờ duyệt (ticket 41)",
                    payload=asked.model_dump(mode="json"),
                    required_scope=SalesScopes.MASTER_DATA_APPROVE.value,
                )
            )
            # After its approval: the row names it (`fk_catalog_snapshots_approval_requests`).
            if not await work.snapshots.update(submitted, expected="parsed"):
                raise ConflictError(
                    "bản nhập vừa thay đổi, tải lại trang",
                    details={"snapshot_id": str(snapshot_id)},
                )
            await work.audit.append(
                _audit(
                    self.ids,
                    self.clock,
                    context,
                    "sales.catalog.submitted",
                    submitted,
                    **changes.counts,
                )
            )
            await work.commit()
        return import_view(submitted)


# ------------------------------------------------------------ the parse --


@dataclass(frozen=True)
class CatalogParsing:
    """The worker's side of an upload: `CATALOG_IMPORTED`, carried out."""

    uow: CatalogUnitOfWorkFactory
    tables: TableReaderPort
    scanner: MalwareScanPort
    catalog: SalesCatalogPort
    clock: UtcClock
    ids: IdGenerator

    async def parse(self, scope: SalesScope, snapshot_id: uuid.UUID) -> str:
        """Reads one queued import; what it did, for the log. Idempotent: an
        import no longer queued (read already, or discarded) is left alone.
        Raises `InfrastructureError` when the scanner or the reader did not
        answer, so the outbox delivers it again."""
        async with self.uow(scope) as work:
            snapshot = await work.snapshots.get(snapshot_id)
            content = None if snapshot is None else await work.snapshots.content(snapshot_id)
        if snapshot is None or snapshot.status != "queued":
            return "import not queued"
        if content is None:
            records, settled = _failed(snapshot, "tệp không còn để đọc")
        else:
            records, settled = await self._read(scope, snapshot, content)
        async with self.uow(scope) as work:
            if not await work.snapshots.update(settled, expected="queued"):
                return "import changed meanwhile"
            await work.snapshots.write_records(
                snapshot_id,
                [(parsed.key, parsed.record.model_dump(mode="json")) for parsed in records],
            )
            await work.audit.append(
                lane_audit_event(
                    lane=CATALOG_IMPORT_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=f"sales.catalog.{settled.status}",
                    resource_type=_RESOURCE,
                    resource_id=str(snapshot_id),
                    occurred_at=self.clock.now(),
                    details=_details(settled) | {"imported_by": str(snapshot.imported_by)},
                )
            )
            await work.commit()
        return f"import {settled.status}"

    async def _read(
        self, scope: SalesScope, snapshot: CatalogSnapshot, content: bytes
    ) -> tuple[Sequence[ParsedRecord], CatalogSnapshot]:
        verdict = await self.scanner.scan(content)
        if verdict.outcome == "unavailable":
            raise InfrastructureError(
                "chưa quét được tệp, thử lại", details={"reason_code": "scanner_unavailable"}
            )
        if verdict.outcome == "infected":
            return _failed(snapshot, "tệp bị trình quét mã độc chặn")
        try:
            table = await self.tables.read(content, snapshot.file_name or "")
        except TableUnreadableError as unreadable:
            return _failed(snapshot, unreadable.reason)
        try:
            parsed = parse_rows(snapshot.catalog_list, table)
        except ValueError as refused:
            return _failed(snapshot, str(refused))
        kept, unknown = await self._references(scope, snapshot, parsed.records)
        rejected = sorted([*parsed.rejected, *unknown], key=lambda r: r.row)
        status: ImportStatus = "parsed" if kept else "failed"
        return kept, snapshot.model_copy(
            update={
                "status": status,
                "error": None if kept else "không có dòng hợp lệ để áp dụng",
                "row_count": len(kept),
                "rejected_count": len(rejected),
                "rejected": tuple(rejected[:MAX_REJECTED_KEPT]),
                "unknown_headers": parsed.unknown_headers,
            }
        )

    async def _references(
        self, scope: SalesScope, snapshot: CatalogSnapshot, records: Sequence[ParsedRecord]
    ) -> tuple[list[ParsedRecord], list[RejectedRow]]:
        """What a row names must be in the lists DW1 reads now, by exact code:
        a convert entry or a quotation names a customer and an item. An LME
        month after the import is refused: ``as_of`` claims the data held then."""
        kept: list[ParsedRecord] = []
        refused: list[RejectedRow] = []
        customers: dict[str, bool] = {}
        items: dict[str, bool] = {}
        last_month = month_key(snapshot.as_of.date())
        for parsed in records:
            record = parsed.record
            reason: tuple[str, str] | None = None
            if isinstance(record, ConvertEntry | Quotation):
                if record.customer_code not in customers:
                    found = await self.catalog.customer_by_code(scope, record.customer_code)
                    customers[record.customer_code] = found.data is not None
                if record.prv_code not in items:
                    item = await self.catalog.item_by_prv_code(scope, record.prv_code)
                    items[record.prv_code] = item.data is not None
                if not customers[record.customer_code]:
                    reason = (
                        "Mã khách hàng",
                        f"khách hàng {record.customer_code} chưa có trong danh mục khách hàng",
                    )
                elif not items[record.prv_code]:
                    reason = ("Mã PRV", f"mã {record.prv_code} chưa có trong danh mục mã hàng")
            if isinstance(record, LmeMonth) and record.month > last_month:
                reason = ("Tháng", "tháng sau thời điểm nhập")
            if reason is None:
                kept.append(parsed)
            else:
                refused.append(RejectedRow(row=parsed.row, column=reason[0], reason=reason[1]))
        return kept, refused


def _failed(
    snapshot: CatalogSnapshot, reason: str
) -> tuple[Sequence[ParsedRecord], CatalogSnapshot]:
    return (), snapshot.model_copy(
        update={"status": "failed", "error": reason[:500], "row_count": 0}
    )


# --------------------------------------------------------- the decision --


def _asked(request: ApprovalRequest) -> CatalogApprovalAsked:
    """The approval as a submission opened it, or a refusal: its payload
    unreadable, or stamped with a scope other than `sales.master_data.approve`
    (the column, which the platform's decision enforced)."""
    refused = ConflictError(
        "the approval is not one a master-data import opened",
        details={"approval_id": str(request.id)},
    )
    if request.approval_type != CATALOG_APPROVAL:
        raise refused
    try:
        asked = CatalogApprovalAsked.model_validate(request.payload)
    except ValidationError:
        raise refused from None
    if request.required_scope != SalesScopes.MASTER_DATA_APPROVE.value or (
        asked.required_scope != request.required_scope
    ):
        raise PermissionDeniedError(
            "a master-data import is decided with sales.master_data.approve",
            details={"approval_type": request.approval_type},
        )
    return asked


def _waiting(snapshot: CatalogSnapshot | None, request: ApprovalRequest) -> CatalogSnapshot:
    """The snapshot this approval was opened for, still waiting on it."""
    if snapshot is None:
        raise NotFoundError("no such import", details={"approval_id": str(request.id)})
    if snapshot.approval_id != request.id or snapshot.status != "submitted":
        raise ConflictError(
            "bản nhập không còn chờ quyết định này",
            details={
                "snapshot_id": str(snapshot.snapshot_id),
                "status": snapshot.status,
                "rule": "decision_stale",
            },
        )
    return snapshot


def _not_a_maker(snapshot: CatalogSnapshot, decider: uuid.UUID) -> None:
    """Maker and checker: whoever imported or submitted it does not decide it."""
    if decider in snapshot.makers:
        raise ConflictError(
            "tách nhiệm: người nhập hoặc gửi duyệt danh mục không tự quyết được",
            details={"snapshot_id": str(snapshot.snapshot_id), "rule": "maker_checker"},
        )


def _same_base(snapshot: CatalogSnapshot, approved: CatalogSnapshot | None) -> None:
    """Refuses approving a snapshot compared with a list that has changed
    since: the decider would apply a diff nobody saw."""
    current = None if approved is None else approved.snapshot_id
    if current != snapshot.base_snapshot_id:
        raise ConflictError(
            "danh mục đã có bản khác được duyệt sau khi bản này gửi: nhập lại để so sánh",
            details={"snapshot_id": str(snapshot.snapshot_id), "rule": "base_changed"},
        )


@dataclass(frozen=True)
class CatalogDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.catalog`: the
    decision as the snapshot would take it, refused or not, unwritten. Called
    after the decider's scope and the separation of duties, before it is
    recorded. A snapshot never changes after its parse, so a decision names
    no subject version."""

    uow: CatalogUnitOfWorkFactory

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = _asked(request)
        async with self.uow(sales_scope(context)) as work:
            snapshot = _waiting(await work.snapshots.get(asked.snapshot_id), request)
            approved = await work.snapshots.approved(snapshot.catalog_list)
        _not_a_maker(snapshot, context.principal_id)
        if decision.approve:
            _same_base(snapshot, approved)


@dataclass(frozen=True)
class CatalogSettlement:
    """Carries out a decided `sales.catalog` approval: the worker's handler
    for `CATALOG_DECIDED` calls it with the decider's tenancy and identity,
    from the event's envelope."""

    uow: CatalogUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> CatalogImportView:
        """The decision on the snapshot, as its decider, read from the
        approval row the decision wrote. Approved: the snapshot is the list in
        force, the one before it superseded. Idempotent: a redelivery finds
        it decided on this approval and writes nothing."""
        # Read as the decider holding the stamp the platform required of them.
        audience = ApprovalAudience(
            context=decider.model_copy(
                update={"scopes": frozenset({SalesScopes.MASTER_DATA_APPROVE.value})}
            ),
            holds_decide=True,
        )
        async with self.uow(sales_scope(decider)) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError(
                    "master-data approval not found", details={"approval_id": str(approval_id)}
                )
            asked = _asked(request)
            stored = await work.snapshots.get(asked.snapshot_id)
            if (
                stored is not None
                and stored.approval_id == request.id
                and stored.status in ("approved", "rejected", "superseded")
            ):
                return import_view(stored)
            submitted = _waiting(stored, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the master-data approval is not decided yet",
                    details={"approval_id": str(approval_id)},
                )
            _not_a_maker(submitted, decider.principal_id)
            approve = request.status is ApprovalStatus.APPROVED
            decision = await work.approvals.latest_decision(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            decided = submitted.model_copy(
                update={
                    "status": "approved" if approve else "rejected",
                    "decided_by": decider.principal_id,
                    "decided_at": self.clock.now(),
                    "comment": _reason(decision),
                }
            )
            if approve:
                approved = await work.snapshots.approved(submitted.catalog_list)
                _same_base(submitted, approved)
                if approved is not None:
                    superseded = approved.model_copy(update={"status": "superseded"})
                    if not await work.snapshots.update(superseded, expected="approved"):
                        raise ConflictError(
                            "the list in force changed meanwhile",
                            details={"snapshot_id": str(approved.snapshot_id)},
                        )
            if not await work.snapshots.update(decided, expected="submitted"):
                raise ConflictError(
                    "the import is decided already",
                    details={"snapshot_id": str(submitted.snapshot_id)},
                )
            action = "sales.catalog.approved" if approve else "sales.catalog.rejected"
            await work.audit.append(_audit(self.ids, self.clock, decider, action, decided))
            await work.commit()
        return import_view(decided)


def _reason(decision: ApprovalDecision | None) -> str | None:
    """The decider's comment as the snapshot keeps it (500 characters)."""
    comment = "" if decision is None else decision.comment.strip()
    if not comment:
        return None
    return comment if len(comment) <= 500 else comment[:499] + "…"
