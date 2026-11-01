"""`/api/v1/purchasing/*`: thin routes over the Purchasing services.

The composition root hands in the services and two of its own dependencies:
the verified access context and the `Idempotency-Key` operation. This package
names neither implementation (it may not import the app).

- **Every route depends on the verified access context**: the tenant and
  workspace come from it and from nothing a request carries.
- **A scope a route needs is checked before anything else**: before a case is
  read, and on a mutation before the idempotency key is claimed, so a replay
  never answers a caller who may not make the request. The service checks
  again where the change happens.
- **A mutation answers ids and codes** (`CaseChange`; `InboxItem`, which
  also carries the mail's sender and subject): what the idempotency store
  keeps holds no request line and no amount.
- **No data source configured**: every route answers 503.
"""

# No `from __future__ import annotations`: the routes annotate their
# parameters with aliases built inside `build_router`, and FastAPI resolves a
# string annotation against the module's globals, where they do not exist.

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import DomainError, InfrastructureError
from dw_platform.application.access_context import AccessContext
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.approvals import PurchaseCheckView
from dw_purchasing.application.automation import SwitchesView
from dw_purchasing.application.intake import CaseChange, InboxItem
from dw_purchasing.application.rules import PurchasingRulesView
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.application.sourcing import ComparisonView, OfferForm
from dw_purchasing.domain.cases import PurchaseCase
from dw_purchasing.domain.requests import PurchaseRequest
from dw_purchasing.domain.sourcing import Choice

NOT_CONFIGURED = "chưa cấu hình nguồn dữ liệu Mua hàng"
_PAGE = 50


@dataclass(frozen=True)
class PurchasingMount:
    """What the composition root mounts: None answers 503 on every route."""

    services: PurchasingServices | None


class IdempotentRecorder(Protocol):
    """The app's `Idempotency-Key` operation."""

    async def record[M: BaseModel](self, result: M, *, status_code: int = 200) -> M: ...


class CasePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PurchaseCase]
    # The keyset of the next page, None on the last one.
    next_before_at: datetime | None
    next_before_id: uuid.UUID | None


class CaseVersionBody(BaseModel):
    """The version of the case the caller saw: a stale one is refused (409)."""

    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)


class OfferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    offer: OfferForm


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    choices: list[Choice] = Field(min_length=1, max_length=100)


class RulesBody(BaseModel):
    """A whole version of a key: what the settings page drafted and the person
    read as a difference in words before sending."""

    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]


class RuleChange(BaseModel):
    """What a proposal answers, and what the idempotency store keeps: ids and
    the status, never the document (it holds the company's limits)."""

    model_config = ConfigDict(frozen=True)

    version_id: uuid.UUID
    version: str
    status: str
    approval_id: uuid.UUID | None
    applied_directly: bool


