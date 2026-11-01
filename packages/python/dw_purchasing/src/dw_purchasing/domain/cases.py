"""The purchase case: one request from the moment DW2 received it, and what
was stamped on it on the way (CONTEXT.md, "Purchase case").

A stamp is written once and read ever after: the rules a case was received
under, the check and the approver it was sent to, the decision. A later
reader takes the stamp, never whatever is in force today.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_purchasing.domain.checks import CrossCheck
from dw_purchasing.domain.orders import PoRound
from dw_purchasing.domain.requests import Currency, Price, PurchaseRequest
from dw_purchasing.domain.sourcing import Offer, RfqRound, Selection

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class PrSource(StrEnum):
    """Where the request came from (DW02: email, Bravo, form, scanned paper;
    this slice reads the first and the third)."""

    FORM = "form"
    MAIL = "mail"
    # Written in DW2 by the requester themselves ("Tôi cần mua…").
    REQUESTER = "requester"


class CaseStatus(StrEnum):
    """Where a purchase case stands (CONTEXT.md, "Purchase case")."""

    RECEIVED = "received"
    # Checked and sent to the approver its amount and findings name.
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    # Approved, and an RFQ drafted per supplier; offers are recorded here.
    RFQ_DRAFTED = "rfq_drafted"
    # A person chose a supplier for every line.
    SUPPLIER_SELECTED = "supplier_selected"
    # One draft order per chosen supplier, and the Bravo file drawn from them.
    PO_DRAFTED = "po_drafted"


class ApprovalAsked(BaseModel):
    """Who the case was sent to, stamped when it was sent: the approval, the
    scope its decider must hold and who that is, the version of the case the
    approver is shown, and who sent it. A later reader takes this stamp, never
    the rules in force today."""

    model_config = _FROZEN

    approval_id: uuid.UUID
    required_scope: str = Field(pattern=r"^purchasing\.approve\.[a-z0-9_]+$")
    tier_label: str = Field(min_length=1, max_length=80)
    # The most the tier decides (None: the last tier, no limit), in
    # ``limit_currency``: a supplier chosen later is held to it.
    limit: Price | None
    limit_currency: Currency
    case_version: int = Field(ge=1)
    submitted_by: uuid.UUID
    submitted_at: AwareDatetime


class Decided(BaseModel):
    """The approver's decision, as the approval recorded it."""

    model_config = _FROZEN

    approved: bool
    decided_by: uuid.UUID
    decided_at: AwareDatetime
    comment: str = Field(default="", max_length=2000)


class PurchaseCase(BaseModel):
    """One request, from the moment DW2 received it.

    ``rules_ref`` is the tenant rules the case was received under
    (``purchasing_rules@<version>``), stamped once: a later reader takes the
    stamp, never whatever is in force today.
    """

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    status: CaseStatus
    source: PrSource
    # The mailbox's message id for a request read from mail.
    source_ref: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")
    request: PurchaseRequest
    received_at: AwareDatetime
    # Who submitted the form, or pressed "DW2 đọc" on the mail.
    received_by: uuid.UUID
    # The person who asked, when DW2 knows them by their sign-in: a requester
    # who wrote the request in DW2 themselves. Only they, of the requesters,
    # see the case, and they never approve it.
    requested_by: uuid.UUID | None = None
    rules_ref: str = Field(pattern=r"^purchasing_rules@\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$")
    # What code found when the case was sent for approval (DW02 function 2).
    check: CrossCheck | None = None
    approval: ApprovalAsked | None = None
    decision: Decided | None = None
    # DW02 function 3: whom DW2 asked, what they offered, whom a person chose.
    rfq: RfqRound | None = None
    offers: tuple[Offer, ...] = ()
    selection: Selection | None = None
    # DW02 function 4: the draft orders and the layout of their Bravo file.
    po: PoRound | None = None

    @model_validator(mode="after")
    def _a_mail_names_its_message(self) -> Self:
        if (self.source is PrSource.MAIL) != (self.source_ref is not None):
            raise ValueError("a request read from mail names its message, and only it does")
        return self

    @model_validator(mode="after")
    def _each_state_holds_what_it_needs(self) -> Self:
        sent = self.status is not CaseStatus.RECEIVED
        sourcing = self.status in (
            CaseStatus.RFQ_DRAFTED,
            CaseStatus.SUPPLIER_SELECTED,
            CaseStatus.PO_DRAFTED,
        )
        chosen = self.status in (CaseStatus.SUPPLIER_SELECTED, CaseStatus.PO_DRAFTED)
        decided = self.status in (CaseStatus.APPROVED, CaseStatus.REJECTED) or sourcing
        if sourcing != (self.rfq is not None):
            raise ValueError("a case being sourced holds its RFQ round, and only it does")
        if chosen != (self.selection is not None):
            raise ValueError("a case with suppliers chosen holds the choice, and only it does")
        if (self.status is CaseStatus.PO_DRAFTED) != (self.po is not None):
            raise ValueError("a case with orders drafted holds them, and only it does")
        if sourcing and (self.decision is None or not self.decision.approved):
            raise ValueError("only an approved request is sourced")
        if sent != (self.check is not None and self.approval is not None):
            raise ValueError("a case sent for approval holds its check and its approval")
        if decided != (self.decision is not None):
            raise ValueError("a decided case holds its decision, and only it does")
        if (
            decided
            and not sourcing
            and self.decision is not None
            and self.decision.approved != (self.status is CaseStatus.APPROVED)
        ):
            raise ValueError("the status is the decision's")
        return self

    @property
    def makers(self) -> frozenset[uuid.UUID]:
        """Who made what an approver decides: who asked for it, who received
        it and who sent it. A strict approval refuses each of them as its
        decider."""
        sent = {self.approval.submitted_by} if self.approval is not None else set()
        asked = {self.requested_by} if self.requested_by is not None else set()
        return frozenset({self.received_by, *sent, *asked})
