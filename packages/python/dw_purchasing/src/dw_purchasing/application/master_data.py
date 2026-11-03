"""The company's lists loaded from a workbook: DW2's master-data page.

Who loads them is who configures DW2 (`purchasing.rules.propose`): they
download the template (`MasterTemplatePort`, one sheet per list), fill it in
Excel and upload it whole. Nothing is typed row by row, and nothing the file
says applies until a second person decides it:

- **queued**: uploaded (`MasterDataService.upload`). The API keeps the bytes
  and reads none of them (`CLAUDE.md`: a customer's file is parsed in a
  sandbox, never in the API); a newer upload forgets an open one.
- **parsed** or **failed**: the worker's `purchasing_master_import` lane
  (`MasterImportLane`) scans the file (`MalwareScanPort`, failing closed),
  has the reader sandbox turn each sheet into rows (`WorkbookReaderPort`),
  and `domain.master_lists.parse_workbook` decides what they mean. The bytes
  go once read; the lane audits as itself (ADR 0011).
- **submitted**: the person sends it to be decided (`submit`). The lists it
  holds replace those in force, the others are kept (`merge`), and the whole
  document goes through the one door every rule version takes
  (`PurchasingRulesService.propose`): the head's applies at once, anyone
  else's waits on a `purchasing.rules` approval the head decides. The page
  shows who decides it and what it changes (`ListChange`), never a price on
  the approval itself.

The lists in force are read by every check through `MasterDataPort`
(`adapters.master_data.RuleMasterData`): one version, the tenant's own or the
platform's empty one.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.malware import MalwareScanPort
from dw_platform.application.rule_versions import ContextScope, Layer
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.rules import (
    PurchasingRuleBook,
    PurchasingRuleKey,
    PurchasingRulesService,
    unused_version,
)
from dw_purchasing.domain.master_lists import (
    SHEETS,
    ListChange,
    ParsedWorkbook,
    Rejected,
    SheetRows,
    merge,
    parse_workbook,
)

MASTER_IMPORT_LANE: Final = "purchasing_master_import"
UPLOADED: Final = "purchasing.master_data.uploaded"
READ: Final = "purchasing.master_data.read"
SUBMITTED: Final = "purchasing.master_data.submitted"
_RESOURCE: Final = "purchasing_master_import"
# A plant's lists are far smaller; the route's body bound is this, as base64.
MAX_FILE_BYTES: Final = 10 * 1024 * 1024
# How long an import is remembered once read (`MasterImportLane.tick`).
KEEP_FOR: Final = timedelta(days=90)
_RECENT: Final = 10
# An `.xlsx` is a zip; an `.xls` an OLE2 compound file. Anything else is
# refused before it is kept; the sandbox still decides what it really is.
_WORKBOOK_MAGIC: Final = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
NOT_A_WORKBOOK: Final = "tệp phải là bảng tính Excel (.xlsx hoặc .xls) theo mẫu"
INFECTED: Final = "tệp bị chặn: phát hiện mã độc"

ImportStatus = Literal["queued", "parsed", "failed", "submitted"]


class MasterImport(BaseModel):
    """One uploaded workbook and what became of it (never its bytes)."""

    model_config = ConfigDict(frozen=True)

    import_id: uuid.UUID
    file_name: str
    sha256: str
    status: ImportStatus
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    read_at: datetime | None = None
    lists: dict[str, list[dict[str, object]]] | None = None
    rejected: list[Rejected] = []
    rejected_total: int = 0
    failure: str | None = None
    version_ref: str | None = None
    submitted_by: uuid.UUID | None = None
    submitted_at: datetime | None = None


class ListCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    list: str
    sheet: str
    rows: int


class MasterImportView(BaseModel):
    """An import as the page shows it: the file, how far it got, and, once
    read, what it would change beside the lists in force now."""

    model_config = ConfigDict(frozen=True)

    import_id: uuid.UUID
    file_name: str
    status: ImportStatus
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    read_at: datetime | None
    rejected: list[Rejected]
    rejected_total: int
    failure: str | None
    version_ref: str | None
    changes: list[ListChange]
    # Rows of the lists in force a file's removals take with them, by sheet.
    dropped: dict[str, int]
    # Why it cannot be sent now, in Vietnamese; None when it can.
    blocked: str | None


class MasterDataView(BaseModel):
    """The page: the lists in force and whose, the version waiting to be
    decided if any, and the latest uploads."""

    model_config = ConfigDict(frozen=True)

    ref: str
    layer: Layer
    lists: list[ListCount]
    waiting: str | None
    imports: list[MasterImportView]
    can_upload: bool


# ------------------------------------------------------------------ ports --


class MasterImportsPort(Protocol):
    """DW2's queue of uploaded workbooks, bound to the scope asked about."""

    async def add(self, record: MasterImport, content: bytes, event: AuditEvent) -> None:
        """A new upload, with its audit event, in one transaction; an import
        of the same workspace still queued or parsed is forgotten."""
        ...

    async def recent(self, scope: ContextScope, *, limit: int) -> Sequence[MasterImport]: ...

    async def get(self, scope: ContextScope, import_id: uuid.UUID) -> MasterImport | None: ...

    async def submitted(
        self, record: MasterImport, *, ref: str, by: uuid.UUID, at: datetime, event: AuditEvent
    ) -> bool:
        """Marks a parsed import sent as ``ref``; False when it is no longer
        parsed (sent already, or forgotten by a newer upload)."""
        ...

    async def queued(
        self, scope: ContextScope, *, limit: int
    ) -> Sequence[tuple[MasterImport, bytes]]:
        """Oldest first, the uploads not read yet, with their bytes."""
        ...

    async def read(
        self,
        scope: ContextScope,
        import_id: uuid.UUID,
        parsed: ParsedWorkbook,
        *,
        at: datetime,
        event: AuditEvent,
    ) -> None:
        """What the file said (or why it says nothing); its bytes forgotten."""
        ...

    async def forget(self, scope: ContextScope, *, read_before: datetime) -> int: ...


