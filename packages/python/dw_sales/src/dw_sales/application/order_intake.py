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
**Then the thread.** A message whose mail thread (`In-Reply-To`/`References`,
`threads.py`) holds a case of the sender's own customer is a reply on it, and
is attached to it (tickets 32 and 24, `ThreadLinkPort`): a "Re:" to a spec
discussion is no new request, whatever its subject repeats. A thread holding
several cases: the numbers the message names choose, as a local model reads
them and code resolves them against the sender's customer (`named_cases`,
where the tenant's rules turn the intent step on); naming none of them, or with
no model, it is routed `reply_to_case` with those cases for Sales to pick
(`thread_cases`), never a guess. Where the tenant's rules turn it on, a local
model reads the reply's thread intents (`ReplyReader`, ticket 26), or, where
they turn that on, reads them with read-only tools first and falls back to the
one call (`ThreadAgent`, tickets 30 and 31); the case and the step are code's.
A message Sales sent never reaches this intake (`outgoing.py`, ticket 25).
**A tenant's own PO layouts read first.** A customer's form a person mapped and
another approved (ticket 30) is read with that layout, the tenant's data;
otherwise with the platform's. The first POs a new layout reads keep every
value `value_uncertain` (`layout_onboarding`). A PO no layout reads is routed
`attachment_unreadable`, and where the tenant turns it on a local model
pre-fills the onboarding screen's mapping (`LayoutPrefiller`).
A message routed as a delivery change, a complaint or a sample request carries,
where the tenant turns it on, a hand-off to PC or QA a local model pre-filled
with the customer's own words and code verified (ticket 33, `HandoffReader`).
A message still routed ``other`` carries, where the tenant turns it on, a
triage card (`TriageReader`): what it seems to be by the tenant's mail kinds,
the case of the sender's customer it seems to concern and one legal step,
advice until Sales takes or dismisses it; its routing is unchanged.
Only a message no reader accepted is classified by its words, and only by a
local model's typed intent where the tenant's rules turn it on and its bar
is met (`message_intent`, dw_sales ADR 0005), which code maps to the route
(`INTENT_ROUTES`). Where the tenant turns it on, the kinds are first the ones
its mail-classifying skill names, each mapped by the skill onto one of those
routes (`mail_kinds`, ticket 42); with no kind read, the one call reads.
**No keyword table decides what a mail means** (CLAUDE.md §6, hardcode audit
finding 6): with the step off or no model wired, a person
reads it, except a mail a verified Design mailbox sent, which goes to the
quotation flow as Design's (an identity code checks, `DesignSenderPort`).
A mail carrying a document no reader accepted is routed
`attachment_unreadable` (its file is what is unread, whatever its words), or
`customer_unknown` when no customer is its sender's (no layout was tried);
any other is routed ``other`` with its subject. So the order is: a readable
document, then the thread headers, then the model, then a person. The model
never sets a value.

**A PO a person uploaded is that customer's PO** ("Tải PO lên", ticket 18):
the customer is the one they chose, which the server stamped on the stored
message (`UploadLookupPort`), never the sender (the person) and never
anything the message carries. It is a PO by that person's word: when no
reader accepts its file it goes the way of a PO no layout reads, and no
model classifies it.

**One case per PO number** (tickets 19 and 22, `po_groups`): the files'
lines are grouped by PO number after reading, a line's own or its file's,
and each PO number opens or joins its own case, every one on the same stored
message, which is recorded once (`MessageDisposition.more_cases`). The same
PO number in two files is one case, the files compared value by value and
neither winning. A mail is processed whole: when one of its POs is routed to
Sales (a late revision, a revision of a closed case, two files that are not
one PO), the mail is, and no case of it opens; reprocessing it opens no
second set, since the message's disposition is its idempotency key.

**The body never changes a value.** Customer, items, quantities, prices and
dates come from the sender's domain (or, for a forwarded PO, the buyer the
document names, which Sales then confirms; for an uploaded PO, the customer
the person chose), the attachment's cells and the master data. The body is
read for routing alone, and only when the subject and the attachment names
say nothing.

**A file is what its bytes say.** Attachments are routed by sniffing their
content, never by their name or the media type the sender declared.

