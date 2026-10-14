"""Ticket 21: the upload file has one row per delivery schedule, and every PO
that prints one date per line still produces the file it did before.

`golden/bravo_upload_rows@1.0.0.json` holds the SO_IMPORT rows each mock PO's
mapped lines produced under `sales_bravo_upload@1.0.0`, captured from the code
before the schedules existed. The mailbox is processed the way the eval world
processes it (oldest first, every message), and the template the platform
ships now must give those POs the same rows, column for column.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.artifact_content import Value
from dw_sales.application.order_artifacts import upload_rows
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import SampleSet, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "bravo_upload_rows@1.0.0.json").read_text(encoding="utf-8")
)
SHIPPED = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
LAYOUT = SHIPPED.upload


def _text(value: Value) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


async def _cases() -> dict[str, OrderCase]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    seen = await world.process_each(AN)
    return {mid: case for mid, (_, case) in seen.items() if isinstance(case, OrderCase)}


def _rows(case: OrderCase) -> list[list[object]]:
    return [
        [_text(row[c.field]) for c in LAYOUT.columns]
        for line in case.lines
        if line.mapping.prv_code is not None
        for row in upload_rows(case, line)
    ]


async def test_every_po_printing_one_date_per_line_keeps_its_upload_rows() -> None:
    cases = await _cases()

    assert LAYOUT.version == "sales_bravo_upload@1.1.0"
    assert [c.header for c in LAYOUT.columns] == GOLDEN["columns"]
    assert set(GOLDEN["rows"]) <= set(cases)
    for message_id, rows in GOLDEN["rows"].items():
        assert _rows(cases[message_id]) == rows, message_id


async def test_a_split_line_is_a_row_per_schedule_with_its_quantity_date_and_amount() -> None:
    case = (await _cases())["M34"]
    fields = [c.field for c in LAYOUT.columns]

    rows = [dict(zip(fields, row, strict=True)) for row in _rows(case)]

    assert [(r["line_no"], r["quantity"], r["requested_date"]) for r in rows] == [
        (1, "6100", "2026-11-16"),
        (1, "6100", "2026-12-01"),
        (2, "6000", "2026-11-27"),
        (3, "1500", "2026-11-27"),
        (3, "900", "2026-12-11"),
        (3, "600", "2026-12-28"),
    ]
    for row in rows:
        line = case.line(int(str(row["line_no"])))
        assert row["prv_code"] == line.mapping.prv_code
        assert row["unit_price"] == str(line.po_line.unit_price)
        if line.po_line.prints_schedules:
            # The PO prints no amount per schedule: quantity times unit price.
            amount = Decimal(str(row["quantity"])) * line.po_line.unit_price
            assert Decimal(str(row["amount"])) == amount
        else:
            assert row["amount"] == str(line.po_line.amount)
        # Each schedule's own date when the lead time allows it.
        assert row["suggested_delivery_date"] == row["requested_date"]
    by_line: dict[object, Decimal] = {}
    for row in rows:
        by_line[row["line_no"]] = by_line.get(row["line_no"], Decimal(0)) + Decimal(
            str(row["quantity"])
        )
    assert by_line == {line.line_no: line.po_line.quantity for line in case.lines}


async def test_a_schedule_too_soon_is_suggested_on_the_first_day_the_lead_time_allows() -> None:
    case = (await _cases())["M35"]
    line = case.line(2)

    assert [
        (str(r["requested_date"]), r["suggested_delivery_date"]) for r in upload_rows(case, line)
    ] == [
        ("2026-10-06", date(2026, 10, 30)),
        ("2026-11-30", date(2026, 11, 30)),
    ]
