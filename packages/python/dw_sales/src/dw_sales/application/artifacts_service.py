"""Rendering and downloading a case's artifacts: the effect boundary until ticket 10.

A person uploads the file to Bravo or sends the draft, so the download is the
step the runtime's approval would otherwise guard (dw_sales ADR 0001). Each
download checks, in order: `sales.case.read`; the case in the caller's
workspace (404 otherwise, another tenant's included); the artifact belongs to
that case; `sales.price.read` for a price-bearing kind (403); the state gate
per kind below (409 before its state); and that the artifact was rendered at
the case's current version, the version every decision so far was made on
(409 otherwise: an edit since then made it stale, and it is rendered again).
The bytes served are the ones whose sha256 the record holds.

Rendering takes the kind's write scope (`sales.order.prepare` or
`sales.quote.prepare`) besides the same checks, and the version the caller
was looking at. It composes the files from the case alone (`order_artifacts`,
`quote_artifacts`), stores them under a key the server derives,
``{tenant}/{workspace}/sales/{case}/{artifact}`` in the bucket offboarding
exports and purges by the tenant's prefix, and records each with its template
``id@version``, case version and sha256. Rendering a kind again at the same
version returns what is stored. Both steps are audited, with ids and hashes
and never an amount (spec decision 8).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

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
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import EML, PDF, XLSX, ArtifactWriterPort
from dw_sales.application.case_store import (
    ArtifactRecord,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.drafting import ArtifactCopy, Drafting, People, Rendered
from dw_sales.application.order_artifacts import (
    OrderDrafting,
    bravo_upload,
    cannot_supply_draft,
    change_summary,
    confirmation_draft,
    convert_list_proposal,
    correction_request,
    cross_check_sheet,
    design_code_request,
    portal_checklist,
)
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    SalesCatalogPort,
    SalesScope,
)
from dw_sales.application.quote_artifacts import (
    DesignRequestSource,
    decline_draft,
    design_request_draft,
    master_list_update,
    quotation_final,
    quotation_preview,
    send_draft,
    spec_discussion_draft,
    ycbg_draft,
)
from dw_sales.application.support import same_version, stored_order, stored_quote
from dw_sales.domain.catalog import ConfirmationChannel, Customer
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import (
    CloseReason,
    FindingCode,
    MappingStatus,
    OrderCase,
    OrderStatus,
)
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

_O = OrderStatus
_Q = QuoteStatus

type Compose[CaseT] = Callable[
    [Drafting[CaseT], DesignRequestSource], Awaitable[tuple[Rendered, ...]]
]


@dataclass(frozen=True, slots=True)
class ArtifactGate[CaseT]:
    """When a kind may be rendered and downloaded, and how it is composed.

    ``channel``: offered only to a customer who confirms orders that way.
    """

    price_bearing: bool
    open_in: Callable[[CaseT, AccessContext, Gate], bool]
    compose: Compose[CaseT]
    channel: ConfirmationChannel | None = None


def _order(compose: Callable[[OrderDrafting], tuple[Rendered, ...]]) -> Compose[OrderCase]:
    async def composed(d: OrderDrafting, _: DesignRequestSource) -> tuple[Rendered, ...]:
        return compose(d)

    return composed


def _unmapped_without_code(case: OrderCase, *_: object) -> bool:
    unmapped = {f.line_no for f in case.findings if f.code is FindingCode.CODE_UNMAPPED}
    return any(
        line.line_no in unmapped
        and line.mapping.status is MappingStatus.UNMAPPED
        and not line.mapping.candidates
        for line in case.lines
    )


# Once prepared, the upload file holds while the order is in Bravo; a return
# from the cross-check reopens the self-check, and a revision of an order in
# Bravo is a change applied there (`change_summary`), never a new upload file.
_UPLOADABLE: Final = frozenset({_O.PREPARED, _O.UPLOADED_TO_BRAVO, _O.CROSS_CHECKED, _O.CONFIRMED})

# Ticket 06's "Download allowed when", one row per kind. The confirmation is
# drafted once Sales confirmed a date for every line (`confirmed`): the dates
# are entered with the confirmation, so a draft at `cross_checked` could not
# carry them.
ORDER_GATES: Final[Mapping[str, ArtifactGate[OrderCase]]] = {
    "bravo_upload": ArtifactGate(True, lambda c, *_: c.status in _UPLOADABLE, _order(bravo_upload)),
    "cross_check_sheet": ArtifactGate(
        True, lambda c, *_: c.status is _O.UPLOADED_TO_BRAVO, _order(cross_check_sheet)
    ),
    "confirmation_draft": ArtifactGate(
        True, lambda c, *_: c.status is _O.CONFIRMED, _order(confirmation_draft), "email"
    ),
    "portal_checklist": ArtifactGate(
        True, lambda c, *_: c.status is _O.CONFIRMED, _order(portal_checklist), "portal"
    ),
    "correction_request": ArtifactGate(
        True, lambda c, *_: c.status is _O.CORRECTION_REQUESTED, _order(correction_request)
    ),
    "change_summary": ArtifactGate(
        True, lambda c, *_: c.status is _O.CHANGE_REVIEW, _order(change_summary)
    ),
    "convert_list_proposal": ArtifactGate(
        False,
        lambda c, *_: any(
            line.mapping.status is MappingStatus.CANDIDATE_CONFIRMED for line in c.lines
        ),
        _order(convert_list_proposal),
    ),
    "design_code_request": ArtifactGate(False, _unmapped_without_code, _order(design_code_request)),
    "cannot_supply_draft": ArtifactGate(
        False,
        lambda c, *_: c.close_reason is CloseReason.CANNOT_SUPPLY,
        _order(cannot_supply_draft),
    ),
}

_BEFORE_YCBG = frozenset({_Q.RECEIVED, _Q.DECLINED})


def _pricer_or_approver(case: QuoteCase, context: AccessContext, gate: Gate) -> bool:
    pricer = case.pricing.decided_by if case.pricing else None
    return context.principal_id == pricer or gate.allows(context, SalesScopes.QUOTE_APPROVE)


QUOTE_GATES: Final[Mapping[str, ArtifactGate[QuoteCase]]] = {
    "ycbg_draft": ArtifactGate(False, lambda c, *_: c.status not in _BEFORE_YCBG, ycbg_draft),
    "design_request_draft": ArtifactGate(
        False,
        lambda c, *_: c.status not in _BEFORE_YCBG | {_Q.YCBG_DRAFTED},
        design_request_draft,
    ),
    "spec_discussion_draft": ArtifactGate(
        False, lambda c, *_: c.status is _Q.SPEC_DISCUSSION, spec_discussion_draft
    ),
    "decline_draft": ArtifactGate(False, lambda c, *_: c.status is _Q.DECLINED, decline_draft),
    "quotation_preview": ArtifactGate(
        True,
        lambda c, ctx, gate: c.status is _Q.PENDING_APPROVAL and _pricer_or_approver(c, ctx, gate),
        quotation_preview,
    ),
    # The final document holds while approved; it is rendered only from a
    # document whose hash the approval names (`quote_artifacts._approval`).
    "quotation_final": ArtifactGate(True, lambda c, *_: c.status is _Q.APPROVED, quotation_final),
    "send_draft": ArtifactGate(True, lambda c, *_: c.status is _Q.APPROVED, send_draft),
    "master_list_update": ArtifactGate(True, lambda c, *_: c.status is _Q.SENT, master_list_update),
}

ORDER_KINDS: Final = frozenset(ORDER_GATES)
QUOTE_KINDS: Final = frozenset(QUOTE_GATES)

_EXTENSIONS: Final[Mapping[str, str]] = {XLSX: ".xlsx", PDF: ".pdf", EML: ".eml"}
_VIEW = ConfigDict(frozen=True)


class ArtifactView(BaseModel):
    """One stored file: what the approval view shows beside it (template,
    case version, hash), and whether this caller may download it now."""

    model_config = _VIEW

    artifact_id: uuid.UUID
    kind: str
    case_version: int
    template_ref: str
    sha256: str
    content_type: str
    size_bytes: int
    file_name: str
    created_by: uuid.UUID
    created_at: datetime
    downloadable: bool


class ArtifactListView(BaseModel):
    model_config = _VIEW

    case_version: int
    # The kinds this caller may render and download at this version.
    available: list[str]
    artifacts: list[ArtifactView]


def file_name(record: ArtifactRecord) -> str:
    """Kind and case, never a value from the file (ui-quality §6)."""
    return f"{record.kind}-{record.case_id}{_EXTENSIONS.get(record.content_type, '')}"


@dataclass(frozen=True, slots=True)
class Download:
    record: ArtifactRecord
    data: bytes

    @property
    def file_name(self) -> str:
        return file_name(self.record)


class _Case(Protocol):
    @property
    def case_id(self) -> uuid.UUID: ...

    @property
    def case_version(self) -> int: ...

    @property
    def customer_code(self) -> str: ...

    @property
    def status(self) -> StrEnum: ...


@dataclass(frozen=True, slots=True)
class _Cases[CaseT: _Case]:
    """What differs between orders and quotes here: the table, how a case is
    read, and the scope rendering takes."""

    kind: CaseKind
    gates: Mapping[str, ArtifactGate[CaseT]]
    load: Callable[[SalesUnitOfWork, uuid.UUID], Awaitable[CaseT]]
    write_scope: SalesScopes


async def _load_order(work: SalesUnitOfWork, case_id: uuid.UUID) -> OrderCase:
    return (await stored_order(work, case_id)).case


async def _load_quote(work: SalesUnitOfWork, case_id: uuid.UUID) -> QuoteCase:
    return (await stored_quote(work, case_id)).case


_ORDERS: Final = _Cases(CaseKind.ORDER, ORDER_GATES, _load_order, SalesScopes.ORDER_PREPARE)
_QUOTES: Final = _Cases(CaseKind.QUOTE, QUOTE_GATES, _load_quote, SalesScopes.QUOTE_PREPARE)


@dataclass(frozen=True)
class ArtifactService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    storage: ArtifactBytesPort
    clock: UtcClock
    ids: IdGenerator
    writer: ArtifactWriterPort
    copy: ArtifactCopy
    catalog: SalesCatalogPort
    directory: MemberDirectoryPort
    design: DesignRequestSource

    # ------------------------------------------------------------- orders --

    async def order_artifacts(self, context: AccessContext, case_id: uuid.UUID) -> ArtifactListView:
        return await self._list(_ORDERS, context, case_id)

    async def render_order(
        self, context: AccessContext, case_id: uuid.UUID, *, kind: str, case_version: int
    ) -> list[ArtifactView]:
        return await self._render(_ORDERS, context, case_id, kind, case_version)

    async def order_artifact(
        self, context: AccessContext, case_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> Download:
        return await self._download(_ORDERS, context, case_id, artifact_id)

    # ------------------------------------------------------------- quotes --

    async def quote_artifacts(self, context: AccessContext, case_id: uuid.UUID) -> ArtifactListView:
        return await self._list(_QUOTES, context, case_id)

    async def render_quote(
        self, context: AccessContext, case_id: uuid.UUID, *, kind: str, case_version: int
    ) -> list[ArtifactView]:
        return await self._render(_QUOTES, context, case_id, kind, case_version)

    async def quote_artifact(
        self, context: AccessContext, case_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> Download:
        return await self._download(_QUOTES, context, case_id, artifact_id)

    # ------------------------------------------------------------ the work --

    async def _list[CaseT: _Case](
        self, cases: _Cases[CaseT], context: AccessContext, case_id: uuid.UUID
    ) -> ArtifactListView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type="sales_artifact", resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = await cases.load(work, case_id)
            records = await work.artifacts.for_case(cases.kind, case_id)
        channel = None
        if any(gate.channel is not None for gate in cases.gates.values()):
            channel = (await self._customer(scope, case.customer_code)).confirmation_channel
        available = sorted(
            kind
            for kind, gate in cases.gates.items()
            if self._may(context, gate, case) and gate.channel in (None, channel)
        )
        return ArtifactListView(
            case_version=case.case_version,
            available=available,
            artifacts=[
                _view(
                    record,
                    downloadable=record.case_version == case.case_version
                    and record.kind in cases.gates
                    and self._may(context, cases.gates[record.kind], case),
                )
                for record in records
            ],
        )

    async def _render[CaseT: _Case](
        self,
        cases: _Cases[CaseT],
        context: AccessContext,
        case_id: uuid.UUID,
        kind: str,
        case_version: int,
    ) -> list[ArtifactView]:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            cases.write_scope,
            resource_type="sales_artifact",
            resource_id=str(case_id),
        )
        gate = cases.gates.get(kind)
        if gate is None:
            raise DomainError("no such artifact kind", details={"field": "kind"})
        self._price(context, gate.price_bearing, kind=kind)
        scope, now = sales_scope(context), self.clock.now()
        async with self.uow(scope) as work:
            case = await cases.load(work, case_id)
            same_version(case_id, case.case_version, case_version)
            if not gate.open_in(case, context, self.gate):
                raise _closed(kind, case.status.value)
            current = [
                record
                for record in await work.artifacts.for_case(cases.kind, case_id)
                if record.kind == kind and record.case_version == case.case_version
            ]
            if not current:
                drafting = Drafting(
                    case=case,
                    case_version=case.case_version,
                    customer=await self._customer(scope, case.customer_code),
                    people=People(
                        {m.user_id: m for m in await self.directory.list_members(context)}
                    ),
                    drafter=context.principal_id,
                    at=now,
                    copy=self.copy,
                    writer=self.writer,
                    scope=scope,
                )
                for rendered in await gate.compose(drafting, self.design):
                    record = self._record(cases.kind, case, kind, rendered, context, now)
                    await self.storage.put_object(
                        record.object_key(scope), rendered.data, rendered.content_type
                    )
                    await work.artifacts.add(record)
                    await work.audit.append(_audit(context, self.ids, record, "rendered", now))
                    current.append(record)
                await work.commit()
        return [_view(record, downloadable=True) for record in current]

    async def _download[CaseT: _Case](
        self,
        cases: _Cases[CaseT],
        context: AccessContext,
        case_id: uuid.UUID,
        artifact_id: uuid.UUID,
    ) -> Download:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type="sales_artifact",
            resource_id=str(artifact_id),
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = await cases.load(work, case_id)
            record = _belongs(
                await work.artifacts.get(artifact_id), cases.kind, case_id, artifact_id
            )
            gate = cases.gates.get(record.kind)
            self._price(context, gate is None or gate.price_bearing, kind=record.kind)
            if gate is None or not gate.open_in(case, context, self.gate):
                raise _closed(record.kind, case.status.value, artifact_id=artifact_id)
            if record.case_version != case.case_version:
                raise ConflictError(
                    "tài liệu được tạo từ một phiên bản hồ sơ cũ: tạo lại để tải bản mới",
                    details={
                        "artifact_id": str(artifact_id),
                        "kind": record.kind,
                        "artifact_case_version": record.case_version,
                        "case_version": case.case_version,
                        "reason": "stale_artifact",
                    },
                )
            data = await self.storage.get_object(record.object_key(scope))
            if hashlib.sha256(data).hexdigest() != record.sha256:
                raise InfrastructureError(
                    "tệp lưu trữ không khớp mã băm đã ghi",
                    details={"artifact_id": str(artifact_id), "reason": "sha256_mismatch"},
                )
            await work.audit.append(
                _audit(context, self.ids, record, "downloaded", self.clock.now())
            )
            await work.commit()
        return Download(record, data)

    # ------------------------------------------------------------ helpers --

    def _may[CaseT](self, context: AccessContext, gate: ArtifactGate[CaseT], case: CaseT) -> bool:
        return gate.open_in(case, context, self.gate) and (
            not gate.price_bearing or self.gate.allows(context, SalesScopes.PRICE_READ)
        )

    def _price(self, context: AccessContext, price_bearing: bool, *, kind: str) -> None:
        if price_bearing and not self.gate.allows(context, SalesScopes.PRICE_READ):
            raise PermissionDeniedError(
                "this artifact carries prices: it needs sales.price.read",
                details={"action": SalesScopes.PRICE_READ.value, "kind": kind},
            )

    async def _customer(self, scope: SalesScope, code: str) -> Customer:
        customer = (await self.catalog.customer_by_code(scope, code)).data
        if customer is None:
            raise ConflictError(
                "khách hàng của hồ sơ không có trong dữ liệu gốc",
                details={"customer_code": code, "reason": "customer_unknown"},
            )
        return customer

    def _record(
        self,
        kind: CaseKind,
        case: _Case,
        artifact_kind: str,
        rendered: Rendered,
        context: AccessContext,
        at: datetime,
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=self.ids.new_uuid(),
            case_kind=kind,
            case_id=case.case_id,
            case_version=case.case_version,
            kind=artifact_kind,
            template_ref=rendered.template_ref,
            sha256=rendered.sha256,
            content_type=rendered.content_type,
            size_bytes=len(rendered.data),
            created_by=context.principal_id,
            created_at=at,
        )


def _view(record: ArtifactRecord, *, downloadable: bool) -> ArtifactView:
    return ArtifactView(
        artifact_id=record.artifact_id,
        kind=record.kind,
        case_version=record.case_version,
        template_ref=record.template_ref,
        sha256=record.sha256,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        file_name=file_name(record),
        created_by=record.created_by,
        created_at=record.created_at,
        downloadable=downloadable,
    )


def _audit(
    context: AccessContext, ids: IdGenerator, record: ArtifactRecord, what: str, at: datetime
) -> AuditEvent:
    """Ids, the template, the version and the hash: never a value from the file."""
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=f"sales.artifact.{what}",
        resource_type="sales_artifact",
        resource_id=str(record.artifact_id),
        occurred_at=at,
        details={
            "case_kind": record.case_kind.value,
            "case_id": str(record.case_id),
            "case_version": record.case_version,
            "kind": record.kind,
            "template_ref": record.template_ref,
            "sha256": record.sha256,
        },
    )


def _belongs(
    record: ArtifactRecord | None, kind: CaseKind, case_id: uuid.UUID, artifact_id: uuid.UUID
) -> ArtifactRecord:
    """The artifact, when it is this case's; another case's reads as none."""
    if record is None or (record.case_kind, record.case_id) != (kind, case_id):
        raise NotFoundError(
            "the case has no such artifact",
            details={"case_id": str(case_id), "artifact_id": str(artifact_id)},
        )
    return record


def _closed(kind: str, status: str, *, artifact_id: uuid.UUID | None = None) -> ConflictError:
    """An artifact asked for outside its state; a kind with no gate is never served."""
    details: dict[str, object] = {"kind": kind, "status": status}
    if artifact_id is not None:
        details["artifact_id"] = str(artifact_id)
    return ConflictError(
        "this artifact is not available in the case's current state", details=details
    )
