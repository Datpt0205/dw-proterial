"""DW1's part of the quotation flow (WIV-03-023), all of it deterministic.

Reads the request from the customer's file, prepares what Design is asked,
matches Design's reply to its case by the YCBG number, gathers the price
evidence, raises the quotation findings a decided price calls for, writes the
quotation document, records the master-list row once Sales confirms it, and
lists what the yearly screening should look at. It decides no price and sends
nothing: Sales decides the price, an approver approves it on the case
(`dw_sales.domain.quotes.QuoteCase`), and a person sends what this prepares.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.application.quote_ports import (
    DesignReplyReaderPort,
    QuotationLedgerPort,
    QuoteCaseLookupPort,
    RfqReaderPort,
)
from dw_sales.domain.catalog import Customer, Item, LmeMonth, customers_named, month_key
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.messages import Attachment, AttachmentContent, InboundMessage
from dw_sales.domain.pricing import Incoterm, SalesPricing
from dw_sales.domain.quotes import (
    INTAKE_FINDINGS,
    CopperBasisKind,
    CustomerQuoteDocument,
    CustomerSource,
    DesignReply,
    DesignReplyDocument,
    DesignRequestDraft,
    DesignRequestLine,
    FreightEvidence,
    InternalQuotation,
    OrderedLine,
    PriceEvidence,
    PricingDecision,
    QuoteAddressee,
    QuoteCase,
    QuoteRequest,
    QuoteStatus,
    ReferenceRule,
    RequestedItem,
    RfqDocument,
    copper_component,
    policy_floor,
    price_findings,
)


class QuoteRules(BaseModel):
    """The quote policy: `configs/policies/sales_quote_rules@<version>.yaml`.

    Whoever loads the file validates it here, so every version passes the
    same checks before any of it is applied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_quote_rules"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    # None (`null` in the file) when the policy defines no reference price:
    # the evidence then offers no number at all. No default, so a file that
    # forgets the key fails here instead of quietly offering none.
    reference_price: ReferenceRule | None
    # The copper basis a decided price must follow (`price_basis_mismatch`).
    copper_basis: CopperBasisKind
    # Counting the quotation's own date: 90 days from 1 October ends 29 December.
    validity_days: int = Field(ge=1, le=366)

    @property
    def version(self) -> str:
        """What a quotation finding is stamped with: ``sales_quote_rules@1.0.0``."""
        return f"{self.policy_id}@{self.policy_version}"


type NotExtractedReason = Literal["no_request_file", "several_request_files", "customer_unknown"]


class RequestNotExtractedError(DomainError):
    """The message holds no request for quotation this code can open a case for.

    A person reads it instead. Nothing is guessed from the subject or the
    body: reading free text is a model's work, and none runs here.
    ``customer_unknown``: neither the sender's domain nor the buyer the file
    names is exactly one customer, so the message is routed to Sales with that
    reason rather than matched to the nearest customer.
    """

    def __init__(self, message_id: str, reason: NotExtractedReason) -> None:
        super().__init__(
            f"message {message_id} holds no request for quotation to open ({reason})",
            details={"message_id": message_id, "reason": reason},
        )
        self.reason = reason


class NotADesignReplyError(DomainError):
    """The message carries no file the Design-reply reader recognises, or more
    than one. A person reads it."""

    def __init__(self, message_id: str) -> None:
        super().__init__(
            f"message {message_id} holds no single Design reply to read",
            details={"message_id": message_id},
        )


@dataclass(frozen=True, slots=True)
class ReplyAttached:
    """The reply's YCBG number is the one case awaiting Design under it, and
    the reply answers every line that case asked: the case, with the reply
    recorded."""

    case: QuoteCase

    @property
    def disposition(self) -> MessageDisposition:
        reply = self.case.design_reply
        assert reply is not None  # built only from a case that just recorded it
        return MessageDisposition(
            message_id=reply.message_id,
            kind=DispositionKind.ATTACHED_TO_CASE,
            case_kind=CaseKind.QUOTE,
            case_id=self.case.case_id,
            customer_code=self.case.customer_code,
        )


# Why a reply was not attached, in words that name no value of the reply.
_NO_CASE_WAITING: Final = "no case awaits Design under the reply's YCBG number"
_LINES_UNANSWERED: Final = "the reply does not answer exactly the lines its case asked"
_NOT_FROM_DESIGN: Final = "the reply does not come from a Design mailbox the mail system verified"


