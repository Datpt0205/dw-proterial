"""An order after it is drafted (DW02 function 5).

A buyer imports the drafted orders into Bravo (function 4); from then on DW2
follows each order by its `po_ref`:

- **Bravo's number** for it, typed by the buyer: Bravo has no connection
  here, so nothing reads it back on its own.
- **The supplier's confirmation**, read from the supplier's mail, held to the
  order line by line (`differences`): the quantity, the unit price and the
  delivery date. A confirmation with no difference is accepted as it is; one
  with differences waits for a buyer, who sees each one.
- **What arrived** (`Receipt`), recorded by a buyer; a line is due once its
  date has passed and less than ordered has arrived (`due_lines`). Its date
  is the one the supplier confirmed, else the order's need-by date.

Every value compared is code's: the model only points at where the mail
states it (`domain.mail_reading`'s rule, ADR 0005 as DW2 applies it).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_purchasing.domain.orders import PoDraft
from dw_purchasing.domain.requests import Code, Price, Quantity

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

DifferenceField = Literal["quantity", "unit_price", "delivery_on", "missing", "not_ordered"]


class ConfirmedLine(BaseModel):
    """One line as the supplier confirmed it; None where the mail says
    nothing of that value."""

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    quantity: Quantity | None = None
    unit_price: Price | None = None
    delivery_on: date | None = None


class Difference(BaseModel):
    """Where a confirmation and its order part, as text a buyer reads."""

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    field: DifferenceField
    ordered: str | None
    confirmed: str | None


class Confirmation(BaseModel):
    """A supplier's confirmation of one order, read from one mail."""

    model_config = _FROZEN

    source_ref: str = Field(pattern=r"^[!-~]{1,512}$")
    lines: tuple[ConfirmedLine, ...] = Field(min_length=1)
    differences: tuple[Difference, ...]
    read_by: uuid.UUID
    read_at: AwareDatetime
    # Who accepted it: DW2's account when it held no difference and the step
    # runs on its own, else the buyer who pressed accept.
    accepted_by: uuid.UUID | None = None
    accepted_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _accepted_is_who_and_when(self) -> Self:
        if (self.accepted_by is None) != (self.accepted_at is None):
            raise ValueError("an acceptance names who and when")
        return self


class Receipt(BaseModel):
    """Goods of one line that arrived, as a buyer recorded them."""

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    quantity: Quantity
    received_on: date
    recorded_by: uuid.UUID
    recorded_at: AwareDatetime


class OrderTracking(BaseModel):
    """What happened to one drafted order, by its `po_ref`."""

    model_config = _FROZEN

    po_ref: Code
    bravo_no: Code | None = None
    bravo_by: uuid.UUID | None = None
    bravo_at: AwareDatetime | None = None
    confirmation: Confirmation | None = None
    receipts: tuple[Receipt, ...] = ()

    @model_validator(mode="after")
    def _bravo_s_number_is_stamped(self) -> Self:
        stamped = (self.bravo_by is not None, self.bravo_at is not None)
        if stamped != (self.bravo_no is not None,) * 2:
            raise ValueError("Bravo's number names who typed it, and when")
        return self


def _text(value: Decimal | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else format(value.normalize(), "f")


def differences(order: PoDraft, lines: Sequence[ConfirmedLine]) -> tuple[Difference, ...]:
    """Each place ``lines`` part from ``order``: a quantity or unit price
    other than ordered, a date later than the line is needed, a line not
    confirmed, a line the order does not hold. Ordered by line."""
    confirmed = {line.line_no: line for line in lines}
    found: list[Difference] = []
    for line in order.lines:
        got = confirmed.get(line.line_no)
        if got is None:
            found.append(
                Difference(
                    line_no=line.line_no,
                    field="missing",
                    ordered=_text(line.quantity),
                    confirmed=None,
                )
            )
            continue
        if got.quantity is not None and got.quantity != line.quantity:
            found.append(
                Difference(
                    line_no=line.line_no,
                    field="quantity",
                    ordered=_text(line.quantity),
                    confirmed=_text(got.quantity),
                )
            )
        if got.unit_price is not None and got.unit_price != line.unit_price:
            found.append(
                Difference(
                    line_no=line.line_no,
                    field="unit_price",
                    ordered=_text(line.unit_price),
                    confirmed=_text(got.unit_price),
                )
            )
        late = line.need_by is not None and got.delivery_on is not None
        if late and got.delivery_on > line.need_by:  # type: ignore[operator]
            found.append(
                Difference(
                    line_no=line.line_no,
                    field="delivery_on",
                    ordered=_text(line.need_by),
                    confirmed=_text(got.delivery_on),
                )
            )
    ordered = {line.line_no for line in order.lines}
    found.extend(
        Difference(
            line_no=line.line_no, field="not_ordered", ordered=None, confirmed=_text(line.quantity)
        )
        for line in lines
        if line.line_no not in ordered
    )
    return tuple(sorted(found, key=lambda d: d.line_no))


def received(tracking: OrderTracking, line_no: int) -> Decimal:
    """How much of ``line_no`` has arrived."""
    return sum((r.quantity for r in tracking.receipts if r.line_no == line_no), Decimal(0))


def due_on(order: PoDraft, tracking: OrderTracking, line_no: int) -> date | None:
    """When ``line_no`` should arrive: the date the supplier confirmed, else
    the order's need-by date; None when neither says."""
    confirmation = tracking.confirmation
    if confirmation is not None:
        for line in confirmation.lines:
            if line.line_no == line_no and line.delivery_on is not None:
                return line.delivery_on
    return next((line.need_by for line in order.lines if line.line_no == line_no), None)


def due_lines(order: PoDraft, tracking: OrderTracking, *, today: date) -> list[int]:
    """The lines past their date with less arrived than ordered."""
    return [
        line.line_no
        for line in order.lines
        if (on := due_on(order, tracking, line.line_no)) is not None
        and on < today
        and received(tracking, line.line_no) < line.quantity
    ]
