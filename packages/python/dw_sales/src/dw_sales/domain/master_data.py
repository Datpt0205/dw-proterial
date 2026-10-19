"""The master-data lists Sales maintains by hand, as a file of rows (ticket 41).

Proterial's customers, items, convert list, quotation master list and monthly
LME price are kept in spreadsheets by Sales. DW1 reads them through
`SalesCatalogPort` (`dw_sales.domain.catalog` owns what a valid record is);
this module owns what a row of such a spreadsheet means:

- **The columns of each list** (`SPECS`): a Vietnamese header, the spellings
  a header is also recognised by, and how a cell is read. A header is matched
  without its diacritics, case, spacing or punctuation (`header_key`), so
  "Mã khách hàng", "ma khach hang" and "MA_KHACH_HANG" are one column. A
  column the file has and no list knows is reported, never guessed at.
- **A row becomes a record or a refusal** (`parse_rows`): each cell is read by
  its column's kind, the record is validated by the catalog's own model, and a
  row that fails is rejected with its row number, its column and a reason in
  Vietnamese. A reason names the column, never the cell's value (spec
  decision 8): a contact address or a price in a refusal is a customer's data
  in a log.
- **The list as a whole** is checked too: a key twice (the later row is
  rejected), an email domain two customers claim, a quote number two
  customers use.
- **A diff** (`diff`) of a proposed list against the one in force, by key:
  added, changed (column by column, old to new, as the template prints them),
  removed, unchanged.

Nothing here reads a file. The reader sandbox turns a workbook or a CSV into
rows of cell values (`ImportedTable`); the cell values are data, no more
trusted than the file.

Where the rows came from is not this module's business: a file today, the
ERP (Bravo) through another adapter later, both become the same records.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_sales.domain.catalog import (
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    Quotation,
    month_key,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class CatalogList(StrEnum):
    """The lists Sales maintains by hand. The ERP's own records (its sales
    orders and open YCBG) are not among them: they come from Bravo."""

    CUSTOMERS = "customers"
    ITEMS = "items"
    CONVERT_LIST = "convert_list"
    QUOTATIONS = "quotations"
    LME = "lme"


type CatalogRecord = Customer | Item | ConvertEntry | Quotation | LmeMonth

# A cell as the reader hands it over: text, a number, a yes/no, or nothing.
# A date cell arrives as ISO text (``2026-10-01``).
CellValue = str | int | float | bool | None


class TableRow(BaseModel):
    """One non-empty row of the sheet, numbered as the spreadsheet numbers it."""

    model_config = _FROZEN

    row: int = Field(ge=1)
    cells: list[CellValue]


class ImportedTable(BaseModel):
    """What the reader read from a file: one sheet's rows, the header first."""

    model_config = _FROZEN

    sheet: str = Field(max_length=200)
    rows: list[TableRow]
    # The sheet held more rows than are read (`MAX_ROWS`).
    truncated: bool = False


# How much of one list a file may hold: far above Proterial's lists, and a
# bound on what one import keeps and diffs.
MAX_ROWS: Final = 5000
# How many rejected rows an import keeps to show; the count is kept whole.
MAX_REJECTED_KEPT: Final = 500


class RejectedRow(BaseModel):
    """A row that is not applied, and why. ``row`` 0 is the file itself."""

    model_config = _FROZEN

    row: int = Field(ge=0)
    column: str | None = Field(default=None, max_length=200)
    reason: str = Field(max_length=300)


# ------------------------------------------------------------- headers --


def header_key(text: str) -> str:
    """A header as it is matched: no diacritics, no case, no spacing or
    punctuation. "Mã khách hàng" and "MA_KHACH_HANG" read the same."""
    decomposed = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", bare.casefold())


# ---------------------------------------------------------- cell kinds --

ColumnKind = Literal[
    "text", "int", "decimal", "date", "month", "bool", "choice", "list", "contacts"
]


class CellError(ValueError):
    """A cell that cannot be read as its column's kind; the reason names no value."""


