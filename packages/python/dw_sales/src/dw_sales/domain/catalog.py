"""The master data a Sales decision reads: customers, items, the convert list,
quotations, the monthly LME copper price, and what the ERP (Bravo) already
holds: its sales orders and its open quote requests (YCBG).

Read-only in this context. These facts are owned by the company's ERP and its
shared files and reach the context through `SalesCatalogPort`; nothing here is
copied into the context's own tables. What this module owns is what a valid
record looks like, and the few rules that are part of a record's meaning
(when a quotation is valid, which LME prices a band covers, which fiscal year
a day falls in), so that every reader applies the same rule.

**The vocabularies are DW1's, not the source's.** `Uom` and the attribute
`Literal`s are the words DW1 can match a PO description on, and the mock's
records are written in them. A source adapter (Bravo, ticket 12) maps its own
values into them through an anti-corruption layer. A value it cannot map is
``None`` on the record: an unmapped attribute that no stated attribute ever
fits, or an item unit that every PO line for the item disagrees with
(`uom_mismatch`). Never a record that fails to load: one unknown colour in the
ERP must not take the whole catalogue down.

Validation errors name the record and the field, never the value (spec
decision 8): a contact address or a price in an error message is a customer's
data in a log.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_sales.domain.messages import EmailAddress, is_domain, is_email_address

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Language = Literal["vi", "en", "ja"]
ItemFamily = Literal["hook_up_wire", "multi_core_cable"]
Shield = Literal["none", "foil", "braid"]
# "single" is lõi đơn (one solid conductor), "stranded" is lõi xoắn.
Stranding = Literal["single", "stranded"]
Conductor = Literal["bare_copper", "tinned_copper"]
Colour = Literal[
    "black", "white", "red", "blue", "green", "yellow", "grey", "brown", "orange", "violet"
]
Packaging = Literal["reel", "coil", "drum"]
# Every item, quotation and order line in this slice is counted in metres. A
# second unit is a conversion rule to decide, not a value to accept quietly.
Uom = Literal["m"]
Currency = Literal["USD", "VND", "JPY"]

CustomerCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$")]
PrvCode = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,31}$")]
# A customer's own part number: their alphabet, not ours.
CustomerItemCode = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,47}$")]
DocumentNo = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9/-]{1,31}$")]
Name = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


def fiscal_year(day: date, *, start_month: int) -> int:
    """The fiscal year ``day`` falls in, named by the calendar year it starts in.

    ``start_month`` is the policy's (`sales_order_rules.fiscal_year_start_month`):
    with April, FY2026 is 2026-04-01 .. 2027-03-31. No default, because a
    default here would be a second copy of the policy's value.
    """
    if not 1 <= start_month <= 12:
        raise ValueError("start_month is not a month")
    return day.year if day.month >= start_month else day.year - 1


def month_key(day: date) -> str:
    """``YYYY-MM`` of ``day``: the key `LmeMonth` is stored and looked up by."""
    return f"{day.year:04d}-{day.month:02d}"


class Compliance(BaseModel):
    """Export-control status. DW1 warns on it and decides nothing.

    NOC is confirmed once per customer; the export screening form (ESF) is
    renewed every fiscal year, so it is recorded by the year it covers.
    """

    model_config = _FROZEN

    noc_confirmed: bool
    esf_fiscal_year: int | None = Field(default=None, ge=2000, le=2100)
    # When the customer was last screened against the denial lists. None when
    # never: an unscreened customer is flagged, not presumed clean.
    denial_list_checked_on: date | None = None


# A temporary code is issued before the customer is registered properly
# (WIV-03-031); its orders are flagged for Sales.
CustomerStatus = Literal["official", "temporary"]
# How a confirmed order goes back: an email draft, or the customer's own portal.
ConfirmationChannel = Literal["email", "portal"]


class Customer(BaseModel):
    model_config = _FROZEN

    code: CustomerCode
    # As the customer's documents print it. A document forwarded by a Sales
    # address names its buyer, and that name is matched against this one.
    name: Name
    # The domains a sender is recognised by. A contact outside them would be a
    # recipient nobody could match back to this customer.
    email_domains: tuple[str, ...] = Field(min_length=1)
    # Who a draft may be addressed to. The only source of customer recipients.
    contacts: tuple[EmailAddress, ...] = Field(min_length=1)
    language: Language
    intra_group: bool
    compliance: Compliance
    status: CustomerStatus
    confirmation_channel: ConfirmationChannel
    # The sign-in email of the Sales PIC a new case is assigned to. Stamped on
    # the case when it is created (ticket 04), never looked up again. None when
    # the customer has none: the case is then every PIC's to pick up. Required
    # all the same, so a record that forgets it is refused, not unassigned.
    sales_pic: str | None = Field(max_length=254)

    @field_validator("email_domains")
    @classmethod
    def _domains_are_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, domain in enumerate(value):
            if not is_domain(domain):
                raise ValueError(f"email_domains[{index}] is not a lowercase domain")
        if len(set(value)) != len(value):
            raise ValueError("email_domains repeat")
        return value

    @field_validator("sales_pic")
    @classmethod
    def _pic_is_an_address(cls, value: str | None) -> str | None:
        if value is not None and not is_email_address(value):
            raise ValueError("sales_pic is not an email address")
        return value

    @model_validator(mode="after")
    def _contacts_use_its_domains(self) -> Self:
        for index, contact in enumerate(self.contacts):
            if contact.domain not in self.email_domains:
                raise ValueError(f"customer {self.code}: contacts[{index}] is outside its domains")
        return self


class ItemAttributes(BaseModel):
    """What a cable is made of: what a PO describes when its code is unknown.

    An attribute is None when the source's value is outside DW1's vocabulary
    (module docstring). Required all the same, so a record that forgets one is
    refused rather than read as unmapped.
    """

    model_config = _FROZEN

    cores: int = Field(ge=1, le=100)
    stranding: Stranding | None
    # ``AWG24`` or a cross-section such as ``0.5mm2``: one spelling per size.
    gauge: str = Field(pattern=r"^(AWG\d{1,2}|\d{1,2}\.\d{1,2}mm2)$")
    conductor: Conductor | None
    shield: Shield | None
    colour: Colour | None
    packaging: Packaging | None
    # The Design specification the item is built to. Several items (the same
    # cable on a reel and on a drum) may share one.
    spec_no: DocumentNo


class Item(BaseModel):
    model_config = _FROZEN

    prv_code: PrvCode
    family: ItemFamily | None
    attributes: ItemAttributes
    # None: a unit DW1 has no word for. Every PO line for the item disagrees
    # with it (`uom_mismatch`).
    uom: Uom | None
    moq: Decimal = Field(gt=0)
    # The length one reel, coil or drum holds; an order is a whole number of them.
    pack_multiple: Decimal = Field(gt=0)
    standard_lead_time_days: int = Field(gt=0, le=365)


class ConvertEntry(BaseModel):
    """One row of the convert list: a customer's code for one of our items."""

    model_config = _FROZEN

    customer_code: CustomerCode
    customer_item_code: CustomerItemCode
    prv_code: PrvCode


