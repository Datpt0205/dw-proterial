"""What a generated artifact says, and the words it is said in (ticket 06).

Code decides every value a file or a draft carries (spec decision 4); the
words around them come from versioned copy, keyed by ``(kind, language)``,
and the layout of the Bravo upload file from its policy. This module holds the
three in their own terms, with no file format in sight:

- **The content model.** `Workbook`/`Sheet` for a spreadsheet (and the PDF the
  quotation is printed from the same sheet), `EmailDraft` for an ``.eml``.
  A string in it is always a string: the writer puts it in a cell as text,
  never as a formula, whoever typed it (G29).
- **The writer port.** `ArtifactWriterPort` turns content into bytes; the
  adapter owns openpyxl, reportlab and the MIME rules.
- **The copy.** `SalesEmailCopy` and `SalesDocumentCopy` (``configs/copy``)
  and `BravoUploadLayout` (``configs/policies``), each pinned by the release
  manifest. A ``(kind, language)`` with no template refuses to render, with
  the reason (G33): there is no fallback to another language, because a
  customer who writes Japanese is not sent Vietnamese by accident.

Templates are `string.Template` (``${name}``). A value is substituted as text
and never read as a template itself, and a template naming a value the draft
does not have refuses to render rather than leaving the placeholder in.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from string import Template
from typing import Annotated, Final, Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_kernel.errors import ConflictError
from dw_platform.domain.messages import EmailAddress
from dw_sales.domain.catalog import Language

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF: Final = "application/pdf"
EML: Final = "message/rfc822"

# The seller's own working language: what an internal sheet or a note to
# Design is written in, whoever the customer is.
INTERNAL: Final[Language] = "vi"

Value = str | int | Decimal | date | None


# ------------------------------------------------------------- the content --


@dataclass(frozen=True, slots=True)
class Sheet:
    """One table: an optional title and label/value lines above it, the
    column headers, the rows, and notes below.

    A sheet with no title and no heading starts with its header row, as an
    import file must; or with its ``banner``, the rows an import template
    prints above its header row, each cell merged over its columns.
    ``formats`` is each column's number format, None for the value's own.
    """

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Value, ...], ...]
    title: str | None = None
    heading: tuple[tuple[str, Value], ...] = ()
    notes: tuple[str, ...] = ()
    banner: tuple[tuple[BannerCell, ...], ...] = ()
    formats: tuple[str | None, ...] = ()


@dataclass(frozen=True, slots=True)
class Workbook:
    """A spreadsheet, or the pages a PDF prints.

    ``stamped_at`` is the time the file's own metadata records. It is a
    decision time from the case, never the clock, so the same case version
    renders to the same bytes: the send draft attaches files byte for byte
    equal to the stored ones.
    """

    sheets: tuple[Sheet, ...]
    language: Language
    stamped_at: datetime


@dataclass(frozen=True, slots=True)
class FileAttachment:
    name: str
    content_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class EmailDraft:
    """A draft a person opens, reads and sends from their own mail client."""

    sender: EmailAddress
    reply_to: EmailAddress
    to: tuple[EmailAddress, ...]
    subject: str
    body: str
    dated: datetime
    attachments: tuple[FileAttachment, ...] = ()


class ArtifactWriterPort(Protocol):
    """Content to bytes. Every string is written as text, never as a formula."""

    def workbook(self, book: Workbook) -> bytes: ...

    def pdf(self, book: Workbook) -> bytes:
        """The first sheet, printed: what the customer reads in the PDF."""
        ...

    def email(self, draft: EmailDraft) -> bytes:
        """An RFC 5322 message marked unsent, so a mail client opens it as a draft."""
        ...


# ----------------------------------------------------------- the formatting --


# English month names, written out here: `%b` prints the server's locale, so
# a customer's document would change with the host it was rendered on.
_EN_MONTHS: Final = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


_DATE_FORMATS: Final[Mapping[Language, Callable[[date], str]]] = {
    "vi": lambda day: f"{day.day:02d}/{day.month:02d}/{day.year}",
    "en": lambda day: f"{day.day:02d} {_EN_MONTHS[day.month - 1]} {day.year}",
    "ja": lambda day: f"{day.year}/{day.month:02d}/{day.day:02d}",
}


def day_text(day: date, language: Language) -> str:
    """One date format per language, in every file and draft, the same on
    every host: digits, and English month names from `_EN_MONTHS`."""
    return _DATE_FORMATS[language](day)


def time_text(at: datetime, language: Language, zone: ZoneInfo) -> str:
    """A time as the seller reads it, in the tenant's time zone (ui-quality
    §8), with the offset it is in written out: "(UTC+7)", "(UTC+5:30)"."""
    local = at.astimezone(zone)
    return f"{day_text(local.date(), language)} {local:%H:%M} ({_utc_offset(local)})"


def _utc_offset(local: datetime) -> str:
    offset = local.utcoffset()
    assert offset is not None  # an aware time, converted to a zone
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


# ----------------------------------------------------------------- the copy --


class TemplateMissingError(ConflictError):
    """No template for this artifact in this language: refused, never replaced
    by another language's (G33)."""

    def __init__(self, kind: str, language: str, *, copy_ref: str) -> None:
        super().__init__(
            "chưa có mẫu cho loại tài liệu này bằng ngôn ngữ của khách hàng",
            details={
                "kind": kind,
                "language": language,
                "copy": copy_ref,
                "reason": "template_missing",
            },
        )