_TRUE: Final = frozenset({"co", "x", "yes", "y", "true", "1", "dung"})
_FALSE: Final = frozenset({"khong", "no", "n", "false", "0", "sai"})
_LIST_SPLIT: Final = re.compile(r"[;,\n]+")
_CONTACT: Final = re.compile(r"^\s*(?:(?P<name>[^<>]*?)\s*<(?P<angle>[^<>]+)>|(?P<bare>\S+))\s*$")
_DATE_DMY: Final = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DATE_ISO: Final = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
_MONTH_ISO: Final = re.compile(r"^(\d{4})[-/.](\d{1,2})$")
_MONTH_MY: Final = re.compile(r"^(\d{1,2})[-/.](\d{4})$")
# Digits grouped by dots in threes, with no other separator: "1.000" is one
# thousand to a Vietnamese reader and one to an English one. Refused, never
# guessed (ui-quality §9: a dot decimal is read correctly or refused).
_AMBIGUOUS_DOTS: Final = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_AMBIGUOUS_COMMAS: Final = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def _text(value: CellValue) -> str | None:
    """A cell as text, or None when it is blank. A whole number typed in a
    text column (a code Excel stored as a number) reads as its digits."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def read_decimal(value: CellValue) -> Decimal | None:
    """A number: a numeric cell as it is, a text cell in either grouping
    ("1.234,5" or "1,234.5"), a comma alone as the decimal mark; a grouping
    that could mean either is refused."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CellError("không phải là số")
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = value.strip().replace(" ", "").replace(chr(0xA0), "")
    if not text:
        return None
    if "," in text and "." in text:
        decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
        group_mark = "." if decimal_mark == "," else ","
        text = text.replace(group_mark, "").replace(decimal_mark, ".")
    elif _AMBIGUOUS_DOTS.match(text) or _AMBIGUOUS_COMMAS.match(text):
        raise CellError(
            "không rõ dấu thập phân: ghi số không phân cách hàng nghìn (ví dụ 1000 hoặc 1,5)"
        )
    elif "," in text:
        text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise CellError("không phải là số") from None
    if not number.is_finite():
        raise CellError("không phải là số")
    return number


def plain(number: Decimal) -> str:
    """A number as one spelling: no exponent, no trailing zeros, a dot as the
    decimal mark. ``0.0420`` and ``0.042`` print alike, so a diff compares the
    value, not how it was typed."""
    return format(number.normalize(), "f")


def _int(value: CellValue) -> int | None:
    number = read_decimal(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise CellError("phải là số nguyên")
    return int(number)


def read_date(value: CellValue) -> date | None:
    """A day: ISO (``2026-10-01``, as the reader hands a date cell over) or
    day first (``01/10/2026``). Never month first."""
    text = _text(value)
    if text is None:
        return None
    try:
        if (iso := _DATE_ISO.match(text)) is not None:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        if (dmy := _DATE_DMY.match(text)) is not None:
            return date(int(dmy[3]), int(dmy[2]), int(dmy[1]))
    except ValueError:
        raise CellError("ngày không tồn tại") from None
    raise CellError("không phải ngày (dd/mm/yyyy)")


def _month(value: CellValue) -> str | None:
    text = _text(value)
    if text is None:
        return None
    for pattern, year, month in ((_MONTH_ISO, 1, 2), (_MONTH_MY, 2, 1)):
        if (found := pattern.match(text)) is not None:
            if not 1 <= int(found[month]) <= 12:
                raise CellError("tháng không tồn tại")
            return f"{int(found[year]):04d}-{int(found[month]):02d}"
    try:
        day = read_date(text)
    except CellError:
        raise CellError("không phải tháng (mm/yyyy)") from None
    assert day is not None
    return month_key(day)


def _bool(value: CellValue) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value)
    if text is None:
        return None
    key = header_key(text)
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    raise CellError("ghi Có hoặc Không")


def _list(value: CellValue) -> list[str] | None:
    text = _text(value)
    if text is None:
        return None
    return [part.strip().lower() for part in _LIST_SPLIT.split(text) if part.strip()]


def _contacts(value: CellValue) -> list[dict[str, str]] | None:
    text = _text(value)
    if text is None:
        return None
    contacts: list[dict[str, str]] = []
    for part in (p for p in re.split(r"[;\n]+", text) if p.strip()):
        found = _CONTACT.match(part)
        if found is None:
            raise CellError("ghi mỗi người là 'Tên <email>' hoặc 'email', cách nhau bởi dấu ;")
        address = (found["angle"] or found["bare"] or "").strip().lower()
        contacts.append({"address": address, "display_name": (found["name"] or "").strip()})
    return contacts