class WorkbookUnreadableError(DomainError):
    """The reader opened the file and found no workbook it reads."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason[:300], details={"reason_code": "workbook_unreadable"})
        self.reason = reason[:300]


class WorkbookReaderPort(Protocol):
    """A workbook's sheets as rows of cells, read in the reader sandbox, only
    the sheets ``wanted`` names. Raises `WorkbookUnreadableError` for a file
    it cannot read, `InfrastructureError` when the sandbox does not answer."""

    async def sheets(self, data: bytes, wanted: Sequence[str]) -> SheetRows: ...


class MasterTemplatePort(Protocol):
    """The workbook a person fills in: one sheet per list, its headers, an
    example row and a sheet that says how."""

    def workbook(self) -> bytes: ...


# --------------------------------------------------------------- the page --


@dataclass(frozen=True)
class MasterDataService:
    gate: Gate
    imports: MasterImportsPort
    rules: PurchasingRulesService
    book: PurchasingRuleBook
    template: MasterTemplatePort
    clock: UtcClock
    ids: IdGenerator

    async def overview(self, context: AccessContext) -> MasterDataView:
        """To who loads the lists and to who decides them."""
        await self._readers(context)
        scope = ContextScope.of(context)
        in_force, layer = await self.book.master_data(scope)
        waiting = await self.rules.waiting(context, PurchasingRuleKey.MASTER_DATA)
        recent = await self.imports.recent(scope, limit=_RECENT)
        return MasterDataView(
            ref=in_force.ref,
            layer=layer,
            lists=[
                ListCount(list=s.name, sheet=s.sheet, rows=len(getattr(in_force, s.name)))
                for s in SHEETS
            ],
            waiting=waiting,
            imports=[await self._view(scope, r, waiting) for r in recent],
            can_upload=self.gate.allows(context, PurchasingScopes.RULES_PROPOSE),
        )

    async def template_file(self, context: AccessContext) -> bytes:
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        return self.template.workbook()

    async def upload(self, context: AccessContext, file_name: str, data: bytes) -> MasterImportView:
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        if not data:
            raise DomainError("tệp rỗng", details={"rule": "empty_file"})
        if len(data) > MAX_FILE_BYTES:
            raise DomainError("tệp lớn hơn 10 MB", details={"rule": "file_too_large"})
        if not data.startswith(_WORKBOOK_MAGIC):
            raise DomainError(NOT_A_WORKBOOK, details={"rule": "not_a_workbook"})
        name = _file_name(file_name)
        record = MasterImport(
            import_id=self.ids.new_uuid(),
            file_name=name,
            sha256=hashlib.sha256(data).hexdigest(),
            status="queued",
            uploaded_by=context.principal_id,
            uploaded_at=self.clock.now(),
        )
        await self.imports.add(
            record,
            data,
            self._audit(context, UPLOADED, record, {"file_name": name, "sha256": record.sha256}),
        )
        return await self._view(ContextScope.of(context), record, None)

    async def get(self, context: AccessContext, import_id: uuid.UUID) -> MasterImportView:
        await self._readers(context)
        scope = ContextScope.of(context)
        record = await self.imports.get(scope, import_id)
        if record is None:
            raise NotFoundError("no such import")
        waiting = await self.rules.waiting(context, PurchasingRuleKey.MASTER_DATA)
        return await self._view(scope, record, waiting)

    async def submit(self, context: AccessContext, import_id: uuid.UUID) -> MasterImportView:
        """The file's lists over those in force, through the rules' one door."""
        await self.gate.require(context, PurchasingScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        scope = ContextScope.of(context)
        record = await self.imports.get(scope, import_id)
        if record is None:
            raise NotFoundError("no such import")
        if record.status != "parsed" or record.lists is None:
            raise ConflictError(
                "tệp này chưa đọc xong hoặc đã được gửi", details={"rule": "not_parsed"}
            )
        in_force, _ = await self.book.master_data(scope)
        version = await unused_version(
            self.book, scope, PurchasingRuleKey.MASTER_DATA.value, in_force.version
        )
        merged = merge(record.lists, in_force, version=version)
        proposed = await self.rules.propose(
            context, PurchasingRuleKey.MASTER_DATA.value, merged.document
        )
        ref = f"{PurchasingRuleKey.MASTER_DATA.value}@{proposed.version}"
        now = self.clock.now()
        marked = await self.imports.submitted(
            record,
            ref=ref,
            by=context.principal_id,
            at=now,
            event=self._audit(
                context,
                SUBMITTED,
                record,
                {
                    "version": ref,
                    "applied_directly": proposed.applied_directly,
                    "rows": {c.list: c.rows for c in merged.changes},
                },
            ),
        )
        if not marked:
            raise ConflictError("tệp này đã được gửi", details={"rule": "not_parsed"})
        sent = record.model_copy(
            update={
                "status": "submitted",
                "version_ref": ref,
                "submitted_by": context.principal_id,
                "submitted_at": now,
            }
        )
        return await self._view(scope, sent, None)

    async def _readers(self, context: AccessContext) -> None:
        await self.gate.require_any(
            context,
            PurchasingScopes.RULES_PROPOSE,
            PurchasingScopes.RULES_APPROVE,
            resource_type=_RESOURCE,
        )

    async def _view(
        self, scope: ContextScope, record: MasterImport, waiting: str | None
    ) -> MasterImportView:
        changes: list[ListChange] = []
        dropped: dict[str, int] = {}
        blocked: str | None = None
        if record.status == "parsed" and record.lists is not None:
            in_force, _ = await self.book.master_data(scope)
            try:
                merged = merge(record.lists, in_force, version=in_force.version)
            except ValueError:
                blocked = "danh sách trong tệp không còn khớp với danh sách đang dùng: tải lên lại"
            else:
                changes, dropped = merged.changes, merged.dropped
            if waiting is not None and blocked is None:
                blocked = f"đang chờ duyệt {waiting}: chờ quyết định xong rồi gửi"
        return MasterImportView(
            import_id=record.import_id,
            file_name=record.file_name,
            status=record.status,
            uploaded_by=record.uploaded_by,
            uploaded_at=record.uploaded_at,
            read_at=record.read_at,
            rejected=record.rejected,
            rejected_total=record.rejected_total,
            failure=record.failure,
            version_ref=record.version_ref,
            changes=changes,
            dropped=dropped,
            blocked=blocked if record.status == "parsed" else None,
        )

    def _audit(
        self,
        context: AccessContext,
        action: str,
        record: MasterImport,
        details: dict[str, object],
    ) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type=_RESOURCE,
            resource_id=str(record.import_id),
            occurred_at=self.clock.now(),
            details=details,
        )


def _file_name(raw: str) -> str:
    """The name as the page shows it: its last part, never a path."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (name or "tep-du-lieu-chu.xlsx")[:200]


