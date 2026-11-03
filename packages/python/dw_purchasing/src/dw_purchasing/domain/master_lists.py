"""DW2's master data as one document, and the workbook it is loaded from.

The company's lists (items, suppliers, supplier quotations on file, prices
paid, budgets) are one document a tenant holds its own version of
(`PurchasingMasterData`, key ``purchasing_master_data``): proposed, decided by
a second person and applied by the platform's rule-version engine, as DW2's
rules are (`docs/adr/0001-master-data-is-a-rule-version.md`). The platform
ships it empty: a tenant without a version has no reference price and no
budget, so its requests go to the last approval tier (`domain.checks`).

A person loads it from one workbook, one sheet per list (`SHEETS`), the
header row first. A sheet left out keeps that list as it is in force; a row
that does not read is refused with its sheet, its row and why, in
Vietnamese, and never applied. Nothing here reads a file: the worker's
reader turns the workbook into rows (`SheetRows`), and this module decides
what the rows mean.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_purchasing.domain.checks import (
    Budget,
    Item,
    MasterData,
    PastPurchase,
    Supplier,
    SupplierQuote,
)

POLICY_ID: Final = "purchasing_master_data"
# Far above a plant's lists, and a bound on what one version holds.
MAX_ROWS: Final = 20_000
# What an import keeps of its refused rows to show; the count is whole.
MAX_REJECTED_SHOWN: Final = 500

_Version = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]

CellValue = str | int | float | bool | None
# One sheet's rows as the reader read them: (row number, cells), header first.
SheetRows = Mapping[str, Sequence[tuple[int, Sequence[CellValue]]]]

ListName = Literal["items", "suppliers", "quotes", "history", "budgets"]


class PurchasingMasterData(BaseModel):
    """One version of the company's lists: every code once, every quotation
    and price paid naming an item and a supplier the lists hold."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    policy_id: Literal["purchasing_master_data"] = POLICY_ID
    version: _Version = Field(alias="policy_version")
    items: tuple[Item, ...] = Field(default=(), max_length=MAX_ROWS)
    suppliers: tuple[Supplier, ...] = Field(default=(), max_length=MAX_ROWS)
    quotes: tuple[SupplierQuote, ...] = Field(default=(), max_length=MAX_ROWS)
    history: tuple[PastPurchase, ...] = Field(default=(), max_length=MAX_ROWS)
    budgets: tuple[Budget, ...] = Field(default=(), max_length=MAX_ROWS)

    @model_validator(mode="after")
    def _codes_once_and_references_held(self) -> Self:
        for name in ("items", "suppliers", "budgets"):
            codes = [row.code for row in getattr(self, name)]
            if len(codes) != len(set(codes)):
                raise ValueError(f"{name}: a code is listed twice")
        items = {i.code for i in self.items}
        suppliers = {s.code for s in self.suppliers}
        for name in ("quotes", "history"):
            for row in getattr(self, name):
                if row.item_code not in items or row.supplier_code not in suppliers:
                    raise ValueError(f"{name}: names an item or supplier the lists lack")
        return self

    @property
    def ref(self) -> str:
        return f"{POLICY_ID}@{self.version}"

    def master_data(self) -> MasterData:
        return MasterData(
            items={i.code: i for i in self.items},
            quotes=self.quotes,
            history=self.history,
            budgets={b.code: b for b in self.budgets},
            suppliers=self.suppliers,
        )


# ------------------------------------------------------------- the workbook --


def _text(value: CellValue) -> str | None:
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    if isinstance(value, float) and value.is_integer():
        # A code typed as a number reads back as 1001.0 from Excel.
        return str(int(value))
    text = str(value).strip()
    return text or None


def _decimal(value: CellValue) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    cleaned = str(value).strip().replace(" ", "")
    # 1.250.000 or 1,250,000 as a person types a price: the grouping goes.
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", cleaned):
        cleaned = re.sub(r"[.,]", "", cleaned)
    try:
        return Decimal(cleaned.replace(",", "."))
    except InvalidOperation:
        raise ValueError("không phải số") from None


def _date(value: CellValue) -> date | None:
    text = _text(value)
    if text is None:
        return None
    for pattern in (r"(\d{4})-(\d{2})-(\d{2})", r"(\d{1,2})/(\d{1,2})/(\d{4})"):
        found = re.fullmatch(pattern, text[:10])
        if found:
            a, b, c = (int(g) for g in found.groups())
            try:
                return date(a, b, c) if a > 31 else date(c, b, a)
            except ValueError:
                break
    raise ValueError("ngày phải ghi dạng 2026-12-31 hoặc 31/12/2026")


def _upper(value: CellValue) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _many(value: CellValue) -> list[str]:
    text = _text(value) or ""
    return [part.strip() for part in re.split(r"[;,\n]", text) if part.strip()]


def _lower_many(value: CellValue) -> list[str]:
    return [part.lower() for part in _many(value)]


_Read = Callable[[CellValue], Any]


@dataclass(frozen=True)
class Column:
    header: str
    field: str
    read: _Read = _text
    required: bool = True


