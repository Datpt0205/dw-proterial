"""How each inbound message ends: exactly one disposition (spec decision 10).

`case_created` (an order or a quote case), `attached_to_case` (a PO revision,
or a Design reply), `routed_to_sales` with its reason, or `not_yet_processed`.
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
    DESIGN_REPLY_UNMATCHED = "design_reply_unmatched"
    SAMPLE_REQUEST = "sample_request"
    CUSTOMER_UNKNOWN = "customer_unknown"
    ATTACHMENT_UNREADABLE = "attachment_unreadable"
    OTHER = "other"


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
        return self

    @classmethod
    def pending(cls, message_id: str) -> MessageDisposition:
        """A message no flow has processed yet."""
        return cls(message_id=message_id, kind=DispositionKind.NOT_YET_PROCESSED)
