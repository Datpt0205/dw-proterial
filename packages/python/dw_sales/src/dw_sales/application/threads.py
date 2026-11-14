"""The mail thread a message is on, and the cases it holds: deterministic, no
model (tickets 32 and 24, dw_sales ADR 0009 decisions 1-2).

**A thread key per stored message.** A customer answers in the same Outlook
conversation, and their mail client writes `In-Reply-To` and `References`,
naming the Message-IDs the reply answers. When a message is stored, code
gives it a key (`thread_key`): the key of the earliest already-stored
message those headers name in the workspace (earliest received); else its
own Message-ID; else its own mailbox id. Never the subject, never a model. A
key never changes once stored (the mailbox takes no UPDATE from the
application): a later message naming messages of two threads joins the
earliest, and no stored key is rewritten.

**Out of order.** A reply may be stored before the message it answers (two
PICs' mailboxes, exported at different times). The answered message then
keeps its own key, and a thread is read as a union (`thread_keys`): the
message's own key and the key of every stored message its headers name. So
a reply still reaches a case on a message stored after it, and a case still
shows the talk before it from an ancestor stored late. Two replies that only
share an ancestor stored after both stay apart until a message names both.

**The cases a reply's thread holds** (`ThreadLinks.cases`): every case of
the sender's own customer that any message of the thread is on, read from
the workspace's log under its row security: another tenant's or workspace's
case is not there to be found. Headers are the sender's to write, so a
thread reaching another customer's case links nothing to it. The thread is
the workspace's; the customer is applied where it is read, because only
then is it known who the sender is (Bravo's contacts, the sender ledger).
One case: the reply is attached to it. Several: the numbers it names choose
(`named_cases`), else Sales picks among them (`order_intake`).

What Sales last asked of the customer on that case (`question`) is built
here from the case, by code, for the model reading of the reply.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from dw_platform.domain.messages import InboundMessage
from dw_sales.application.case_store import (
    LoggedMessage,
    MessageOnCase,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.dispositions import CaseKind, DispositionKind
from dw_sales.domain.message_intent import ResolvedReference
from dw_sales.domain.orders import DispositionKind as FindingDisposition
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

# What Sales last did on the case a reply answers, for `question`.
AskedAbout = Literal["correction", "spec", "decline", "order", "quote"]


# ------------------------------------------------------------- the key --


@dataclass(frozen=True, slots=True)
class KeyedMessage:
    """A stored message as a new one's key reads it."""

    message_id: str
    received_at: datetime
    thread_key: str


def thread_key(message: InboundMessage, named: Iterable[KeyedMessage]) -> str:
    """The key ``message`` is stored with. ``named``: the messages already
    stored in its workspace whose Message-ID its `In-Reply-To`/`References`
    name. The earliest received of them gives its key; with none, the
    message's own Message-ID, else its own mailbox id."""
    earliest = min(named, key=lambda m: (m.received_at, m.message_id), default=None)
    if earliest is not None:
        return earliest.thread_key
    return message.internet_message_id or message.message_id


def thread_keys(own: str | None, named: Iterable[str]) -> frozenset[str]:
    """The keys a message's thread is read by: its own (None while it is not
    stored) and those of the stored messages its headers name, so a message
    stored before what it answers still reaches it (module docstring)."""
    return frozenset({*named, *(() if own is None else (own,))})


class ThreadIndex:
    """The thread keys of messages held in memory, added in the order they
    are stored: what the mock mailbox and a test's mailbox answer with, by
    the same two functions the stored mailbox applies."""

    def __init__(self, messages: Iterable[InboundMessage] = ()) -> None:
        self._held: list[InboundMessage] = []
        self._keys: dict[str, str] = {}
        for message in messages:
            self.add(message)

    def add(self, message: InboundMessage) -> str:
        """Keys ``message`` as stored now, once, and returns its key."""
        if message.message_id in self._keys:
            return self._keys[message.message_id]
        named = [
            KeyedMessage(m.message_id, m.received_at, self._keys[m.message_id])
            for m in self._named(message)
        ]
        key = self._keys[message.message_id] = thread_key(message, named)
        self._held.append(message)
        return key

    def key(self, message_id: str) -> str | None:
        return self._keys.get(message_id)

    def thread_of(self, message: InboundMessage) -> list[InboundMessage]:
        """Every held message on ``message``'s thread, oldest first."""
        keys = thread_keys(
            self._keys.get(message.message_id),
            (self._keys[m.message_id] for m in self._named(message)),
        )
        return sorted(
            (m for m in self._held if self._keys[m.message_id] in keys),
            key=lambda m: (m.received_at, m.message_id),
        )

    def _named(self, message: InboundMessage) -> list[InboundMessage]:
        named = set(message.references)
        return [
            m
            for m in self._held
            if m.internet_message_id in named and m.message_id != message.message_id
        ]


