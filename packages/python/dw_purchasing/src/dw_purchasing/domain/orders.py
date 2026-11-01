"""Draft purchase orders and the file Bravo imports them from (DW02 function 4).

Once a person chose a supplier per line, code drafts one purchase order per
supplier from what was chosen: the request's lines, the chosen offers' unit
prices, the supplier's name from the master data. Nothing is recorded in
Bravo by DW2: Bravo has no connection here, so a buyer imports the file
(the contract accepts a file where the ERP offers no connection, as DW1's
Bravo upload does).

Which columns the file has, their headers, in which order, the sheet's name
and how a date is written are the tenant's rule (`BravoPoLayout`), stamped on
the case when the orders are drafted: the file drawn again later is the file
drawn then, whatever the rules say by that time. The value in each column is
code's, from a fixed set of fields (`BravoField`): a layout may arrange the
fields, never invent one.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_purchasing.domain.requests import Code, Currency, Price, PurchaseRequest, Quantity
from dw_purchasing.domain.sourcing import Offer, Selection

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

BravoField = Literal[
    "po_ref",
    "pr_no",
    "order_date",
    "supplier_code",
    "supplier_name",
    "item_code",
    "description",
    "quantity",
    "unit",
    "unit_price",
    "currency",
    "amount",
    "need_by",
    "budget_code",
    "department",
]
# Excel's own limit on a sheet name: 1 to 31 characters, none of `[]:*?/\`.
SheetName = Annotated[str, Field(pattern=r"^[^\[\]:*?/\\\x00-\x1f]{1,31}$")]
# How a date is shown, in Excel's format codes.
DateFormat = Literal["dd/mm/yyyy", "yyyy-mm-dd", "mm/dd/yyyy"]


class BravoColumn(BaseModel):
    model_config = _FROZEN

    header: str = Field(min_length=1, max_length=60, pattern=r"^[^\x00-\x1f]+$")
    field: BravoField


class BravoPoLayout(BaseModel):
    """The import file's shape, as the tenant's Bravo expects it."""

    model_config = _FROZEN

    # The platform's stand-in (rules 1.4.0): a deployed DW2 drafts no order
    # with it, since the company's Bravo would not import it.
    mock: bool = False
    sheet: SheetName
    date_format: DateFormat
    columns: tuple[BravoColumn, ...] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def _headers_are_unique(self) -> Self:
        headers = [c.header for c in self.columns]
        if len(headers) != len(set(headers)):
            raise ValueError("a header repeats")
        return self


class PoLine(BaseModel):
    model_config = _FROZEN

    line_no: int = Field(ge=1)
    item_code: Code | None
    description: str
    quantity: Quantity
    unit: str
    unit_price: Price
    amount: Price
    need_by: date | None


class PoDraft(BaseModel):
    """One supplier's draft order."""

    model_config = _FROZEN

    po_ref: Code
    supplier_code: Code
    supplier_name: str
    currency: Currency
    lines: tuple[PoLine, ...] = Field(min_length=1)
    total: Price


class PoRound(BaseModel):
    """The orders drafted for a case, and the layout their file is drawn with."""

    model_config = _FROZEN

    order_date: date
    drafted_by: uuid.UUID
    drafted_at: AwareDatetime
    orders: tuple[PoDraft, ...] = Field(min_length=1)
    layout: BravoPoLayout
    # The rules the layout came from: what the file says it was drawn under.
    rules_ref: str


def draft_orders(
    request: PurchaseRequest,
    selection: Selection,
    offers: Sequence[Offer],
    supplier_names: Mapping[str, str],
) -> tuple[PoDraft, ...]:
    """One order per chosen supplier, by supplier code, its lines in the
    request's order at the chosen offer's unit price."""
    lines = {line.line_no: line for line in request.lines}
    latest: dict[tuple[str, int], Offer] = {}
    for offer in sorted(offers, key=lambda o: o.recorded_at):
        latest[(offer.supplier_code, offer.line_no)] = offer
    by_supplier: dict[str, list[PoLine]] = {}
    for choice in sorted(selection.choices, key=lambda c: c.line_no):
        line = lines[choice.line_no]
        offer = latest[(choice.supplier_code, choice.line_no)]
        by_supplier.setdefault(choice.supplier_code, []).append(
            PoLine(
                line_no=line.line_no,
                item_code=line.item_code,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=offer.unit_price,
                amount=offer.unit_price * line.quantity,
                need_by=line.need_by or request.need_by,
            )
        )
    return tuple(
        PoDraft(
            po_ref=f"{request.pr_no}-{index:02d}",
            supplier_code=code,
            supplier_name=supplier_names[code],
            currency=selection.currency,
            lines=tuple(po_lines),
            total=sum((line.amount for line in po_lines), Decimal(0)),
        )
        for index, (code, po_lines) in enumerate(sorted(by_supplier.items()), start=1)
    )


Cell = str | Decimal | date | None


def bravo_rows(round_: PoRound, request: PurchaseRequest) -> list[list[Cell]]:
    """The file's rows: the headers, then one row per order line, each column
    the field its layout names."""

    def value(field: BravoField, order: PoDraft, line: PoLine) -> Cell:
        match field:
            case "po_ref":
                return order.po_ref
            case "pr_no":
                return request.pr_no
            case "order_date":
                return round_.order_date
            case "supplier_code":
                return order.supplier_code
            case "supplier_name":
                return order.supplier_name
            case "item_code":
                return line.item_code
            case "description":
                return line.description
            case "quantity":
                return line.quantity
            case "unit":
                return line.unit
            case "unit_price":
                return line.unit_price
            case "currency":
                return order.currency
            case "amount":
                return line.amount
            case "need_by":
                return line.need_by
            case "budget_code":
                return request.budget_code
            case "department":
                return request.department

    columns = round_.layout.columns
    rows: list[list[Cell]] = [[c.header for c in columns]]
    for order in round_.orders:
        for line in order.lines:
            rows.append([value(c.field, order, line) for c in columns])
    return rows
