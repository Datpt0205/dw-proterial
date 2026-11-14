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
  rejected), a quote number two customers use. An email domain several
  customers claim is shared, and recognises none of them.
- **A file as Bravo exports it** is read as it is (ticket 36): its header
  found by shape under the title rows (`header_row`), each column also known
  by Bravo's own label, a column Bravo does not have read as unknown or as its
  default where one fails closed.
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
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_platform.domain.notation import is_ambiguous_number, read_number
from dw_sales.domain.catalog import (
    ConvertEntry,
    Customer,
    Item,
    LmeMonth,
    OrderType,
    Quotation,
    month_key,
)
from dw_sales.domain.item_names import read_name

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


# How much of one list a file may hold: above Proterial's lists as Bravo
# exports them (B04 11,523 rows, B06 12,271), and a bound on what one import
# keeps and diffs.
MAX_ROWS: Final = 20_000
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
    "text",
    "int",
    "decimal",
    "pack",
    "date",
    "month",
    "bool",
    "choice",
    "list",
    "domains",
    "contacts",
]
# The kinds whose column a file may hold twice: the cells add up (Bravo's
# customer list has an "E-mail liên hệ" for the contact and another for who
# stands in for them).
_REPEATABLE: Final[frozenset[ColumnKind]] = frozenset({"list", "domains", "contacts"})


class CellError(ValueError):
    """A cell that cannot be read as its column's kind; the reason names no value."""


