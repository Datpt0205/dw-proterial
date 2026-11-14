"""A customer's SalesOrder rules: the closed set of steps, and the row they
compose with the tenant's layout (ticket 38, dw_sales ADR 0013). Synthetic
values only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.adapters.policy_files import load_bravo_upload, load_policy
from dw_sales.application.artifact_content import UploadField, Value
from dw_sales.application.salesorder_rules import (
    ColumnRule,
    CustomerSalesOrderRules,
    Lookups,
    SalesOrderRules,
    StepRefusedError,
    apply_rule,
    column_index,
    column_letter,
    filled_row,
    outside,
)
from dw_sales.domain.catalog import ConvertEntry, Customer, Item

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
POLICIES = REPO / "configs" / "policies"
LAYOUT = load_bravo_upload(POLICIES / "sales_bravo_upload@2.0.0.yaml")

CUSTOMER = Customer.model_validate(
    {
        "code": "KHA",
        "name": "Khach A Synthetic Co.",
        "email_domains": ["kha.example"],
        "contacts": [{"address": "po@kha.example"}],
        "language": "en",
        "intra_group": False,
        "compliance": {
            "noc_confirmed": True,
            "esf_fiscal_year": 2026,
            "denial_list_checked_on": "2026-09-01",
        },
        "status": "official",
        "confirmation_channel": "email",
        "sales_pic": None,
        "order_type": "Mass",
    }
)
ITEM = Item.model_validate(
    {
        "prv_code": "PRV-0001-RD",
        "family": "hook_up_wire",
        "attributes": {
            "cores": 1,
            "stranding": "stranded",
            "gauge": "AWG24",
            "conductor": "tinned_copper",
            "shield": "none",
            "colour": "red",
            "packaging": "reel",
            "spec_no": "SP-0001",
        },
        "unit": "m",
        "moq": None,
        "pack_multiple": "610",
        "standard_lead_time_days": None,
        "specification": "DS-0001",
    }
)
LOOKUPS = Lookups.of(
    "KHA",
    (
        ConvertEntry(customer_code="KHA", customer_item_code="W24-R", prv_code="PRV-0001-RD"),
        ConvertEntry(customer_code="OTHER", customer_item_code="W24-B", prv_code="PRV-0001-RD"),
    ),
    (ITEM,),
)
VALUES: dict[UploadField, Value] = {
    "row_no": 1,
    "customer_code": "KHA",
    "po_no": "SYN-PO-1",
    "revision": 0,
    "po_date": date(2026, 11, 2),
    "received_date": date(2026, 11, 3),
    "currency": "USD",
    "usd_rate": 1,
    "line_no": 1,
    "customer_item_code": "W24-R",
    "prv_code": None,
    "description": "WIRE 24 R",
    "quantity": Decimal("1.22"),
    "uom": "KM",
    "unit_price": Decimal("41.50"),
    "amount": Decimal("50.63"),
    "requested_date": date(2026, 12, 20),
    "suggested_delivery_date": None,
}


def _rule(**data: Any) -> ColumnRule:
    return ColumnRule.model_validate(data)


def _apply(**data: Any) -> Value:
    return apply_rule(_rule(**data), VALUES, CUSTOMER, LOOKUPS)


def test_each_step_of_the_closed_set_does_one_thing() -> None:
    assert _apply(column="V", field="customer_item_code", steps=[{"step": "copy"}]) == "W24-R"
    assert _apply(column="W", steps=[{"step": "constant", "value": "HK"}]) == "HK"
    assert _apply(
        column="AF", field="requested_date", steps=[{"step": "shift_days", "days": -10}]
    ) == date(2026, 12, 10)
    assert _apply(
        column="AA", field="quantity", steps=[{"step": "unit_factor", "from": "km", "to": "m"}]
    ) == Decimal(1220)
    # A price per km written per m: one m is a thousandth of a km.
    assert _apply(
        column="AE",
        field="unit_price",
        steps=[{"step": "unit_factor", "from": "m", "to": "km"}, {"step": "round", "places": 4}],
    ) == Decimal("0.0415")
    assert _apply(
        column="AE", field="unit_price", steps=[{"step": "round", "places": 0, "mode": "down"}]
    ) == Decimal(41)
    assert (
        _apply(column="X", field="customer_item_code", steps=[{"step": "cut", "start": -1}]) == "R"
    )
    assert (
        _apply(
            column="Y",
            field="customer_item_code",
            steps=[{"step": "concat", "sources": ["po_no", "line_no"], "separator": "-"}],
        )
        == "W24-R-SYN-PO-1-1"
    )
    assert _apply(
        column="AE", field="quantity", steps=[{"step": "multiply", "source": "unit_price"}]
    ) == Decimal("50.6300")


def test_a_lookup_reads_the_customers_own_convert_list_and_the_item_master() -> None:
    """Colour letters reach the PRV code through the convert list (Bravo
    writes the colour into it); the item master's columns by PRV code."""
    assert (
        _apply(
            column="T",
            field="customer_item_code",
            steps=[{"step": "lookup", "table": "convert_list"}],
        )
        == "PRV-0001-RD"
    )
    assert (
        _apply(
            column="V",
            field="customer_item_code",
            steps=[
                {"step": "lookup", "table": "convert_list"},
                {"step": "lookup", "table": "item_colour"},
            ],
        )
        == "red"
    )
    assert _apply(
        column="AB",
        field="customer_item_code",
        steps=[
            {"step": "lookup", "table": "convert_list"},
            {"step": "lookup", "table": "item_standard_length"},
        ],
    ) == Decimal(610)
    # Another customer's row of the convert list never answers this one's line.
    other: dict[UploadField, Value] = {**VALUES, "customer_item_code": "W24-B"}
    with pytest.raises(StepRefusedError) as refused:
        apply_rule(
            _rule(
                column="T",
                field="customer_item_code",
                steps=[{"step": "lookup", "table": "convert_list"}],
            ),
            other,
            CUSTOMER,
            LOOKUPS,
        )
    assert (refused.value.column, refused.value.step, refused.value.problem) == (
        "T",
        1,
        "lookup_missing",
    )