class FixedCopper(BaseModel):
    """The price does not move with copper."""

    model_config = _FROZEN

    kind: Literal["fixed"] = "fixed"


class LmeBand(BaseModel):
    """The price holds while LME copper is in ``[low, high)`` USD per tonne."""

    model_config = _FROZEN

    kind: Literal["lme_band"] = "lme_band"
    low_usd_per_tonne: Decimal = Field(gt=0)
    high_usd_per_tonne: Decimal

    @model_validator(mode="after")
    def _band_is_not_empty(self) -> Self:
        if self.high_usd_per_tonne <= self.low_usd_per_tonne:
            raise ValueError("an LME band needs high > low")
        return self

    def contains(self, usd_per_tonne: Decimal) -> bool:
        """Half-open, so a price on a boundary belongs to exactly one band."""
        return self.low_usd_per_tonne <= usd_per_tonne < self.high_usd_per_tonne


CopperBasis = Annotated[FixedCopper | LmeBand, Field(discriminator="kind")]


class Quotation(BaseModel):
    """A price quoted to one customer for one item, for a period."""

    model_config = _FROZEN

    quote_no: DocumentNo
    customer_code: CustomerCode
    prv_code: PrvCode
    unit_price: Decimal = Field(gt=0)
    currency: Currency
    uom: Uom | None
    moq: Decimal = Field(gt=0)
    lead_time_days: int = Field(gt=0, le=365)
    copper_basis: CopperBasis
    valid_from: date
    valid_to: date

    @model_validator(mode="after")
    def _period_is_not_empty(self) -> Self:
        if self.valid_to < self.valid_from:
            raise ValueError(f"quotation {self.quote_no}: valid_to ends before it starts")
        return self

    def is_valid_on(self, day: date) -> bool:
        """Both ends inclusive: a quotation valid to 31 December covers that day."""
        return self.valid_from <= day <= self.valid_to


class LmeMonth(BaseModel):
    """The LME copper price that applies to one month, in USD per tonne."""

    model_config = _FROZEN

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    usd_per_tonne: Decimal = Field(gt=0)


# ------------------------------------------------- what the ERP already holds --


class BravoOrderLine(BaseModel):
    """One line of a sales order as entered in the ERP, in the item's own unit."""

    model_config = _FROZEN

    line_no: int = Field(ge=1, le=9999)
    prv_code: PrvCode
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    # The date the line was entered for: the PO's requested date unless Sales
    # agreed another.
    delivery_date: date


class BravoOrder(BaseModel):
    """A sales order in the ERP's export, with the customer PO it was keyed from.

    What makes a PO already keyed by hand a duplicate, and a revision of it a
    revision with a base. Also the order history a price is weighed against,
    and the yearly screening's evidence.
    """

    model_config = _FROZEN

    so_no: DocumentNo
    customer_code: CustomerCode
    po_no: DocumentNo
    po_revision: int = Field(ge=0)
    order_date: date
    currency: Currency
    lines: tuple[BravoOrderLine, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _lines_are_distinct(self) -> Self:
        numbers = [line.line_no for line in self.lines]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"order {self.so_no}: lines repeat a line_no")
        return self


class OpenYcbg(BaseModel):
    """A quote request (YCBG) the ERP holds open.

    It stays open until its quotation is issued, so it is still listed after
    Design has replied. Design's reply quotes the YCBG number, and only that
    number matches the reply to the customer's request.
    """

    model_config = _FROZEN

    ycbg_no: DocumentNo
    customer_code: CustomerCode
    # The customer's own number for the request the YCBG was raised from.
    rfq_no: DocumentNo
    issued_on: date


def customers_named(customers: Sequence[Customer], printed: str) -> list[Customer]:
    """The customers whose name equals a printed buyer name after NFKC
    normalisation, case folding and whitespace collapsing: exactly, never the
    nearest. One rule for order intake and quotation alike."""
    wanted = _folded(printed)
    return [customer for customer in customers if _folded(customer.name) == wanted]


def _folded(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())
