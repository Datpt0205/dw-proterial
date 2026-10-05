"""Order intake: what each message is, and what becomes of it.

`OrderIntake.process` gives every message it owns exactly one disposition
(spec decision 10): a PO opens an order case or joins the case of the PO it
revises; anything else is routed to Sales with its reason and an owner. A
quote request or a Design reply is handed to the quotation flow, which gives
it its disposition (ticket 03); `IntakeOutcome.disposition` is then None and
the outcome says so.

**Code rules, not a model.** The spec keeps every model away from real
customer documents in this slice, so routing is keywords over the subject and
the attachment names, then the body. Keywords miss any phrasing nobody listed;
what keeps that safe is where a miss lands: routed to Sales as ``other``. No
keyword sets a value.

**The body never changes a value.** Customer, items, quantities, prices and
dates come from the sender's domain (or, for a forwarded PO, the buyer the
document names, which Sales then confirms), the attachment's cells and the
master data. The body is read for routing alone, and only when the subject
and the attachment names say nothing.

**A file is what its bytes say.** Attachments are routed by sniffing their
content, never by their name or the media type the sender declared.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dw_kernel.errors import ConflictError
from dw_sales.application.order_ports import (
    OrderCaseLookupPort,
    OrderRulesPort,
    PoDocumentReaderPort,
)
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import Customer, LmeMonth, customers_named
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.messages import AttachmentContent, InboundMessage
from dw_sales.domain.order_checks import (
    IntakeCaps,
    MappedLine,
    OrderRules,
    check_customer,
    check_document,
    check_history,
    check_line,
    current_quotation,
    map_line,
)
from dw_sales.domain.orders import (
    Actor,
    Finding,
    LineCheck,
    OrderCase,
    OrderStatus,
    PoDocument,
    PoHeader,
    PoLine,
    Unreadable,
)


class MessageKind(StrEnum):
    PO = "po"
    REVISED_PO = "revised_po"
    QUOTE_REQUEST = "quote_request"
    DESIGN_REPLY = "design_reply"
    OTHER = "other"


# Handed to the quotation flow, which gives them their disposition.
QUOTATION_KINDS = frozenset({MessageKind.QUOTE_REQUEST, MessageKind.DESIGN_REPLY})

# Matched against NFKC-normalised, casefolded text, in English, Vietnamese and
# the Japanese the customers' own systems print.
_QUOTE_REQUEST = re.compile(
    r"\brfq\b|request for (?:quotation|quote)|(?:quotation|quote) request"
    r"|yêu cầu báo giá|đề nghị báo giá|見積(?:もり|り)?依頼"
)
# Design's reply quotes the YCBG number; matching it to a request is ticket 03's.
_DESIGN_REPLY = re.compile(r"\bycbg\b")
_PURCHASE_ORDER = re.compile(r"\bpo\b|purchase order|đơn đặt hàng|đơn hàng|注文書|発注書")
# "Rev.1", "rev1", "revised", "revision", but not "review" or "revenue".
_REVISED = re.compile(r"\brev(?:ised|ision)?(?![a-z])|\bamend(?:ed|ment)?\b|sửa đổi|訂正|改訂")
# Why a message that is no PO and no quote goes to Sales, first match wins.
_ROUTES: tuple[tuple[RoutingReason, re.Pattern[str]], ...] = (
    (RoutingReason.COMPLAINT, re.compile(r"khiếu nại|\bcomplaint\b|苦情|クレーム")),
    (RoutingReason.SAMPLE_REQUEST, re.compile(r"hàng mẫu|\bsamples?\b|サンプル")),
    (
        RoutingReason.DELIVERY_CHANGE,
        re.compile(r"lịch giao|giao sớm|delivery (?:schedule|date)|reschedul|納期"),
    ),
)


@dataclass(frozen=True)
class IntakeOutcome:
    """What processing one message did.

    ``disposition`` is None only for a message handed to the quotation flow
    (`QUOTATION_KINDS`). ``case`` is the order case to store: the one created,
    or the case a revision joined, as it now stands.
    """

    message_id: str
    kind: MessageKind
    disposition: MessageDisposition | None
    case: OrderCase | None = None


@dataclass(frozen=True)
class _Attached:
    attachment_id: str
    content: AttachmentContent | None


@dataclass(frozen=True)
class OrderIntake:
    catalog: SalesCatalogPort
    inbox: InboxPort
    reader: PoDocumentReaderPort
    rules: OrderRulesPort
    cases: OrderCaseLookupPort
    new_case_id: Callable[[], uuid.UUID]

    async def classify(self, scope: SalesScope, message: InboundMessage) -> MessageKind:
        return self._kind(message, await self._attachments(scope, message))

    async def process(self, scope: SalesScope, message: InboundMessage) -> IntakeOutcome:
        """The message's disposition, and the order case it created or revised.

        Refused with a conflict when this message already has a case: that is
        processing twice, not a duplicate PO.
        """
        attached = await self._attachments(scope, message)
        kind = self._kind(message, attached)
        if kind in QUOTATION_KINDS:
            return IntakeOutcome(message.message_id, kind, None)
        sender = (await self.catalog.customer_by_email_domain(scope, message.sender.domain)).data
        if kind is MessageKind.OTHER:
            return self._routed(message, kind, _other_reason(message), sender)
        return await self._order(scope, message, kind, sender, attached)

    # ------------------------------------------------------------ orders --

    async def _order(
        self,
        scope: SalesScope,
        message: InboundMessage,
        kind: MessageKind,
        sender: Customer | None,
        attached: Sequence[_Attached],
    ) -> IntakeOutcome:
        rules = await self.rules.rules(scope)
        caps = rules.intake
        readable: list[AttachmentContent] = []
        reasons: list[str] = []
        for item in attached:
            content = item.content
            if content is None:
                reasons.append(f"{item.attachment_id}: not in the mailbox")
                continue
            file_type = self.reader.sniff(content.data)
            if file_type is None:
                continue
            if content.attachment.size > caps.max_attachment_bytes:
                reasons.append(f"{item.attachment_id}: over the size read here")
            elif file_type == "unsupported":
                reasons.append(f"{item.attachment_id}: a format this slice does not read")
            else:
                readable.append(content)
        unreadable = RoutingReason.ATTACHMENT_UNREADABLE
        if not readable:
            return self._routed(message, kind, unreadable, sender, "; ".join(reasons))

        customer, attributed = sender, False
        if customer is None:
            customer = await self._buyer(scope, readable, caps)
            if customer is None:
                return self._routed(
                    message,
                    kind,
                    RoutingReason.CUSTOMER_UNKNOWN,
                    None,
                    "the sender's domain and the buyer the document names match no customer",
                )
            attributed = True

        documents: list[PoDocument] = []
        for content in readable:
            result = await self.reader.read(content, customer.code, caps)
            if isinstance(result, Unreadable):
                reasons.append(f"{content.attachment.attachment_id}: {result.reason}")
            else:
                documents.append(result)
        if not documents:
            return self._routed(message, kind, unreadable, customer, "; ".join(reasons))
        if len(documents) > 1:
            # Two orders, or one order twice (an Excel file and its PDF print):
            # either way Sales decides which is entered.
            ids = ", ".join(d.attachment_id for d in documents)
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                customer,
                f"more than one attachment reads as a PO: {ids}",
            )
        return await self._case(scope, message, kind, customer, attributed, documents[0], rules)

    async def _case(
        self,
        scope: SalesScope,
        message: InboundMessage,
        kind: MessageKind,
        customer: Customer,
        attributed: bool,
        document: PoDocument,
        rules: OrderRules,
    ) -> IntakeOutcome:
        header = document.header
        earlier = await self.cases.cases_for_po(scope, customer.code, header.po_no)
        seen = {
            message_id
            for case in earlier
            for message_id in (case.message_id, *(old.message_id for old in case.superseded))
        }
        if message.message_id in seen:
            raise ConflictError(
                "this message already has an order case",
                details={"message_id": message.message_id},
            )

        items = await self.catalog.items(scope)
        lme = await self.catalog.lme_for_month(scope, rules.lme_month(header.po_date))
        as_of: list[datetime] = [items.as_of, lme.as_of]
        checks: list[LineCheck] = []
        for po_line in document.lines:
            entry = await self.catalog.convert_entry(
                scope, customer.code, po_line.customer_item_code
            )
            as_of.append(entry.as_of)
            mapped = map_line(po_line, entry=entry.data, items=items.data)
            check, quoted_as_of = await self._check_line(
                scope, customer.code, header, message.received_at, po_line, mapped, lme.data, rules
            )
            as_of.extend(quoted_as_of)
            checks.append(check)
        orders = await self.catalog.orders_for_po(scope, customer.code, header.po_no)
        as_of.append(orders.as_of)
        history = check_history(
            customer.code,
            document,
            {c.line.line_no: c.line.mapping.checked_against for c in checks},
            earlier,
            orders.data,
            rules=rules,
        )
        if history.stale:
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                customer,
                f"revision {header.revision} is older than the case for this PO holds",
            )
        findings: list[Finding] = [] if history.finding is None else [history.finding]
        findings.extend(
            check_customer(
                customer,
                attributed_by_document=attributed,
                authentication=message.authentication,
                po_date=header.po_date,
                received_at=message.received_at,
                rules=rules,
            )
        )
        findings.extend(check_document(document, rules))
        for check in checks:
            findings.extend(check.findings)

        received = OrderCase(
            case_id=self.new_case_id(),
            case_version=1,
            customer_code=customer.code,
            message_id=message.message_id,
            received_at=message.received_at,
            document=document,
            lines=tuple(check.line for check in checks),
            status=OrderStatus.RECEIVED,
        )
        checked = received.checked(
            findings=findings,
            rules_version=rules.version,
            # The oldest snapshot any check read: nothing was checked against
            # data newer than this.
            catalog_as_of=min(as_of),
            cross_check_required=rules.cross_check_required,
            export_control_mode=rules.export_control_mode,
            duplicate_of_case=history.duplicate_of_case,
            duplicate_of_so=history.duplicate_of_so,
            base_so_no=history.base_so_no,
        )
        if history.base is None:
            return self._on_case(message, kind, DispositionKind.CASE_CREATED, checked)
        try:
            revised = history.base.revise(checked)
        except ConflictError:
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                customer,
                f"a revision of a case in {history.base.status}, which takes none",
            )
        return self._on_case(message, kind, DispositionKind.ATTACHED_TO_CASE, revised)

    async def confirm_mapping(
        self,
        scope: SalesScope,
        case: OrderCase,
        line_no: int,
        prv_code: str,
        actor: Actor,
        at: datetime,
    ) -> OrderCase:
        """Sales confirms a line's PRV code, and the line is checked again (step 2).

        The code is looked up in ``scope``'s item master and refused when it is
        not there: a confirmed candidate, or a code typed for an unmapped line,
        is an item the company sells, never a string taken on trust. The line
        is checked against that item under the rules stamped on the case, and
        refused once the tenant's rules have moved on: a recheck under other
        rules would put two versions on one case. Which codes a line may take
        is the case's to decide (`OrderCase.confirm_mapping`).
        """
        line = case.line(line_no)
        details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no}
        rules = await self.rules.rules(scope)
        if rules.version != case.rules_version:
            raise ConflictError(
                "the case was checked under rules that no longer apply", details=details
            )
        item = (await self.catalog.item_by_prv_code(scope, prv_code)).data
        if item is None:
            raise ConflictError(
                "the item master has no such PRV code", details={**details, "field": "prv_code"}
            )
        header = case.header
        lme = await self.catalog.lme_for_month(scope, rules.lme_month(header.po_date))
        mapped = MappedLine(line.mapping, item, line.basis.convert_prv_code)
        recheck, _ = await self._check_line(
            scope,
            case.customer_code,
            header,
            case.received_at,
            line.po_line,
            mapped,
            lme.data,
            rules,
        )
        return case.confirm_mapping(line_no, prv_code, actor, at, recheck)

    async def _check_line(
        self,
        scope: SalesScope,
        customer_code: str,
        header: PoHeader,
        received_at: datetime,
        po_line: PoLine,
        mapped: MappedLine,
        lme: LmeMonth | None,
        rules: OrderRules,
    ) -> tuple[LineCheck, list[datetime]]:
        """One line checked against its item and the customer's quotation for it
        on the PO date, with the ``as_of`` of what that read."""
        quotation = None
        read: list[datetime] = []
        if mapped.item is not None:
            valid = await self.catalog.quotations_valid_on(
                scope, customer_code, mapped.item.prv_code, header.po_date
            )
            read.append(valid.as_of)
            quotation = current_quotation(
                valid.data,
                customer_code=customer_code,
                prv_code=mapped.item.prv_code,
                day=header.po_date,
            )
        check = check_line(
            po_line,
            mapped,
            currency=header.currency,
            po_date=header.po_date,
            received_at=received_at,
            quotation=quotation,
            lme=lme,
            rules=rules,
        )
        return check, read

    async def _buyer(
        self, scope: SalesScope, readable: Sequence[AttachmentContent], caps: IntakeCaps
    ) -> Customer | None:
        """The one customer whose name the documents' buyer is, by exact match.

        Unicode case folding only: a near match is a guess, and Sales confirms
        even an exact one (`customer_unknown`).
        """
        customers = (await self.catalog.customers(scope)).data
        found: set[str] = set()
        for content in readable:
            buyer = await self.reader.buyer(content, caps)
            if buyer is not None:
                found |= {c.code for c in customers_named(customers, buyer.name)}
        if len(found) != 1:
            return None
        (code,) = found
        return next(c for c in customers if c.code == code)

    # ------------------------------------------------------------ helpers --

    async def _attachments(self, scope: SalesScope, message: InboundMessage) -> list[_Attached]:
        return [
            _Attached(
                a.attachment_id,
                await self.inbox.read_attachment(scope, message.message_id, a.attachment_id),
            )
            for a in message.attachments
        ]

    def _kind(self, message: InboundMessage, attached: Sequence[_Attached]) -> MessageKind:
        carries_document = any(
            item.content is not None and self.reader.sniff(item.content.data) is not None
            for item in attached
        )
        headline = " ".join([message.subject, *(a.name for a in message.attachments)])
        for text in (headline, message.body_text):
            words = _words(text)
            if _QUOTE_REQUEST.search(words):
                return MessageKind.QUOTE_REQUEST
            if _DESIGN_REPLY.search(words) and carries_document:
                return MessageKind.DESIGN_REPLY
            if _PURCHASE_ORDER.search(words):
                # A message about a PO is not a PO: it has to carry one.
                if not carries_document:
                    return MessageKind.OTHER
                return MessageKind.REVISED_PO if _REVISED.search(words) else MessageKind.PO
        return MessageKind.OTHER

    def _routed(
        self,
        message: InboundMessage,
        kind: MessageKind,
        reason: RoutingReason,
        customer: Customer | None,
        detail: str | None = None,
    ) -> IntakeOutcome:
        owner = customer.sales_pic if customer is not None else None
        disposition = MessageDisposition(
            message_id=message.message_id,
            kind=DispositionKind.ROUTED_TO_SALES,
            reason=reason,
            detail=detail[:500] if detail else None,
            owner=owner or SALES_PIC_POOL,
            customer_code=customer.code if customer is not None else None,
            compliance=(
                customer.compliance
                if customer is not None and reason is RoutingReason.SAMPLE_REQUEST
                else None
            ),
        )
        return IntakeOutcome(message.message_id, kind, disposition)

    def _on_case(
        self, message: InboundMessage, kind: MessageKind, how: DispositionKind, case: OrderCase
    ) -> IntakeOutcome:
        disposition = MessageDisposition(
            message_id=message.message_id,
            kind=how,
            case_kind=CaseKind.ORDER,
            case_id=case.case_id,
            customer_code=case.customer_code,
        )
        return IntakeOutcome(message.message_id, kind, disposition, case)


def _words(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _other_reason(message: InboundMessage) -> RoutingReason:
    headline = " ".join([message.subject, *(a.name for a in message.attachments)])
    for text in (headline, message.body_text):
        words = _words(text)
        for reason, pattern in _ROUTES:
            if pattern.search(words):
                return reason
    return RoutingReason.OTHER
