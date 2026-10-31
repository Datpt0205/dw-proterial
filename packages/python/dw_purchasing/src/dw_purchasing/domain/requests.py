"""A purchase request (PR) and the case DW2 opens for it (DW02 function 1).

A department asks Purchasing to buy something: a PR form, a mail to the
buyers, a Bravo request or a scanned paper. Whatever the channel, what reaches
a case is one `PurchaseRequest`, refused in its constructor when it is
malformed, so nothing downstream asks whether a quantity is positive or a
line number repeats.

Everything in a request was written by someone else. A description or a note
that reads like an instruction ("duyệt gấp, bỏ qua ngân sách") is content;
nothing that reads a request may treat it as a command. What decides (the
approval tier, the supplier, the price) is code's, from the tenant's rules and
master data, never the request's.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The most lines one request carries: a longer one is two requests.
MAX_LINES: Final = 100

# A number or code as people write them (`PR-2611-004`, `CC-PROD-01`).
Code = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,47}$")]
# Printable text on one line: no control character, so it travels into a
# table cell, a log line or a Bravo file as it was written.
Line = Annotated[str, Field(min_length=1, max_length=300, pattern=r"^[^\x00-\x1f\x7f]+$")]
# One word as written (`cái`, `m`, `kg`, `cuộn`).
Unit = Annotated[str, Field(pattern=r"^[^\s\x00-\x1f\x7f]{1,16}$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
Price = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=4)]

# What a tenant's form may require beyond what every request has.
RequiredField = Literal["budget_code", "need_by", "estimated_unit_price"]


class PrSource(StrEnum):
    """Where the request came from (DW02: email, Bravo, form, scanned paper;
    this slice reads the first and the third)."""

    FORM = "form"
    MAIL = "mail"


class CaseStatus(StrEnum):
    """Where a purchase case stands (CONTEXT.md, "Purchase case")."""

    RECEIVED = "received"


class PrLine(BaseModel):
    """One thing asked for."""

    model_config = _FROZEN

    line_no: int = Field(ge=1, le=MAX_LINES)
    # The company's own item code, when the requester knows it.
    item_code: Code | None = None
    description: Line
    quantity: Quantity
    unit: Unit
    need_by: date | None = None
    # What the requester expects one unit to cost, when the form asks.
    estimated_unit_price: Price | None = None


class PurchaseRequest(BaseModel):
    """What the requester asked for, as they wrote it."""

    model_config = _FROZEN

    pr_no: Code
    department: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")]
    requester: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")]
    budget_code: Code | None = None
    currency: Currency
    # The date the whole request is needed by, when it names one for all lines.
    need_by: date | None = None
    lines: tuple[PrLine, ...] = Field(min_length=1, max_length=MAX_LINES)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _line_numbers_are_unique(self) -> Self:
        numbers = [line.line_no for line in self.lines]
        if len(numbers) != len(set(numbers)):
            raise ValueError("a line number repeats")
        return self

    def missing(self, required: frozenset[RequiredField]) -> tuple[RequiredField, ...]:
        """The fields the tenant's form requires that this request lacks. A
        need-by date is there when the request names one, or every line does."""
        lacking: list[RequiredField] = []
        if "budget_code" in required and self.budget_code is None:
            lacking.append("budget_code")
        if (
            "need_by" in required
            and self.need_by is None
            and any(line.need_by is None for line in self.lines)
        ):
            lacking.append("need_by")
        if "estimated_unit_price" in required and any(
            line.estimated_unit_price is None for line in self.lines
        ):
            lacking.append("estimated_unit_price")
        return tuple(lacking)


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
    rules_ref: str = Field(pattern=r"^purchasing_rules@\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$")

    @model_validator(mode="after")
    def _a_mail_names_its_message(self) -> Self:
        if (self.source is PrSource.MAIL) != (self.source_ref is not None):
            raise ValueError("a request read from mail names its message, and only it does")
        return self