@dataclass(frozen=True)
class ListSpec:
    name: ListName
    sheet: str
    columns: tuple[Column, ...]
    model: type[BaseModel]
    # What identifies a row: two rows with one key are one row written twice.
    key: Callable[[Any], tuple[Any, ...]]
    example: tuple[CellValue, ...]

    def complete(self, record: dict[str, Any]) -> dict[str, Any]:
        """What a row leaves out and the list can say: a supplier's mail
        domains are its contacts' when no column names them."""
        if self.name == "suppliers" and not record.get("domains"):
            record["domains"] = sorted({a.rsplit("@", 1)[-1] for a in record.get("contacts", [])})
        return record


SHEETS: Final[tuple[ListSpec, ...]] = (
    ListSpec(
        "items",
        "Vật tư",
        (
            Column("Mã vật tư", "code"),
            Column("Mô tả", "description"),
            Column("Đơn vị", "unit"),
        ),
        Item,
        lambda r: (r.code,),
        ("GT-CUT-05", "Găng tay chống cắt cấp 5", "đôi"),
    ),
    ListSpec(
        "suppliers",
        "Nhà cung cấp",
        (
            Column("Mã NCC", "code"),
            Column("Tên NCC", "name"),
            Column("Email liên hệ", "contacts", _lower_many),
            Column("Tên miền thư", "domains", _lower_many, required=False),
            Column("Mã vật tư cung cấp", "items", _many, required=False),
        ),
        Supplier,
        lambda r: (r.code,),
        ("NCC-ANPHAT", "Công ty An Phát", "sales@anphat.vn; kd@anphat.vn", "", "GT-CUT-05"),
    ),
    ListSpec(
        "quotes",
        "Báo giá",
        (
            Column("Mã vật tư", "item_code"),
            Column("Mã NCC", "supplier_code"),
            Column("Đơn giá", "unit_price", _decimal),
            Column("Tiền tệ", "currency", _upper),
            Column("Hiệu lực đến", "valid_until", _date),
            Column("Thời gian giao (ngày)", "lead_time_days", _decimal),
        ),
        SupplierQuote,
        lambda r: (r.item_code, r.supplier_code),
        ("GT-CUT-05", "NCC-ANPHAT", 85000, "VND", "2026-12-31", 7),
    ),
    ListSpec(
        "history",
        "Giá đã mua",
        (
            Column("Mã vật tư", "item_code"),
            Column("Mã NCC", "supplier_code"),
            Column("Đơn giá", "unit_price", _decimal),
            Column("Tiền tệ", "currency", _upper),
            Column("Ngày đặt", "ordered_on", _date),
        ),
        PastPurchase,
        lambda r: (r.item_code, r.supplier_code, r.ordered_on),
        ("GT-CUT-05", "NCC-ANPHAT", 82000, "VND", "2026-06-15"),
    ),
    ListSpec(
        "budgets",
        "Ngân sách",
        (
            Column("Mã ngân sách", "code"),
            Column("Còn lại", "remaining", _decimal),
            Column("Tiền tệ", "currency", _upper),
        ),
        Budget,
        lambda r: (r.code,),
        ("NS-ATLD-2026", 150000000, "VND"),
    ),
)
SPEC_OF: Final[Mapping[str, ListSpec]] = {s.name: s for s in SHEETS}


class Rejected(BaseModel):
    """A row that was not applied, and why (never a value of the row)."""

    model_config = ConfigDict(frozen=True)

    sheet: str
    row: int | None
    reason: str


class ParsedWorkbook(BaseModel):
    """What a workbook says: the lists it holds (a list it leaves out is
    absent, not empty), the rows refused, and why nothing applies when the
    workbook as a whole does not read."""

    model_config = ConfigDict(frozen=True)

    lists: dict[ListName, list[dict[str, Any]]]
    rejected: list[Rejected]
    rejected_total: int
    failure: str | None = None


def fold(text: str) -> str:
    """A header as compared: case, accents and spacing aside."""
    plain = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", plain).strip().casefold()


def _sheet_of(
    sheets: SheetRows, spec: ListSpec
) -> Sequence[tuple[int, Sequence[CellValue]]] | None:
    wanted = fold(spec.sheet)
    return next((rows for name, rows in sheets.items() if fold(name) == wanted), None)


def _label(spec: ListSpec, error: ValidationError) -> str:
    fields = {c.field: c.header for c in spec.columns}
    for detail in error.errors():
        for part in detail.get("loc", ()):
            if part in fields:
                return f"cột “{fields[part]}” không hợp lệ"
    return "dòng không hợp lệ"


