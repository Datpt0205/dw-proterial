"""A sales order read back from Bravo after the paste, compared with what DW1
prepared (dw_sales ticket 03, ADR 0026).

Sales imports the paste sheet DW1 prepared through Bravo's "Import / Cập nhật
đơn đặt hàng bán", which runs with "Bỏ qua các lỗi…" and "Không ghi nhật
ký…" ticked (11-16): a row Bravo refuses is skipped and nothing records it.
An import that finished proves nothing, so DW1 reads the order back and
compares it, row by row, with the rows it prepared (`compare`). The PIC still
records the entry (human-in-command); the comparison is what a cross-checker
reads instead of the PIC's word.

What is compared is what a row of the paste sheet states and Bravo keeps:
the item code, the quantity, the unit price as printed on the PO, and the
date the customer asked for, per PO line, a row per delivery in the order
the sheet lists them. A line PC cancelled whole is a row of nothing on the
sheet and expects no row in Bravo. A PO is compared under one sales order
only: Bravo's B02 export holds POs under two and four SOs (a revision keyed
again, Q-B6), so which of them the paste made is not this module's guess;
the caller sends such a PO to Sales uncompared.

Nothing here reads a file or knows where Bravo's rows came from: the
vendor's API (R10) once it exists, the export of "Customer order information
(Form 1)" a person uploaded until then.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_PRINTED = r"^[!-~]{1,64}$"

SoField = Literal[
    "missing_row",
    "extra_row",
    "item_code",
    "quantity",
    "unit_price",
    "requested_date",
    "confirmed_date",
]


class BravoSoRow(BaseModel):
    """One row of a sales order as Bravo holds it."""

    model_config = _FROZEN

    # Where it was read: the export's row, or the API's order.
    row: int = Field(ge=1)
    so_no: str = Field(pattern=_PRINTED)
    customer_code: str = Field(pattern=_PRINTED)
    po_no: str = Field(min_length=1, max_length=64)
    po_line: int = Field(ge=1, le=99999)
    item_code: str | None = Field(default=None, max_length=64)
    quantity: Decimal
    # As the PO prints it, in its currency ("Original Price").
    unit_price: Decimal | None = None
    requested_date: date | None = None
    # "XN giao hàng" (`EstimatedTimeDelivery`): read through the gateway
    # (ticket 51); the Form 1 export does not carry it.
    confirmed_date: date | None = None


class BravoSalesOrder(BaseModel):
    """One customer PO's rows in Bravo, in the order Bravo lists them."""

    model_config = _FROZEN

    customer_code: str = Field(pattern=_PRINTED)
    po_no: str = Field(min_length=1, max_length=64)
    rows: tuple[BravoSoRow, ...] = Field(min_length=1)

    @property
    def so_numbers(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(row.so_no for row in self.rows))

    @property
    def so_no(self) -> str | None:
        """The one sales order the PO is under; None when it is under several."""
        numbers = self.so_numbers
        return numbers[0] if len(numbers) == 1 else None


class PreparedRow(BaseModel):
    """One row of the paste sheet DW1 prepared, as it was approved."""

    model_config = _FROZEN

    po_no: str = Field(min_length=1, max_length=64)
    line_no: int = Field(ge=1)
    prv_code: str
    quantity: Decimal
    unit_price: Decimal
    requested_date: date | None
    # The confirmed date the row carries (PC's, ticket 07), if any.
    confirmed_date: date | None = None


class SoDifference(BaseModel):
    """Where Bravo's order is not what was prepared. ``expected`` and
    ``actual`` are the values as printed; a unit price's are shown only to
    those who may read prices (the view's concern)."""

    model_config = _FROZEN

    po_no: str = Field(min_length=1, max_length=64)
    line_no: int
    field: SoField
    expected: str | None = Field(default=None, max_length=200)
    actual: str | None = Field(default=None, max_length=200)
    # The export's row it was read from, where there is one.
    row: int | None = None


def _plain(number: Decimal) -> str:
    return format(number.normalize(), "f")


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return _plain(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _row(prepared: PreparedRow, bravo: BravoSoRow, *, confirmed_dates: bool) -> list[SoDifference]:
    found: list[SoDifference] = []

    def differs(field: SoField, expected: object, actual: object) -> None:
        if expected != actual:
            found.append(
                SoDifference(
                    po_no=prepared.po_no,
                    line_no=prepared.line_no,
                    field=field,
                    expected=_text(expected),
                    actual=_text(actual),
                    row=bravo.row,
                )
            )

    differs("item_code", prepared.prv_code, bravo.item_code)
    differs("quantity", prepared.quantity, bravo.quantity)
    differs("unit_price", prepared.unit_price, bravo.unit_price)
    if prepared.requested_date is not None:
        differs("requested_date", prepared.requested_date, bravo.requested_date)
    # Bravo clears "XN giao hàng" it finds earlier than the SO's DocDate
    # (ticket 51): a confirmed date the row carried and Bravo does not hold.
    if confirmed_dates and prepared.confirmed_date is not None:
        differs("confirmed_date", prepared.confirmed_date, bravo.confirmed_date)
    return found


def compare(
    prepared: Sequence[PreparedRow], order: BravoSalesOrder, *, confirmed_dates: bool = False
) -> tuple[SoDifference, ...]:
    """Every difference between the rows prepared for ``order``'s PO and the
    rows Bravo holds for it (module docstring), by PO line, in line order:
    empty when Bravo holds exactly what was prepared. ``confirmed_dates``:
    the source read Bravo's confirmed dates (the gateway), so a row's is
    compared too. Raises ValueError for an order under several sales
    orders: it is not compared."""
    if order.so_no is None:
        raise ValueError("a PO under several sales orders is not compared")
    found: list[SoDifference] = []
    wanted = [row for row in prepared if row.po_no == order.po_no and row.quantity != 0]
    lines = sorted({row.line_no for row in wanted} | {row.po_line for row in order.rows})
    for line in lines:
        mine = [row for row in wanted if row.line_no == line]
        held = [row for row in order.rows if row.po_line == line]
        for prepared_row, bravo_row in zip(mine, held, strict=False):
            found.extend(_row(prepared_row, bravo_row, confirmed_dates=confirmed_dates))
        found.extend(
            SoDifference(
                po_no=order.po_no,
                line_no=line,
                field="missing_row",
                expected=_text(row.quantity),
            )
            for row in mine[len(held) :]
        )
        found.extend(
            SoDifference(
                po_no=order.po_no,
                line_no=line,
                field="extra_row",
                actual=_text(row.quantity),
                row=row.row,
            )
            for row in held[len(mine) :]
        )
    return tuple(found)
