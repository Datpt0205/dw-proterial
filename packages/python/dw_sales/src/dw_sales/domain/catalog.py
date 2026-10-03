"""The master data a Sales decision reads: customers, items, the convert list,
quotations and the monthly LME copper price.

Read-only in this context. These facts are owned by the company's ERP and its
shared files and reach the context through `SalesCatalogPort`; nothing here is
copied into the context's own tables. What this module owns is what a valid
record looks like, and the few rules that are part of a record's meaning
(when a quotation is valid, which LME prices a band covers, which fiscal year
a day falls in), so that every reader applies the same rule.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_sales.domain.messages import EmailAddress, is_domain

_FROZEN = ConfigDict(frozen=True, extra="forbid")

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

# The fiscal year runs April to March and is named by the calendar year it
# starts in: FY2026 is 2026-04-01 .. 2027-03-31.
FISCAL_YEAR_START_MONTH = 4


def fiscal_year(day: date) -> int:
    """The fiscal year ``day`` falls in."""
    return day.year if day.month >= FISCAL_YEAR_START_MONTH else day.year - 1


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


class Customer(BaseModel):
    model_config = _FROZEN

    code: CustomerCode
    name: Name
    # The domains a sender is recognised by. A contact outside them would be a
    # recipient nobody could match back to this customer.
    email_domains: tuple[str, ...] = Field(min_length=1)
    # Who a draft may be addressed to. The only source of customer recipients.
    contacts: tuple[EmailAddress, ...] = Field(min_length=1)
    language: Language
    intra_group: bool
    compliance: Compliance

    @field_validator("email_domains")
    @classmethod
    def _domains_are_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for domain in value:
            if not is_domain(domain):
                raise ValueError(f"not a lowercase domain: {domain!r}")
        if len(set(value)) != len(value):
            raise ValueError("email domains repeat")
        return value

    @model_validator(mode="after")
    def _contacts_use_its_domains(self) -> Self:
        for contact in self.contacts:
            if contact.domain not in self.email_domains:
                raise ValueError(
                    f"contact {contact.address} is outside {self.code}'s domains"
                    f" {list(self.email_domains)}"
                )
        return self


class ItemAttributes(BaseModel):
    """What a cable is made of: what a PO describes when its code is unknown."""

    model_config = _FROZEN

    cores: int = Field(ge=1, le=100)
    stranding: Stranding
    # ``AWG24`` or a cross-section such as ``0.5mm2``: one spelling per size.
    gauge: str = Field(pattern=r"^(AWG\d{1,2}|\d{1,2}\.\d{1,2}mm2)$")
    conductor: Conductor
    shield: Shield
    colour: Colour
    packaging: Packaging
    # The Design specification the item is built to. Several items (the same
    # cable on a reel and on a drum) may share one.
    spec_no: DocumentNo


class Item(BaseModel):
    model_config = _FROZEN

    prv_code: PrvCode
    family: ItemFamily
    attributes: ItemAttributes
    uom: Uom
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
    uom: Uom
    moq: Decimal = Field(gt=0)
    lead_time_days: int = Field(gt=0, le=365)
    copper_basis: CopperBasis
    valid_from: date
    valid_to: date

    @model_validator(mode="after")
    def _period_is_not_empty(self) -> Self:
        if self.valid_to < self.valid_from:
            raise ValueError(f"quotation {self.quote_no} ends before it starts")
        return self

    def is_valid_on(self, day: date) -> bool:
        """Both ends inclusive: a quotation valid to 31 December covers that day."""
        return self.valid_from <= day <= self.valid_to


class LmeMonth(BaseModel):
    """The LME copper price that applies to one month, in USD per tonne."""

    model_config = _FROZEN

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    usd_per_tonne: Decimal = Field(gt=0)
