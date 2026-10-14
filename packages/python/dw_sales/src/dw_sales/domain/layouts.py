"""A customer's PO form, mapped once by a person and approved by another: which
label on it names which value (ticket 30, dw_sales ADR 0005).

The reader finds a PO's values by their printed labels (`adapters/readers`).
A customer whose form has no layout was routed to Sales with nothing read,
and Sales typed the whole PO. Now a person maps the form once on the
layout-onboarding screen, picking for each field the label the form prints
(`LayoutMapping`), and a second person approves it (`PoLayout`); every later
PO of that form is read by the reader with no model. Where a tenant turns it on
(`sales_order_rules.model_assist.layout_proposal`), a local model pre-fills the
screen (`ModelLayoutProposal`): label names only, never a value.

**What code checks of any mapping**, a person's or the model's, before it can
be proposed (`check_labels`, `plausible`):

1. every label is a cell of the form exactly once, and the table's column
   titles sit on one row;
2. the reader reads the form end to end with it, and the printed total is the
   sum of the lines (no `line_total_mismatch`); a form with no total row has
   no layout;
3. each column is plausible, because ``qty * unit_price = amount`` is
   commutative and a mapping that swaps quantity and unit price passes every
   line and the total: quantities are whole, prices fall within the
   customer's quoted range where it has quotations, a requested date is not
   before the PO date and not the PO date on every line (the order date read
   as the delivery date), and some line's item code is one the convert list
   or the item master knows.

**What a person still does**: maps or corrects the labels, and a second person
approves. The first POs read through a new layout keep every value
`value_uncertain` (`sales_order_rules.layout_onboarding`), for Sales to
confirm field by field, so an approved but wrong mapping cannot repeat
silently.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError
from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.messages import AttachmentId, Sha256Hex
from dw_sales.domain.orders import (
    FlaggedValue,
    PoDocument,
    PoHeaderField,
    PoLineField,
    RegionFlag,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

LayoutKind = Literal["excel", "pdf"]
# How a date typed as text reads on the form (a `datetime.strptime` format).
DateFormat = Literal["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"]
ThousandsSeparator = Literal[",", ".", " ", "none"]
DecimalSeparator = Literal[".", ","]

_Label = Annotated[str, Field(min_length=1, max_length=80)]

HEADER_FIELDS: Final[tuple[PoHeaderField, ...]] = ("po_no", "revision", "po_date", "currency")
COLUMN_FIELDS: Final[tuple[PoLineField, ...]] = (
    "line_no",
    "customer_item_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "amount",
    "requested_date",
)
# A form need not print a revision: its POs are read as revision 0.
OPTIONAL_FIELDS: Final = frozenset({"revision"})


def label_key(text: str) -> str:
    """A label as compared: NFKC, casefolded, single-spaced, no trailing
    colon. The readers compare labels the same way."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(":").rstrip()


class LayoutMapping(BaseModel):
    """Which label on the form names each value, and how its numbers and text
    dates are written. A person maps it on the onboarding screen; a model may
    pre-fill it."""

    model_config = _FROZEN

    kind: LayoutKind
    po_no: _Label
    revision: _Label | None = None
    po_date: _Label
    currency: _Label
    line_no: _Label
    customer_item_code: _Label
    description: _Label
    quantity: _Label
    uom: _Label
    unit_price: _Label
    amount: _Label
    requested_date: _Label
    # A form printing one sheet per page: the label beside the sheet's "n / N".
    page_label: _Label | None = None
    total_label: _Label
    thousands_separator: ThousandsSeparator = ","
    decimal_separator: DecimalSeparator = "."
    date_format: DateFormat = "%d/%m/%Y"
    # A PDF's table titles in print order, every one, mapped or not: what the
    # reader splits a row by. Found by code on the form, never given.
    pdf_columns: tuple[_Label, ...] | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _a_label_names_one_field(self) -> Self:
        named = [label_key(label) for label in self.labels().values()]
        if len(named) != len(set(named)):
            raise ValueError("one label names two fields")
        if self.thousands_separator == self.decimal_separator:
            raise ValueError("thousands and decimals are written with different separators")
        if self.kind == "excel" and self.pdf_columns is not None:
            raise ValueError("only a PDF form names its table's titles in print order")
        if self.kind == "pdf" and self.page_label is not None:
            raise ValueError("a PDF form is read page by page, not by a page label")
        return self

    def header_labels(self) -> dict[PoHeaderField, str]:
        found = {field: getattr(self, field) for field in HEADER_FIELDS}
        return {field: label for field, label in found.items() if label is not None}

    def column_labels(self) -> dict[PoLineField, str]:
        return {field: getattr(self, field) for field in COLUMN_FIELDS}

    def labels(self) -> dict[str, str]:
        """Every label the form must print, by what it names."""
        found: dict[str, str] = {
            str(field): label
            for field, label in [*self.header_labels().items(), *self.column_labels().items()]
        }
        found["total_label"] = self.total_label
        if self.page_label is not None:
            found["page_label"] = self.page_label
        return found


