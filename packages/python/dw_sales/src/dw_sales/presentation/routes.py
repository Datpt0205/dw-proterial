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
- **No data source configured** (a deployed profile without the demo tenant):
  every route answers 503 "chưa cấu hình nguồn dữ liệu".
- **No decision of a checker is made here.** Approving or returning a
  quotation and cross-checking or returning an order are decisions on a
  platform approval (`POST /api/v1/approvals/{id}/decisions`), which DW1's
  run pauses on and applies (dw_sales ADR 0004). The routes that raise them
  (`submit`, `bravo-entry`) and "DW xử lý" start a DW1 run (`svc.dw1`).
"""

# No `from __future__ import annotations` here: the routes annotate their
# parameters with aliases built inside `build_router` from the dependencies
# the app hands in, and FastAPI resolves a string annotation against the
# module's globals, where those aliases do not exist.

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import InfrastructureError
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import SalesScopes
from dw_sales.application.artifacts_service import ArtifactListView, ArtifactView, Download
from dw_sales.application.overview_service import OverviewView, WorkItem
from dw_sales.application.quotation import ScreeningRow
from dw_sales.application.quotes_service import PricedLine
from dw_sales.application.services import SalesServices
from dw_sales.application.source import SourceView
from dw_sales.application.views import (
    BravoOrderView,
    CaseChangeView,
    ConvertEntryView,
    CustomerView,
    InboxMessageView,
    ItemView,
    LmeView,
    MasterDataView,
    MessageDispositionView,
    OpenYcbgView,
    OrderCaseView,
    OrderSummaryView,
    QuotationRowView,
    QuoteCaseView,
    QuoteSummaryView,
    WorkerStateView,
)
from dw_sales.domain.catalog import CopperBasis, CustomerCode, DocumentNo, PrvCode
from dw_sales.domain.orders import CloseReason, Note
from dw_sales.domain.pricing import Incoterm
from dw_sales.domain.quotes import DeclineReason, Guidance, Reason

NOT_CONFIGURED = "chưa cấu hình nguồn dữ liệu"

_BODY = ConfigDict(extra="forbid", hide_input_in_errors=True)
_FindingKey = Annotated[str, Field(pattern=r"^[a-z_]{1,40}:([1-9][0-9]{0,4}|-)$")]
_MessageId = Annotated[str, Field(pattern=r"^[!-~]{1,512}$")]
_AttachmentId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")]


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


class BravoEntryBody(VersionBody):
    # Absent only when applying a revision's change to an order already in Bravo.
    so_no: DocumentNo | None = None
    entry_compared: bool


class LineDate(BaseModel):
    model_config = _BODY

    line_no: int = Field(ge=1)
    confirmed_date: date


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


class ProcessAllView(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[MessageDispositionView]


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
) -> APIRouter:
    """The Sales router; ``services`` None answers 503 on every route."""
    router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

    def _services(
        context: Annotated[AccessContext, Depends(access_context)],
    ) -> SalesServices:
        # Depends on the access context first, so an unauthenticated caller
        # learns nothing, not even that the source is unconfigured.
        if services is None:
            raise InfrastructureError(NOT_CONFIGURED, details={"context": "sales"})
        return services

    Ctx = Annotated[AccessContext, Depends(access_context)]  # noqa: N806 (a type alias)
    Svc = Annotated[SalesServices, Depends(_services)]  # noqa: N806 (a type alias)
    Idem = Annotated[IdempotentRecorder, Depends(idempotency)]  # noqa: N806 (a type alias)

    def scopes(*needed: SalesScopes) -> Any:
        async def guard(context: Ctx, svc: Svc) -> None:
            await svc.gate.require(context, *needed)

        return Depends(guard)

    prepare_scope = [scopes(SalesScopes.ORDER_PREPARE)]
    quote_scope = [scopes(SalesScopes.QUOTE_PREPARE)]

    # ------------------------------------------------------------ overview --

    @router.get("/overview", response_model=OverviewView)
    async def overview(context: Ctx, svc: Svc) -> OverviewView:
        return await svc.overview.overview(context)

    @router.get("/my-work", response_model=list[WorkItem])
    async def my_work(context: Ctx, svc: Svc) -> list[WorkItem]:
        return await svc.overview.my_work(context)

    # --------------------------------------------------------------- inbox --

    @router.get("/inbox", response_model=list[InboxMessageView])
    async def inbox(context: Ctx, svc: Svc) -> list[InboxMessageView]:
        return await svc.inbox.messages(context)

    @router.post(
        "/inbox/process-all",
        response_model=ProcessAllView,
        dependencies=[scopes(SalesScopes.INBOX_PROCESS)],
    )
    async def process_all(context: Ctx, svc: Svc, idem: Idem) -> ProcessAllView:
        results = await svc.dw1.process_all(context)
        return await idem.record(ProcessAllView(results=results))

    @router.post(
        "/inbox/{message_id}/process",
        response_model=MessageDispositionView,
        dependencies=[scopes(SalesScopes.INBOX_PROCESS)],
    )
    async def process(
        message_id: _MessageId, context: Ctx, svc: Svc, idem: Idem
    ) -> MessageDispositionView:
        return await idem.record(await svc.dw1.process(context, message_id))

    # -------------------------------------------------------------- orders --

    @router.get("/orders", response_model=list[OrderSummaryView])
    async def orders(context: Ctx, svc: Svc) -> list[OrderSummaryView]:
        return await svc.orders.summaries(context)

    @router.get("/orders/{case_id}", response_model=OrderCaseView)
    async def order(case_id: uuid.UUID, context: Ctx, svc: Svc) -> OrderCaseView:
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
            delivery_dates={d.line_no: d.confirmed_date for d in body.delivery_dates},
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
    async def quotes(context: Ctx, svc: Svc) -> list[QuoteSummaryView]:
        return await svc.quotes.summaries(context)

    @router.get("/quotes/screening", response_model=list[ScreeningRow])
    async def screening(
        context: Ctx, svc: Svc, as_of: Annotated[date | None, Query()] = None
    ) -> list[ScreeningRow]:
        return await svc.quotes.screening(context, as_of)

    @router.get("/quotes/{case_id}", response_model=QuoteCaseView)
    async def quote(
        case_id: uuid.UUID,
        context: Ctx,
        svc: Svc,
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
