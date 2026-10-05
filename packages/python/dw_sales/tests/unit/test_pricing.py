"""`sales_pricing`: the shipped (fictional) policy loads, and each question has one answer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from dw_sales.domain.catalog import LmeMonth
from dw_sales.domain.pricing import SalesPricing

pytestmark = pytest.mark.unit

SHIPPED = Path(__file__).resolve().parents[5] / "configs" / "policies" / "sales_pricing@1.0.0.yaml"


def _raw() -> dict[str, Any]:
    raw = yaml.safe_load(SHIPPED.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_the_shipped_policy_loads_and_is_named_for_its_file() -> None:
    pricing = SalesPricing.model_validate(_raw())

    assert SHIPPED.name == f"{pricing.version}.yaml"


@pytest.mark.parametrize(
    ("usd_per_tonne", "adder"),
    [("9000", "310"), ("10499.99", "360"), ("10500", "385"), ("10870", "385")],
)
def test_an_lme_price_inside_the_table_has_exactly_its_bands_adder(
    usd_per_tonne: str, adder: str
) -> None:
    pricing = SalesPricing.model_validate(_raw())
    found = pricing.copper_adder(LmeMonth(month="2026-09", usd_per_tonne=Decimal(usd_per_tonne)))

    assert found is not None
    assert found.adder_usd_per_tonne == Decimal(adder)


@pytest.mark.parametrize("usd_per_tonne", ["8999", "11500"])
def test_an_lme_price_outside_the_table_has_no_adder_not_a_zero_one(usd_per_tonne: str) -> None:
    pricing = SalesPricing.model_validate(_raw())

    assert (
        pricing.copper_adder(LmeMonth(month="2026-09", usd_per_tonne=Decimal(usd_per_tonne)))
        is None
    )


def test_freight_is_found_by_lane_and_a_missing_lane_says_so() -> None:
    pricing = SalesPricing.model_validate(_raw())
    lane = pricing.freight_rate("CIF", "japan")

    assert lane is not None
    assert lane.usd_per_km == Decimal("19.50")
    assert pricing.freight_rate("CIF", "domestic_north") is None


def test_adders_with_a_gap_or_out_of_order_are_refused() -> None:
    raw = _raw()
    adders = raw["copper_adders"]

    with pytest.raises(ValidationError, match="not contiguous"):
        SalesPricing.model_validate(raw | {"copper_adders": [adders[0], adders[2]]})
    with pytest.raises(ValidationError, match="not contiguous"):
        SalesPricing.model_validate(raw | {"copper_adders": adders[::-1]})


def test_a_lane_listed_twice_is_refused() -> None:
    raw = _raw()

    with pytest.raises(ValidationError, match="repeats"):
        SalesPricing.model_validate(raw | {"freight": [raw["freight"][1], raw["freight"][1]]})


@pytest.mark.parametrize(
    "change",
    [
        {"floor_margin": "-0.01"},
        {"floor_margin": "1"},
        {"policy_id": "sales_order_rules"},
        {"approval_matrix": []},
    ],
    ids=["negative_margin", "margin_of_all", "another_policy", "an_unread_key"],
)
def test_a_policy_with_an_impossible_or_unknown_value_is_refused(change: dict[str, Any]) -> None:
    """An unknown key is refused too: a key nothing reads reads like a safeguard."""
    with pytest.raises(ValidationError):
        SalesPricing.model_validate(_raw() | change)
