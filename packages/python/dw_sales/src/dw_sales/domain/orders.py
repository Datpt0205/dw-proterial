"""An order case: one customer PO number, from its first revision to confirmation.

The flow it records is WIV-03-012 steps 1-3 and 6-10: a PO is read (every value
with the place on the file it came from), each line's customer code is mapped
to a PRV code, the checks raise findings, the PIC decides each finding and
prepares the order, enters it in Bravo and records the sales-order number, a
different Sales member cross-checks it, and the order is confirmed. DW1
prepares; it never decides.

Rules that hold everywhere in this module:

- **Every value read from a PO carries its anchor** (`anchors.SourceAnchor`):
  a cell, or boxes on a page, in a file named by its sha256.
- **A finding is stamped when it is raised**: its severity and the version of
  the rules that raised it, and so is every check's basis (what it compared
  against). Later steps read the stamp, never today's policy or master data.
- **Status moves only along `transition`**, and each step's own conditions
  (every finding decided, every line mapped, maker is not checker) are
  refused here, in the model, whoever calls it.
- **Every change bumps `case_version`**, so a decision names the version it
  was made on.

Errors name ids, codes and fields, never a value read from a customer's file
(spec decision 8): the models hide their input in validation errors.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import (
    CopperBasis,
    Currency,
    CustomerCode,
    DocumentNo,
    PrvCode,
    Uom,
)
from dw_sales.domain.messages import AttachmentId, Sha256Hex

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# Text as a customer printed it: one line, no control characters, no padding.
# Raw on purpose: a code outside the convert list's alphabet is still what the
# PO says, and it is reported as unmapped rather than refused as unreadable.
_PRINTED_END = r"[^\s\x00-\x1f\x7f]"
PrintedText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        pattern=rf"^{_PRINTED_END}(?:[^\x00-\x1f\x7f]*{_PRINTED_END})?$",
    ),
]
# Who acted: the verified principal's id, never a display name.
ActorId = Annotated[str, Field(pattern=r"^[!-~]{1,254}$")]
# A person's words on a decision: a reason, a source note.
Note = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
# ``<id>@<semver>``: a policy or a parser, as stamped on a case.
VersionRef = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")]

PoHeaderField = Literal["po_no", "revision", "po_date", "currency"]
PoLineField = Literal[
    "line_no",
    "customer_item_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "amount",
    "requested_date",
]


class RegionFlag(StrEnum):
    """Why a value read from a file is not taken on trust (`value_uncertain`).

    Each is a place a person looking at the file would not see the value, or
    would see something else than the reader read.
    """

    HIDDEN_SHEET = "hidden_sheet"
    HIDDEN_ROW = "hidden_row"
    HIDDEN_COLUMN = "hidden_column"
    FONT_MATCHES_FILL = "font_matches_fill"
    FORMULA_WITHOUT_CACHED_VALUE = "formula_without_cached_value"


class FlaggedValue(BaseModel):
    """One value read from a flagged region, by the field it fills."""

    model_config = _FROZEN

    field: str = Field(pattern=r"^[a-z_]{1,32}$")
    flag: RegionFlag


def _require_fields(flags: Iterable[FlaggedValue], allowed: Iterable[str], owner: str) -> None:
    known = set(allowed)
    if unknown := sorted({f.field for f in flags} - known):
        raise ValueError(f"{owner} flags fields it does not have: {unknown}")


class PoHeaderAnchors(BaseModel):
    model_config = _FROZEN

    po_no: SourceAnchor
    revision: SourceAnchor
    po_date: SourceAnchor
    currency: SourceAnchor


class PoHeader(BaseModel):
    """The PO as a whole: the customer's number for it, its revision and date."""

    model_config = _FROZEN

    po_no: PrintedText
    revision: int = Field(ge=0, le=999)
    po_date: date
    currency: Currency
    anchors: PoHeaderAnchors
    flags: tuple[FlaggedValue, ...] = ()

    @model_validator(mode="after")
    def _flags_name_header_fields(self) -> Self:
        _require_fields(self.flags, PoHeaderAnchors.model_fields, "a header")
        return self


class PoLineAnchors(BaseModel):
    model_config = _FROZEN

    line_no: SourceAnchor
    customer_item_code: SourceAnchor
    description: SourceAnchor
    quantity: SourceAnchor
    uom: SourceAnchor
    unit_price: SourceAnchor
    amount: SourceAnchor
    requested_date: SourceAnchor


class PoLine(BaseModel):
    """One line as the PO states it, before anything is mapped or checked."""

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    customer_item_code: PrintedText
    # Empty when the line names its item by code alone.
    description: str = Field(max_length=500, pattern=r"^[^\x00-\x1f\x7f]*$")
    quantity: Decimal = Field(gt=0)
    # The unit as printed. A unit DW1 has no word for is `uom_mismatch` on
    # the line, not a PO that cannot be read.
    uom: str = Field(min_length=1, max_length=16, pattern=r"^[^\s\x00-\x1f\x7f]+$")
    # Zero is a value the price check reports, not a value the reader refuses.
    unit_price: Decimal = Field(ge=0)
    # The line amount as printed: what `line_total_mismatch` adds up.
    amount: Decimal = Field(ge=0)
    requested_date: date
    anchors: PoLineAnchors
    flags: tuple[FlaggedValue, ...] = ()

    @model_validator(mode="after")
    def _flags_name_line_fields(self) -> Self:
        _require_fields(self.flags, PoLineAnchors.model_fields, f"line {self.line_no}")
        return self


class PrintedTotal(BaseModel):
    """The total the PO prints under its lines."""

    model_config = _FROZEN

    amount: Decimal = Field(ge=0)
    anchor: SourceAnchor
    flags: tuple[FlaggedValue, ...] = ()

    @model_validator(mode="after")
    def _flags_name_the_amount(self) -> Self:
        _require_fields(self.flags, ("amount",), "a total")
        return self