_TRUE: Final = frozenset({"co", "x", "yes", "y", "true", "1", "dung"})
_FALSE: Final = frozenset({"khong", "no", "n", "false", "0", "sai"})
# Items of a list cell, contacts included: one per line or separated by ";"
# or ",", as Sales types them into Bravo's export (B05); a name keeps a
# full-width comma (U+FF0C).
_LIST_SPLIT: Final = re.compile(r"[;,\n]+")
_CONTACT: Final = re.compile(r"^\s*(?:(?P<name>[^<>]*?)\s*<(?P<angle>[^<>]+)>|(?P<bare>\S+))\s*$")
_DATE_DMY: Final = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DATE_ISO: Final = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
_MONTH_ISO: Final = re.compile(r"^(\d{4})[-/.](\d{1,2})$")
_MONTH_MY: Final = re.compile(r"^(\d{1,2})[-/.](\d{4})$")


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
    """A number: a numeric cell as it is, a text cell as the platform's one
    rule reads it (`dw_platform.domain.notation.read_number`: "1.234,5" or
    "1,234.5", a comma alone as the decimal mark). "1.000" is one thousand to
    a Vietnamese reader and one to an English one: a cell is read alone, with
    no document to settle it, so it is refused, never guessed (ui-quality §9:
    a dot decimal is read correctly or refused)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CellError("không phải là số")
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = value.strip().replace(" ", "").replace(chr(0xA0), "")
    if not text:
        return None
    if is_ambiguous_number(text):
        raise CellError(
            "không rõ dấu thập phân: ghi số không phân cách hàng nghìn (ví dụ 1000 hoặc 1,5)"
        )
    number = read_number(text)
    if number is None:
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


def _domains(value: CellValue) -> list[str] | None:
    """Domains, each as it follows the "@" ("@example.com" as Bravo's list
    writes one, or "example.com")."""
    listed = _list(value)
    if listed is None:
        return None
    return [domain.removeprefix("@") for domain in listed if domain.removeprefix("@")]


def _pack(value: CellValue) -> str | None:
    """A pack multiple: 0 is "not known", as Bravo writes it (B06's Unit
    Packing), never a pack of nothing."""
    number = read_decimal(value)
    if number is None or number == 0:
        return None
    return str(number)


def _contacts(value: CellValue) -> list[dict[str, str]] | None:
    text = _text(value)
    if text is None:
        return None
    contacts: list[dict[str, str]] = []
    for part in (p for p in _LIST_SPLIT.split(text) if p.strip()):
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
    # The headers the column is also recognised by: other spellings, and
    # Bravo's own label where its export names the column (B04, B05, B06).
    aliases: tuple[str, ...] = ()
    # A choice column's words, by `header_key`, and the value each means.
    choices: Mapping[str, str] = field(default_factory=dict)
    # How a choice value prints, for the template and the diff.
    labels: Mapping[str, str] = field(default_factory=dict)
    # The value a file that lacks the column gives, where one fails closed
    # (no NOC is "not confirmed"); a blank cell in a column it has is blank.
    default: Any = None
    # Where the printed value is read from in a record, when it is not at
    # ``path`` (a column the record keeps in another shape).
    shown: Callable[[Mapping[str, Any]], Any] | None = None
    # A choice cell may name several values ("Vietnamese/English"); the first
    # one named is read, the order Sales wrote them in.
    first_of_several: bool = False

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
            case "pack":
                return _pack(value)
            case "domains":
                return _domains(value)
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
                # Several values where the column takes the first one named
                # (`first_of_several`): each must be one the column knows.
                named = re.split(r"[/;,]", text) if self.first_of_several else [text]
                chosen = [self.choices.get(header_key(part)) for part in named if part.strip()]
                if not chosen or None in chosen:
                    allowed = ", ".join(dict.fromkeys(self.labels.values()))
                    raise CellError(f"chỉ nhận: {allowed}")
                return chosen[0]

    def show(self, value: Any) -> str:
        """The value as the template prints it: what a diff compares."""
        if value is None:
            return ""
        if self.kind == "bool":
            return "Có" if value else "Không"
        if self.kind == "choice":
            return self.labels.get(str(value), str(value))
        if self.kind in ("list", "domains"):
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
        if self.kind in ("decimal", "pack"):
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
    required: bool = True,
    default: str | None = None,
    first_of_several: bool = False,
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
        required=required,
        default=default,
        first_of_several=first_of_several,
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
        return {
            c.header: c.show(_get(record, c.path) if c.shown is None else c.shown(record))
            for c in self.columns
        }


def _nested(flat: dict[str, Any]) -> dict[str, Any]:
    shaped: dict[str, Any] = {}
    for path, value in flat.items():
        _put(shaped, path, value)
    return shaped


def _customer_shape(flat: dict[str, Any]) -> dict[str, Any]:
    """A file without "Trạng thái mã" states it by Bravo's group: a
    TEMPSALES customer's code is temporary, every other one official. A
    blank domain cell is a customer with no domain of its own."""
    flat = {**flat, "email_domains": flat.get("email_domains") or ()}
    if flat.get("status") is None and flat.get("group") is not None:
        flat["status"] = "temporary" if flat["group"] == "temporary" else "official"
    return _nested(flat)


# The attributes a PRV item's name states (`item_names`), where no column of
# the file gave them.
_NAME_ATTRIBUTES: Final = ("cores", "gauge", "stranding", "colour", "standard")


def _item_shape(flat: dict[str, Any]) -> dict[str, Any]:
    """An item: the attributes no column gave, read from its name's spec
    string, and its unit conversions paired unit by factor (`_cross_fields`
    refused a pair that does not hold)."""
    shaped = dict(flat)
    read = read_name(shaped["name"]) if shaped.get("name") else None
    for attribute in _NAME_ATTRIBUTES:
        path = f"attributes.{attribute}"
        if shaped.get(path) is None:
            shaped[path] = None if read is None else getattr(read, attribute)
    units = _units(shaped.pop("conversion_units", None))
    factors = _factors(shaped.pop("conversion_factors", None), len(units)) or []
    shaped["conversions"] = [
        {"unit": unit, "factor": str(factor)} for unit, factor in zip(units, factors, strict=True)
    ]
    return _nested(shaped)


def _units(text: str | None) -> list[str]:
    """The units of a conversion cell, as Bravo spells them ("km,m")."""
    return [] if text is None else [u.strip() for u in re.split(r"[;,]", text) if u.strip()]


def _factors(text: str | None, units: int) -> list[Decimal] | None:
    """The conversion factors of ``units`` units, as Bravo writes them: one
    per unit, separated by a comma or ";" ("0.074,0.000074" for "km,m"); a
    single unit's factor may itself use a comma as its decimal mark. None
    when the cell does not give exactly one readable factor per unit."""
    if text is None:
        return [] if units == 0 else None
    pieces = [p for p in re.split(r"[;,]", text) if p.strip()]
    try:
        if len(pieces) == units:
            factors = [read_decimal(p) for p in pieces]
        elif units == 1:
            factors = [read_decimal(text)]
        else:
            return None
    except CellError:
        return None
    if any(f is None or f <= 0 for f in factors):
        return None
    return [f for f in factors if f is not None]


def _conversion_units(record: Mapping[str, Any]) -> str | None:
    return "; ".join(c["unit"] for c in record.get("conversions") or ()) or None


def _conversion_factors(record: Mapping[str, Any]) -> str | None:
    factors = [plain(Decimal(str(c["factor"]))) for c in record.get("conversions") or ()]
    return "; ".join(factors) or None


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
_GROUPS: Final = {"direct": "Trực tiếp", "temporary": "Khách tạm", "indirect": "Gián tiếp"}
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
_ORDER_TYPES: Final = {v: v for v in get_args(OrderType)}


def _no_spellings(values: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(values, ())


_CUSTOMERS = ListSpec(
    list=CatalogList.CUSTOMERS,
    label="Khách hàng",
    model=Customer,
    key=lambda r: str(r.get("code") or ""),
    shape=_customer_shape,
    columns=(
        Column(
            "code",
            "Mã khách hàng",
            "text",
            "Chữ in hoa và số, 2-16 ký tự, ví dụ VLX",
            aliases=("Mã KH", "Mã khách", "Code"),
        ),
        Column(
            "name",
            "Tên khách hàng",
            "text",
            "Như chứng từ của khách in",
            aliases=("Tên KH", "Tên khách", "Tên đối tượng"),
        ),
        Column(
            "email_domains",
            "Tên miền email",
            "domains",
            "Tên miền riêng của khách, cách nhau bởi dấu ;. Tên miền nhiều khách cùng dùng"
            " (của tập đoàn) không nhận ra khách nào nên được bỏ trống",
            aliases=("Domain", "Tên miền"),
        ),
        Column(
            "contacts",
            "Email liên hệ",
            "contacts",
            "Mỗi người 'Tên <email>' hoặc 'email', mỗi người một dòng hoặc cách nhau bởi dấu ;",
            aliases=("Người liên hệ", "Liên hệ"),
        ),
        # Bravo's list names several for a customer that reads several
        # (B05: "Vietnamese/English"); drafts are written in the first.
        _choice(
            "language",
            "Ngôn ngữ",
            "Tiếng Việt / Tiếng Anh / Tiếng Nhật; ghi nhiều thì thư soạn bằng tiếng ghi đầu",
            {
                "vi": ("Việt", "Vietnamese"),
                "en": ("Anh", "English"),
                "ja": ("Nhật", "Japanese"),
            },
            labels=_LANGUAGES,
            first_of_several=True,
        ),
        Column(
            "intra_group",
            "Cùng tập đoàn",
            "bool",
            _YES_NO_HINT,
            aliases=("Nội bộ tập đoàn",),
            required=False,
            default=False,
        ),
        # Bravo's list has no NOC: a file without the column says nothing is
        # confirmed, and every order raises `missing_noc_esf` (fails closed).
        Column(
            "compliance.noc_confirmed",
            "NOC đã xác nhận",
            "bool",
            _YES_NO_HINT,
            aliases=("NOC",),
            required=False,
            default=False,
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
        # Without this column, the status is read from Bravo's group below.
        _choice(
            "status",
            "Trạng thái mã",
            "Chính thức / Tạm thời",
            {"official": ("Chinh thuc",), "temporary": ("Tam", "Mã tạm")},
            labels=_STATUSES,
            aliases=("Trạng thái",),
            required=False,
        ),
        # Bravo's own codes for its groups ("Nhóm mẹ", B05): its closed set.
        _choice(
            "group",
            "Nhóm khách",
            "Trực tiếp / Khách tạm / Gián tiếp, như nhóm mẹ ở Bravo; để trống nếu chưa rõ",
            {
                "direct": ("01.CUSTOMER",),
                "temporary": ("02.TEMPSALES",),
                "indirect": ("03.INDIRECTCUSTOMER",),
            },
            labels=_GROUPS,
            aliases=("Nhóm mẹ",),
            required=False,
        ),
        # A customer confirmed on its portal is set so here; without the
        # column, a confirmation is a mail draft Sales sends.
        _choice(
            "confirmation_channel",
            "Kênh xác nhận",
            "Email / Cổng khách hàng",
            {"email": ("Mail",), "portal": ("Portal", "Cổng")},
            labels=_CHANNELS,
            required=False,
            default="email",
        ),
        Column(
            "sales_pic",
            "Sales phụ trách (email)",
            "text",
            "Email đăng nhập của Sales phụ trách, để trống nếu chưa giao",
            required=False,
            aliases=("Sales phụ trách", "PIC"),
        ),
        # What the customer's sales orders carry in Bravo (B41, ticket 02),
        # read into the upload file's columns; each also recognised by the
        # header Bravo's own "Import Sales Order" template prints.
        _choice(
            "order_type",
            "Loại đơn hàng",
            "Mass / Returned / Sample / SampleFee, để trống nếu chưa rõ",
            _no_spellings(_ORDER_TYPES),
            labels=_ORDER_TYPES,
            aliases=("Type", "Loại đơn"),
            required=False,
        ),
        Column(
            "delivery_term",
            "Điều kiện giao hàng",
            "text",
            "Như trên đơn bán của khách ở Bravo, ví dụ DAP; để trống nếu chưa rõ",
            required=False,
            aliases=("Delivery term",),
        ),
        Column(
            "delivery_mode",
            "Phương thức giao hàng",
            "text",
            "Như trên đơn bán của khách ở Bravo, ví dụ ROAD; để trống nếu chưa rõ",
            required=False,
            aliases=("Delivery mode",),
        ),
        Column(
            "destination",
            "Nơi giao",
            "text",
            "Như trên đơn bán của khách ở Bravo; để trống nếu chưa rõ",
            required=False,
            aliases=("Destination",),
        ),
        Column(
            "shipment_type",
            "Loại lô hàng",
            "text",
            "Như trên đơn bán của khách ở Bravo; để trống nếu chưa rõ",
            required=False,
            aliases=("Shipment type",),
        ),
    ),
)

_ATTRIBUTE_HINT = ", để trống thì DW1 đọc từ tên hàng nếu tên ghi"

_ITEMS = ListSpec(
    list=CatalogList.ITEMS,
    label="Mã hàng",
    model=Item,
    key=lambda r: str(r.get("prv_code") or ""),
    shape=_item_shape,
    columns=(
        Column("prv_code", "Mã PRV", "text", "Ví dụ HW-1001", aliases=("Mã hàng", "PRV", "Mã")),
        Column(
            "name",
            "Tên hàng",
            "text",
            "Như Bravo đặt, ví dụ 'Hook up wire - UL1007 1X24AWG(11/0.16) LF WHITE'",
            required=False,
            aliases=("Tên vật tư",),
        ),
        _choice(
            "family",
            "Họ cáp",
            "Dây đơn / Cáp nhiều lõi, để trống nếu không thuộc hai họ này",
            _no_spellings(_FAMILIES),
            labels=_FAMILIES,
            required=False,
        ),
        Column("attributes.cores", "Số lõi", "int", "1-100" + _ATTRIBUTE_HINT, required=False),
        _choice(
            "attributes.stranding",
            "Kiểu lõi",
            "Lõi đơn / Lõi xoắn" + _ATTRIBUTE_HINT,
            _no_spellings(_STRANDING),
            labels=_STRANDING,
            required=False,
        ),
        Column(
            "attributes.gauge",
            "Tiết diện",
            "text",
            "AWG24 hoặc 0.5mm2" + _ATTRIBUTE_HINT,
            required=False,
        ),
        _choice(
            "attributes.conductor",
            "Ruột dẫn",
            "Đồng trần / Đồng mạ thiếc",
            _no_spellings(_CONDUCTORS),
            labels=_CONDUCTORS,
            required=False,
        ),
        _choice(
            "attributes.shield",
            "Chống nhiễu",
            "Không / Lá nhôm / Lưới bện",
            _no_spellings(_SHIELDS),
            labels=_SHIELDS,
            required=False,
        ),
        _choice(
            "attributes.colour",
            "Màu",
            ", ".join(_COLOURS.values()) + _ATTRIBUTE_HINT,
            _no_spellings(_COLOURS),
            labels=_COLOURS,
            required=False,
        ),
        _choice(
            "attributes.packaging",
            "Đóng gói",
            "Cuộn (reel) / Cuộn tròn (coil) / Lô (drum)",
            {"reel": ("reel", "Cuộn"), "coil": ("coil",), "drum": ("drum", "Lô")},
            labels=_PACKAGING,
            required=False,
        ),
        Column(
            "attributes.spec_no",
            "Số spec",
            "text",
            "Số tiêu chuẩn Design, ví dụ SP-1124",
            aliases=("Spec",),
            required=False,
        ),
        Column(
            "unit",
            "ĐVT",
            "text",
            "Như Bravo ghi (m, Pcs, kg…); DW1 chỉ so số lượng tính bằng m",
            aliases=("Đơn vị tính",),
        ),
        Column(
            "conversion_units",
            "Đvt quy đổi",
            "text",
            "Như Bravo ghi, nhiều đơn vị cách nhau bởi dấu phẩy, ví dụ km,m",
            required=False,
            shown=_conversion_units,
        ),
        Column(
            "conversion_factors",
            "Hệ số quy đổi",
            "text",
            "Mỗi đơn vị ở cột trước một hệ số, cùng thứ tự, ví dụ 0.001,1",
            required=False,
            shown=_conversion_factors,
        ),
        Column(
            "moq",
            "MOQ",
            "decimal",
            "Số lượng đặt tối thiểu, theo ĐVT; để trống nếu chưa có",
            required=False,
        ),
        Column(
            "pack_multiple",
            "Quy cách đóng gói",
            "pack",
            "Số mét một cuộn/lô; 0 hoặc để trống là chưa biết, không kiểm",
            aliases=("Quy cách", "Unit Packing"),
        ),
        Column(
            "standard_lead_time_days",
            "Lead time chuẩn (ngày)",
            "int",
            "1-365; để trống nếu chưa có",
            aliases=("Lead time chuẩn", "Lead time"),
            required=False,
        ),
        Column(
            "packaging_style",
            "Kiểu đóng gói",
            "text",
            "Như Bravo ghi, ví dụ Coil, P-30K",
            required=False,
            aliases=("Packaging style",),
        ),
        Column(
            "category",
            "Phân loại",
            "text",
            "Như Bravo ghi, ví dụ HK, CA",
            required=False,
            # Bravo's item list spells its own header so (B06).
            aliases=("Category", "Catergory"),
        ),
        Column(
            "bp_code",
            "Mã BP",
            "text",
            "Như Bravo ghi, ví dụ BP12",
            required=False,
            aliases=("BP Code",),
        ),
        Column(
            "specification",
            "Specification",
            "text",
            "Số tiêu chuẩn kỹ thuật như Bravo ghi",
            required=False,
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
            "Khách trực tiếp, phải có trong danh mục khách hàng",
            aliases=("Mã KH", "Khách", "Direct customer code"),
        ),
        Column(
            "customer_item_code",
            "Mã hàng của khách",
            "text",
            "Mã hoặc mô tả của khách, như PO của khách in",
            aliases=("Mã của khách", "Converting description"),
        ),
        Column(
            "prv_code",
            "Mã PRV",
            "text",
            "Phải có trong danh mục mã hàng",
            aliases=("Mã hàng PRV", "PRV code"),
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


# Where the header row may be: among the first rows of the sheet, under the
# title rows an export prints above it.
_HEADER_SEARCH: Final = 10


def header_row(rows: Sequence[TableRow]) -> int:
    """Where the header is, by the rows' shape alone, never by their words:
    the first row whose text cells number at least half of the widest of the
    first rows (and at least two). A title above it ("Danh mục vật tư hàng
    hóa", merged across the sheet) is one cell, and hints beside it a few; a
    header names every column. The index into ``rows``; 0 for a sheet whose
    first row is its header, as the template's is."""
    first = rows[:_HEADER_SEARCH]
    widest = max((sum(cell is not None for cell in r.cells) for r in first), default=0)
    needed = max(2, -(-widest // 2))
    for index, row in enumerate(first):
        if sum(isinstance(cell, str) for cell in row.cells) >= needed:
            return index
    return 0


def _columns_of(spec: ListSpec, header: TableRow) -> dict[int, Column]:
    """Which cell of each row is which column; refuses a file that lacks a
    required one or names one twice (a list or contacts column may repeat:
    its cells add up)."""
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
        if column.path in seen and column.kind not in _REPEATABLE:
            raise ValueError(f"cột '{column.header}' xuất hiện hai lần")
        seen.setdefault(column.path, index)
        found[index] = column
    missing = [c.header for c in spec.columns if c.required and c.path not in seen]
    if missing:
        raise MissingColumnsError(missing)
    return found


def _unknown(spec: ListSpec, header: TableRow) -> tuple[str, ...]:
    """At most 20 headers no column matched, each cut to 100 characters: the
    file's own text, shown back to the importer, bounded."""
    known = {key for column in spec.columns for key in column.keys}
    return tuple(
        text[:100]
        for cell in header.cells
        if (text := _text(cell)) is not None and header_key(text) not in known
    )[:20]


# What a model refusal means, by pydantic's error type: no value is quoted.
_REASONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "missing": "thiếu giá trị",
        # A column's reader hands over its kind or None: a value of another
        # type is a blank cell where the record needs one.
        "string_type": "thiếu giá trị",
        "tuple_type": "thiếu giá trị",
        "bool_type": "thiếu giá trị",
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
    if spec.list is CatalogList.ITEMS:
        units = _units(flat.get("conversion_units"))
        if _factors(flat.get("conversion_factors"), len(units)) is None:
            return "Hệ số quy đổi", "cần đúng một hệ số (số dương) cho mỗi đơn vị quy đổi"
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
            read = column.read(value)
        except CellError as refused:
            return RejectedRow(row=row.row, column=column.header, reason=str(refused))
        # A column the file holds twice (`_REPEATABLE`): its cells add up.
        held = flat.get(column.path)
        flat[column.path] = read if held is None else [*held, *(read or ())]
    if (broken := _cross_fields(spec, flat)) is not None:
        return RejectedRow(row=row.row, column=broken[0], reason=broken[1])
    # A field the file has no column for is its column's default, None
    # unless one fails closed; a blank optional cell is None: the model
    # refuses what it requires, and reads the rest as unknown.
    held_paths = {column.path for column in columns.values()}
    for column in spec.columns:
        flat.setdefault(column.path, None if column.path in held_paths else column.default)
    try:
        record = spec.model.model_validate(spec.shape(flat))
    except ValidationError as exc:
        return _refusal(spec, row.row, exc.errors()[0])
    assert isinstance(record, Customer | Item | ConvertEntry | Quotation | LmeMonth)
    return record


def parse_rows(catalog_list: CatalogList, table: ImportedTable) -> ParsedList:
    """The file's rows as the list's records (module docstring). The header
    is found by the rows' shape (`header_row`), the title rows above it
    skipped; the reader already left out a group's label row (Bravo's "3. Đã
    duyệt" over its SUBTOTAL). Raises `MissingColumnsError` (or ValueError for
    a header named twice, or no rows at all); every other problem is a
    rejected row."""
    spec = SPECS[catalog_list]
    if not table.rows:
        raise ValueError("tệp không có dòng nào")
    header, *rows = table.rows[header_row(table.rows) :]
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
    kept, refused = _list_wide(_unshared(records, rejected))
    return ParsedList(
        records=tuple(kept),
        rejected=tuple(sorted([*rejected, *refused], key=lambda r: r.row)),
        unknown_headers=_unknown(spec, header),
    )


def _unshared(records: Sequence[ParsedRecord], notes: list[RejectedRow]) -> list[ParsedRecord]:
    """A domain several customers of the file claim is shared (the group's:
    132 customers in Bravo's list, B05): it recognises none of them, so it is
    taken off each, the rows kept, and the file noted (row 0). The customer's
    address decides there, never the domain (dw_sales ticket 20)."""
    claims: dict[str, set[str]] = {}
    for parsed in records:
        if isinstance(parsed.record, Customer):
            for domain in parsed.record.email_domains:
                claims.setdefault(domain, set()).add(parsed.record.code)
    shared = {domain for domain, codes in claims.items() if len(codes) > 1}
    if not shared:
        return list(records)
    notes.append(
        RejectedRow(
            row=0,
            column="Tên miền email",
            reason=f"{len(shared)} tên miền nhiều khách cùng dùng: bỏ khỏi các khách đó,"
            " khách được nhận theo địa chỉ email",
        )
    )
    return [
        replace(
            parsed,
            record=parsed.record.model_copy(
                update={
                    "email_domains": tuple(
                        d for d in parsed.record.email_domains if d not in shared
                    )
                }
            ),
        )
        if isinstance(parsed.record, Customer)
        else parsed
        for parsed in records
    ]


def _list_wide(records: Sequence[ParsedRecord]) -> tuple[list[ParsedRecord], list[RejectedRow]]:
    """Rules over the whole list: a quote number is one customer's. The later
    row is refused. (A domain claimed twice is shared: `_unshared`.)"""
    kept: list[ParsedRecord] = []
    refused: list[RejectedRow] = []
    owners: dict[str, tuple[str, int]] = {}
    for parsed in records:
        record, row = parsed.record, parsed.row
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
