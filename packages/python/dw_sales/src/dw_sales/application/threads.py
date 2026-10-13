"""A reply's case, from its thread headers: deterministic, no model (ticket 32).

A customer answers a spec discussion, a decline or a correction request by
replying in the thread. Their mail client writes `In-Reply-To` and
`References`, naming the Message-IDs the reply answers. `ThreadLinks` links the
reply to a case when those headers name a message already on a case, and only
then:

- the named message is in this workspace's mailbox and has a disposition on
  a case (`case_created` or `attached_to_case`) in this workspace's log, read
  under its row security: another tenant's or workspace's case is not there
  to be found;
- that case belongs to the customer the reply's sender domain is: headers
  are the sender's to write, so a reference to another customer's message is
  a claim nobody honours;
- exactly one case is named. Two cases, or none, link nothing, and the reply
  is classified as any other message is.

What Sales last asked of the customer on that case (`open_question`) is built
here from the case, by code, for the model reading of the reply.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from dw_sales.application.case_store import SalesUnitOfWork, SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.orders import DispositionKind, OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

# What Sales last did on the case a reply answers, for `question`.
AskedAbout = Literal["correction", "spec", "decline", "order", "quote"]


@dataclass(frozen=True, slots=True)
class ThreadedCase:
    """The case a reply's thread names, as code found it."""

    case_kind: CaseKind
    case_id: uuid.UUID
    customer_code: str
    status: str
    # The message on the case the reply's headers name.
    linked_to: str
    # What Sales last asked the customer on the case, in code's words.
    question: str


class MessageListPort(Protocol):
    """The workspace's mailbox, as far as a thread goes: what it holds."""

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]: ...


@dataclass(frozen=True)
class ThreadLinks:
    """Implements `ThreadLinkPort` with the mailbox and the workspace's log."""

    uow: SalesUnitOfWorkFactory
    inbox: MessageListPort

    async def linked_case(
        self, scope: SalesScope, message: InboundMessage, sender: Customer | None
    ) -> ThreadedCase | None:
        """The one case of ``sender`` the reply's thread names, or None."""
        if sender is None or not message.references:
            return None
        named = set(message.references)
        linked = [
            other.message_id
            for other in await self.inbox.list_messages(scope)
            if other.internet_message_id in named and other.message_id != message.message_id
        ]
        if not linked:
            return None
        found: dict[uuid.UUID, ThreadedCase] = {}
        async with self.uow(scope) as work:
            for message_id in linked:
                threaded = await _case_of(work, message_id)
                if threaded is not None and threaded.customer_code == sender.code:
                    found.setdefault(threaded.case_id, threaded)
        if len(found) != 1:
            return None
        (threaded,) = found.values()
        return threaded


async def _case_of(work: SalesUnitOfWork, message_id: str) -> ThreadedCase | None:
    disposition = await work.messages.get(message_id)
    if disposition is None or disposition.case_id is None or disposition.case_kind is None:
        return None
    if disposition.case_kind is CaseKind.ORDER:
        order = await work.orders.get(disposition.case_id)
        if order is None:
            return None
        return ThreadedCase(
            CaseKind.ORDER,
            order.case.case_id,
            order.case.customer_code,
            order.case.status.value,
            message_id,
            order_question(order.case),
        )
    quote = await work.quotes.get(disposition.case_id)
    if quote is None:
        return None
    return ThreadedCase(
        CaseKind.QUOTE,
        quote.case.case_id,
        quote.case.customer_code,
        quote.case.status.value,
        message_id,
        quote_question(quote.case),
    )


def order_question(case: OrderCase) -> str:
    """What Sales last asked the customer about their PO, in code's words."""
    if case.status is not OrderStatus.CORRECTION_REQUESTED:
        return question("order", case.header.po_no)
    asked = [
        finding.code.value + (f" (line {finding.line_no})" if finding.line_no else "")
        for finding in case.findings
        if finding.disposition.kind is DispositionKind.ASK_CUSTOMER
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
