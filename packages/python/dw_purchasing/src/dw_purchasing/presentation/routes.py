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

import base64
import binascii
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, Query, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import DomainError, InfrastructureError
from dw_platform.application.access_context import AccessContext
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.approvals import PurchaseCheckView
from dw_purchasing.application.assistant import (
    AssistantAnswerView,
    AssistantSessionDetailView,
    AssistantSessionView,
)
from dw_purchasing.application.automation import SwitchesView
from dw_purchasing.application.follow_up import ConfirmationMail, LateLine
from dw_purchasing.application.intake import CaseChange, InboxItem
from dw_purchasing.application.master_data import MasterDataView, MasterImportView
from dw_purchasing.application.requesters import DraftView, MyRequest
from dw_purchasing.application.rfq_mail import RfqMailView
from dw_purchasing.application.rule_drafting import WordsDraft
from dw_purchasing.application.rules import PurchasingRulesView
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.application.sourcing import ComparisonView, OfferForm, ReplyItem, SupplierName
from dw_purchasing.domain.assistant import QUESTION_CHARS
from dw_purchasing.domain.cases import PurchaseCase
from dw_purchasing.domain.requests import Code, PurchaseRequest, Quantity
from dw_purchasing.domain.sourcing import Choice

NOT_CONFIGURED = "chưa cấu hình nguồn dữ liệu Mua hàng"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PAGE = 50
_APPROVERS = (
    PurchasingScopes.APPROVE_TIER1,
    PurchasingScopes.APPROVE_TIER2,
    PurchasingScopes.APPROVE_TIER3,
)


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


class RfqBody(BaseModel):
    """The version the buyer saw, and the suppliers they name for a line the
    master data lists nobody for (or one more for a line)."""

    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    suppliers: list[Choice] = Field(default_factory=list, max_length=100)


class RfqWordsBody(BaseModel):
    """A buyer's words for one supplier's RFQ."""

    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)


class OfferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    offer: OfferForm


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    choices: list[Choice] = Field(min_length=1, max_length=100)


class BravoNoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    bravo_no: Code


class ReceiptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_version: int = Field(ge=1)
    line_no: int = Field(ge=1)
    quantity: Quantity
    received_on: date


