"""`/api/v1/sales/*`: thin routes over the Sales services.

The composition root hands in the services and two of its own dependencies:
the verified access context and the `Idempotency-Key` operation. This package
names neither implementation (it may not import the app).

- **Every route depends on the verified access context**, through
  `_services`: the tenant and workspace come from it and from nothing a
  request carries. A route-inventory test asserts it for every path here.
- **A scope a route needs is checked before anything else**: before the case
  is read, and, on a mutation, before the idempotency key is claimed, so a
  replay never answers a caller who may not make the request. The service
  checks again where the change happens.
- **Every mutation takes `case_version`** (409 when stale) and honours
  `Idempotency-Key`, and answers with ids only (`CaseChangeView`): the
  response the idempotency store keeps holds no amount.
- **FPT support reads five routes, and only these** (dw_sales ADR 0003 §5,
  ADR 0024): the overview and the order and quote lists and details take
  ``support_access_context``, which also admits a support staff member under a
  customer's grant. The composition root lists the same five in
  `SUPPORT_ALLOWED_ROUTES`; every other route refuses a support context. The
  grant carries no price scope, so `PriceView` marks every amount hidden.
- **No data source configured** (a deployed profile without the demo tenant):
  every route answers 503 "chưa cấu hình nguồn dữ liệu".
- **No decision of a checker is made here.** Approving or returning a
  quotation and cross-checking or returning an order are decisions on a
  platform approval (`POST /api/v1/approvals/{id}/decisions`), which DW1's
  run pauses on and applies (dw_sales ADR 0004). The routes that raise them
  (`submit`, `bravo-entry`, `resend-cross-check`) start a DW1 run
  (`svc.dw1`); "DW xử lý" queues one for the worker (`svc.processing`, 202).
"""

# No `from __future__ import annotations` here: the routes annotate their
# parameters with aliases built inside `build_router` from the dependencies
# the app hands in, and FastAPI resolves a string annotation against the
# module's globals, where those aliases do not exist.

import base64
import binascii
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import DomainError, InfrastructureError
from dw_kernel.pagination import MAX_PAGE_SIZE, Page
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import SalesScopes
from dw_sales.application.artifacts_service import ArtifactListView, ArtifactView, Download
from dw_sales.application.assignment import AssigneeView
from dw_sales.application.catalog_imports import (
    CatalogImportView,
    CatalogPreviewView,
    CatalogStateView,
)
from dw_sales.application.layouts import LayoutPreviewView, LayoutSourceView, LayoutView
from dw_sales.application.overview_service import WORK_PAGE, OverviewView, WorkItem
from dw_sales.application.quotation import ScreeningRow
from dw_sales.application.quotes_service import PricedLine
from dw_sales.application.rules import RuleKey, RulesInForceView, RuleVersionView
from dw_sales.application.services import SalesServices
from dw_sales.application.source import MessageTextView, SourceView
from dw_sales.application.views import (
    BravoOrderView,
    CaseChangeView,
    ConvertEntryView,
    CustomerView,
    InboxMessageView,
    ItemView,
    LmeView,
    MasterDataView,
    OpenYcbgView,
    OrderCaseView,
    OrderSummaryView,
    ProcessingJobView,
    QuotationRowView,
    QuoteCaseView,
    QuoteSummaryView,
    WorkerStateView,
)
from dw_sales.domain.catalog import CopperBasis, CustomerCode, DocumentNo, PrvCode
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.layouts import LayoutMapping
from dw_sales.domain.master_data import CatalogList
from dw_sales.domain.orders import CloseReason, Note
from dw_sales.domain.pricing import Incoterm
from dw_sales.domain.quotes import DeclineReason, Guidance, Reason

NOT_CONFIGURED = "chưa cấu hình nguồn dữ liệu"

_BODY = ConfigDict(extra="forbid", hide_input_in_errors=True)
_FindingKey = Annotated[str, Field(pattern=r"^[a-z_]{1,40}:([1-9][0-9]{0,4}|-)$")]
_MessageId = Annotated[str, Field(pattern=r"^[!-~]{1,512}$")]
_AttachmentId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")]


class LayoutBody(BaseModel):
    """A mapping of the form one message's attachment prints (ticket 30)."""

    model_config = _BODY

    message_id: _MessageId
    attachment_id: _AttachmentId
    mapping: LayoutMapping


