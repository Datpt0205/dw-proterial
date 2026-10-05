"""A request for quotation, the case that answers it, and what the customer receives.

WIV-03-023 as DW1 supports it: read the request (step 1), draft the quote-request
form (YCBG) Sales enters in the ERP (2), ask Design (3) and take its reply by the
YCBG number (4), discuss the spec with the customer when needed (6), gather the
evidence Sales weighs (7), carry Sales' price through the quotation document
(8) and its approval (9) to the customer (10) and the master list (11), or to a
decline at any step before the quotation is sent (5).

Two rules shape the module. A price is decided by a person in Sales, never by
this code: evidence holds no price of its own making, a reference price is a
different type from a decided one, and a decision cannot exist without who
made it. And another customer's price is internal: it reaches Sales marked as
such, and the document written for a customer has no field that could carry
it, nor the management guidance Sales records for the approver.

The state names and their labels are listed once, in the context's
``CONTEXT.md``; this module owns the moves between them. Validation errors name
fields and ids, never a value (spec decision 8): a price in an error message is
a customer's price in a log.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import (
    BravoOrder,
    CopperBasis,
    Currency,
    Customer,
    CustomerCode,
    CustomerItemCode,
    DocumentNo,
    Language,
    LmeBand,
    LmeMonth,
    Name,
    PrvCode,
    Quotation,
    Uom,
)
from dw_sales.domain.messages import Attachment, EmailAddress, Sha256Hex
from dw_sales.domain.pricing import FreightRate, Incoterm, SalesPricing

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

LineNo = Annotated[int, Field(ge=1, le=9999)]
Quantity = Annotated[Decimal, Field(gt=0)]
UnitPrice = Annotated[Decimal, Field(gt=0)]
LeadTimeDays = Annotated[int, Field(gt=0, le=365)]
Description = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
# Design's own code for a design. Not in the master data: Design issues it.
BpCode = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,31}$")]
Reason = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]
Guidance = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
CopperWeight = Annotated[Decimal, Field(gt=0)]
MessageId = Annotated[str, Field(pattern=r"^[!-~]{1,512}$")]

# A requested value the customer may leave blank, and the case then asks for.
RfqField = Literal["quantity", "needed_by"]
# How a quotation's price follows copper: what `sales_quote_rules` prescribes
# and what a line's `CopperBasis.kind` is.
CopperBasisKind = Literal["fixed", "lme_band"]
# How the customer of a request was found: by the sender's domain, or, for a
# message forwarded from an internal address, by the buyer the file names.
CustomerSource = Literal["sender_domain", "named_buyer"]

_KG_PER_TONNE: Final = Decimal(1000)


class Sourced[T](BaseModel):
    """A value together with the place in the customer's file it was read from.

    One cannot exist without the other: a number nobody can trace back to the
    file is a number nobody can check. A value the customer left blank is
    ``None`` anchored at the blank cell, so the reviewer is shown where it is
    missing.
    """

    model_config = _FROZEN

    value: T
    source: SourceAnchor


def _one_file(anchors: Iterable[SourceAnchor]) -> bool:
    return len({(a.attachment_id, a.attachment_sha256) for a in anchors}) == 1


def _distinct(numbers: Iterable[int]) -> bool:
    listed = list(numbers)
    return len(listed) == len(set(listed))


# ------------------------------------------------------------- the request --


class RequestedItem(BaseModel):
    """One line of a request for quotation, as the customer wrote it.

    The description is the customer's words. Which of our items it is, if any,
    is Design's answer (`DesignReplyLine`), not something read into the text.
    """

    model_config = _FROZEN

    line_no: LineNo
    customer_item_code: Sourced[CustomerItemCode] | None = None
    description: Sourced[Description]
    quantity: Sourced[Quantity | None]
    uom: Sourced[Uom]
    target_price: Sourced[UnitPrice] | None = None
    needed_by: Sourced[date | None]

    def missing(self) -> tuple[RfqField, ...]:
        """What the customer left blank: the line's `rfq_incomplete`."""
        blank: list[RfqField] = []
        if self.quantity.value is None:
            blank.append("quantity")
        if self.needed_by.value is None:
            blank.append("needed_by")
        return tuple(blank)

    def anchors(self) -> tuple[SourceAnchor, ...]:
        optional = (self.customer_item_code, self.target_price)
        return (
            self.description.source,
            self.quantity.source,
            self.uom.source,
            self.needed_by.source,
            *(value.source for value in optional if value is not None),
        )