# ----------------------------------------------------------- the cases --


@dataclass(frozen=True, slots=True)
class ThreadedCase:
    """A case a reply's thread holds, as code found it."""

    case_kind: CaseKind
    case_id: uuid.UUID
    customer_code: str
    status: str
    # The case's message the reply is linked to: the one its headers name
    # nearest, else the case's latest on the thread.
    linked_to: str
    # What Sales last asked the customer on the case, in code's words.
    question: str
    # The numbers a quote case is named by (its RFQ and YCBG); an order case
    # is named by its id, which resolving a PO number gives.
    numbers: tuple[str, ...] = ()


class ThreadMembersPort(Protocol):
    """The workspace's mailbox, as far as a thread goes: one message, and the
    messages of a message's thread (`thread_keys`), oldest first, the message
    itself among them once stored. Never the whole mailbox."""

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None: ...

    async def thread_messages(
        self, scope: SalesScope, message: InboundMessage
    ) -> Sequence[InboundMessage]: ...


@dataclass(frozen=True)
class ThreadLinks:
    """Implements `ThreadLinkPort` with the mailbox's threads and the
    workspace's log."""

    uow: SalesUnitOfWorkFactory
    mailbox: ThreadMembersPort

    async def cases(
        self, scope: SalesScope, message: InboundMessage, sender: Customer | None
    ) -> tuple[ThreadedCase, ...]:
        """Every case of ``sender`` the reply's thread holds, in the order
        their messages came; none without a sender or thread headers."""
        if sender is None or not message.references:
            return ()
        thread = [
            m
            for m in await self.mailbox.thread_messages(scope, message)
            if m.message_id != message.message_id
        ]
        if not thread:
            return ()
        place = {m.message_id: index for index, m in enumerate(thread)}
        found: list[ThreadedCase] = []
        async with self.uow(scope) as work:
            by_case: dict[uuid.UUID, list[MessageOnCase]] = {}
            for entry in await work.messages.cases_of(list(place)):
                by_case.setdefault(entry.case_id, []).append(entry)
            for entries in sorted(
                by_case.values(), key=lambda on: min(place[e.message_id] for e in on)
            ):
                linked = _linked_to(message, thread, {e.message_id for e in entries})
                threaded = await _case_of(work, entries[0].case_kind, entries[0].case_id, linked)
                if threaded is not None and threaded.customer_code == sender.code:
                    found.append(threaded)
        return tuple(found)


def _linked_to(message: InboundMessage, thread: Sequence[InboundMessage], on_case: set[str]) -> str:
    """The case's message the reply is linked to: the one its headers name
    nearest (they list the nearest ancestor first), else the latest."""
    named = {m.internet_message_id: m.message_id for m in thread if m.message_id in on_case}
    for reference in message.references:
        if reference in named:
            return named[reference]
    return [m.message_id for m in thread if m.message_id in on_case][-1]


def named_cases(
    cases: Sequence[ThreadedCase], references: Iterable[ResolvedReference]
) -> tuple[ThreadedCase, ...]:
    """The cases among ``cases`` the numbers a message names point at, as
    `IntentReader.resolve` resolved them: exactly, uniquely, of the sender's
    customer only. An order by the one live case its PO number resolved to;
    a quote by its request's numbers."""
    resolved = list(references)
    orders = {r.order_case_id for r in resolved if r.order_case_id is not None}
    requests = {r.number for r in resolved if r.record == "quote_request"}
    return tuple(
        case
        for case in cases
        if (case.case_kind is CaseKind.ORDER and case.case_id in orders)
        or (case.case_kind is CaseKind.QUOTE and not requests.isdisjoint(case.numbers))
    )