# ------------------------------------------------ what the model proposes --


class ModelLayoutProposal(BaseModel):
    """What one call returns: for each field, the label (a header value's) or
    the title (a table column's) copied from the form, or None where the model
    finds none, and the number and date conventions from closed sets. Flat,
    every key required, so a server decoding against the schema writes each
    one. Named for what they hold, so the schema itself asks for a label and
    never a value."""

    model_config = _FROZEN

    po_no_label: _Label | None
    revision_label: _Label | None
    po_date_label: _Label | None
    currency_label: _Label | None
    line_no_title: _Label | None
    customer_item_code_title: _Label | None
    description_title: _Label | None
    quantity_title: _Label | None
    uom_title: _Label | None
    unit_price_title: _Label | None
    amount_title: _Label | None
    requested_date_title: _Label | None
    page_label: _Label | None
    total_label: _Label | None
    thousands_separator: ThousandsSeparator
    decimal_separator: DecimalSeparator
    date_format: DateFormat

    def mapping(self, kind: LayoutKind) -> LayoutMapping | None:
        """The proposal as a mapping, or None when a required label is missing
        or the proposal is not one (two fields under one label)."""
        answered = self.model_dump()
        values = {field: answered[key] for field, key in PROPOSAL_KEYS.items()}
        required = [*HEADER_FIELDS, *COLUMN_FIELDS, "total_label"]
        if any(values[field] is None for field in required if field not in OPTIONAL_FIELDS):
            return None
        if kind == "pdf":
            values["page_label"] = None
        try:
            return LayoutMapping.model_validate({**values, "kind": kind})
        except ValueError:
            return None


# A mapping's field, by the key the model answers it under: one table, for
# the conversion above and for whoever writes a proposal (an eval, a test).
PROPOSAL_KEYS: Final[dict[str, str]] = {
    **{field: f"{field}_label" for field in HEADER_FIELDS},
    **{field: f"{field}_title" for field in COLUMN_FIELDS},
    "page_label": "page_label",
    "total_label": "total_label",
    "thousands_separator": "thousands_separator",
    "decimal_separator": "decimal_separator",
    "date_format": "date_format",
}


def as_proposal(values: dict[str, object]) -> dict[str, object]:
    """A mapping's fields under the keys a model answers them with."""
    return {
        PROPOSAL_KEYS[field]: value for field, value in values.items() if field in PROPOSAL_KEYS
    }


# --------------------------------------------------------- the form's cells --


class LabelCell(BaseModel):
    """One text cell of the form a label may be: where it is, and its text.

    A workbook's visible text cells, by sheet, row and column; a PDF's first
    page, each text line split into its cells, by line and position. What a
    person would not see (a hidden row, sheet or column, text in its fill
    colour) is never a label: it is also the injection channel."""

    model_config = _FROZEN

    ref: str = Field(min_length=1, max_length=64)
    sheet: str = Field(min_length=1, max_length=64)
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=200)
    # A PDF's ``Label: value`` line, as its label: where a PDF prints a header
    # value and its total. A table's titles are cells of no such line.
    labelled: bool = False


