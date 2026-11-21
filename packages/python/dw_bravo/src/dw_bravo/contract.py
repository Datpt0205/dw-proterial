"""What crosses to the Bravo gateway: typed, versioned commands, and nothing else.

ADR 0027 decision 1: DW1 and DW2 reach Bravo through one gateway
(`apps/bravo-gateway`) with typed commands; there is no free-form SQL. This
module is that contract's one owner. The gateway parses a request into one of
these classes and the contexts' HTTP adapters build them;
`contracts/jsonschema/bravo_gateway.json` is generated from them
(`scripts/generate_contracts.py`), so a change here that the schema file does
not carry fails CI.

A command's **content hash** is what the PIC approved: the approval token
(`dw_bravo.approval_token`) carries it, and the gateway recomputes it from
the command it received. Two commands differing in any field, kind or version
hash differently; the same command hashes the same on both sides.

A **write kind** declares what it depends on in Bravo (the screen whose
rules it runs, the tables it writes), so a change Bravo makes to one of them
pauses only that kind (ticket 65).

Every Bravo name below comes from the SO layout (`EDIT_BizDocSO`, layout
8212), the 11-20 UAT trace or Import template 72; none is guessed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Final, Literal

# Bravo's `timestamp` column is SQL Server's rowversion: 8 bytes, written by
# the client as a hex literal. Carried so a write holds the condition the
# client holds: the row is as the PIC saw it, or nothing is written.
_ROWVERSION: Final = re.compile(r"^0x[0-9A-F]{16}$")
_CODE: Final = re.compile(r"^[^\x00-\x1f]{1,64}$")
_TEXT_LIMIT: Final = 512

# pydantic reads this on a stdlib dataclass: the gateway refuses a field the
# contract does not name instead of dropping it.
_STRICT: Final[dict[str, object]] = {"extra": "forbid"}


class ContractError(ValueError):
    """A command that does not satisfy the contract; nothing is sent or run."""


def _rowversion(name: str, value: str) -> None:
    if not _ROWVERSION.match(value):
        raise ContractError(f"{name} must be a rowversion such as 0x00000000000007D1")


def _positive(name: str, value: Decimal) -> None:
    if not value.is_finite() or value <= 0:
        raise ContractError(f"{name} must be a positive number")


def _code(name: str, value: str | None) -> None:
    if value is not None and not _CODE.match(value):
        raise ContractError(f"{name} must be 1-64 printable characters")


def _text(name: str, value: str | None) -> None:
    if value is not None and len(value) > _TEXT_LIMIT:
        raise ContractError(f"{name} is longer than {_TEXT_LIMIT} characters")


# --------------------------------------------------------------------- writes


@dataclass(frozen=True)
class LineRef:
    """One SO line as DW read it: the document, the line, and the line's
    rowversion when the PIC saw it. A line changed since is refused. The
    header's rowversion is not carried: Bravo rewrites the header on every
    save of any line, so an approval bound to it would be spent by a
    colleague's save on another line; the gateway holds the header's
    condition from its own read, as the client does from its load."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT

    so_id: int  # B30BizDoc.Id
    line_id: int  # B30BizDocDetailSO.Id
    line_rowversion: str  # B30BizDocDetailSO.timestamp, as read

    def __post_init__(self) -> None:
        if self.so_id <= 0 or self.line_id <= 0:
            raise ContractError("so_id and line_id are Bravo's positive ids")
        _rowversion("line_rowversion", self.line_rowversion)


@dataclass(frozen=True)
class SetConfirmedDate:
    """ "XN giao hàng": the line's `EstimatedTimeDelivery`; the first confirmed
    date (`OriginalConfirmedDate`) is the layout's to keep, not the command's."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "so.line.set_confirmed_date"
    version: ClassVar[int] = 1

    line: LineRef
    confirmed_date: date


@dataclass(frozen=True)
class SplitPart:
    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT

    quantity: Decimal
    confirmed_date: date | None = None

    def __post_init__(self) -> None:
        _positive("quantity", self.quantity)


@dataclass(frozen=True)
class SplitLine:
    """A line split into parts with Bravo's group fields (`QuantityGroup`,
    `GroupDivi`, `Divide`); the first part stays on the line, each further
    part is a new line. The parts' total is the layout's validator to check."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "so.line.split"
    version: ClassVar[int] = 1

    line: LineRef
    parts: tuple[SplitPart, ...]

    def __post_init__(self) -> None:
        if len(self.parts) < 2:
            raise ContractError("a split has at least two parts")


