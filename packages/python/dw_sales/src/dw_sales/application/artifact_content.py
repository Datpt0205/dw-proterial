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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from string import Template
from typing import Annotated, Final, Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_kernel.errors import ConflictError
from dw_sales.domain.catalog import Language
from dw_sales.domain.messages import EmailAddress

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF: Final = "application/pdf"
EML: Final = "message/rfc822"

# The seller's own working language: what an internal sheet or a note to
# Design is written in, whoever the customer is.
INTERNAL: Final[Language] = "vi"
_LOCAL: Final = ZoneInfo("Asia/Ho_Chi_Minh")

Value = str | int | Decimal | date | None


# ------------------------------------------------------------- the content --


@dataclass(frozen=True, slots=True)
class Sheet:
    """One table: an optional title and label/value lines above it, the
    column headers, the rows, and notes below.

    A sheet with no title and no heading starts with its header row, as an
    import file must.
    """

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Value, ...], ...]
    title: str | None = None
    heading: tuple[tuple[str, Value], ...] = ()
    notes: tuple[str, ...] = ()


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


_DATE_FORMATS: Final[Mapping[Language, str]] = {
    "vi": "%d/%m/%Y",
    "en": "%d %b %Y",
    "ja": "%Y/%m/%d",
}


def day_text(day: date, language: Language) -> str:
    """One date format per language, in every file and draft."""
    return day.strftime(_DATE_FORMATS[language])


def local_time(at: datetime) -> datetime:
    """A time as the seller reads it: Asia/Ho_Chi_Minh (ui-quality §8)."""
    return at.astimezone(_LOCAL)


def time_text(at: datetime, language: Language) -> str:
    local = local_time(at)
    return f"{day_text(local.date(), language)} {local:%H:%M} (UTC+7)"


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
    subject: _Text
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

# What an upload row can carry. Code decides each value (`order_artifacts`);
# the policy decides only which of them the template has, in what order, under
# what header.
UploadField = Literal[
    "customer_code",
    "po_no",
    "revision",
    "po_date",
    "currency",
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
]


class UploadColumn(BaseModel):
    model_config = _FROZEN

    field: UploadField
    header: Annotated[str, Field(min_length=1, max_length=64)]


class BravoUploadLayout(BaseModel):
    """``configs/policies/sales_bravo_upload@<version>.yaml``.

    MOCK until Proterial sends its Bravo import template (requirements doc,
    inputs owed): the file says so, and so does every file made from it.
    """

    model_config = _FROZEN

    schema_version: Literal["1.0"]
    policy_id: Literal["sales_bravo_upload"]
    policy_version: _Semver
    mock: bool
    description: str = ""
    sheet_name: Annotated[str, Field(min_length=1, max_length=31, pattern=r"^[^\[\]:*?/\\']+$")]
    columns: tuple[UploadColumn, ...] = Field(min_length=1)

    @field_validator("columns")
    @classmethod
    def _each_field_once(cls, value: tuple[UploadColumn, ...]) -> tuple[UploadColumn, ...]:
        fields = [column.field for column in value]
        if len(fields) != len(set(fields)):
            raise ValueError("a field is a column once")
        return value

    @model_validator(mode="after")
    def _names_the_lines(self) -> BravoUploadLayout:
        if not {"po_no", "line_no", "prv_code", "quantity"} <= {c.field for c in self.columns}:
            raise ValueError("an upload names the PO, the line, the item and the quantity")
        return self

    @property
    def version(self) -> str:
        """``id@version``, as the release manifest pins it and an artifact records it."""
        return f"{self.policy_id}@{self.policy_version}"