FormRow = tuple[Annotated[str, Field(max_length=200)], ...]


class LayoutSource(BaseModel):
    """The cells of one form a mapping is checked against, and its first rows
    as a person reads them, values included, left to right: what a model is
    shown to tell a label from the value beside it."""

    model_config = _FROZEN

    kind: LayoutKind
    cells: tuple[LabelCell, ...] = Field(max_length=2000)
    rows: tuple[FormRow, ...] = Field(default=(), max_length=60)

    def find(self, label: str, *, labelled: bool | None = None) -> list[LabelCell]:
        """The cells reading ``label``; on a PDF, only those of ``Label:
        value`` lines (``labelled``) or only those of none, where it says."""
        wanted = label_key(label)
        return [
            cell
            for cell in self.cells
            if label_key(cell.text) == wanted and (labelled is None or cell.labelled == labelled)
        ]


_VALUE_LIKE = re.compile(r"^[\d\s.,:/%()+-]*\d[\d\s.,:/%()+-]*$")
# A table's title row holds at least this many cells, none of them a number.
_TITLES = 5


@dataclass(frozen=True, slots=True)
class FormParts:
    """A form's first rows as a model is shown them: the header's label and
    value pairs, the table's title row with its first lines, and what is
    printed under the lines (where a total is). Found by code from the rows'
    shape; every label the model then names is checked against the cells."""

    header: list[list[str]]
    table: list[list[str]]
    footer: list[list[str]]


def form_parts(rows: Sequence[Sequence[str]]) -> FormParts:
    """The header pairs above the first row of five or more cells none of
    which is a number (the table's titles), that row and the two below it,
    and the rows after the lines."""
    titles = next(
        (
            index
            for index, row in enumerate(rows)
            if len(row) >= _TITLES and not any(_VALUE_LIKE.match(cell) for cell in row)
        ),
        None,
    )
    if titles is None:
        return FormParts([list(row) for row in rows[:30]], [], [])
    header: list[list[str]] = []
    for row in rows[:titles]:
        if len(row) < 2:
            continue
        header += [list(row[i : i + 2]) for i in range(0, len(row), 2)]
    lines = titles + 1
    while lines < len(rows) and rows[lines] and _VALUE_LIKE.match(rows[lines][0]):
        lines += 1
    return FormParts(
        header=header,
        table=[list(row) for row in rows[titles : titles + 3]],
        footer=[list(row) for row in rows[lines : lines + 3]],
    )


LayoutProblem = Literal[
    "label_not_found",
    "label_repeated",
    "columns_not_on_one_row",
    "unreadable",
    "no_total",
    "line_total_mismatch",
    "quantity_not_whole",
    "price_out_of_quoted_range",
    "requested_before_po_date",
    "requested_is_po_date",
    "no_item_known",
]


class Problem(BaseModel):
    """Why a mapping is refused: the check, and the field it is about. Names
    fields, never a value read from the form."""

    model_config = _FROZEN

    problem: LayoutProblem
    field: str | None = Field(default=None, max_length=32)

    def __str__(self) -> str:
        return self.problem if self.field is None else f"{self.problem}:{self.field}"


def check_labels(mapping: LayoutMapping, source: LayoutSource) -> list[Problem]:
    """Check 1: each label is one cell of the form, and the column titles are
    on one row (of one sheet)."""
    problems: list[Problem] = []
    places: dict[str, LabelCell] = {}
    columns_named = set(COLUMN_FIELDS)
    for field, label in mapping.labels().items():
        # A PDF prints a header value and its total on a `Label: value` line,
        # and its table's titles on a line of cells: each is looked for there.
        labelled = None if source.kind == "excel" else field not in columns_named
        found = source.find(label, labelled=labelled)
        if not found:
            problems.append(Problem(problem="label_not_found", field=field))
        elif len(found) > 1 and source.kind == "pdf":
            problems.append(Problem(problem="label_repeated", field=field))
        else:
            places[field] = found[0]
    if source.kind == "excel":
        # A label repeated on another sheet is the sheet-per-page form; twice
        # on one sheet is no label at all.
        for field, label in mapping.labels().items():
            sheets = [cell.sheet for cell in source.find(label)]
            if len(sheets) != len(set(sheets)):
                problems.append(Problem(problem="label_repeated", field=field))
    columns = [places[field] for field in COLUMN_FIELDS if field in places]
    if len(columns) == len(COLUMN_FIELDS) and len({(c.sheet, c.row) for c in columns}) != 1:
        problems.append(Problem(problem="columns_not_on_one_row"))
    return problems