@dataclass(frozen=True)
class Column:
    """One column of a list's template, and how its cell is read."""

    path: str  # where the value goes in the record, dotted for a nested field
    header: str  # as the template prints it
    kind: ColumnKind
    hint: str  # what the template's guidance sheet says about it
    required: bool = True  # the file must have the column
    aliases: tuple[str, ...] = ()
    # A choice column's words, by `header_key`, and the value each means.
    choices: Mapping[str, str] = field(default_factory=dict)
    # How a choice value prints, for the template and the diff.
    labels: Mapping[str, str] = field(default_factory=dict)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(header_key(name) for name in (self.header, self.path, *self.aliases))

    def read(self, value: CellValue) -> Any:
        match self.kind:
            case "text":
                return _text(value)
            case "int":
                return _int(value)
            case "decimal":
                number = read_decimal(value)
                return None if number is None else str(number)
            case "date":
                day = read_date(value)
                return None if day is None else day.isoformat()
            case "month":
                return _month(value)
            case "bool":
                return _bool(value)
            case "list":
                return _list(value)
            case "contacts":
                return _contacts(value)
            case "choice":
                text = _text(value)
                if text is None:
                    return None
                chosen = self.choices.get(header_key(text))
                if chosen is None:
                    allowed = ", ".join(dict.fromkeys(self.labels.values()))
                    raise CellError(f"chỉ nhận: {allowed}")
                return chosen

    def show(self, value: Any) -> str:
        """The value as the template prints it: what a diff compares."""
        if value is None:
            return ""
        if self.kind == "bool":
            return "Có" if value else "Không"
        if self.kind == "choice":
            return self.labels.get(str(value), str(value))
        if self.kind == "list":
            return "; ".join(str(v) for v in value)
        if self.kind == "contacts":
            return "; ".join(
                f"{c['display_name']} <{c['address']}>" if c.get("display_name") else c["address"]
                for c in value
            )
        if self.kind == "date":
            return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
        if self.kind == "month":
            year, month = str(value).split("-")
            return f"{month}/{year}"
        if self.kind == "decimal":
            return plain(Decimal(str(value)))
        return str(value)


def _choice(
    path: str,
    header: str,
    hint: str,
    options: Mapping[str, tuple[str, ...]],
    *,
    labels: Mapping[str, str],
    aliases: tuple[str, ...] = (),
) -> Column:
    """A column of a fixed set: each value is recognised by its label, its
    own code and the extra spellings in ``options``."""
    words: dict[str, str] = {}
    for value, spellings in options.items():
        for spelling in (value, labels[value], *spellings):
            words[header_key(spelling)] = value
    return Column(
        path=path,
        header=header,
        kind="choice",
        hint=hint,
        aliases=aliases,
        choices=MappingProxyType(words),
        labels=MappingProxyType(dict(labels)),
    )


# ------------------------------------------------------------- the lists --


def _get(record: Mapping[str, Any], path: str) -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _put(target: dict[str, Any], path: str, value: Any) -> None:
    *parents, leaf = path.split(".")
    for part in parents:
        target = target.setdefault(part, {})
    target[leaf] = value


@dataclass(frozen=True)
class ListSpec:
    """One list: its record, its columns in template order, its key, and the
    name its template and its tab carry."""

    list: CatalogList
    label: str
    model: type[BaseModel]
    columns: tuple[Column, ...]
    key: Callable[[Mapping[str, Any]], str]
    # The record's input as its model reads it, from the columns' values.
    shape: Callable[[dict[str, Any]], dict[str, Any]] = lambda flat: flat

    def column_at(self, path: str) -> Column | None:
        return next((c for c in self.columns if c.path == path), None)

    def cells(self, record: Mapping[str, Any]) -> dict[str, str]:
        """The record as the template's row prints it, by header."""
        return {c.header: c.show(_get(record, c.path)) for c in self.columns}


def _nested(flat: dict[str, Any]) -> dict[str, Any]:
    shaped: dict[str, Any] = {}
    for path, value in flat.items():
        _put(shaped, path, value)
    return shaped


def _quotation_shape(flat: dict[str, Any]) -> dict[str, Any]:
    shaped = _nested(flat)
    basis = shaped.get("copper_basis") or {}
    if basis.get("kind") == "fixed":
        # A fixed price takes no band; a band left on it is ignored, not refused.
        shaped["copper_basis"] = {"kind": "fixed"}
    return shaped


