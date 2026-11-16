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
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_platform.domain.messages import EmailAddress, is_domain, is_email_address

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
# Text as a customer printed it: one line, no control characters, no padding.
# Raw on purpose: a code outside the convert list's alphabet is still what the
# PO says, and it is reported as unmapped rather than refused as unreadable.
_PRINTED_END = r"[^\s\x00-\x1f\x7f]"
PrintedText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=rf"^{_PRINTED_END}(?:[^\x00-\x1f\x7f]*{_PRINTED_END})?$",
    ),
]
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
    """Export-control status. DW1 decides nothing on it: a customer without a
    valid NOC, ESF or denial-list check raises `missing_noc_esf`, which holds
    the order's confirmation until the export-control PIC accepts it.

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
# The group Bravo files a customer under ("Nhóm mẹ" in its customer list,
# B05): one PRV sells to directly, a temporary code (TEMPSALES) of one, or an
# indirect customer, the end user a direct customer buys for.
CustomerGroup = Literal["direct", "temporary", "indirect"]
# How a confirmed order goes back: an email draft, or the customer's own portal.
ConfirmationChannel = Literal["email", "portal"]
# The kind of sales order Bravo files a customer's orders as: the set its
# "Import Sales Order" template prints in its own header (B41, dw_sales
# ticket 02), spelled as Bravo spells them.
OrderType = Literal["Mass", "Returned", "Sample", "SampleFee"]
# A delivery value as the customer's sales orders carry it (delivery term,
# mode, destination, shipment type): free text, since no list of Bravo's own
# values has been seen, only the few the filled files use.
OrderTerm = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")]


class Customer(BaseModel):
    model_config = _FROZEN

    code: CustomerCode
    # As the customer's documents print it. A document forwarded by a Sales
    # address names its buyer, and that name is matched against this one.
    name: Name
    # The domains a sender is recognised by: the customer's own. Empty where
    # its people write from a domain other customers share (the group's, B05:
    # 132 customers), which recognises nobody; the address decides there
    # (dw_sales ticket 20), never the domain.
    email_domains: tuple[str, ...] = ()
    # Who a draft may be addressed to. The only source of customer recipients.
    # On any domain: a contact on a shared domain is still this customer's.
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
    # Bravo's group for the customer; None where the list does not say. An
    # indirect customer has no convert-list rows of its own (B04 keys on the
    # direct customer), so the import refuses one named there.
    group: CustomerGroup | None = None
    # What every sales order of this customer carries in Bravo, the same on
    # every order seen (B41): a column of the Bravo upload file may read them
    # (`sales_bravo_upload`, a `customer` column). None where the list does
    # not say, and the column is then left blank for the person who pastes.
    order_type: OrderType | None = None
    delivery_term: OrderTerm | None = None
    delivery_mode: OrderTerm | None = None
    destination: OrderTerm | None = None
    shipment_type: OrderTerm | None = None

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


class ItemAttributes(BaseModel):
    """What a cable is made of: what a PO describes when its code is unknown.

    An attribute is None when the source's value is outside DW1's vocabulary
    (module docstring), or the source does not say: Bravo's item master holds
    none of them, and they are read from the item's name
    (`item_names.name_attributes`). Required all the same, so a record that
    forgets one is refused rather than read as unmapped. None never fits a
    stated value (`StatedAttributes.fits`).
    """

    model_config = _FROZEN

    cores: int | None = Field(ge=1, le=100)
    stranding: Stranding | None
    # ``AWG24`` or a cross-section such as ``0.5mm2``: one spelling per size.
    gauge: str | None = Field(pattern=r"^(AWG\d{1,2}|\d{1,2}\.\d{1,2}mm2)$")
    conductor: Conductor | None
    shield: Shield | None
    colour: Colour | None
    packaging: Packaging | None
    # The Design specification the item is built to. Several items (the same
    # cable on a reel and on a drum) may share one.
    spec_no: DocumentNo | None
    # The wire standard its name states (``UL1007``), or None.
    standard: str | None = Field(default=None, pattern=r"^UL\d{3,5}$")


def known_uom(printed: str) -> Uom | None:
    """DW1's word for a unit as a PO or the item master prints it, or None
    when it has none."""
    folded = printed.strip().casefold()
    return next((u for u in get_args(Uom) if u.casefold() == folded), None)


class UnitConversion(BaseModel):
    """A unit Bravo also counts the item in, and its factor, as Bravo writes
    them ("Đvt quy đổi", "Hệ số quy đổi"). Kept, not applied: DW1 converts
    no quantity (a second unit is a rule to decide, `Uom`)."""

    model_config = _FROZEN

    unit: str = Field(min_length=1, max_length=16, pattern=r"^[^\s\x00-\x1f\x7f]+$")
    factor: Decimal = Field(gt=0)


_Text = Annotated[str, Field(min_length=1, max_length=500, pattern=r"^[^\x00-\x1f\x7f]+$")]


class Item(BaseModel):
    """One item of the item master. The fields after ``standard_lead_time_days``
    are Bravo's own (B06, ticket 36), None where the source does not have
    them: the mock's records, and DW's own template."""

    model_config = _FROZEN

    prv_code: PrvCode
    family: ItemFamily | None
    attributes: ItemAttributes
    # DW1's word for the item's unit, read from ``unit``: None where DW1 has
    # none, and every PO line for the item disagrees with it (`uom_mismatch`).
    uom: Uom | None
    # None where the list does not say: the line's MOQ is then the
    # quotation's, or not checked (`LineBasis.checks_run`).
    moq: Decimal | None = Field(gt=0)
    # The length one reel, coil or drum holds; an order is a whole number of
    # them. None where unknown (Bravo writes 0): the pack is not checked.
    pack_multiple: Decimal | None = Field(gt=0)
    # None where the list does not say: the lead time is then the
    # quotation's, or not checked.
    standard_lead_time_days: int | None = Field(gt=0, le=365)
    # Bravo's name for it ("Tên vật tư"), whose spec string the attributes
    # are read from.
    name: _Text | None = None
    # The unit as Bravo writes it ("m", "Pcs", "kg"); DW1's own word where the
    # source wrote only that.
    unit: Annotated[str, Field(min_length=1, max_length=16)] | None = None
    conversions: tuple[UnitConversion, ...] = ()
    # Bravo's own words, shown to Sales, not interpreted: how it is packed
    # ("Coil", "P-30K", a note), its category ("HK", "CA"), its base-price code
    # and its specification numbers.
    packaging_style: _Text | None = None
    category: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    bp_code: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    specification: _Text | None = None

    @model_validator(mode="before")
    @classmethod
    def _unit_names_the_uom(cls, data: Any) -> Any:
        """``unit`` is the owner, ``uom`` is DW1's word for it: a record
        stating only one of them reads the other from it."""
        if not isinstance(data, dict):
            return data
        unit, uom = data.get("unit"), data.get("uom")
        if unit is not None and "uom" not in data:
            return {**data, "uom": known_uom(str(unit))}
        if unit is None and uom is not None:
            return {**data, "unit": uom}
        return data

    @model_validator(mode="after")
    def _uom_is_the_units(self) -> Self:
        if self.unit is not None and known_uom(self.unit) != self.uom:
            raise ValueError(f"item {self.prv_code}: uom is not its unit's")
        return self


ConvertState = Literal["approved", "waiting"]


class ConvertEntry(BaseModel):
    """One row of the convert list: a customer's code for one of our items.

    The customer's side is what Bravo's list holds as the converting
    description (B04): their part number, or their words for the item, as a
    PO prints it. Keyed per direct customer: the same words name different
    items at different customers (66 do in B04), so one customer's row never
    answers another's line."""

    model_config = _FROZEN

    customer_code: CustomerCode
    customer_item_code: PrintedText
    prv_code: PrvCode
    # Where the row stands in Bravo's approval (ticket 04): only an approved
    # one answers a PO line; one waiting in states 1 or 2 is held, unused.
    bravo_state: ConvertState = "approved"


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