async def talk_before(
    mailbox: ThreadMembersPort,
    scope: SalesScope,
    logged: Mapping[str, LoggedMessage],
    *,
    case_kind: CaseKind,
    case_id: uuid.UUID,
    customer_code: str,
) -> list[InboundMessage]:
    """The messages of the case's thread(s) received before it opened, oldest
    first: the talk before the PO (ADR 0009 decision 2). Only those DW1 read
    as the case's own customer's: a thread is the workspace's, and a chain
    naming this customer's mail from another sender shows nothing here.
    ``logged`` is the workspace's log by message id."""
    own: list[InboundMessage] = []
    opened: list[datetime] = []
    for entry in logged.values():
        disposition = entry.disposition
        if not disposition.is_on(case_kind, case_id):
            continue
        message = await mailbox.get_message(scope, disposition.message_id)
        if message is None:
            continue
        own.append(message)
        if disposition.kind is DispositionKind.CASE_CREATED:
            opened.append(message.received_at)
    if not own:
        return []
    since = min(opened or [m.received_at for m in own])
    mine = {m.message_id for m in own}
    before: dict[str, InboundMessage] = {}
    for message in own:
        for other in await mailbox.thread_messages(scope, message):
            seen = logged.get(other.message_id)
            if (
                other.message_id not in mine
                and other.received_at < since
                and seen is not None
                and seen.disposition.customer_code == customer_code
            ):
                before[other.message_id] = other
    return sorted(before.values(), key=lambda m: (m.received_at, m.message_id))


async def _case_of(
    work: SalesUnitOfWork, kind: CaseKind, case_id: uuid.UUID, linked_to: str
) -> ThreadedCase | None:
    if kind is CaseKind.ORDER:
        order = await work.orders.get(case_id)
        if order is None:
            return None
        return ThreadedCase(
            CaseKind.ORDER,
            order.case.case_id,
            order.case.customer_code,
            order.case.status.value,
            linked_to,
            order_question(order.case),
        )
    quote = await work.quotes.get(case_id)
    if quote is None:
        return None
    case = quote.case
    numbers = (case.request.rfq_no, case.ycbg.ycbg_no if case.ycbg is not None else None)
    return ThreadedCase(
        CaseKind.QUOTE,
        case.case_id,
        case.customer_code,
        case.status.value,
        linked_to,
        quote_question(case),
        tuple(n for n in numbers if n),
    )


def order_question(case: OrderCase) -> str:
    """What Sales last asked the customer about their PO, in code's words."""
    if case.status is not OrderStatus.CORRECTION_REQUESTED:
        return question("order", case.header.po_no)
    asked = [
        finding.code.value + (f" (line {finding.line_no})" if finding.line_no else "")
        for finding in case.findings
        if finding.disposition.kind is FindingDisposition.ASK_CUSTOMER
    ]
    return question("correction", case.header.po_no, asked)


def quote_question(case: QuoteCase) -> str:
    """What Sales last asked the customer about their request, in code's words."""
    number = case.request.rfq_no or "(no number)"
    if case.status is QuoteStatus.SPEC_DISCUSSION:
        return question("spec", number)
    if case.status is QuoteStatus.DECLINED:
        return question("decline", number)
    return question("quote", number)


def question(asked_about: AskedAbout, number: str, asked: list[str] | None = None) -> str:
    """The question in words, by what Sales last did: one wording per step,
    for the cases and the evals alike."""
    if asked_about == "correction":
        return (
            f"Sales asked the customer to correct their purchase order {number}, about: "
            f"{', '.join(asked or [])}. The customer may send a corrected PO, ask to keep"
            " the PO as it is, or ask a question."
        )
    if asked_about == "spec":
        return (
            "Sales sent the customer the specification the seller's Design team proposed"
            f" for their request for quotation {number}, and asked whether they accept it."
        )
    if asked_about == "decline":
        return f"Sales told the customer the seller will not quote their request {number}."
    if asked_about == "order":
        return f"Sales is handling the customer's purchase order {number}."
    return f"Sales is handling the customer's request for quotation {number}."