class AssistantAskBody(BaseModel):
    """A question, and the session it continues (None opens one)."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=QUESTION_CHARS)
    session_id: uuid.UUID | None = None


class RulesBody(BaseModel):
    """A whole version of a key: what the settings page drafted and the person
    read as a difference in words before sending."""

    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]


class WordsBody(BaseModel):
    """What a requester typed in "Tôi cần mua…"."""

    model_config = ConfigDict(extra="forbid")

    words: str = Field(min_length=1, max_length=2000)


class PurchasingRuleWordsBody(BaseModel):
    """What a person wants changed, in their words, and the part it is about."""

    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=2000)
    focus: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$", max_length=200)


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
_SupplierCode = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,47}$")]
_PoRef = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")]


class MasterUploadBody(BaseModel):
    """A master-data workbook: its name and its bytes, base64. Decoded here
    and never opened: the worker reads it in the reader sandbox."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    file_name: Annotated[str, Field(min_length=1, max_length=200)]
    # 10 MiB of bytes, as base64 (`MAX_FILE_BYTES`; the service refuses more).
    content_b64: Annotated[str, Field(min_length=1, max_length=13_981_016)]

    def data(self) -> bytes:
        try:
            return base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError):
            raise DomainError(
                "nội dung tệp không hợp lệ", details={"rule": "file_encoding"}
            ) from None


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

    async def any_reader(context: Ctx, svc: Svc) -> None:
        """Every case, or a requester's own: the service narrows which."""
        if not svc.requests.gate.allows(context, PurchasingScopes.REQUEST_READ):
            await svc.requests.gate.require(context, PurchasingScopes.REQUEST_READ_OWN)

    async def case_reader(context: Ctx, svc: Svc) -> None:
        """A reader, or an approver: the service gives an approver only the
        one case waiting on the scope they hold, and 404 for any other."""
        gate = svc.requests.gate
        if not any(gate.allows(context, s) for s in _APPROVERS):
            await any_reader(context, svc)

    read = [scope(PurchasingScopes.REQUEST_READ)]
    reader = [Depends(any_reader)]
    one_case = [Depends(case_reader)]
    create = [scope(PurchasingScopes.REQUEST_CREATE)]
    intake = [scope(PurchasingScopes.REQUEST_INTAKE)]
    submit = [scope(PurchasingScopes.REQUEST_SUBMIT)]
    rfq = [scope(PurchasingScopes.RFQ_PREPARE)]
    po = [scope(PurchasingScopes.PO_PREPARE)]
    download = [scope(PurchasingScopes.PO_DOWNLOAD)]
    propose = [scope(PurchasingScopes.RULES_PROPOSE)]

    def any_of(*needed: PurchasingScopes) -> Any:
        async def guard(context: Ctx, svc: Svc) -> None:
            await svc.requests.gate.require_any(context, *needed)

        return [Depends(guard)]

    rules_reader = any_of(PurchasingScopes.RULES_PROPOSE, PurchasingScopes.RULES_APPROVE)
    switches_reader = any_of(
        PurchasingScopes.REQUEST_READ,
        PurchasingScopes.RULES_PROPOSE,
        PurchasingScopes.RULES_APPROVE,
    )

    @router.get("/requests", response_model=CasePage, dependencies=reader)
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

    @router.post("/requests/mine/draft", response_model=DraftView, dependencies=create)
    async def draft_my_request(body: WordsBody, context: Ctx, svc: Svc) -> DraftView:
        return await svc.requester.draft(context, body.words)

    @router.post("/requests/mine", response_model=CaseChange, status_code=201, dependencies=create)
    async def send_my_request(body: MyRequest, context: Ctx, svc: Svc, idem: Idem) -> CaseChange:
        change = await svc.requester.submit(context, body)
        return await idem.record(change, status_code=201)

    @router.get("/requests/{case_id}", response_model=PurchaseCase, dependencies=one_case)
    async def get_request(case_id: uuid.UUID, context: Ctx, svc: Svc) -> PurchaseCase:
        return await svc.requests.case(context, case_id)

    @router.post("/requests", response_model=CaseChange, status_code=201, dependencies=intake)
    async def submit_request(
        body: PurchaseRequest, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.requests.submit_form(context, body)
        return await idem.record(change, status_code=201)

    @router.post("/requests/{case_id}/review", response_model=CaseChange, dependencies=intake)
    async def review_request(
        case_id: uuid.UUID, body: CaseVersionBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.requests.reviewed(context, case_id, case_version=body.case_version)
        return await idem.record(change)

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
        case_id: uuid.UUID, body: RfqBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.sourcing.draft_rfq(
            context, case_id, case_version=body.case_version, named=body.suppliers
        )
        return await idem.record(change)

    @router.post(
        "/requests/{case_id}/rfq/{supplier_code}",
        response_model=CaseChange,
        dependencies=rfq,
    )
    async def write_rfq(
        case_id: uuid.UUID,
        supplier_code: _SupplierCode,
        body: RfqWordsBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChange:
        change = await svc.sourcing.write_rfq(
            context,
            case_id,
            supplier_code,
            subject=body.subject,
            body=body.body,
            case_version=body.case_version,
        )
        return await idem.record(change)

    @router.get("/suppliers", response_model=list[SupplierName], dependencies=rfq)
    async def suppliers(context: Ctx, svc: Svc) -> list[SupplierName]:
        return await svc.sourcing.suppliers(context)

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

    @router.post(
        "/requests/{case_id}/po/{po_ref}/bravo-number", response_model=CaseChange, dependencies=po
    )
    async def record_bravo_no(
        case_id: uuid.UUID, po_ref: _PoRef, body: BravoNoBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.follow_up.record_bravo_no(
            context, case_id, po_ref, body.bravo_no, case_version=body.case_version
        )
        return await idem.record(change)

    @router.get(
        "/requests/{case_id}/po/confirmations",
        response_model=list[ConfirmationMail],
        dependencies=po,
    )
    async def confirmation_mails(
        case_id: uuid.UUID, context: Ctx, svc: Svc
    ) -> list[ConfirmationMail]:
        return await svc.follow_up.confirmation_mails(context, case_id)

    @router.post(
        "/requests/{case_id}/po/confirmations/from-mail/{message_id}",
        response_model=CaseChange,
        dependencies=po,
    )
    async def read_confirmation(
        case_id: uuid.UUID,
        message_id: _MessageId,
        body: CaseVersionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChange:
        change = await svc.follow_up.read_confirmation(
            context, case_id, message_id, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/requests/{case_id}/po/{po_ref}/confirmation/accept",
        response_model=CaseChange,
        dependencies=po,
    )
    async def accept_confirmation(
        case_id: uuid.UUID,
        po_ref: _PoRef,
        body: CaseVersionBody,
        context: Ctx,
        svc: Svc,
        idem: Idem,
    ) -> CaseChange:
        change = await svc.follow_up.accept_confirmation(
            context, case_id, po_ref, case_version=body.case_version
        )
        return await idem.record(change)

    @router.post(
        "/requests/{case_id}/po/{po_ref}/receipts", response_model=CaseChange, dependencies=po
    )
    async def record_receipt(
        case_id: uuid.UUID, po_ref: _PoRef, body: ReceiptBody, context: Ctx, svc: Svc, idem: Idem
    ) -> CaseChange:
        change = await svc.follow_up.record_receipt(
            context,
            case_id,
            po_ref,
            line_no=body.line_no,
            quantity=body.quantity,
            received_on=body.received_on,
            case_version=body.case_version,
        )
        return await idem.record(change)

    # DW02 function 6: status questions, in the asker's own sessions. Any
    # reader of requests asks; the service narrows what each may see.
    @router.post("/assistant/ask", response_model=AssistantAnswerView, dependencies=reader)
    async def assistant_ask(
        body: AssistantAskBody, context: Ctx, svc: Svc, idem: Idem
    ) -> AssistantAnswerView:
        answer = await svc.assistant.ask(context, body.question.strip(), body.session_id)
        return await idem.record(answer)

    @router.get(
        "/assistant/sessions", response_model=list[AssistantSessionView], dependencies=reader
    )
    async def assistant_sessions(context: Ctx, svc: Svc) -> list[AssistantSessionView]:
        return await svc.assistant.sessions(context)

    @router.get(
        "/assistant/sessions/{session_id}",
        response_model=AssistantSessionDetailView,
        dependencies=reader,
    )
    async def assistant_session(
        session_id: uuid.UUID, context: Ctx, svc: Svc
    ) -> AssistantSessionDetailView:
        return await svc.assistant.session(context, session_id)

    @router.get("/orders/late", response_model=list[LateLine], dependencies=po)
    async def late_lines(context: Ctx, svc: Svc) -> list[LateLine]:
        return await svc.follow_up.late(context)

    @router.get("/requests/{case_id}/po/bravo.xlsx", dependencies=download)
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

    @router.get("/automation", response_model=SwitchesView, dependencies=switches_reader)
    async def automation(context: Ctx, svc: Svc) -> SwitchesView:
        return await svc.switches.view(context)

    @router.get("/rules", response_model=PurchasingRulesView, dependencies=rules_reader)
    async def rules_in_force(context: Ctx, svc: Svc) -> PurchasingRulesView:
        return await svc.rules.list(context)

    @router.get("/rules/{key}/schema", dependencies=propose)
    async def rule_schema(key: _RuleKey, context: Ctx, svc: Svc) -> dict[str, Any]:
        return await svc.rules.schema(context, key)

    @router.post("/rules/{key}/words", response_model=WordsDraft, dependencies=propose)
    async def rule_in_words(
        key: _RuleKey, body: PurchasingRuleWordsBody, context: Ctx, svc: Svc
    ) -> WordsDraft:
        return await svc.words.draft(context, key, body.request, body.focus)

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

    @router.get("/requests/{case_id}/rfq/replies", response_model=list[ReplyItem], dependencies=rfq)
    async def rfq_replies(case_id: uuid.UUID, context: Ctx, svc: Svc) -> list[ReplyItem]:
        return await svc.sourcing.replies(context, case_id)

    @router.post(
        "/requests/{case_id}/rfq/{supplier_code}/send",
        response_model=RfqMailView,
        status_code=202,
        dependencies=rfq,
    )
    async def send_rfq(
        case_id: uuid.UUID, supplier_code: _SupplierCode, context: Ctx, svc: Svc, idem: Idem
    ) -> RfqMailView:
        mail = await svc.rfq_mails.send(context, case_id, supplier_code)
        return await idem.record(mail, status_code=202)

    @router.get(
        "/requests/{case_id}/rfq/mails",
        response_model=list[RfqMailView],
        dependencies=any_of(PurchasingScopes.REQUEST_READ, PurchasingScopes.RFQ_PREPARE),
    )
    async def rfq_mails(case_id: uuid.UUID, context: Ctx, svc: Svc) -> list[RfqMailView]:
        return await svc.rfq_mails.of_case(context, case_id)

    @router.get("/master-data", response_model=MasterDataView, dependencies=rules_reader)
    async def master_data(context: Ctx, svc: Svc) -> MasterDataView:
        return await svc.master_data.overview(context)

    @router.get("/master-data/template.xlsx", dependencies=propose)
    async def master_template(context: Ctx, svc: Svc) -> Response:
        return Response(
            content=await svc.master_data.template_file(context),
            media_type=_XLSX,
            headers={
                "Content-Disposition": 'attachment; filename="du-lieu-chu-dw2.xlsx"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post(
        "/master-data/imports",
        response_model=MasterImportView,
        status_code=202,
        dependencies=propose,
    )
    async def master_upload(
        body: MasterUploadBody, context: Ctx, svc: Svc, idem: Idem
    ) -> MasterImportView:
        view = await svc.master_data.upload(context, body.file_name, body.data())
        return await idem.record(view, status_code=202)

    @router.get(
        "/master-data/imports/{import_id}",
        response_model=MasterImportView,
        dependencies=rules_reader,
    )
    async def master_import(import_id: uuid.UUID, context: Ctx, svc: Svc) -> MasterImportView:
        return await svc.master_data.get(context, import_id)

    @router.post(
        "/master-data/imports/{import_id}/submit",
        response_model=MasterImportView,
        dependencies=propose,
    )
    async def master_submit(
        import_id: uuid.UUID, context: Ctx, svc: Svc, idem: Idem
    ) -> MasterImportView:
        return await idem.record(await svc.master_data.submit(context, import_id))

    return router