class RfqDocument(BaseModel):
    """What one request-for-quotation file states, every value with its anchor."""

    model_config = _FROZEN

    # The buyer the file names, as printed. Read for a request forwarded from
    # an internal address, whose sender names no customer.
    buyer: Sourced[Name] | None = None
    rfq_no: Sourced[DocumentNo]
    rfq_date: Sourced[date]
    # When the customer wants the quotation by, when the file says. It drives
    # the due-date order of the work list and the derived "overdue".
    quote_due: Sourced[date] | None = None
    currency: Sourced[Currency]
    items: tuple[RequestedItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_file_and_distinct_lines(self) -> Self:
        if not _one_file(self.anchors()):
            raise ValueError("a request's values are read from one file")
        if not _distinct(item.line_no for item in self.items):
            raise ValueError("a request repeats a line number")
        return self

    def anchors(self) -> tuple[SourceAnchor, ...]:
        optional = (self.buyer, self.quote_due)
        return (
            self.rfq_no.source,
            self.rfq_date.source,
            self.currency.source,
            *(value.source for value in optional if value is not None),
            *(anchor for item in self.items for anchor in item.anchors()),
        )

    def line_numbers(self) -> frozenset[int]:
        return frozenset(item.line_no for item in self.items)

    def item(self, line_no: int) -> RequestedItem:
        return next(item for item in self.items if item.line_no == line_no)


class QuoteRequest(BaseModel):
    """A customer's request for quotation: who sent it, when, and what it asks.

    The subject and the body are never read for values, so text in them that
    reads like an instruction changes nothing.
    """

    model_config = _FROZEN

    message_id: MessageId
    received_at: AwareDatetime
    sender: EmailAddress
    # The attachment of this message every value was read from.
    attachment: Attachment
    customer_code: CustomerCode
    customer_from: CustomerSource
    document: RfqDocument

    @model_validator(mode="after")
    def _read_from_this_messages_file(self) -> Self:
        for anchor in self.document.anchors():
            if (anchor.attachment_id, anchor.attachment_sha256) != (
                self.attachment.attachment_id,
                self.attachment.sha256,
            ):
                raise ValueError(
                    f"the request was read from a file other than {self.attachment.attachment_id}"
                )
        if self.customer_from == "named_buyer" and self.document.buyer is None:
            raise ValueError("a customer found by the buyer's name needs the name the file prints")
        return self

    @property
    def currency(self) -> Currency:
        return self.document.currency.value


class DesignRequestLine(BaseModel):
    model_config = _FROZEN

    line_no: LineNo
    customer_item_code: CustomerItemCode | None
    # The item the convert list names for the customer's code, for Design to
    # confirm; None when the code is not in it.
    known_prv_code: PrvCode | None
    description: Description
    quantity: Quantity
    uom: Uom
    needed_by: date


class DesignRequestDraft(BaseModel):
    """What Design is asked (steps 2-3): the content of the quote-request form
    (YCBG) Sales checks, enters in the ERP and sends to Design.

    No price, target or otherwise: Design answers what the product is, and the
    commercial terms stay with Sales.
    """

    model_config = _FROZEN

    customer_code: CustomerCode
    customer_name: Name
    rfq_no: DocumentNo
    quote_due: date | None
    lines: tuple[DesignRequestLine, ...] = Field(min_length=1)


# ------------------------------------------------------------ Design's reply --


class DesignReplyLine(BaseModel):
    """Design's answer for one requested line, every value with its anchor."""

    model_config = _FROZEN

    line_no: LineNo
    bp_code: Sourced[BpCode]
    spec_no: Sourced[DocumentNo]
    # None while a new item's code is still to be created by Design.
    prv_code: Sourced[PrvCode] | None = None
    # Copper in one kilometre of the cable, as the specification states it.
    # None when the reply does not state it: the copper component of the price
    # evidence is then unknown rather than guessed.
    copper_kg_per_km: Sourced[CopperWeight] | None = None

    def anchors(self) -> tuple[SourceAnchor, ...]:
        optional = (self.prv_code, self.copper_kg_per_km)
        return (
            self.bp_code.source,
            self.spec_no.source,
            *(value.source for value in optional if value is not None),
        )


class DesignReplyDocument(BaseModel):
    """What one Design reply file states: the YCBG it answers, and per line
    what Design specified. Names nothing else of the request: the YCBG number
    is the only thing a reply is matched by."""

    model_config = _FROZEN

    ycbg_no: Sourced[DocumentNo]
    reply_date: Sourced[date]
    lines: tuple[DesignReplyLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_file_and_distinct_lines(self) -> Self:
        if not _one_file(self.anchors()):
            raise ValueError("a reply's values are read from one file")
        if not _distinct(line.line_no for line in self.lines):
            raise ValueError("a reply answers a line twice")
        return self

    def anchors(self) -> tuple[SourceAnchor, ...]:
        return (
            self.ycbg_no.source,
            self.reply_date.source,
            *(anchor for line in self.lines for anchor in line.anchors()),
        )


class DesignReply(BaseModel):
    """A Design reply as a case holds it: the message it arrived in, and what
    its file says."""

    model_config = _FROZEN

    message_id: MessageId
    received_at: AwareDatetime
    attachment: Attachment
    document: DesignReplyDocument

    @model_validator(mode="after")
    def _read_from_this_messages_file(self) -> Self:
        for anchor in self.document.anchors():
            if (anchor.attachment_id, anchor.attachment_sha256) != (
                self.attachment.attachment_id,
                self.attachment.sha256,
            ):
                raise ValueError(
                    f"the reply was read from a file other than {self.attachment.attachment_id}"
                )
        return self

    @property
    def ycbg_no(self) -> str:
        return self.document.ycbg_no.value

    def line(self, line_no: int) -> DesignReplyLine:
        return next(line for line in self.document.lines if line.line_no == line_no)


# ------------------------------------------------------------ the evidence --


def copper_cost_per_uom(copper_kg_per_km: Decimal, usd_per_tonne: Decimal, uom: Uom) -> Decimal:
    """The copper in one unit of the item at a copper price, in USD.

    Copper kg/km times USD per tonne, over 1000 kg per tonne, is USD per km;
    from there to the item's unit of measure.
    """
    return copper_kg_per_km * usd_per_tonne / _KG_PER_TONNE / _units_per_km(uom)


def _units_per_km(uom: Uom) -> Decimal:
    # No fallback branch: a unit added to `Uom` fails typecheck here (missing
    # return) instead of being converted as if it were metres.
    match uom:
        case "m":
            return Decimal(1000)


class CopperComponent(BaseModel):
    """What the copper in one unit of the item costs at an LME month, with the
    policy's adder for the month's band (`sales_pricing.copper_adders`)."""

    model_config = _FROZEN

    copper_kg_per_km: CopperWeight
    lme: LmeMonth
    adder_usd_per_tonne: Decimal = Field(ge=0)
    uom: Uom
    usd_per_uom: Decimal

    @model_validator(mode="after")
    def _is_the_formula(self) -> Self:
        # Stored so the evidence serialises whole; checked so a stored value
        # can never disagree with the formula it claims to be.
        copper = self.lme.usd_per_tonne + self.adder_usd_per_tonne
        if self.usd_per_uom != copper_cost_per_uom(self.copper_kg_per_km, copper, self.uom):
            raise ValueError("usd_per_uom is not the copper kg/km at the month's LME plus adder")
        return self


def copper_component(
    copper_kg_per_km: Decimal | None, lme: LmeMonth | None, uom: Uom, pricing: SalesPricing
) -> CopperComponent | None:
    """The copper component, or None when the copper weight, the LME month or
    the policy's adder for it is unknown. None is not zero: an unknown
    component is one nobody has priced."""
    if copper_kg_per_km is None or lme is None:
        return None
    adder = pricing.copper_adder(lme)
    if adder is None:
        return None
    copper = lme.usd_per_tonne + adder.adder_usd_per_tonne
    return CopperComponent(
        copper_kg_per_km=copper_kg_per_km,
        lme=lme,
        adder_usd_per_tonne=adder.adder_usd_per_tonne,
        uom=uom,
        usd_per_uom=copper_cost_per_uom(copper_kg_per_km, copper, uom),
    )


class PolicyFloor(BaseModel):
    """The lowest price before `price_below_policy_floor`: the copper component
    times (1 + `sales_pricing.floor_margin`), in USD."""

    model_config = _FROZEN

    copper_usd_per_uom: Decimal
    floor_margin: Decimal = Field(ge=0, lt=1)
    price: Decimal

    @classmethod
    def of(cls, copper: CopperComponent, pricing: SalesPricing) -> PolicyFloor:
        return cls(
            copper_usd_per_uom=copper.usd_per_uom,
            floor_margin=pricing.floor_margin,
            price=copper.usd_per_uom * (1 + pricing.floor_margin),
        )

    @model_validator(mode="after")
    def _is_the_formula(self) -> Self:
        if self.price != self.copper_usd_per_uom * (1 + self.floor_margin):
            raise ValueError("price is not the copper component times one plus the margin")
        return self


# The copper component and the policy are in USD. A price in another currency
# is not compared with them: the exchange-rate rule is owed by the customer.
_FLOOR_CURRENCY: Final[Currency] = "USD"


def policy_floor(
    copper: CopperComponent | None, currency: Currency, pricing: SalesPricing
) -> PolicyFloor | None:
    if copper is None or currency != _FLOOR_CURRENCY:
        return None
    return PolicyFloor.of(copper, pricing)


class InternalQuotation(BaseModel):
    """Another customer's quotation for the item: evidence for Sales only.

    Nothing written for the requester may contain it: the customer document
    has no field of this type, nor of anything derived from it.
    """

    model_config = _FROZEN

    internal_only: Literal[True] = True
    quotation: Quotation


class ReferencePrice(BaseModel):
    """The price the quote policy points Sales to, and the band around it.

    A reference, never a decision. Formed from other customers' prices, so it
    is internal like them.
    """

    model_config = _FROZEN

    internal_only: Literal[True] = True
    price: UnitPrice
    floor: UnitPrice
    ceiling: UnitPrice
    currency: Currency
    # The quotations it was formed from.
    basis: tuple[DocumentNo, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _price_is_inside_its_band(self) -> Self:
        if not self.floor <= self.price <= self.ceiling:
            raise ValueError("a reference price lies inside its own band")
        return self


class ReferenceRule(BaseModel):
    """How the quote policy forms a reference price, and the band around it.

    The reference is the mean of the prices the item is quoted at on the day,
    to any customer, in the request's currency, counting a price tied to an
    LME band only while the month's LME is inside that band. It is rounded to
    the precision those prices are quoted in, and the band is rounded inwards,
    so rounding never widens it.
    """

    model_config = _FROZEN

    band_below_percent: Decimal = Field(ge=0, lt=100)
    band_above_percent: Decimal = Field(ge=0, le=100)

    def reference_price(
        self,
        quotations: Iterable[Quotation],
        *,
        currency: Currency,
        lme: LmeMonth | None,
        as_of: date,
    ) -> ReferencePrice | None:
        """None when no quotation qualifies: there is then nothing to refer to."""
        current = sorted(
            (
                quotation
                for quotation in quotations
                if quotation.currency == currency
                and quotation.is_valid_on(as_of)
                and _copper_basis_holds(quotation, lme)
            ),
            key=lambda quotation: quotation.quote_no,
        )
        if not current:
            return None
        prices = [quotation.unit_price for quotation in current]
        step = Decimal(1).scaleb(min(_exponent(price) for price in prices))
        price = (sum(prices, Decimal(0)) / len(prices)).quantize(step, ROUND_HALF_UP)
        hundred = Decimal(100)
        below = price * (hundred - self.band_below_percent) / hundred
        above = price * (hundred + self.band_above_percent) / hundred
        return ReferencePrice(
            price=price,
            floor=below.quantize(step, ROUND_UP),
            ceiling=above.quantize(step, ROUND_DOWN),
            currency=currency,
            basis=tuple(quotation.quote_no for quotation in current),
        )


def _copper_basis_holds(quotation: Quotation, lme: LmeMonth | None) -> bool:
    """A fixed price holds whatever copper does; a banded one only while the
    LME is inside its band, which an unknown LME cannot show."""
    basis = quotation.copper_basis
    if isinstance(basis, LmeBand):
        return lme is not None and basis.contains(lme.usd_per_tonne)
    return True


def _exponent(price: Decimal) -> int:
    exponent = price.as_tuple().exponent
    if not isinstance(exponent, int):
        # Every model that holds a price refuses NaN and infinity before this.
        raise ValueError("not a finite price")
    return exponent


class OrderedLine(BaseModel):
    """One line of an ERP order of the item by the requester: its ordering status."""

    model_config = _FROZEN

    so_no: DocumentNo
    customer_code: CustomerCode
    order_date: date
    currency: Currency
    prv_code: PrvCode
    quantity: Quantity
    unit_price: UnitPrice

    @classmethod
    def lines_of(cls, order: BravoOrder, prv_code: str) -> tuple[OrderedLine, ...]:
        return tuple(
            cls(
                so_no=order.so_no,
                customer_code=order.customer_code,
                order_date=order.order_date,
                currency=order.currency,
                prv_code=line.prv_code,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
            for line in order.lines
            if line.prv_code == prv_code
        )


class FreightEvidence(BaseModel):
    """Freight for the lane Sales named, from `sales_pricing.freight`.

    ``rate`` is None when the policy lists no rate for the lane, and the
    evidence says so rather than showing a zero.
    """

    model_config = _FROZEN

    incoterm: Incoterm
    destination: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    rate: FreightRate | None

    @model_validator(mode="after")
    def _rate_is_for_the_lane(self) -> Self:
        if self.rate is not None and (self.rate.incoterm, self.rate.destination) != (
            self.incoterm,
            self.destination,
        ):
            raise ValueError("the freight rate is for another lane")
        return self


class PriceEvidence(BaseModel):
    """What Sales weighs to decide one line's price (step 7), as of one day.

    Every factor of the process: the customer's target price, its quotation
    history and its orders of the item, other customers' prices (internal),
    the LME month with the copper component and the policy floor at it,
    freight for the lane Sales names, and the policy's reference when the
    policy defines one. The management guidance is not here: Sales writes it
    on the decision, where the approver reads it. The constructor keeps the
    customer's own rows apart from other customers' rows: a row filed under
    the wrong heading is how another customer's price ends up treated as this
    customer's.
    """

    model_config = _FROZEN

    line_no: LineNo
    customer_code: CustomerCode
    # None for a new design: an item without a code has no history.
    prv_code: PrvCode | None
    currency: Currency
    as_of: date
    # ``sales_pricing@<version>``: the policy the copper component, the floor
    # and the freight were read from.
    pricing_policy: str = Field(pattern=r"^sales_pricing@\d+\.\d+\.\d+$")
    target_price: UnitPrice | None = None
    own_history: tuple[Quotation, ...] = ()
    other_customers: tuple[InternalQuotation, ...] = ()
    orders: tuple[OrderedLine, ...] = ()
    lme: LmeMonth | None = None
    copper: CopperComponent | None = None
    floor: PolicyFloor | None = None
    freight: FreightEvidence | None = None
    reference: ReferencePrice | None = None

    @model_validator(mode="after")
    def _rows_belong_where_they_are_filed(self) -> Self:
        for quotation in self.own_history:
            if quotation.customer_code != self.customer_code:
                raise ValueError(
                    f"{quotation.quote_no} is {quotation.customer_code}'s quotation, filed as"
                    f" {self.customer_code}'s own"
                )
        for row in self.other_customers:
            if row.quotation.customer_code == self.customer_code:
                raise ValueError(
                    f"{row.quotation.quote_no} is {self.customer_code}'s own quotation, filed as"
                    " another customer's"
                )
        for quotation in (*self.own_history, *(row.quotation for row in self.other_customers)):
            if quotation.prv_code != self.prv_code:
                raise ValueError(f"{quotation.quote_no} quotes {quotation.prv_code}, not this item")
        for line in self.orders:
            if (line.customer_code, line.prv_code) != (self.customer_code, self.prv_code):
                raise ValueError(f"{line.so_no} is not this customer's order of this item")
        if self.copper is not None and self.copper.lme != self.lme:
            raise ValueError("the copper component is priced at another LME month")
        if self.floor is not None and (
            self.copper is None
            or self.currency != _FLOOR_CURRENCY
            or self.floor.copper_usd_per_uom != self.copper.usd_per_uom
        ):
            raise ValueError("the floor is the copper component's, in its currency")
        if self.reference is not None and self.reference.currency != self.currency:
            raise ValueError("the reference price is in another currency")
        return self


# ------------------------------------------------------------ the decision --


class LinePrice(BaseModel):
    """Sales' terms for one line: the price, the MOQ and lead time it holds
    for, and how it follows copper."""

    model_config = _FROZEN

    line_no: LineNo
    unit_price: UnitPrice
    moq: Quantity
    lead_time_days: LeadTimeDays
    copper_basis: CopperBasis


class PricingDecision(BaseModel):
    """The price Sales decided (step 7), in the request's currency.

    Made by a person and saying who: nothing in this context produces one on
    its own, and a reference price is a different type that cannot stand in
    for it.
    """

    model_config = _FROZEN

    decided_by: uuid.UUID
    decided_at: AwareDatetime
    # The LME month the price was decided against. Stamped here so the
    # quotation states the copper basis its price was set on, not whatever the
    # LME is when the document happens to be written.
    lme: LmeMonth | None
    lines: tuple[LinePrice, ...] = Field(min_length=1)
    # What management told Sales about this price, in Sales' words, for the
    # approver. Internal: no type written for the customer has a field for it.
    management_guidance: Guidance | None = None

    @model_validator(mode="after")
    def _one_price_per_line(self) -> Self:
        if not _distinct(line.line_no for line in self.lines):
            raise ValueError("a decision prices a line twice")
        if self.lme is None and any(isinstance(line.copper_basis, LmeBand) for line in self.lines):
            raise ValueError("a price banded on LME names the LME month it was decided against")
        return self

    def line(self, line_no: int) -> LinePrice:
        return next(line for line in self.lines if line.line_no == line_no)


# ---------------------------------------------------------------- findings --


class QuoteFindingCode(StrEnum):
    """The quotation checks of the spec's table, plus `customer_unknown`, which
    a request forwarded from an internal address raises as an order does."""

    RFQ_INCOMPLETE = "rfq_incomplete"
    CUSTOMER_UNKNOWN = "customer_unknown"
    PRICE_BELOW_POLICY_FLOOR = "price_below_policy_floor"
    PRICE_BASIS_MISMATCH = "price_basis_mismatch"
    ABOVE_TARGET_PRICE = "above_target_price"


# Raised when the case opens and decided by Sales before the YCBG is drafted.
INTAKE_FINDINGS: Final = frozenset(
    {QuoteFindingCode.RFQ_INCOMPLETE, QuoteFindingCode.CUSTOMER_UNKNOWN}
)
# Raised by a price decision and decided by the approver.
PRICE_FINDINGS: Final = frozenset(
    {
        QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR,
        QuoteFindingCode.PRICE_BASIS_MISMATCH,
        QuoteFindingCode.ABOVE_TARGET_PRICE,
    }
)
BLOCKING_FINDINGS: Final = frozenset(QuoteFindingCode) - {QuoteFindingCode.ABOVE_TARGET_PRICE}


class FindingOpen(BaseModel):
    model_config = _FROZEN

    kind: Literal["open"] = "open"


class FindingAccepted(BaseModel):
    """Accepted by the approver: with a reason for a blocking finding, as an
    acknowledgement for `above_target_price`."""

    model_config = _FROZEN

    kind: Literal["accepted"] = "accepted"
    by: uuid.UUID
    at: AwareDatetime
    reason: Reason | None = None


class FindingCorrected(BaseModel):
    """Sales typed the answer: the customer's missing values, asked for in
    Sales' own mail, or the customer a forwarded request is for. Shown as
    hand-entered, naming who typed it."""

    model_config = _FROZEN

    kind: Literal["corrected_by_sales"] = "corrected_by_sales"
    by: uuid.UUID
    at: AwareDatetime
    note: Reason | None = None
    quantity: Quantity | None = None
    needed_by: date | None = None
    customer_code: CustomerCode | None = None


FindingDisposition = Annotated[
    FindingOpen | FindingAccepted | FindingCorrected, Field(discriminator="kind")
]


class QuoteFinding(BaseModel):
    """One quotation check that did not pass, and what was decided about it.

    ``expected`` and ``actual`` are amounts or bases as text, computed by code.
    They are price-bearing: only a holder of ``sales.price.read`` is shown
    them, and they never travel into an event or a log.
    """

    model_config = _FROZEN

    code: QuoteFindingCode
    # Stamped with the code's own blocking flag when raised.
    blocking: bool
    line_no: LineNo | None = None
    # `rfq_incomplete` only: which values the customer left blank.
    missing: tuple[RfqField, ...] = ()
    expected: str | None = Field(default=None, max_length=200)
    actual: str | None = Field(default=None, max_length=200)
    # ``<policy_id>@<version>`` of every policy whose value raised it.
    rule_versions: tuple[str, ...] = ()
    disposition: FindingDisposition = FindingOpen()

    @model_validator(mode="after")
    def _one_meaning_per_code(self) -> Self:
        code = self.code
        if self.blocking != (code in BLOCKING_FINDINGS):
            raise ValueError(f"{code} is blocking only if the table says so")
        if (code is QuoteFindingCode.CUSTOMER_UNKNOWN) != (self.line_no is None):
            raise ValueError(f"{code}: only customer_unknown is about the request as a whole")
        if (code is QuoteFindingCode.RFQ_INCOMPLETE) != bool(self.missing):
            raise ValueError(f"{code}: only rfq_incomplete names missing values")
        if (code in PRICE_FINDINGS) != bool(self.rule_versions):
            raise ValueError(f"{code}: a price finding names the policies it was raised under")
        for version in self.rule_versions:
            if not version.startswith(("sales_pricing@", "sales_quote_rules@")):
                raise ValueError(f"{code}: {version} is not a quotation policy")
        disposition = self.disposition
        if isinstance(disposition, FindingCorrected):
            if code is QuoteFindingCode.RFQ_INCOMPLETE:
                given = {
                    field
                    for field, value in (
                        ("quantity", disposition.quantity),
                        ("needed_by", disposition.needed_by),
                    )
                    if value is not None
                }
                if given != set(self.missing) or disposition.customer_code is not None:
                    raise ValueError(f"{code}: the correction gives exactly the missing values")
            elif code is QuoteFindingCode.CUSTOMER_UNKNOWN:
                if disposition.customer_code is None or (
                    disposition.quantity is not None or disposition.needed_by is not None
                ):
                    raise ValueError(f"{code}: the correction names the customer and only that")
            else:
                raise ValueError(f"{code} is not corrected by Sales")
        if isinstance(disposition, FindingAccepted):
            if code in INTAKE_FINDINGS:
                raise ValueError(f"{code} is not accepted: Sales types the answer")
            if self.blocking and disposition.reason is None:
                raise ValueError(f"{code} is accepted with a reason")
        return self

    @property
    def is_open(self) -> bool:
        return isinstance(self.disposition, FindingOpen)

    @property
    def key(self) -> tuple[QuoteFindingCode, int | None]:
        return (self.code, self.line_no)


def intake_findings(request: QuoteRequest) -> tuple[QuoteFinding, ...]:
    """What a request raises before anyone works on it."""
    findings = []
    if request.customer_from == "named_buyer":
        findings.append(QuoteFinding(code=QuoteFindingCode.CUSTOMER_UNKNOWN, blocking=True))
    for item in request.document.items:
        if missing := item.missing():
            findings.append(
                QuoteFinding(
                    code=QuoteFindingCode.RFQ_INCOMPLETE,
                    blocking=True,
                    line_no=item.line_no,
                    missing=missing,
                )
            )
    return tuple(findings)


def price_findings(
    case: QuoteCase,
    decision: PricingDecision,
    *,
    latest_lme: LmeMonth | None,
    pricing: SalesPricing,
    prescribed_basis: CopperBasisKind,
    quote_rules_version: str,
) -> tuple[QuoteFinding, ...]:
    """The quotation findings a decision raises, line by line.

    - `price_below_policy_floor`: the price is under the copper component at
      the decision's LME month times (1 + the floor margin).
    - `price_basis_mismatch`: the line's copper basis is not the prescribed
      kind; or, banded, its band is not the policy's band for the decision's
      LME, or that month is not the latest one published when it was decided.
    - `above_target_price`: the price is over the customer's target.
    """
    reply = case.design_reply
    if reply is None:
        raise ConflictError(
            "a price is checked against Design's reply", details={"case_id": str(case.case_id)}
        )
    pricing_version = pricing.version
    findings = []
    for line in sorted(decision.lines, key=lambda line: line.line_no):
        item = case.request.document.item(line.line_no)
        copper_weight = reply.line(line.line_no).copper_kg_per_km
        copper = copper_component(
            copper_weight.value if copper_weight else None, decision.lme, item.uom.value, pricing
        )
        floor = policy_floor(copper, case.request.currency, pricing)
        if floor is not None and line.unit_price < floor.price:
            findings.append(
                QuoteFinding(
                    code=QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR,
                    blocking=True,
                    line_no=line.line_no,
                    expected=f">= {floor.price}",
                    actual=str(line.unit_price),
                    rule_versions=(pricing_version,),
                )
            )
        if mismatch := _basis_mismatch(
            line.copper_basis, decision.lme, latest_lme, pricing, prescribed_basis
        ):
            expected, actual = mismatch
            findings.append(
                QuoteFinding(
                    code=QuoteFindingCode.PRICE_BASIS_MISMATCH,
                    blocking=True,
                    line_no=line.line_no,
                    expected=expected,
                    actual=actual,
                    rule_versions=(pricing_version, quote_rules_version),
                )
            )
        target = item.target_price
        if target is not None and line.unit_price > target.value:
            findings.append(
                QuoteFinding(
                    code=QuoteFindingCode.ABOVE_TARGET_PRICE,
                    blocking=False,
                    line_no=line.line_no,
                    expected=f"<= {target.value}",
                    actual=str(line.unit_price),
                    rule_versions=(pricing_version,),
                )
            )
    return tuple(findings)


def _basis_mismatch(
    basis: CopperBasis,
    lme: LmeMonth | None,
    latest: LmeMonth | None,
    pricing: SalesPricing,
    prescribed: CopperBasisKind,
) -> tuple[str, str] | None:
    """What the basis should have been and what it is, or None when it holds."""
    if basis.kind != prescribed:
        return prescribed, basis.kind
    if not isinstance(basis, LmeBand):
        return None
    assert lme is not None  # PricingDecision refuses a banded price without its month
    adder = pricing.copper_adder(lme)
    actual = f"{basis.low_usd_per_tonne}-{basis.high_usd_per_tonne} @{lme.month}"
    if adder is None or adder.band != basis:
        band = (
            "none"
            if adder is None
            else (f"{adder.band.low_usd_per_tonne}-{adder.band.high_usd_per_tonne}")
        )
        return f"{band} @{lme.month}", actual
    if latest is not None and lme.month != latest.month:
        return f"@{latest.month}", actual
    return None


# ---------------------------------------------------- what the customer gets --


class QuoteAddressee(BaseModel):
    """The customer a quotation is written for: as much of the master record
    as a quotation may carry. No export-control status, nothing of anyone else."""

    model_config = _FROZEN

    code: CustomerCode
    name: Name
    language: Language
    contacts: tuple[EmailAddress, ...] = Field(min_length=1)

    @classmethod
    def of(cls, customer: Customer) -> QuoteAddressee:
        return cls(
            code=customer.code,
            name=customer.name,
            language=customer.language,
            contacts=customer.contacts,
        )


class CustomerQuoteLine(BaseModel):
    """One quoted line: the customer's item, our specification and Sales' terms."""

    model_config = _FROZEN

    line_no: LineNo
    customer_item_code: CustomerItemCode | None
    description: Description
    # None for a new design whose code Design has still to create.
    prv_code: PrvCode | None
    bp_code: BpCode
    spec_no: DocumentNo
    quantity: Quantity
    uom: Uom
    unit_price: UnitPrice
    moq: Quantity
    lead_time_days: LeadTimeDays
    copper_basis: CopperBasis


class CustomerQuoteDocument(BaseModel):
    """The quotation one customer receives (steps 8 and 10): the data the
    xlsx and PDF are filled from.

    Bound to that customer in the constructor: it is addressed only to the
    customer's own contacts from master data. Its fields hold the request's own
    values, Design's specification and Sales' decided terms. None can hold
    price evidence, another customer's quotation, a reference price or the
    management guidance, and pydantic refuses those types where a price or a
    line is expected.
    """

    model_config = _FROZEN

    quote_no: DocumentNo
    addressee: QuoteAddressee
    recipients: tuple[EmailAddress, ...] = Field(min_length=1)
    # The customer's own request number.
    their_reference: DocumentNo
    issued_on: date
    # The last day the prices hold.
    valid_to: date
    currency: Currency
    # The LME month the prices were decided against; None when none was known.
    lme: LmeMonth | None
    lines: tuple[CustomerQuoteLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _for_one_customer(self) -> Self:
        contacts = {contact.address.lower() for contact in self.addressee.contacts}
        addresses = [recipient.address.lower() for recipient in self.recipients]
        for index, address in enumerate(addresses):
            if address not in contacts:
                raise ValueError(f"recipients[{index}] is not a contact of {self.addressee.code}")
        if len(addresses) != len(set(addresses)):
            raise ValueError("a recipient is listed twice")
        if not _distinct(line.line_no for line in self.lines):
            raise ValueError("a quotation repeats a line number")
        if self.valid_to < self.issued_on:
            raise ValueError("a quotation expires before it is issued")
        if self.lme is None and any(isinstance(line.copper_basis, LmeBand) for line in self.lines):
            raise ValueError("a price banded on LME names the LME month")
        return self

    def sha256(self) -> str:
        """The hash an approval is bound to: of the canonical JSON of the data,
        so the same terms hash the same however the files are rendered."""
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ------------------------------------------------------- the state machine --


class QuoteStatus(StrEnum):
    RECEIVED = "received"
    YCBG_DRAFTED = "ycbg_drafted"
    YCBG_RECORDED = "ycbg_recorded"
    SENT_TO_DESIGN = "sent_to_design"
    DESIGN_REPLIED = "design_replied"
    SPEC_DISCUSSION = "spec_discussion"
    PRICED = "priced"
    PENDING_APPROVAL = "pending_approval"
    RETURNED = "returned"
    APPROVED = "approved"
    SENT = "sent"
    MASTER_LIST_RECORDED = "master_list_recorded"
    DECLINED = "declined"


# Before the quotation reaches the customer: Sales may still decline.
_BEFORE_SENT: Final = frozenset(QuoteStatus) - {
    QuoteStatus.SENT,
    QuoteStatus.MASTER_LIST_RECORDED,
    QuoteStatus.DECLINED,
}


def _with_decline(*targets: QuoteStatus) -> frozenset[QuoteStatus]:
    return frozenset({*targets, QuoteStatus.DECLINED})


# Every move a quotation may make; anything else is refused.
_MOVES: Final[Mapping[QuoteStatus, frozenset[QuoteStatus]]] = {
    QuoteStatus.RECEIVED: _with_decline(QuoteStatus.YCBG_DRAFTED),
    QuoteStatus.YCBG_DRAFTED: _with_decline(QuoteStatus.YCBG_RECORDED),
    QuoteStatus.YCBG_RECORDED: _with_decline(QuoteStatus.SENT_TO_DESIGN),
    QuoteStatus.SENT_TO_DESIGN: _with_decline(QuoteStatus.DESIGN_REPLIED),
    QuoteStatus.DESIGN_REPLIED: _with_decline(QuoteStatus.SPEC_DISCUSSION, QuoteStatus.PRICED),
    # Settled with the customer (back to design_replied), or Design must
    # answer again (sent_to_design).
    QuoteStatus.SPEC_DISCUSSION: _with_decline(
        QuoteStatus.DESIGN_REPLIED, QuoteStatus.SENT_TO_DESIGN
    ),
    # Priced again: Sales may change the price until it is submitted.
    QuoteStatus.PRICED: _with_decline(QuoteStatus.PRICED, QuoteStatus.PENDING_APPROVAL),
    # Back to priced: a change to price, MOQ or lead time after submitting
    # withdraws the document the approver was shown.
    QuoteStatus.PENDING_APPROVAL: _with_decline(
        QuoteStatus.APPROVED, QuoteStatus.RETURNED, QuoteStatus.PRICED
    ),
    QuoteStatus.RETURNED: _with_decline(QuoteStatus.PRICED),
    QuoteStatus.APPROVED: _with_decline(QuoteStatus.SENT, QuoteStatus.PRICED),
    QuoteStatus.SENT: frozenset({QuoteStatus.MASTER_LIST_RECORDED}),
    QuoteStatus.MASTER_LIST_RECORDED: frozenset(),
    QuoteStatus.DECLINED: frozenset(),
}


def transition(current: QuoteStatus, target: QuoteStatus) -> QuoteStatus:
    """``target``, when a quotation may move there from ``current``."""
    if target not in _MOVES[current]:
        raise ConflictError(
            f"a quotation cannot move from {current} to {target}",
            details={"from": current.value, "to": target.value},
        )
    return target


class DeclineReason(StrEnum):
    NOT_OUR_PRODUCT = "not_our_product"
    DESIGN_CANNOT = "design_cannot"
    CUSTOMER_REJECTED_SPEC = "customer_rejected_spec"
    COMMERCIAL = "commercial"


class QuoteCapability(StrEnum):
    """What a caller may do on a quote that the case itself checks.

    Resolved by the caller from the verified access context and handed in as a
    value: the domain never asks the platform who holds what.
    """

    # The scope ``sales.quote.approve``: the head of Sales, or a deputy
    # holding the approver permission set.
    APPROVE = "approve"


class QuoteActor(BaseModel):
    """Who acts on a quote, with the capabilities the caller verified."""

    model_config = _FROZEN

    user_id: uuid.UUID
    capabilities: frozenset[QuoteCapability] = frozenset()


class YcbgRecord(BaseModel):
    """The ERP's number for the quote request, as Sales typed it."""

    model_config = _FROZEN

    ycbg_no: DocumentNo
    recorded_by: uuid.UUID
    recorded_at: AwareDatetime


class Submission(BaseModel):
    """The document the approver is shown, its hash, and who priced it."""

    model_config = _FROZEN

    document: CustomerQuoteDocument
    document_sha256: Sha256Hex
    # The decision's `decided_by`: the one person who may not approve it.
    priced_by: uuid.UUID
    submitted_by: uuid.UUID
    submitted_at: AwareDatetime

    @model_validator(mode="after")
    def _hash_is_the_documents(self) -> Self:
        if self.document_sha256 != self.document.sha256():
            raise ValueError("document_sha256 is not the document's")
        return self


class Return(BaseModel):
    """The approver sent the price back to the pricer, and why."""

    model_config = _FROZEN

    returned_by: uuid.UUID
    returned_at: AwareDatetime
    reason: Reason
    # The version of the case the returned document belonged to.
    case_version: int = Field(ge=1)


class Approval(BaseModel):
    model_config = _FROZEN

    approved_by: uuid.UUID
    approved_at: AwareDatetime
    # What exactly was approved: the case as it stood, and the document's hash.
    case_version: int = Field(ge=1)
    document_sha256: Sha256Hex


class Stamp(BaseModel):
    """Who did a step that needs nothing more than who and when."""

    model_config = _FROZEN

    by: uuid.UUID
    at: AwareDatetime


class Decline(BaseModel):
    """Sales' decision not to quote (step 5), with the reason the customer is told."""

    model_config = _FROZEN

    declined_by: uuid.UUID
    declined_at: AwareDatetime
    reason: DeclineReason
    note: Reason | None = None


# What each status needs on the case; anything not listed must be absent,
# except what `_MAY_HOLD` allows. A declined case holds what it had.
_NEEDS: Final[Mapping[QuoteStatus, frozenset[str]]] = {
    QuoteStatus.RECEIVED: frozenset(),
    QuoteStatus.YCBG_DRAFTED: frozenset(),
    QuoteStatus.YCBG_RECORDED: frozenset({"ycbg"}),
    QuoteStatus.SENT_TO_DESIGN: frozenset({"ycbg"}),
    QuoteStatus.DESIGN_REPLIED: frozenset({"ycbg", "design_reply"}),
    QuoteStatus.SPEC_DISCUSSION: frozenset({"ycbg", "design_reply"}),
    QuoteStatus.PRICED: frozenset({"ycbg", "design_reply", "pricing"}),
    QuoteStatus.PENDING_APPROVAL: frozenset({"ycbg", "design_reply", "pricing", "submission"}),
    QuoteStatus.RETURNED: frozenset({"ycbg", "design_reply", "pricing", "return"}),
    QuoteStatus.APPROVED: frozenset({"ycbg", "design_reply", "pricing", "submission", "approval"}),
    QuoteStatus.SENT: frozenset(
        {"ycbg", "design_reply", "pricing", "submission", "approval", "sent"}
    ),
    QuoteStatus.MASTER_LIST_RECORDED: frozenset(
        {"ycbg", "design_reply", "pricing", "submission", "approval", "sent", "master_list"}
    ),
}
# Design is asked again after a spec discussion: its earlier reply stays.
# Returns are history and stay on the case whatever comes after.
_MAY_HOLD: Final[Mapping[QuoteStatus, frozenset[str]]] = {
    QuoteStatus.SENT_TO_DESIGN: frozenset({"design_reply"}),
}
_HISTORY: Final = frozenset({"return"})


class QuoteCase(BaseModel):
    """One request for quotation on its way to a quotation or a decline.

    Immutable: each step returns the next case, built through the constructor,
    so a case whose data does not support its status (approved without an
    approval, a document whose prices are not the decided ones, approved by
    its pricer) cannot exist, whether it was just made or read back from
    storage. Every step bumps ``case_version``.
    """

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int = Field(default=1, ge=1)
    request: QuoteRequest
    status: QuoteStatus = QuoteStatus.RECEIVED
    findings: tuple[QuoteFinding, ...] = ()
    ycbg: YcbgRecord | None = None
    # Every reply Design sent for this case, oldest first; the last is current.
    design_replies: tuple[DesignReply, ...] = ()
    pricing: PricingDecision | None = None
    # Decisions replaced by a later one, oldest first: kept, never edited.
    earlier_pricing: tuple[PricingDecision, ...] = ()
    returns: tuple[Return, ...] = ()
    submission: Submission | None = None
    approval: Approval | None = None
    sent: Stamp | None = None
    master_list: Stamp | None = None
    decline: Decline | None = None

    @classmethod
    def open(cls, case_id: uuid.UUID, request: QuoteRequest) -> QuoteCase:
        """A new case, with what the request raises on its own."""
        return cls(case_id=case_id, request=request, findings=intake_findings(request))

    # -------------------------------------------------------- invariants --

    @model_validator(mode="after")
    def _data_supports_status(self) -> Self:
        held = {
            "ycbg": self.ycbg is not None,
            "design_reply": bool(self.design_replies),
            "pricing": self.pricing is not None,
            "submission": self.submission is not None,
            "approval": self.approval is not None,
            "sent": self.sent is not None,
            "master_list": self.master_list is not None,
            "return": bool(self.returns),
        }
        if (self.status is QuoteStatus.DECLINED) != (self.decline is not None):
            raise ValueError("a decline goes with the declined status, and only with it")
        if self.status is not QuoteStatus.DECLINED:
            needs = _NEEDS[self.status]
            allowed = needs | _MAY_HOLD.get(self.status, frozenset()) | _HISTORY
            for what, present in held.items():
                if what in needs and not present:
                    raise ValueError(f"a {self.status} quotation needs its {what}")
                if present and what not in allowed:
                    raise ValueError(f"a {self.status} quotation cannot hold a {what}")
        self._check_findings()
        self._check_design()
        self._check_pricing()
        self._check_submission_and_approval()
        return self

    def _check_findings(self) -> None:
        keys = [finding.key for finding in self.findings]
        if len(keys) != len(set(keys)):
            raise ValueError("a finding is raised twice")
        lines = self.request.document.line_numbers()
        for finding in self.findings:
            if finding.line_no is not None and finding.line_no not in lines:
                raise ValueError(f"{finding.code} names a line the request does not have")
            if finding.code in PRICE_FINDINGS and self.pricing is None:
                raise ValueError(f"{finding.code} is raised by a decided price")
        intake = {f.key for f in self.findings if f.code in INTAKE_FINDINGS}
        if intake != {f.key for f in intake_findings(self.request)}:
            raise ValueError("the request's own findings are the ones it raises")
        if self.status not in (QuoteStatus.RECEIVED, QuoteStatus.DECLINED) and any(
            f.is_open for f in self.findings if f.code in INTAKE_FINDINGS
        ):
            raise ValueError("a request leaves received once Sales has answered its findings")

    def _check_design(self) -> None:
        lines = self.request.document.line_numbers()
        for reply in self.design_replies:
            if self.ycbg is None or reply.ycbg_no != self.ycbg.ycbg_no:
                raise ValueError("a Design reply answers this case's YCBG")
        if self.design_replies:
            current = self.design_replies[-1].document.lines
            if {line.line_no for line in current} != lines:
                raise ValueError("Design's reply answers every requested line once")

    def _check_pricing(self) -> None:
        if (
            self.pricing is not None
            and {line.line_no for line in self.pricing.lines}
            != self.request.document.line_numbers()
        ):
            raise ValueError("a decision prices every requested line")

    def _check_submission_and_approval(self) -> None:
        submission, approval, pricing = self.submission, self.approval, self.pricing
        if submission is not None:
            assert pricing is not None  # _NEEDS: a submission comes with its pricing
            document = submission.document
            if submission.priced_by != pricing.decided_by:
                raise ValueError("priced_by is the decision's decided_by")
            if (
                document.addressee.code != self.customer_code
                or document.their_reference != self.request.document.rfq_no.value
                or document.currency != self.request.currency
                or document.lme != pricing.lme
                or document.lines != self.document_lines()
            ):
                raise ValueError("the document states the request and the decided terms")
        if approval is not None:
            assert submission is not None  # _NEEDS: an approval comes with its submission
            if approval.approved_by == submission.priced_by:
                raise ValueError("approved_by is not priced_by")
            if approval.document_sha256 != submission.document_sha256:
                raise ValueError("the approval is of the submitted document")
            for finding in self.findings:
                if finding.code not in PRICE_FINDINGS:
                    continue
                disposition = finding.disposition
                if not isinstance(disposition, FindingAccepted) or (
                    disposition.by != approval.approved_by
                ):
                    raise ValueError(f"{finding.code} is decided by the approver")

    # --------------------------------------------------- reading the case --

    @property
    def customer_code(self) -> str:
        """The customer the quotation is for: the request's, or the one Sales
        confirmed for a forwarded request."""
        for finding in self.findings:
            disposition = finding.disposition
            if isinstance(disposition, FindingCorrected) and disposition.customer_code:
                return disposition.customer_code
        return self.request.customer_code

    @property
    def design_reply(self) -> DesignReply | None:
        """Design's current reply: the last one it sent."""
        return self.design_replies[-1] if self.design_replies else None

    def quantity(self, line_no: int) -> Decimal | None:
        """The line's quantity: as the customer wrote it, or as Sales typed it."""
        typed = self._completion(line_no)
        value = self.request.document.item(line_no).quantity.value
        return value if value is not None else (typed.quantity if typed else None)

    def needed_by(self, line_no: int) -> date | None:
        typed = self._completion(line_no)
        value = self.request.document.item(line_no).needed_by.value
        return value if value is not None else (typed.needed_by if typed else None)

    def _completion(self, line_no: int) -> FindingCorrected | None:
        for finding in self.findings:
            if finding.key == (QuoteFindingCode.RFQ_INCOMPLETE, line_no) and isinstance(
                finding.disposition, FindingCorrected
            ):
                return finding.disposition
        return None

    def is_overdue(self, today: date) -> bool:
        """Past the customer's quote due date and not yet sent or declined.

        Derived on every read and never stored: a stored "overdue" is one
        nobody updates the day after.
        """
        due = self.request.document.quote_due
        return due is not None and self.status in _BEFORE_SENT and today > due.value

    def document_lines(self) -> tuple[CustomerQuoteLine, ...]:
        """The quoted lines: the customer's item, Design's specification and
        Sales' decided terms, and nothing else."""
        reply, pricing = self.design_reply, self.pricing
        if reply is None or pricing is None:
            raise ConflictError(
                "a quotation is written from Design's reply and a decided price",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        lines = []
        for item in self.request.document.items:
            design = reply.line(item.line_no)
            terms = pricing.line(item.line_no)
            quantity = self.quantity(item.line_no)
            assert quantity is not None  # _check_findings: answered before pricing
            lines.append(
                CustomerQuoteLine(
                    line_no=item.line_no,
                    customer_item_code=(
                        item.customer_item_code.value if item.customer_item_code else None
                    ),
                    description=item.description.value,
                    prv_code=design.prv_code.value if design.prv_code else None,
                    bp_code=design.bp_code.value,
                    spec_no=design.spec_no.value,
                    quantity=quantity,
                    uom=item.uom.value,
                    unit_price=terms.unit_price,
                    moq=terms.moq,
                    lead_time_days=terms.lead_time_days,
                    copper_basis=terms.copper_basis,
                )
            )
        return tuple(lines)

    def master_list_rows(self) -> tuple[Quotation, ...]:
        """The master-list rows of a sent quotation (step 11), one per line,
        valid from the day it was issued to the last day its prices hold."""
        submission = self.submission
        if self.status is not QuoteStatus.SENT or submission is None:
            raise ConflictError(
                "a master-list row is made for a sent quotation",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        document = submission.document
        pending = [line.line_no for line in document.lines if line.prv_code is None]
        if pending:
            raise ConflictError(
                "a line whose item code Design has still to create has no master-list row",
                details={"case_id": str(self.case_id), "line_nos": pending},
            )
        return tuple(
            Quotation(
                quote_no=document.quote_no,
                customer_code=document.addressee.code,
                prv_code=line.prv_code,
                unit_price=line.unit_price,
                currency=document.currency,
                uom=line.uom,
                moq=line.moq,
                lead_time_days=line.lead_time_days,
                copper_basis=line.copper_basis,
                valid_from=document.issued_on,
                valid_to=document.valid_to,
            )
            for line in document.lines
            if line.prv_code is not None
        )

    # -------------------------------------------------------------- moves --

    def _changed(self, **changes: object) -> QuoteCase:
        """The next version of the case: every change bumps ``case_version``."""
        return QuoteCase.model_validate(
            {**dict(self), **changes, "case_version": self.case_version + 1}
        )

    def _moved(self, target: QuoteStatus, **changes: object) -> QuoteCase:
        return self._changed(**changes, status=transition(self.status, target))

    def _answer(
        self, key: tuple[QuoteFindingCode, int | None], answer: FindingCorrected
    ) -> QuoteCase:
        if self.status is not QuoteStatus.RECEIVED:
            raise ConflictError(
                "a request's own findings are answered while it is received",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        found = next((f for f in self.findings if f.key == key and f.is_open), None)
        if found is None:
            raise ConflictError(
                "no such open finding",
                details={"case_id": str(self.case_id), "code": key[0].value, "line_no": key[1]},
            )
        findings = tuple(
            f.model_copy(update={"disposition": answer}) if f is found else f for f in self.findings
        )
        return self._changed(findings=findings)

    def complete_line(
        self,
        line_no: int,
        *,
        by: uuid.UUID,
        at: AwareDatetime,
        quantity: Decimal | None = None,
        needed_by: date | None = None,
        note: str | None = None,
    ) -> QuoteCase:
        """Sales types what the customer left blank, after asking in their own mail."""
        return self._answer(
            (QuoteFindingCode.RFQ_INCOMPLETE, line_no),
            FindingCorrected(by=by, at=at, quantity=quantity, needed_by=needed_by, note=note),
        )

    def confirm_customer(
        self, customer_code: str, *, by: uuid.UUID, at: AwareDatetime
    ) -> QuoteCase:
        """Sales confirms, or picks, the customer of a forwarded request."""
        return self._answer(
            (QuoteFindingCode.CUSTOMER_UNKNOWN, None),
            FindingCorrected(by=by, at=at, customer_code=customer_code),
        )

    def draft_ycbg(self) -> QuoteCase:
        return self._moved(QuoteStatus.YCBG_DRAFTED)

    def record_ycbg(self, ycbg_no: str, *, by: uuid.UUID, at: AwareDatetime) -> QuoteCase:
        """The number the ERP gave the YCBG Sales entered: what Design's reply quotes."""
        return self._moved(
            QuoteStatus.YCBG_RECORDED,
            ycbg=YcbgRecord(ycbg_no=ycbg_no, recorded_by=by, recorded_at=at),
        )

    def send_to_design(self) -> QuoteCase:
        return self._moved(QuoteStatus.SENT_TO_DESIGN)

    def record_design_reply(self, reply: DesignReply) -> QuoteCase:
        return self._moved(QuoteStatus.DESIGN_REPLIED, design_replies=(*self.design_replies, reply))

    def discuss_spec(self) -> QuoteCase:
        return self._moved(QuoteStatus.SPEC_DISCUSSION)

    def settle_spec(self) -> QuoteCase:
        """The customer agreed the specification Design replied with."""
        return self._moved(QuoteStatus.DESIGN_REPLIED)

    def decide_price(
        self, decision: PricingDecision, findings: Iterable[QuoteFinding], *, by: uuid.UUID
    ) -> QuoteCase:
        """Sales' price and the findings it raised (`price_findings`).

        ``by`` is the verified caller, and the decision must be theirs: its
        ``decided_by`` is the one person who may not approve it, so a decision
        recorded under someone else's name would let its real author approve
        their own price. From `pending_approval` or `approved` this is the
        change after submit: the document and any approval go, and the
        quotation is priced again. Every replaced decision is kept.
        """
        if decision.decided_by != by:
            raise DomainError(
                "a price decision is recorded as its actor's",
                details={"case_id": str(self.case_id), "field": "decided_by"},
            )
        raised = tuple(findings)
        if any(finding.code not in PRICE_FINDINGS for finding in raised):
            raise ValueError("a price decision raises price findings only")
        earlier = self.earlier_pricing + ((self.pricing,) if self.pricing is not None else ())
        kept = tuple(f for f in self.findings if f.code not in PRICE_FINDINGS)
        return self._moved(
            QuoteStatus.PRICED,
            pricing=decision,
            earlier_pricing=earlier,
            findings=kept + raised,
            submission=None,
            approval=None,
        )

    def submit_for_approval(
        self, document: CustomerQuoteDocument, *, by: uuid.UUID, at: AwareDatetime
    ) -> QuoteCase:
        """The document the approver is shown, stamped with its hash and the pricer."""
        transition(self.status, QuoteStatus.PENDING_APPROVAL)
        assert self.pricing is not None  # _NEEDS: a priced case holds its pricing
        return self._moved(
            QuoteStatus.PENDING_APPROVAL,
            submission=Submission(
                document=document,
                document_sha256=document.sha256(),
                priced_by=self.pricing.decided_by,
                submitted_by=by,
                submitted_at=at,
            ),
        )

    def return_to_pricer(self, actor: QuoteActor, *, at: AwareDatetime, reason: str) -> QuoteCase:
        """The approver sends the price back; the returned decision stays on record."""
        transition(self.status, QuoteStatus.RETURNED)
        by = self._approver(actor)
        returned = Return(
            returned_by=by, returned_at=at, reason=reason, case_version=self.case_version
        )
        return self._moved(QuoteStatus.RETURNED, returns=(*self.returns, returned), submission=None)

    def approve(
        self,
        actor: QuoteActor,
        *,
        at: AwareDatetime,
        document_sha256: str,
        reasons: Mapping[tuple[QuoteFindingCode, int | None], str] | None = None,
    ) -> QuoteCase:
        """The approver approves the document they were shown.

        Refused for a caller without the approve capability, for the person
        who priced it, for a document other than the
        submitted one (``document_sha256`` is the hash of what the approver
        saw), and while a blocking price finding has no reason. Accepting a
        finding is part of the approval: ``reasons`` names each blocking one,
        and `above_target_price` is acknowledged by the approval itself.
        """
        transition(self.status, QuoteStatus.APPROVED)
        by = self._approver(actor)
        submission = self.submission
        assert submission is not None  # _NEEDS: pending approval holds its submission
        if document_sha256 != submission.document_sha256:
            raise ConflictError(
                "the document changed after it was shown: approve the current one",
                details={"case_id": str(self.case_id), "case_version": self.case_version},
            )
        given = dict(reasons or {})
        price_keys = {f.key for f in self.findings if f.code in PRICE_FINDINGS}
        unknown = sorted(f"{code}:{line}" for code, line in given if (code, line) not in price_keys)
        unreasoned = sorted(
            f"{f.code}:{f.line_no}"
            for f in self.findings
            if f.code in PRICE_FINDINGS and f.blocking and f.key not in given
        )
        if unknown or unreasoned:
            raise ConflictError(
                "each blocking price finding is accepted with a reason, and only those raised",
                details={"case_id": str(self.case_id), "unknown": unknown, "missing": unreasoned},
            )
        findings = tuple(
            f.model_copy(
                update={"disposition": FindingAccepted(by=by, at=at, reason=given.get(f.key))}
            )
            if f.code in PRICE_FINDINGS
            else f
            for f in self.findings
        )
        return self._moved(
            QuoteStatus.APPROVED,
            findings=findings,
            approval=Approval(
                approved_by=by,
                approved_at=at,
                case_version=self.case_version,
                document_sha256=submission.document_sha256,
            ),
        )

    def _approver(self, actor: QuoteActor) -> uuid.UUID:
        """The approver's id, once they may approve this quote: they hold the
        approve capability (else 403) and did not decide its price (else 409)."""
        if QuoteCapability.APPROVE not in actor.capabilities:
            raise PermissionDeniedError(
                "approving or returning a quotation needs sales.quote.approve",
                details={"case_id": str(self.case_id)},
            )
        by = actor.user_id
        if self.pricing is not None and self.pricing.decided_by == by:
            raise ConflictError(
                "separation of duties: the person who decided the price cannot approve or"
                " return it (WIV-03-023 step 9)",
                details={"case_id": str(self.case_id)},
            )
        return by

    def mark_sent(self, *, by: uuid.UUID, at: AwareDatetime) -> QuoteCase:
        return self._moved(QuoteStatus.SENT, sent=Stamp(by=by, at=at))

    def record_master_list(self, *, by: uuid.UUID, at: AwareDatetime) -> QuoteCase:
        return self._moved(QuoteStatus.MASTER_LIST_RECORDED, master_list=Stamp(by=by, at=at))

    def decline_request(
        self,
        *,
        by: uuid.UUID,
        at: AwareDatetime,
        reason: DeclineReason,
        note: str | None = None,
    ) -> QuoteCase:
        return self._moved(
            QuoteStatus.DECLINED,
            decline=Decline(declined_by=by, declined_at=at, reason=reason, note=note),
        )
