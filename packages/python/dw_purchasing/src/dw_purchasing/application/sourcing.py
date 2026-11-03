"""Asking suppliers, recording what they offer, choosing (DW02 function 3).

- **Draft the RFQs** (`draft_rfq`, an approved request): code picks the
  suppliers per line from the master data (`domain.sourcing.suppliers_for`,
  at most the rules' number), the recipients are each supplier's contacts,
  and the reply date is the rules'. The model words each mail from code's
  facts (`purchasing.rfq_mail@1.0.0`); the words are kept only when every
  figure is in the facts and no amount is named; else the draft waits for a
  buyer to write it (`write_rfq`), never a fixed template. Nothing is sent: a
  buyer sends each draft.
- **Record an offer**: typed by a buyer (`record_offer`), or read from a
  supplier's reply (`read_offer_mail`). A reply counts only from a verified
  sender whose domain is one of an asked supplier's; the model copies spans
  (`purchasing.supplier_quote_reading@1.0.0`), code ties them to the lines that
  supplier was asked for and parses them. A reply is read once.
- **Compare** (`comparison`): code's, cheapest valid offer first per line.
- **Choose** (`select`): a person picks one offer per line; the total is held
  to the most the approver's tier decides (stamped when the request was sent).
  Past it, the choice is refused: the request needs a higher approver.

Nothing a supplier wrote ranks, selects or sends anything.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.figure_check import names_amount, unsupported
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.mail_parts import newest_part
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import NOT_READ_NOW, CaseChange, Worker
from dw_purchasing.application.ports import InboxPort, MasterDataPort, PurchasingUnitOfWork
from dw_purchasing.application.reapprovals import Reapprovals, over_limit
from dw_purchasing.application.rules import PurchasingRuleBook
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase
from dw_purchasing.domain.checks import MasterData, Supplier
from dw_purchasing.domain.mail_reading import fold
from dw_purchasing.domain.offer_reading import MAX_OFFER_LINES, ModelOffer, read_offer_mail
from dw_purchasing.domain.requests import Code, Currency, Price, PrLine
from dw_purchasing.domain.sourcing import (
    Choice,
    ComparedLine,
    Offer,
    RfqDraft,
    RfqRound,
    Selection,
    compare,
    suppliers_for,
    valid_offers,
    with_named,
)

RFQ_MAIL: Final = PromptRef("purchasing.rfq_mail", "1.0.0")
SUPPLIER_QUOTE_READING: Final = PromptRef("purchasing.supplier_quote_reading", "1.0.0")
# Names that hold a digit and are no figure: the Digital Worker's own.
DW_NAMES: Final = frozenset({"DW2"})
_RESOURCE: Final = "purchase_case"
_PROMPT_TOKENS: Final = 1200
_OFFER_TOKENS: Final = 120 * MAX_OFFER_LINES + 100
_RFQ_TOKENS: Final = 900
# How many cases still asking a reply is matched among: far above a plant's.
_ASKING: Final = 500
NO_RFQ_RULES: Final = "quy tắc mua hàng đang áp dụng chưa có quy tắc hỏi giá: chưa soạn RFQ được"


class RfqWording(BaseModel):
    """What the model writes for one RFQ."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)