**A file locked with a password is opened with its own mail's** (ticket 17):
the scanned mailbox hands it over locked, the reader sandbox opens it with
the candidates the mail carries, and every value read from it is flagged for
Sales. One none of them opens routes the message `attachment_locked`, as an
unreadable file is routed; the password is never held here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final, Protocol
from zoneinfo import ZoneInfo

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.agent_turn import TurnCeilingReachedError
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import ConflictError, QuotaExceededError
from dw_platform.application.malware import (
    AttachmentInfectedError,
    AttachmentRefusedError,
)
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import AttachmentContent, InboundMessage
from dw_sales.application.autonomy import AutonomyGate
from dw_sales.application.examples import Lookup
from dw_sales.application.handoff_kinds import HandoffKindReader
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.layouts import LayoutPrefiller, LearnedLayout
from dw_sales.application.linked_quotes import LinkedQuotesPort
from dw_sales.application.local_time import LocalZonePort, local_day
from dw_sales.application.mail_kinds import MailKindReader
from dw_sales.application.message_intent import IntentRead, IntentReader
from dw_sales.application.model_reading import DescriptionReader, Showing
from dw_sales.application.order_ports import (
    READ_AS,
    DesignSenderPort,
    LayoutLookupPort,
    ModelStepGatePort,
    OrderCaseLookupPort,
    OrderRulesPort,
    PoDocumentReaderPort,
    PoUpload,
    QuoteFormPort,
    ThreadLinkPort,
    UploadLookupPort,
)
from dw_sales.application.po_body_reading import PoBodyReader
from dw_sales.application.ports import (
    CatalogNotConnectedError,
    InboxPort,
    SalesCatalogPort,
    SalesScope,
    Snapshot,
)
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.shadow import ShadowReadings
from dw_sales.application.support import decided
from dw_sales.application.thread_agent import ThreadAgent
from dw_sales.application.threads import ThreadedCase, named_cases
from dw_sales.application.triage import TriageReader
from dw_sales.domain.catalog import ConvertEntry, Customer, Item, LmeMonth, customers_named
from dw_sales.domain.description_reading import GateRoute
from dw_sales.domain.dispositions import (
    MAX_MESSAGE_CASES,
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
    ThreadCase,
)
from dw_sales.domain.handoffs import Handoff, HandoffKind
from dw_sales.domain.layouts import (
    LayoutPrefill,
    LayoutSample,
    PoLayout,
    flagged_as_new,
    layout_ref,
)
from dw_sales.domain.message_intent import IntentKind, IntentReading
from dw_sales.domain.order_checks import (
    CUSTOMER_CHECK_CODES,
    DOCUMENT_CHECK_CODES,
    HISTORY_CHECK_CODES,
    IntakeCaps,
    MappedLine,
    ModelStep,
    OrderRules,
    check_customer,
    check_document,
    check_history,
    check_line,
    current_quotation,
    map_line,
    wants_reading,
)
from dw_sales.domain.order_quotes import quoted_for_po
from dw_sales.domain.orders import (
    Actor,
    AppliedChange,
    BravoHistory,
    Corrected,
    Finding,
    FindingCode,
    ImpliedTerm,
    InternalReason,
    LineCheck,
    LineMapping,
    MappingStatus,
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
from dw_sales.domain.po_body_autonomy import may_apply_itself, model_read_values
from dw_sales.domain.po_groups import ReadFile, one_per_po
from dw_sales.domain.reply_intent import AgentFallback, Author, CaseReply, ReplyReading
from dw_sales.domain.revision_hints import name_revision
from dw_sales.domain.shadow import (
    REPLY_SHADOW_STEPS,
    description_shadows,
    kind_shadow,
    reply_shadow,
)


class MessageKind(StrEnum):
    PO = "po"
    REVISED_PO = "revised_po"
    QUOTE_REQUEST = "quote_request"
    DESIGN_REPLY = "design_reply"
    # A reply on a case its thread headers name (ticket 32).
    CASE_REPLY = "case_reply"
    OTHER = "other"


_LOG = logging.getLogger("dw_sales.model")

# Handed to the quotation flow, which gives them their disposition.
QUOTATION_KINDS = frozenset({MessageKind.QUOTE_REQUEST, MessageKind.DESIGN_REPLY})

# Where each kind a model reads goes (ticket 31): the legal routes, which a
# tenant's mail-classifying skill maps each of its kinds onto (ticket 42,
# `mail_kinds.ROUTES` is this table's keys). The order and quotation
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
    "portal_notice": RoutingReason.PORTAL_NOTICE,
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
# Why a message about an order goes to Sales when no PO is read from it.
NO_DOCUMENT: Final = "it names an order but carries no document"

# Why a message no reader, thread or model classified goes to a person.
UNREAD_DOCUMENT: Final = "a document no reader accepted, and no model read the mail"
NOT_CLASSIFIED: Final = "no model read the mail"
UNKNOWN_SENDER: Final = "a document from a sender who is no customer, so no layout reads it"
# Why a reply goes to Sales when its thread holds several cases (ticket 24).
THREAD_CASES_UNNAMED: Final = "its mail thread holds several cases and it names none of them"


@dataclass(frozen=True)
class Classification:
    """What a message is, and what decided it.

    ``reason`` and ``detail`` say why an ``other`` message goes to Sales (a
    model's kind, two kinds of document, nothing that read it); without a
    reason it is ``other``. ``reading`` is the model reading's
    stamp, for the disposition. ``retry``: the model gave no usable answer
    and the message is young enough to try again, so it stays not yet
    processed (`ModelAssist.unread_retry_hours`). ``thread``: the case a
    `case_reply` is attached to. ``candidates``: the cases a reply's thread
    holds when it names none of them, offered to Sales (ticket 24).
    """

    kind: MessageKind
    reason: RoutingReason | None = None
    detail: str | None = None
    reading: IntentReading | None = None
    retry: bool = False
    thread: ThreadedCase | None = None
    candidates: tuple[ThreadedCase, ...] = ()


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
    # The further cases the message's other POs opened or joined (ticket 19),
    # in the disposition's order (`MessageDisposition.more_cases`).
    more_cases: tuple[OrderCase, ...] = ()
    # The layout DW1 learned to read the PO with (dw_sales ADR 0006), stored
    # by the caller with the case, in its transaction.
    learned: LearnedLayout | None = None

    @property
    def cases(self) -> tuple[OrderCase, ...]:
        """Every case to store, the disposition's first first."""
        return () if self.case is None else (self.case, *self.more_cases)


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
class CustomerPoReading:
    """The normal reading of a customer's PO file: with the tenant's own
    approved layout of the customer's form where it has one (ticket 30), the
    platform's otherwise. Intake reads every PO through it, and so does the
    replay of a worked example (ticket 38): one reading, not two."""

    reader: PoDocumentReaderPort
    layouts: LayoutLookupPort | None

    async def stored_layout(
        self, scope: SalesScope, customer_code: str, content: AttachmentContent
    ) -> PoLayout | None:
        if self.layouts is None:
            return None
        read_as = READ_AS.get(self.reader.sniff(content.data) or "", "")
        kind = {"xlsx": "excel", "pdf": "pdf", "csv": "csv"}.get(read_as)
        approved = await self.layouts.approved(scope, customer_code)
        return next((layout for layout in approved if layout.kind == kind), None)

    async def read(
        self, scope: SalesScope, content: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        stored = await self.stored_layout(scope, customer_code, content)
        return await self.read_through(content, customer_code, caps, stored)

    async def read_through(
        self,
        content: AttachmentContent,
        customer_code: str,
        caps: IntakeCaps,
        stored: PoLayout | None,
    ) -> PoDocument | Unreadable:
        """``content`` read through ``stored``, the layout `stored_layout`
        found, or the platform's layouts where it found none."""
        if stored is None:
            return await self.reader.read(content, customer_code, caps)
        return await self.reader.read_with(content, stored.mapping, caps, layout_ref=stored.ref)


class FormRecognitionPort(Protocol):
    """Whether a message's files read into a request by one of the
    customer's document forms (`document_forms.DocumentFormReader`)."""

    async def recognises(
        self,
        scope: SalesScope,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        received_on: date,
        run: RunContext,
    ) -> bool: ...


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
    # The tenant's time zone, where the day a message arrived is counted
    # (the received date, the lead time's start): `working_hours.time_zone`,
    # its one owner (audit 14).
    zones: LocalZonePort
    # A model reading of the descriptions DW1's vocabulary does not read
    # (dw_sales ADR 0005), for a tenant whose rules turn it on. None: no model
    # is wired in this process, and those lines stay unmapped as before.
    descriptions: DescriptionReader | None = None
    # A model reading of the intent of a message no reader accepted (ticket
    # 31), for a tenant whose rules turn it on. None: no model is wired, and
    # a person reads those messages (module docstring).
    intents: IntentReader | None = None
    # The same classification by the kinds the tenant's mail-classifying
    # skill names (ticket 42), asked first where the tenant's rules turn it
    # on; with no kind read, the message is classified as if it were off.
    # None: no model is wired.
    mail_kinds: MailKindReader | None = None
    # A card for a message still routed ``other`` (ticket 33): what it seems
    # to be by the tenant's mail kinds, the case it seems to concern and one
    # step, for Sales to take or dismiss; where the tenant's rules turn it
    # on. The routing stays as it is. None: no model is wired, and no card.
    triage: TriageReader | None = None
    # A customer's own request form, read by the forms the tenant's
    # document-forms skill names for the sender's customer (ticket 42 family
    # 3): a file it reads into a request makes the mail a quotation request,
    # beside the ``RFQ No.`` marker (`quote_forms`), never instead of it;
    # where the tenant's rules turn it on. None: no model is wired.
    document_forms: FormRecognitionPort | None = None
    # The case a reply's thread headers name (ticket 32). None: no case log is
    # wired (a reader-only test), and no reply is linked.
    threads: ThreadLinkPort | None = None
    # A model reading of such a reply, for a tenant whose rules turn it on.
    # None: no model is wired, and the reply is attached unread.
    replies: ReplyReader | None = None
    # The same reading with read-only tools first (tickets 30 and 31), for a
    # tenant whose rules turn it on; over its ceiling or with no usable
    # answer, `replies` reads it, else a person. None: no tool-calling model
    # is wired in this process.
    thread_agent: ThreadAgent | None = None
    # DW1's agent with its skills (ticket 40, dw_sales ADR 0014), asked before
    # the thread agent, for a tenant whose rules turn it on; without a
    # reading of its own, the thread agent reads it, else the one call, else
    # a person. None: no tool-calling model is wired in this process.
    skill_agent: ThreadAgent | None = None
    # A model pre-filling a routed message's hand-off to PC or QA (ticket 33),
    # for a tenant whose rules turn it on. None: no model is wired, and the
    # message is routed with no hand-off, as before.
    handoffs: HandoffReader | None = None
    # The same hand-off by the kinds the tenant's hand-off skill names (ticket
    # 42 family 5), asked first where its step runs; with no kind of it for
    # the message or no usable answer, `handoffs` reads it as before. None:
    # no model is wired here.
    handoff_kinds: HandoffKindReader | None = None
    # The PO layouts the tenant approved (ticket 30). None: none are stored in
    # this process (a reader-only test), and the platform's layouts read.
    layouts: LayoutLookupPort | None = None
    # A model pre-filling the mapping of a form no layout reads (ticket 30),
    # for a tenant whose rules turn it on. None: no model is wired.
    layout_prefiller: LayoutPrefiller | None = None
    # A model reading a PO written in the mail body, with no file (AI item 4),
    # for a tenant whose rules turn it on. None: no model is wired, and such a
    # message is routed to Sales as before.
    body_pos: PoBodyReader | None = None
    # Whether a model step the tenant's rules turn on may run: its live eval
    # met the bar for the model and prompt it runs on now (dw_sales ADR 0005,
    # addendum of 2026-10-23). Asked before every model call above; where it
    # says no, the step does what it does when it is off. None: no step may
    # run, whatever the rules say.
    model_steps: ModelStepGatePort | None = None
    # What code's gate does with a line's one candidate a model reading gave
    # (dw_sales ADR 0015, ticket 44): stamped on the reading, then applied by
    # `AutoApply` once the case is stored where it says so. None: no
    # threshold is read here, and every such line goes to a person.
    autonomy: AutonomyGate | None = None
    # Whether a verified Design mailbox sent a message no reader, thread or
    # model classified: Design's answer written in the mail (AI item 6) goes
    # to the quotation flow, which matches it by its YCBG or routes it as
    # `design_reply_unmatched` with the reader of its text. None: no Design
    # mailbox is known here (a reader-only test).
    design_senders: DesignSenderPort | None = None
    # The id a learned layout is stored under (dw_sales ADR 0006).
    new_layout_id: Callable[[], uuid.UUID] = uuid.uuid4
    # Which stored messages are POs a person uploaded, and for which customer
    # (ticket 18). None: no upload is stored in this process (the mock
    # mailbox), and every message's customer is its sender's.
    uploads: UploadLookupPort | None = None
    # The quote cases opened from an order for its lines with no valid
    # quotation (ticket 09): an approved one is the quotation those lines are
    # checked against. None: none is read here, and such a line keeps
    # `quotation_missing`, never a pass.
    linked_quotes: LinkedQuotesPort | None = None
    # Where a step the tenant lists in shadow reads while it is not on and
    # passing, and keeps what it read for a person's decision to label
    # (ticket 67). None: nothing reads in shadow here.
    shadow: ShadowReadings | None = None

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

    async def reads_thread_intents(self, scope: SalesScope) -> bool:
        """Whether a thread message's intents are read for this tenant now:
        a model and a thread log wired, the step on in its rules and measured
        at its bar (ticket 26). The mailbox lane asks it before taking up a
        message Sales sent, which costs a run. Either reading counts: the
        thread agent's (tickets 30 and 31) or the one call's."""
        if self.threads is None:
            return False
        rules = await self.rules.rules(scope)
        for agent, step in self._agents():
            if agent is not None and await self._model_step(scope, rules, step):
                return True
        return self.replies is not None and await self._model_step(
            scope, rules, ModelStep.REPLY_INTENT
        )

    def _agents(self) -> tuple[tuple[ThreadAgent | None, ModelStep], ...]:
        """The readers with tools, in the order asked: DW1's agent with its
        skills (ticket 40), then the thread agent (tickets 30 and 31)."""
        return (
            (self.skill_agent, ModelStep.SKILL_INTENTS),
            (self.thread_agent, ModelStep.THREAD_AGENT),
        )

    async def read_sent(
        self, scope: SalesScope, message: InboundMessage, *, run: RunContext
    ) -> ReplyReading | None:
        """What a message Sales sent does (tickets 25 and 26), read where
        `reads_thread_intents` says so and its thread holds a case it is
        addressed to (`ThreadLinkPort.sent_cases`); None otherwise. Nothing
        else of it is read: no customer, no document, no value."""
        if not await self.reads_thread_intents(scope):
            return None
        assert self.threads is not None  # said above
        cases = await self.threads.sent_cases(scope, message)
        if not cases:
            return None
        return await self._read_thread(
            scope,
            message,
            author="sales",
            about=" ".join(case.question for case in cases),
            cases=cases,
            rules=await self.rules.rules(scope),
            run=run,
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
            reply = await self._reply(scope, message, classification.thread, run)
            return _stamped(reply, classification.reading)
        sender = await self._customer(scope, message, await self._upload(scope, message))
        if kind is MessageKind.OTHER and classification.detail == UNREAD_DOCUMENT:
            # Which file was not read, and why, as a PO's files are told
            # (`_order`): what the mail is stays the person's to say.
            outcome = await self._order(scope, message, kind, sender, attached, run)
        elif kind is MessageKind.OTHER:
            reason = classification.reason or RoutingReason.OTHER
            outcome = self._routed(
                message, kind, reason, sender, classification.detail, classification.candidates
            )
            outcome = await self._with_handoff(
                scope, message, outcome, sender, classification.reading, run
            )
            outcome = await self._with_triage(
                scope, message, outcome, sender, classification.reading, run
            )
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
        upload = await self._upload(scope, message)
        sender = await self._customer(scope, message, upload)
        rules = await self.rules.rules(scope)
        by_content = await self._by_content(scope, attached, sender, rules.intake)
        if (
            not by_content
            and upload is None
            and await self._a_form(scope, message, attached, sender, rules, run)
        ):
            by_content = {MessageKind.QUOTE_REQUEST}
        if len(by_content) > 1:
            return Classification(
                MessageKind.OTHER,
                RoutingReason.OTHER,
                "its attachments read as more than one kind of document",
            )
        if by_content:
            (kind,) = by_content
            return Classification(kind)
        if upload is not None:
            # A person uploaded it as a PO: no reader read it, so it goes the
            # way a PO no layout reads goes (module docstring).
            return Classification(MessageKind.PO)
        if self.threads is not None and message.references:
            cases = await self.threads.cases(scope, message, sender)
            if len(cases) == 1:
                return Classification(MessageKind.CASE_REPLY, thread=cases[0])
            if cases:
                return await self._among(scope, message, sender, rules, cases, run, now)
        if (
            self.mail_kinds is not None
            and run is not None
            and await self._model_step(scope, rules, ModelStep.SKILL_MAIL_KINDS)
        ):
            read = await self.mail_kinds.read(
                scope, newest_part(message), sender, rules_version=rules.version, run=run
            )
            if read is not None:
                return await self._routed_read(scope, read, attached, rules, run)
        if (
            self.intents is not None
            and run is not None
            and await self._model_step(scope, rules, ModelStep.MESSAGE_INTENT)
        ):
            return await self._intent(scope, message, attached, sender, rules, run, now)
        if self.design_senders is not None and await self.design_senders.from_design(
            scope, message
        ):
            return Classification(MessageKind.DESIGN_REPLY)
        await self._shadow_kind(scope, message, sender, rules, run)
        return _for_a_person(
            message, carries_document=self._carries_document(attached), sender=sender
        )

    async def _shadow_kind(
        self,
        scope: SalesScope,
        message: InboundMessage,
        sender: Customer | None,
        rules: OrderRules,
        run: RunContext | None,
    ) -> None:
        """The kind `message_intent` reads in shadow of a mail going to a
        person (ticket 67): kept for the kind the person picks as they mark
        it handled. A shadow reading never fails the mail."""
        step = ModelStep.MESSAGE_INTENT
        if self.intents is None or self.shadow is None or run is None:
            return
        if not await self.shadow.shadows(scope, rules, step):
            return
        try:
            read = await self.intents.read(
                scope, newest_part(message), sender, rules_version=rules.version, run=run
            )
        except (ModelUnavailableError, BudgetExceededError, QuotaExceededError) as exc:
            _LOG.info(
                "shadow reading of %s gave nothing for %s in tenant %s: %s",
                step.value,
                message.message_id,
                scope.tenant_id.value,
                type(exc).__name__,
            )
            return
        if read is None:
            return
        await self.shadow.keep(
            scope,
            [
                kind_shadow(
                    read.route,
                    read.reading,
                    message_id=message.message_id,
                    at=self.shadow.clock.now(),
                    new_id=uuid.uuid4,
                )
            ],
        )

    async def customer_of(self, scope: SalesScope, message: InboundMessage) -> Customer | None:
        """Whose message it is, as intake reads it: the one answer the layout
        screen asks too, so a form mapped from an uploaded PO is that
        customer's (ticket 18)."""
        return await self._customer(scope, message, await self._upload(scope, message))

    async def _upload(self, scope: SalesScope, message: InboundMessage) -> PoUpload | None:
        """The upload the server stamped on the stored message, if it is one."""
        if self.uploads is None:
            return None
        return await self.uploads.upload_of(scope, message.message_id)

    async def _customer(
        self, scope: SalesScope, message: InboundMessage, upload: PoUpload | None
    ) -> Customer | None:
        """Whose message it is: the customer a person chose for a PO they
        uploaded, else the sender's (by address, then domain)."""
        if upload is not None:
            return (await self.catalog.customer_by_code(scope, upload.customer_code)).data
        return (await self.catalog.customer_by_sender(scope, message.sender.address)).data

    async def _received_on(self, scope: SalesScope, at: datetime) -> date:
        """The day ``at`` falls on where the tenant works (`zones`)."""
        return local_day(at, await self.zones.time_zone(scope))

    async def _model_step(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        """Whether ``step`` may call a model for this tenant now: on in its
        rules and measured at its bar (`model_steps`); never without a gate."""
        return self.model_steps is not None and await self.model_steps.allows(scope, rules, step)

    async def _reads_body(
        self,
        scope: SalesScope,
        rules: OrderRules,
        attached: Sequence[_Attached],
        run: RunContext | None,
    ) -> bool:
        """Whether a PO written in the mail may be read (AI item 4): it
        carries no document, a reader and a DW1 run are here, and the step
        may run for the tenant now."""
        return (
            self.body_pos is not None
            and run is not None
            and not self._carries_document(attached)
            and await self._model_step(scope, rules, ModelStep.PO_BODY_EXTRACTION)
        )

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

    async def _a_form(
        self,
        scope: SalesScope,
        message: InboundMessage,
        attached: Sequence[_Attached],
        sender: Customer | None,
        rules: OrderRules,
        run: RunContext | None,
    ) -> bool:
        """Whether the message's files read as a request by one of the
        tenant's document forms for the sender's customer (ticket 42 family
        3): asked only where no reader recognised a file, the sender's
        domain names a customer, a DW1 run is here and the step may run for
        the tenant now. Nothing read is no form, and the message is
        classified as before."""
        contents = [item.content for item in attached if item.content is not None]
        if (
            self.document_forms is None
            or run is None
            or sender is None
            or not contents
            or not await self._model_step(scope, rules, ModelStep.SKILL_DOCUMENT_FORMS)
        ):
            return False
        return await self.document_forms.recognises(
            scope,
            contents,
            sender,
            rules,
            received_on=await self._received_on(scope, message.received_at),
            run=run,
        )

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
        return await self._routed_read(scope, read, attached, rules, run)

    async def _routed_read(
        self,
        scope: SalesScope,
        read: IntentRead,
        attached: Sequence[_Attached],
        rules: OrderRules,
        run: RunContext,
    ) -> Classification:
        """Where a kind read goes: its route's row of `INTENT_ROUTES`, the
        one table for the one call's kinds and the tenant's (ticket 42)."""
        route = INTENT_ROUTES[read.route]
        if isinstance(route, RoutingReason):
            return Classification(MessageKind.OTHER, route, reading=read.reading)
        if (
            route is MessageKind.PO
            and not self._carries_document(attached)
            and not await self._reads_body(scope, rules, attached, run)
        ):
            # A message about a PO is not a PO: it has to carry one, or, where
            # a model reads it, be written in the mail.
            return Classification(MessageKind.OTHER, RoutingReason.OTHER, NO_DOCUMENT, read.reading)
        return Classification(route, reading=read.reading)

    async def _among(
        self,
        scope: SalesScope,
        message: InboundMessage,
        sender: Customer | None,
        rules: OrderRules,
        cases: tuple[ThreadedCase, ...],
        run: RunContext | None,
        now: datetime | None,
    ) -> Classification:
        """A reply whose thread holds several cases (ticket 24): the one its
        numbers name, as a model reads them and code resolves them against
        the sender's customer (`IntentReader.resolve`), where the tenant's
        rules turn the intent step on; else routed `reply_to_case` with the
        cases for Sales to pick. No usable answer from the model: tried
        again while the message is young, then Sales picks."""
        reading = None
        if (
            self.intents is not None
            and run is not None
            and await self._model_step(scope, rules, ModelStep.MESSAGE_INTENT)
        ):
            read = await self.intents.read(
                scope, newest_part(message), sender, rules_version=rules.version, run=run
            )
            if read is None:
                window = timedelta(hours=rules.model_assist.unread_retry_hours)
                if now is not None and now - message.received_at < window:
                    return Classification(MessageKind.OTHER, retry=True)
                reading = self.intents.unavailable(rules.version)
            else:
                reading = read.reading
                named = named_cases(cases, reading.references)
                if len(named) == 1:
                    return Classification(MessageKind.CASE_REPLY, thread=named[0], reading=reading)
        return Classification(
            MessageKind.OTHER,
            RoutingReason.REPLY_TO_CASE,
            THREAD_CASES_UNNAMED,
            reading,
            candidates=cases,
        )

    async def _reply(
        self,
        scope: SalesScope,
        message: InboundMessage,
        thread: ThreadedCase,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """A reply attached to the case its thread names, with a model's
        reading of it where the tenant's rules, a wired model and a DW1 run
        allow. Nothing on the case changes: Sales confirms any step. Each
        reply reader that is not on and passing reads it in shadow where the
        tenant's rules allow (ticket 67), for the PIC's next move to label."""
        rules = await self.rules.rules(scope)
        reading = (
            None
            if run is None
            else await self._read_thread(
                scope,
                message,
                author="customer",
                about=thread.question,
                cases=(thread,),
                rules=rules,
                run=run,
            )
        )
        if run is not None:
            await self._shadow_reply(scope, message, thread, rules, run)
        disposition = MessageDisposition(
            message_id=message.message_id,
            kind=DispositionKind.ATTACHED_TO_CASE,
            case_kind=thread.case_kind,
            case_id=thread.case_id,
            customer_code=thread.customer_code,
            reply=CaseReply(linked_to=thread.linked_to, reading=reading),
        )
        return IntakeOutcome(message.message_id, MessageKind.CASE_REPLY, disposition)

    async def _shadow_reply(
        self,
        scope: SalesScope,
        message: InboundMessage,
        thread: ThreadedCase,
        rules: OrderRules,
        run: RunContext,
    ) -> None:
        """What each reply reader not on and passing reads of a customer's
        reply in shadow, kept beside its case (ticket 67). A shadow reading
        never fails the mail: a reader that gives nothing keeps nothing."""
        if self.shadow is None:
            return
        kept = []
        for step in REPLY_SHADOW_STEPS:
            if await self._model_step(scope, rules, step):
                continue
            if not await self.shadow.shadows(scope, rules, step):
                continue
            reading = await self._shadow_read(scope, message, thread, rules, run, step)
            shadow = (
                None
                if reading is None
                else reply_shadow(
                    step,
                    reading,
                    message_id=message.message_id,
                    case_kind=thread.case_kind,
                    case_id=thread.case_id,
                    status=thread.status,
                    at=self.shadow.clock.now(),
                    new_id=uuid.uuid4,
                )
            )
            if shadow is not None:
                kept.append(shadow)
        await self.shadow.keep(scope, kept)

    async def _shadow_read(
        self,
        scope: SalesScope,
        message: InboundMessage,
        thread: ThreadedCase,
        rules: OrderRules,
        run: RunContext,
        step: ModelStep,
    ) -> ReplyReading | None:
        """``step``'s reader alone on the reply, as it reads when it is on;
        None where it gives no reading."""
        try:
            if step is ModelStep.SKILL_INTENTS:
                if self.skill_agent is None:
                    return None
                return await self.skill_agent.read(
                    scope,
                    message,
                    author="customer",
                    about=thread.question,
                    cases=(thread,),
                    rules_version=rules.version,
                    run=run,
                    pick_floor=rules.model_assist.skill_pick_confidence,
                )
            if self.replies is None:
                return None
            return await self.replies.read(
                newest_part(message),
                author="customer",
                about=thread.question,
                rules_version=rules.version,
                run=run,
            )
        except (
            ModelUnavailableError,
            TurnCeilingReachedError,
            BudgetExceededError,
            QuotaExceededError,
        ) as exc:
            # Ids and the reason only: never the message.
            _LOG.info(
                "shadow reading of %s gave nothing for %s in tenant %s: %s",
                step.value,
                message.message_id,
                scope.tenant_id.value,
                type(exc).__name__,
            )
            return None

    async def _read_thread(
        self,
        scope: SalesScope,
        message: InboundMessage,
        *,
        author: Author,
        about: str,
        cases: Sequence[ThreadedCase],
        rules: OrderRules,
        run: RunContext,
    ) -> ReplyReading | None:
        """A thread message's intents, read by the steps the tenant's rules
        turn on and their bars allow: DW1's agent with its skills first
        (ticket 40), then the thread agent (tickets 30 and 31), then the
        one-call reading (ticket 26). Where an agent was asked and gave no
        reading, the one-call reading is stamped with why (the last agent's,
        `ReplyReading.fallback`), or, with that step off too, an unread
        reading is, for Sales. None: no step runs."""
        fallback: AgentFallback | None = None
        asked: ThreadAgent | None = None
        for agent, step in self._agents():
            if agent is None or not await self._model_step(scope, rules, step):
                continue
            try:
                agents_reading = await agent.read(
                    scope,
                    message,
                    author=author,
                    about=about,
                    cases=cases,
                    rules_version=rules.version,
                    run=run,
                    pick_floor=rules.model_assist.skill_pick_confidence,
                )
                if agents_reading is None:
                    # No skill picked surely enough (ticket 40): read as if
                    # the step were off, and say nothing of it.
                    continue
                return agents_reading
            except TurnCeilingReachedError as exc:
                fallback = exc.ceiling
            except ModelUnavailableError:
                fallback = "unavailable"
            asked = agent
            # Ids and the reason only: never the message.
            _LOG.info(
                "%s gave no reading of %s for tenant %s: %s",
                step.value,
                message.message_id,
                scope.tenant_id.value,
                fallback,
            )
        if self.replies is not None and await self._model_step(
            scope, rules, ModelStep.REPLY_INTENT
        ):
            reading = await self.replies.read(
                newest_part(message),
                author=author,
                about=about,
                rules_version=rules.version,
                run=run,
            )
            if fallback is None:
                return reading
            return ReplyReading.model_validate({**reading.model_dump(), "fallback": fallback})
        if fallback is not None and asked is not None:
            return asked.unavailable(rules.version, fallback)
        return None

    async def _with_handoff(
        self,
        scope: SalesScope,
        message: InboundMessage,
        outcome: IntakeOutcome,
        sender: Customer | None,
        reading: IntentReading | None,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """The routed outcome with the hand-off a model pre-filled, where the
        sender is a customer, a model is wired, a DW1 run is processing and
        either the tenant's hand-off kinds name the message's kind (ticket 42
        family 5, `_skill_handoff`) or the reason takes one of ticket 33's
        and the tenant's rules turn that step on."""
        disposition = outcome.disposition
        if disposition is None or disposition.reason is None:
            return outcome
        if sender is None or self.handoffs is None or run is None:
            return outcome
        kind = HANDOFF_KINDS.get(disposition.reason)
        rules = await self.rules.rules(scope)
        received_on = await self._received_on(scope, message.received_at)
        handoff = await self._skill_handoff(
            scope, message, disposition.reason, sender, reading, rules, received_on, run
        )
        if handoff is None:
            if kind is None or not await self._model_step(scope, rules, ModelStep.REQUEST_HANDOFF):
                return outcome
            handoff = await self.handoffs.read(
                scope,
                newest_part(message),
                sender,
                kind,
                received_on=received_on,
                rules_version=rules.version,
                run=run,
            )
        # With the reading it may be of (its kind, ticket 42 family 5), which
        # `_stamped` puts on every routed disposition anyway.
        read = {} if reading is None else {"reading": reading}
        stamped = MessageDisposition.model_validate(
            {**disposition.model_dump(), "handoff": handoff, **read}
        )
        return IntakeOutcome(outcome.message_id, outcome.kind, stamped, outcome.case)

    async def _skill_handoff(
        self,
        scope: SalesScope,
        message: InboundMessage,
        reason: RoutingReason,
        sender: Customer,
        reading: IntentReading | None,
        rules: OrderRules,
        received_on: date,
        run: RunContext,
    ) -> Handoff | None:
        """The hand-off by the tenant's hand-off kinds, where their step may
        run: the kind the message's reading stamped, else the platform kind
        of its reason, and only where the reading routed it here (a reading
        opens no door code would not). None: as with the step off."""
        if self.handoff_kinds is None:
            return None
        names: list[str] = []
        routed = None if reading is None else reading.routed
        if reading is not None and reading.kind and routed and INTENT_ROUTES[routed] is reason:
            names.append(reading.kind)
        if reason in HANDOFF_KINDS:
            names.append(HANDOFF_KINDS[reason])
        if not names or not await self._model_step(scope, rules, ModelStep.SKILL_HANDOFFS):
            return None
        return await self.handoff_kinds.read(
            scope,
            newest_part(message),
            sender,
            names,
            received_on=received_on,
            rules_version=rules.version,
            run=run,
        )

    async def _with_triage(
        self,
        scope: SalesScope,
        message: InboundMessage,
        outcome: IntakeOutcome,
        sender: Customer | None,
        reading: IntentReading | None,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """The outcome with a triage card, where the message is routed
        ``other``, a card reader is wired, a DW1 run is processing, the
        tenant's rules turn the step on and it meets its bar, and the
        tenant's mail kinds did not already read it (the card would ask the
        same question again). The disposition is otherwise the one it had."""
        disposition = outcome.disposition
        if (
            disposition is None
            or disposition.reason is not RoutingReason.OTHER
            or (reading is not None and reading.skill is not None)
            or self.triage is None
            or run is None
        ):
            return outcome
        rules = await self.rules.rules(scope)
        if not await self._model_step(scope, rules, ModelStep.TRIAGE_CARD):
            return outcome
        card = await self.triage.read(
            scope, newest_part(message), sender, rules_version=rules.version, run=run
        )
        if card is None:
            return outcome
        stamped = MessageDisposition.model_validate({**disposition.model_dump(), "triage": card})
        return replace(outcome, disposition=stamped)

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
            if await self._reads_body(scope, rules, attached, run):
                return await self._body_order(scope, message, sender, rules, run)
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
        locked = False
        for content in readable:
            result = await self._read_po(scope, content, customer.code, caps, flag=rules)
            if isinstance(result, Unreadable):
                reasons.append(f"{content.attachment.attachment_id}: {result.reason}")
                locked = locked or result.locked
            else:
                documents.append(result)
                # A legacy workbook pairs with its print as a workbook does.
                kinds.append(READ_AS.get(self.reader.sniff(content.data) or "", ""))
        if not documents and locked:
            # A file locked with a password none its mail carries opens
            # (ticket 17): Sales opens it by hand; nothing is learned from a
            # form nobody could open.
            reason = RoutingReason.ATTACHMENT_LOCKED
            return self._routed(message, kind, reason, customer, "; ".join(reasons))
        if not documents:
            routed = self._routed(message, kind, unreadable, customer, "; ".join(reasons))
            learned = await self._learn(scope, message, readable, customer, rules, run)
            if isinstance(learned, tuple):
                document, layout = learned
                outcome = await self._case(
                    scope, message, kind, customer, attributed, document, rules, run
                )
                return replace(outcome, learned=layout)
            return _with_prefill(routed, learned)
        # One document per PO number (tickets 19 and 22): a file's several
        # POs apart, the same PO's two files together.
        grouped = one_per_po([ReadFile(d, k) for d, k in zip(documents, kinds, strict=True)])
        if isinstance(grouped, str):
            return self._routed(message, kind, RoutingReason.OTHER, customer, grouped)
        if len(grouped) > MAX_MESSAGE_CASES:
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                customer,
                f"{len(grouped)} PO numbers, more than one message opens cases for",
            )
        if len(grouped) == 1:
            return await self._case(
                scope, message, kind, customer, attributed, grouped[0], rules, run
            )
        return await self._several(scope, message, kind, customer, attributed, grouped, rules, run)

    async def _several(
        self,
        scope: SalesScope,
        message: InboundMessage,
        kind: MessageKind,
        customer: Customer,
        attributed: bool,
        documents: Sequence[PoDocument],
        rules: OrderRules,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """A mail's POs, one case each (ticket 19), all on the one message;
        routed whole, opening none, when any of them would be routed (module
        docstring). The disposition names a case the mail opened first, so
        the case's ingest is the message's, and lists the rest in the mail's
        order."""
        outcomes: list[IntakeOutcome] = []
        for document in documents:
            outcome = await self._case(
                scope, message, kind, customer, attributed, document, rules, run
            )
            if outcome.case is None:
                assert outcome.disposition is not None  # routed by `_case`
                detail = f"PO {document.header.po_no}: {outcome.disposition.detail or ''}"
                return self._routed(message, kind, RoutingReason.OTHER, customer, detail)
            outcomes.append(outcome)
        created = [
            o
            for o in outcomes
            if o.disposition is not None and o.disposition.kind is DispositionKind.CASE_CREATED
        ]
        first = (created or outcomes)[0]
        assert first.case is not None and first.disposition is not None
        more = tuple(o.case for o in outcomes if o is not first and o.case is not None)
        disposition = MessageDisposition(
            message_id=message.message_id,
            kind=first.disposition.kind,
            case_kind=CaseKind.ORDER,
            case_id=first.case.case_id,
            customer_code=customer.code,
            more_cases=tuple(case.case_id for case in more),
        )
        return IntakeOutcome(message.message_id, kind, disposition, first.case, more)

    async def _body_order(
        self,
        scope: SalesScope,
        message: InboundMessage,
        sender: Customer | None,
        rules: OrderRules,
        run: RunContext | None,
    ) -> IntakeOutcome:
        """A PO written in the mail (AI item 4): read by a model, every value
        flagged for Sales to confirm against the mail. The customer is the
        sender's, never a name the mail writes; a PO not read is routed to
        Sales as before, with why."""
        assert self.body_pos is not None and run is not None  # `_reads_body`
        kind = MessageKind.PO
        if sender is None:
            return self._routed(
                message,
                kind,
                RoutingReason.CUSTOMER_UNKNOWN,
                None,
                "the sender's domain matches no customer, and a PO in the mail names no buyer",
            )
        read = await self.body_pos.read(
            message,
            scope=scope,
            customer_code=sender.code,
            received_on=await self._received_on(scope, message.received_at),
            run=run,
        )
        if isinstance(read, str):
            return self._routed(
                message,
                kind,
                RoutingReason.OTHER,
                sender,
                f"{NO_DOCUMENT}; DW1 did not read a PO from the mail ({read})",
            )
        return await self._case(scope, message, kind, sender, False, read, rules, run)

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
        form where it has one, the platform's otherwise (`CustomerPoReading`).
        With ``flag``, the rules under which a PO among the first a new layout
        reads has every value flagged `new_layout`."""
        reading = CustomerPoReading(self.reader, self.layouts)
        stored = await reading.stored_layout(scope, customer_code, content)
        read = await reading.read_through(content, customer_code, caps, stored)
        if stored is None or isinstance(read, Unreadable) or flag is None or self.layouts is None:
            return read
        seen = await self.layouts.read_count(scope, stored.ref)
        if seen < flag.layout_onboarding.uncertain_first_pos:
            return flagged_as_new(read)
        return read

    async def _stored_layout(
        self, scope: SalesScope, customer_code: str, content: AttachmentContent
    ) -> PoLayout | None:
        return await CustomerPoReading(self.reader, self.layouts).stored_layout(
            scope, customer_code, content
        )

    async def _learn(
        self,
        scope: SalesScope,
        message: InboundMessage,
        readable: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        run: RunContext | None,
    ) -> tuple[PoDocument, LearnedLayout] | LayoutPrefill | None:
        """The first form no layout of the customer's reads, mapped by a model
        where the tenant's rules turn the step on, a model is wired and a DW1
        run is processing: read with that mapping and learned when every check
        passed (dw_sales ADR 0006), or the pre-fill as the model left it, for
        Sales to start from. None: nothing was asked."""
        prefiller = self.layout_prefiller
        if prefiller is None or run is None:
            return None
        if not await self._model_step(scope, rules, ModelStep.LAYOUT_PROPOSAL):
            return None
        for content in readable:
            file_type = self.reader.sniff(content.data)
            # A portal's export is mapped by a person (ticket 18): no model
            # pre-fills its columns.
            if file_type is None or file_type in ("unsupported", "csv"):
                continue
            if await self.reader.has_layout(customer.code, file_type):
                continue
            if await self._stored_layout(scope, customer.code, content) is not None:
                continue
            prefill = await prefiller.prefill(scope, content, customer, rules, run=run)
            if prefill is None:
                continue
            if prefill.mapping is None or self.layouts is None:
                return prefill
            layout_id = self.new_layout_id()
            version = await self.layouts.next_version(scope, customer.code, prefill.mapping.kind)
            read = await self.reader.read_with(
                content, prefill.mapping, rules.intake, layout_ref=layout_ref(layout_id, version)
            )
            if isinstance(read, Unreadable):
                return prefill
            learned = LearnedLayout(
                layout_id=layout_id,
                version=version,
                customer_code=customer.code,
                mapping=prefill.mapping,
                sample=LayoutSample(
                    message_id=message.message_id,
                    attachment_id=content.attachment.attachment_id,
                    attachment_sha256=content.attachment.sha256,
                ),
                prefill=prefill,
            )
            # A new layout's first POs are confirmed value by value, learned
            # or approved alike (`layout_onboarding.uncertain_first_pos`).
            if rules.layout_onboarding.uncertain_first_pos > 0:
                read = flagged_as_new(read)
            return read, learned
        return None

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
        document = _named_revision(message, document, rules.revision_marks)
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

        received_on = await self._received_on(scope, message.received_at)
        # A source with nothing to answer (`CatalogNotConnectedError`, audit 1) is
        # read as empty and named on the PO among what nobody checked.
        unchecked: list[str] = []
        items = await _unless_unconnected(self.catalog.items(scope), unchecked)
        lme = await _unless_unconnected(
            self.catalog.lme_for_month(scope, rules.lme_month(header.po_date)), unchecked
        )
        as_of: list[datetime] = [found.as_of for found in (items, lme) if found is not None]
        item_rows = () if items is None else items.data
        mapped_lines: list[tuple[PoLine, MappedLine]] = []
        unread: list[PoLine] = []
        for po_line in document.lines:
            entry = await _unless_unconnected(
                _convert_entry(self.catalog, scope, customer.code, po_line),
                unchecked,
            )
            listed = None if entry is None else entry.data
            as_of += [] if entry is None else [entry.as_of]
            mapped_lines.append((po_line, map_line(po_line, entry=listed, items=item_rows)))
            if wants_reading(po_line, entry=listed):
                unread.append(po_line)
        item = f"{message.message_id}:{document.attachment_id or '-'}"
        read = await self._gated(
            scope,
            await self._read(
                scope,
                unread,
                item_rows,
                rules,
                run,
                customer.code,
                message_id=message.message_id,
                attachment_id=document.attachment_id,
            ),
            rules,
            item=item,
        )
        checks: list[LineCheck] = []
        for po_line, by_code in mapped_lines:
            mapped = read.get(po_line.line_no, by_code)
            check, quoted_as_of = await self._check_line(
                scope,
                customer.code,
                header,
                received_on,
                po_line,
                mapped,
                None if lme is None else lme.data,
                rules,
                unchecked,
                # A revision of a PO a quote was opened for (ticket 09).
                linked=[q for case in earlier for q in case.quotes_for(po_line.line_no)],
            )
            as_of.extend(quoted_as_of)
            checks.append(check)
        # Bravo not connected: DW1's own cases still say duplicate or
        # revision; what Bravo holds is unchecked, never "no duplicate".
        orders = await _unless_unconnected(
            self.catalog.orders_for_po(scope, customer.code, header.po_no), unchecked
        )
        as_of += [] if orders is None else [orders.as_of]
        document = document.with_unchecked(unchecked)
        history = check_history(
            customer.code,
            document,
            {c.line.line_no: c.line.mapping.checked_against for c in checks},
            earlier,
            () if orders is None else orders.data,
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
                received_on=received_on,
                delivery_term=header.delivery_term,
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
            # data newer than this. Where nothing was read, nothing newer than
            # the message.
            catalog_as_of=min(as_of, default=message.received_at),
            cross_check_required=rules.cross_check_required,
            export_control_mode=rules.export_control_mode,
            duplicate_of_case=history.duplicate_of_case,
            duplicate_of_so=history.duplicate_of_so,
            base_so_no=history.base_so_no,
        )
        checked = await self._value_gates(
            scope, checked, rules, item=f"{message.message_id}:{document.attachment_id or '-'}"
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
        item = (await self.catalog.item_by_prv_code(scope, prv_code)).data
        if item is None:
            raise ConflictError(
                "the item master has no such PRV code", details={**details, "field": "prv_code"}
            )
        # The reading the candidates came from, and what it stated, stay the
        # line's evidence.
        mapped = MappedLine(
            line.mapping,
            item,
            line.basis.convert_prv_code,
            line.basis.description_reading,
            line.basis.stated_attributes,
        )
        recheck = await self._line_again(scope, case, line, mapped, details)
        return case.confirm_mapping(line_no, prv_code, actor, at, recheck)

    async def reject_candidates(
        self, scope: SalesScope, case: OrderCase, line_no: int
    ) -> OrderCase:
        """Sales rejects the candidates a model's reading proposed for a line
        (ticket 44): the line is checked again as unmapped, against no item
        and without the reading, under the rules stamped on the case, as for
        a confirmed code. Which lines may reject is the case's to decide
        (`OrderCase.reject_candidates`)."""
        line = case.line(line_no)
        details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no}
        unmapped = MappedLine(
            LineMapping(status=MappingStatus.UNMAPPED), None, line.basis.convert_prv_code
        )
        recheck = await self._line_again(scope, case, line, unmapped, details)
        return case.reject_candidates(line_no, recheck)

    async def _line_again(
        self,
        scope: SalesScope,
        case: OrderCase,
        line: OrderLine,
        mapped: MappedLine,
        details: dict[str, object],
    ) -> LineCheck:
        """One line's checks run again on its entered values against
        ``mapped``, under the rules stamped on the case (refused once the
        tenant's rules have moved on: two versions on one case)."""
        rules = await self._case_rules(scope, case, details)
        header = case.effective_header
        # No LME price list: the band is unchecked, a finding (`check_line`).
        lme = await _unless_unconnected(
            self.catalog.lme_for_month(scope, rules.lme_month(header.po_date)), []
        )
        recheck, _ = await self._check_line(
            scope,
            case.customer_code,
            header,
            await self._received_on(scope, case.received_at),
            line.effective,
            mapped,
            None if lme is None else lme.data,
            rules,
            [],
            linked=case.quotes_for(line.line_no),
        )
        return recheck

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

        The PO's history against Bravo is checked again too: the comparison
        reads the currency and each line's code, quantity, price and date, so
        a correction can make the PO a duplicate of an order keyed by hand,
        or stop it being one. Only for a PO no other DW1 case holds, and no
        earlier revision of this one: its history Bravo alone decided, as it
        does again. Not when Bravo now holds a later revision, which intake
        routes and no finding names.
        """
        details: dict[str, object] = {"case_id": str(case.case_id), "finding": finding_key}
        correction = decided(
            lambda: ValueCorrection(field=field, value=value, by=actor.user_id, at=at)
        )
        corrected = decided(lambda: case.corrected(finding_key, correction, actor))
        recheck = await self._recheck(scope, case, corrected, details)
        return decided(lambda: case.correct_value(finding_key, correction, actor, recheck))

    async def take_change(
        self,
        scope: SalesScope,
        case: OrderCase,
        line_no: int,
        change: AppliedChange,
        actor: Actor,
    ) -> OrderCase:
        """A change the customer asked by mail, confirmed by a person, applied
        to the case with its checks run again on the changed values, as for a
        value Sales typed (`correct_value`; ticket 27). Which statuses and lines
        take a change is the case's to decide (`OrderCase.changed`)."""
        details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no}
        corrected = decided(lambda: case.changed(line_no, change, actor))
        recheck = await self._recheck(scope, case, corrected, details)
        return decided(lambda: case.take_change(line_no, change, actor, recheck))

    async def take_pc_answer(
        self,
        scope: SalesScope,
        case: OrderCase,
        line_no: int,
        deliveries: Sequence[tuple[Decimal, date]],
        actor: Actor,
        at: datetime,
    ) -> OrderCase:
        """PC's answer for one line, recorded by a person, applied with the
        line's checks run again through the path a change the customer asked
        takes (`take_change`; ticket 07). What a line may take, and what a
        re-confirmation keeps, is the case's (`OrderCase.pc_answered`)."""
        details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no}
        corrected = decided(lambda: case.pc_answered(line_no, deliveries, actor, at))
        recheck = await self._recheck(scope, case, corrected, details)
        return decided(lambda: case.take_pc_answer(line_no, deliveries, actor, at, recheck))

    async def take_update(self, scope: SalesScope, case: OrderCase, at: datetime) -> OrderCase:
        """A customer's change on an order in Bravo, accepted: applied with
        the changed lines' checks run again, as a change before Bravo is
        (`take_change`; ticket 29). Which loop step accepts, and what each
        line takes, is the case's (`OrderCase.update_accepted`)."""
        details: dict[str, object] = {"case_id": str(case.case_id)}
        corrected = decided(case.update_accepted)
        recheck = await self._recheck(scope, case, corrected, details)
        return decided(lambda: case.take_update(at, recheck))

    async def take_internal_change(
        self,
        scope: SalesScope,
        case: OrderCase,
        change_id: uuid.UUID,
        reason: InternalReason,
        lines: Mapping[int, Sequence[tuple[Decimal, date]]],
        actor: Actor,
        at: datetime,
    ) -> OrderCase:
        """Proterial's own change of a confirmed order (ticket 10), applied
        with the changed lines' checks run again, as an accepted change is
        (`take_update`). What it may change is the case's
        (`OrderCase.internal_change`)."""
        details: dict[str, object] = {"case_id": str(case.case_id)}
        loop = decided(lambda: case.internal_change(change_id, reason, lines, actor, at))
        recheck = await self._recheck(scope, case, case.internal_changed(loop), details)
        return decided(
            lambda: case.take_internal_change(change_id, reason, lines, actor, at, recheck)
        )

    async def take_quote_check(
        self, scope: SalesScope, case: OrderCase, lines: Collection[int]
    ) -> OrderCase:
        """``lines``' checks run again once a quote opened from the order for
        them is approved (ticket 09), its terms the quotation they are checked
        against (`_check_line`), through the path a change takes. Which lines
        and statuses take it is the case's (`OrderCase.quote_check`)."""
        details: dict[str, object] = {"case_id": str(case.case_id)}
        corrected = decided(lambda: case.quote_check(lines))
        recheck = await self._recheck(scope, case, corrected, details)
        return decided(lambda: case.take_quote_check(corrected, recheck))

    async def _recheck(
        self, scope: SalesScope, case: OrderCase, corrected: Corrected, details: dict[str, object]
    ) -> Recheck:
        """The checks run again on ``corrected``'s values under the rules
        stamped on the case (`correct_value`'s docstring says which)."""
        rules = await self._case_rules(scope, case, details)
        header = corrected.document.header
        # No LME price list: the band is unchecked, a finding (`check_line`).
        lme = await _unless_unconnected(
            self.catalog.lme_for_month(scope, rules.lme_month(header.po_date)), []
        )
        received_on = await self._received_on(scope, case.received_at)
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
                received_on,
                line.effective,
                mapped,
                None if lme is None else lme.data,
                rules,
                [],
                linked=case.quotes_for(line.line_no),
            )
            checks.append(check)
        po_findings = list(check_document(corrected.document, rules))
        po_codes = DOCUMENT_CHECK_CODES
        if corrected.line_no is None:
            po_findings += await self._customer_findings(scope, case, header, rules)
            po_codes |= CUSTOMER_CHECK_CODES
        bravo: BravoHistory | None = None
        others = [
            other
            for other in await self.cases.cases_for_po(scope, case.customer_code, header.po_no)
            if other.case_id != case.case_id
        ]
        # An order DW1 already entered in Bravo is not checked against its own
        # entry there: it would read as its own duplicate (ticket 29).
        in_bravo = case.bravo_so_no is not None
        if not others and not case.superseded and case.duplicate_of_case is None and not in_bravo:
            codes = {line.line_no: line.mapping.checked_against for line in corrected.lines}
            codes |= {c.line.line_no: c.line.mapping.checked_against for c in checks}
            # Bravo not connected: its history stays unchecked, as the case
            # was read (`_case`), and no finding of it is raised again.
            orders = await _unless_unconnected(
                self.catalog.orders_for_po(scope, case.customer_code, header.po_no), []
            )
            history = (
                None
                if orders is None
                else check_history(
                    case.customer_code, corrected.document, codes, (), orders.data, rules=rules
                )
            )
            if history is not None and not history.stale:
                po_findings += [] if history.finding is None else [history.finding]
                po_codes |= HISTORY_CHECK_CODES
                bravo = BravoHistory(history.duplicate_of_so, history.base_so_no)
        return Recheck(tuple(checks), tuple(po_findings), po_codes, bravo)

    async def _read(
        self,
        scope: SalesScope,
        lines: Sequence[PoLine],
        items: Sequence[Item],
        rules: OrderRules,
        run: RunContext | None,
        customer_code: str,
        *,
        message_id: str,
        attachment_id: str | None,
    ) -> dict[int, MappedLine]:
        """The lines a model read (dw_sales ADR 0005), by line number: only
        where the tenant's rules turn it on and its live eval met the bar, a
        model is wired, and a DW1 run is doing the processing. Otherwise none,
        and every line keeps the mapping code gave it. The reading is shown
        the tenant's decided lines most like these, the case's customer's
        first, as many as its rules say (ticket 43). Not on and passing but
        listed in shadow (ticket 67), the lines are read the same way and
        kept for Sales' confirmation to label, and none is returned."""
        if not lines or self.descriptions is None or run is None:
            return {}
        step = ModelStep.DESCRIPTION_ATTRIBUTES
        showing = Showing(Lookup(customer_code, rules.learning.examples_per_line))
        if await self._model_step(scope, rules, step):
            return await self.descriptions.read(lines, items, run=run, showing=showing)
        if self.shadow is not None and await self.shadow.shadows(scope, rules, step):
            try:
                read = await self.descriptions.read(lines, items, run=run, showing=showing)
            except (BudgetExceededError, QuotaExceededError):
                # A shadow reading never stops the mail's own processing.
                return {}
            await self.shadow.keep(
                scope,
                description_shadows(
                    read,
                    message_id=message_id,
                    attachment_id=attachment_id,
                    rules=rules.version,
                    at=self.shadow.clock.now(),
                    new_id=uuid.uuid4,
                ),
            )
        return {}

    async def _gated(
        self, scope: SalesScope, read: dict[int, MappedLine], rules: OrderRules, *, item: str
    ) -> dict[int, MappedLine]:
        """Each read line with exactly one candidate, stamped with what code's
        gate does with it (ticket 44); every other line as it was read. The
        item key names the message, the document and the line, so the audit
        sample is the same for the same line whenever it is read."""
        if self.autonomy is None:
            return read
        step = ModelStep.DESCRIPTION_ATTRIBUTES
        gated: dict[int, MappedLine] = {}
        for line_no, mapped in read.items():
            reading = mapped.reading
            if (
                reading is None
                or reading.outcome != "read"
                or mapped.mapping.status is not MappingStatus.CANDIDATE
            ):
                gated[line_no] = mapped
                continue
            route = await self.autonomy.route(
                scope,
                rules,
                step,
                prompt=reading.prompt,
                model_profile=reading.model_profile,
                confidence=reading.confidence,
                item_key=f"{item}:{line_no}:{step.value}",
            )
            gated[line_no] = mapped._replace(reading=reading.model_copy(update={"gate": route}))
        return gated

    async def _value_gates(
        self, scope: SalesScope, case: OrderCase, rules: OrderRules, *, item: str
    ) -> OrderCase:
        """Each value a model read of a PO written in the mail, stamped with
        what code's gate does with it (ticket 44): `person` where Đạt's rule
        keeps it a person's (`po_body_autonomy.may_apply_itself`), else the
        gate's route for its confidence. Nothing applies a PO's value by itself
        yet (the effect, its undo and its screen are the next slice), so a
        value that clears the threshold is logged as `shadow`: measured, and
        decided by a person as before. Stamped so every value Sales settles is
        a labelled case the step's threshold is measured on."""
        if self.autonomy is None or not case.document.from_message:
            return case
        step = ModelStep.PO_BODY_EXTRACTION
        profile = case.document.model_profile
        gates: dict[tuple[int | None, str], GateRoute] = {}
        for line_no, field, confidence in model_read_values(case):
            if profile is None or not may_apply_itself(case, line_no, field):
                gates[(line_no, field)] = "person"
                continue
            route = await self.autonomy.route(
                scope,
                rules,
                step,
                prompt=case.document.parser_version,
                model_profile=profile,
                confidence=confidence,
                item_key=f"{item}:{line_no or 0}:{field}:{step.value}",
            )
            gates[(line_no, field)] = "shadow" if route == "applied" else route
        return case.with_value_gates(gates)

    async def implied_term(
        self, scope: SalesScope, case: OrderCase
    ) -> tuple[ImpliedTerm | None, ZoneInfo]:
        """The customer's days of silence that count as agreement, as the
        rules stamped on the case give them (ticket 28), and the tenant's time
        zone they are counted in. None where the customer has none, or the
        stamped rules no longer load: never implied (fail closed)."""
        stamped = case.rules_version
        rules = None if stamped is None else await self.rules.rules_at(scope, stamped)
        term = None if rules is None else rules.implied_acceptance.get(case.customer_code)
        return term, await self.zones.time_zone(scope)

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
            entry = await _convert_entry(self.catalog, scope, customer_code, entered)
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
            line.mapping,
            item,
            line.basis.convert_prv_code,
            line.basis.description_reading,
            line.basis.stated_attributes,
        )

    async def _customer_findings(
        self, scope: SalesScope, case: OrderCase, header: PoHeader, rules: OrderRules
    ) -> tuple[Finding, ...]:
        """The customer's and the sender's checks again, on the entered PO date
        (the fiscal year an ESF is renewed for) and delivery term. The sender's
        results are the message's; a customer taken from the document is one
        with `customer_unknown`, which that check raised exactly then."""
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
            po_date=header.po_date,
            received_on=await self._received_on(scope, case.received_at),
            delivery_term=header.delivery_term,
            rules=rules,
        )

    async def _check_line(
        self,
        scope: SalesScope,
        customer_code: str,
        header: PoHeader,
        received_on: date,
        po_line: PoLine,
        mapped: MappedLine,
        lme: LmeMonth | None,
        rules: OrderRules,
        unchecked: list[str],
        *,
        linked: Collection[uuid.UUID] = (),
    ) -> tuple[LineCheck, list[datetime]]:
        """One line checked against its item and the customer's quotation for it
        on the PO date, with the ``as_of`` of what that read. Quotations with
        nothing to answer are named in ``unchecked`` and read as none, which
        raises `quotation_missing`: never a pass. With none valid, the one
        approved on a quote case opened from the order for the line
        (``linked``, ticket 09) applies to this PO."""
        quotation = None
        read: list[datetime] = []
        if mapped.item is not None:
            valid = await _unless_unconnected(
                self.catalog.quotations_valid_on(
                    scope, customer_code, mapped.item.prv_code, header.po_date
                ),
                unchecked,
            )
            read += [] if valid is None else [valid.as_of]
            quotation = current_quotation(
                () if valid is None else valid.data,
                customer_code=customer_code,
                prv_code=mapped.item.prv_code,
                day=header.po_date,
            )
            if quotation is None and linked and self.linked_quotes is not None:
                quotation = quoted_for_po(
                    await self.linked_quotes.quotes(scope, linked),
                    customer_code=customer_code,
                    prv_code=mapped.item.prv_code,
                    po_date=header.po_date,
                )
        check = check_line(
            po_line,
            mapped,
            currency=header.currency,
            po_date=header.po_date,
            received_on=received_on,
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

    def _routed(
        self,
        message: InboundMessage,
        kind: MessageKind,
        reason: RoutingReason,
        customer: Customer | None,
        detail: str | None = None,
        candidates: Sequence[ThreadedCase] = (),
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
            thread_cases=tuple(
                ThreadCase(case_kind=c.case_kind, case_id=c.case_id, linked_to=c.linked_to)
                for c in candidates
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


async def _convert_entry(
    catalog: SalesCatalogPort, scope: SalesScope, customer_code: str, line: PoLine
) -> Snapshot[ConvertEntry | None]:
    """The convert list's row for a line, by whichever of its two texts the
    customer's PO names the item with: its code, else its description, as
    Bravo's list holds a customer's converting description (B04, ticket 36).
    Always that one customer's row: the same words are another customer's
    other item."""
    by_code = await catalog.convert_entry(scope, customer_code, line.customer_item_code)
    description = line.description.strip()
    if by_code.data is not None or not description or description == line.customer_item_code:
        return by_code
    return await catalog.convert_entry(scope, customer_code, description)


async def _unless_unconnected[T](
    read: Awaitable[Snapshot[T]], unchecked: list[str]
) -> Snapshot[T] | None:
    """What ``read`` answers, or None where its source has nothing to answer
    (`CatalogNotConnectedError`), named once in ``unchecked``."""
    try:
        return await read
    except CatalogNotConnectedError as missing:
        if missing.statement not in unchecked:
            unchecked.append(missing.statement)
        return None


def _named_revision(
    message: InboundMessage, document: PoDocument, marks: Sequence[str]
) -> PoDocument:
    """The PO with the revision its file's name suggests with the tenant's
    ``marks`` (ticket 22; ticket 42 family 6), a hint shown beside what
    decides; as it was when the name suggests none."""
    name = next(
        (a.name for a in message.attachments if a.attachment_id == document.attachment_id),
        None,
    )
    hint = None if name is None else name_revision(name, document.header.po_no, marks)
    if hint is None or hint == document.name_revision:
        return document
    return document.model_copy(update={"name_revision": hint})


def _stamped(outcome: IntakeOutcome, reading: IntentReading | None) -> IntakeOutcome:
    """The outcome with the model reading's stamp on its disposition."""
    if reading is None or outcome.disposition is None:
        return outcome
    disposition = MessageDisposition.model_validate(
        {**outcome.disposition.model_dump(), "reading": reading}
    )
    return replace(outcome, disposition=disposition)


def _with_prefill(outcome: IntakeOutcome, prefill: LayoutPrefill | None) -> IntakeOutcome:
    """The routed outcome with the model's pre-fill stamped on it, for the
    onboarding screen to open with; as it was without one."""
    if prefill is None or outcome.disposition is None:
        return outcome
    stamped = MessageDisposition.model_validate(
        {**outcome.disposition.model_dump(), "layout_prefill": prefill}
    )
    return replace(outcome, disposition=stamped)


def _for_a_person(
    message: InboundMessage, *, carries_document: bool, sender: Customer | None
) -> Classification:
    """What no reader, thread or model classified (module docstring): a
    person reads it, told why, never a kind its words were taken to mean. A
    document from a sender no customer is was never read (a layout is a
    customer's): the customer is what is unknown."""
    if carries_document and sender is None:
        return Classification(MessageKind.OTHER, RoutingReason.CUSTOMER_UNKNOWN, UNKNOWN_SENDER)
    if carries_document:
        return Classification(
            MessageKind.OTHER, RoutingReason.ATTACHMENT_UNREADABLE, UNREAD_DOCUMENT
        )
    return Classification(
        MessageKind.OTHER, RoutingReason.OTHER, f"{NOT_CLASSIFIED}: {message.subject}"
    )