def pdf_columns(mapping: LayoutMapping, source: LayoutSource) -> tuple[str, ...] | None:
    """A PDF form's table titles in print order: every cell of the row the
    mapped column titles share, as printed. None when they share none."""
    titles = {label_key(label) for label in mapping.column_labels().values()}
    rows: dict[tuple[str, int], list[LabelCell]] = {}
    for cell in source.cells:
        rows.setdefault((cell.sheet, cell.row), []).append(cell)
    for cells in rows.values():
        if titles <= {label_key(cell.text) for cell in cells}:
            return tuple(cell.text for cell in sorted(cells, key=lambda c: c.column))
    return None


# ------------------------------------------------------------ plausibility --


def plausible(
    document: PoDocument,
    *,
    quoted_prices: Sequence[Decimal],
    known_codes: Iterable[str],
) -> list[Problem]:
    """Check 3, over the lines the reader read with the mapping (module
    docstring). ``quoted_prices``: the customer's quoted unit prices, in any
    currency of theirs; none means the price check cannot run and is not
    claimed. ``known_codes``: the customer's codes the convert list holds and
    the PRV codes of the item master."""
    problems: list[Problem] = []
    lines = document.lines
    if any(line.quantity != line.quantity.to_integral_value() for line in lines):
        problems.append(Problem(problem="quantity_not_whole", field="quantity"))
    if quoted_prices:
        low, high = min(quoted_prices) / 2, max(quoted_prices) * 2
        if any(not low <= line.unit_price <= high for line in lines):
            problems.append(Problem(problem="price_out_of_quoted_range", field="unit_price"))
    po_date = document.header.po_date
    days = [line.requested_date for line in lines if line.requested_date is not None]
    if any(day < po_date for day in days):
        problems.append(Problem(problem="requested_before_po_date", field="requested_date"))
    elif days and all(day == po_date for day in days):
        problems.append(Problem(problem="requested_is_po_date", field="requested_date"))
    known = {code.casefold() for code in known_codes}
    if not any(line.customer_item_code.casefold() in known for line in lines):
        problems.append(Problem(problem="no_item_known", field="customer_item_code"))
    return problems


# --------------------------------------------------------------- the record --

LayoutStatus = Literal["proposed", "approved", "rejected", "superseded"]
PrefillOutcome = Literal["proposed", "refused", "unavailable"]


class LayoutPrefill(BaseModel):
    """What the model pre-fill of a form did, stamped on the message it was
    asked for and on the layout a person proposed from it: the prompt,
    profile and route of the call, the rules whose switch asked, and the
    outcome. ``proposed``: every check passed and the screen opens with the
    mapping; ``refused``: a check failed (the problems say which), and the
    screen opens empty; ``unavailable``: no usable answer."""

    model_config = _FROZEN

    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    rules: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    outcome: PrefillOutcome
    attachment_id: AttachmentId
    mapping: LayoutMapping | None = None
    problems: tuple[str, ...] = Field(default=(), max_length=40)

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        if (self.outcome == "proposed") != (self.mapping is not None):
            raise ValueError("a pre-fill holds a mapping exactly when it was proposed")
        if self.problems and self.outcome != "refused":
            raise ValueError("only a refused pre-fill names problems")
        return self


class LayoutSample(BaseModel):
    """The PO the form was mapped from: what the approver sees beside it."""

    model_config = _FROZEN

    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    attachment_id: AttachmentId
    attachment_sha256: Sha256Hex