class PoDocument(BaseModel):
    """What a reader got out of one attachment, and how it read it."""

    model_config = _FROZEN

    attachment_id: AttachmentId
    attachment_sha256: Sha256Hex
    # The reader that produced it: stamped on the case (spec decision 11).
    parser_version: VersionRef
    header: PoHeader
    lines: tuple[PoLine, ...] = Field(min_length=1)
    # Numbered rows the reader found in the PO table: "Đã đọc N/N dòng".
    rows_printed: int = Field(ge=1)
    # The sheets or pages the lines were read from, in reading order.
    regions: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = Field(min_length=1)
    # Sheets holding something no layout reads: content nobody checked.
    unchecked_regions: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = ()
    # The buyer the file names, when it names one where the reader looks.
    buyer: PrintedText | None = None
    buyer_anchor: SourceAnchor | None = None
    total: PrintedTotal | None = None

    @model_validator(mode="after")
    def _lines_and_anchors_belong(self) -> Self:
        _require_unique_line_numbers(line.line_no for line in self.lines)
        if self.rows_printed < len(self.lines):
            raise ValueError("more lines read than rows printed")
        if (self.buyer is None) != (self.buyer_anchor is None):
            raise ValueError("a buyer and its anchor go together")
        for anchor in self.anchors():
            if (anchor.attachment_id, anchor.attachment_sha256) != (
                self.attachment_id,
                self.attachment_sha256,
            ):
                raise ValueError(f"an anchor points outside attachment {self.attachment_id}")
        return self

    def anchors(self) -> Iterable[SourceAnchor]:
        """Every anchor the document holds."""
        yield from (anchor for _, anchor in self.header.anchors)
        for line in self.lines:
            yield from (anchor for _, anchor in line.anchors)
        if self.buyer_anchor is not None:
            yield self.buyer_anchor
        if self.total is not None:
            yield self.total.anchor


class PrintedBuyer(BaseModel):
    """The buyer a document names, where it names it: how a PO forwarded by
    someone who is not the customer is attributed (by exact name, then Sales
    confirms)."""

    model_config = _FROZEN

    name: PrintedText
    anchor: SourceAnchor


class Unreadable(BaseModel):
    """Why a reader returned no PO: shown to Sales, who then handles the file.

    The reason names fields, rows and cells, never a value read from the file.
    """

    model_config = _FROZEN

    reason: str = Field(min_length=1, max_length=500)
    anchor: SourceAnchor | None = None


# ---------------------------------------------------------------- findings --


class FindingCode(StrEnum):
    """The order checks of the spec's findings table, one code each."""

    CODE_UNMAPPED = "code_unmapped"
    CODE_AMBIGUOUS = "code_ambiguous"
    PRICE_MISMATCH = "price_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    UOM_MISMATCH = "uom_mismatch"
    QUOTATION_MISSING = "quotation_missing"
    LME_BAND_MISMATCH = "lme_band_mismatch"
    MOQ_VIOLATION = "moq_violation"
    PACK_MULTIPLE = "pack_multiple"
    LINE_TOTAL_MISMATCH = "line_total_mismatch"
    VALUE_UNCERTAIN = "value_uncertain"
    CUSTOMER_UNKNOWN = "customer_unknown"
    DUPLICATE_PO = "duplicate_po"
    REQUESTED_DATE_SHORT_LT = "requested_date_short_lt"
    MISSING_NOC_ESF = "missing_noc_esf"
    REVISED_PO = "revised_po"
    REVISION_WITHOUT_BASE = "revision_without_base"
    CUSTOMER_TEMPORARY = "customer_temporary"
    SENDER_UNVERIFIED = "sender_unverified"


# About the PO as a whole.
PO_LEVEL_FINDINGS: Final = frozenset(
    {
        FindingCode.LINE_TOTAL_MISMATCH,
        FindingCode.CUSTOMER_UNKNOWN,
        FindingCode.DUPLICATE_PO,
        FindingCode.MISSING_NOC_ESF,
        FindingCode.REVISED_PO,
        FindingCode.REVISION_WITHOUT_BASE,
        FindingCode.CUSTOMER_TEMPORARY,
        FindingCode.SENDER_UNVERIFIED,
    }
)
# About one line or the PO as a whole: a value in a line or in the header.
EITHER_LEVEL_FINDINGS: Final = frozenset({FindingCode.VALUE_UNCERTAIN})
# The codes a line's own checks raise once its PRV code is known: replaced
# when the code is confirmed and the line is checked again.
ITEM_FINDINGS: Final = frozenset(
    {
        FindingCode.QUOTATION_MISSING,
        FindingCode.PRICE_MISMATCH,
        FindingCode.CURRENCY_MISMATCH,
        FindingCode.LME_BAND_MISMATCH,
        FindingCode.UOM_MISMATCH,
        FindingCode.MOQ_VIOLATION,
        FindingCode.PACK_MULTIPLE,
        FindingCode.REQUESTED_DATE_SHORT_LT,
    }
)
MAPPING_FINDINGS: Final = frozenset({FindingCode.CODE_UNMAPPED, FindingCode.CODE_AMBIGUOUS})


class Severity(StrEnum):
    """``error`` is blocking; ``warning`` is shown. Both need a decision."""

    ERROR = "error"
    WARNING = "warning"