# --------------------------------------------------------------- the lane --


@dataclass(frozen=True)
class MasterImportLane:
    """The worker's `purchasing_master_import` lane over one scope."""

    imports: MasterImportsPort
    reader: WorkbookReaderPort
    scanner: MalwareScanPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: ContextScope, *, limit: int = 5) -> int:
        """Reads what was uploaded, oldest first; forgets what was read long
        ago. A scanner or reader that does not answer leaves the file queued
        for the next tick (`InfrastructureError`), never read unscanned."""
        await self.imports.forget(scope, read_before=self.clock.now() - KEEP_FOR)
        done = 0
        for record, data in await self.imports.queued(scope, limit=limit):
            parsed = await self._read(data)
            now = self.clock.now()
            await self.imports.read(
                scope,
                record.import_id,
                parsed,
                at=now,
                event=lane_audit_event(
                    lane=MASTER_IMPORT_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=READ,
                    resource_type=_RESOURCE,
                    resource_id=str(record.import_id),
                    occurred_at=now,
                    details={
                        "outcome": "failed" if parsed.failure else "parsed",
                        "lists": sorted(parsed.lists),
                        "rejected": parsed.rejected_total,
                    },
                ),
            )
            done += 1
        return done

    async def _read(self, data: bytes) -> ParsedWorkbook:
        verdict = await self.scanner.scan(data)
        if verdict.outcome == "unavailable":
            raise InfrastructureError("chưa quét được mã độc tệp, thử lại", details={})
        if verdict.outcome == "infected":
            return _failed(INFECTED)
        try:
            sheets = await self.reader.sheets(data, [s.sheet for s in SHEETS])
        except WorkbookUnreadableError as unreadable:
            return _failed(unreadable.reason)
        return parse_workbook(sheets)


def _failed(reason: str) -> ParsedWorkbook:
    return ParsedWorkbook(lists={}, rejected=[], rejected_total=0, failure=reason)