_MessageId = Annotated[str, PathParam(pattern=r"^[!-~]{1,512}$")]
_RuleKey = Annotated[str, PathParam(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


def build_router(
    services: PurchasingServices | None,
    *,
    access_context: Callable[..., Any],
    idempotency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

    def _services(
        context: Annotated[AccessContext, Depends(access_context)],
    ) -> PurchasingServices:
        # The access context first: an unauthenticated caller learns nothing,
        # not even that the source is unconfigured.
        if services is None:
            raise InfrastructureError(NOT_CONFIGURED, details={"context": "purchasing"})
        return services

    Ctx = Annotated[AccessContext, Depends(access_context)]  # noqa: N806 (a type alias)
    Svc = Annotated[PurchasingServices, Depends(_services)]  # noqa: N806 (a type alias)
    Idem = Annotated[IdempotentRecorder, Depends(idempotency)]  # noqa: N806 (a type alias)

    def scope(needed: PurchasingScopes) -> Any:
        async def guard(context: Ctx, svc: Svc) -> None:
            await svc.requests.gate.require(context, needed)

        return Depends(guard)

    read = [scope(PurchasingScopes.REQUEST_READ)]
    intake = [scope(PurchasingScopes.REQUEST_INTAKE)]
    submit = [scope(PurchasingScopes.REQUEST_SUBMIT)]
    rfq = [scope(PurchasingScopes.RFQ_PREPARE)]
    po = [scope(PurchasingScopes.PO_PREPARE)]
    propose = [scope(PurchasingScopes.RULES_PROPOSE)]

    @router.get("/requests", response_model=CasePage, dependencies=read)
    async def list_requests(
        context: Ctx,
        svc: Svc,
        before_at: datetime | None = None,
        before_id: uuid.UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=_PAGE)] = _PAGE,
    ) -> CasePage:
        if (before_at is None) != (before_id is None):
            raise DomainError("before_at and before_id go together")
        before = (before_at, before_id) if before_at and before_id else None
        items = list(await svc.requests.cases(context, limit=limit, before=before))
        last = items[-1] if len(items) == limit else None
        return CasePage(
            items=items,
            next_before_at=last.received_at if last else None,
            next_before_id=last.case_id if last else None,
        )

    @router.get("/requests/{case_id}", response_model=PurchaseCase, dependencies=read)
    async def get_request(case_id: uuid.UUID, context: Ctx, svc: Svc) -> PurchaseCase:
        return await svc.requests.case(context, case_id)

    @router.post("/requests", response_model=CaseChange, status_code=201, dependencies=intake)
    async def submit_request(
        body: PurchaseRequest, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.requests.submit_form(context, body)
        return await idem.record(change, status_code=201)

    @router.get("/requests/{case_id}/check", response_model=PurchaseCheckView, dependencies=read)
    async def check_request(case_id: uuid.UUID, context: Ctx, svc: Svc) -> PurchaseCheckView:
        return await svc.approvals.preview(context, case_id)

    @router.post("/requests/{case_id}/submit", response_model=CaseChange, dependencies=submit)
    async def submit_request_for_approval(
        case_id: uuid.UUID, body: CaseVersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.approvals.submit(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.post("/requests/{case_id}/rfq", response_model=CaseChange, dependencies=rfq)
    async def draft_rfq(
        case_id: uuid.UUID, body: CaseVersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.sourcing.draft_rfq(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.post("/requests/{case_id}/offers", response_model=CaseChange, dependencies=rfq)
    async def record_offer(
        case_id: uuid.UUID, body: OfferBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.sourcing.record_offer(
            context, case_id, body.offer, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/requests/{case_id}/offers/from-mail/{message_id}",
        response_model=CaseChange,
        dependencies=rfq,
    )
    async def read_offer_mail(
        case_id: uuid.UUID,
        message_id: _MessageId,
        body: CaseVersionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChange:
        change = await svc.sourcing.read_offer_mail(
            context, case_id, message_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.get("/requests/{case_id}/comparison", response_model=ComparisonView, dependencies=read)
    async def comparison(case_id: uuid.UUID, context: Ctx, svc: Svc) -> ComparisonView:
        return await svc.sourcing.comparison(context, case_id)

    @router.post("/requests/{case_id}/selection", response_model=CaseChange, dependencies=rfq)
    async def select_suppliers(
        case_id: uuid.UUID, body: SelectionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.sourcing.select(
            context, case_id, body.choices, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post("/requests/{case_id}/po", response_model=CaseChange, dependencies=po)
    async def draft_orders(
        case_id: uuid.UUID, body: CaseVersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.orders.draft(context, case_id, case_version=body.case_version)
        return await idem.record(change)

    @router.get("/requests/{case_id}/po/bravo.xlsx", dependencies=po)
    async def bravo_file(case_id: uuid.UUID, context: Ctx, svc: Svc) -> Response:
        download = await svc.orders.bravo_file(context, case_id)
        return Response(
            content=download.data,
            media_type=download.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{download.filename}"',
                "Cache-Control": "no-store",
            },
        )

    @router.get("/mail", response_model=list[InboxItem], dependencies=read)
    async def mailbox(context: Ctx, svc: Svc) -> list[InboxItem]:
        return await svc.requests.mailbox(context)

    @router.post("/mail/{message_id}/read", response_model=InboxItem, dependencies=intake)
    async def read_mail(message_id: _MessageId, context: Ctx, svc: Svc, idem: Idem) -> InboxItem:
        item = await svc.requests.read_mail(context, message_id)
        return await idem.record(item)

    @router.get("/automation", response_model=SwitchesView, dependencies=read)
    async def automation(context: Ctx, svc: Svc) -> SwitchesView:
        return await svc.switches.view(context)

    @router.get("/rules", response_model=PurchasingRulesView, dependencies=propose)
    async def rules_in_force(context: Ctx, svc: Svc) -> PurchasingRulesView:
        return await svc.rules.list(context)

    @router.get("/rules/{key}/schema", dependencies=propose)
    async def rule_schema(key: _RuleKey, context: Ctx, svc: Svc) -> dict[str, Any]:
        return await svc.rules.schema(context, key)

    @router.post("/rules/{key}/versions", response_model=RuleChange, dependencies=propose)
    async def propose_rules(
        key: _RuleKey, body: RulesBody, context: Ctx, svc: Svc, idem: Idem
    ) -> RuleChange:
        version = await svc.rules.propose(context, key, body.document)
        change = RuleChange(
            version_id=version.version_id,
            version=version.version,
            status=version.status,
            approval_id=version.approval_id,
            applied_directly=version.applied_directly,
        )
        return await idem.record(change)

    return router