class DispositionKind(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    CORRECTED_BY_SALES = "corrected_by_sales"
    ASK_CUSTOMER = "ask_customer"


class Open(BaseModel):
    """Nobody has decided yet."""

    model_config = _FROZEN

    kind: Literal[DispositionKind.OPEN] = DispositionKind.OPEN


class Accepted(BaseModel):
    """Sales accepts the finding as it stands, for the reason given."""

    model_config = _FROZEN

    kind: Literal[DispositionKind.ACCEPTED] = DispositionKind.ACCEPTED
    reason: Note
    by: ActorId
    at: AwareDatetime


class CorrectedBySales(BaseModel):
    """Sales states the right value, and where it comes from.

    A typed value: whoever typed it is a maker of the case, so they cannot
    cross-check it (spec decision 7).
    """

    model_config = _FROZEN

    kind: Literal[DispositionKind.CORRECTED_BY_SALES] = DispositionKind.CORRECTED_BY_SALES
    value: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    source: Note
    by: ActorId
    at: AwareDatetime


class AskCustomer(BaseModel):
    """The customer is asked to correct the PO (WIV-03-012 step 8)."""

    model_config = _FROZEN

    kind: Literal[DispositionKind.ASK_CUSTOMER] = DispositionKind.ASK_CUSTOMER
    by: ActorId
    at: AwareDatetime


FindingDisposition = Annotated[
    Open | Accepted | CorrectedBySales | AskCustomer, Field(discriminator="kind")
]

_ACCEPT_OR_ASK = frozenset({DispositionKind.ACCEPTED, DispositionKind.ASK_CUSTOMER})
_CORRECT_OR_ASK = frozenset({DispositionKind.CORRECTED_BY_SALES, DispositionKind.ASK_CUSTOMER})
_ACCEPT = frozenset({DispositionKind.ACCEPTED})

# The spec's "Dispositions allowed" column; `open` is always allowed.
ALLOWED_DISPOSITIONS: Final[Mapping[FindingCode, frozenset[DispositionKind]]] = MappingProxyType(
    {
        FindingCode.CODE_UNMAPPED: _CORRECT_OR_ASK,
        FindingCode.CODE_AMBIGUOUS: _CORRECT_OR_ASK,
        FindingCode.PRICE_MISMATCH: _ACCEPT_OR_ASK,
        FindingCode.CURRENCY_MISMATCH: _ACCEPT_OR_ASK,
        FindingCode.UOM_MISMATCH: _ACCEPT_OR_ASK,
        FindingCode.QUOTATION_MISSING: _ACCEPT_OR_ASK,
        FindingCode.LME_BAND_MISMATCH: _ACCEPT_OR_ASK,
        FindingCode.MOQ_VIOLATION: _ACCEPT_OR_ASK,
        FindingCode.PACK_MULTIPLE: _ACCEPT_OR_ASK,
        FindingCode.LINE_TOTAL_MISMATCH: _CORRECT_OR_ASK,
        FindingCode.VALUE_UNCERTAIN: _CORRECT_OR_ASK,
        FindingCode.CUSTOMER_UNKNOWN: frozenset({DispositionKind.CORRECTED_BY_SALES}),
        # None: the case's only exit is `closed(duplicate)`.
        FindingCode.DUPLICATE_PO: frozenset(),
        FindingCode.REQUESTED_DATE_SHORT_LT: _ACCEPT,
        FindingCode.MISSING_NOC_ESF: _ACCEPT,
        FindingCode.REVISED_PO: _ACCEPT,
        FindingCode.REVISION_WITHOUT_BASE: _ACCEPT,
        FindingCode.CUSTOMER_TEMPORARY: _ACCEPT,
        FindingCode.SENDER_UNVERIFIED: _ACCEPT,
    }
)


class Finding(BaseModel):
    """One check that did not pass, with the values it compared, and its decision.

    ``expected`` and ``actual`` are the compared values as text, computed by
    code. Price-bearing codes carry amounts: they reach only holders of
    ``sales.price.read`` (spec decision 8), never an audit event or a log.
    """

    model_config = _FROZEN

    code: FindingCode
    severity: Severity
    line_no: int | None = Field(default=None, ge=1)
    expected: str | None = Field(default=None, max_length=200)
    actual: str | None = Field(default=None, max_length=200)
    # ``<policy_id>@<policy_version>``: the rules this finding was raised under.
    rule_version: VersionRef
    disposition: FindingDisposition = Open()

    @model_validator(mode="after")
    def _level_and_disposition_fit_the_code(self) -> Self:
        if self.code not in EITHER_LEVEL_FINDINGS and (self.code in PO_LEVEL_FINDINGS) != (
            self.line_no is None
        ):
            where = "the PO as a whole" if self.code in PO_LEVEL_FINDINGS else "one line"
            raise ValueError(f"{self.code} is about {where}")
        kind = self.disposition.kind
        if kind is not DispositionKind.OPEN and kind not in ALLOWED_DISPOSITIONS[self.code]:
            raise ValueError(f"{self.code} cannot be {kind}")
        return self

    @property
    def key(self) -> str:
        """``code:line`` (``-`` for the PO): unique on a case, what a decision names."""
        return f"{self.code.value}:{self.line_no or '-'}"

    @property
    def blocking(self) -> bool:
        return self.severity is Severity.ERROR

    @property
    def is_open(self) -> bool:
        return self.disposition.kind is DispositionKind.OPEN


class Capability(StrEnum):
    """What an actor may do that a finding's decision depends on.

    Resolved by the caller from the verified access context (the scope
    ``sales.compliance.ack``) and handed in as a value: the domain never asks
    the platform who holds what.
    """

    ACKNOWLEDGE_EXPORT_CONTROL = "acknowledge_export_control"


class Actor(BaseModel):
    """Who acts on a case, with the capabilities the caller verified."""

    model_config = _FROZEN

    user_id: ActorId
    capabilities: frozenset[Capability] = frozenset()


# ----------------------------------------------------------------- mapping --


class MappingStatus(StrEnum):
    """How a line's customer code becomes a PRV code (labels in CONTEXT.md).

    ``exact``: the convert list has the code. ``candidate``: it does not, and
    exactly one item fits the description; Sales confirms it explicitly.
    ``ambiguous``: several items fit. ``unmapped``: none does.
    ``candidate_confirmed``: Sales confirmed one of the candidates, or typed a
    PRV code that exists in the item master for an unmapped line.
    """

    EXACT = "exact"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"
    CANDIDATE_CONFIRMED = "candidate_confirmed"


class LineMapping(BaseModel):
    model_config = _FROZEN

    status: MappingStatus
    # The code the line is entered with: exact or confirmed lines only.
    prv_code: PrvCode | None = None
    # The items the description fits, as computed; kept after confirmation.
    candidates: tuple[PrvCode, ...] = ()
    confirmed_by: ActorId | None = None
    confirmed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _status_says_what_is_there(self) -> Self:
        status, count = self.status, len(self.candidates)
        if count != len(set(self.candidates)):
            raise ValueError("candidates repeat")
        confirmed = status is MappingStatus.CANDIDATE_CONFIRMED
        if confirmed != (self.confirmed_by is not None and self.confirmed_at is not None):
            raise ValueError("a confirmation names who and when, and only a confirmed line has one")
        if (status in (MappingStatus.EXACT, MappingStatus.CANDIDATE_CONFIRMED)) != (
            self.prv_code is not None
        ):
            raise ValueError(f"a line mapped {status} has the wrong PRV code")
        wrong_count = {
            MappingStatus.EXACT: count != 0,
            MappingStatus.CANDIDATE: count != 1,
            MappingStatus.AMBIGUOUS: count < 2,
            MappingStatus.UNMAPPED: count != 0,
            MappingStatus.CANDIDATE_CONFIRMED: bool(count) and self.prv_code not in self.candidates,
        }[status]
        if wrong_count:
            raise ValueError(f"a line mapped {status} has the wrong candidates")
        return self

    @property
    def ready(self) -> bool:
        """Whether the line can be entered in Bravo."""
        return self.status in (MappingStatus.EXACT, MappingStatus.CANDIDATE_CONFIRMED)

    @property
    def hand_entered(self) -> bool:
        """A PRV code typed by Sales rather than chosen from computed candidates."""
        return self.status is MappingStatus.CANDIDATE_CONFIRMED and not self.candidates

    @property
    def checked_against(self) -> str | None:
        """The item the line's checks ran against: its code, or the one candidate."""
        if self.status is MappingStatus.CANDIDATE:
            return self.candidates[0]
        return self.prv_code


# ------------------------------------------------------------- check basis --

LeadTimeSource = Literal["item_standard", "quotation"]
CheckName = Literal[
    "read",
    "mapping",
    "quotation",
    "price",
    "currency",
    "lme_band",
    "uom",
    "moq",
    "pack",
    "lead_time",
]


class ItemBasis(BaseModel):
    """The item-master values a line was checked against, as they were."""

    model_config = _FROZEN

    prv_code: PrvCode
    uom: Uom | None
    moq: Decimal
    pack_multiple: Decimal
    standard_lead_time_days: int


class QuotationBasis(BaseModel):
    """The valid quotation a line was checked against, as it was."""

    model_config = _FROZEN

    quote_no: DocumentNo
    unit_price: Decimal
    currency: Currency
    uom: Uom | None
    moq: Decimal
    lead_time_days: int
    copper_basis: CopperBasis
    valid_from: date
    valid_to: date


class LmeBasis(BaseModel):
    """The LME month a banded quotation was held to, and its price then."""

    model_config = _FROZEN

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    # None: no price on record for the month, which is itself the finding.
    usd_per_tonne: Decimal | None


class LineBasis(BaseModel):
    """What a line's checks compared against, stamped when they ran.

    Evidence of the decision, never master data: it is not refreshed from the
    catalogue and not served as the current price (spec decision 11).
    """

    model_config = _FROZEN

    # The convert list's code for the customer's code, when it had one.
    convert_prv_code: PrvCode | None = None
    candidates: tuple[PrvCode, ...] = ()
    item: ItemBasis | None = None
    quotation: QuotationBasis | None = None
    lme: LmeBasis | None = None
    lead_time_days: int | None = None
    lead_time_source: LeadTimeSource | None = None
    checks_run: tuple[CheckName, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _lead_time_names_its_source(self) -> Self:
        if (self.lead_time_days is None) != (self.lead_time_source is None):
            raise ValueError("a lead time names where it came from")
        return self


class OrderLine(BaseModel):
    """A PO line with its PRV code, what it was checked against, and its dates."""

    model_config = _FROZEN

    po_line: PoLine
    mapping: LineMapping
    basis: LineBasis
    # max(requested date, received date + lead time): DW1's proposal, labelled
    # as one. None when the line has no item to take a lead time from.
    suggested_delivery_date: date | None = None
    # What Sales confirms to the customer, entered at confirmation.
    confirmed_delivery_date: date | None = None
    # Who agreed a short lead time with PC (outside the portal), and when.
    pc_confirmed_by: ActorId | None = None
    pc_confirmed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _pc_confirmation_names_who_and_when(self) -> Self:
        if (self.pc_confirmed_by is None) != (self.pc_confirmed_at is None):
            raise ValueError("a PC confirmation names who and when")
        return self

    @property
    def line_no(self) -> int:
        return self.po_line.line_no


class LineCheck(BaseModel):
    """One line's checks: what it maps to, what it was compared with, what failed."""

    model_config = _FROZEN

    line: OrderLine
    findings: tuple[Finding, ...] = ()

    @model_validator(mode="after")
    def _findings_are_the_lines(self) -> Self:
        if any(f.line_no != self.line.line_no for f in self.findings):
            raise ValueError(f"a check of line {self.line.line_no} names another line")
        return self


# ---------------------------------------------------------------- revisions --

# What a revised PO is compared on: every value of a line except its number
# and the amount, which follows from quantity and price.
_COMPARED: Final[tuple[PoLineField, ...]] = (
    "customer_item_code",
    "description",
    "quantity",
    "uom",
    "unit_price",
    "requested_date",
)


class LineChange(BaseModel):
    """One value of one line that a revision changed.

    A line the revision adds has every value with ``before`` None; a line it
    drops has every value with ``after`` None.
    """

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    field: PoLineField
    before: str | None
    after: str | None

    @model_validator(mode="after")
    def _is_a_change(self) -> Self:
        if self.before == self.after:
            raise ValueError("a change needs a before and an after that differ")
        return self


def diff_lines(before: Sequence[PoLine], after: Sequence[PoLine]) -> tuple[LineChange, ...]:
    """What changed between two revisions of one PO, line by line number.

    Values are compared as values: ``0.658`` and ``0.6580`` are one price.
    """
    old = {line.line_no: line for line in before}
    new = {line.line_no: line for line in after}
    changes: list[LineChange] = []
    for line_no in sorted(old.keys() | new.keys()):
        was, now = old.get(line_no), new.get(line_no)
        for field in _COMPARED:
            value_before = getattr(was, field) if was is not None else None
            value_after = getattr(now, field) if now is not None else None
            if value_before != value_after:
                changes.append(
                    LineChange(
                        line_no=line_no,
                        field=field,
                        before=_text(value_before),
                        after=_text(value_after),
                    )
                )
    return tuple(changes)


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class SupersededRevision(BaseModel):
    """A revision a later one replaced, kept on the case as it was read."""

    model_config = _FROZEN

    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    received_at: AwareDatetime
    document: PoDocument


# ------------------------------------------------------------------ status --


class OrderStatus(StrEnum):
    """Names and labels in CONTEXT.md; the moves in `_NEXT`."""

    RECEIVED = "received"
    CHECKED = "checked"
    IN_REVIEW = "in_review"
    CORRECTION_REQUESTED = "correction_requested"
    PREPARED = "prepared"
    UPLOADED_TO_BRAVO = "uploaded_to_bravo"
    CROSS_CHECKED = "cross_checked"
    CONFIRMED = "confirmed"
    CHANGE_REVIEW = "change_review"
    CLOSED = "closed"


class CloseReason(StrEnum):
    DUPLICATE = "duplicate"
    NOT_AN_ORDER = "not_an_order"
    SUPERSEDED = "superseded"
    CANNOT_SUPPLY = "cannot_supply"


# warn: an acknowledged `missing_noc_esf` lets the order be confirmed.
# block_confirmation: its presence refuses `confirmed` even when acknowledged.
ExportControlMode = Literal["warn", "block_confirmation"]

_S = OrderStatus
# Before the order is in Bravo: what may still be closed, and where a new
# revision restarts the checks.
BEFORE_UPLOAD: Final = frozenset(
    {_S.RECEIVED, _S.CHECKED, _S.IN_REVIEW, _S.CORRECTION_REQUESTED, _S.PREPARED}
)
# The order is in Bravo: a new revision is a change to apply there.
IN_BRAVO: Final = frozenset(
    {_S.UPLOADED_TO_BRAVO, _S.CROSS_CHECKED, _S.CONFIRMED, _S.CHANGE_REVIEW}
)
# Where lines, mappings and dispositions are decided.
_EDITABLE: Final = frozenset({_S.IN_REVIEW, _S.PREPARED, _S.CHANGE_REVIEW})
# Where the export-control PIC may acknowledge `missing_noc_esf` without
# moving the case: it blocks only `confirmed` (spec decision 9).
_ACKNOWLEDGEABLE: Final = frozenset(
    {_S.IN_REVIEW, _S.PREPARED, _S.UPLOADED_TO_BRAVO, _S.CROSS_CHECKED, _S.CHANGE_REVIEW}
)

_NEXT: Final[Mapping[OrderStatus, frozenset[OrderStatus]]] = MappingProxyType(
    {
        _S.RECEIVED: frozenset({_S.CHECKED, _S.CLOSED}),
        # A status moving to itself: a further revision, or a decision that
        # leaves the case where it is.
        _S.CHECKED: frozenset({_S.IN_REVIEW, _S.CHECKED, _S.CLOSED}),
        _S.IN_REVIEW: frozenset(
            {_S.IN_REVIEW, _S.PREPARED, _S.CORRECTION_REQUESTED, _S.CHECKED, _S.CLOSED}
        ),
        _S.CORRECTION_REQUESTED: frozenset({_S.CHECKED, _S.CLOSED}),
        _S.PREPARED: frozenset(
            {_S.PREPARED, _S.UPLOADED_TO_BRAVO, _S.IN_REVIEW, _S.CHECKED, _S.CLOSED}
        ),
        # -> confirmed only when the rules stamped on the case need no cross-check.
        _S.UPLOADED_TO_BRAVO: frozenset(
            {_S.UPLOADED_TO_BRAVO, _S.CROSS_CHECKED, _S.CONFIRMED, _S.IN_REVIEW, _S.CHANGE_REVIEW}
        ),
        _S.CROSS_CHECKED: frozenset({_S.CROSS_CHECKED, _S.CONFIRMED, _S.CHANGE_REVIEW}),
        _S.CONFIRMED: frozenset({_S.CHANGE_REVIEW}),
        _S.CHANGE_REVIEW: frozenset({_S.CHANGE_REVIEW, _S.UPLOADED_TO_BRAVO}),
        _S.CLOSED: frozenset(),
    }
)


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    """``target`` when the case may move there from ``current``; refused otherwise."""
    if target not in _NEXT[current]:
        raise ConflictError(
            f"an order case cannot move from {current} to {target}",
            details={"from": current.value, "to": target.value},
        )
    return target


class Coverage(BaseModel):
    """What was read and checked on one order: "Đã đọc N/N dòng …"."""

    model_config = _FROZEN

    lines_printed: int
    lines_read: int
    regions: tuple[str, ...]
    checks_run: int
    findings: int


# -------------------------------------------------------------------- case --

# Stamps that belong to a step, by the first status that has them.
_PREPARED_ON: Final = frozenset({_S.PREPARED}) | IN_BRAVO
_CROSS_CHECKED_ON: Final = frozenset({_S.CROSS_CHECKED, _S.CONFIRMED})
MAKER_CHECKER_RULE: Final = "tách nhiệm, WIV-03-012 bước 9"


class OrderCase(BaseModel):
    """One customer PO number, every revision of it, from reading to confirmation."""

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    customer_code: CustomerCode
    # The current revision: the message it came in, when, and what it says.
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    received_at: AwareDatetime
    document: PoDocument
    lines: tuple[OrderLine, ...] = Field(min_length=1)
    status: OrderStatus
    findings: tuple[Finding, ...] = ()
    # Stamped when the case is checked (spec decision 11).
    rules_version: VersionRef | None = None
    catalog_as_of: AwareDatetime | None = None
    cross_check_required: bool | None = None
    export_control_mode: ExportControlMode | None = None
    # Earlier revisions, oldest first, and what the current one changed.
    superseded: tuple[SupersededRevision, ...] = ()
    changes: tuple[LineChange, ...] = ()
    # What a duplicate repeats: a DW1 case, or a sales order in Bravo.
    duplicate_of_case: uuid.UUID | None = None
    duplicate_of_so: DocumentNo | None = None
    # A revision whose base is a sales order Bravo holds, not a DW1 case.
    base_so_no: DocumentNo | None = None
    # WIV-03-012 step 7: the PIC's self-check.
    prepared_by: ActorId | None = None
    prepared_at: AwareDatetime | None = None
    # Step 7 on the Bravo entry: the sales-order number, who keyed it, and
    # their statement that the entry was compared with the PO.
    bravo_so_no: DocumentNo | None = None
    bravo_recorded_by: ActorId | None = None
    bravo_recorded_at: AwareDatetime | None = None
    bravo_entry_compared: bool = False
    # Step 9.
    cross_checked_by: ActorId | None = None
    cross_checked_at: AwareDatetime | None = None
    # The last "trả lại" from the cross-check, kept with its reason.
    returned_reason: Note | None = None
    returned_by: ActorId | None = None
    returned_at: AwareDatetime | None = None
    # Step 10.
    confirmed_by: ActorId | None = None
    confirmed_at: AwareDatetime | None = None
    close_reason: CloseReason | None = None
    closed_by: ActorId | None = None
    closed_at: AwareDatetime | None = None
    # The case that replaced this one: the link `closed(superseded)` carries.
    superseded_by_case: uuid.UUID | None = None

    @model_validator(mode="after")
    def _case_is_consistent(self) -> Self:
        if tuple(line.po_line for line in self.lines) != self.document.lines:
            raise ValueError("the case's lines are the document's lines")
        line_numbers = {line.line_no for line in self.lines}
        if self.status is _S.RECEIVED:
            if self.findings or self.rules_version or self.catalog_as_of:
                raise ValueError("a received case is not checked yet")
        elif None in (
            self.rules_version,
            self.catalog_as_of,
            self.cross_check_required,
            self.export_control_mode,
        ):
            raise ValueError(f"a {self.status} case names the rules and data it was checked with")
        keys = [finding.key for finding in self.findings]
        if len(keys) != len(set(keys)):
            raise ValueError("a finding repeats")
        for finding in self.findings:
            if finding.rule_version != self.rules_version:
                raise ValueError(f"finding {finding.key} was raised under other rules")
            if finding.line_no is not None and finding.line_no not in line_numbers:
                raise ValueError(f"finding {finding.key} names a line the case lacks")
        codes = {finding.code for finding in self.findings}
        duplicate = self.duplicate_of_case is not None or self.duplicate_of_so is not None
        if duplicate != (FindingCode.DUPLICATE_PO in codes):
            raise ValueError("a duplicate names what it duplicates, and only a duplicate does")
        if self.changes and not self.superseded:
            raise ValueError("only a revised case lists changes")
        if (self.superseded_by_case is not None) != (self.close_reason is CloseReason.SUPERSEDED):
            raise ValueError("a case closed as superseded names its successor, and only it does")
        self._stamps_fit_the_status()
        if self.cross_checked_by is not None and self.cross_checked_by in (
            self.prepared_by,
            self.bravo_recorded_by,
        ):
            raise ValueError(f"the cross-checker is a maker of the case ({MAKER_CHECKER_RULE})")
        return self

    def _stamps_fit_the_status(self) -> None:
        status = self.status

        def require(present: bool, stamp: str, *values: object) -> None:
            if present != all(value is not None for value in values) or (
                not present and any(value is not None for value in values)
            ):
                raise ValueError(f"a {status} case {'needs' if present else 'has no'} {stamp}")

        closed = status is _S.CLOSED
        require(closed, "close reason", self.close_reason, self.closed_by, self.closed_at)
        if closed:
            return
        require(status in _PREPARED_ON, "preparer", self.prepared_by, self.prepared_at)
        require(
            status in IN_BRAVO,
            "Bravo entry",
            self.bravo_so_no,
            self.bravo_recorded_by,
            self.bravo_recorded_at,
        )
        if self.bravo_entry_compared != (status in IN_BRAVO):
            raise ValueError(f"a {status} case has the wrong Bravo comparison statement")
        require(
            status in _CROSS_CHECKED_ON and self.cross_check_required is not False,
            "cross-checker",
            self.cross_checked_by,
            self.cross_checked_at,
        )
        require(status is _S.CONFIRMED, "confirmation", self.confirmed_by, self.confirmed_at)

    # ------------------------------------------------------------ reading --

    @property
    def header(self) -> PoHeader:
        return self.document.header

    @property
    def attachment_id(self) -> str:
        return self.document.attachment_id

    @property
    def blocking_findings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.blocking)

    @property
    def makers(self) -> frozenset[str]:
        """Everyone the cross-checker must not be (spec decision 7).

        The preparer, whoever recorded the Bravo entry, and whoever typed a
        value still on the case: a corrected value, or a PRV code typed for an
        unmapped line.
        """
        names = {self.prepared_by, self.bravo_recorded_by}
        names |= {
            f.disposition.by for f in self.findings if isinstance(f.disposition, CorrectedBySales)
        }
        names |= {line.mapping.confirmed_by for line in self.lines if line.mapping.hand_entered}
        return frozenset(name for name in names if name is not None)

    def finding(self, key: str) -> Finding:
        for finding in self.findings:
            if finding.key == key:
                return finding
        raise ConflictError(
            "the case has no such finding", details={"case_id": str(self.case_id), "finding": key}
        )

    def line(self, line_no: int) -> OrderLine:
        for line in self.lines:
            if line.line_no == line_no:
                return line
        raise ConflictError(
            "the case has no such line", details={"case_id": str(self.case_id), "line": line_no}
        )

    def coverage(self) -> Coverage:
        return Coverage(
            lines_printed=self.document.rows_printed,
            lines_read=len(self.lines),
            regions=self.document.regions,
            checks_run=sum(len(line.basis.checks_run) for line in self.lines),
            findings=len(self.findings),
        )

    # ------------------------------------------------------------ the flow --

    def checked(
        self,
        *,
        findings: Sequence[Finding],
        rules_version: str,
        catalog_as_of: datetime,
        cross_check_required: bool,
        export_control_mode: ExportControlMode,
        duplicate_of_case: uuid.UUID | None = None,
        duplicate_of_so: str | None = None,
        base_so_no: str | None = None,
    ) -> OrderCase:
        """received -> checked, with the findings and the rules they were raised under."""
        return self._next(
            transition(self.status, _S.CHECKED),
            findings=tuple(findings),
            rules_version=rules_version,
            catalog_as_of=catalog_as_of,
            cross_check_required=cross_check_required,
            export_control_mode=export_control_mode,
            duplicate_of_case=duplicate_of_case,
            duplicate_of_so=duplicate_of_so,
            base_so_no=base_so_no,
        )

    def start_review(self) -> OrderCase:
        """checked -> in_review: the PIC has the case."""
        return self._next(transition(self.status, _S.IN_REVIEW))

    def dispose(self, key: str, disposition: FindingDisposition, actor: Actor) -> OrderCase:
        """Record the decision on one finding (WIV-03-012 steps 7-8).

        Nothing accepts findings in bulk. A decision in ``prepared`` reopens
        the self-check: the case goes back to ``in_review``. `missing_noc_esf`
        is the export-control PIC's: only an actor with that capability accepts
        it, and accepting it leaves the case where it is.
        """
        finding = self.finding(key)
        kind = disposition.kind
        if not isinstance(disposition, Open):
            if kind not in ALLOWED_DISPOSITIONS[finding.code]:
                raise ConflictError(
                    f"{finding.code} cannot be {kind}",
                    details={"case_id": str(self.case_id), "finding": key, "disposition": kind},
                )
            if disposition.by != actor.user_id:
                raise DomainError(
                    "a decision is recorded as its actor's",
                    details={"case_id": str(self.case_id), "finding": key},
                )
        if finding.code in MAPPING_FINDINGS and kind is DispositionKind.CORRECTED_BY_SALES:
            raise ConflictError(
                "a PRV code is corrected by confirming the line's mapping",
                details={"case_id": str(self.case_id), "finding": key},
            )
        if (
            finding.code is FindingCode.CUSTOMER_UNKNOWN
            and isinstance(disposition, CorrectedBySales)
            and disposition.value != self.customer_code
        ):
            # Every check ran against this customer's master data; another
            # customer is another case, processed again from the message.
            raise ConflictError(
                "customer_unknown is confirmed for the customer the case was checked for",
                details={"case_id": str(self.case_id), "finding": key, "field": "value"},
            )
        replaced = tuple(
            f.model_copy(update={"disposition": disposition}) if f.key == key else f
            for f in self.findings
        )
        # Validated again by `_next`: model_copy alone skips the invariants.
        replaced = tuple(Finding.model_validate(dict(f)) for f in replaced)
        if finding.code is FindingCode.MISSING_NOC_ESF:
            if Capability.ACKNOWLEDGE_EXPORT_CONTROL not in actor.capabilities:
                raise PermissionDeniedError(
                    "only the export-control PIC decides missing_noc_esf",
                    details={"case_id": str(self.case_id), "finding": key},
                )
            if self.status not in _ACKNOWLEDGEABLE:
                raise ConflictError(
                    f"missing_noc_esf cannot be decided in {self.status}",
                    details={"case_id": str(self.case_id), "status": self.status.value},
                )
            return self._next(self.status, findings=replaced)
        return self._edited(findings=replaced)

    def confirm_mapping(
        self, line_no: int, prv_code: str, actor: Actor, at: datetime, recheck: LineCheck
    ) -> OrderCase:
        """The line's PRV code, confirmed by Sales, with the line checked again.

        The code must be one of the line's computed candidates. The one
        exception is a line with none (`code_unmapped`): Sales may type a code
        the item master holds, and ``recheck`` must have been checked against
        exactly that item. Either way the line's item checks are replaced by
        ``recheck``'s, run under this case's rules.
        """
        line = self.line(line_no)
        mapping = line.mapping
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if mapping.status is MappingStatus.EXACT:
            raise ConflictError("an exact mapping is the convert list's", details=details)
        if mapping.candidates and prv_code not in mapping.candidates:
            raise ConflictError("the code is not among the line's candidates", details=details)
        item = recheck.line.basis.item
        if item is None or item.prv_code != prv_code or recheck.line.line_no != line_no:
            raise DomainError("the line was checked again against another item", details=details)
        if any(f.rule_version != self.rules_version for f in recheck.findings):
            raise ConflictError("the line was checked again under other rules", details=details)
        confirmed = LineMapping(
            status=MappingStatus.CANDIDATE_CONFIRMED,
            prv_code=prv_code,
            candidates=mapping.candidates,
            confirmed_by=actor.user_id,
            confirmed_at=at,
        )
        new_line = recheck.line.model_copy(update={"mapping": confirmed})
        source = "candidate" if mapping.candidates else "PRV code typed by Sales (item master)"
        kept: list[Finding] = []
        for f in self.findings:
            if f.line_no != line_no or f.code in EITHER_LEVEL_FINDINGS:
                kept.append(f)
            elif f.code in MAPPING_FINDINGS:
                corrected = CorrectedBySales(value=prv_code, source=source, by=actor.user_id, at=at)
                kept.append(f.model_copy(update={"disposition": corrected}))
        return self._edited(
            lines=tuple(new_line if x.line_no == line_no else x for x in self.lines),
            findings=_in_line_order((*kept, *recheck.findings)),
        )

    def request_correction(self) -> OrderCase:
        """in_review -> correction_requested: the customer is asked (step 8)."""
        if not any(f.disposition.kind is DispositionKind.ASK_CUSTOMER for f in self.findings):
            raise ConflictError(
                "no finding is sent back to the customer",
                details={"case_id": str(self.case_id)},
            )
        return self._next(transition(self.status, _S.CORRECTION_REQUESTED))

    def prepare(self, actor: Actor, at: datetime) -> OrderCase:
        """in_review -> prepared: the PIC's self-check is done (step 7).

        Refused while a finding other than `missing_noc_esf` is open, while
        one is sent back to the customer, or while a line is not mapped to a
        code Bravo can take. Each one is named.
        """
        status = transition(self.status, _S.PREPARED)
        if status is self.status:
            raise ConflictError(
                "the case is already prepared", details={"case_id": str(self.case_id)}
            )
        open_findings = [
            f.key for f in self.findings if f.is_open and f.code is not FindingCode.MISSING_NOC_ESF
        ]
        asked = [f.key for f in self.findings if f.disposition.kind is DispositionKind.ASK_CUSTOMER]
        unmapped = [line.line_no for line in self.lines if not line.mapping.ready]
        if open_findings or asked or unmapped:
            raise ConflictError(
                "the self-check is not complete",
                details={
                    "case_id": str(self.case_id),
                    "open_findings": open_findings,
                    "ask_customer": asked,
                    "lines_not_mapped": unmapped,
                },
            )
        return self._next(status, prepared_by=actor.user_id, prepared_at=at)

    def record_bravo_entry(
        self, so_no: str, actor: Actor, at: datetime, *, entry_compared: bool
    ) -> OrderCase:
        """prepared -> uploaded_to_bravo: the sales-order number, and the PIC's
        statement that the entry was compared with the PO (step 7)."""
        status = transition(self.status, _S.UPLOADED_TO_BRAVO)
        if self.status is not _S.PREPARED:
            raise ConflictError(
                "a Bravo entry is recorded for a prepared case",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        self._require_compared(entry_compared)
        return self._next(
            status,
            bravo_so_no=so_no,
            bravo_recorded_by=actor.user_id,
            bravo_recorded_at=at,
            bravo_entry_compared=True,
        )

    def cross_check(self, actor: Actor, at: datetime) -> OrderCase:
        """uploaded_to_bravo -> cross_checked, by someone who made none of it (step 9)."""
        status = transition(self.status, _S.CROSS_CHECKED)
        if status is self.status:
            raise ConflictError(
                "the case is already cross-checked", details={"case_id": str(self.case_id)}
            )
        self._require_not_a_maker(actor)
        return self._next(status, cross_checked_by=actor.user_id, cross_checked_at=at)

    def return_from_cross_check(self, reason: str, actor: Actor, at: datetime) -> OrderCase:
        """uploaded_to_bravo -> in_review: "trả lại", with the reason.

        The preparation and the Bravo entry are cleared, so the corrected entry
        is recorded and cross-checked again.
        """
        if self.status is not _S.UPLOADED_TO_BRAVO:
            raise ConflictError(
                "only an order awaiting its cross-check is returned",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        return self._next(
            transition(self.status, _S.IN_REVIEW),
            returned_reason=reason,
            returned_by=actor.user_id,
            returned_at=at,
            **_CLEARED_FROM_PREPARED,
        )

    def record_pc_confirmation(self, line_no: int, actor: Actor, at: datetime) -> OrderCase:
        """PC agreed a short lead time for the line (outside the portal)."""
        if not any(
            f.code is FindingCode.REQUESTED_DATE_SHORT_LT and f.line_no == line_no
            for f in self.findings
        ):
            raise ConflictError(
                "the line's requested date is not short",
                details={"case_id": str(self.case_id), "line": line_no},
            )
        if self.status in (_S.CLOSED, _S.CONFIRMED, _S.RECEIVED, _S.CHECKED):
            raise ConflictError(
                f"a PC date is not recorded in {self.status}",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        lines = tuple(
            line.model_copy(update={"pc_confirmed_by": actor.user_id, "pc_confirmed_at": at})
            if line.line_no == line_no
            else line
            for line in self.lines
        )
        return self._next(
            self.status, lines=tuple(OrderLine.model_validate(dict(x)) for x in lines)
        )

    def confirm(self, actor: Actor, at: datetime, delivery_dates: Mapping[int, date]) -> OrderCase:
        """-> confirmed, with the date Sales confirms for every line (step 10).

        From ``cross_checked``; from ``uploaded_to_bravo`` only when the rules
        stamped on the case need no cross-check. Refused while
        `missing_noc_esf` is open, or present at all under
        ``block_confirmation``, and while a short lead time has no PC date.
        """
        status = transition(self.status, _S.CONFIRMED)
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if self.status is _S.UPLOADED_TO_BRAVO and self.cross_check_required:
            raise ConflictError(
                "the order is cross-checked before it is confirmed", details=details
            )
        export = [f for f in self.findings if f.code is FindingCode.MISSING_NOC_ESF]
        if any(f.is_open for f in export):
            raise ConflictError("missing_noc_esf is not acknowledged", details=details)
        if export and self.export_control_mode == "block_confirmation":
            raise ConflictError("export control blocks confirmation", details=details)
        short = {f.line_no for f in self.findings if f.code is FindingCode.REQUESTED_DATE_SHORT_LT}
        if waiting := sorted(
            line.line_no
            for line in self.lines
            if line.line_no in short and line.pc_confirmed_by is None
        ):
            raise ConflictError(
                "a short lead time has no PC-confirmed date", details={**details, "lines": waiting}
            )
        if set(delivery_dates) != {line.line_no for line in self.lines}:
            raise DomainError("every line gets its confirmed delivery date", details=details)
        lines = tuple(
            OrderLine.model_validate(
                {**dict(line), "confirmed_delivery_date": delivery_dates[line.line_no]}
            )
            for line in self.lines
        )
        return self._next(status, lines=lines, confirmed_by=actor.user_id, confirmed_at=at)

    def revise(self, revision: OrderCase) -> OrderCase:
        """The customer's next revision of this PO joins this case and supersedes it.

        ``revision`` is the new revision checked on its own, as a received
        case would be. Before the order is in Bravo the case goes back to
        ``checked``, its preparation cleared. Once it is in Bravo the case goes
        to ``change_review``: the diff is applied in Bravo, no new upload file.
        """
        if revision.status is not _S.CHECKED or FindingCode.REVISED_PO not in {
            f.code for f in revision.findings
        }:
            raise DomainError(
                "a revision joins a case once checked as a revised PO",
                details={"case_id": str(self.case_id)},
            )
        if self.status in IN_BRAVO:
            status = transition(self.status, _S.CHANGE_REVIEW)
            cleared: dict[str, object] = {
                "cross_checked_by": None,
                "cross_checked_at": None,
                "confirmed_by": None,
                "confirmed_at": None,
            }
        else:
            status = transition(self.status, _S.CHECKED)
            cleared = dict(_CLEARED_FROM_PREPARED)
        return self._next(
            status,
            message_id=revision.message_id,
            received_at=revision.received_at,
            document=revision.document,
            lines=revision.lines,
            findings=revision.findings,
            rules_version=revision.rules_version,
            catalog_as_of=revision.catalog_as_of,
            cross_check_required=revision.cross_check_required,
            export_control_mode=revision.export_control_mode,
            superseded=(
                *self.superseded,
                SupersededRevision(
                    message_id=self.message_id, received_at=self.received_at, document=self.document
                ),
            ),
            changes=diff_lines(self.document.lines, revision.document.lines),
            **cleared,
        )

    def apply_change(self, actor: Actor, at: datetime, *, entry_compared: bool) -> OrderCase:
        """change_review -> uploaded_to_bravo: the PIC states the change is applied
        in Bravo and compared with the revised PO. It is cross-checked again."""
        if self.status is not _S.CHANGE_REVIEW:
            raise ConflictError(
                "only a change under review is applied",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        self._require_compared(entry_compared)
        if open_findings := [
            f.key for f in self.findings if f.is_open and f.code is not FindingCode.MISSING_NOC_ESF
        ]:
            raise ConflictError(
                "the revision's findings are not all decided",
                details={"case_id": str(self.case_id), "open_findings": open_findings},
            )
        return self._next(
            transition(self.status, _S.UPLOADED_TO_BRAVO),
            bravo_recorded_by=actor.user_id,
            bravo_recorded_at=at,
        )

    def close(
        self,
        reason: CloseReason,
        actor: Actor,
        at: datetime,
        *,
        superseded_by: uuid.UUID | None = None,
    ) -> OrderCase:
        """-> closed(reason), from any state before the order is in Bravo.

        A duplicate's only exit is ``closed(duplicate)``, which links to what it
        duplicates; ``duplicate`` is refused for a case that duplicates nothing.
        ``superseded`` names the case that replaced this one (a revision that
        arrived before its base and opened a case of its own).
        """
        status = transition(self.status, _S.CLOSED)
        details: dict[str, object] = {"case_id": str(self.case_id), "reason": reason.value}
        is_duplicate = any(f.code is FindingCode.DUPLICATE_PO for f in self.findings)
        if is_duplicate != (reason is CloseReason.DUPLICATE):
            raise ConflictError(
                "a duplicate is closed as a duplicate, and only a duplicate is", details=details
            )
        if (superseded_by is not None) != (reason is CloseReason.SUPERSEDED):
            raise DomainError("closed(superseded) names the case that replaced it", details=details)
        if superseded_by == self.case_id:
            raise DomainError("a case does not supersede itself", details=details)
        return self._next(
            status,
            close_reason=reason,
            closed_by=actor.user_id,
            closed_at=at,
            superseded_by_case=superseded_by,
        )

    # ------------------------------------------------------------- helpers --

    def _require_compared(self, entry_compared: bool) -> None:
        if not entry_compared:
            raise DomainError(
                "the Bravo entry is recorded with the statement that it was compared with the PO",
                details={"case_id": str(self.case_id), "field": "bravo_entry_compared"},
            )

    def _require_not_a_maker(self, actor: Actor) -> None:
        if actor.user_id in self.makers:
            raise ConflictError(
                f"the cross-checker made part of this case ({MAKER_CHECKER_RULE})",
                details={"case_id": str(self.case_id), "rule": "maker_checker"},
            )

    def _edited(self, **changes: object) -> OrderCase:
        """A change to lines, mappings or dispositions, allowed where the PIC decides.

        In ``prepared`` it reopens the self-check: back to ``in_review``,
        the preparation cleared.
        """
        if self.status not in _EDITABLE:
            raise ConflictError(
                f"an order case is not edited in {self.status}",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        if self.status is _S.PREPARED:
            return self._next(
                transition(self.status, _S.IN_REVIEW), **changes, **_CLEARED_FROM_PREPARED
            )
        return self._next(self.status, **changes)

    def _next(self, status: OrderStatus, **changes: object) -> OrderCase:
        # Validated again: `model_copy(update=...)` would skip the invariants.
        return OrderCase.model_validate(
            {**dict(self), **changes, "status": status, "case_version": self.case_version + 1}
        )


_CLEARED_FROM_PREPARED: Final[Mapping[str, object]] = MappingProxyType(
    {
        "prepared_by": None,
        "prepared_at": None,
        "bravo_so_no": None,
        "bravo_recorded_by": None,
        "bravo_recorded_at": None,
        "bravo_entry_compared": False,
    }
)


def _in_line_order(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    """PO-level findings first, then by line, each line's in the order raised."""
    listed = list(findings)
    return tuple(sorted(listed, key=lambda f: (f.line_no or 0, listed.index(f))))


def _require_unique_line_numbers(line_numbers: Iterable[int]) -> None:
    numbers = list(line_numbers)
    if len(numbers) != len(set(numbers)):
        raise ValueError("line numbers repeat")