_YES_NO_HINT = "Có / Không"
_LANGUAGES: Final = {"vi": "Tiếng Việt", "en": "Tiếng Anh", "ja": "Tiếng Nhật"}
_STATUSES: Final = {"official": "Chính thức", "temporary": "Tạm thời"}
_CHANNELS: Final = {"email": "Email", "portal": "Cổng khách hàng"}
_FAMILIES: Final = {"hook_up_wire": "Dây đơn", "multi_core_cable": "Cáp nhiều lõi"}
_STRANDING: Final = {"single": "Lõi đơn", "stranded": "Lõi xoắn"}
_CONDUCTORS: Final = {"bare_copper": "Đồng trần", "tinned_copper": "Đồng mạ thiếc"}
_SHIELDS: Final = {"none": "Không", "foil": "Lá nhôm", "braid": "Lưới bện"}
_COLOURS: Final = {
    "black": "Đen",
    "white": "Trắng",
    "red": "Đỏ",
    "blue": "Xanh dương",
    "green": "Xanh lá",
    "yellow": "Vàng",
    "grey": "Xám",
    "brown": "Nâu",
    "orange": "Cam",
    "violet": "Tím",
}
_PACKAGING: Final = {"reel": "Cuộn (reel)", "coil": "Cuộn tròn (coil)", "drum": "Lô (drum)"}
_UOMS: Final = {"m": "m"}
_CURRENCIES: Final = {"USD": "USD", "VND": "VND", "JPY": "JPY"}
_BASES: Final = {"fixed": "Cố định", "lme_band": "Theo LME"}


