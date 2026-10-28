"""DW1 suggests each line's price from its evidence (Q7, 2026-10-28: "Sales
nhập giá; DW1 chỉ đưa căn cứ"): the requester's own valid quotation first,
then their last order, then the policy's reference for a viewer who may see
other customers' prices. Never under the policy floor, and never a decision."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from dw_sales.domain.catalog import LmeMonth, Quotation
from dw_sales.domain.quotes import (
    CopperComponent,
    InternalQuotation,
    OrderedLine,
    PolicyFloor,
    PriceEvidence,
    ReferencePrice,
    SuggestionBasis,
    copper_cost_per_uom,
    suggest_price,
)

pytestmark = pytest.mark.unit

AS_OF = date(2026, 10, 2)
LME = LmeMonth(month="2026-09", usd_per_tonne=Decimal(10000))
BAND = {"kind": "lme_band", "low_usd_per_tonne": "10500", "high_usd_per_tonne": "11000"}


def _quotation(**overrides: Any) -> Quotation:
    return Quotation.model_validate(
        {
            "quote_no": "Q26-0122",
            "customer_code": "NRV",
            "prv_code": "CB-2007",
            "unit_price": "0.6980",
            "currency": "USD",
            "uom": "m",
            "moq": "3000",
            "lead_time_days": 28,
            "copper_basis": {"kind": "fixed"},
            "valid_from": "2026-07-01",
            "valid_to": "2026-12-31",
        }
        | overrides
    )


def _order(so_no: str, day: date, price: str, currency: str = "USD") -> OrderedLine:
    return OrderedLine.model_validate(
        {
            "so_no": so_no,
            "customer_code": "NRV",
            "order_date": day,
            "currency": currency,
            "prv_code": "CB-2007",
            "quantity": "1000",
            "unit_price": price,
        }
    )


def _reference(price: str) -> ReferencePrice:
    return ReferencePrice(
        price=Decimal(price),
        floor=Decimal(price),
        ceiling=Decimal(price),
        currency="USD",
        basis=("Q26-0300",),
    )


def _evidence(**fields: Any) -> PriceEvidence:
    return PriceEvidence.model_validate(
        {
            "line_no": 1,
            "customer_code": "NRV",
            "prv_code": "CB-2007",
            "currency": "USD",
            "as_of": AS_OF,
            "pricing_policy": "sales_pricing@0.2.0",
            "lme": LME,
        }
        | fields
    )


def _floored(**fields: Any) -> PriceEvidence:
    """Copper 50 kg/km at 10,000 USD/t is 0.50 USD/m; the floor 10% above, 0.55."""
    weight = Decimal(50)
    copper = CopperComponent(
        copper_kg_per_km=weight,
        lme=LME,
        adder_usd_per_tonne=Decimal(0),
        uom="m",
        usd_per_uom=copper_cost_per_uom(weight, LME.usd_per_tonne, "m"),
    )
    floor = PolicyFloor(
        copper_usd_per_uom=copper.usd_per_uom,
        floor_margin=Decimal("0.1"),
        price=copper.usd_per_uom * Decimal("1.1"),
    )
    return _evidence(copper=copper, floor=floor, **fields)


def test_the_requesters_own_valid_quotation_comes_first_with_its_terms() -> None:
    evidence = _evidence(
        own_history=(_quotation(),),
        orders=(_order("SO-1", date(2026, 9, 1), "0.7100"),),
        other_customers=(InternalQuotation(quotation=_quotation(customer_code="ABC")),),
        reference=_reference("0.7500"),
    )

    suggestion = suggest_price(evidence, others=True)

    assert suggestion is not None
    assert suggestion.basis is SuggestionBasis.OWN_QUOTATION
    assert (suggestion.unit_price, suggestion.source_no) == (Decimal("0.6980"), "Q26-0122")
    assert (suggestion.moq, suggestion.lead_time_days) == (Decimal(3000), 28)
    assert suggestion.copper_basis is not None and suggestion.copper_basis.kind == "fixed"
    assert suggestion.raised_to_floor is False


@pytest.mark.parametrize(
    "unusable",
    [
        {"valid_to": "2026-09-30"},  # expired on the day
        {"currency": "JPY"},  # another currency
        {"copper_basis": BAND},  # banded, and September's LME is outside the band
    ],
)
def test_an_own_quotation_that_does_not_hold_today_gives_way_to_the_last_order(
    unusable: dict[str, Any],
) -> None:
    evidence = _evidence(
        own_history=(_quotation(**unusable),),
        orders=(
            _order("SO-1", date(2026, 6, 1), "0.6500"),
            _order("SO-2", date(2026, 9, 1), "0.7100"),
            _order("SO-3", date(2026, 9, 15), "0.6000", currency="JPY"),
        ),
    )

    suggestion = suggest_price(evidence, others=True)

    assert suggestion is not None
    assert suggestion.basis is SuggestionBasis.LAST_ORDER
    assert (suggestion.unit_price, suggestion.source_no) == (Decimal("0.7100"), "SO-2")
    assert suggestion.moq is None and suggestion.copper_basis is None


def test_the_reference_is_a_basis_only_for_a_viewer_who_may_see_other_customers() -> None:
    evidence = _evidence(reference=_reference("0.7500"))

    every = suggest_price(evidence, others=True)

    assert every is not None and every.basis is SuggestionBasis.REFERENCE
    assert every.unit_price == Decimal("0.7500") and every.source_no is None
    assert suggest_price(evidence, others=False) is None


def test_nothing_to_go_on_suggests_nothing() -> None:
    assert suggest_price(_evidence(prv_code=None), others=True) is None


def test_a_basis_under_the_floor_is_raised_to_it_at_the_basis_precision() -> None:
    evidence = _floored(own_history=(_quotation(unit_price="0.4980"),))

    suggestion = suggest_price(evidence, others=True)

    assert suggestion is not None
    assert suggestion.unit_price == Decimal("0.5500")
    assert suggestion.raised_to_floor is True
    assert suggestion.source_no == "Q26-0122"


def test_a_basis_above_the_floor_is_left_alone() -> None:
    evidence = _floored(own_history=(_quotation(),))

    suggestion = suggest_price(evidence, others=True)

    assert suggestion is not None
    assert suggestion.unit_price == Decimal("0.6980")
    assert suggestion.raised_to_floor is False
