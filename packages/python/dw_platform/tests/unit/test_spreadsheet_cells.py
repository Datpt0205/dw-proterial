"""A string written to a spreadsheet stays text, never a formula, whoever
wrote it (sales G29, lifted by docs/adr/0013)."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from dw_platform.adapters.spreadsheet import put

pytestmark = pytest.mark.unit


def _round_trip(*values: object) -> list[object]:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for col, value in enumerate(values, start=1):
        put(sheet, 1, col, value)  # type: ignore[arg-type]
    buffer = io.BytesIO()
    book.save(buffer)
    read = load_workbook(io.BytesIO(buffer.getvalue())).active
    assert read is not None
    return [read.cell(row=1, column=c) for c in range(1, len(values) + 1)]


@pytest.mark.parametrize("text", ['=HYPERLINK("http://x")', "+1+1", "-2", "@SUM(A1)", "\tx"])
def test_a_string_a_spreadsheet_would_compute_is_kept_as_text(text: str) -> None:
    (cell,) = _round_trip(text)
    assert cell.data_type == "s" and cell.value == text  # type: ignore[attr-defined]
    assert cell.quotePrefix  # type: ignore[attr-defined]


def test_numbers_keep_their_places_and_dates_their_format() -> None:
    amount, day, plain = _round_trip(Decimal("0.6890"), date(2026, 11, 2), "Dao cắt")
    assert amount.number_format == "0.0000"  # type: ignore[attr-defined]
    assert day.number_format == "yyyy-mm-dd"  # type: ignore[attr-defined]
    assert not plain.quotePrefix  # type: ignore[attr-defined]