def _no_spellings(values: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(values, ())


_CUSTOMERS = ListSpec(
    list=CatalogList.CUSTOMERS,
    label="Khách hàng",
    model=Customer,
    key=lambda r: str(r.get("code") or ""),
    shape=_nested,
    columns=(
        Column(
            "code",
            "Mã khách hàng",
            "text",
            "Chữ in hoa và số, 2-16 ký tự, ví dụ VLX",
            aliases=("Mã KH", "Mã khách"),
        ),
        Column(
            "name",
            "Tên khách hàng",
            "text",
            "Như chứng từ của khách in",
            aliases=("Tên KH", "Tên khách"),
        ),
        Column(
            "email_domains",
            "Tên miền email",
            "list",
            "Các tên miền người gửi, cách nhau bởi dấu ;",
            aliases=("Domain", "Tên miền"),
        ),
        Column(
            "contacts",
            "Email liên hệ",
            "contacts",
            "Mỗi người 'Tên <email>', cách nhau bởi dấu ;. Email phải thuộc tên miền ở cột trước",
            aliases=("Người liên hệ", "Liên hệ"),
        ),
        _choice(
            "language",
            "Ngôn ngữ",
            "Tiếng Việt / Tiếng Anh / Tiếng Nhật",
            {"vi": ("Việt",), "en": ("Anh", "English"), "ja": ("Nhật", "Japanese")},
            labels=_LANGUAGES,
        ),
        Column("intra_group", "Cùng tập đoàn", "bool", _YES_NO_HINT, aliases=("Nội bộ tập đoàn",)),
        Column(
            "compliance.noc_confirmed", "NOC đã xác nhận", "bool", _YES_NO_HINT, aliases=("NOC",)
        ),
        Column(
            "compliance.esf_fiscal_year",
            "ESF năm tài chính",
            "int",
            "Năm tài chính ESF đã gia hạn, để trống nếu chưa có",
            required=False,
            aliases=("ESF", "Năm ESF"),
        ),
        Column(
            "compliance.denial_list_checked_on",
            "Ngày kiểm tra danh sách cấm",
            "date",
            "dd/mm/yyyy, để trống nếu chưa kiểm",
            required=False,
            aliases=("Kiểm tra danh sách cấm",),
        ),
        _choice(
            "status",
            "Trạng thái mã",
            "Chính thức / Tạm thời",
            {"official": ("Chinh thuc",), "temporary": ("Tam", "Mã tạm")},
            labels=_STATUSES,
            aliases=("Trạng thái",),
        ),
        _choice(
            "confirmation_channel",
            "Kênh xác nhận",
            "Email / Cổng khách hàng",
            {"email": ("Mail",), "portal": ("Portal", "Cổng")},
            labels=_CHANNELS,
        ),
        Column(
            "sales_pic",
            "Sales phụ trách (email)",
            "text",
            "Email đăng nhập của Sales phụ trách, để trống nếu chưa giao",
            required=False,
            aliases=("Sales phụ trách", "PIC"),
        ),
    ),
)

_ITEMS = ListSpec(
    list=CatalogList.ITEMS,
    label="Mã hàng",
    model=Item,
    key=lambda r: str(r.get("prv_code") or ""),
    shape=_nested,
    columns=(
        Column("prv_code", "Mã PRV", "text", "Ví dụ HW-1001", aliases=("Mã hàng", "PRV")),
        _choice(
            "family",
            "Họ cáp",
            "Dây đơn / Cáp nhiều lõi, để trống nếu không thuộc hai họ này",
            _no_spellings(_FAMILIES),
            labels=_FAMILIES,
        ),
        Column("attributes.cores", "Số lõi", "int", "1-100"),
        _choice(
            "attributes.stranding",
            "Kiểu lõi",
            "Lõi đơn / Lõi xoắn",
            _no_spellings(_STRANDING),
            labels=_STRANDING,
        ),
        Column("attributes.gauge", "Tiết diện", "text", "AWG24 hoặc 0.5mm2"),
        _choice(
            "attributes.conductor",
            "Ruột dẫn",
            "Đồng trần / Đồng mạ thiếc",
            _no_spellings(_CONDUCTORS),
            labels=_CONDUCTORS,
        ),
        _choice(
            "attributes.shield",
            "Chống nhiễu",
            "Không / Lá nhôm / Lưới bện",
            _no_spellings(_SHIELDS),
            labels=_SHIELDS,
        ),
        _choice(
            "attributes.colour",
            "Màu",
            ", ".join(_COLOURS.values()),
            _no_spellings(_COLOURS),
            labels=_COLOURS,
        ),
        _choice(
            "attributes.packaging",
            "Đóng gói",
            "Cuộn (reel) / Cuộn tròn (coil) / Lô (drum)",
            {"reel": ("reel", "Cuộn"), "coil": ("coil",), "drum": ("drum", "Lô")},
            labels=_PACKAGING,
        ),
        Column(
            "attributes.spec_no",
            "Số spec",
            "text",
            "Số tiêu chuẩn Design, ví dụ SP-1124",
            aliases=("Spec",),
        ),
        _choice(
            "uom",
            "ĐVT",
            "m (mét)",
            {"m": ("mét", "met", "meter")},
            labels=_UOMS,
            aliases=("Đơn vị tính",),
        ),
        Column("moq", "MOQ", "decimal", "Số lượng đặt tối thiểu, theo ĐVT"),
        Column(
            "pack_multiple",
            "Quy cách đóng gói",
            "decimal",
            "Số mét một cuộn/lô",
            aliases=("Quy cách",),
        ),
        Column(
            "standard_lead_time_days",
            "Lead time chuẩn (ngày)",
            "int",
            "1-365",
            aliases=("Lead time chuẩn", "Lead time"),
        ),
    ),
)

_CONVERT = ListSpec(
    list=CatalogList.CONVERT_LIST,
    label="Bảng quy đổi mã",
    model=ConvertEntry,
    key=lambda r: f"{r.get('customer_code') or ''} · {r.get('customer_item_code') or ''}",
    columns=(
        Column(
            "customer_code",
            "Mã khách hàng",
            "text",
            "Phải có trong danh mục khách hàng",
            aliases=("Mã KH", "Khách"),
        ),
        Column(
            "customer_item_code",
            "Mã hàng của khách",
            "text",
            "Như PO của khách in",
            aliases=("Mã của khách",),
        ),
        Column(
            "prv_code", "Mã PRV", "text", "Phải có trong danh mục mã hàng", aliases=("Mã hàng PRV",)
        ),
    ),
)

_QUOTATIONS = ListSpec(
    list=CatalogList.QUOTATIONS,
    label="Báo giá",
    model=Quotation,
    key=lambda r: f"{r.get('quote_no') or ''} · {r.get('prv_code') or ''}",
    shape=_quotation_shape,
    columns=(
        Column("quote_no", "Số báo giá", "text", "Ví dụ Q26-0101", aliases=("Báo giá",)),
        Column(
            "customer_code",
            "Mã khách hàng",
            "text",
            "Phải có trong danh mục khách hàng",
            aliases=("Mã KH", "Khách"),
        ),
        Column("prv_code", "Mã PRV", "text", "Phải có trong danh mục mã hàng"),
        Column(
            "unit_price",
            "Đơn giá",
            "decimal",
            "Theo đồng tiền ở cột sau, dấu phẩy là dấu thập phân",
        ),
        _choice(
            "currency", "Tiền tệ", "USD / VND / JPY", _no_spellings(_CURRENCIES), labels=_CURRENCIES
        ),
        _choice(
            "uom",
            "ĐVT",
            "m (mét)",
            {"m": ("mét", "met", "meter")},
            labels=_UOMS,
            aliases=("Đơn vị tính",),
        ),
        Column("moq", "MOQ", "decimal", "Số lượng đặt tối thiểu"),
        Column("lead_time_days", "Lead time (ngày)", "int", "1-365", aliases=("Lead time",)),
        _choice(
            "copper_basis.kind",
            "Căn cứ giá đồng",
            "Cố định / Theo LME",
            {"fixed": ("Fixed",), "lme_band": ("LME",)},
            labels=_BASES,
            aliases=("Căn cứ đồng",),
        ),
        Column(
            "copper_basis.low_usd_per_tonne",
            "LME từ (USD/tấn)",
            "decimal",
            "Chỉ khi theo LME: giá đồng thấp nhất của khoảng (gồm)",
            required=False,
            aliases=("LME từ",),
        ),
        Column(
            "copper_basis.high_usd_per_tonne",
            "LME đến (USD/tấn)",
            "decimal",
            "Chỉ khi theo LME: giá đồng cao nhất của khoảng (không gồm)",
            required=False,
            aliases=("LME đến",),
        ),
        Column("valid_from", "Hiệu lực từ", "date", "dd/mm/yyyy"),
        Column("valid_to", "Hiệu lực đến", "date", "dd/mm/yyyy, gồm cả ngày này"),
    ),
)

_LME = ListSpec(
    list=CatalogList.LME,
    label="Giá đồng LME",
    model=LmeMonth,
    key=lambda r: str(r.get("month") or ""),
    columns=(
        Column("month", "Tháng", "month", "mm/yyyy"),
        Column(
            "usd_per_tonne",
            "Giá đồng LME (USD/tấn)",
            "decimal",
            "Giá áp dụng cho tháng",
            aliases=("Giá LME", "USD/tấn"),
        ),
    ),
)

SPECS: Final[Mapping[CatalogList, ListSpec]] = MappingProxyType(
    {spec.list: spec for spec in (_CUSTOMERS, _ITEMS, _CONVERT, _QUOTATIONS, _LME)}
)


def record_key(catalog_list: CatalogList, record: CatalogRecord) -> str:
    """The key a record is found and diffed by in its list."""
    return SPECS[catalog_list].key(record.model_dump(mode="json"))


# ---------------------------------------------------------------- parsing --


class MissingColumnsError(ValueError):
    """The file lacks a column its list needs: nothing of it is read."""

    def __init__(self, headers: Sequence[str]) -> None:
        super().__init__("thiếu cột: " + ", ".join(headers))
        self.headers = tuple(headers)


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """A row read as a record: where it was in the file, and its key."""

    row: int
    key: str
    record: CatalogRecord


@dataclass(frozen=True)
class ParsedList:
    """A file's rows as records, the rows refused, and the headers no column
    of the list matched."""

    records: tuple[ParsedRecord, ...]
    rejected: tuple[RejectedRow, ...]
    unknown_headers: tuple[str, ...] = ()


def _columns_of(spec: ListSpec, header: TableRow) -> dict[int, Column]:
    """Which cell of each row is which column; refuses a file that lacks a
    required one or names one twice."""
    by_key = {key: column for column in spec.columns for key in column.keys}
    found: dict[int, Column] = {}
    seen: dict[str, int] = {}
    for index, cell in enumerate(header.cells):
        text = _text(cell)
        if text is None:
            continue
        column = by_key.get(header_key(text))
        if column is None:
            continue
        if column.path in seen:
            raise ValueError(f"cột '{column.header}' xuất hiện hai lần")
        seen[column.path] = index
        found[index] = column
    missing = [c.header for c in spec.columns if c.required and c.path not in seen]
    if missing:
        raise MissingColumnsError(missing)
    return found


def _unknown(spec: ListSpec, header: TableRow) -> tuple[str, ...]:
    known = {key for column in spec.columns for key in column.keys}
    return tuple(
        text
        for cell in header.cells
        if (text := _text(cell)) is not None and header_key(text) not in known
    )[:20]


# What a model refusal means, by pydantic's error type: no value is quoted.
_REASONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "missing": "thiếu giá trị",
        "string_pattern_mismatch": "sai định dạng",
        "string_too_short": "thiếu giá trị",
        "string_too_long": "quá dài",
        "too_short": "thiếu giá trị",
        "literal_error": "giá trị không thuộc danh sách cho phép",
        "greater_than": "phải lớn hơn {gt}",
        "greater_than_equal": "phải từ {ge} trở lên",
        "less_than_equal": "phải không quá {le}",
        "int_parsing": "phải là số nguyên",
        "decimal_parsing": "không phải là số",
        "date_from_datetime_parsing": "không phải ngày",
        "date_parsing": "không phải ngày",
        "union_tag_invalid": "giá trị không thuộc danh sách cho phép",
        "extra_forbidden": "cột không dùng cho bản ghi này",
    }
)