def fill(template: str, values: Mapping[str, object], *, ref: str) -> str:
    """``template`` with ``values`` substituted as text.

    A placeholder with no value refuses to render: a draft that went out with
    ``${confirmed_date}`` in it would be worse than no draft.
    """
    try:
        return Template(template).substitute({k: "" if v is None else v for k, v in values.items()})
    except (KeyError, ValueError) as exc:
        raise ConflictError(
            "mẫu tài liệu dùng một giá trị hồ sơ không có",
            details={"template": ref, "reason": "template_value_unknown", "name": str(exc)},
        ) from None


_Text = Annotated[str, Field(min_length=1, max_length=4000)]
_Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")]
_KindName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")]
_Semver = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class _Words(BaseModel):
    """Fixed phrases code inserts by key: a missing key refuses to render."""

    model_config = _FROZEN

    words: dict[_Key, _Text] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Bound[T: _Words]:
    """One template, with the ``id@version`` an artifact records it under."""

    template: T
    ref: str

    def word(self, key: str, **values: object) -> str:
        text = self.template.words.get(key)
        if text is None:
            raise ConflictError(
                "mẫu tài liệu thiếu một cụm từ",
                details={"template": self.ref, "reason": "template_word_missing", "word": key},
            )
        return fill(text, values, ref=self.ref)

    def fill(self, text: str, values: Mapping[str, object]) -> str:
        return fill(text, values, ref=self.ref)


class EmailTemplate(_Words):
    # One header line: a tenant writes its own copy (ticket 36), and a line
    # break here would leave a draft the mail writer refuses to build.
    subject: Annotated[str, Field(min_length=1, max_length=4000, pattern=r"^[^\x00-\x1f\x7f]+$")]
    body: _Text
    # One line of the draft's list, joined into the body's ``${lines}``.
    line: _Text | None = None


class DocumentTemplate(_Words):
    title: _Text
    # Heading labels and column headers, by the field code decides.
    labels: dict[_Key, _Text] = Field(default_factory=dict)
    columns: dict[_Key, _Text] = Field(default_factory=dict)


def _label(bound: Bound[DocumentTemplate], table: Mapping[str, str], key: str) -> str:
    text = table.get(key)
    if text is None:
        raise ConflictError(
            "mẫu tài liệu thiếu một nhãn",
            details={"template": bound.ref, "reason": "template_label_missing", "label": key},
        )
    return text


def label(bound: Bound[DocumentTemplate], key: str) -> str:
    return _label(bound, bound.template.labels, key)


def column(bound: Bound[DocumentTemplate], key: str) -> str:
    return _label(bound, bound.template.columns, key)


