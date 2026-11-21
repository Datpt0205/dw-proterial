"""The gateway's contract (ADR 0027, ticket 63): typed, versioned, hashed alike."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from dw_bravo.contract import (
    READ_KINDS,
    WRITE_KINDS,
    CancelLine,
    ContractError,
    CreateSalesOrder,
    LineRef,
    SalesOrderLine,
    SetConfirmedDate,
    SetQuantity,
    SplitLine,
    SplitPart,
    canonical_json,
    content_hash,
)

pytestmark = pytest.mark.unit

LINE = LineRef(
    so_id=10,
    line_id=20,
    line_rowversion="0x00000000000007D2",
)


def test_the_same_command_hashes_the_same_and_quantities_hash_by_value() -> None:
    a = SetQuantity(line=LINE, quantity=Decimal("1.50"))
    b = SetQuantity(line=dataclasses.replace(LINE), quantity=Decimal("1.5"))

    assert content_hash(a) == content_hash(b)
    assert json.loads(canonical_json(a)) == {
        "kind": "so.line.set_quantity",
        "version": 1,
        "content": {
            "line": {
                "so_id": 10,
                "line_id": 20,
                "line_rowversion": "0x00000000000007D2",
            },
            "quantity": "1.5",
        },
    }


@pytest.mark.parametrize(
    "changed",
    [
        SetConfirmedDate(line=LINE, confirmed_date=date(2026, 12, 2)),
        SetConfirmedDate(
            line=dataclasses.replace(LINE, line_rowversion="0x00000000000007D3"),
            confirmed_date=date(2026, 12, 1),
        ),
        SetConfirmedDate(
            line=dataclasses.replace(LINE, line_id=21), confirmed_date=date(2026, 12, 1)
        ),
    ],
    ids=["date", "rowversion", "line"],
)
def test_any_field_changed_changes_the_hash(changed: SetConfirmedDate) -> None:
    approved = SetConfirmedDate(line=LINE, confirmed_date=date(2026, 12, 1))

    assert content_hash(changed) != content_hash(approved)


def test_two_kinds_with_one_content_hash_differently() -> None:
    # A cancel and a confirmed date on the same line must never share an
    # approval: the kind is inside the hash.
    assert content_hash(CancelLine(line=LINE)) != content_hash(
        SetConfirmedDate(line=LINE, confirmed_date=date(2026, 12, 1))
    )


@pytest.mark.parametrize(
    "build",
    [
        lambda: dataclasses.replace(LINE, line_rowversion="7D2"),
        lambda: dataclasses.replace(LINE, so_id=0),
        lambda: SetQuantity(line=LINE, quantity=Decimal(0)),
        lambda: SetQuantity(line=LINE, quantity=Decimal("NaN")),
        lambda: SplitLine(line=LINE, parts=(SplitPart(Decimal(1)),)),
        lambda: CreateSalesOrder(
            case_ref="M01",
            doc_date=date(2026, 12, 1),
            currency_code="USD",
            customer_code="C1",
            po_customer="PO-1",
            lines=(),
        ),
        lambda: SalesOrderLine(
            po_line="1", customer_description="x", quantity=Decimal(1), unit_price=Decimal(-1)
        ),
    ],
    ids=["rowversion", "id", "zero", "nan", "one_part", "no_lines", "negative_price"],
)
def test_a_malformed_command_is_refused_where_it_is_built(build: object) -> None:
    with pytest.raises(ContractError):
        build()  # type: ignore[operator]


def test_a_time_is_never_hashed_as_a_date() -> None:
    command = SetConfirmedDate(line=LINE, confirmed_date=datetime(2026, 12, 1, 9))

    with pytest.raises(ContractError):
        content_hash(command)


def test_every_kind_is_keyed_by_its_name_and_version() -> None:
    assert set(WRITE_KINDS) == {
        "so.line.set_confirmed_date@1",
        "so.line.split@1",
        "so.line.set_quantity@1",
        "so.line.cancel@1",
        "so.create@1",
    }
    assert all(k.screen == "EDIT_BizDocSO" for k in WRITE_KINDS.values())
    assert {k for k, w in WRITE_KINDS.items() if w.operation == "insert"} == {
        "so.line.split@1",
        "so.create@1",
    }
    # Only what the 11-20 trace shows a PIC saving may run.
    assert {k for k, w in WRITE_KINDS.items() if w.pending is None} == {
        "so.line.set_confirmed_date@1",
        "so.line.set_quantity@1",
    }
    assert set(READ_KINDS) == {
        "customer.get@1",
        "item.get@1",
        "item.convert@1",
        "quotation.lookup@1",
        "document.state@1",
        "compliance.on_date@1",
        # The two a proposed write needs (ticket 53), served by the gateway.
        "so.by_number@1",
        "user.by_employee_code@1",
    }