def _refusal(spec: ListSpec, row: int, error: Mapping[str, Any]) -> RejectedRow:
    loc = [str(part) for part in error.get("loc", ()) if not isinstance(part, int)]
    column: Column | None = None
    while loc and column is None:
        column = spec.column_at(".".join(loc))
        loc = loc[:-1]
    template = _REASONS.get(str(error.get("type")))
    if template is None:
        reason = "không thỏa ràng buộc của danh mục"
    else:
        ctx = {k: str(v) for k, v in (error.get("ctx") or {}).items()}
        try:
            reason = template.format(**ctx)
        except KeyError:
            reason = template
    return RejectedRow(row=row, column=None if column is None else column.header, reason=reason)


def _cross_fields(spec: ListSpec, flat: Mapping[str, Any]) -> tuple[str, str] | None:
    """The record-wide rules a model would refuse in English, said in
    Vietnamese first: (column, reason) or None."""
    if spec.list is CatalogList.CUSTOMERS:
        domains = set(flat.get("email_domains") or ())
        if len(domains) != len(flat.get("email_domains") or ()):
            return "Tên miền email", "một tên miền ghi hai lần"
        for contact in flat.get("contacts") or ():
            if contact["address"].rpartition("@")[2] not in domains:
                return "Email liên hệ", "có email không thuộc tên miền của khách"
    if spec.list is CatalogList.QUOTATIONS:
        valid_from, valid_to = flat.get("valid_from"), flat.get("valid_to")
        if valid_from and valid_to and valid_to < valid_from:
            return "Hiệu lực đến", "kết thúc trước ngày bắt đầu"
        if flat.get("copper_basis.kind") == "lme_band":
            low = flat.get("copper_basis.low_usd_per_tonne")
            high = flat.get("copper_basis.high_usd_per_tonne")
            if low is None or high is None:
                return "Căn cứ giá đồng", "theo LME cần cả 'LME từ' và 'LME đến'"
            if Decimal(high) <= Decimal(low):
                return "LME đến (USD/tấn)", "phải lớn hơn 'LME từ'"
    return None