class RuleProposalBody(BaseModel):
    """A whole policy document for one key, validated by that key's schema."""

    model_config = _BODY

    document: dict[str, Any]


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class CatalogUploadBody(BaseModel):
    """A master-data file (ticket 41): its name and its bytes, base64. The
    bytes are decoded here and never opened: the worker reads them in the
    reader sandbox."""

    model_config = _BODY

    file_name: Annotated[str, Field(min_length=1, max_length=200)]
    # 2 MiB of bytes, as base64 (`MAX_IMPORT_BYTES`; the service refuses more).
    content_b64: Annotated[str, Field(min_length=1, max_length=2_796_204)]

    def data(self) -> bytes:
        try:
            return base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError):
            raise DomainError(
                "nội dung tệp không hợp lệ", details={"rule": "file_encoding"}
            ) from None


class VersionBody(BaseModel):
    """The case version the decision was made on."""

    model_config = _BODY

    case_version: int = Field(ge=1)


class RenderBody(VersionBody):
    """An artifact kind to render from the case at the version the caller saw;
    which kinds are open now is `GET .../artifacts`'s ``available``."""

    kind: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")]


class DispositionBody(VersionBody):
    disposition: Literal["open", "accepted", "corrected_by_sales", "ask_customer"]
    reason: Note | None = None
    value: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")] | None = None
    source: Note | None = None


class MappingBody(VersionBody):
    prv_code: PrvCode


class CorrectionBody(VersionBody):
    """One value a `value_uncertain` flagged, as Sales reads it on the source:
    the field it is, and the value as text, which the case validates as that
    field's type (a number, a date, a unit, text)."""

    field: Annotated[str, Field(pattern=r"^[a-z_]{1,32}$")]
    value: Annotated[str, Field(min_length=1, max_length=200)]


class BravoEntryBody(VersionBody):
    # Absent only when applying a revision's change to an order already in Bravo.
    so_no: DocumentNo | None = None
    entry_compared: bool


class AssigneeBody(VersionBody):
    """Who the case is given to; null gives it to nobody (every PIC's)."""

    assignee: uuid.UUID | None


class LineDate(BaseModel):
    """The date Sales confirms for a line delivered once, or, for a line the
    PO splits over several schedules, one per schedule in their order
    (ticket 35): exactly one of the two."""

    model_config = _BODY

    line_no: int = Field(ge=1)
    confirmed_date: date | None = None
    schedule_dates: list[date] | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _one_of_the_two(self) -> "LineDate":
        if (self.confirmed_date is None) == (self.schedule_dates is None):
            raise ValueError("a line gets confirmed_date or schedule_dates, not both")
        return self

    @property
    def dates(self) -> list[date]:
        if self.schedule_dates is not None:
            return self.schedule_dates
        assert self.confirmed_date is not None  # one of the two, above
        return [self.confirmed_date]


class ConfirmBody(VersionBody):
    delivery_dates: list[LineDate] = Field(min_length=1, max_length=9999)


class CloseBody(VersionBody):
    reason: CloseReason
    superseded_by: uuid.UUID | None = None


class AnswerBody(VersionBody):
    quantity: Decimal | None = Field(default=None, gt=0)
    needed_by: date | None = None
    customer_code: CustomerCode | None = None
    note: Reason | None = None
    # `value_uncertain` (ticket 29): one value a model read, as Sales types it.
    field: Annotated[str, Field(pattern=r"^[a-z_]{1,32}$")] | None = None
    value: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class YcbgBody(VersionBody):
    # Absent: draft the YCBG. Present: the number Bravo gave it.
    ycbg_no: DocumentNo | None = None


class SpecBody(VersionBody):
    step: Literal["start", "settle", "ask_design_again"]


class PriceLineBody(BaseModel):
    model_config = _BODY

    line_no: int = Field(ge=1, le=9999)
    unit_price: Decimal = Field(gt=0)
    moq: Decimal = Field(gt=0)
    lead_time_days: int = Field(gt=0, le=365)
    copper_basis: CopperBasis


class PriceBody(VersionBody):
    # The LME month the price was decided against; its figure is read from
    # master data, never taken from here.
    lme_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    lines: list[PriceLineBody] = Field(min_length=1, max_length=9999)
    management_guidance: Guidance | None = None


class SubmitBody(VersionBody):
    quote_no: DocumentNo


class DeclineBody(VersionBody):
    reason: DeclineReason
    note: Reason | None = None