def test_a_step_given_the_wrong_kind_of_value_is_refused_by_name() -> None:
    cases = (
        ({"field": "description", "steps": [{"step": "shift_days", "days": 1}]}, "not_a_date"),
        ({"field": "description", "steps": [{"step": "round", "places": 1}]}, "not_a_number"),
        ({"field": "requested_date", "steps": [{"step": "cut", "end": 2}]}, "not_text"),
        ({"field": "prv_code", "steps": [{"step": "copy"}, {"step": "cut"}]}, "value_missing"),
    )
    for data, problem in cases:
        with pytest.raises(StepRefusedError) as refused:
            _apply(column="X", **data)
        assert refused.value.problem == problem


@pytest.mark.parametrize(
    "data",
    [
        # A step outside the closed set.
        {"column": "X", "field": "po_no", "steps": [{"step": "formula", "text": "=A1*2"}]},
        # A field nothing reads.
        {"column": "X", "field": "po_line_text", "steps": []},
        # A lookup in a table that is not master data.
        {"column": "X", "field": "po_no", "steps": [{"step": "lookup", "table": "prices"}]},
        # A separator that would carry a value of its own.
        {
            "column": "X",
            "field": "po_no",
            "steps": [{"step": "concat", "sources": ["line_no"], "separator": "PO 123"}],
        },
        # Two starts, or none without a constant first.
        {"column": "X", "field": "po_no", "customer": "order_type"},
        {"column": "X", "steps": [{"step": "copy"}]},
        # A key the step does not have.
        {"column": "X", "field": "po_no", "steps": [{"step": "copy", "code": "x"}]},
    ],
)
def test_anything_outside_the_closed_set_refuses_the_rule(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ColumnRule.model_validate(data)


def test_a_customers_rules_name_each_column_once() -> None:
    with pytest.raises(ValidationError, match="named once"):
        CustomerSalesOrderRules.model_validate(
            {
                "columns": [
                    {"column": "W", "steps": [{"step": "constant", "value": "A"}]},
                    {"column": "W", "steps": [{"step": "constant", "value": "B"}]},
                ]
            }
        )


def test_a_row_takes_the_named_columns_from_the_rules_and_the_rest_from_the_layout() -> None:
    rules = CustomerSalesOrderRules.model_validate(
        {
            "columns": [
                {
                    "column": "AF",
                    "field": "requested_date",
                    "steps": [{"step": "shift_days", "days": -10}],
                },
                {
                    "column": "AA",
                    "field": "quantity",
                    "steps": [{"step": "unit_factor", "from": "km", "to": "m"}],
                },
                {"column": "W", "steps": [{"step": "constant", "value": "HK"}]},
            ]
        }
    )
    plain = filled_row(LAYOUT, None, VALUES, CUSTOMER, LOOKUPS)
    ruled = filled_row(LAYOUT, rules, VALUES, CUSTOMER, LOOKUPS)

    changed = {
        column_letter(i) for i, (a, b) in enumerate(zip(plain, ruled, strict=True)) if a != b
    }
    assert changed == {"AF", "AA", "W"}
    assert ruled[column_index("AF")] == date(2026, 12, 10)
    assert ruled[column_index("AA")] == Decimal(1220)
    # The layout's own columns: the PO number, the customer's order type.
    assert ruled[column_index("L")] == "SYN-PO-1"
    assert ruled[column_index("F")] == "Mass"


def test_a_rule_for_a_column_the_layout_does_not_have_is_found() -> None:
    rules = CustomerSalesOrderRules.model_validate(
        {"columns": [{"column": "BZ", "steps": [{"step": "constant", "value": "X"}]}]}
    )
    assert outside(LAYOUT, rules) == ["BZ"]
    assert (column_index("A"), column_index("AM"), column_letter(38)) == (0, 38, "AM")


def test_the_platform_holds_no_customers_rules() -> None:
    shipped = load_policy(POLICIES / "sales_salesorder_rules@1.0.0.yaml", SalesOrderRules)
    assert (shipped.ref, dict(shipped.customers), shipped.mock) == (
        "sales_salesorder_rules@1.0.0",
        {},
        False,
    )