@dataclass(frozen=True, slots=True)
class ReplyUnmatched:
    """The reply is not attached and the message goes to Sales: no case awaits
    Design under its YCBG number (`design_reply_unmatched`), the one that does
    asked other lines than the reply answers (`other`), or the message is not
    from a Design mailbox (`other`, its file left unread, so ``ycbg_no`` is
    None). Nothing else of the reply (customer, item, wording) is tried."""

    message_id: str
    ycbg_no: str | None
    reason: RoutingReason = RoutingReason.DESIGN_REPLY_UNMATCHED
    detail: str = _NO_CASE_WAITING

    @property
    def disposition(self) -> MessageDisposition:
        return MessageDisposition(
            message_id=self.message_id,
            kind=DispositionKind.ROUTED_TO_SALES,
            reason=self.reason,
            detail=self.detail,
            owner=SALES_PIC_POOL,
        )


class ScreeningRow(BaseModel):
    """One customer's item quoted to them with no order of it in the window
    (WIV-03-023 step 12): for Sales to decide whether the quotation stays."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_code: str
    prv_code: str
    # The quotations valid on the screening day, by number.
    quote_nos: tuple[str, ...] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class QuotationService:
    """What DW1 prepares for a request for quotation; Sales decides on the case.

    ``design_mailboxes``: the addresses Design replies from, supplied by the
    composition root from the deployment's configuration. A reply sets the
    specification a customer is quoted and the copper weight the price floor
    is computed from, so only mail from one of them, with every sender check
    passed, is taken as Design's. Empty takes no reply at all.
    """

    catalog: SalesCatalogPort
    inbox: InboxPort
    rfq_reader: RfqReaderPort
    reply_reader: DesignReplyReaderPort
    cases: QuoteCaseLookupPort
    ledger: QuotationLedgerPort
    rules: QuoteRules
    pricing: SalesPricing
    design_mailboxes: frozenset[str]

    # ---------------------------------------------------------- step 1 --

    async def extract_request(self, scope: SalesScope, message_id: str) -> QuoteRequest:
        """The request, read from the one request file the message carries.

        The customer is the one master data names for the sender's domain.
        For a sender on no customer's domain (a request forwarded from an
        internal address), it is the customer whose name equals the buyer the
        file prints, and the case raises `customer_unknown` until Sales
        confirms it. With neither, no case is opened.
        """
        message = await self._message(scope, message_id)
        found = await self._files(scope, message, self.rfq_reader.read)
        if not found:
            raise RequestNotExtractedError(message_id, "no_request_file")
        if len(found) > 1:
            raise RequestNotExtractedError(message_id, "several_request_files")
        ((attachment, document),) = found
        customer, found_by = await self._requester(scope, message, document)
        return QuoteRequest(
            message_id=message_id,
            received_at=message.received_at,
            sender=message.sender,
            attachment=attachment,
            customer_code=customer.code,
            customer_from=found_by,
            document=document,
        )

    # ------------------------------------------------------- steps 2-3 --

    async def design_request(self, scope: SalesScope, case: QuoteCase) -> DesignRequestDraft:
        """What Design is asked about each requested line: the content of the
        YCBG Sales enters in the ERP. Drafted once the request's own findings
        are answered, so every quantity and date is known."""
        if any(f.is_open for f in case.findings if f.code in INTAKE_FINDINGS):
            raise ConflictError(
                "the YCBG is drafted once the request's own findings are answered",
                details={"case_id": str(case.case_id)},
            )
        customer = await self._customer(scope, case.customer_code)
        lines = []
        for item in case.request.document.items:
            known = await self._catalogue_item(scope, case.customer_code, item)
            quantity, needed_by = case.quantity(item.line_no), case.needed_by(item.line_no)
            assert quantity is not None and needed_by is not None  # answered above
            lines.append(
                DesignRequestLine(
                    line_no=item.line_no,
                    customer_item_code=(
                        item.customer_item_code.value if item.customer_item_code else None
                    ),
                    known_prv_code=known.prv_code if known else None,
                    description=item.description.value,
                    quantity=quantity,
                    uom=item.uom.value,
                    needed_by=needed_by,
                )
            )
        document = case.request.document
        return DesignRequestDraft(
            customer_code=customer.code,
            customer_name=customer.name,
            rfq_no=document.rfq_no.value,
            quote_due=document.quote_due.value if document.quote_due else None,
            lines=tuple(lines),
        )

    # ---------------------------------------------------------- step 4 --

    async def take_design_reply(
        self, scope: SalesScope, message_id: str
    ) -> ReplyAttached | ReplyUnmatched:
        """Design's reply, matched to its case by the YCBG number it quotes.

        Only a message from one of `design_mailboxes` that the mail system
        verified is read as one; any other sender is routed to Sales unread,
        whatever its file says. Attached only to the one case of the scope
        recorded under that number and waiting on Design; anything else (no
        such case, one not waiting, or more than one) routes the message to
        Sales.
        """
        message = await self._message(scope, message_id)
        if not self._from_design(message):
            return ReplyUnmatched(
                message_id=message_id,
                ycbg_no=None,
                reason=RoutingReason.OTHER,
                detail=_NOT_FROM_DESIGN,
            )
        found = await self._files(scope, message, self.reply_reader.read)
        if len(found) != 1:
            raise NotADesignReplyError(message_id)
        ((attachment, document),) = found
        ycbg_no = document.ycbg_no.value
        waiting = [
            case
            for case in await self.cases.cases_for_ycbg(scope, ycbg_no)
            if case.status is QuoteStatus.SENT_TO_DESIGN
        ]
        if len(waiting) != 1:
            return ReplyUnmatched(message_id=message_id, ycbg_no=ycbg_no)
        (case,) = waiting
        if {line.line_no for line in document.lines} != case.request.document.line_numbers():
            return ReplyUnmatched(
                message_id=message_id,
                ycbg_no=ycbg_no,
                reason=RoutingReason.OTHER,
                detail=_LINES_UNANSWERED,
            )
        reply = DesignReply(
            message_id=message_id,
            received_at=message.received_at,
            attachment=attachment,
            document=document,
        )
        return ReplyAttached(case=case.record_design_reply(reply))

    # ---------------------------------------------------------- step 7 --

    async def price_evidence(
        self,
        scope: SalesScope,
        case: QuoteCase,
        *,
        as_of: date,
        incoterm: Incoterm | None = None,
        destination: str | None = None,
    ) -> tuple[PriceEvidence, ...]:
        """What Sales weighs for each line, as of ``as_of``.

        The item is the one Design's reply names. Its quotations are split into
        the requester's own history and other customers' rows, which are marked
        internal. The requester's orders of it come from the ERP's last 12
        months. The copper component, the floor and freight (for the lane
        Sales names) come from `sales_pricing`; the reference price only from
        a rule the quote policy defines.
        """
        reply = case.design_reply
        if reply is None:
            raise ConflictError(
                "price evidence is gathered once Design has replied",
                details={"case_id": str(case.case_id), "status": case.status.value},
            )
        customer_code = case.customer_code
        currency = case.request.currency
        lme = await self._lme_as_of(scope, as_of)
        since = _year_before(as_of)
        orders = [
            order
            for order in (await self.catalog.orders_since(scope, since)).data
            if order.customer_code == customer_code and order.order_date <= as_of
        ]
        freight = (
            FreightEvidence(
                incoterm=incoterm,
                destination=destination,
                rate=self.pricing.freight_rate(incoterm, destination),
            )
            if incoterm is not None and destination is not None
            else None
        )
        rule = self.rules.reference_price
        evidence = []
        for item in case.request.document.items:
            design = reply.line(item.line_no)
            prv_code = design.prv_code.value if design.prv_code else None
            quotations = (
                (await self.catalog.quotations_for_item(scope, prv_code)).data
                if prv_code is not None
                else ()
            )
            newest_first = sorted(
                quotations, key=lambda q: (q.valid_from, q.quote_no), reverse=True
            )
            weight = design.copper_kg_per_km.value if design.copper_kg_per_km else None
            copper = copper_component(weight, lme, item.uom.value, self.pricing)
            evidence.append(
                PriceEvidence(
                    line_no=item.line_no,
                    customer_code=customer_code,
                    prv_code=prv_code,
                    currency=currency,
                    as_of=as_of,
                    pricing_policy=self.pricing.version,
                    target_price=item.target_price.value if item.target_price else None,
                    own_history=tuple(q for q in newest_first if q.customer_code == customer_code),
                    other_customers=tuple(
                        InternalQuotation(quotation=q)
                        for q in newest_first
                        if q.customer_code != customer_code
                    ),
                    orders=tuple(
                        line
                        for order in orders
                        if prv_code is not None
                        for line in OrderedLine.lines_of(order, prv_code)
                    ),
                    lme=lme,
                    copper=copper,
                    floor=policy_floor(copper, currency, self.pricing),
                    freight=freight,
                    reference=(
                        rule.reference_price(quotations, currency=currency, lme=lme, as_of=as_of)
                        if rule is not None
                        else None
                    ),
                )
            )
        return tuple(evidence)

    async def decide_price(
        self, scope: SalesScope, case: QuoteCase, decision: PricingDecision, *, by: uuid.UUID
    ) -> QuoteCase:
        """Sales' price on the case, with the findings it raises. ``by`` is the
        verified caller, whose decision it must be (`QuoteCase.decide_price`).

        `price_basis_mismatch` compares the decision's LME month with the
        latest month published when it was decided, read here once and
        compared there, never re-read later. From `pending_approval` or
        `approved` this withdraws the document and returns the case to
        `priced`.
        """
        latest = await self._lme_as_of(scope, decision.decided_at.date())
        await self._recorded_lme(scope, decision, latest)
        findings = price_findings(
            case,
            decision,
            latest_lme=latest,
            pricing=self.pricing,
            prescribed_basis=self.rules.copper_basis,
            quote_rules_version=self.rules.version,
        )
        return case.decide_price(decision, findings, by=by)

    # ------------------------------------------------------- steps 8-9 --

    async def quotation_document(
        self, scope: SalesScope, case: QuoteCase, *, quote_no: str, issued_on: date
    ) -> CustomerQuoteDocument:
        """The quotation the customer receives, from a priced case.

        Built from the case (the customer's request, Design's specification,
        Sales' decided terms) and the customer's own master record, and from
        nothing else: price evidence is not among its inputs, and quotations
        are not read here. Addressed to the contact who sent the request when
        master data lists them, otherwise to the customer's listed contacts:
        never to an address the message itself supplied.
        """
        pricing = case.pricing
        if case.status is not QuoteStatus.PRICED or pricing is None:
            raise ConflictError(
                "the quotation document is written from a priced case",
                details={"case_id": str(case.case_id), "status": case.status.value},
            )
        customer = await self._customer(scope, case.customer_code)
        sender = case.request.sender.address.lower()
        recipients = tuple(c for c in customer.contacts if c.address.lower() == sender)
        return CustomerQuoteDocument(
            quote_no=quote_no,
            addressee=QuoteAddressee.of(customer),
            recipients=recipients or customer.contacts,
            their_reference=case.request.document.rfq_no.value,
            issued_on=issued_on,
            valid_to=issued_on + timedelta(days=self.rules.validity_days - 1),
            currency=case.request.currency,
            lme=pricing.lme,
            lines=case.document_lines(),
        )

    async def submit(
        self,
        scope: SalesScope,
        case: QuoteCase,
        *,
        quote_no: str,
        issued_on: date,
        by: uuid.UUID,
        at: AwareDatetime,
    ) -> QuoteCase:
        """The document is written and stamped with its hash and the pricer;
        the case waits for an approver."""
        document = await self.quotation_document(
            scope, case, quote_no=quote_no, issued_on=issued_on
        )
        return case.submit_for_approval(document, by=by, at=at)

    # --------------------------------------------------------- step 11 --

    async def record_master_list(
        self, scope: SalesScope, case: QuoteCase, *, by: uuid.UUID, at: AwareDatetime
    ) -> QuoteCase:
        """Sales confirmed the sent quotation's master-list rows: they are
        written to the ledger, then the case records it. A ledger that refuses
        leaves the case `sent`."""
        rows = case.master_list_rows()
        await self.ledger.record(scope, rows)
        return case.record_master_list(by=by, at=at)

    # --------------------------------------------------------- step 12 --

    async def screening(self, scope: SalesScope, as_of: date) -> tuple[ScreeningRow, ...]:
        """Each customer's item with a quotation valid on ``as_of`` and no ERP
        order of it in the 12 months before, ordered by customer and item."""
        since = _year_before(as_of)
        ordered = {
            (order.customer_code, line.prv_code)
            for order in (await self.catalog.orders_since(scope, since)).data
            if order.order_date <= as_of
            for line in order.lines
        }
        quoted: dict[tuple[str, str], list[str]] = {}
        for quotation in (await self.catalog.quotations(scope)).data:
            key = (quotation.customer_code, quotation.prv_code)
            if quotation.is_valid_on(as_of) and key not in ordered:
                quoted.setdefault(key, []).append(quotation.quote_no)
        return tuple(
            ScreeningRow(customer_code=customer, prv_code=prv, quote_nos=tuple(sorted(numbers)))
            for (customer, prv), numbers in sorted(quoted.items())
        )

    # --------------------------------------------------------- helpers --

    def _from_design(self, message: InboundMessage) -> bool:
        mailboxes = {address.lower() for address in self.design_mailboxes}
        return message.authentication.verified and message.sender.address.lower() in mailboxes

    async def _message(self, scope: SalesScope, message_id: str) -> InboundMessage:
        message = await self.inbox.get_message(scope, message_id)
        if message is None:
            raise NotFoundError("message not found", details={"message_id": message_id})
        return message

    async def _files[T: (RfqDocument, DesignReplyDocument)](
        self, scope: SalesScope, message: InboundMessage, read: _Reader[T]
    ) -> list[tuple[Attachment, T]]:
        """Every attachment ``read`` recognises, with what it read. The caller
        refuses more than one: which one is the document would be a guess."""
        found: list[tuple[Attachment, T]] = []
        for attachment in message.attachments:
            content = await self.inbox.read_attachment(
                scope, message.message_id, attachment.attachment_id
            )
            if content is None:
                raise NotFoundError(
                    "attachment not found",
                    details={
                        "message_id": message.message_id,
                        "attachment_id": attachment.attachment_id,
                    },
                )
            document = read(content)
            if document is not None:
                found.append((attachment, document))
        return found

    async def _requester(
        self, scope: SalesScope, message: InboundMessage, document: RfqDocument
    ) -> tuple[Customer, CustomerSource]:
        by_domain = (await self.catalog.customer_by_email_domain(scope, message.sender.domain)).data
        if by_domain is not None:
            return by_domain, "sender_domain"
        if document.buyer is not None:
            named = customers_named(
                (await self.catalog.customers(scope)).data, document.buyer.value
            )
            if len(named) == 1:
                return named[0], "named_buyer"
        raise RequestNotExtractedError(message.message_id, "customer_unknown")

    async def _customer(self, scope: SalesScope, code: str) -> Customer:
        customer = (await self.catalog.customer_by_code(scope, code)).data
        if customer is None:
            raise NotFoundError("customer not found", details={"customer_code": code})
        return customer

    async def _catalogue_item(
        self, scope: SalesScope, customer_code: str, item: RequestedItem
    ) -> Item | None:
        """The item the convert list names for the line's customer code: an
        exact hit or nothing, because a near match is a guess and the guess is
        Design's to make."""
        if item.customer_item_code is None:
            return None
        entry = (
            await self.catalog.convert_entry(scope, customer_code, item.customer_item_code.value)
        ).data
        if entry is None:
            return None
        found = (await self.catalog.item_by_prv_code(scope, entry.prv_code)).data
        if found is None:
            raise DomainError(
                "the convert list names an item the catalogue does not hold",
                details={"customer_code": customer_code, "prv_code": entry.prv_code},
            )
        return found

    async def _recorded_lme(
        self, scope: SalesScope, decision: PricingDecision, latest: LmeMonth | None
    ) -> None:
        """Refuses a decision whose LME month is not the one on record.

        The floor and the band are computed from the figure the decision
        carries, so a figure that is not the published one (or none, while one
        is published) would move the floor wherever its sender liked.
        """
        stated = decision.lme
        if stated is None:
            if latest is not None:
                raise ConflictError(
                    "a price names the LME month it was decided against",
                    details={"latest_month": latest.month},
                )
            return
        recorded = next(
            (
                lme
                for lme in (await self.catalog.lme_months(scope)).data
                if lme.month == stated.month
            ),
            None,
        )
        if recorded != stated:
            raise ConflictError(
                "the decision's LME figure is not the one on record for its month",
                details={"month": stated.month},
            )

    async def _lme_as_of(self, scope: SalesScope, as_of: date) -> LmeMonth | None:
        """The LME month that applies on ``as_of``: its own month, or, before
        that month's figure is on record, the latest month before it. The month
        travels with the figure, so an old figure shows as old."""
        month = month_key(as_of)
        return max(
            (lme for lme in (await self.catalog.lme_months(scope)).data if lme.month <= month),
            key=lambda lme: lme.month,
            default=None,
        )


class _Reader[T](Protocol):
    def __call__(self, content: AttachmentContent, /) -> T | None: ...


def _year_before(day: date) -> date:
    """The same day a year earlier; 28 February for 29 February."""
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)