class SenderPolicy(BaseModel):
    """Who a customer draft is from, until Proterial answers (requirements
    doc §3.1): ``drafting_pic`` is the address of the PIC who drafts it and
    sends it from their own mailbox; ``shared_sales`` the shared address.
    Reply-To is always the shared Sales address."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    from_: Literal["drafting_pic", "shared_sales"] = Field(alias="from")
    shared_sales: EmailAddress


def _copy_ref(copy_id: str, version: str) -> str:
    return f"{copy_id}@{version}"


class _Copy(BaseModel):
    model_config = _FROZEN

    schema_version: Literal["1.0"]
    version: _Semver
    # The platform layer is fictional until Proterial's wording arrives as a
    # tenant version (spec decision 14). Stated, so nobody mistakes it.
    mock: bool
    description: str = ""


def _bound[T: _Words](
    table: Mapping[str, Mapping[Language, T]],
    kind: str,
    language: Language,
    *,
    copy_id: str,
    version: str,
) -> Bound[T]:
    template = table.get(kind, {}).get(language)
    if template is None:
        raise TemplateMissingError(kind, language, copy_ref=_copy_ref(copy_id, version))
    return Bound(template, f"{copy_id}.{kind}.{language}@{version}")


class SalesEmailCopy(_Copy):
    """``configs/copy/sales_emails@<version>.yaml``: every draft's words."""

    copy_id: Literal["sales_emails"]
    sender: SenderPolicy
    emails: dict[_KindName, dict[Language, EmailTemplate]]

    @property
    def ref(self) -> str:
        return _copy_ref(self.copy_id, self.version)

    def template(self, kind: str, language: Language) -> Bound[EmailTemplate]:
        return _bound(self.emails, kind, language, copy_id=self.copy_id, version=self.version)


class SalesDocumentCopy(_Copy):
    """``configs/copy/sales_documents@<version>.yaml``: every sheet's words."""

    copy_id: Literal["sales_documents"]
    documents: dict[_KindName, dict[Language, DocumentTemplate]]

    @property
    def ref(self) -> str:
        return _copy_ref(self.copy_id, self.version)

    def template(self, kind: str, language: Language) -> Bound[DocumentTemplate]:
        return _bound(self.documents, kind, language, copy_id=self.copy_id, version=self.version)


# ----------------------------------------------------- the Bravo upload file --

# What an upload row can carry. Code decides each value (`order_artifacts`):
# the case's values, and three of the file's own (`row_no`, the row's number
# from 1; `received_date`, the day the PO came in, in the tenant's zone;
# `usd_rate`, 1 for a USD order and blank otherwise, never a guessed rate).
# The policy decides only which of them the template has, where, under what
# header.
UploadField = Literal[
    "row_no",
    "customer_code",
    "po_no",
    "revision",
    "po_date",
    "received_date",
    "currency",
    "usd_rate",
    "line_no",
    "customer_item_code",
    "prv_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "amount",
    "requested_date",
    "suggested_delivery_date",
    # PC's dates for the row's delivery (ticket 07): the one PC confirmed
    # first and the one it confirms now; blank until PC's answer is recorded.
    "first_confirmed_date",
    "confirmed_date",
]
# What only a case holds, never a PO: PC's dates (ticket 07). No worked
# example (ticket 38) or template sample can bear one out, so the prompts that
# learn a layout or a customer's rules do not offer them (their measured
# versions stand), and a replay leaves a layout column reading one uncompared.
CASE_ONLY_FIELDS: Final[frozenset[UploadField]] = frozenset(
    {"first_confirmed_date", "confirmed_date"}
)
# What a column may read from the customer's master record (`Customer`, the
# fields of the same names): what every sales order of the customer carries.
CustomerAttribute = Literal[
    "order_type", "delivery_term", "delivery_mode", "destination", "shipment_type"
]
# What every upload names: the PO, the line and the quantity, and the item by
# one of its two codes (`UPLOAD_ITEM_FIELDS`). Read by the layout's own check
# and by a draft made from a template (`template_reading`).
REQUIRED_UPLOAD_FIELDS: Final[frozenset[UploadField]] = frozenset({"po_no", "line_no", "quantity"})
# Proterial's Bravo converts the customer's code to its own on import, so its
# template leaves the PRV code blank (B41): either code names the item.
UPLOAD_ITEM_FIELDS: Final[frozenset[UploadField]] = frozenset({"prv_code", "customer_item_code"})


# The longest header or fixed value an upload column holds.
UPLOAD_HEADER_MAX: Final = 200
# How many columns a layout holds, and rows above its header row.
UPLOAD_COLUMNS_MAX: Final = 120
UPLOAD_BANNER_MAX: Final = 10

_Line = Annotated[str, Field(max_length=UPLOAD_HEADER_MAX, pattern=r"^[^\x00-\x1f\x7f]*$")]
# An Excel number format, as the template's own cells carry it.
_NumberFormat = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")]


