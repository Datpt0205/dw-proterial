"""A request checked against what the company knows (DW02 function 2).

Before a request goes to its approver, code compares each line with the
company's master data: a supplier quotation still valid, the last price paid,
and the budget the request is charged to. Nothing here asks a model; every
figure is the master data's or the requester's.

Each line's **reference price** is, in order: the lowest quotation on file
still valid on the day of the check, else the last price paid, else the
requester's estimate. A reference in another currency than the request's is
no reference (no rate is guessed). The request's **amount** is the sum of
quantity times reference over its lines, or unknown when one line has none:
an unknown amount is never read as a small one.

Findings are codes with the line they concern; none is a decision. Which
findings send a request to the highest approver is the tenant's rule
(`ApprovalRules.escalate`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_purchasing.domain.requests import (
    Code,
    Currency,
    Price,
    PurchaseRequest,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class Item(BaseModel):
    model_config = _FROZEN

    code: Code
    description: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=16)


class SupplierQuote(BaseModel):
    """A supplier's price for an item, on file until ``valid_until``."""

    model_config = _FROZEN

    item_code: Code
    supplier_code: Code
    unit_price: Price
    currency: Currency
    valid_until: date
    lead_time_days: int = Field(ge=0, le=365)


class PastPurchase(BaseModel):
    """A price the company paid."""

    model_config = _FROZEN

    item_code: Code
    supplier_code: Code
    unit_price: Price
    currency: Currency
    ordered_on: date


Address = Annotated[str, Field(pattern=r"^[A-Za-z0-9._%+-]{1,64}@[a-z0-9.-]{1,253}$")]


class Supplier(BaseModel):
    """A supplier as the master data lists it."""

    model_config = _FROZEN

    code: Code
    name: str = Field(min_length=1, max_length=200)
    # The mail domains its replies come from: a reply from any other is not
    # the supplier's.
    domains: frozenset[str] = Field(min_length=1)
    contacts: tuple[Address, ...] = Field(min_length=1)
    items: frozenset[str] = frozenset()


class Budget(BaseModel):
    model_config = _FROZEN

    code: Code
    remaining: Price
    currency: Currency


class MasterData(BaseModel):
    """What the company knows, for one tenant and workspace."""

    model_config = _FROZEN

    items: Mapping[str, Item] = Field(default_factory=dict)
    quotes: tuple[SupplierQuote, ...] = ()
    history: tuple[PastPurchase, ...] = ()
    budgets: Mapping[str, Budget] = Field(default_factory=dict)
    suppliers: tuple[Supplier, ...] = ()

    def supplier(self, code: str) -> Supplier | None:
        return next((s for s in self.suppliers if s.code == code), None)


class FindingCode(StrEnum):
    # The line names no item the company knows.
    ITEM_UNKNOWN = "item_unknown"
    # No quotation, no past price and no estimate: the line has no price.
    NO_REFERENCE_PRICE = "no_reference_price"
    # A quotation or past price exists only in another currency.
    CURRENCY_MISMATCH = "currency_mismatch"
    # The requester's estimate is above the reference by more than the
    # tenant's tolerance.
    ESTIMATE_ABOVE_REFERENCE = "estimate_above_reference"
    # The date the line is needed by comes before the quotation's lead time.
    NEED_BY_SHORT = "need_by_short"
    BUDGET_MISSING = "budget_missing"
    BUDGET_UNKNOWN = "budget_unknown"
    OVER_BUDGET = "over_budget"


Basis = Literal["quote", "history", "estimate"]


class Finding(BaseModel):
    model_config = _FROZEN

    code: FindingCode
    # The line it concerns; None for the request as a whole.
    line_no: int | None = None


class LineCheck(BaseModel):
    model_config = _FROZEN

    line_no: int
    reference_price: Price | None
    basis: Basis | None
    supplier_code: Code | None
    amount: Price | None


class CrossCheck(BaseModel):
    """What code found, stamped on the case when it goes to its approver."""

    model_config = _FROZEN

    checked_on: date
    currency: Currency
    lines: tuple[LineCheck, ...]
    # None when a line has no reference price.
    amount: Price | None
    findings: tuple[Finding, ...]

    @property
    def codes(self) -> frozenset[FindingCode]:
        return frozenset(f.code for f in self.findings)


def cross_check(
    request: PurchaseRequest,
    master: MasterData,
    *,
    today: date,
    tolerance_percent: Decimal,
) -> CrossCheck:
    """The request held to ``master`` on ``today`` (module docstring)."""
    findings: list[Finding] = []
    lines: list[LineCheck] = []
    for line in request.lines:
        need_by = line.need_by or request.need_by
        known = line.item_code is not None and line.item_code in master.items
        if not known:
            findings.append(Finding(code=FindingCode.ITEM_UNKNOWN, line_no=line.line_no))
        quotes = [
            q
            for q in master.quotes
            if known and q.item_code == line.item_code and q.valid_until >= today
        ]
        past = sorted(
            (p for p in master.history if known and p.item_code == line.item_code),
            key=lambda p: p.ordered_on,
        )
        same = [q for q in quotes if q.currency == request.currency]
        paid = [p for p in past if p.currency == request.currency]
        reference: Decimal | None = None
        basis: Basis | None = None
        supplier: str | None = None
        if same:
            best = min(same, key=lambda q: (q.unit_price, q.supplier_code))
            reference, basis, supplier = best.unit_price, "quote", best.supplier_code
            if need_by is not None and need_by < today + timedelta(days=best.lead_time_days):
                findings.append(Finding(code=FindingCode.NEED_BY_SHORT, line_no=line.line_no))
        elif paid:
            reference, basis, supplier = paid[-1].unit_price, "history", paid[-1].supplier_code
        elif line.estimated_unit_price is not None:
            reference, basis = line.estimated_unit_price, "estimate"
        if (quotes or past) and not (same or paid):
            findings.append(Finding(code=FindingCode.CURRENCY_MISMATCH, line_no=line.line_no))
        if reference is None:
            findings.append(Finding(code=FindingCode.NO_REFERENCE_PRICE, line_no=line.line_no))
        elif (
            basis != "estimate"
            and line.estimated_unit_price is not None
            and line.estimated_unit_price > reference * (1 + tolerance_percent / 100)
        ):
            findings.append(
                Finding(code=FindingCode.ESTIMATE_ABOVE_REFERENCE, line_no=line.line_no)
            )
        lines.append(
            LineCheck(
                line_no=line.line_no,
                reference_price=reference,
                basis=basis,
                supplier_code=supplier,
                amount=None if reference is None else reference * line.quantity,
            )
        )
    priced = [line.amount for line in lines if line.amount is not None]
    amount = sum(priced, Decimal(0)) if len(priced) == len(lines) else None
    findings.extend(_budget(request, master, amount))
    return CrossCheck(
        checked_on=today,
        currency=request.currency,
        lines=tuple(lines),
        amount=amount,
        findings=tuple(findings),
    )


def _budget(request: PurchaseRequest, master: MasterData, amount: Decimal | None) -> list[Finding]:
    if request.budget_code is None:
        return [Finding(code=FindingCode.BUDGET_MISSING)]
    budget = master.budgets.get(request.budget_code)
    if budget is None or budget.currency != request.currency:
        return [Finding(code=FindingCode.BUDGET_UNKNOWN)]
    if amount is not None and amount > budget.remaining:
        return [Finding(code=FindingCode.OVER_BUDGET)]
    return []