def _record(
    spec: ListSpec, columns: Mapping[int, Column], row: TableRow
) -> CatalogRecord | RejectedRow:
    flat: dict[str, Any] = {}
    for index, column in columns.items():
        value = row.cells[index] if index < len(row.cells) else None
        try:
            flat[column.path] = column.read(value)
        except CellError as refused:
            return RejectedRow(row=row.row, column=column.header, reason=str(refused))
    if (broken := _cross_fields(spec, flat)) is not None:
        return RejectedRow(row=row.row, column=broken[0], reason=broken[1])
    # A field the file has no column for, and a blank optional cell, is None:
    # the model refuses what it requires, and reads the rest as unknown.
    for column in spec.columns:
        flat.setdefault(column.path, None)
    try:
        record = spec.model.model_validate(spec.shape(flat))
    except ValidationError as exc:
        return _refusal(spec, row.row, exc.errors()[0])
    assert isinstance(record, Customer | Item | ConvertEntry | Quotation | LmeMonth)
    return record


def parse_rows(catalog_list: CatalogList, table: ImportedTable) -> ParsedList:
    """The file's rows as the list's records (module docstring). The first
    non-empty row is the header. Raises `MissingColumnsError` (or ValueError
    for a header named twice, or no rows at all); every other problem is a
    rejected row."""
    spec = SPECS[catalog_list]
    if not table.rows:
        raise ValueError("tệp không có dòng nào")
    header, *rows = table.rows
    columns = _columns_of(spec, header)
    rejected: list[RejectedRow] = []
    if table.truncated or len(rows) > MAX_ROWS:
        rejected.append(
            RejectedRow(row=0, reason=f"tệp có hơn {MAX_ROWS} dòng: chỉ đọc {MAX_ROWS} dòng đầu")
        )
    seen: dict[str, int] = {}
    records: list[ParsedRecord] = []
    for row in rows[:MAX_ROWS]:
        if all(_text(cell) is None for cell in row.cells):
            continue
        read = _record(spec, columns, row)
        if isinstance(read, RejectedRow):
            rejected.append(read)
            continue
        key = record_key(catalog_list, read)
        if key in seen:
            rejected.append(
                RejectedRow(
                    row=row.row,
                    column=spec.columns[0].header,
                    reason=f"trùng khóa với dòng {seen[key]}",
                )
            )
            continue
        seen[key] = row.row
        records.append(ParsedRecord(row.row, key, read))
    kept, refused = _list_wide(records)
    return ParsedList(
        records=tuple(kept),
        rejected=tuple(sorted([*rejected, *refused], key=lambda r: r.row)),
        unknown_headers=_unknown(spec, header),
    )