class UploadColumn(BaseModel):
    """One column of the upload file, at its place in the template, and where
    its value comes from: a field code computes from the case, an attribute of
    the customer's master record, or a fixed text; none of the three, and the
    column is blank for the person who pastes (ticket 02: a column change is
    data, never code). ``number_format`` is the template's own format for the
    column's cells; without one a value prints as it is held."""

    model_config = _FROZEN

    header: _Line
    field: UploadField | None = None
    customer: CustomerAttribute | None = None
    constant: Annotated[_Line, Field(min_length=1)] | None = None
    number_format: _NumberFormat | None = None

    @model_validator(mode="after")
    def _one_source(self) -> UploadColumn:
        if sum(s is not None for s in (self.field, self.customer, self.constant)) > 1:
            raise ValueError("a column reads one source: a field, a customer value or a constant")
        if not self.blank and not self.header.strip():
            raise ValueError("a column that is filled has a header")
        return self

    @property
    def blank(self) -> bool:
        """Nothing is written in the column: the person fills it, or Bravo does."""
        return self.field is None and self.customer is None and self.constant is None


class BannerCell(BaseModel):
    """A text above the header row, merged over columns ``first`` to ``last``
    (1 is A), as the template prints its title and its group labels."""

    model_config = _FROZEN

    text: Annotated[_Line, Field(min_length=1)]
    first: int = Field(ge=1, le=UPLOAD_COLUMNS_MAX)
    last: int = Field(ge=1, le=UPLOAD_COLUMNS_MAX)


class BravoUploadLayout(BaseModel):
    """``configs/policies/sales_bravo_upload@<version>.yaml``.

    Schema 1.0 (the mock layouts 1.0.0 and 1.1.0) is a header row and the
    fields under it. Schema 2.0 (B41, ticket 02) is the template as Bravo's
    "Import Sales Order" prints it: the rows above the header row
    (``banner``, an empty row for a row with nothing on it), then the header
    row, each column at its place with its source, then a row per delivery.
    A 1.0 document has no rows above its headers: one read over a 2.0
    platform version (`read_over`) is not given the platform's.
    """

    model_config = _FROZEN

    schema_version: Literal["1.0", "2.0"]
    policy_id: Literal["sales_bravo_upload"]
    policy_version: _Semver
    mock: bool
    description: str = ""
    sheet_name: Annotated[str, Field(min_length=1, max_length=31, pattern=r"^[^\[\]:*?/\\']+$")]
    banner: tuple[tuple[BannerCell, ...], ...] = Field(default=(), max_length=UPLOAD_BANNER_MAX)
    columns: tuple[UploadColumn, ...] = Field(min_length=1, max_length=UPLOAD_COLUMNS_MAX)

    @model_validator(mode="before")
    @classmethod
    def _no_banner_before_2(cls, data: object) -> object:
        if isinstance(data, Mapping) and data.get("schema_version") == "1.0":
            return {key: value for key, value in data.items() if key != "banner"}
        return data

    @field_validator("columns")
    @classmethod
    def _each_field_once(cls, value: tuple[UploadColumn, ...]) -> tuple[UploadColumn, ...]:
        fields = [column.field for column in value if column.field is not None]
        if len(fields) != len(set(fields)):
            raise ValueError("a field is a column once")
        return value

    @model_validator(mode="after")
    def _names_the_lines(self) -> BravoUploadLayout:
        fields = self.fields
        if not (fields >= REQUIRED_UPLOAD_FIELDS and fields & UPLOAD_ITEM_FIELDS):
            raise ValueError("an upload names the PO, the line, the item and the quantity")
        for number, row in enumerate(self.banner, start=1):
            end = 0
            for cell in row:
                if not end < cell.first <= cell.last <= len(self.columns):
                    raise ValueError(f"banner row {number}: cells overlap or pass the columns")
                end = cell.last
        return self

    @property
    def fields(self) -> frozenset[UploadField]:
        return frozenset(c.field for c in self.columns if c.field is not None)

    @property
    def version(self) -> str:
        """``id@version``, as the release manifest pins it and an artifact records it."""
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        """``key@x.y.z``, as a tenant's version of it is named (ticket 36)."""
        return self.version