class PauseBody(BaseModel):
    model_config = _BODY

    reason: Note | None = None


class ResumeBody(BaseModel):
    model_config = _BODY

    reason: Note


class IdempotentRecorder(Protocol):
    """The app's `Idempotency-Key` operation: stores what a mutation answered,
    so a retry with the same key gets the same answer and acts once."""

    async def record[M: BaseModel](self, result: M, *, status_code: int = 200) -> M: ...


class ProcessingQueuedView(BaseModel):
    """What "DW xử lý tất cả" queued (ticket 25): one job per message."""

    model_config = ConfigDict(frozen=True)

    jobs: list[ProcessingJobView]


class RenderedView(BaseModel):
    """The files one render stored: ids, template, version and hash only."""

    model_config = ConfigDict(frozen=True)

    artifacts: list[ArtifactView]


@dataclass(frozen=True)
class SalesMount:
    """What the composition root mounts: the services, or None when no data
    source is configured for this deployment."""

    services: SalesServices | None


def build_router(
    services: SalesServices | None,
    *,
    access_context: Callable[..., Any],
    idempotency: Callable[..., Any],
    support_access_context: Callable[..., Any] | None = None,
) -> APIRouter:
    """The Sales router; ``services`` None answers 503 on every route.

    ``support_access_context`` is the dependency the support reads take (a
    member's context, or a support staff member's under a grant); without
    one they take ``access_context`` like every other route.
    """
    router = APIRouter(prefix="/api/v1/sales", tags=["sales"])
    read_context = support_access_context or access_context

    def services_after(context_dependency: Callable[..., Any]) -> Callable[..., SalesServices]:
        def _services(
            context: Annotated[AccessContext, Depends(context_dependency)],
        ) -> SalesServices:
            # Depends on the access context first, so an unauthenticated caller
            # learns nothing, not even that the source is unconfigured.
            if services is None:
                raise InfrastructureError(NOT_CONFIGURED, details={"context": "sales"})
            return services

        return _services

    Ctx = Annotated[AccessContext, Depends(access_context)]  # noqa: N806 (a type alias)
    Svc = Annotated[SalesServices, Depends(services_after(access_context))]  # noqa: N806 (a type alias)
    # The support reads (module docstring): the same context, or a support one.
    ReadCtx = Annotated[AccessContext, Depends(read_context)]  # noqa: N806 (a type alias)
    ReadSvc = Annotated[SalesServices, Depends(services_after(read_context))]  # noqa: N806 (a type alias)
    Idem = Annotated[IdempotentRecorder, Depends(idempotency)]  # noqa: N806 (a type alias)

    def scopes(*needed: SalesScopes) -> Any:
        async def guard(context: Ctx, svc: Svc) -> None:
            await svc.gate.require(context, *needed)

        return Depends(guard)

    prepare_scope = [scopes(SalesScopes.ORDER_PREPARE)]
    quote_scope = [scopes(SalesScopes.QUOTE_PREPARE)]

    # ------------------------------------------------------------ overview --

    @router.get("/overview", response_model=OverviewView)
    async def overview(context: ReadCtx, svc: ReadSvc) -> OverviewView:
        return await svc.overview.overview(context)

    @router.get("/my-work", response_model=Page[WorkItem])
    async def my_work(
        context: Ctx,
        svc: Svc,
        limit: int = Query(default=WORK_PAGE, ge=1, le=MAX_PAGE_SIZE),
        cursor: str | None = Query(default=None, description="Opaque cursor from a previous page."),
    ) -> Page[WorkItem]:
        return await svc.overview.my_work(context, limit=limit, cursor=cursor)

    # --------------------------------------------------------------- inbox --

    @router.get("/inbox", response_model=list[InboxMessageView])
    async def inbox(context: Ctx, svc: Svc) -> list[InboxMessageView]:
        return await svc.inbox.messages(context)

    # "DW xử lý" queues (ticket 25): 202 with the job, which the worker runs;
    # the inbox shows where it stands (`InboxMessageView.processing`).
    @router.post(
        "/inbox/process-all",
        response_model=ProcessingQueuedView,
        status_code=202,
        dependencies=[scopes(SalesScopes.INBOX_PROCESS)],
    )
    async def process_all(context: Ctx, svc: Svc, idem: Idem) -> ProcessingQueuedView:
        jobs = await svc.processing.enqueue_waiting(context)
        return await idem.record(ProcessingQueuedView(jobs=jobs), status_code=202)

    @router.post(
        "/inbox/{message_id}/process",
        response_model=ProcessingJobView,
        status_code=202,
        dependencies=[scopes(SalesScopes.INBOX_PROCESS)],
    )
    async def process(
        message_id: _MessageId, context: Ctx, svc: Svc, idem: Idem
    ) -> ProcessingJobView:
        job = await svc.processing.enqueue(context, message_id)
        return await idem.record(job, status_code=202)

    # -------------------------------------------------------------- orders --

    @router.get("/orders", response_model=list[OrderSummaryView])
    async def orders(context: ReadCtx, svc: ReadSvc) -> list[OrderSummaryView]:
        return await svc.orders.summaries(context)

    @router.get("/orders/{case_id}", response_model=OrderCaseView)
    async def order(case_id: uuid.UUID, context: ReadCtx, svc: ReadSvc) -> OrderCaseView:
        return await svc.orders.get(context, case_id)

    @router.get(
        "/orders/{case_id}/source/{attachment_id}",
        response_model=SourceView,
        dependencies=[scopes(SalesScopes.CASE_READ, SalesScopes.PRICE_READ)],
    )
    async def order_source(
        case_id: uuid.UUID,
        attachment_id: _AttachmentId,
        context: Ctx,
        svc: Svc,
        page: Annotated[int | None, Query(ge=1, le=9999)] = None,
        sheet: Annotated[str | None, Query(min_length=1, max_length=31)] = None,
    ) -> SourceView:
        return await svc.sources.order_source(
            context, case_id, attachment_id, page=page, sheet=sheet
        )

    @router.get("/orders/{case_id}/artifacts", response_model=ArtifactListView)
    async def order_artifacts(case_id: uuid.UUID, context: Ctx, svc: Svc) -> ArtifactListView:
        return await svc.artifacts.order_artifacts(context, case_id)

    @router.post(
        "/orders/{case_id}/artifacts", response_model=RenderedView, dependencies=prepare_scope
    )
    async def render_order_artifact(
        case_id: uuid.UUID, body: RenderBody, context: Ctx, svc: Svc, idem: Idem
    ) -> RenderedView:
        rendered = await svc.artifacts.render_order(
            context, case_id, kind=body.kind, case_version=body.case_version
        )
        return await idem.record(RenderedView(artifacts=rendered))

    @router.get("/orders/{case_id}/artifacts/{artifact_id}", response_class=Response)
    async def order_artifact(
        case_id: uuid.UUID, artifact_id: uuid.UUID, context: Ctx, svc: Svc
    ) -> Response:
        return _download(await svc.artifacts.order_artifact(context, case_id, artifact_id))

    @router.post(
        "/orders/{case_id}/findings/{finding_key}/disposition",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def dispose(
        case_id: uuid.UUID,
        finding_key: _FindingKey,
        body: DispositionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChangeView:
        change = await svc.order_commands.dispose(
            context,
            case_id,
            finding_key,
            case_version=body.case_version,
            disposition=body.disposition,
            reason=body.reason,
            value=body.value,
            source=body.source,
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/findings/{finding_key}/corrections",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def correct_value(
        case_id: uuid.UUID,
        finding_key: _FindingKey,
        body: CorrectionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChangeView:
        change = await svc.order_commands.correct_value(
            context,
            case_id,
            finding_key,
            case_version=body.case_version,
            field=body.field,
            value=body.value,
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/lines/{line_no}/mapping",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def mapping(
        case_id: uuid.UUID,
        line_no: Annotated[int, PathParam(ge=1, le=9999)],
        body: MappingBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChangeView:
        change = await svc.order_commands.confirm_mapping(
            context, case_id, line_no, case_version=body.case_version, prv_code=body.prv_code
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/lines/{line_no}/delivery-date",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def delivery_date(
        case_id: uuid.UUID,
        line_no: Annotated[int, PathParam(ge=1, le=9999)],
        body: VersionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChangeView:
        """PC agreed the line's short lead time: recorded as who and when."""
        change = await svc.order_commands.record_pc_date(
            context, case_id, line_no, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/correction-request",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def correction_request(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.order_commands.request_correction(
            context, case_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/resume-review",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def resume_review(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.order_commands.resume_review(
            context, case_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/prepare", response_model=CaseChangeView, dependencies=prepare_scope
    )
    async def prepare(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.order_commands.prepare(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/bravo-entry", response_model=CaseChangeView, dependencies=prepare_scope
    )
    async def bravo_entry(
        case_id: uuid.UUID, body: BravoEntryBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.dw1.record_bravo_entry(
            context,
            case_id,
            case_version=body.case_version,
            so_no=body.so_no,
            entry_compared=body.entry_compared,
        )
        return await idem.record(change)

    # ------------------------------------------------- the assignee (17) --
    # Who a case may be given to, and giving it: the head's
    # (`sales.case.assign`), for an order or a quote alike.

    assign_scope = [scopes(SalesScopes.CASE_ASSIGN)]

    @router.get(
        "/orders/{case_id}/assignees",
        response_model=list[AssigneeView],
        dependencies=assign_scope,
    )
    async def order_assignees(case_id: uuid.UUID, context: Ctx, svc: Svc) -> list[AssigneeView]:
        return await svc.assignment.candidates(context, CaseKind.ORDER, case_id)

    @router.put(
        "/orders/{case_id}/assignee", response_model=CaseChangeView, dependencies=assign_scope
    )
    async def reassign_order(
        case_id: uuid.UUID, body: AssigneeBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.assignment.reassign(
            context,
            CaseKind.ORDER,
            case_id,
            assignee=body.assignee,
            case_version=body.case_version,
        )
        return await idem.record(change)

    @router.get(
        "/quotes/{case_id}/assignees",
        response_model=list[AssigneeView],
        dependencies=assign_scope,
    )
    async def quote_assignees(case_id: uuid.UUID, context: Ctx, svc: Svc) -> list[AssigneeView]:
        return await svc.assignment.candidates(context, CaseKind.QUOTE, case_id)

    @router.put(
        "/quotes/{case_id}/assignee", response_model=CaseChangeView, dependencies=assign_scope
    )
    async def reassign_quote(
        case_id: uuid.UUID, body: AssigneeBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.assignment.reassign(
            context,
            CaseKind.QUOTE,
            case_id,
            assignee=body.assignee,
            case_version=body.case_version,
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/resend-cross-check",
        response_model=CaseChangeView,
        dependencies=prepare_scope,
    )
    async def resend_cross_check(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        """ "Gửi kiểm chéo lại" (ticket 14). Whoever recorded the Bravo entry,
        with `sales.order.prepare`; anyone else also needs
        `sales.order.resend_cross_check`, which the case checks (403)."""
        change = await svc.dw1.resend_cross_check(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/confirm", response_model=CaseChangeView, dependencies=prepare_scope
    )
    async def confirm(
        case_id: uuid.UUID, body: ConfirmBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.order_commands.confirm(
            context,
            case_id,
            case_version=body.case_version,
            delivery_dates={d.line_no: d.dates for d in body.delivery_dates},
        )
        return await idem.record(change)

    @router.post(
        "/orders/{case_id}/close", response_model=CaseChangeView, dependencies=prepare_scope
    )
    async def close(
        case_id: uuid.UUID, body: CloseBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.order_commands.close(
            context,
            case_id,
            case_version=body.case_version,
            reason=body.reason,
            superseded_by=body.superseded_by,
        )
        return await idem.record(change)

    # -------------------------------------------------------------- quotes --

    @router.get("/quotes", response_model=list[QuoteSummaryView])
    async def quotes(context: ReadCtx, svc: ReadSvc) -> list[QuoteSummaryView]:
        return await svc.quotes.summaries(context)

    @router.get("/quotes/screening", response_model=list[ScreeningRow])
    async def screening(
        context: Ctx, svc: Svc, as_of: Annotated[date | None, Query()] = None
    ) -> list[ScreeningRow]:
        return await svc.quotes.screening(context, as_of)

    @router.get("/quotes/{case_id}", response_model=QuoteCaseView)
    async def quote(
        case_id: uuid.UUID,
        context: ReadCtx,
        svc: ReadSvc,
        incoterm: Annotated[Incoterm | None, Query()] = None,
        destination: Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,31}$")] = None,
    ) -> QuoteCaseView:
        return await svc.quotes.get(context, case_id, incoterm=incoterm, destination=destination)

    @router.get(
        "/quotes/{case_id}/source/{attachment_id}",
        response_model=SourceView,
        dependencies=[scopes(SalesScopes.CASE_READ, SalesScopes.PRICE_READ)],
    )
    async def quote_source(
        case_id: uuid.UUID,
        attachment_id: _AttachmentId,
        context: Ctx,
        svc: Svc,
        page: Annotated[int | None, Query(ge=1, le=9999)] = None,
        sheet: Annotated[str | None, Query(min_length=1, max_length=31)] = None,
    ) -> SourceView:
        return await svc.sources.quote_source(
            context, case_id, attachment_id, page=page, sheet=sheet
        )

    @router.get(
        "/quotes/{case_id}/message-text",
        response_model=MessageTextView,
        dependencies=[scopes(SalesScopes.CASE_READ, SalesScopes.PRICE_READ)],
    )
    async def quote_message_text(case_id: uuid.UUID, context: Ctx, svc: Svc) -> MessageTextView:
        return await svc.sources.quote_message_text(context, case_id)

    @router.get("/quotes/{case_id}/artifacts", response_model=ArtifactListView)
    async def quote_artifacts(case_id: uuid.UUID, context: Ctx, svc: Svc) -> ArtifactListView:
        return await svc.artifacts.quote_artifacts(context, case_id)

    @router.post(
        "/quotes/{case_id}/artifacts", response_model=RenderedView, dependencies=quote_scope
    )
    async def render_quote_artifact(
        case_id: uuid.UUID, body: RenderBody, context: Ctx, svc: Svc, idem: Idem
    ) -> RenderedView:
        rendered = await svc.artifacts.render_quote(
            context, case_id, kind=body.kind, case_version=body.case_version
        )
        return await idem.record(RenderedView(artifacts=rendered))

    @router.get("/quotes/{case_id}/artifacts/{artifact_id}", response_class=Response)
    async def quote_artifact(
        case_id: uuid.UUID, artifact_id: uuid.UUID, context: Ctx, svc: Svc
    ) -> Response:
        return _download(await svc.artifacts.quote_artifact(context, case_id, artifact_id))

    @router.post(
        "/quotes/{case_id}/findings/{finding_key}/answer",
        response_model=CaseChangeView,
        dependencies=quote_scope,
    )
    async def answer(
        case_id: uuid.UUID,
        finding_key: _FindingKey,
        body: AnswerBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChangeView:
        change = await svc.quote_commands.answer_finding(
            context,
            case_id,
            finding_key,
            case_version=body.case_version,
            quantity=body.quantity,
            needed_by=body.needed_by,
            customer_code=body.customer_code,
            note=body.note,
            field=body.field,
            value=body.value,
        )
        return await idem.record(change)

    @router.post("/quotes/{case_id}/ycbg", response_model=CaseChangeView, dependencies=quote_scope)
    async def ycbg(
        case_id: uuid.UUID, body: YcbgBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.ycbg(
            context, case_id, case_version=body.case_version, ycbg_no=body.ycbg_no
        )
        return await idem.record(change)

    @router.post(
        "/quotes/{case_id}/design-sent", response_model=CaseChangeView, dependencies=quote_scope
    )
    async def design_sent(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.design_sent(
            context, case_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/quotes/{case_id}/spec-discussion",
        response_model=CaseChangeView,
        dependencies=quote_scope,
    )
    async def spec_discussion(
        case_id: uuid.UUID, body: SpecBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.spec_discussion(
            context, case_id, case_version=body.case_version, step=body.step
        )
        return await idem.record(change)

    @router.post("/quotes/{case_id}/price", response_model=CaseChangeView, dependencies=quote_scope)
    async def price(
        case_id: uuid.UUID, body: PriceBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.price(
            context,
            case_id,
            case_version=body.case_version,
            lme_month=body.lme_month,
            lines=[
                PricedLine(
                    line_no=line.line_no,
                    unit_price=line.unit_price,
                    moq=line.moq,
                    lead_time_days=line.lead_time_days,
                    copper_basis=line.copper_basis,
                )
                for line in body.lines
            ],
            management_guidance=body.management_guidance,
        )
        return await idem.record(change)

    @router.post(
        "/quotes/{case_id}/submit", response_model=CaseChangeView, dependencies=quote_scope
    )
    async def submit(
        case_id: uuid.UUID, body: SubmitBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.dw1.submit_quote(
            context, case_id, case_version=body.case_version, quote_no=body.quote_no
        )
        return await idem.record(change)

    @router.post("/quotes/{case_id}/sent", response_model=CaseChangeView, dependencies=quote_scope)
    async def sent(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.sent(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.post(
        "/quotes/{case_id}/master-list", response_model=CaseChangeView, dependencies=quote_scope
    )
    async def master_list(
        case_id: uuid.UUID, body: VersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.master_list(
            context, case_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/quotes/{case_id}/decline", response_model=CaseChangeView, dependencies=quote_scope
    )
    async def decline(
        case_id: uuid.UUID, body: DeclineBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChangeView:
        change = await svc.quote_commands.decline(
            context, case_id, case_version=body.case_version, reason=body.reason, note=body.note
        )
        return await idem.record(change)

    # --------------------------------------------------------- master data --

    @router.get("/master-data/customers", response_model=MasterDataView[CustomerView])
    async def customers(context: Ctx, svc: Svc) -> MasterDataView[CustomerView]:
        return await svc.master_data.customers(context)

    @router.get("/master-data/items", response_model=MasterDataView[ItemView])
    async def items(context: Ctx, svc: Svc) -> MasterDataView[ItemView]:
        return await svc.master_data.items(context)

    @router.get("/master-data/convert-list", response_model=MasterDataView[ConvertEntryView])
    async def convert_list(context: Ctx, svc: Svc) -> MasterDataView[ConvertEntryView]:
        return await svc.master_data.convert_list(context)

    @router.get("/master-data/quotations", response_model=MasterDataView[QuotationRowView])
    async def quotations(context: Ctx, svc: Svc) -> MasterDataView[QuotationRowView]:
        return await svc.master_data.quotations(context)

    @router.get("/master-data/lme", response_model=MasterDataView[LmeView])
    async def lme(context: Ctx, svc: Svc) -> MasterDataView[LmeView]:
        return await svc.master_data.lme(context)

    @router.get("/master-data/bravo-orders", response_model=MasterDataView[BravoOrderView])
    async def bravo_orders(context: Ctx, svc: Svc) -> MasterDataView[BravoOrderView]:
        return await svc.master_data.bravo_orders(context)

    @router.get("/master-data/open-ycbg", response_model=MasterDataView[OpenYcbgView])
    async def open_ycbg(context: Ctx, svc: Svc) -> MasterDataView[OpenYcbgView]:
        return await svc.master_data.open_ycbg(context)

    # ------------------------------------- master-data imports (ticket 41) --
    # A PIC or the head imports a list from a file (`sales.master_data.import`;
    # the quotation and LME lists need the price scopes too). The file is only
    # kept here: the worker reads it in the reader sandbox (202). Submitting
    # opens a `sales.catalog` platform approval, which the head, who neither
    # imported nor submitted it, decides on `/approvals`: no route here does.

    import_scope = [scopes(SalesScopes.MASTER_DATA_IMPORT)]

    @router.get(
        "/master-data/imports",
        response_model=CatalogStateView,
        dependencies=[scopes(SalesScopes.CASE_READ)],
    )
    async def catalog_state(context: Ctx, svc: Svc) -> CatalogStateView:
        return await svc.catalog_imports.state(context)

    @router.get(
        "/master-data/imports/{catalog_list}/template",
        response_class=Response,
        dependencies=import_scope,
    )
    async def catalog_template(catalog_list: CatalogList, context: Ctx, svc: Svc) -> Response:
        data, file_name = await svc.catalog_imports.template(context, catalog_list)
        return Response(
            content=data,
            media_type=_XLSX,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post(
        "/master-data/imports/{catalog_list}",
        response_model=CatalogImportView,
        status_code=202,
        dependencies=import_scope,
    )
    async def catalog_upload(
        catalog_list: CatalogList, body: CatalogUploadBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CatalogImportView:
        view = await svc.catalog_imports.upload(context, catalog_list, body.file_name, body.data())
        return await idem.record(view, status_code=202)

    @router.get(
        "/master-data/imports/snapshots/{snapshot_id}",
        response_model=CatalogPreviewView,
        dependencies=[scopes(SalesScopes.CASE_READ)],
    )
    async def catalog_preview(snapshot_id: uuid.UUID, context: Ctx, svc: Svc) -> CatalogPreviewView:
        return await svc.catalog_imports.preview(context, snapshot_id)

    @router.post(
        "/master-data/imports/snapshots/{snapshot_id}/submit",
        response_model=CatalogImportView,
        dependencies=import_scope,
    )
    async def catalog_submit(
        snapshot_id: uuid.UUID, context: Ctx, svc: Svc, idem: Idem
    ) -> CatalogImportView:
        return await idem.record(await svc.catalog_imports.submit(context, snapshot_id))

    # -------------------------------------------------------------- worker --

    @router.post(
        "/worker/pause",
        response_model=WorkerStateView,
        dependencies=[scopes(SalesScopes.WORKER_PAUSE)],
    )
    async def pause(body: PauseBody, context: Ctx, svc: Svc, idem: Idem) -> WorkerStateView:
        return await idem.record(await svc.worker.pause(context, body.reason))

    @router.post(
        "/worker/resume",
        response_model=WorkerStateView,
        dependencies=[scopes(SalesScopes.WORKER_RESUME)],
    )
    async def resume(body: ResumeBody, context: Ctx, svc: Svc, idem: Idem) -> WorkerStateView:
        return await idem.record(await svc.worker.resume(context, body.reason))

    # ------------------------------------------- PO layouts (ticket 30) --
    # A PIC maps a customer's form (`sales.order.prepare`, and the prices a
    # PO shows). The head, who did not map it, decides it on the platform
    # approval the proposal opens (`sales.layout`, stamped with
    # `sales.layout.approve`): no route here decides it (dw_sales ADR 0004).

    mapper_scope = [scopes(SalesScopes.ORDER_PREPARE, SalesScopes.PRICE_READ)]

    @router.get(
        "/layouts", response_model=list[LayoutView], dependencies=[scopes(SalesScopes.CASE_READ)]
    )
    async def layouts(context: Ctx, svc: Svc) -> list[LayoutView]:
        return await svc.layouts.list(context)

    @router.get("/layouts/source", response_model=LayoutSourceView, dependencies=mapper_scope)
    async def layout_source(
        context: Ctx,
        svc: Svc,
        message_id: Annotated[str, Query(pattern=r"^[!-~]{1,512}$")],
        attachment_id: Annotated[str, Query(pattern=r"^[A-Za-z0-9._-]{1,128}$")],
    ) -> LayoutSourceView:
        return await svc.layouts.source(context, message_id, attachment_id)

    @router.post("/layouts/preview", response_model=LayoutPreviewView, dependencies=mapper_scope)
    async def layout_preview(
        body: LayoutBody, context: Ctx, svc: Svc, idem: Idem
    ) -> LayoutPreviewView:
        # Writes nothing, but a POST like every other: a retried press is
        # answered with the first answer.
        return await idem.record(
            await svc.layouts.preview(context, body.message_id, body.attachment_id, body.mapping)
        )

    @router.post("/layouts", response_model=LayoutView, dependencies=mapper_scope)
    async def propose_layout(body: LayoutBody, context: Ctx, svc: Svc, idem: Idem) -> LayoutView:
        return await idem.record(
            await svc.layouts.propose(context, body.message_id, body.attachment_id, body.mapping)
        )

    # ---------------------------------- a tenant's own rules (ticket 19) --
    # A PIC or the head proposes a version of one key (`sales.rules.propose`),
    # which opens a `sales.rules` platform approval; the head, who did not
    # propose it, decides it there (`sales.rules.approve`, ticket 38): no
    # Sales route decides. An unknown key, or one no reader resolves per
    # tenant yet, is not a path this router has: 422.

    @router.get(
        "/rules",
        response_model=RulesInForceView,
        dependencies=[scopes(SalesScopes.RULES_PROPOSE)],
    )
    async def rules_in_force(context: Ctx, svc: Svc) -> RulesInForceView:
        return await svc.rules.list(context)

    @router.post(
        "/rules/{key}/versions",
        response_model=RuleVersionView,
        dependencies=[scopes(SalesScopes.RULES_PROPOSE)],
    )
    async def propose_rules(
        key: RuleKey, body: RuleProposalBody, context: Ctx, svc: Svc, idem: Idem
    ) -> RuleVersionView:
        return await idem.record(await svc.rules.propose(context, key, body.document))

    return router


def _download(download: Download) -> Response:
    """The file as stored, never rendered inline by the browser and never kept
    by a shared cache: a Bravo upload or a quotation carries prices."""
    return Response(
        content=download.data,
        media_type=download.record.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download.file_name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
