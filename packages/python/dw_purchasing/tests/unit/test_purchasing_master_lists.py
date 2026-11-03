"""DW2's master data read from a workbook (`domain.master_lists`): what a
sheet's rows mean, what is refused and why, and the version a file makes
over the one in force."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from dw_purchasing.domain.master_lists import (
    SHEETS,
    PurchasingMasterData,
    merge,
    parse_workbook,
)

_ITEMS = [(1, ["Mã vật tư", "Mô tả", "Đơn vị"]), (2, ["GT-01", "Găng tay", "đôi"])]
_SUPPLIERS = [
    (1, ["Mã NCC", "Tên NCC", "Email liên hệ"]),
    (2, ["NCC-A", "An Phát", "Sales@AnPhat.vn; kd@anphat.vn"]),
]


def _in_force(**lists: Any) -> PurchasingMasterData:
    return PurchasingMasterData.model_validate({"policy_version": "1.0.0", **lists})


def test_each_sheet_reads_into_its_list_whatever_the_headers_case_and_accents() -> None:
    parsed = parse_workbook(
        {
            "vat tu": [(1, ["MÃ VẬT TƯ", "mô tả ", "Đơn  vị"]), (2, [1001.0, "Ốc", "cái"])],
            "Nhà cung cấp": _SUPPLIERS,
            "Báo giá": [
                (
                    1,
                    [
                        "Mã vật tư",
                        "Mã NCC",
                        "Đơn giá",
                        "Tiền tệ",
                        "Hiệu lực đến",
                        "Thời gian giao (ngày)",
                    ],
                ),
                (2, ["1001", "NCC-A", "1.250.000", "vnd", "31/12/2026", 7]),
            ],
        }
    )

    assert parsed.failure is None, parsed.rejected
    assert parsed.lists["items"] == [{"code": "1001", "description": "Ốc", "unit": "cái"}]
    supplier = parsed.lists["suppliers"][0]
    assert supplier["contacts"] == ["sales@anphat.vn", "kd@anphat.vn"]
    # The mail domains are the contacts' when no column names them.
    assert supplier["domains"] == ["anphat.vn"]
    quote = parsed.lists["quotes"][0]
    assert Decimal(quote["unit_price"]) == Decimal("1250000")
    assert (quote["currency"], quote["valid_until"], quote["lead_time_days"]) == (
        "VND",
        "2026-12-31",
        7,
    )
    assert set(parsed.lists) == {"items", "suppliers", "quotes"}


def test_a_row_that_does_not_read_is_refused_with_its_sheet_row_and_column() -> None:
    parsed = parse_workbook(
        {
            "Vật tư": [*_ITEMS, (3, ["bad code!", "x", "cái"]), (4, ["GT-01", "again", "đôi"])],
            "Ngân sách": [
                (1, ["Mã ngân sách", "Còn lại", "Tiền tệ"]),
                (5, ["NS-1", "nhiều", "VND"]),
            ],
        }
    )

    reasons = {(r.sheet, r.row): r.reason for r in parsed.rejected}
    assert reasons[("Vật tư", 3)] == "cột “Mã vật tư” không hợp lệ"
    assert reasons[("Vật tư", 4)] == "trùng với dòng 2"
    assert reasons[("Ngân sách", 5)] == "không phải số"
    assert parsed.rejected_total == 3
    # The rows that read are kept; the refused ones are not.
    assert [r["code"] for r in parsed.lists["items"]] == ["GT-01"]
    assert parsed.lists["budgets"] == []
    assert parsed.failure is None


def test_a_sheet_missing_a_required_column_is_refused_whole() -> None:
    parsed = parse_workbook({"Vật tư": [(1, ["Mã vật tư", "Đơn vị"]), (2, ["GT-01", "đôi"])]})

    assert parsed.failure is not None
    assert "items" not in parsed.lists
    assert parsed.rejected[0].reason == "thiếu cột Mô tả"


def test_a_workbook_with_no_sheet_of_the_template_is_refused() -> None:
    parsed = parse_workbook({"Sheet1": [(1, ["a", "b"])]})

    assert parsed.lists == {}
    assert parsed.failure is not None and "Vật tư" in parsed.failure


def test_a_value_of_a_row_never_appears_in_a_reason() -> None:
    secret = "SECRET-PRICE-9999"
    parsed = parse_workbook(
        {"Ngân sách": [(1, ["Mã ngân sách", "Còn lại", "Tiền tệ"]), (2, ["NS-1", secret, "VND"])]}
    )

    assert all(secret not in r.reason for r in parsed.rejected)


def test_the_template_names_every_list_once() -> None:
    assert len({s.name for s in SHEETS}) == len(SHEETS) == 5
    assert all(len(s.example) == len(s.columns) for s in SHEETS)


# ------------------------------------------------------------------ merge --


def test_a_list_left_out_is_kept_and_one_in_the_file_replaces_it() -> None:
    in_force = _in_force(
        items=[{"code": "GT-01", "description": "Găng tay", "unit": "đôi"}],
        budgets=[{"code": "NS-1", "remaining": "100", "currency": "VND"}],
    )
    parsed = parse_workbook(
        {"Vật tư": [*_ITEMS, (3, ["GT-02", "Kính", "cái"])]},
    )

    merged = merge(parsed.lists, in_force, version="1.0.1")

    document = PurchasingMasterData.model_validate(merged.document)
    assert [i.code for i in document.items] == ["GT-01", "GT-02"]
    assert [b.code for b in document.budgets] == ["NS-1"]
    by_list = {c.list: c for c in merged.changes}
    assert (by_list["items"].in_file, by_list["items"].added, by_list["items"].removed) == (
        True,
        1,
        0,
    )
    assert (by_list["budgets"].in_file, by_list["budgets"].rows) == (False, 1)
    assert document.ref == "purchasing_master_data@1.0.1"


def test_a_quotation_whose_supplier_the_file_removes_goes_and_is_counted() -> None:
    in_force = _in_force(
        items=[{"code": "GT-01", "description": "Găng tay", "unit": "đôi"}],
        suppliers=[
            {"code": "NCC-A", "name": "A", "domains": ["a.vn"], "contacts": ["x@a.vn"]},
            {"code": "NCC-B", "name": "B", "domains": ["b.vn"], "contacts": ["x@b.vn"]},
        ],
        quotes=[
            {
                "item_code": "GT-01",
                "supplier_code": "NCC-B",
                "unit_price": "10",
                "currency": "VND",
                "valid_until": "2026-12-31",
                "lead_time_days": 3,
            }
        ],
    )

    merged = merge(parse_workbook({"Nhà cung cấp": _SUPPLIERS}).lists, in_force, version="1.0.1")

    assert merged.dropped == {"Báo giá": 1}
    assert PurchasingMasterData.model_validate(merged.document).quotes == ()


def test_a_version_naming_an_unknown_item_or_a_code_twice_does_not_read() -> None:
    with pytest.raises(ValidationError):
        _in_force(
            history=[
                {
                    "item_code": "X",
                    "supplier_code": "Y",
                    "unit_price": "1",
                    "currency": "VND",
                    "ordered_on": date(2026, 1, 1).isoformat(),
                }
            ]
        )
    with pytest.raises(ValidationError):
        _in_force(budgets=[{"code": "NS", "remaining": "1", "currency": "VND"}] * 2)


def test_the_master_data_checks_read_is_the_documents() -> None:
    document = _in_force(items=[{"code": "GT-01", "description": "Găng tay", "unit": "đôi"}])

    assert set(document.master_data().items) == {"GT-01"}