@dataclass(frozen=True)
class SetQuantity:
    """The line's ordered quantity (`Quantity9`)."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "so.line.set_quantity"
    version: ClassVar[int] = 1

    line: LineRef
    quantity: Decimal

    def __post_init__(self) -> None:
        _positive("quantity", self.quantity)


@dataclass(frozen=True)
class CancelLine:
    """The whole line cancelled (`IsCancel`); a partial cancel is a split,
    then this on the part that goes (ticket 53). What the client writes for a
    cancel is not yet traced (the 11-20 trace holds only a cancel cleared), so
    the gateway refuses this kind until it is (`WriteKind.pending`)."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "so.line.cancel"
    version: ClassVar[int] = 1

    line: LineRef


@dataclass(frozen=True)
class SalesOrderLine:
    """A line as Import template 72 carries it (columns S-AM)."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT

    po_line: str  # POLine
    customer_description: str  # CustomerDescription: Bravo converts the code from it
    quantity: Decimal  # Quantity9
    unit_price: Decimal  # OriginalUnitCost
    item_code: str | None = None  # ItemCode
    customer_prs: str | None = None  # CustomerPRS
    customer_item_code: str | None = None  # CustomerItemCode
    po_request_date: date | None = None  # PORequestDate
    confirmed_date: date | None = None  # OriginalConfirmedDate
    estimated_delivery: date | None = None  # EstimatedTimeDelivery

    def __post_init__(self) -> None:
        _positive("quantity", self.quantity)
        if not self.unit_price.is_finite() or self.unit_price < 0:
            raise ContractError("unit_price must be zero or more")
        for name in ("po_line", "item_code", "customer_prs", "customer_item_code"):
            _code(name, getattr(self, name))
        _text("customer_description", self.customer_description)


@dataclass(frozen=True)
class CreateSalesOrder:
    """A new SO carrying the PO's values (Đạt, 11-20), as template 72's header
    (columns B-R) and lines. `case_ref` names DW's case; it is not Bravo's."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "so.create"
    version: ClassVar[int] = 1

    case_ref: str
    doc_date: date  # DocDate
    currency_code: str  # CurrencyCode
    customer_code: str  # CustomerCode
    po_customer: str  # POCustomer
    lines: tuple[SalesOrderLine, ...]
    indirect_customer_code: str | None = None  # IndirectCustomerCode
    receipt_date: date | None = None  # ReceiptDate
    delivery_term: str | None = None  # DeliveryTerm
    delivery_mode: str | None = None  # DeliveryMode
    delivery_place: str | None = None  # DeliveryPlace
    end_user: str | None = None  # EndUser

    def __post_init__(self) -> None:
        if not self.lines:
            raise ContractError("an SO has at least one line")
        for name in ("case_ref", "currency_code", "customer_code", "indirect_customer_code"):
            _code(name, getattr(self, name))
        for name in ("po_customer", "delivery_term", "delivery_mode", "delivery_place"):
            _text(name, getattr(self, name))
        _text("end_user", self.end_user)


WriteCommand = SetConfirmedDate | SplitLine | SetQuantity | CancelLine | CreateSalesOrder


@dataclass(frozen=True)
class WriteKind:
    """A write the gateway may perform, and what in Bravo it depends on.

    `screen` is the `B00Command` key whose layout's rules the write runs;
    `tables` are the tables it writes. A change to that layout, to a column
    or trigger of those tables, or to a routine the layout calls, concerns
    this kind and no other (ticket 65). `pending` says why the gateway may
    not run the kind yet: what the client writes for it is not measured.
    """

    command: type[Any]
    screen: str
    tables: frozenset[str]
    operation: Literal["update", "insert"]
    pending: str | None = None

    @property
    def key(self) -> str:
        return f"{self.command.kind}@{self.command.version}"


_SO_TABLES: Final = frozenset({"B30BizDoc", "B30BizDocDetailSO"})

