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
from dw_purchasing.domain.tracking import OrderTracking

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class PrSource(StrEnum):
    """Where the request came from (DW02: email, Bravo, form, scanned paper;
    a mail's own words, its Excel form or its scanned paper are all `mail`,
    `ReadFrom` saying which)."""

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
    # The suppliers chosen come to more than the approver's tier decides: the
    # choice waits on an approval at the tier its total names.
    AWAITING_REAPPROVAL = "awaiting_reapproval"
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


class ReadFrom(BaseModel):
    """Where in a mail DW2 read the request, when a document was attached:
    the file (its id in the stored mailbox, and its name) when the lines
    were in it (None: the mail's own words), and whether any value was read
    only on a scanned page, which a person compares with the paper before
    DW2 sends it on (`review`)."""

    model_config = _FROZEN

    attachment_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,128}$")
    attachment: str | None = Field(default=None, min_length=1, max_length=255)
    scanned: bool = False

    @model_validator(mode="after")
    def _a_file_by_id_and_name(self) -> Self:
        if (self.attachment_id is None) != (self.attachment is None):
            raise ValueError("a file read from is named by its id and its name, or neither")
        return self


class Review(BaseModel):
    """A case DW2 opened on its own, or read from a scan, that a person is to
    look over first."""

    model_config = _FROZEN

    asked_at: AwareDatetime
    reviewed_by: uuid.UUID | None = None
    reviewed_at: AwareDatetime | None = None

    @property
    def pending(self) -> bool:
        return self.reviewed_by is None


class Decided(BaseModel):
    """The approver's decision, as the approval recorded it."""

    model_config = _FROZEN

    approved: bool
    decided_by: uuid.UUID
    decided_at: AwareDatetime
    comment: str = Field(default="", max_length=2000)


class Reapproval(BaseModel):
    """A choice of suppliers whose total passed what the approver's tier
    decides (plus the tenant's tolerance), sent to the tier that total names:
    the choice waits here, and becomes the case's selection only once that
    approver approves it. ``explanation`` is the model's words for why, kept
    only when every figure in them is one of code's facts; None otherwise."""

    model_config = _FROZEN

    approval: ApprovalAsked
    selection: Selection
    approved_limit: Price | None
    explanation: str | None = Field(default=None, max_length=2000)
    decision: Decided | None = None


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
    # Read from a mail with a document attached: which, and whether by OCR.
    read_from: ReadFrom | None = None
    # Opened by DW2 from a mail it read while the step is "AI làm, người
    # duyệt", or read from a scan: a person looks it over before DW2 sends
    # it anywhere. Who did and when, once they have.
    review: Review | None = None
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
    # The last choice that went back for approval past the tier.
    reapproval: Reapproval | None = None
    # DW02 function 5: what happened to each drafted order since, by po_ref.
    tracking: tuple[OrderTracking, ...] = ()

    @model_validator(mode="after")
    def _a_mail_names_its_message(self) -> Self:
        if (self.source is PrSource.MAIL) != (self.source_ref is not None):
            raise ValueError("a request read from mail names its message, and only it does")
        if self.read_from is not None and self.source is not PrSource.MAIL:
            raise ValueError("only a request read from mail was read from its attachment")
        if self.read_from is not None and self.read_from.scanned and self.review is None:
            raise ValueError("a request read from a scan waits for a person to look it over")
        return self

    @model_validator(mode="after")
    def _each_state_holds_what_it_needs(self) -> Self:
        sent = self.status is not CaseStatus.RECEIVED
        sourcing = self.status in (
            CaseStatus.RFQ_DRAFTED,
            CaseStatus.AWAITING_REAPPROVAL,
            CaseStatus.SUPPLIER_SELECTED,
            CaseStatus.PO_DRAFTED,
        )
        waiting = self.status is CaseStatus.AWAITING_REAPPROVAL
        if waiting != (self.reapproval is not None and self.reapproval.decision is None):
            raise ValueError("a choice waits on its approval exactly while the case says so")
        chosen = self.status in (CaseStatus.SUPPLIER_SELECTED, CaseStatus.PO_DRAFTED)
        decided = self.status in (CaseStatus.APPROVED, CaseStatus.REJECTED) or sourcing
        if sourcing != (self.rfq is not None):
            raise ValueError("a case being sourced holds its RFQ round, and only it does")
        if chosen != (self.selection is not None):
            raise ValueError("a case with suppliers chosen holds the choice, and only it does")
        if (self.status is CaseStatus.PO_DRAFTED) != (self.po is not None):
            raise ValueError("a case with orders drafted holds them, and only it does")
        drafted = {o.po_ref for o in self.po.orders} if self.po is not None else set()
        followed = [t.po_ref for t in self.tracking]
        if len(followed) != len(set(followed)) or not set(followed) <= drafted:
            raise ValueError("an order is followed once, and only an order drafted here")
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