class SupplierName(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str


class OfferForm(BaseModel):
    """An offer a buyer types (a supplier answered by phone, or on paper)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supplier_code: Code
    line_no: int = Field(ge=1)
    unit_price: Price
    currency: Currency
    lead_time_days: int = Field(ge=0, le=365)
    valid_until: date | None = None


class ReplyItem(BaseModel):
    """A mail that answers one of the case's RFQs, as the offer card lists it."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender: str
    subject: str
    received_at: datetime
    supplier_code: str


class ComparisonView(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    case_version: int
    currency: str
    lines: tuple[ComparedLine, ...]
    # The most the approver's tier decides; None: no limit.
    approved_limit: Decimal | None


@dataclass(frozen=True)
class SupplierSourcing:
    uow: PurchasingUnitOfWork
    gate: Gate
    rules: PurchasingRuleBook
    master: MasterDataPort
    inbox: InboxPort
    # None where the deployment has no model: a buyer writes each RFQ, and a
    # reply is typed rather than read.
    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator
    # Where a choice past the approved tier goes back for approval; None:
    # such a choice is refused, as before rules 1.5.0.
    reapprovals: Reapprovals | None = None

    # ----------------------------------------------------------- the RFQ --

    async def draft_rfq(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        named: Sequence[Choice] = (),
    ) -> CaseChange:
        """The RFQs of an approved request: to the suppliers the master data
        lists for each line, and to those the buyer ``named`` (a line nobody
        is listed for, a supplier more for a line)."""
        await self._require(context, case_id)
        case = await self._case(context, case_id, case_version, CaseStatus.APPROVED)
        rules = await self.rules.resolve(context)
        if rules.rfq is None:
            raise ConflictError(NO_RFQ_RULES, details={"rules_ref": rules.ref, "rule": "no_rfq"})
        master = await self.master.for_context(context)
        most = rules.rfq.max_suppliers_per_line
        asked, unsourced = suppliers_for(case.request, master, most=most)
        try:
            asked, unsourced = with_named(asked, unsourced, named, case.request, master, most=most)
        except ValueError as exc:
            raise DomainError(
                "nhà cung cấp được chọn không hợp lệ cho yêu cầu này",
                details={"case_id": str(case_id), "rule": str(exc)},
            ) from None
        if not asked:
            raise ConflictError(
                "không nhà cung cấp nào trong dữ liệu chủ cung cấp các mặt hàng này",
                details={"case_id": str(case_id), "rule": "no_supplier"},
            )
        today = self.clock.now().date()
        reply_by = today + timedelta(days=rules.rfq.reply_days)
        drafts = []
        for code, line_nos in sorted(asked.items()):
            supplier = master.supplier(code)
            assert supplier is not None  # `suppliers_for` keeps only known ones
            lines = [line for line in case.request.lines if line.line_no in line_nos]
            drafts.append(await self._draft(context, case, supplier, lines, _day(reply_by)))
        round_ = RfqRound(
            drafted_by=context.principal_id,
            drafted_at=self.clock.now(),
            reply_by=reply_by,
            drafts=tuple(drafts),
            unsourced=tuple(unsourced),
        )
        drafted = _moved(case, CaseStatus.RFQ_DRAFTED, rfq=round_)
        await self._save(
            context,
            case,
            drafted,
            "purchasing.rfq.drafted",
            {"suppliers": ",".join(d.supplier_code for d in drafts)},
        )
        return _change(drafted)

    async def write_rfq(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        supplier_code: str,
        *,
        subject: str,
        body: str,
        case_version: int,
    ) -> CaseChange:
        """A buyer's own words for one supplier's RFQ: one DW2 could not write,
        or the model's changed. Nothing is sent; the buyer sends it."""
        await self._require(context, case_id)
        case = await self._case(context, case_id, case_version, CaseStatus.RFQ_DRAFTED)
        assert case.rfq is not None  # an RFQ_DRAFTED case holds its round
        drafts = list(case.rfq.drafts)
        at = next((i for i, d in enumerate(drafts) if d.supplier_code == supplier_code), None)
        if at is None:
            raise NotFoundError(
                "nhà cung cấp này không có thư hỏi giá trong hồ sơ",
                details={"case_id": str(case_id), "supplier_code": supplier_code},
            )
        if not subject.strip() or not body.strip():
            raise DomainError(
                "thư hỏi giá cần cả tiêu đề và nội dung",
                details={"case_id": str(case_id), "rule": "rfq_words_empty"},
            )
        drafts[at] = drafts[at].model_copy(
            update={"subject": subject.strip(), "body": body.strip(), "written_by": "person"}
        )
        rfq = case.rfq.model_copy(update={"drafts": tuple(drafts)})
        written = _moved(case, CaseStatus.RFQ_DRAFTED, rfq=rfq)
        await self._save(
            context, case, written, "purchasing.rfq.written", {"supplier": supplier_code}
        )
        return _change(written)

    async def _draft(
        self,
        context: AccessContext,
        case: PurchaseCase,
        supplier: Supplier,
        lines: Sequence[PrLine],
        reply_by: str,
    ) -> RfqDraft:
        facts = {
            "supplier": supplier.name,
            "request": case.request.pr_no,
            "reply_by": reply_by,
            "lines": [
                {
                    "item_code": line.item_code,
                    "description": line.description,
                    "quantity": f"{line.quantity.normalize():f}",
                    "unit": line.unit,
                    "need_by": _day(line.need_by or case.request.need_by),
                }
                for line in lines
            ],
        }
        text = json.dumps(facts, ensure_ascii=False)
        words = await self._words(context, case, text)
        if words is None:
            # No words a person can stand behind: the buyer writes them.
            subject, body, by = "", "", "pending"
        else:
            subject, body, by = words.subject, words.body, "model"
        return RfqDraft(
            supplier_code=supplier.code,
            to=supplier.contacts,
            line_nos=tuple(line.line_no for line in lines),
            subject=subject,
            body=body,
            written_by=by,
        )

    async def _words(
        self, context: AccessContext, case: PurchaseCase, facts: str
    ) -> RfqWording | None:
        """The model's wording, when it holds no figure the facts lack and
        names no amount; None otherwise, or without a model."""
        if self.model is None:
            return None
        try:
            words = await self.model.interpret(
                RFQ_MAIL,
                {"facts": facts},
                RfqWording,
                run=self._run(context, f"purchase_case:{case.case_id}", "dw2-rfq"),
                max_output_tokens=_RFQ_TOKENS,
            )
        except ModelUnavailableError:
            return None
        written = f"{words.subject}\n{words.body}"
        if unsupported(written, facts, names=DW_NAMES) or names_amount(written):
            return None
        return words

    # --------------------------------------------------------- the offers --

    async def record_offer(
        self, context: AccessContext, case_id: uuid.UUID, form: OfferForm, *, case_version: int
    ) -> CaseChange:
        await self._require(context, case_id)
        case = await self._case(context, case_id, case_version, CaseStatus.RFQ_DRAFTED)
        master = await self.master.for_context(context)
        if master.supplier(form.supplier_code) is None:
            raise NotFoundError(
                "không có nhà cung cấp này", details={"supplier_code": form.supplier_code}
            )
        if form.line_no not in {line.line_no for line in case.request.lines}:
            raise NotFoundError("không có dòng này", details={"line_no": str(form.line_no)})
        offer = Offer(
            supplier_code=form.supplier_code,
            line_no=form.line_no,
            unit_price=form.unit_price,
            currency=form.currency,
            lead_time_days=form.lead_time_days,
            valid_until=form.valid_until,
            source="form",
            recorded_by=context.principal_id,
            recorded_at=self.clock.now(),
        )
        recorded = _moved(case, case.status, offers=(*case.offers, offer))
        await self._save(
            context, case, recorded, "purchasing.offer.recorded", {"supplier": offer.supplier_code}
        )
        return _change(recorded)

    async def read_offer_mail(
        self, context: AccessContext, case_id: uuid.UUID, message_id: str, *, case_version: int
    ) -> CaseChange:
        await self._require(context, case_id)
        case = await self._case(context, case_id, case_version, CaseStatus.RFQ_DRAFTED)
        message = await self.inbox.get_message(context, message_id)
        if message is None:
            raise NotFoundError("không có thư này", details={"message_id": message_id})
        if any(o.source_ref == message_id for o in case.offers):
            raise ConflictError(
                "thư báo giá này đã được đọc", details={"message_id": message_id, "rule": "read"}
            )
        assert case.rfq is not None
        master = await self.master.for_context(context)
        supplier = _replying(case.rfq, master, message.sender.domain)
        if supplier is None or not message.authentication.verified:
            raise ConflictError(
                "thư không phải của một nhà cung cấp đã được hỏi giá, hoặc chưa xác thực",
                details={
                    "message_id": message_id,
                    "rule": "sender_not_asked" if supplier is None else "sender_unverified",
                },
            )
        draft = case.rfq.asked(supplier.code)
        assert draft is not None
        asked = {
            line.item_code: line.line_no
            for line in case.request.lines
            if line.line_no in draft.line_nos and line.item_code is not None
        }
        if self.model is None:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "no_model"})
        part = newest_part(message)
        shown = cut_to_tokens(
            part.text, self.model.max_input_tokens - _PROMPT_TOKENS - _OFFER_TOKENS
        )
        try:
            answer = await self.model.interpret(
                SUPPLIER_QUOTE_READING,
                {"mail": shown},
                ModelOffer,
                run=self._run(context, f"purchasing_mail:{message_id}", "dw2-offer-mail"),
                max_output_tokens=_OFFER_TOKENS,
            )
        except ModelUnavailableError as exc:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "model"}) from exc
        verdict = read_offer_mail(
            shown,
            answer,
            asked=asked,
            received_on=message.received_at.date(),
            currency=case.request.currency,
        )
        if verdict.not_read is not None:
            raise ConflictError(
                "DW2 không đọc được báo giá trong thư: nhập tay",
                details={"message_id": message_id, "rule": verdict.not_read},
            )
        now = self.clock.now()
        offers = tuple(
            Offer(
                supplier_code=supplier.code,
                line_no=read.line_no,
                unit_price=read.unit_price,
                currency=read.currency,
                lead_time_days=read.lead_time_days,
                valid_until=read.valid_until,
                source="mail",
                source_ref=message_id,
                recorded_by=context.principal_id,
                recorded_at=now,
            )
            for read in verdict.offers
        )
        recorded = _moved(case, case.status, offers=(*case.offers, *offers))
        await self._save(
            context,
            case,
            recorded,
            "purchasing.offer.read",
            {"supplier": supplier.code, "message_id": message_id, "lines": len(offers)},
        )
        return _change(recorded)

    # ---------------------------------------------------- compare, choose --

    async def suppliers(self, context: AccessContext) -> list[SupplierName]:
        """The suppliers the company knows, by code and name, for a buyer to
        name one for a line: no contact address, no price."""
        await self.gate.require(context, PurchasingScopes.RFQ_PREPARE, resource_type="supplier")
        master = await self.master.for_context(context)
        return [
            SupplierName(code=s.code, name=s.name)
            for s in sorted(master.suppliers, key=lambda s: s.code)
        ]

    async def replies(self, context: AccessContext, case_id: uuid.UUID) -> list[ReplyItem]:
        """The mails in the mailbox that answer this case's RFQs
        (`reply_case`): from a supplier it asked, the sender verified by the
        mail system, not yet read into it. What the offer card offers first."""
        await self._require(context, case_id)
        case = await self._get(context, case_id)
        if case.status is not CaseStatus.RFQ_DRAFTED or case.rfq is None:
            return []
        async with self.uow(context) as work:
            asking = await work.cases.waiting(
                frozenset({CaseStatus.RFQ_DRAFTED.value}), limit=_ASKING
            )
        master = await self.master.for_context(context)
        read = {o.source_ref for o in case.offers if o.source_ref}
        found: list[ReplyItem] = []
        for message in await self.inbox.list_messages(context):
            if message.message_id in read or not message.authentication.verified:
                continue
            supplier = _replying(case.rfq, master, message.sender.domain)
            if supplier is None:
                continue
            text = f"{message.subject}\n{newest_part(message).text}"
            answered = reply_case(asking, master, message.sender.domain, text)
            if answered is None or answered.case_id != case.case_id:
                continue
            found.append(
                ReplyItem(
                    message_id=message.message_id,
                    sender=message.sender.address,
                    subject=message.subject,
                    received_at=message.received_at,
                    supplier_code=supplier.code,
                )
            )
        return found

    async def comparison(self, context: AccessContext, case_id: uuid.UUID) -> ComparisonView:
        await self.gate.require(
            context,
            PurchasingScopes.REQUEST_READ,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )
        case = await self._get(context, case_id)
        if case.approval is None:
            raise ConflictError("yêu cầu chưa được duyệt", details={"case_id": str(case_id)})
        return ComparisonView(
            case_id=case.case_id,
            case_version=case.case_version,
            currency=case.request.currency,
            lines=compare(case.request, case.offers, on=self.clock.now().date()),
            approved_limit=case.approval.limit,
        )

    async def select(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        choices: Sequence[Choice],
        *,
        case_version: int,
    ) -> CaseChange:
        await self._require(context, case_id)
        case = await self._case(context, case_id, case_version, CaseStatus.RFQ_DRAFTED)
        assert case.approval is not None
        lines = {line.line_no: line for line in case.request.lines}
        if sorted(c.line_no for c in choices) != sorted(lines):
            raise ConflictError(
                "chọn đúng một nhà cung cấp cho mỗi dòng",
                details={"case_id": str(case_id), "rule": "one_per_line"},
            )
        usable = {
            (o.supplier_code, o.line_no): o
            for o in valid_offers(
                case.offers, on=self.clock.now().date(), currency=case.request.currency
            )
        }
        total = Decimal(0)
        for choice in choices:
            offer = usable.get((choice.supplier_code, choice.line_no))
            if offer is None:
                raise ConflictError(
                    "không có báo giá còn hiệu lực của nhà cung cấp này cho dòng này",
                    details={"line_no": str(choice.line_no), "rule": "no_offer"},
                )
            total += offer.unit_price * lines[choice.line_no].quantity
        selection = Selection(
            choices=tuple(sorted(choices, key=lambda c: c.line_no)),
            total=total,
            currency=case.request.currency,
            selected_by=context.principal_id,
            selected_at=self.clock.now(),
        )
        rules = (await self.rules.resolve(context)).approval
        if over_limit(case, total, rules):
            if rules is None or self.reapprovals is None:
                raise ConflictError(
                    "tổng theo nhà cung cấp đã chọn vượt hạn mức người đã duyệt:"
                    " cần duyệt lại bậc cao hơn",
                    details={"case_id": str(case_id), "rule": "exceeds_approved_limit"},
                )
            prices = {(o.supplier_code, o.line_no): o.unit_price for o in usable.values()}
            waiting = await self.reapprovals.ask(context, self.uow, case, selection, rules, prices)
            return _change(waiting)
        selected = _moved(case, CaseStatus.SUPPLIER_SELECTED, selection=selection)
        await self._save(
            context,
            case,
            selected,
            "purchasing.supplier.selected",
            {"suppliers": ",".join(sorted({c.supplier_code for c in choices}))},
        )
        return _change(selected)

    # ------------------------------------------------------------- helpers --

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context,
            PurchasingScopes.RFQ_PREPARE,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )

    async def _get(self, context: AccessContext, case_id: uuid.UUID) -> PurchaseCase:
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        return case

    async def _case(
        self, context: AccessContext, case_id: uuid.UUID, version: int, status: CaseStatus
    ) -> PurchaseCase:
        case = await self._get(context, case_id)
        if case.case_version != version:
            raise ConflictError(
                "hồ sơ đã thay đổi: tải lại",
                details={"case_id": str(case_id), "rule": "stale_version"},
            )
        if case.status is not status:
            raise ConflictError(
                "hồ sơ không ở bước này",
                details={"case_id": str(case_id), "status": case.status.value},
            )
        return case

    async def _save(
        self,
        context: AccessContext,
        before: PurchaseCase,
        after: PurchaseCase,
        action: str,
        details: dict[str, object],
    ) -> None:
        async with self.uow(context) as work:
            await work.cases.save(after, expected_version=before.case_version)
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action=action,
                    resource_type=_RESOURCE,
                    resource_id=str(after.case_id),
                    occurred_at=self.clock.now(),
                    details={"case_version": after.case_version, **details},
                )
            )

    def _run(self, context: AccessContext, subject: str, trace: str) -> RunContext:
        return caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker.worker_id,
            worker_version=self.worker.worker_version,
            trace=trace,
            subject_ref=subject,
        )