def _parse_sheet(
    spec: ListSpec, rows: Sequence[tuple[int, Sequence[CellValue]]], rejected: list[Rejected]
) -> list[dict[str, Any]] | None:
    """The sheet's records, or None when its header lacks a required column
    (the whole sheet refused: a shifted column would misread every row)."""
    if not rows:
        return []
    header_row, header = rows[0]
    at = {fold(str(cell)): i for i, cell in enumerate(header) if cell is not None}
    missing = [c.header for c in spec.columns if c.required and fold(c.header) not in at]
    if missing:
        rejected.append(
            Rejected(sheet=spec.sheet, row=header_row, reason=f"thiếu cột {', '.join(missing)}")
        )
        return None
    records: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], int] = {}
    for number, cells in rows[1:]:
        raw: dict[str, Any] = {}
        try:
            for column in spec.columns:
                index = at.get(fold(column.header))
                cell = cells[index] if index is not None and index < len(cells) else None
                value = column.read(cell)
                if value not in (None, []):
                    raw[column.field] = value
        except ValueError as exc:
            rejected.append(Rejected(sheet=spec.sheet, row=number, reason=str(exc)[:120]))
            continue
        try:
            model = spec.model.model_validate(spec.complete(raw))
        except ValidationError as exc:
            rejected.append(Rejected(sheet=spec.sheet, row=number, reason=_label(spec, exc)))
            continue
        key = spec.key(model)
        if key in seen:
            rejected.append(
                Rejected(sheet=spec.sheet, row=number, reason=f"trùng với dòng {seen[key]}")
            )
            continue
        seen[key] = number
        records.append(model.model_dump(mode="json"))
    if len(records) > MAX_ROWS:
        rejected.append(
            Rejected(sheet=spec.sheet, row=None, reason=f"quá {MAX_ROWS} dòng: chia nhỏ tệp")
        )
        return None
    return records


def parse_workbook(sheets: SheetRows) -> ParsedWorkbook:
    """The lists ``sheets`` holds, sheet by sheet (`SHEETS`)."""
    rejected: list[Rejected] = []
    lists: dict[ListName, list[dict[str, Any]]] = {}
    refused: list[str] = []
    for spec in SHEETS:
        rows = _sheet_of(sheets, spec)
        if rows is None:
            continue
        records = _parse_sheet(spec, rows, rejected)
        if records is None:
            refused.append(spec.sheet)
        else:
            lists[spec.name] = records
    failure = None
    if refused:
        failure = f"trang {', '.join(refused)} không đọc được: xem dòng lỗi"
    elif not lists:
        names = ", ".join(s.sheet for s in SHEETS)
        failure = f"tệp không có trang nào của mẫu ({names})"
    return ParsedWorkbook(
        lists=lists,
        rejected=rejected[:MAX_REJECTED_SHOWN],
        rejected_total=len(rejected),
        failure=failure,
    )


# ------------------------------------------------------------ the new version --


class ListChange(BaseModel):
    """One list of a new version beside the one in force."""

    model_config = ConfigDict(frozen=True)

    list: ListName
    sheet: str
    in_file: bool
    rows: int
    in_force: int
    added: int
    removed: int
    changed: int


class Merged(BaseModel):
    """The whole document a file makes over the version in force, what it
    changes, and the rows of the version in force it can no longer keep."""

    model_config = ConfigDict(frozen=True)

    document: dict[str, Any]
    changes: list[ListChange]
    # Quotations and prices paid of the version in force whose item or
    # supplier the file removed, dropped with them (by sheet, how many).
    dropped: dict[str, int]


def _models(spec: ListSpec, records: Sequence[Mapping[str, Any]]) -> list[BaseModel]:
    return [spec.model.model_validate(r) for r in records]


def merge(
    lists: Mapping[str, Sequence[Mapping[str, Any]]],
    in_force: PurchasingMasterData,
    *,
    version: str,
) -> Merged:
    """The version a file makes: each list it holds replaces the one in force,
    each it leaves out is kept. A quotation or price paid naming an item or a
    supplier the new lists lack goes, and is counted (``dropped``)."""
    new: dict[str, list[BaseModel]] = {}
    for spec in SHEETS:
        if spec.name in lists:
            new[spec.name] = _models(spec, lists[spec.name])
        else:
            new[spec.name] = list(getattr(in_force, spec.name))
    items = {i.code for i in new["items"]}  # type: ignore[attr-defined]
    suppliers = {s.code for s in new["suppliers"]}  # type: ignore[attr-defined]
    dropped: dict[str, int] = {}
    for name in ("quotes", "history"):
        kept = [
            r
            for r in new[name]
            if r.item_code in items and r.supplier_code in suppliers  # type: ignore[attr-defined]
        ]
        if len(kept) != len(new[name]):
            dropped[SPEC_OF[name].sheet] = len(new[name]) - len(kept)
        new[name] = kept
    changes = []
    for spec in SHEETS:
        before = {spec.key(r): r for r in getattr(in_force, spec.name)}
        after = {spec.key(r): r for r in new[spec.name]}
        changes.append(
            ListChange(
                list=spec.name,
                sheet=spec.sheet,
                in_file=spec.name in lists,
                rows=len(after),
                in_force=len(before),
                added=len(after.keys() - before.keys()),
                removed=len(before.keys() - after.keys()),
                changed=sum(1 for k in after.keys() & before.keys() if after[k] != before[k]),
            )
        )
    document = PurchasingMasterData.model_validate(
        {"policy_version": version, **dict(new)}
    ).model_dump(mode="json", by_alias=True)
    return Merged(document=document, changes=changes, dropped=dropped)