WRITE_KINDS: Final[dict[str, WriteKind]] = {
    k.key: k
    for k in (
        # Traced 11-20: the person typed Quantity9, or EstimatedTimeDelivery,
        # and the layout computed the rest of what the client wrote.
        WriteKind(SetConfirmedDate, "EDIT_BizDocSO", _SO_TABLES, "update"),
        WriteKind(SetQuantity, "EDIT_BizDocSO", _SO_TABLES, "update"),
        WriteKind(
            CancelLine,
            "EDIT_BizDocSO",
            _SO_TABLES,
            "update",
            pending="a real cancel's save is not traced (ticket 52 item 2)",
        ),
        # A split's further parts are new lines, and creation is an INSERT:
        # both wait on the shared template before their columns are known.
        WriteKind(
            SplitLine,
            "EDIT_BizDocSO",
            _SO_TABLES,
            "insert",
            pending="a new line's columns wait on the shared template (script 03c)",
        ),
        WriteKind(
            CreateSalesOrder,
            "EDIT_BizDocSO",
            _SO_TABLES,
            "insert",
            pending="a new SO's columns wait on the shared template (script 03c)",
        ),
    )
}


# ---------------------------------------------------------------------- reads


@dataclass(frozen=True)
class CustomerQuery:
    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "customer.get"
    version: ClassVar[int] = 1

    customer_code: str

    def __post_init__(self) -> None:
        _code("customer_code", self.customer_code)


@dataclass(frozen=True)
class ItemQuery:
    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "item.get"
    version: ClassVar[int] = 1

    item_code: str

    def __post_init__(self) -> None:
        _code("item_code", self.item_code)


@dataclass(frozen=True)
class ItemConvertQuery:
    """Bravo's own convert of a customer's description to an item code
    (`usp_B20ItemCustomerDescription_Convert_ItemCode`)."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "item.convert"
    version: ClassVar[int] = 1

    customer_code: str
    customer_description: str

    def __post_init__(self) -> None:
        _code("customer_code", self.customer_code)
        _text("customer_description", self.customer_description)


@dataclass(frozen=True)
class QuotationQuery:
    """The quotation valid on a date, as `usp_B30BizDocDetailSO_GetSQData_HCV`
    finds it: BP code, customer and indirect customer, on the SO's DocDate."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "quotation.lookup"
    version: ClassVar[int] = 1

    bp_code: str
    customer_code: str
    on_date: date
    indirect_customer_code: str | None = None

    def __post_init__(self) -> None:
        for name in ("bp_code", "customer_code", "indirect_customer_code"):
            _code(name, getattr(self, name))


@dataclass(frozen=True)
class DocumentStateQuery:
    """An SO's or a YCBG's state: lines, statuses, rowversions."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "document.state"
    version: ClassVar[int] = 1

    screen: Literal["EDIT_BizDocSO", "EDIT_BizDocRQ"]
    doc_id: int

    def __post_init__(self) -> None:
        if self.doc_id <= 0:
            raise ContractError("doc_id is Bravo's positive id")


@dataclass(frozen=True)
class ComplianceQuery:
    """Black list (`B20BlackList`), LME (`B20LME`) and export control
    (`B20ExportControlList`) as they stand on a date."""

    __pydantic_config__: ClassVar[dict[str, object]] = _STRICT
    kind: ClassVar[str] = "compliance.on_date"
    version: ClassVar[int] = 1

    list_name: Literal["black_list", "lme", "export_control"]
    on_date: date
    code: str | None = None

    def __post_init__(self) -> None:
        _code("code", self.code)


ReadQuery = (
    CustomerQuery
    | ItemQuery
    | ItemConvertQuery
    | QuotationQuery
    | DocumentStateQuery
    | ComplianceQuery
)

READ_KINDS: Final[dict[str, type[Any]]] = {
    f"{q.kind}@{q.version}": q
    for q in (
        CustomerQuery,
        ItemQuery,
        ItemConvertQuery,
        QuotationQuery,
        DocumentStateQuery,
        ComplianceQuery,
    )
}


# ----------------------------------------------------------------- the hash


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Decimal):
        # 1.50 and 1.5 are one quantity: hashed as the same text.
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        raise ContractError("a command carries dates, never times")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_canonical(v) for v in value]
    if value is None or isinstance(value, str | int | bool):
        return value
    raise ContractError(f"cannot hash a value of type {type(value).__name__}")


def canonical_json(command: object) -> str:
    """The command as the one text both sides hash: kind, version, fields."""
    body = _canonical(command)
    assert isinstance(body, dict)
    kind = type(command).kind  # type: ignore[attr-defined]
    version = type(command).version  # type: ignore[attr-defined]
    return json.dumps(
        {"kind": kind, "version": version, "content": body},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def content_hash(command: object) -> str:
    """SHA-256 of `canonical_json`, hex: what an approval token binds."""
    return hashlib.sha256(canonical_json(command).encode("utf-8")).hexdigest()
