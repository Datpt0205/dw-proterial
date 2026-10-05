"""Master-data records: what their constructors refuse, and the rules they carry."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.domain.catalog import (
    BravoOrder,
    Customer,
    FixedCopper,
    Item,
    LmeBand,
    LmeMonth,
    OpenYcbg,
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
        "status": "official",
        "confirmation_channel": "email",
        "sales_pic": "an.nguyen@alpha.local",
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
    assert fiscal_year(day, start_month=4) == expected


def test_the_fiscal_year_turns_where_the_policy_says() -> None:
    """The month is the policy's (`sales_order_rules`), so another one moves it."""
    assert fiscal_year(date(2026, 3, 31), start_month=1) == 2026
    assert fiscal_year(date(2026, 9, 30), start_month=10) == 2025
    assert fiscal_year(date(2026, 10, 1), start_month=10) == 2026


@pytest.mark.parametrize("month", [0, 13])
def test_a_fiscal_year_start_that_is_no_month_is_refused(month: int) -> None:
    with pytest.raises(ValueError, match="not a month"):
        fiscal_year(date(2026, 9, 30), start_month=month)


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
    with pytest.raises(ValidationError, match=r"customer VLX: contacts\[0\] is outside") as refused:
        Customer.model_validate(
            _customer(contacts=[{"address": "attacker@evil.example"}]),
        )

    assert "attacker" not in str(refused.value)


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


@pytest.mark.parametrize(
    ("overrides", "secret"),
    [
        ({"email_domains": ["Secret-Domain.example"]}, "Secret-Domain"),
        ({"contacts": [{"address": "secret.person@evil.example"}]}, "secret.person"),
        ({"sales_pic": "secret-pic"}, "secret-pic"),
        ({"name": ""}, None),
    ],
    ids=["domain", "contact", "sales_pic", "name"],
)
def test_a_refusal_names_the_field_never_the_value(
    overrides: dict[str, Any], secret: str | None
) -> None:
    """Spec decision 8: a refusal travels into logs, and the value is a customer's."""
    with pytest.raises(ValidationError) as refused:
        Customer.model_validate(_customer(**overrides))

    assert "input_value" not in str(refused.value)
    if secret is not None:
        assert secret not in str(refused.value)


def test_a_quotation_refusal_carries_no_price() -> None:
    with pytest.raises(ValidationError) as refused:
        Quotation.model_validate(_quotation(unit_price="-0.4271"))

    assert "0.4271" not in str(refused.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "provisional"},
        {"confirmation_channel": "fax"},
        {"sales_pic": "not-an-address"},
    ],
)
def test_a_customer_with_an_unknown_status_channel_or_pic_is_refused(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        Customer.model_validate(_customer(**overrides))


@pytest.mark.parametrize("field", ["status", "confirmation_channel", "sales_pic"])
def test_a_customer_that_forgets_a_field_is_refused_not_defaulted(field: str) -> None:
    """A forgotten status would read as official, a forgotten PIC as unassigned:
    both fail open, so neither has a default."""
    record = _customer()
    del record[field]

    with pytest.raises(ValidationError):
        Customer.model_validate(record)


def test_a_customer_without_a_sales_pic_says_so_explicitly() -> None:
    assert Customer.model_validate(_customer(sales_pic=None)).sales_pic is None


def test_an_unscreened_customer_reads_as_unscreened() -> None:
    """The denial-list date defaults to never, the side that raises a warning."""
    customer = Customer.model_validate(_customer())

    assert customer.compliance.denial_list_checked_on is None


def test_a_value_outside_the_vocabulary_is_unmapped_not_a_load_failure() -> None:
    """What a source adapter's anti-corruption layer hands over for a colour or a
    unit DW1 has no word for: the record loads, the value is None."""
    attributes = _item()["attributes"] | {"colour": None, "packaging": None}
    item = Item.model_validate(_item(attributes=attributes, uom=None, family=None))

    assert item.attributes.colour is None
    assert item.uom is None
    assert Quotation.model_validate(_quotation(uom=None)).uom is None


def test_an_attribute_left_out_is_refused_rather_than_read_as_unmapped() -> None:
    attributes = _item()["attributes"]
    del attributes["colour"]

    with pytest.raises(ValidationError):
        Item.model_validate(_item(attributes=attributes))


def _order(**overrides: Any) -> dict[str, Any]:
    return {
        "so_no": "SO26-0919",
        "customer_code": "QRL",
        "po_no": "QRL-PO-0918-07",
        "po_revision": 0,
        "order_date": "2026-09-19",
        "currency": "USD",
        "lines": [
            {
                "line_no": 1,
                "prv_code": "HW-1006",
                "quantity": "12200",
                "unit_price": "0.0640",
                "delivery_date": "2026-11-20",
            }
        ],
    } | overrides


def test_an_erp_order_reads_with_its_lines() -> None:
    order = BravoOrder.model_validate(_order())

    assert order.lines[0].prv_code == "HW-1006"


@pytest.mark.parametrize(
    "overrides",
    [
        {"lines": []},
        {"lines": [_order()["lines"][0], _order()["lines"][0]]},
        {"po_revision": -1},
        {"currency": "EUR"},
    ],
    ids=["no_lines", "repeated_line", "negative_revision", "unknown_currency"],
)
def test_an_impossible_erp_order_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BravoOrder.model_validate(_order(**overrides))


def test_an_open_ycbg_names_the_request_it_was_raised_from() -> None:
    ycbg = OpenYcbg.model_validate(
        {
            "ycbg_no": "YCBG-2609-028",
            "customer_code": "QRL",
            "rfq_no": "QRL-RFQ-2609-03",
            "issued_on": "2026-09-29",
        }
    )

    assert (ycbg.customer_code, ycbg.rfq_no) == ("QRL", "QRL-RFQ-2609-03")