def _list_wide(records: Sequence[ParsedRecord]) -> tuple[list[ParsedRecord], list[RejectedRow]]:
    """Rules over the whole list: an email domain is one customer's, a quote
    number one customer's. The later row is refused."""
    kept: list[ParsedRecord] = []
    refused: list[RejectedRow] = []
    owners: dict[str, tuple[str, int]] = {}
    for parsed in records:
        record, row = parsed.record, parsed.row
        if isinstance(record, Customer):
            claimed = next((d for d in record.email_domains if d in owners), None)
            if claimed is not None:
                refused.append(
                    RejectedRow(
                        row=row,
                        column="Tên miền email",
                        reason=f"tên miền đã thuộc khách hàng ở dòng {owners[claimed][1]}",
                    )
                )
                continue
            owners |= dict.fromkeys(record.email_domains, (record.code, row))
        if isinstance(record, Quotation):
            owner = owners.get(record.quote_no)
            if owner is not None and owner[0] != record.customer_code:
                refused.append(
                    RejectedRow(
                        row=row,
                        column="Số báo giá",
                        reason=f"số báo giá đã dùng cho khách khác ở dòng {owner[1]}",
                    )
                )
                continue
            owners.setdefault(record.quote_no, (record.customer_code, row))
        kept.append(parsed)
    return kept, refused


# ------------------------------------------------------------------ diff --


class DiffRow(BaseModel):
    """A record as its template row prints it."""

    model_config = _FROZEN

    key: str
    cells: dict[str, str]


class CellChange(BaseModel):
    model_config = _FROZEN

    column: str
    old: str
    new: str


class ChangedRow(BaseModel):
    model_config = _FROZEN

    key: str
    changes: list[CellChange]


class ListDiff(BaseModel):
    """A proposed list against the one in force, by key."""

    model_config = _FROZEN

    added: list[DiffRow]
    changed: list[ChangedRow]
    removed: list[DiffRow]
    unchanged: int = Field(ge=0)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "changed": len(self.changed),
            "removed": len(self.removed),
            "unchanged": self.unchanged,
        }


def diff(
    catalog_list: CatalogList,
    current: Sequence[CatalogRecord],
    proposed: Sequence[CatalogRecord],
) -> ListDiff:
    """What applying ``proposed`` changes, compared column by column as the
    template prints each value; in the proposed list's order, removals in the
    current list's."""
    spec = SPECS[catalog_list]
    before = {record_key(catalog_list, r): spec.cells(r.model_dump(mode="json")) for r in current}
    added: list[DiffRow] = []
    changed: list[ChangedRow] = []
    unchanged = 0
    after_keys: set[str] = set()
    for record in proposed:
        key = record_key(catalog_list, record)
        after_keys.add(key)
        cells = spec.cells(record.model_dump(mode="json"))
        old = before.get(key)
        if old is None:
            added.append(DiffRow(key=key, cells=cells))
            continue
        changes = [
            CellChange(column=column, old=old[column], new=value)
            for column, value in cells.items()
            if old[column] != value
        ]
        if changes:
            changed.append(ChangedRow(key=key, changes=changes))
        else:
            unchanged += 1
    removed = [
        DiffRow(key=key, cells=cells) for key, cells in before.items() if key not in after_keys
    ]
    return ListDiff(added=added, changed=changed, removed=removed, unchanged=unchanged)


def records_of(
    catalog_list: CatalogList, documents: Sequence[Mapping[str, Any]]
) -> tuple[CatalogRecord, ...]:
    """Stored records read back by the list's model."""
    model = SPECS[catalog_list].model
    records: list[CatalogRecord] = []
    for document in documents:
        record = model.model_validate(document)
        assert isinstance(record, Customer | Item | ConvertEntry | Quotation | LmeMonth)
        records.append(record)
    return tuple(records)