class BasePrice(BaseModel):
    """One BP of Bravo's "Danh mục Base price" (Box B21, dw_sales ticket 11):
    what Design prices an item at, per BP unit, at the LME of the BP. The
    cost split is internal: it reaches a price reader only, as every amount
    here does (`catalog_imports._PRICED`)."""

    model_config = _FROZEN

    bp_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,31}$")
    bp_date: date
    description: str = Field(min_length=1, max_length=500)
    # The unit the BP is priced in (``km``) and how many standard units one
    # is (1,000 m), as Bravo states them.
    bp_unit: str = Field(min_length=1, max_length=16)
    convert_rate: Decimal = Field(gt=0)
    std_unit: str | None = Field(default=None, max_length=16)
    specification: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=32)
    # Copper, kg per BP unit.
    copper_kg: Decimal | None = Field(default=None, ge=0)
    # USD per BP unit.
    base_price: Decimal = Field(ge=0)
    lead_time_weeks: int | None = Field(default=None, ge=0, le=520)
    moq: Decimal | None = Field(default=None, ge=0)
    lme_of_bp: Decimal | None = Field(default=None, gt=0)
    mr_percent: Decimal | None = Field(default=None, ge=0)
    material_cost: Decimal | None = Field(default=None, ge=0)
    variable_cost: Decimal | None = Field(default=None, ge=0)
    fixed_cost: Decimal | None = Field(default=None, ge=0)


class BravoQuotation(BaseModel):
    """One row of Bravo's "Master list báo giá" (Box B07, dw_sales ticket
    12): one quotation line, keyed by Bravo's own row id (RowIdSQ), with the
    BP it was priced from and the centre price at the quotation's LME. Read
    only; what a price check does with it waits on dw_sales ADR 0008."""

    model_config = _FROZEN

    row_id: str = Field(min_length=1, max_length=64)
    quote_no: str = Field(min_length=1, max_length=64)
    line_no: int | None = Field(default=None, ge=0, le=9999)
    quotation_date: date
    valid_date: date | None = None
    quote_class: str | None = Field(default=None, max_length=32)
    delivery_term: str | None = Field(default=None, max_length=64)
    delivery_mode: str | None = Field(default=None, max_length=64)
    destination: str | None = Field(default=None, max_length=128)
    direct_customer_code: str = Field(min_length=1, max_length=32)
    group_customer: str | None = Field(default=None, max_length=32)
    indirect_customer_code: str | None = Field(default=None, max_length=32)
    customer_description: str | None = Field(default=None, max_length=500)
    bp_code: str | None = Field(default=None, max_length=32)
    moq: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=16)
    copper_kg: Decimal | None = Field(default=None, ge=0)
    center_price: Decimal | None = Field(default=None, ge=0)
    lme: Decimal | None = Field(default=None, ge=0)
    # As Bravo holds it (B07 also has "JYP"): read, not corrected.
    currency: str | None = Field(default=None, max_length=8)
    usd_rate: Decimal | None = Field(default=None, gt=0)
    change: str | None = Field(default=None, max_length=16)


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