class PoLayout(BaseModel):
    """One customer's form, mapped by a person and decided by another.

    Tenant data: stored per tenant and workspace under row security, never
    committed, never read for another tenant. Immutable: each decision
    returns the next record, built through the constructor, so a layout
    approved by its proposer cannot exist, whether just made or read back.

    The decision is a platform approval (`approval_id`, type `sales.layout`,
    dw_sales ADR 0004): the checker decides it there, and its comment stays
    on the platform's decision record, never here.
    """

    model_config = _FROZEN

    layout_id: uuid.UUID
    customer_code: CustomerCode
    version: int = Field(ge=1)
    mapping: LayoutMapping
    sample: LayoutSample
    status: LayoutStatus = "proposed"
    proposed_by: uuid.UUID
    proposed_at: AwareDatetime
    # The model pre-fill the person started from, if any (its stamp).
    prefill: LayoutPrefill | None = None
    # The platform approval the proposal waits on, opened with it.
    approval_id: uuid.UUID
    decided_by: uuid.UUID | None = None
    decided_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _maker_is_never_the_checker(self) -> Self:
        decided = self.status != "proposed"
        if decided != (self.decided_by is not None and self.decided_at is not None):
            raise ValueError("a decided layout names who decided it and when")
        if self.decided_by is not None and self.decided_by == self.proposed_by:
            raise ValueError("the person who proposed a layout cannot decide it")
        return self

    @property
    def kind(self) -> LayoutKind:
        return self.mapping.kind

    @property
    def ref(self) -> str:
        """What a PO read through it is stamped with."""
        return f"po_layout:{self.layout_id}@{self.version}"

    def approve(self, by: uuid.UUID, at: AwareDatetime) -> PoLayout:
        return self._decided("approved", by, at)

    def reject(self, by: uuid.UUID, at: AwareDatetime) -> PoLayout:
        return self._decided("rejected", by, at)

    def supersede(self) -> PoLayout:
        """An approved layout a newer approved one of the form replaces."""
        if self.status != "approved":
            raise ConflictError(
                "only an approved layout is superseded",
                details={"layout_id": str(self.layout_id), "status": self.status},
            )
        return self.model_copy(update={"status": "superseded"})

    def _decided(self, status: LayoutStatus, by: uuid.UUID, at: AwareDatetime) -> PoLayout:
        details: dict[str, object] = {"layout_id": str(self.layout_id), "status": self.status}
        if self.status != "proposed":
            raise ConflictError("the layout is already decided", details=details)
        if by == self.proposed_by:
            raise ConflictError(
                "tách nhiệm: người đề xuất mẫu PO không tự duyệt được",
                details={**details, "rule": "maker_checker"},
            )
        return PoLayout.model_validate(
            {**dict(self), "status": status, "decided_by": by, "decided_at": at}
        )


def flagged_as_new(document: PoDocument) -> PoDocument:
    """``document`` with every value it read flagged `new_layout`: the header,
    each line and the total, so each is `value_uncertain` and Sales confirms
    it field by field (`layout_onboarding.uncertain_first_pos`)."""
    return flagged_everywhere(document, RegionFlag.NEW_LAYOUT)


def flagged_everywhere(document: PoDocument, flag: RegionFlag) -> PoDocument:
    """``document`` with every value it read flagged ``flag``: the header,
    each line and the total, so each is `value_uncertain` until Sales
    confirms it field by field (a new layout's first POs; an OCR reading,
    ticket 27)."""

    def flags(existing: tuple[FlaggedValue, ...], fields: Iterable[str]) -> list[FlaggedValue]:
        added = [FlaggedValue(field=field, flag=flag) for field in fields]
        return [*existing, *added]

    header = document.header.model_dump()
    header["flags"] = flags(document.header.flags, HEADER_FIELDS)
    lines = []
    for line in document.lines:
        dumped = line.model_dump()
        dumped["flags"] = flags(line.flags, COLUMN_FIELDS)
        lines.append(dumped)
    total = None
    if document.total is not None:
        total = document.total.model_dump()
        total["flags"] = flags(document.total.flags, ("amount",))
    return PoDocument.model_validate(
        {**document.model_dump(), "header": header, "lines": lines, "total": total}
    )
