"""How each inbound message ends: exactly one disposition (spec decision 10).

`case_created` (an order or a quote case), `attached_to_case` (a PO revision,
or a Design reply), `routed_to_sales` with its reason, or `not_yet_processed`.
A mail carrying several POs is one message on several order cases (ticket
19): its disposition names the first and lists the others (`more_cases`).
"No message missed" is then a count anyone can take: messages still
`not_yet_processed`, and routed messages without an owner. Names and labels
are in CONTEXT.md.

A disposition carries ids, codes and reasons, never a value read from the
message: it travels into audit events and the overview (spec decision 8).
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import Compliance, CustomerCode
from dw_sales.domain.handoffs import Handoff
from dw_sales.domain.layouts import LayoutPrefill
from dw_sales.domain.message_intent import IntentReading
from dw_sales.domain.reply_intent import CaseReply
from dw_sales.domain.triage import TriageCard

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class DispositionKind(StrEnum):
    CASE_CREATED = "case_created"
    ATTACHED_TO_CASE = "attached_to_case"
    ROUTED_TO_SALES = "routed_to_sales"
    NOT_YET_PROCESSED = "not_yet_processed"


class CaseKind(StrEnum):
    ORDER = "order"
    QUOTE = "quote"


class RoutingReason(StrEnum):
    DELIVERY_CHANGE = "delivery_change"
    COMPLAINT = "complaint"
    # A reply about a case or an order already in hand that is none of the
    # reasons above (ticket 31: only a model reading gives it).
    REPLY_TO_CASE = "reply_to_case"
    DESIGN_REPLY_UNMATCHED = "design_reply_unmatched"
    SAMPLE_REQUEST = "sample_request"
    CUSTOMER_UNKNOWN = "customer_unknown"
    ATTACHMENT_UNREADABLE = "attachment_unreadable"
    # A file locked with a password that no password its own mail carries
    # opens (ticket 17): routed as an unreadable file is, saying why.
    ATTACHMENT_LOCKED = "attachment_locked"
    # The scanner found malware in an attachment (ticket 25): nothing in the
    # message is read, and its bytes are never served.
    MALWARE_DETECTED = "malware_detected"
    # A customer's portal saying a PO is waiting there (ticket 18): the mail
    # carries none, and DW never logs into a portal, so the PIC downloads it
    # and uploads it ("Tải PO lên"). Only a model reading gives it.
    PORTAL_NOTICE = "portal_notice"
    OTHER = "other"


# The most cases a routed reply offers: a thread holds a few POs, not fifty.
MAX_THREAD_CASES = 50
# The most POs one message opens cases for (ticket 19): customer 1 sends nine.
MAX_MESSAGE_CASES = 50


class ThreadCase(BaseModel):
    """A case of the sender's own customer that a reply's thread holds,
    offered to Sales when the reply names none of them (ticket 24, dw_sales
    ADR 0009): ids only. ``linked_to`` is the message on the case the thread
    holds, which the reply is linked to once Sales picks the case."""

    model_config = _FROZEN

    case_kind: CaseKind
    case_id: uuid.UUID
    linked_to: str = Field(pattern=r"^[!-~]{1,512}$")


# The owner of a routed message nobody's Sales PIC is known for: every holder
# of the role picks it up, which is an owner, not none.
SALES_PIC_POOL = "role:sales_pic"


class MessageDisposition(BaseModel):
    """What became of one message, and who handles it now."""

    model_config = _FROZEN

    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    kind: DispositionKind
    case_kind: CaseKind | None = None
    case_id: uuid.UUID | None = None
    reason: RoutingReason | None = None
    # Why, in words that name fields, attachments and codes, never values.
    detail: str | None = Field(default=None, max_length=500)
    # Who the routed message is for: the customer's Sales PIC, else the pool.
    owner: str | None = Field(default=None, max_length=254)
    customer_code: CustomerCode | None = None
    # A sample request carries the customer's export-control status, so the
    # PIC who handles it sees what an order would have been warned about.
    compliance: Compliance | None = None
    # What a model reading of the message's intent did, where the tenant's
    # rules asked for one (ticket 31): ids, codes and numbers, never words.
    reading: IntentReading | None = None
    # A reply attached to its case by the mail's thread headers (ticket 32),
    # with what a model read of it where the tenant's rules asked.
    reply: CaseReply | None = None
    # The hand-off to PC or QA a model pre-filled from a delivery change, a
    # complaint or a sample request (ticket 33), for Sales to review and send.
    handoff: Handoff | None = None
    # The layout a model pre-filled for a PO no layout of the customer reads
    # (ticket 30), for the onboarding screen to open with.
    layout_prefill: LayoutPrefill | None = None
    # The cases a reply's thread holds when it names none of them (ticket
    # 24): Sales picks one ("Chọn hồ sơ"), and only one of these.
    thread_cases: tuple[ThreadCase, ...] = Field(default=(), max_length=MAX_THREAD_CASES)
    # The further order cases the message opened or joined, one per PO
    # number after the first (ticket 19), in the order the mail names them.
    # Empty for a message with one PO, as every message before ticket 19.
    more_cases: tuple[uuid.UUID, ...] = Field(default=(), max_length=MAX_MESSAGE_CASES - 1)
    # The card a message routed ``other`` carries where the tenant's rules
    # ask for one (ticket 33): what it seems to be, the case it seems to
    # concern and one step, advice until a person decides; kept, with that
    # decision, on the disposition the decision gave it.
    triage: TriageCard | None = None

    @model_validator(mode="after")
    def _kind_says_what_is_there(self) -> Self:
        kind = self.kind
        on_case = kind in (DispositionKind.CASE_CREATED, DispositionKind.ATTACHED_TO_CASE)
        if on_case != (self.case_id is not None and self.case_kind is not None):
            raise ValueError(f"a {kind} disposition names a case only when it is on one")
        routed = kind is DispositionKind.ROUTED_TO_SALES
        if routed != (self.reason is not None and self.owner is not None):
            raise ValueError("a routed message has a reason and an owner, and only it does")
        if self.compliance is not None and self.reason is not RoutingReason.SAMPLE_REQUEST:
            raise ValueError("only a sample request carries the export-control status")
        if self.reply is not None and kind is not DispositionKind.ATTACHED_TO_CASE:
            raise ValueError("only a message attached to a case is a reply on it")
        if self.handoff is not None and (
            self.reason is None or self.reason.value != self.handoff.kind
        ):
            raise ValueError("a hand-off is of the kind the message was routed as")
        if (
            self.layout_prefill is not None
            and self.reason is not RoutingReason.ATTACHMENT_UNREADABLE
        ):
            raise ValueError("a layout is pre-filled only for a PO nothing could read")
        if self.thread_cases and (
            self.reason is not RoutingReason.REPLY_TO_CASE
            or len(self.thread_cases) < 2
            or len({c.case_id for c in self.thread_cases}) != len(self.thread_cases)
        ):
            raise ValueError("only a reply routed for its thread's several cases offers them")
        if self.more_cases and (
            not on_case
            or self.case_kind is not CaseKind.ORDER
            or self.reply is not None
            or len({self.case_id, *self.more_cases}) != len(self.more_cases) + 1
        ):
            raise ValueError("only a message whose POs opened several order cases lists them")
        if self.triage is not None:
            decided = self.triage.decided
            if decided is None and not (routed and self.reason is RoutingReason.OTHER):
                raise ValueError("an undecided card is on a message routed other")
            if decided is not None and decided.case_id is not None:
                if kind is not DispositionKind.ATTACHED_TO_CASE or self.case_id != decided.case_id:
                    raise ValueError("a card that attached a message is on that case")
            elif decided is not None and not routed:
                raise ValueError("a card's decision keeps the message routed to Sales")
        return self

    @property
    def case_ids(self) -> tuple[uuid.UUID, ...]:
        """Every case the message is on: none, one, or one per PO (ticket 19)."""
        return () if self.case_id is None else (self.case_id, *self.more_cases)

    def is_on(self, case_kind: CaseKind, case_id: uuid.UUID) -> bool:
        """Whether the message is on that case, as its first or a further one."""
        return self.case_kind is case_kind and case_id in self.case_ids

    def thread_case(self, case_id: uuid.UUID) -> ThreadCase | None:
        """The offered case with this id, or None when it is not one of them."""
        return next((c for c in self.thread_cases if c.case_id == case_id), None)

    @classmethod
    def pending(cls, message_id: str) -> MessageDisposition:
        """A message no flow has processed yet."""
        return cls(message_id=message_id, kind=DispositionKind.NOT_YET_PROCESSED)
