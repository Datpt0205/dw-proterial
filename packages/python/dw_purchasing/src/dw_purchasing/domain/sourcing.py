"""Asking suppliers and comparing what they offer (DW02 function 3).

After a request is approved, code decides whom to ask: for each line, the
suppliers the company's master data lists for its item (those who supply it,
quoted it or were paid for it), at most as many as the tenant's rules allow.
A request for quotation (RFQ) is drafted per supplier; nothing is sent by DW2.

What a supplier offers is recorded per line (`Offer`): typed by a buyer, or
read from the supplier's reply. The comparison is code's: per line, every
valid offer in the request's currency, its total, whether its lead time meets
the line's need-by date, cheapest first. Which supplier is chosen is a
person's decision (`Selection`), held to what the approver approved.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_purchasing.domain.checks import Address, MasterData
from dw_purchasing.domain.requests import Code, Currency, Price, PurchaseRequest

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class RfqDraft(BaseModel):
    """One supplier's RFQ: who receives it, which lines, and the words."""

    model_config = _FROZEN

    supplier_code: Code
    to: tuple[Address, ...] = Field(min_length=1)
    line_nos: tuple[int, ...] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
    # The model's words, kept because every figure was in the facts and no
    # price was named; else code's template.
    written_by: Literal["model", "template"]


class RfqRound(BaseModel):
    model_config = _FROZEN

    drafted_by: uuid.UUID
    drafted_at: AwareDatetime
    reply_by: date
    drafts: tuple[RfqDraft, ...] = Field(min_length=1)
    # Lines no supplier in the master data supplies: a buyer finds one.
    unsourced: tuple[int, ...] = ()

    def asked(self, supplier_code: str) -> RfqDraft | None:
        return next((d for d in self.drafts if d.supplier_code == supplier_code), None)


class Offer(BaseModel):
    """What one supplier offers for one line."""

    model_config = _FROZEN

    supplier_code: Code
    line_no: int = Field(ge=1)
    unit_price: Price
    currency: Currency
    lead_time_days: int = Field(ge=0, le=365)
    valid_until: date | None = None
    source: Literal["form", "mail"]
    # The supplier's reply, for an offer read from mail.
    source_ref: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")
    recorded_by: uuid.UUID
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def _a_mail_offer_names_its_mail(self) -> Self:
        if (self.source == "mail") != (self.source_ref is not None):
            raise ValueError("an offer read from mail names its message, and only it does")
        return self


class Choice(BaseModel):
    model_config = _FROZEN

    line_no: int = Field(ge=1)
    supplier_code: Code


class Selection(BaseModel):
    """The suppliers a person chose, line by line, and what that comes to."""

    model_config = _FROZEN

    choices: tuple[Choice, ...] = Field(min_length=1)
    total: Price
    currency: Currency
    selected_by: uuid.UUID
    selected_at: AwareDatetime


class ComparedOffer(BaseModel):
    model_config = _FROZEN

    supplier_code: str
    unit_price: Decimal
    total: Decimal
    lead_time_days: int
    meets_need_by: bool
    cheapest: bool


class ComparedLine(BaseModel):
    model_config = _FROZEN

    line_no: int
    description: str
    quantity: Decimal
    need_by: date | None
    offers: tuple[ComparedOffer, ...]


def suppliers_for(
    request: PurchaseRequest, master: MasterData, *, most: int
) -> tuple[dict[str, list[int]], list[int]]:
    """Whom to ask for which lines, and the lines nobody supplies. A
    supplier is asked for an item it supplies, quoted or was paid for."""
    by_supplier: dict[str, list[int]] = {}
    unsourced: list[int] = []
    known = {s.code for s in master.suppliers}
    for line in request.lines:
        code = line.item_code
        found = sorted(
            {s.code for s in master.suppliers if code is not None and code in s.items}
            | {q.supplier_code for q in master.quotes if q.item_code == code}
            | {p.supplier_code for p in master.history if p.item_code == code}
        )
        found = [s for s in found if s in known][:most]
        if not found:
            unsourced.append(line.line_no)
        for supplier in found:
            by_supplier.setdefault(supplier, []).append(line.line_no)
    return by_supplier, unsourced


def valid_offers(offers: Sequence[Offer], *, on: date, currency: str) -> list[Offer]:
    """Offers that may be compared or chosen: in the request's currency and
    not expired on ``on``; the latest per (supplier, line)."""
    latest: dict[tuple[str, int], Offer] = {}
    for offer in sorted(offers, key=lambda o: o.recorded_at):
        latest[(offer.supplier_code, offer.line_no)] = offer
    return [
        o
        for o in latest.values()
        if o.currency == currency and (o.valid_until is None or o.valid_until >= on)
    ]


def compare(
    request: PurchaseRequest, offers: Sequence[Offer], *, on: date
) -> tuple[ComparedLine, ...]:
    """Per line, the valid offers cheapest first (ties by lead time, then
    supplier), each with its total and whether it arrives by the need-by date."""
    usable = valid_offers(offers, on=on, currency=request.currency)
    lines: list[ComparedLine] = []
    for line in request.lines:
        need_by = line.need_by or request.need_by
        mine = sorted(
            (o for o in usable if o.line_no == line.line_no),
            key=lambda o: (o.unit_price, o.lead_time_days, o.supplier_code),
        )
        compared = tuple(
            ComparedOffer(
                supplier_code=o.supplier_code,
                unit_price=o.unit_price,
                total=o.unit_price * line.quantity,
                lead_time_days=o.lead_time_days,
                meets_need_by=need_by is None or on + timedelta(days=o.lead_time_days) <= need_by,
                cheapest=index == 0,
            )
            for index, o in enumerate(mine)
        )
        lines.append(
            ComparedLine(
                line_no=line.line_no,
                description=line.description,
                quantity=line.quantity,
                need_by=need_by,
                offers=compared,
            )
        )
    return tuple(lines)