def _day(day: date | None) -> str:
    """A date as the mail writes it, day first (``05/11/2026``): the facts
    hold it the way a model will copy it, so the figure check can find it."""
    return "" if day is None else day.strftime("%d/%m/%Y")


def _moved(case: PurchaseCase, status: CaseStatus, **changes: object) -> PurchaseCase:
    return PurchaseCase.model_validate(
        {
            **case.model_dump(),
            "case_version": case.case_version + 1,
            "status": status,
            **changes,
        }
    )


def _change(case: PurchaseCase) -> CaseChange:
    return CaseChange(case_id=case.case_id, case_version=case.case_version, status=case.status)


def reply_case(
    cases: Sequence[PurchaseCase], master: MasterData, domain: str, text: str
) -> PurchaseCase | None:
    """The case a supplier's mail answers, decided by code: the one case
    still asking (`rfq_drafted`) that asked a supplier this domain is one of
    and whose PR number the mail names (an RFQ's subject carries it, and a
    reply keeps it). A supplier writes about other things too, a request of
    its own or another order: anything else is None, and a buyer picks."""
    folded = fold(text)
    asking = [
        c
        for c in cases
        if c.status is CaseStatus.RFQ_DRAFTED
        and c.rfq is not None
        and _replying(c.rfq, master, domain) is not None
        and fold(c.request.pr_no) in folded
    ]
    return asking[0] if len(asking) == 1 else None


def _replying(rfq: RfqRound, master: MasterData, domain: str) -> Supplier | None:
    """The asked supplier whose domain the reply came from; None for anyone
    else, or when two asked suppliers share it."""
    asked = [master.supplier(d.supplier_code) for d in rfq.drafts]
    found = [s for s in asked if s is not None and domain in s.domains]
    return found[0] if len(found) == 1 else None
