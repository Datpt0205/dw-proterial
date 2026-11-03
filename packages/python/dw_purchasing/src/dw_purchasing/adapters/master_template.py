"""`MasterTemplatePort`: DW2's master-data workbook to fill in, as an ``.xlsx``.

A guide sheet first ("Hướng dẫn": every sheet's columns, whether each must be
there, an example of what it takes), then one empty sheet per list, its
header row in the list's column order (`domain.master_lists.SHEETS`). The
examples live on the guide, never on a list's sheet: an example row left in
place would be loaded as data. Written, never read, in this process.
"""

from __future__ import annotations

import io
from typing import Final

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from dw_purchasing.domain.master_lists import SHEETS

_GUIDE: Final = "Hướng dẫn"
_NOTES: Final = (
    "Điền mỗi trang một danh sách, dòng đầu là tên cột (giữ nguyên tên cột).",
    "Chỉ cần điền trang muốn cập nhật: trang bị xoá khỏi tệp thì danh sách đó giữ như đang dùng.",
    "Trang có trong tệp sẽ thay cả danh sách đang dùng khi được duyệt: dòng không có trong"
    " tệp sẽ bị bỏ.",
    "Ngày ghi dạng 2026-12-31 hoặc 31/12/2026. Nhiều email hoặc mã cách nhau dấu ;.",
    "Mã vật tư và Mã NCC ở trang Báo giá và Giá đã mua phải có ở trang Vật tư và Nhà cung cấp.",
)


class XlsxMasterTemplate:
    """Implements `MasterTemplatePort`."""

    def workbook(self) -> bytes:
        book = Workbook()
        guide = book.active
        assert guide is not None
        guide.title = _GUIDE
        guide.append(["Cách dùng"])
        guide["A1"].font = Font(bold=True)
        for note in _NOTES:
            guide.append([note])
        guide.append([])
        guide.append(["Trang", "Cột", "Bắt buộc", "Ví dụ"])
        for cell in guide[guide.max_row]:
            cell.font = Font(bold=True)
        for spec in SHEETS:
            for column, example in zip(spec.columns, spec.example, strict=True):
                guide.append(
                    [spec.sheet, column.header, "Có" if column.required else "Không", example]
                )
        for letter, width in (("A", 18), ("B", 26), ("C", 10), ("D", 40)):
            guide.column_dimensions[letter].width = width
        for spec in SHEETS:
            sheet = book.create_sheet(spec.sheet)
            sheet.append([column.header for column in spec.columns])
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for index, column in enumerate(spec.columns, start=1):
                sheet.column_dimensions[get_column_letter(index)].width = max(
                    14, len(column.header) + 4
                )
            sheet.freeze_panes = "A2"
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()
