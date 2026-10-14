"""Order intake: what each message is, and what becomes of it.

`OrderIntake.process` gives every message it owns exactly one disposition
(spec decision 10): a PO opens an order case or joins the case of the PO it
revises; anything else is routed to Sales with its reason and an owner. A
quote request or a Design reply is handed to the quotation flow, which gives
it its disposition (ticket 03); `IntakeOutcome.disposition` is then None and
the outcome says so.

**A readable document decides first.** An attachment the seller's request
form or Design's reply form recognises, or one that reads as a PO, decides the
message's kind whatever its subject says, and no model is asked (ticket 31).
**Then the thread.** A message whose `In-Reply-To`/`References` name a message
already on one case of the sender's own customer is a reply on that case, and
is attached to it (ticket 32, `ThreadLinkPort`): a "Re:" to a spec discussion
is no new request, whatever its subject repeats. Where the tenant's rules turn
it on, a local model reads the reply into a typed intent (`ReplyReader`); the
case and the step are code's.
**A tenant's own PO layouts read first.** A customer's form a person mapped and
another approved (ticket 30) is read with that layout, the tenant's data;
otherwise with the platform's. The first POs a new layout reads keep every
value `value_uncertain` (`layout_onboarding`). A PO no layout reads is routed
`attachment_unreadable`, and where the tenant turns it on a local model
pre-fills the onboarding screen's mapping (`LayoutPrefiller`).
A message routed as a delivery change, a complaint or a sample request carries,
where the tenant turns it on, a hand-off to PC or QA a local model pre-filled
with the customer's own words and code verified (ticket 33, `HandoffReader`).
Only a message no reader accepted is classified by its words: by a local
model's typed intent where the tenant's rules turn it on (`message_intent`,
dw_sales ADR 0005), which code maps to the route (`INTENT_ROUTES`), else by
the keyword tables over the subject and the attachment names, then the body.
A miss lands where it is safe: routed to Sales as ``other``. Neither a
keyword nor the model sets a value.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.layouts import LayoutPrefiller
from dw_sales.application.malware import AttachmentInfectedError, AttachmentRefusedError
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.model_reading import DescriptionReader
from dw_sales.application.order_ports import (
    READ_AS,
    LayoutLookupPort,
    OrderCaseLookupPort,
    OrderRulesPort,
    PoDocumentReaderPort,
    QuoteFormPort,
    ThreadLinkPort,
)
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.support import decided
from dw_sales.application.threads import ThreadedCase
from dw_sales.domain.catalog import Customer, Item, LmeMonth, customers_named
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.handoffs import HandoffKind
from dw_sales.domain.layouts import PoLayout, flagged_as_new
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.message_intent import IntentKind, IntentReading
from dw_sales.domain.messages import AttachmentContent, InboundMessage
from dw_sales.domain.order_checks import (
    CUSTOMER_CHECK_CODES,
    DOCUMENT_CHECK_CODES,
    IntakeCaps,
    MappedLine,
    OrderRules,
    check_customer,
    check_document,
    check_history,
    check_line,
    current_quotation,
    map_line,
    received_date,
    wants_reading,
)
from dw_sales.domain.orders import (
    Actor,
    Finding,
    FindingCode,
    LineCheck,
    OrderCase,
    OrderLine,
    OrderStatus,
    PoDocument,
    PoHeader,
    PoLine,
    Recheck,
    Unreadable,
    ValueCorrection,
)
from dw_sales.domain.print_pairs import one_po
from dw_sales.domain.reply_intent import CaseReply


class MessageKind(StrEnum):
    PO = "po"
    REVISED_PO = "revised_po"
    QUOTE_REQUEST = "quote_request"
    DESIGN_REPLY = "design_reply"
    # A reply on a case its thread headers name (ticket 32).
    CASE_REPLY = "case_reply"
    OTHER = "other"


# Handed to the quotation flow, which gives them their disposition.
QUOTATION_KINDS = frozenset({MessageKind.QUOTE_REQUEST, MessageKind.DESIGN_REPLY})

# Where each kind a model reads goes (ticket 31). The order and quotation
# flows still decide for themselves: a PO without a readable file, or a
# Design reply from a sender the mail system did not verify, is routed as it
# would be anyway. The rest go to the customer's Sales PIC with the reason.
# One table: a kind is a row, never a branch.
INTENT_ROUTES: Final[Mapping[IntentKind, MessageKind | RoutingReason]] = {
    "po": MessageKind.PO,
    "quote_request": MessageKind.QUOTE_REQUEST,
    "design_reply": MessageKind.DESIGN_REPLY,
    "reply_to_case": RoutingReason.REPLY_TO_CASE,
    "delivery_change": RoutingReason.DELIVERY_CHANGE,
    "complaint": RoutingReason.COMPLAINT,
    "sample_request": RoutingReason.SAMPLE_REQUEST,
    "other": RoutingReason.OTHER,
}
# The routing reasons a hand-off to PC or QA is pre-filled for (ticket 33):
# the hand-off's kind is the reason, never a model's choice.
HANDOFF_KINDS: Final[Mapping[RoutingReason, HandoffKind]] = {
    RoutingReason.DELIVERY_CHANGE: "delivery_change",
    RoutingReason.COMPLAINT: "complaint",
    RoutingReason.SAMPLE_REQUEST: "sample_request",
}
# Why a message no model could read goes to Sales once its retries are over.
NOT_UNDERSTOOD: Final = "DW1 did not understand the message: no usable model answer"

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
class Classification:
    """What a message is, and what decided it.

    ``reason`` and ``detail`` say why an ``other`` message goes to Sales when
    the classification already knows (a model's kind, two kinds of document);
    otherwise the keyword reasons apply. ``reading`` is the model reading's
    stamp, for the disposition. ``retry``: the model gave no usable answer
    and the message is young enough to try again, so it stays not yet
    processed (`ModelAssist.unread_retry_hours`). ``thread``: the case a
    `case_reply`'s thread headers name.
    """

    kind: MessageKind
    reason: RoutingReason | None = None
    detail: str | None = None
    reading: IntentReading | None = None
    retry: bool = False
    thread: ThreadedCase | None = None


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
    # What the scanner found in it (ticket 25): then there are no bytes.
    infected: str | None = None
    # Why it was refused unread (ticket 25): not what its name says, or
    # encrypted. Then there are no bytes either.
    refused: str | None = None


@dataclass(frozen=True)
class OrderIntake:
    catalog: SalesCatalogPort
    inbox: InboxPort
    reader: PoDocumentReaderPort
    rules: OrderRulesPort
    cases: OrderCaseLookupPort
    new_case_id: Callable[[], uuid.UUID]
    # Recognises the seller's request and Design-reply forms, so that a
    # readable document decides its message's kind first (ticket 31).
    quote_forms: QuoteFormPort
    # A model reading of the descriptions DW1's vocabulary does not read
    # (dw_sales ADR 0005), for a tenant whose rules turn it on. None: no model
    # is wired in this process, and those lines stay unmapped as before.
    descriptions: DescriptionReader | None = None
    # A model reading of the intent of a message no reader accepted (ticket
    # 31), for a tenant whose rules turn it on. None: no model is wired, and
    # the keyword tables classify those messages as before.
    intents: IntentReader | None = None
    # The case a reply's thread headers name (ticket 32). None: no case log is
    # wired (a reader-only test), and no reply is linked.
    threads: ThreadLinkPort | None = None
    # A model reading of such a reply, for a tenant whose rules turn it on.
    # None: no model is wired, and the reply is attached unread.
    replies: ReplyReader | None = None
    # A model pre-filling a routed message's hand-off to PC or QA (ticket 33),
    # for a tenant whose rules turn it on. None: no model is wired, and the
    # message is routed with no hand-off, as before.
    handoffs: HandoffReader | None = None
    # The PO layouts the tenant approved (ticket 30). None: none are stored in
    # this process (a reader-only test), and the platform's layouts read.
    layouts: LayoutLookupPort | None = None
    # A model pre-filling the mapping of a form no layout reads (ticket 30),
    # for a tenant whose rules turn it on. None: no model is wired.
    layout_prefiller: LayoutPrefiller | None = None

    async def classify(
        self,
        scope: SalesScope,
        message: InboundMessage,
        *,
        run: RunContext | None = None,
        now: datetime | None = None,
    ) -> Classification:
        """What the message is (module docstring). ``run`` is the DW1 run
        processing it: a model is asked only inside one. ``now`` is when it is
        processed, which says whether a message the model could not read is
        still young enough to try again; without it, it is not."""
        return await self._classified(
            scope, message, await self._attachments(scope, message), run, now
        )

    async def process(
        self,
        scope: SalesScope,
        message: InboundMessage,
        *,
        run: RunContext | None = None,
        now: datetime | None = None,
        classified: Classification | None = None,
    ) -> IntakeOutcome:
        """The message's disposition, and the order case it created or revised.

        Refused with a conflict when this message already has a case: that is
        processing twice, not a duplicate PO. ``run`` is the DW1 run doing the
        processing: a model call is made only inside one, attributed to it.
        ``classified`` is the classification the caller already made, so the
        message is not read, and no model asked, twice.
        """
        attached = await self._attachments(scope, message)
        classification = classified or await self._classified(scope, message, attached, run, now)
        if classification.retry:
            raise ValueError("a message left for a retry is not processed")
        kind = classification.kind
        if kind in QUOTATION_KINDS:
            return IntakeOutcome(message.message_id, kind, None)
        if classification.thread is not None:
            return await self._reply(scope, message, classification.thread, run)
        sender = (await self.catalog.customer_by_email_domain(scope, message.sender.domain)).data
        if kind is MessageKind.OTHER:
            reason = classification.reason or _other_reason(message)
            outcome = self._routed(message, kind, reason, sender, classification.detail)
            outcome = await self._with_handoff(scope, message, outcome, sender, run)
        else:
            outcome = await self._order(scope, message, kind, sender, attached, run)
        return _stamped(outcome, classification.reading)

    # ------------------------------------------------------ classification --

    async def _classified(
        self,
        scope: SalesScope,
        message: InboundMessage,
        attached: Sequence[_Attached],
        run: RunContext | None,
        now: datetime | None,
    ) -> Classification:
        if infected := [a for a in attached if a.infected is not None]:
            # Malware in any attachment: the mail is Sales', and nothing in it
            # is read, no model asked (ticket 25). Ids and signatures only.
            return Classification(
                MessageKind.OTHER,
                RoutingReason.MALWARE_DETECTED,
                "; ".join(f"{a.attachment_id}: {a.infected}" for a in infected),
            )
        sender = (await self.catalog.customer_by_email_domain(scope, message.sender.domain)).data
        rules = await self.rules.rules(scope)
        by_content = await self._by_content(scope, attached, sender, rules.intake)
        if len(by_content) > 1:
            return Classification(
                MessageKind.OTHER,
                RoutingReason.OTHER,
                "its attachments read as more than one kind of document",
            )
        if by_content:
            (kind,) = by_content
            return Classification(kind)
        if self.threads is not None and message.references:
            thread = await self.threads.linked_case(scope, message, sender)
            if thread is not None:
                return Classification(MessageKind.CASE_REPLY, thread=thread)
        if self.intents is not None and run is not None and rules.model_assist.message_intent:
            return await self._intent(scope, message, attached, sender, rules, run, now)
        return Classification(self._kind(message, attached))

    async def _by_content(
        self,
        scope: SalesScope,
        attached: Sequence[_Attached],
        sender: Customer | None,
        caps: IntakeCaps,
    ) -> set[MessageKind]:
        """The kinds the attachments' content says: a request or Design-reply
        form by its marker, a PO by the reader of the sender's (or the named
        buyer's) layout. Several POs are one kind; intake decides on them."""
        kinds: set[MessageKind] = set()
        readable: list[AttachmentContent] = []
        for item in attached:
            content = item.content
            if content is None:
                continue
            form = await self.quote_forms.form(content)
            if form is not None:
                kinds.add(MessageKind(form))
            elif (
                READ_AS.get(self.reader.sniff(content.data) or "") is not None
                and content.attachment.size <= caps.max_attachment_bytes
            ):
                readable.append(content)
        customer = sender or (await self._buyer(scope, readable, caps) if readable else None)
        if customer is None:
            return kinds
        revised: list[bool] = []
        for content in readable:
            document = await self._read_po(scope, content, customer.code, caps, flag=None)
            if not isinstance(document, Unreadable):
                revised.append(document.header.revision > 0)
        if revised:
            kinds.add(MessageKind.REVISED_PO if any(revised) else MessageKind.PO)
        return kinds

    async def _intent(
        self,
        scope: SalesScope,
        message: InboundMessage,
        attached: Sequence[_Attached],
        sender: Customer | None,
        rules: OrderRules,
        run: RunContext,
        now: datetime | None,
    ) -> Classification:
        """The kind a model reads (ticket 31), routed by `INTENT_ROUTES`."""
        assert self.intents is not None  # asked only where one is wired
        read = await self.intents.read(
            scope, newest_part(message), sender, rules_version=rules.version, run=run
        )
        if read is None:
            window = timedelta(hours=rules.model_assist.unread_retry_hours)
            if now is not None and now - message.received_at < window:
                return Classification(MessageKind.OTHER, retry=True)
            return Classification(
                MessageKind.OTHER,
                RoutingReason.OTHER,
                NOT_UNDERSTOOD,
                self.intents.unavailable(rules.version),
            )
        route = INTENT_ROUTES[read.kind]
        if isinstance(route, RoutingReason):
            return Classification(MessageKind.OTHER, route, reading=read.reading)
        if route is MessageKind.PO and not self._carries_document(attached):
            # A message about a PO is not a PO: it has to carry one.
            return Classification(
                MessageKind.OTHER,
                RoutingReason.OTHER,
                "it names an order but carries no document",
                read.reading,
            )
        return Classification(route, reading=read.reading)

    async def _reply(
        self,
        scope: SalesScope,
        message: InboundMessage,
        thread: ThreadedCase,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """A reply attached to the case its thread names, with a model's
        reading of it where the tenant's rules, a wired model and a DW1 run
        allow. Nothing on the case changes: Sales confirms any step."""
        rules = await self.rules.rules(scope)
        reading = None
        if self.replies is not None and run is not None and rules.model_assist.reply_intent:
            reading = await self.replies.read(
                newest_part(message), thread, rules_version=rules.version, run=run
            )
        disposition = MessageDisposition(
            message_id=message.message_id,
            kind=DispositionKind.ATTACHED_TO_CASE,
            case_kind=thread.case_kind,
            case_id=thread.case_id,
            customer_code=thread.customer_code,
            reply=CaseReply(linked_to=thread.linked_to, reading=reading),
        )
        return IntakeOutcome(message.message_id, MessageKind.CASE_REPLY, disposition)

    async def _with_handoff(
        self,
        scope: SalesScope,
        message: InboundMessage,
        outcome: IntakeOutcome,
        sender: Customer | None,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """The routed outcome with the hand-off a model pre-filled, where the
        reason takes one, the sender is a customer, the tenant's rules turn
        the step on, a model is wired and a DW1 run is processing."""
        disposition = outcome.disposition
        if disposition is None or disposition.reason is None:
            return outcome
        kind = HANDOFF_KINDS.get(disposition.reason)
        if kind is None or sender is None or self.handoffs is None or run is None:
            return outcome
        rules = await self.rules.rules(scope)
        if not rules.model_assist.request_handoff:
            return outcome
        handoff = await self.handoffs.read(
            scope,
            newest_part(message),
            sender,
            kind,
            received_on=received_date(message.received_at),
            rules_version=rules.version,
            run=run,
        )
        stamped = MessageDisposition.model_validate(
            {**disposition.model_dump(), "handoff": handoff}
        )
        return IntakeOutcome(outcome.message_id, outcome.kind, stamped, outcome.case)

    # ------------------------------------------------------------ orders --

    async def _order(
        self,
        scope: SalesScope,
        message: InboundMessage,
        kind: MessageKind,
        sender: Customer | None,
        attached: Sequence[_Attached],
        run: RunContext | None,
    ) -> IntakeOutcome:
        rules = await self.rules.rules(scope)
        caps = rules.intake
        readable: list[AttachmentContent] = []
        reasons: list[str] = []
        for item in attached:
            content = item.content
            if content is None:
                reasons.append(f"{item.attachment_id}: {item.refused or 'not in the mailbox'}")
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
        kinds: list[str] = []
        for content in readable:
            result = await self._read_po(scope, content, customer.code, caps, flag=rules)
            if isinstance(result, Unreadable):
                reasons.append(f"{content.attachment.attachment_id}: {result.reason}")
            else:
                documents.append(result)
                # A legacy workbook pairs with its print as a workbook does.
                kinds.append(READ_AS.get(self.reader.sniff(content.data) or "", ""))
        if not documents:
            routed = self._routed(message, kind, unreadable, customer, "; ".join(reasons))
            return await self._with_prefill(scope, routed, readable, customer, rules, run)
        if sorted(kinds) == ["pdf", "xlsx"]:
            # A workbook and its PDF print are one PO, read from the workbook
            # (ticket 34); `one_po` says None when they are two.
            workbook, printed = documents if kinds[0] == "xlsx" else documents[::-1]
            if (paired := one_po(workbook, printed)) is not None:
                documents = [paired]
        if len(documents) > 1:
            # Two orders, or a workbook and a print that are not the same PO:
            # either way Sales decides which is entered.
            ids = ", ".join(d.attachment_id for d in documents)
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                customer,
                f"more than one attachment reads as a PO: {ids}",
            )
        return await self._case(
            scope, message, kind, customer, attributed, documents[0], rules, run
        )

    async def _read_po(
        self,
        scope: SalesScope,
        content: AttachmentContent,
        customer_code: str,
        caps: IntakeCaps,
        *,
        flag: OrderRules | None,
    ) -> PoDocument | Unreadable:
        """The PO, read with the tenant's own approved layout of the customer's
        form where it has one, the platform's otherwise. With ``flag``, the
        rules under which a PO among the first a new layout reads has every
        value flagged `new_layout`."""
        stored = await self._stored_layout(scope, customer_code, content)
        if stored is None:
            return await self.reader.read(content, customer_code, caps)
        read = await self.reader.read_with(content, stored.mapping, caps, layout_ref=stored.ref)
        if isinstance(read, Unreadable) or flag is None or self.layouts is None:
            return read
        seen = await self.layouts.read_count(scope, stored.ref)
        if seen < flag.layout_onboarding.uncertain_first_pos:
            return flagged_as_new(read)
        return read

    async def _stored_layout(
        self, scope: SalesScope, customer_code: str, content: AttachmentContent
    ) -> PoLayout | None:
        if self.layouts is None:
            return None
        read_as = READ_AS.get(self.reader.sniff(content.data) or "", "")
        kind = {"xlsx": "excel", "pdf": "pdf"}.get(read_as)
        approved = await self.layouts.approved(scope, customer_code)
        return next((layout for layout in approved if layout.kind == kind), None)

    async def _with_prefill(
        self,
        scope: SalesScope,
        outcome: IntakeOutcome,
        readable: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """The routed outcome with a model's pre-filled mapping of the first
        form no layout of the customer's reads, where the tenant's rules turn
        the step on, a model is wired and a DW1 run is processing."""
        prefiller, disposition = self.layout_prefiller, outcome.disposition
        if prefiller is None or run is None or disposition is None:
            return outcome
        if not rules.model_assist.layout_proposal:
            return outcome
        for content in readable:
            file_type = self.reader.sniff(content.data)
            if file_type is None or file_type == "unsupported":
                continue
            if await self.reader.has_layout(customer.code, file_type):
                continue
            if await self._stored_layout(scope, customer.code, content) is not None:
                continue
            prefill = await prefiller.prefill(scope, content, customer, rules, run=run)
            if prefill is None:
                continue
            stamped = MessageDisposition.model_validate(
                {**disposition.model_dump(), "layout_prefill": prefill}
            )
            return IntakeOutcome(outcome.message_id, outcome.kind, stamped, outcome.case)
        return outcome

    async def _case(
        self,
        scope: SalesScope,
        message: InboundMessage,
        kind: MessageKind,
        customer: Customer,
        attributed: bool,
        document: PoDocument,
        rules: OrderRules,
        run: RunContext | None,
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
        mapped_lines: list[tuple[PoLine, MappedLine]] = []
        unread: list[PoLine] = []
        for po_line in document.lines:
            entry = await self.catalog.convert_entry(
                scope, customer.code, po_line.customer_item_code
            )
            as_of.append(entry.as_of)
            mapped_lines.append((po_line, map_line(po_line, entry=entry.data, items=items.data)))
            if wants_reading(po_line, entry=entry.data):
                unread.append(po_line)
        read = await self._read(unread, items.data, rules, run)
        checks: list[LineCheck] = []
        for po_line, by_code in mapped_lines:
            mapped = read.get(po_line.line_no, by_code)
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
        rules = await self._case_rules(scope, case, details)
        item = (await self.catalog.item_by_prv_code(scope, prv_code)).data
        if item is None:
            raise ConflictError(
                "the item master has no such PRV code", details={**details, "field": "prv_code"}
            )
        header = case.effective_header
        lme = await self.catalog.lme_for_month(scope, rules.lme_month(header.po_date))
        # The reading the candidates came from stays the line's evidence.
        mapped = MappedLine(
            line.mapping, item, line.basis.convert_prv_code, line.basis.description_reading
        )
        recheck, _ = await self._check_line(
            scope,
            case.customer_code,
            header,
            case.received_at,
            line.effective,
            mapped,
            lme.data,
            rules,
        )
        return case.confirm_mapping(line_no, prv_code, actor, at, recheck)

    async def correct_value(
        self,
        scope: SalesScope,
        case: OrderCase,
        finding_key: str,
        field: str,
        value: str,
        actor: Actor,
        at: datetime,
    ) -> OrderCase:
        """Sales types one value a `value_uncertain` flagged, and the checks
        run again on the corrected values (ticket 15; Đạt, 2026-10-12).

        A line's correction runs that line's checks again, and the document's
        (its amount is one the total adds up). A header correction runs the
        document's and the customer's checks again, and every line's when the
        PO date or the currency changed. Lines are checked against today's
        master data under the rules stamped on the case, as for a confirmed
        mapping; once the tenant's rules have moved on it is refused. What the
        case keeps and reopens is the case's to decide
        (`OrderCase.correct_value`).
        """
        details: dict[str, object] = {"case_id": str(case.case_id), "finding": finding_key}
        correction = decided(
            lambda: ValueCorrection(field=field, value=value, by=actor.user_id, at=at)
        )
        corrected = decided(lambda: case.corrected(finding_key, correction, actor))
        rules = await self._case_rules(scope, case, details)
        header = corrected.document.header
        lme = await self.catalog.lme_for_month(scope, rules.lme_month(header.po_date))
        checks: list[LineCheck] = []
        for line in corrected.lines:
            if line.line_no not in corrected.rechecked:
                continue
            remap = corrected.remapped and line.line_no == corrected.line_no
            mapped = await self._mapped_again(scope, case.customer_code, line, remap=remap)
            check, _ = await self._check_line(
                scope,
                case.customer_code,
                header,
                case.received_at,
                line.effective,
                mapped,
                lme.data,
                rules,
            )
            checks.append(check)
        po_findings = list(check_document(corrected.document, rules))
        po_codes = DOCUMENT_CHECK_CODES
        if corrected.line_no is None:
            po_findings += await self._customer_findings(scope, case, header.po_date, rules)
            po_codes |= CUSTOMER_CHECK_CODES
        recheck = Recheck(tuple(checks), tuple(po_findings), po_codes)
        return decided(lambda: case.correct_value(finding_key, correction, actor, recheck))

    async def _read(
        self,
        lines: Sequence[PoLine],
        items: Sequence[Item],
        rules: OrderRules,
        run: RunContext | None,
    ) -> dict[int, MappedLine]:
        """The lines a model read (dw_sales ADR 0005), by line number: only
        where the tenant's rules turn it on, a model is wired, and a DW1 run
        is doing the processing. Otherwise none, and every line keeps the
        mapping code gave it."""
        if not lines or not rules.model_assist.description_attributes:
            return {}
        if self.descriptions is None or run is None:
            return {}
        return await self.descriptions.read(lines, items, run=run)

    async def _case_rules(
        self, scope: SalesScope, case: OrderCase, details: dict[str, object]
    ) -> OrderRules:
        """The rules stamped on the case, read by the stamp (ticket 19): a
        recheck under other rules would put two versions on one case, and a
        version the tenant approved since does not reach a case checked
        before it. Refused when this process no longer holds that version."""
        stamped = case.rules_version
        rules = None if stamped is None else await self.rules.rules_at(scope, stamped)
        if rules is None:
            raise ConflictError(
                "the case was checked under rules that no longer apply", details=details
            )
        return rules

    async def _mapped_again(
        self, scope: SalesScope, customer_code: str, line: OrderLine, *, remap: bool
    ) -> MappedLine:
        """What a line is checked against again: its PRV code computed again
        from its entered values when ``remap``, else its mapping as it stands
        and the item that names."""
        if remap:
            entered = line.effective
            entry = await self.catalog.convert_entry(
                scope, customer_code, entered.customer_item_code
            )
            items = await self.catalog.items(scope)
            return map_line(entered, entry=entry.data, items=items.data)
        code = line.mapping.checked_against
        item = None if code is None else (await self.catalog.item_by_prv_code(scope, code)).data
        if code is not None and item is None:
            raise ConflictError(
                "the item the line was checked against is no longer in the item master",
                details={"line": line.line_no},
            )
        return MappedLine(
            line.mapping, item, line.basis.convert_prv_code, line.basis.description_reading
        )

    async def _customer_findings(
        self, scope: SalesScope, case: OrderCase, po_date: date, rules: OrderRules
    ) -> tuple[Finding, ...]:
        """The customer's and the sender's checks again, on the entered PO date
        (the fiscal year an ESF is renewed for). The sender's results are the
        message's; a customer taken from the document is one with
        `customer_unknown`, which that check raised exactly then."""
        customer = (await self.catalog.customer_by_code(scope, case.customer_code)).data
        message = await self.inbox.get_message(scope, case.message_id)
        if customer is None or message is None:
            raise ConflictError(
                "the customer or the message the case was read from is no longer there",
                details={"case_id": str(case.case_id)},
            )
        return check_customer(
            customer,
            attributed_by_document=any(
                f.code is FindingCode.CUSTOMER_UNKNOWN for f in case.findings
            ),
            authentication=message.authentication,
            po_date=po_date,
            received_at=case.received_at,
            rules=rules,
        )

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
        """Each attachment as the scanned mailbox hands it over (ticket 25):
        an infected one has no bytes; one the scanner could not answer for
        stops the processing (`ScanUnavailableError`), to be tried again."""
        attached: list[_Attached] = []
        for a in message.attachments:
            try:
                content = await self.inbox.read_attachment(
                    scope, message.message_id, a.attachment_id
                )
            except AttachmentInfectedError as infected:
                attached.append(_Attached(a.attachment_id, None, infected.signature))
                continue
            except AttachmentRefusedError as refused:
                attached.append(_Attached(a.attachment_id, None, refused=refused.reason))
                continue
            attached.append(_Attached(a.attachment_id, content))
        return attached

    def _carries_document(self, attached: Sequence[_Attached]) -> bool:
        """Whether a file in it is a document: by its bytes, or by the name of
        one refused unread for not being what it says (ticket 25), whose
        message is then routed with that reason rather than read as mail."""
        return any(
            item.refused is not None
            or (item.content is not None and self.reader.sniff(item.content.data) is not None)
            for item in attached
        )

    def _kind(self, message: InboundMessage, attached: Sequence[_Attached]) -> MessageKind:
        """The keyword tables: for a message no reader accepted, while the
        tenant's rules leave the model reading off."""
        carries_document = self._carries_document(attached)
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


def _stamped(outcome: IntakeOutcome, reading: IntentReading | None) -> IntakeOutcome:
    """The outcome with the model reading's stamp on its disposition."""
    if reading is None or outcome.disposition is None:
        return outcome
    disposition = MessageDisposition.model_validate(
        {**outcome.disposition.model_dump(), "reading": reading}
    )
    return IntakeOutcome(outcome.message_id, outcome.kind, disposition, outcome.case)


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
