"""Master-data records: what their constructors refuse, and the rules they carry."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.domain.catalog import (
    Customer,
    FixedCopper,
    Item,
    LmeBand,
    LmeMonth,
    Quotation,
    fiscal_year,
    month_key,
)

pytestmark = pytest.mark.unit


def _customer(**overrides: Any) -> dict[str, Any]:
    return {
        "code": "VLX",
        "name": "Velatrix Electronics Vietnam Co., Ltd.",
        "email_domains": ["velatrix.example"],
        "contacts": [{"address": "an.trinh@velatrix.example", "display_name": "An"}],
        "language": "vi",
        "intra_group": False,
        "compliance": {"noc_confirmed": True, "esf_fiscal_year": 2026},
    } | overrides


def _quotation(**overrides: Any) -> dict[str, Any]:
    return {
        "quote_no": "Q26-0101",
        "customer_code": "VLX",
        "prv_code": "HW-1001",
        "unit_price": "0.0420",
        "currency": "USD",
        "uom": "m",
        "moq": "6100",
        "lead_time_days": 21,
        "copper_basis": {"kind": "fixed"},
        "valid_from": "2026-07-01",
        "valid_to": "2026-12-31",
    } | overrides


def _item(**overrides: Any) -> dict[str, Any]:
    return {
        "prv_code": "HW-1001",
        "family": "hook_up_wire",
        "attributes": {
            "cores": 1,
            "stranding": "stranded",
            "gauge": "AWG24",
            "conductor": "tinned_copper",
            "shield": "none",
            "colour": "black",
            "packaging": "reel",
            "spec_no": "SP-1124",
        },
        "uom": "m",
        "moq": "6100",
        "pack_multiple": "610",
        "standard_lead_time_days": 21,
    } | overrides


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 3, 31), 2025),
        (date(2026, 4, 1), 2026),
        (date(2026, 12, 31), 2026),
        (date(2027, 1, 1), 2026),
        (date(2027, 3, 31), 2026),
        (date(2027, 4, 1), 2027),
    ],
)
def test_the_fiscal_year_turns_on_the_first_of_april(day: date, expected: int) -> None:
    assert fiscal_year(day) == expected


def test_month_key_is_the_key_an_lme_month_is_stored_under() -> None:
    assert month_key(date(2026, 9, 30)) == "2026-09"
    assert month_key(date(2027, 1, 1)) == "2027-01"
    assert (
        LmeMonth(month=month_key(date(2026, 1, 15)), usd_per_tonne=Decimal(9860)).month == "2026-01"
    )


@pytest.mark.parametrize("month", ["2026-13", "2026-9", "26-09", "2026/09"])
def test_an_lme_month_in_another_spelling_is_refused(month: str) -> None:
    with pytest.raises(ValidationError):
        LmeMonth(month=month, usd_per_tonne=Decimal(9860))


def test_an_lme_band_holds_its_low_end_and_not_its_high_end() -> None:
    band = LmeBand(low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000))

    assert band.contains(Decimal(10500))
    assert band.contains(Decimal("10999.99"))
    assert not band.contains(Decimal(11000))
    assert not band.contains(Decimal("10499.99"))


def test_an_empty_lme_band_is_refused() -> None:
    with pytest.raises(ValidationError):
        LmeBand(low_usd_per_tonne=Decimal(11000), high_usd_per_tonne=Decimal(11000))


def test_a_quotation_is_valid_on_both_ends_of_its_period_and_not_beyond() -> None:
    quotation = Quotation.model_validate(_quotation())

    assert quotation.is_valid_on(date(2026, 7, 1))
    assert quotation.is_valid_on(date(2026, 12, 31))
    assert not quotation.is_valid_on(date(2026, 6, 30))
    assert not quotation.is_valid_on(date(2027, 1, 1))


def test_a_quotation_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="ends before it starts"):
        Quotation.model_validate(_quotation(valid_from="2026-12-31", valid_to="2026-07-01"))


def test_the_copper_basis_is_read_by_its_kind() -> None:
    fixed = Quotation.model_validate(_quotation())
    banded = Quotation.model_validate(
        _quotation(
            copper_basis={
                "kind": "lme_band",
                "low_usd_per_tonne": "10500",
                "high_usd_per_tonne": "11000",
            }
        )
    )

    assert isinstance(fixed.copper_basis, FixedCopper)
    assert isinstance(banded.copper_basis, LmeBand)
    with pytest.raises(ValidationError):
        Quotation.model_validate(_quotation(copper_basis={"kind": "floating"}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit_price": "0"},
        {"currency": "EUR"},
        {"uom": "km"},
        {"moq": "-1"},
    ],
)
def test_a_quotation_with_an_impossible_value_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Quotation.model_validate(_quotation(**overrides))


def test_a_contact_outside_the_customers_domains_is_refused() -> None:
    """Drafts are addressed to contacts only, so a contact must be the customer's."""
    with pytest.raises(ValidationError, match="outside VLX's domains"):
        Customer.model_validate(
            _customer(contacts=[{"address": "attacker@evil.example"}]),
        )


def test_a_customer_may_list_several_domains() -> None:
    customer = Customer.model_validate(
        _customer(email_domains=["velatrix.example", "vn.velatrix.example"])
    )

    assert customer.email_domains == ("velatrix.example", "vn.velatrix.example")


@pytest.mark.parametrize(
    "second",
    [
        "Velatrix.example",
        "velatrix",
        "velatrix.example",
        # Every label within 63 characters, the whole over 253.
        ".".join(["a" * 63] * 4) + ".example",
    ],
    ids=["uppercase", "one_label", "repeated", "over_253_characters"],
)
def test_customer_domains_are_distinct_lowercase_keys(second: str) -> None:
    """The contact's own domain stays first, so only the rule under test refuses."""
    with pytest.raises(ValidationError):
        Customer.model_validate(_customer(email_domains=["velatrix.example", second]))


def test_a_customer_needs_a_domain() -> None:
    with pytest.raises(ValidationError):
        Customer.model_validate(_customer(email_domains=[]))


def test_a_customer_needs_a_contact() -> None:
    with pytest.raises(ValidationError):
        Customer.model_validate(_customer(contacts=[]))


@pytest.mark.parametrize("gauge", ["24AWG", "AWG 24", "0.5", "0,5mm2", "0.5MM2"])
def test_a_gauge_has_one_spelling(gauge: str) -> None:
    attributes = _item()["attributes"] | {"gauge": gauge}
    with pytest.raises(ValidationError):
        Item.model_validate(_item(attributes=attributes))


@pytest.mark.parametrize(
    "overrides",
    [{"moq": "0"}, {"pack_multiple": "0"}, {"standard_lead_time_days": 0}, {"uom": "km"}],
)
def test_an_item_with_an_impossible_value_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Item.model_validate(_item(**overrides))
