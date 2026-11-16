"""One reader for every file Bravo exports (ticket 14): its header row found
by the columns' titles, never by position, a column missing named, a column
no list knows listed. Every row here is synthetic, shaped as Bravo's exports
are (Box B02, B04, B07, B16, B21): a title above, sometimes a row of block
labels, titles written in two languages with Excel's ``_x000D_`` inside."""

from __future__ import annotations

import pytest

from dw_sales.domain.bravo_exports import (
    ExportColumn,
    MissingColumnsError,
    find_header,
)
from dw_sales.domain.master_data import TableRow, header_key

pytestmark = pytest.mark.unit

_NO = ExportColumn("RFQ No")
_STATUS = ExportColumn("Status", aliases=("Trạng thái",))
_LINE = ExportColumn("Số thứ tự", aliases=("Số thứ tự/_x000D_ No.",), required=False)
_COLUMNS = (_NO, _STATUS, _LINE)


def _rows(*cells: list[object]) -> list[TableRow]:
    return [TableRow(row=i, cells=list(c)) for i, c in enumerate(cells, start=1)]


def test_excels_escaped_line_break_is_not_part_of_a_title() -> None:
    assert header_key("Quotation _x000D_ request date") == header_key("Quotation request date")
    assert header_key("Class_x000d_ (Update/New)") == header_key("Class (Update/New)")


def test_the_header_is_the_row_naming_the_columns_under_a_title_and_block_labels() -> None:
    rows = _rows(
        ["Phiếu yêu cầu báo giá"],
        ["Request for quotation", None, "Base price"],
        ["Received date", "RFQ No", "Status", "Số thứ tự/_x000D_ No.", "Người thiết kế"],
        ["2026-11-01", "RFQ261101-001", "PENDING", None, None],
    )
    found = find_header(rows, _COLUMNS)
    assert found.index == 2
    assert {column.header for column in found.at.values()} == {"RFQ No", "Status", "Số thứ tự"}
    # Bravo's other columns are listed, never guessed at.
    assert found.extra == ("Received date", "Người thiết kế")


def test_a_title_written_in_the_other_language_is_the_same_column() -> None:
    found = find_header(_rows(["Trạng thái", "RFQ No"]), _COLUMNS)
    assert found.cell(TableRow(row=2, cells=["CLOSE", "RFQ261101-001"]), _STATUS) == "CLOSE"


def test_a_file_missing_a_required_column_is_refused_naming_it_not_read_by_position() -> None:
    with pytest.raises(MissingColumnsError) as refused:
        find_header(_rows(["Ngày", "RFQ No", "Design check"]), _COLUMNS)
    assert refused.value.headers == ("Status",)
    # A file naming none of them names every required one.
    with pytest.raises(MissingColumnsError) as none:
        find_header(_rows(["a", "b"], ["c", "d"]), _COLUMNS)
    assert none.value.headers == ("RFQ No", "Status")


def test_a_column_titled_twice_is_refused_unless_it_adds_up() -> None:
    with pytest.raises(ValueError, match="hai lần"):
        find_header(_rows(["RFQ No", "Status", "Trạng thái"]), _COLUMNS)
    contacts = ExportColumn("E-mail liên hệ", repeatable=True)
    found = find_header(_rows(["E-mail liên hệ", "Tên", "E-mail liên hệ"]), (contacts,))
    assert sorted(found.at) == [0, 2]


def test_a_cell_past_the_rows_end_is_blank() -> None:
    found = find_header(_rows(["Status", "RFQ No", "Số thứ tự"]), _COLUMNS)
    short = TableRow(row=2, cells=["CLOSE", "RFQ261101-001"])
    assert found.cell(short, _LINE) is None
    assert found.cell(short, ExportColumn("Never titled", required=False)) is None


def test_a_title_two_blocks_share_is_told_apart_by_the_block_above() -> None:
    """Box B07: "LME" under "Base price (at quotation)" and again under
    "QUOTATION"; "RowIdSQ" titled on the block row only."""
    rows = _rows(
        ["Master list báo giá"],
        ["Base price", None, "QUOTATION", None, None, "RowIdSQ"],
        ["BP Code", "LME", "Quote No.", "LME", "Center price", None],
        ["BP000001", 7750, "QN-1", 8250, 1.5, "1SQ"],
    )
    quoted = ExportColumn("LME", block="QUOTATION")
    at_bp = ExportColumn("LME", block="Base price")
    row_id = ExportColumn("RowIdSQ", block="RowIdSQ")
    found = find_header(rows, (ExportColumn("Quote No."), quoted, at_bp, row_id))

    data = rows[3]
    assert found.index == 2
    assert (found.cell(data, quoted), found.cell(data, at_bp), found.cell(data, row_id)) == (
        8250,
        7750,
        "1SQ",
    )
    # Without its block, the title is two columns: refused, never the first.
    with pytest.raises(ValueError, match="hai lần"):
        find_header(rows, (ExportColumn("Quote No."), ExportColumn("LME")))
