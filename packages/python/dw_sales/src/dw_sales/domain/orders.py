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
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Final, Literal, NamedTuple, Self, cast
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_platform.domain.messages import AttachmentId, Sha256Hex
from dw_sales.domain.anchors import MessageText, SourceAnchor
from dw_sales.domain.catalog import (
    CopperBasis,
    Currency,
    CustomerCode,
    DocumentNo,
    PrintedText,
    PrvCode,
    Uom,
)
from dw_sales.domain.description_reading import DescriptionReading, GateRoute
from dw_sales.domain.descriptions import StatedAttributes
from dw_sales.domain.legacy_fonts import LegacyEncoding

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# Who acted: the verified principal's id (`AccessContext.principal_id`), never
# a subject or a display name. One type for orders and quotes alike, so a maker
# on one side and a checker on the other are compared as the same kind of id.
ActorId = uuid.UUID
# A person's words on a decision: a reason, a source note.
Note = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
# ``<id>@<semver>``: a policy or a parser, as stamped on a case.
VersionRef = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")]

# ``delivery_term``: the term of delivery the PO prints ("DAP Hanoi"), as
# printed, where a layout maps it (dw_sales ticket 02); a PO need not state one.
PoHeaderField = Literal["po_no", "revision", "po_date", "currency", "delivery_term"]
# The printed total, as a value of the PO's header a correction names: a
# line's `amount` is another value.
TOTAL_FIELD: Final = "total"
# The values that are amounts (spec decision 8): read and typed only with
# `sales.price.read`, never in an audit row or an error.
AMOUNT_FIELDS: Final = frozenset({"unit_price", "amount", TOTAL_FIELD})
# What a line and the PO are known by (finding keys, revisions, the history
# of the PO number). A correction confirms them as read; a different one is
# another line or another PO, which the customer is asked about.
_IDENTITY_FIELDS: Final = frozenset({"line_no", "po_no", "revision"})
# A line's values its PRV code is computed from (`order_checks.map_line`).
_MAPPING_INPUTS: Final = frozenset({"customer_item_code", "description"})
# The header values every line is checked with (`order_checks.check_line`).
_LINE_CHECK_HEADER_INPUTS: Final = frozenset({"po_date", "currency"})
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
    # Read by a model (dw_sales ADR 0005): code found the words and parsed the
    # value, but which field the words fill is the model's reading, and the
    # residual risk is field confusion (`24` of `AWG24`, a reel length read as
    # the quantity, the send date as the required date). Sales confirms each.
    MODEL_READ = "model_read"
    # Read through a PO layout people approved recently (ticket 30): the first
    # POs a new or changed layout reads are confirmed value by value, so a
    # wrong mapping cannot repeat silently (`layout_onboarding`).
    NEW_LAYOUT = "new_layout"
    # The PDF print attached beside the workbook in the same mail prints this
    # value differently (ticket 34): the workbook is the source of record, the
    # print is kept beside it, and a person decides which the customer meant.
    PRINT_DIFFERS = "print_differs"
    # Read by OCR from a scanned page (ticket 27): what the engine saw is not
    # what the page says until a person compares them, whatever its confidence.
    OCR = "ocr"
    # Read from a file locked with a password, which the reader sandbox opened
    # with a password its own mail carries (ticket 17): ClamAV could not scan
    # inside it, and every value read still waits for a person (Đạt, 11-13).
    OPENED_WITH_PASSWORD = "opened_with_password"
    # The file prints no such value (ticket 18: a customer portal's export
    # prints no price and no currency). DW1 holds the currency the PO layout
    # states, and zero for a price, beside the value it stands with; Sales
    # confirms or types it.
    NOT_PRINTED = "not_printed"
    # Its words ("1.500 m", "05/11/2026", a bare "$") read one way only by
    # the customer's notation record, which Sales' earlier confirmations
    # settled (ticket 37): the document itself does not say, so a person
    # sees which record read it, and changes the record if it is wrong.
    NOTATION_FROM_RECORD = "notation_from_record"


class FlaggedValue(BaseModel):
    """One value read from a flagged region, by the field it fills."""

    model_config = _FROZEN

    field: str = Field(pattern=r"^[a-z_]{1,32}$")
    flag: RegionFlag
    # A `model_read` value's probability from the call's tokens (ticket 44,
    # `dw_agent_runtime.model.scoring`); None: the call gave none, or the
    # flag is not a model's. Nothing without one applies itself.
    confidence: float | None = Field(default=None, ge=0, le=1)
    # What code's gate did with it (ticket 44, `po_body_autonomy`): the
    # stamp its labelled case carries. None: no gate saw it.
    gate: GateRoute | None = None


class LegacyText(BaseModel):
    """One value read from text typed in a TCVN3 or VNI font, by the field it
    fills: its letters are not what the customer sees (`legacy_encoding`), so
    nothing is matched on it."""

    model_config = _FROZEN

    field: str = Field(pattern=r"^[a-z_]{1,32}$")
    encoding: LegacyEncoding


def _require_fields(
    flags: Iterable[FlaggedValue | LegacyText], allowed: Iterable[str], owner: str
) -> None:
    known = set(allowed)
    if unknown := sorted({f.field for f in flags} - known):
        raise ValueError(f"{owner} flags fields it does not have: {unknown}")


class ValueCorrection(BaseModel):
    """The value Sales typed for one field a `value_uncertain` flagged.

    Kept beside the value as read, which stays the evidence. ``value`` is the
    field's value as text, validated as that field's type (a Decimal, a date,
    a unit, text) by the line or header it corrects. Whoever typed it is a
    maker of the case (spec decision 7).
    """

    model_config = _FROZEN

    field: str = Field(pattern=r"^[a-z_]{1,32}$")
    value: PrintedText
    by: ActorId
    at: AwareDatetime


# What a customer's change request may change on a line (ticket 27): the
# fields `domain.change_requests.ChangeField` names.
ChangedField = Literal["quantity", "requested_date"]


class AppliedChange(BaseModel):
    """A value of a line the customer asked to change by mail, which a person
    confirmed (dw_sales ADR 0010 decision 2, ticket 27). It replaces the
    value as read, or as corrected, where the line is entered; the request it
    came from keeps where the mail asks it. Whoever confirmed it is a maker of
    the case, as one who types a value is (spec decision 7)."""

    model_config = _FROZEN

    field: ChangedField
    value: PrintedText
    request_id: uuid.UUID
    by: ActorId
    at: AwareDatetime


# The values of a line PC's answer is given for (ticket 07): a person who
# changes one (a correction, a change the customer asked) drops the answer,
# and PC is asked again.
_PC_INPUTS: Final = frozenset({"quantity", "requested_date"})
# How many deliveries PC may split one line into.
PC_DELIVERIES_MAX: Final = 99


class PcDelivery(BaseModel):
    """One delivery of a line as PC confirmed it (ticket 07): how much, the
    date PC confirmed first for it (Bravo's "Ngày XN giao hàng lần đầu") and
    the date PC confirms now ("Ngày XN giao hàng"). A re-confirmation by PC
    changes ``date`` and keeps ``first_date``."""

    model_config = _FROZEN

    quantity: Decimal = Field(gt=0)
    first_date: date
    date: date


class PcAnswer(BaseModel):
    """PC's answer for one line, recorded by the person who read it: the
    line's deliveries, which add up to the line's quantity. A line delivered
    once that PC splits over several dates is several deliveries, each a row
    of the paste sheet; a line the PO prints split is confirmed schedule by
    schedule, one delivery per printed schedule, in their order. No delivery
    at all: PC cancelled the whole line, which only Proterial's own change
    does (ticket 10, `OrderLine.cancelled`)."""

    model_config = _FROZEN

    deliveries: tuple[PcDelivery, ...] = Field(max_length=PC_DELIVERIES_MAX)
    by: ActorId
    at: AwareDatetime

    @property
    def quantities(self) -> tuple[Decimal, ...]:
        return tuple(d.quantity for d in self.deliveries)


class PcRequest(BaseModel):
    """Sales asked PC for the delivery dates of ``lines`` (ticket 07): who
    recorded it, and when, the moment the case's wait on PC begins. Open until
    each of those lines has PC's answer recorded at or after ``at``."""

    model_config = _FROZEN

    lines: tuple[int, ...] = Field(min_length=1)
    by: ActorId
    at: AwareDatetime

    def answered(self, lines: Iterable[OrderLine]) -> bool:
        """Whether every line asked has PC's answer since the request."""
        found = {line.line_no: line.pc_answer for line in lines}
        return all(
            (answer := found.get(no)) is not None and answer.at >= self.at for no in self.lines
        )


class DesignRequest(BaseModel):
    """Sales asked Design to create a PRV code for line ``line_no``, which no
    item fits (ticket 06): who recorded the request sent, and when, the
    moment the case's wait on Design for that line begins. Open while the
    line has no code; the code Design names maps it only as Sales confirms
    it (`confirm_mapping`), which ends the wait."""

    model_config = _FROZEN

    line_no: int = Field(ge=1, le=9999)
    by: ActorId
    at: AwareDatetime


def reconfirmed(
    line: OrderLine,
    deliveries: Sequence[tuple[Decimal, date]],
    by: ActorId,
    at: datetime,
) -> PcAnswer:
    """PC's answer for ``line`` from ``deliveries`` (each quantity with PC's
    date), keeping the date first confirmed for it (Bravo's "Ngày XN giao
    hàng lần đầu"): PC's first dates where PC answered the line before, else
    the dates Sales confirmed it with (a line confirmed without PC's
    answer); delivery by delivery while the quantities stay as they were;
    split anew, every delivery keeps the line's earliest first date; with
    nothing confirmed before, PC's dates are the first ones (ticket 07). The
    one owner of the rule, for an answer before the order is in Bravo and
    for one an update loop applies (tickets 29 and 10)."""
    before = line.pc_answer
    held = (
        tuple((d.quantity, d.first_date) for d in before.deliveries)
        if before is not None
        else line.confirmed_deliveries()
    )
    quantities = tuple(quantity for quantity, _ in deliveries)
    if not held:
        firsts = [day for _, day in deliveries]
    elif tuple(quantity for quantity, _ in held) == quantities:
        firsts = [first for _, first in held]
    else:
        firsts = [min(first for _, first in held)] * len(deliveries)
    return PcAnswer(
        deliveries=tuple(
            PcDelivery(quantity=quantity, first_date=first, date=day)
            for (quantity, day), first in zip(deliveries, firsts, strict=True)
        ),
        by=by,
        at=at,
    )


# ------------------------------------------------- the update loop (ticket 29) --

# Where an order already in Bravo stands in the BA's step 6 (dw_sales ADR 0010
# decision 3): a change the PIC confirmed waits to be asked of PC (6-DW2),
# then on PC; PC's answer is drafted back to the customer (6-DW4 or 6-DW3),
# then the case waits on the customer; once they accept, the Bravo update is
# approved and entered (6.2-SP) and the order is confirmed again (6.3).
UpdateStep = Literal["ask_pc", "waiting_pc", "answer_customer", "waiting_customer", "bravo_update"]
# What a person records the customer answered (the BA's "Khách quyết định?").
CustomerAnswer = Literal["keep", "accept", "ask_pc_again"]
# Code's comparison of PC's answer with what was asked: PC can do it (6-DW4),
# or PC proposes otherwise (6-DW3). Never a model's.
PcVerdict = Literal["can_do", "proposes"]
_ANSWERED: Final = frozenset({"answer_customer", "waiting_customer", "bravo_update"})
# Why Proterial itself changes a confirmed order (ticket 10, the BA's 6.1B):
# PC has no capacity, the goods failed inspection (NG), stock is short, or
# another reason Sales tells the customer in its own words.
InternalReason = Literal["overcapacity", "ng", "short_stock", "other"]
# The most lines one internal change holds: a whole PO of customer 1's size.
INTERNAL_LINES_MAX: Final = 300


class LoopLine(BaseModel):
    """One line of the order a change asks about, in the update loop: the
    changes the PIC confirmed (one per field, held apart from the line until
    the customer accepts), and PC's answer for the values asked. PC's answer
    here names PC's dates only (``first_date`` is ``date``): the line's own
    first confirmed date is kept when the update is applied (`reconfirmed`).
    A line of Proterial's own change (ticket 10) holds PC's answer and, where
    PC cuts the line, the quantity it cuts to; a date moved or a line split
    changes no value the customer ordered, so it holds no change, nor does a
    line PC cancels whole, whose answer gives no delivery."""

    model_config = _FROZEN

    line_no: int = Field(ge=1, le=99_999)
    changes: tuple[AppliedChange, ...] = Field(default=(), max_length=2)
    pc_answer: PcAnswer | None = None

    @model_validator(mode="after")
    def _one_change_per_field(self) -> Self:
        fields = [c.field for c in self.changes]
        if len(fields) != len(set(fields)):
            raise ValueError(f"line {self.line_no} is asked two values of one field")
        return self


class BravoUpdateApproval(BaseModel):
    """The PIC's approval of the exact Bravo update file (6.2-SP; ADR 0026 as
    amended 2026-11-13): the file rendered at ``case_version``, by its id and
    hash. What is entered in Bravo is that file; until Bravo's write API
    exists a person imports it, and records it entered."""

    model_config = _FROZEN

    artifact_id: uuid.UUID
    sha256: Sha256Hex
    case_version: int = Field(ge=1)
    by: ActorId
    at: AwareDatetime


class UpdateLoop(BaseModel):
    """A change on an order already in Bravo, from the PIC's confirmation to
    the order confirmed again (ticket 29). One per case, from one change
    request, or from Proterial's own change (``reason``, ticket 10); its step
    says what it waits on and ``since`` when it began waiting there, the
    clock a reminder reads."""

    model_config = _FROZEN

    request_id: uuid.UUID
    step: UpdateStep
    since: AwareDatetime
    lines: tuple[LoopLine, ...] = Field(min_length=1, max_length=INTERNAL_LINES_MAX)
    # Stamped by code when PC's answer is in for every line, and kept: what
    # the draft to the customer says does not change after it is drafted.
    verdict: PcVerdict | None = None
    approval: BravoUpdateApproval | None = None
    # Why, when the change is Proterial's own (ticket 10): no customer asked
    # it, so the loop begins at its Bravo update with PC's answer for every
    # line, nothing is compared with what was asked, and the customer is
    # told (`internal_change_notice`). None: a customer's change.
    reason: InternalReason | None = None

    @model_validator(mode="after")
    def _loop_is_consistent(self) -> Self:
        numbers = [line.line_no for line in self.lines]
        if len(numbers) != len(set(numbers)):
            raise ValueError("the update loop names a line twice")
        if any(c.request_id != self.request_id for line in self.lines for c in line.changes):
            raise ValueError("the update loop holds another request's change")
        answered = [line.pc_answer is not None for line in self.lines]
        if self.reason is not None:
            if self.step != "bravo_update" or not all(answered) or self.verdict is not None:
                raise ValueError(
                    "Proterial's own change is at its Bravo update, PC's answer in for every"
                    " line and nothing compared"
                )
            if any(c.field != "quantity" for line in self.lines for c in line.changes):
                raise ValueError("Proterial's own change cuts a quantity, or changes no value")
        elif any(not line.changes for line in self.lines):
            raise ValueError("a customer's change names what it asks of every line")
        elif self.step in _ANSWERED:
            if not all(answered) or self.verdict is None:
                raise ValueError("PC's answer is in for every line once drafted to the customer")
        elif self.verdict is not None or (self.step == "ask_pc" and any(answered)):
            raise ValueError(f"an update loop at {self.step} has no answer from PC yet")
        elif self.step == "waiting_pc" and all(answered):
            raise ValueError("PC answered every line: the loop is past waiting on PC")
        if self.approval is not None and self.step != "bravo_update":
            raise ValueError("only the Bravo update is approved")
        return self

    def line(self, line_no: int) -> LoopLine | None:
        return next((x for x in self.lines if x.line_no == line_no), None)


# ------------------------------------- the customer's agreement (ticket 28) --

# dw_sales ADR 0011: the confirmation leaves (`confirmation_sent`), then the
# customer agrees in words (`accepted`) or by staying silent past their days
# (`implied`), and a person records which. DW1 never moves the case itself.
AgreementHow = Literal["accepted", "implied"]
# How a customer's days of silence are counted: every day, or Monday to
# Friday only (no tenant holiday calendar exists yet), and from which day.
DayCount = Literal["calendar", "business"]
CountedFrom = Literal["confirmation_sent", "po_date"]
# Mon-Fri, `date.weekday()` order: Saturday is 5.
_FIRST_WEEKEND_DAY: Final = 5


class ImpliedTerm(BaseModel):
    """A customer's silence that counts as agreement: after this many days,
    counted this way, from that day (the order rules' `implied_acceptance`,
    one per customer, none by default)."""

    model_config = _FROZEN

    days: int = Field(ge=1, le=60)
    day_count: DayCount = "calendar"
    counted_from: CountedFrom = "confirmation_sent"

    def implied_from(self, sent_at: datetime, po_date: date, zone: ZoneInfo) -> datetime:
        """The first instant silence counts as agreement: midnight, local
        time, after the last day the customer has. The start day itself is
        not counted; a business day is Monday to Friday."""
        day = po_date if self.counted_from == "po_date" else sent_at.astimezone(zone).date()
        counted = 0
        while counted < self.days:
            day += timedelta(days=1)
            if self.day_count == "calendar" or day.weekday() < _FIRST_WEEKEND_DAY:
                counted += 1
        return datetime.combine(day + timedelta(days=1), time(0), tzinfo=zone)


class ConfirmationSent(BaseModel):
    """The confirmation that left (ADR 0011): when (the clock of implied
    acceptance), the sent copy it was recorded from when a person recorded
    it from one, and, where the customer has days of silence in the rules
    stamped on the case, the term and the instant silence counts as
    agreement. No term: never implied, whatever the wait."""

    model_config = _FROZEN

    sent_at: AwareDatetime
    message_id: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")
    term: ImpliedTerm | None = None
    implied_from: AwareDatetime | None = None

    @model_validator(mode="after")
    def _implied_with_its_term(self) -> Self:
        if (self.term is None) != (self.implied_from is None):
            raise ValueError("an implied acceptance names its term, and only then its instant")
        return self


class CustomerAgreement(BaseModel):
    """The customer agreed to the confirmation, as a person recorded it:
    in words (`accepted`, from one of their replies on the case when the
    person recorded it from one, with the sentences DW1 located there), or by
    silence past their days (`implied`)."""

    model_config = _FROZEN

    how: AgreementHow
    by: ActorId
    at: AwareDatetime
    message_id: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")
    quotes: tuple[Annotated[str, Field(min_length=1, max_length=400)], ...] = Field(
        default=(), max_length=3
    )

    @model_validator(mode="after")
    def _silence_quotes_nothing(self) -> Self:
        if self.how == "implied" and (self.message_id is not None or self.quotes):
            raise ValueError("silence names no reply")
        if self.quotes and self.message_id is None:
            raise ValueError("a quote names the reply it is from")
        return self


def _require_corrections(
    corrections: Sequence[ValueCorrection], flagged: frozenset[str], owner: str
) -> None:
    fields = [c.field for c in corrections]
    if len(fields) != len(set(fields)):
        raise ValueError(f"{owner} corrects a field twice")
    if unflagged := sorted(set(fields) - flagged):
        raise ValueError(f"{owner} corrects fields nothing flagged: {unflagged}")


def _with_values[M: BaseModel](
    model: M, corrections: Iterable[ValueCorrection | AppliedChange]
) -> M:
    """``model`` holding each correction's value, validated as its field's type."""
    typed = {c.field: c.value for c in corrections}
    if not typed:
        return model
    return type(model).model_validate({**dict(model), **typed})


def value_with_correction[M: BaseModel](model: M, correction: ValueCorrection) -> M:
    """``model`` (a PO line or header as read) holding ``correction``'s value,
    validated as its field's type: what a labelled case compares the value
    read with (ticket 43)."""
    return _with_values(model, [correction])


def _keeps_identity(before: BaseModel, after: BaseModel, owner: str) -> None:
    for field in _IDENTITY_FIELDS & type(before).model_fields.keys():
        if getattr(before, field) != getattr(after, field):
            raise ValueError(f"{owner} corrects its {field}, which is who it is")


class PoHeaderAnchors(BaseModel):
    model_config = _FROZEN

    po_no: SourceAnchor
    revision: SourceAnchor
    po_date: SourceAnchor
    currency: SourceAnchor
    delivery_term: SourceAnchor | None = None

    def stated(self) -> Iterator[tuple[str, SourceAnchor]]:
        """Each value's name and anchor, a value the PO does not state (its
        delivery term) left out."""
        return ((name, anchor) for name, anchor in self if anchor is not None)


class PoHeader(BaseModel):
    """The PO as a whole: the customer's number for it, its revision and date."""

    model_config = _FROZEN

    po_no: PrintedText
    revision: int = Field(ge=0, le=999)
    po_date: date
    currency: Currency
    anchors: PoHeaderAnchors
    flags: tuple[FlaggedValue, ...] = ()
    legacy: tuple[LegacyText, ...] = ()
    # As printed, words and place ("FCA Haiphong"); None where the PO states
    # none or its layout maps none. Compared with the customer's own term by
    # `order_checks.check_customer`, never written over it (ticket 02).
    delivery_term: PrintedText | None = None

    @model_validator(mode="after")
    def _flags_name_header_fields(self) -> Self:
        _require_fields((*self.flags, *self.legacy), PoHeaderAnchors.model_fields, "a header")
        if (self.delivery_term is None) != (self.anchors.delivery_term is None):
            raise ValueError("a delivery term is read with the place it is printed")
        return self

    @property
    def flagged(self) -> frozenset[str]:
        """The fields read from a flagged region."""
        return frozenset(flag.field for flag in self.flags)


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


class DeliverySchedule(BaseModel):
    """One delivery of a line's quantity: how much, on which requested date,
    and where the PO prints it (ticket 21). A schedule row under the line, or
    one entry of a "date: quantity" list in its date cell: the date's cell."""

    model_config = _FROZEN

    quantity: Decimal = Field(gt=0)
    requested_date: date
    anchor: SourceAnchor


class LinePo(BaseModel):
    """The PO number a line prints for itself (ticket 18): a customer portal's
    export puts one PO number on every row. Where a line has one, it is the
    line's PO number, and the PO's own (`PoHeader.po_no`) is the first line's.
    Intake opens one case per PO number (ticket 19, `po_groups`), each dated
    by its own first line's ``po_date`` where the file prints one per row."""

    model_config = _FROZEN

    po_no: PrintedText
    anchor: SourceAnchor
    # The PO date the line's row prints, and where (ticket 19); None: the
    # file prints the date once, the PO's.
    po_date: date | None = None
    po_date_anchor: SourceAnchor | None = None

    @model_validator(mode="after")
    def _a_date_names_its_cell(self) -> Self:
        if (self.po_date is None) != (self.po_date_anchor is None):
            raise ValueError("a line's PO date and its anchor go together")
        return self


class PoLine(BaseModel):
    """One line as the PO states it, before anything is mapped or checked.

    Its delivery schedules are `schedules`: the one ``quantity`` on the one
    ``requested_date`` the line prints, or the ones the PO prints apart from
    the line, as rows under it or a "date: quantity" list in its date cell
    (``printed_schedules``, ticket 21). Then ``quantity`` stays the line
    quantity as printed, which the schedules are checked to add up to
    (`order_checks.check_document`), and ``requested_date`` is the first
    schedule's date, read from its cell.

    A line whose date cell is blank, "date to follow", has ``requested_date``
    None and no schedule (ticket 34): its anchor is the blank cell, or the
    line's row on a PDF, and the checks raise `requested_date_missing`.
    """

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
    # None: printed blank (ticket 34).
    requested_date: date | None
    anchors: PoLineAnchors
    flags: tuple[FlaggedValue, ...] = ()
    legacy: tuple[LegacyText, ...] = ()
    # Earliest first; empty when the line prints one quantity and one date,
    # which are its one schedule. A flag on a schedule's cells is the line's
    # `requested_date`'s: its dates are asked of the customer, never typed.
    printed_schedules: tuple[DeliverySchedule, ...] = ()
    # The line's own PO number, where the file prints one per line (ticket
    # 18); None: the PO's.
    line_po: LinePo | None = None

    @model_validator(mode="after")
    def _flags_name_line_fields(self) -> Self:
        _require_fields(
            (*self.flags, *self.legacy), PoLineAnchors.model_fields, f"line {self.line_no}"
        )
        return self

    @model_validator(mode="after")
    def _requested_date_is_the_first_schedules(self) -> Self:
        printed = self.printed_schedules
        if not printed:
            return self
        days = [s.requested_date for s in printed]
        if days != sorted(days):
            raise ValueError(f"line {self.line_no}'s schedules are not in date order")
        first = printed[0]
        if (first.requested_date, first.anchor) != (
            self.requested_date,
            self.anchors.requested_date,
        ):
            raise ValueError(f"line {self.line_no}'s requested date is not its first schedule's")
        return self

    @property
    def schedules(self) -> tuple[DeliverySchedule, ...]:
        """When and how much the line is to be delivered, earliest first: a
        line with one quantity and one date is a list of one, a line printed
        with no date has none yet."""
        if self.printed_schedules:
            return self.printed_schedules
        if self.requested_date is None:
            return ()
        only = DeliverySchedule(
            quantity=self.quantity,
            requested_date=self.requested_date,
            anchor=self.anchors.requested_date,
        )
        return (only,)

    @property
    def prints_schedules(self) -> bool:
        """Whether the PO prints the line's schedules apart from the line."""
        return bool(self.printed_schedules)

    @property
    def scheduled_quantity(self) -> Decimal:
        """What the line's schedules add up to."""
        return sum((s.quantity for s in self.schedules), Decimal(0))

    @property
    def flagged(self) -> frozenset[str]:
        """The fields read from a flagged region."""
        return frozenset(flag.field for flag in self.flags)

    @property
    def legacy_fields(self) -> frozenset[str]:
        """The fields read from text typed in a TCVN3 or VNI font."""
        return frozenset(text.field for text in self.legacy)


class PrintedTotal(BaseModel):
    """The total the PO prints under its lines."""

    model_config = _FROZEN

    amount: Decimal = Field(ge=0)
    anchor: SourceAnchor
    flags: tuple[FlaggedValue, ...] = ()
    legacy: tuple[LegacyText, ...] = ()

    @model_validator(mode="after")
    def _flags_name_the_amount(self) -> Self:
        _require_fields((*self.flags, *self.legacy), ("amount",), "a total")
        return self


class PrintDifference(BaseModel):
    """One value a PDF print shows differently from its workbook (ticket 34):
    which, and where the print shows it. The workbook's own value carries a
    `print_differs` flag beside it."""

    model_config = _FROZEN

    # None: the header's value, or the total (``total``).
    line_no: int | None = Field(default=None, ge=1)
    field: str = Field(pattern=r"^[a-z_]{1,32}$")
    anchor: SourceAnchor
    # Both values as text, as each file prints them (ticket 22): the case's
    # file's (``ours``) and this one's (``theirs``). Kept here, as read, so
    # the finding citing them reads the same however Sales corrects the
    # case's value. None on a difference stored before they were kept.
    ours: str | None = Field(default=None, max_length=200)
    theirs: str | None = Field(default=None, max_length=200)


class PrintCopy(BaseModel):
    """The second file of the same PO in one mail, kept as a second source
    and never read as a second PO: the PDF print beside its workbook (ticket
    34), or any other file naming the same PO number (ticket 22, `print_pairs`)."""

    model_config = _FROZEN

    attachment_id: AttachmentId
    attachment_sha256: Sha256Hex
    parser_version: VersionRef
    differences: tuple[PrintDifference, ...] = ()

    @model_validator(mode="after")
    def _anchors_point_into_the_print(self) -> Self:
        for difference in self.differences:
            anchor = difference.anchor
            if (anchor.attachment_id, anchor.attachment_sha256) != (
                self.attachment_id,
                self.attachment_sha256,
            ):
                raise ValueError(f"a print anchor points outside attachment {self.attachment_id}")
        return self


class Derivation(BaseModel):
    """How the bytes a PO was read from were made from the customer's file
    (ticket 27): converted from a legacy Office format, or read by OCR from
    images of its pages. The tool's own version is kept: another converter or
    engine is another reading of the same file."""

    model_config = _FROZEN

    method: Literal["converted", "ocr"]
    # `soffice --version`'s first line, or `tesseract --version`'s with its
    # languages: what produced the reading, as it named itself.
    tool: str = Field(min_length=1, max_length=200)
    # The converted copy's sha256; None for OCR, which makes no file.
    derived_sha256: Sha256Hex | None = None

    @model_validator(mode="after")
    def _a_copy_is_named_by_its_hash(self) -> Self:
        if (self.method == "converted") != (self.derived_sha256 is not None):
            raise ValueError("a converted copy names its hash, and an OCR reading none")
        return self


class PoDocument(BaseModel):
    """What a reader got out of one attachment, and how it read it.

    Or, for a PO the customer wrote in the mail itself (AI item 4), what a
    model read of the message's newest part (`po_body_reading`):
    ``attachment_id`` None, ``body`` the text as DW1 read it, and every
    anchor a range of that text with its digest, as a quotation's request
    read from the mail is (ticket 29).
    """

    model_config = _FROZEN

    # None: read from the message's text (``body``), not from a file.
    attachment_id: AttachmentId | None
    # The attachment's bytes' sha256; for the message's text, its text's.
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
    # The tenant's own approved layout the reader read it with (ticket 30):
    # `po_layout:<id>@<version>`. None: the platform's layout for the customer.
    layout_ref: str | None = Field(default=None, pattern=r"^po_layout:[0-9a-f-]{36}@\d+$")
    # Its PDF print, attached to the same mail (ticket 34); None: none was.
    print_copy: PrintCopy | None = None
    # How the bytes it was read from were made from the attachment (ticket 27);
    # None: read from the attachment itself.
    derivation: Derivation | None = None
    # The message's newest part a PO written in the mail was read from.
    body: MessageText | None = None
    # The model profile a PO written in the mail was read on (ticket 44): a
    # step's threshold is measured per prompt and profile. None: no model.
    model_profile: str | None = Field(default=None, min_length=1, max_length=64)
    # Rows the file marks as other than a firm order (ticket 18: a customer
    # portal's export mixes forecast rows with firm ones): counted and shown,
    # never read as lines and never ordered.
    forecast_rows: int = Field(default=0, ge=0)
    # The revision the file's name suggests after the PO number ("R1", "2",
    # "RV"; ticket 22, `revision_hints.name_revision`): a hint shown beside
    # the printed revision, which, with the lines, still decides
    # (`check_history`). None: the name suggests none.
    name_revision: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,8}$")

    @model_validator(mode="after")
    def _lines_and_anchors_belong(self) -> Self:
        if (self.attachment_id is None) != (self.body is not None):
            raise ValueError("a PO is read from one attachment or from the message's text")
        if self.body is not None and (
            self.body.sha256 != self.attachment_sha256
            or self.print_copy is not None
            or self.derivation is not None
            or self.layout_ref is not None
        ):
            raise ValueError("a PO read from the message's text has no file of its own")
        _require_unique_line_numbers(line.line_no for line in self.lines)
        if self.rows_printed < len(self.lines):
            raise ValueError("more lines read than rows printed")
        if (self.buyer is None) != (self.buyer_anchor is None):
            raise ValueError("a buyer and its anchor go together")
        derived = None if self.derivation is None else self.derivation.derived_sha256
        for anchor in self.anchors():
            if (anchor.attachment_id, anchor.attachment_sha256, anchor.derived_sha256) != (
                self.attachment_id,
                self.attachment_sha256,
                derived,
            ):
                raise ValueError(f"an anchor points outside attachment {self.attachment_id}")
            if self.body is not None and (
                anchor.chars is None or anchor.chars.end > len(self.body.text)
            ):
                raise ValueError("an anchor points outside the message's text")
        if self.print_copy is not None and self.print_copy.attachment_id == self.attachment_id:
            raise ValueError("a PO's print is another attachment than the PO")
        return self

    @property
    def from_message(self) -> bool:
        """Whether the PO was written in the mail, not attached to it."""
        return self.body is not None

    @property
    def opened_with_password(self) -> bool:
        """Whether it was read from a file the reader sandbox opened with a
        password its mail carries (ticket 17), as its values are flagged."""
        return any(f.flag is RegionFlag.OPENED_WITH_PASSWORD for f in self.header.flags)

    def legacy_texts(self) -> list[tuple[str, SourceAnchor, LegacyEncoding]]:
        """Each value read from text typed in a TCVN3 or VNI font, in reading
        order (header, then the lines, then the total): its field, where it
        is, and its encoding. The total's field is `TOTAL_FIELD`."""
        header = self.header
        found = [(t.field, getattr(header.anchors, t.field), t.encoding) for t in header.legacy]
        for line in self.lines:
            found += [(t.field, getattr(line.anchors, t.field), t.encoding) for t in line.legacy]
        if self.total is not None:
            found += [(TOTAL_FIELD, self.total.anchor, t.encoding) for t in self.total.legacy]
        return found

    def first_legacy_text(self) -> tuple[SourceAnchor, LegacyEncoding] | None:
        """Where the first value read from legacy text is, and its encoding;
        None when every value was read from Unicode text (`legacy_encoding`)."""
        found = self.legacy_texts()
        return (found[0][1], found[0][2]) if found else None

    def with_unchecked(self, sources: Iterable[str]) -> PoDocument:
        """The PO with each of ``sources`` named among what nobody checked:
        a source a check needed and could not read (audit finding 1, "Bravo
        (chưa kết nối)"). The case then says it was not checked, never that
        it passed: the PO-level `value_uncertain` names it, and Sales settles
        it with a note of what they checked by hand."""
        added = tuple(dict.fromkeys(s for s in sources if s not in self.unchecked_regions))
        if not added:
            return self
        return PoDocument.model_validate(
            {**dict(self), "unchecked_regions": (*self.unchecked_regions, *added)}
        )

    def anchors(self) -> Iterable[SourceAnchor]:
        """Every anchor the document holds."""
        yield from (anchor for _, anchor in self.header.anchors.stated())
        for line in self.lines:
            yield from (anchor for _, anchor in line.anchors)
            if line.line_po is not None:
                yield line.line_po.anchor
                if line.line_po.po_date_anchor is not None:
                    yield line.line_po.po_date_anchor
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
    # The file is locked with a password, and none its mail carries opens it
    # (ticket 17): routed as `attachment_locked`, not as unreadable.
    locked: bool = False


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
    LEGACY_ENCODING = "legacy_encoding"
    REQUESTED_DATE_MISSING = "requested_date_missing"
    # The length per reel the PO's line states ("610X12", "305M") is not the
    # item's standard length; `pack_multiple` checks the quantity only.
    REEL_LENGTH_MISMATCH = "reel_length_mismatch"
    # The spec number the PO's line states is not one of the item's.
    SPEC_MISMATCH = "spec_mismatch"
    # Two files of the same PO in one mail print a value differently (ticket
    # 22): neither file wins, each value waits for a person.
    FILES_DISAGREE = "files_disagree"
    # The delivery term the PO prints is not the customer's (ticket 02): the
    # upload file keeps the customer's, and Sales decides which one stands.
    DELIVERY_TERM_MISMATCH = "delivery_term_mismatch"


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
        FindingCode.LEGACY_ENCODING,
        FindingCode.FILES_DISAGREE,
        FindingCode.DELIVERY_TERM_MISMATCH,
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
        FindingCode.REEL_LENGTH_MISMATCH,
        FindingCode.SPEC_MISMATCH,
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
        FindingCode.REEL_LENGTH_MISMATCH: _ACCEPT_OR_ASK,
        FindingCode.SPEC_MISMATCH: _ACCEPT_OR_ASK,
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
        # The customer sends the PO again in Unicode, which arrives as a
        # revision of the case and is read afresh (ticket 20): nobody types
        # over text DW1 cannot read, and nobody accepts it as read.
        FindingCode.LEGACY_ENCODING: frozenset({DispositionKind.ASK_CUSTOMER}),
        # A line printed with no date, "date to follow" (ticket 34): Sales asks
        # the customer for it, or goes ahead with the date to follow, DW1
        # suggesting the first day the lead time allows and PC confirming one.
        FindingCode.REQUESTED_DATE_MISSING: _ACCEPT_OR_ASK,
        # Two files of one PO disagree (ticket 22): every differing value is
        # also `value_uncertain` on the case's file, typed by Sales or asked
        # of the customer; this one names both values and both files, and is
        # accepted once Sales has settled them, or asked of the customer.
        FindingCode.FILES_DISAGREE: _ACCEPT_OR_ASK,
        # Sales accepts the PO's term or the customer's for the order, for the
        # reason given, or asks the customer which one they meant.
        FindingCode.DELIVERY_TERM_MISMATCH: _ACCEPT_OR_ASK,
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
    # Raise an order's cross-check again when the recorder of its Bravo entry
    # cannot (`sales.order.resend_cross_check`, the head's).
    RESEND_CROSS_CHECK = "resend_cross_check"


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
    ``ambiguous``: several items fit. ``unmapped``: none does, or Sales
    rejected the candidates a model's reading proposed (`reject_candidates`).
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
    "reel_length",
    "spec",
    "lead_time",
]


class ItemBasis(BaseModel):
    """The item-master values a line was checked against, as they were."""

    model_config = _FROZEN

    prv_code: PrvCode
    uom: Uom | None
    # None: the item master did not hold it, and the check did not run.
    moq: Decimal | None
    pack_multiple: Decimal | None
    standard_lead_time_days: int | None


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
    # What a model reading of the description did, when the tenant's rules
    # asked for one (dw_sales ADR 0005): the prompt, profile and route it ran
    # on, and the spans the candidates were computed from. None: no model was
    # asked, because the convert list or DW1's own vocabulary mapped the line,
    # or the tenant has it off.
    description_reading: DescriptionReading | None = None
    # The attributes the candidates were computed from: what DW1's own
    # vocabulary read from the description, or what code accepted of a model's
    # reading. Shown against each candidate (the candidate picker), so the
    # screen compares with the reading the mapping used, never a later one.
    # None: the description was not read (a convert entry decided, the text
    # was not understood or typed in a legacy font), or the line was checked
    # before this was stamped.
    stated_attributes: StatedAttributes | None = None

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
    # What Sales confirms to the customer, entered at confirmation: one date
    # per delivery (`deliveries`), so a line the PO splits over several dates
    # has one per schedule, in the schedules' order (ticket 35). Empty until
    # the order is confirmed.
    confirmed_delivery_dates: tuple[date, ...] = ()
    # Who agreed a short lead time with PC (outside the portal), and when.
    pc_confirmed_by: ActorId | None = None
    pc_confirmed_at: AwareDatetime | None = None
    # What Sales typed for the values its `value_uncertain` flagged, one per
    # field; `po_line` keeps the values as read.
    corrections: tuple[ValueCorrection, ...] = ()
    # The changes the customer asked by mail that a person confirmed, one per
    # field, the latest (ticket 27); they win over a correction of the field.
    changes: tuple[AppliedChange, ...] = ()
    # PC's answer: the line's deliveries with PC's dates (ticket 07). None
    # until a person records it.
    pc_answer: PcAnswer | None = None

    @model_validator(mode="after")
    def _pc_confirmation_names_who_and_when(self) -> Self:
        if (self.pc_confirmed_by is None) != (self.pc_confirmed_at is None):
            raise ValueError("a PC confirmation names who and when")
        return self

    @model_validator(mode="after")
    def _pc_answer_delivers_the_line(self) -> Self:
        answer = self.pc_answer
        if answer is None or self.cancelled:
            return self
        po = self.effective
        if po.prints_schedules:
            if answer.quantities != tuple(s.quantity for s in po.schedules):
                raise ValueError(f"line {self.line_no}: PC's deliveries are not its schedules")
        elif sum(answer.quantities, Decimal(0)) != po.quantity:
            raise ValueError(f"line {self.line_no}: PC's deliveries do not add up to the line")
        return self

    @model_validator(mode="after")
    def _a_confirmed_date_per_delivery(self) -> Self:
        dates = self.confirmed_delivery_dates
        if dates and len(dates) != self.deliveries:
            raise ValueError(
                f"line {self.line_no} is confirmed with {len(dates)} dates"
                f" for {self.deliveries} deliveries"
            )
        return self

    @model_validator(mode="after")
    def _a_model_reading_is_never_exact(self) -> Self:
        # A model-read label is a judgement, so the code it narrows to is a
        # candidate Sales confirms, never a line entered as it stands.
        reading = self.basis.description_reading
        read = reading is not None and reading.outcome == "read"
        if read and self.mapping.status is MappingStatus.EXACT:
            raise ValueError(f"line {self.line_no}: a model-read description is never exact")
        return self

    @model_validator(mode="after")
    def _corrections_are_the_flagged_values(self) -> Self:
        owner = f"line {self.line_no}"
        _require_corrections(self.corrections, self.po_line.flagged, owner)
        fields = [c.field for c in self.changes]
        if len(fields) != len(set(fields)):
            raise ValueError(f"{owner} holds two changes of one field")
        if self.changes and self.po_line.prints_schedules:
            # One value cannot say which of the printed schedules it changes.
            raise ValueError(f"{owner} prints its schedules, and takes no change by mail")
        _keeps_identity(self.po_line, self.effective, owner)
        return self

    @property
    def line_no(self) -> int:
        return self.po_line.line_no

    @property
    def effective(self) -> PoLine:
        """The line as it is entered: the values as read, each corrected one
        replaced by what Sales typed, and each changed one by the change a
        person confirmed (ticket 27). What the checks, the upload file and
        every draft read."""
        return _with_values(_with_values(self.po_line, self.corrections), self.changes)

    def correction(self, field: str) -> ValueCorrection | None:
        return next((c for c in self.corrections if c.field == field), None)

    @property
    def cancelled(self) -> bool:
        """PC cancelled the whole line (ticket 10, W07 "cancel all"): its
        answer delivers none of it. The line keeps what the customer ordered;
        it is delivered never, confirmed with no date (`deliveries` is 0),
        and its paste-sheet row holds nothing (`upload_rows`)."""
        return self.pc_answer is not None and not self.pc_answer.deliveries

    @property
    def deliveries(self) -> int:
        """How many dates the line is confirmed with: one per delivery PC's
        answer gives it (ticket 07), else one per schedule the PO prints apart
        from the line, else one (a line printed with no date is still
        delivered once, on the date Sales confirms)."""
        return len(self.delivery_quantities)

    @property
    def delivery_quantities(self) -> tuple[Decimal, ...]:
        """How much each delivery of the line holds, in their order: PC's
        deliveries once PC answered, else the schedules the PO prints apart
        from the line, else the line's quantity at once. The one owner of what
        a delivery of the line is, for the confirmation and the paste sheet."""
        if self.pc_answer is not None:
            return self.pc_answer.quantities
        po = self.effective
        if po.prints_schedules:
            return tuple(s.quantity for s in po.schedules)
        return (po.quantity,)

    @property
    def confirmed_delivery_date(self) -> date | None:
        """The date Sales confirmed for a line delivered once; None before
        confirmation and for a split line, whose dates are per schedule
        (`confirmed_schedules`)."""
        dates = self.confirmed_delivery_dates
        return dates[0] if len(dates) == 1 and not self.effective.prints_schedules else None

    def confirmed_deliveries(self) -> tuple[tuple[Decimal, date], ...]:
        """Each delivery's quantity with the date Sales confirmed for it
        (`delivery_quantities`); empty before confirmation."""
        if not self.confirmed_delivery_dates:
            return ()
        return tuple(zip(self.delivery_quantities, self.confirmed_delivery_dates, strict=True))

    def confirmed_schedules(self) -> tuple[tuple[DeliverySchedule, date], ...]:
        """A split line's schedules, each with the date Sales confirmed for
        it; empty for any other line, or before confirmation."""
        po = self.effective
        if not po.prints_schedules or not self.confirmed_delivery_dates:
            return ()
        return tuple(zip(po.schedules, self.confirmed_delivery_dates, strict=True))

    def suggested_date(self, schedule: DeliverySchedule) -> date | None:
        """DW1's proposal for one of the line's schedules: its date when the
        lead time allows it, else the first day it does. The line's own
        suggestion is its first schedule's, and a later one is never earlier
        than that first day."""
        if self.suggested_delivery_date is None:
            return None
        return max(schedule.requested_date, self.suggested_delivery_date)


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


class Corrected(NamedTuple):
    """A case's values with one more correction (`OrderCase.corrected`): what
    its checks are run again on before `OrderCase.correct_value` takes them."""

    # The line corrected; None for the PO header or its total.
    line_no: int | None
    lines: tuple[OrderLine, ...]
    header_corrections: tuple[ValueCorrection, ...]
    # The PO as it is entered: every value as read or as corrected.
    document: PoDocument
    # The lines to check again: the corrected one, or every line when a
    # header value they were checked with (the date, the currency) is.
    rechecked: frozenset[int]
    # The corrected line's PRV code is computed again: a value it was mapped
    # from changed.
    remapped: bool


class BravoHistory(NamedTuple):
    """The PO's history against Bravo, checked again on the values as entered:
    the sales order it duplicates, or the one its revision is of."""

    duplicate_of_so: str | None
    base_so_no: str | None


class Recheck(NamedTuple):
    """The checks run again on a case's corrected values, under its rules."""

    lines: tuple[LineCheck, ...]
    # The PO-level findings raised again, and every code the checks that
    # raised them can raise: those of the case are replaced, the others kept.
    po_findings: tuple[Finding, ...]
    po_codes: frozenset[FindingCode]
    # Set when the history check ran again (its codes are then in
    # ``po_codes``): what the case names in Bravo, replaced.
    bravo: BravoHistory | None = None


class _Rechecked(NamedTuple):
    """A case's values once its checks ran again (`OrderCase._rechecked`):
    the fields of the case they replace."""

    lines: tuple[OrderLine, ...]
    findings: tuple[Finding, ...]
    header_corrections: tuple[ValueCorrection, ...]
    history: dict[str, object]
    revision_changes: tuple[LineChange, ...]

    def changes(self) -> dict[str, object]:
        """As `OrderCase._edited` takes them."""
        return {
            "lines": self.lines,
            # Validated again: model_copy alone skips the invariants.
            "findings": tuple(Finding.model_validate(dict(f)) for f in self.findings),
            "header_corrections": self.header_corrections,
            **self.history,
            "changes": self.revision_changes,
        }


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
# A line's schedules, compared as their text (`schedules_text`) when either
# revision prints them apart from the line (ticket 21); otherwise its quantity
# and date say all there is.
SCHEDULES_FIELD: Final = "schedules"
LineChangeField = PoLineField | Literal["schedules"]


def schedules_text(line: PoLine) -> str:
    """``2026-11-15: 2000; 2026-12-01: 3000``: a line's schedules as one
    value, each quantity as a value (``2000.0`` is ``2000``)."""
    return "; ".join(
        f"{s.requested_date.isoformat()}: {format(s.quantity.normalize(), 'f')}"
        for s in line.schedules
    )


class LineChange(BaseModel):
    """One value of one line that a revision changed.

    A line the revision adds has every value with ``before`` None; a line it
    drops has every value with ``after`` None.
    """

    model_config = _FROZEN

    line_no: int = Field(ge=1)
    field: LineChangeField
    before: str | None
    after: str | None

    @model_validator(mode="after")
    def _is_a_change(self) -> Self:
        if self.before == self.after:
            raise ValueError("a change needs a before and an after that differ")
        return self


def _schedules_of(was: PoLine | None, now: PoLine | None) -> tuple[str | None, str | None] | None:
    """Both revisions' schedules as text, when either prints them; else None."""
    if not any(line is not None and line.prints_schedules for line in (was, now)):
        return None
    return (
        schedules_text(was) if was is not None else None,
        schedules_text(now) if now is not None else None,
    )


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
        schedules = _schedules_of(was, now)
        if schedules is not None and schedules[0] != schedules[1]:
            changes.append(
                LineChange(
                    line_no=line_no, field=SCHEDULES_FIELD, before=schedules[0], after=schedules[1]
                )
            )
    return tuple(changes)


def rebase_changes(
    changes: Sequence[LineChange], was: Sequence[PoLine], now: Sequence[PoLine]
) -> tuple[LineChange, ...]:
    """A revision's change list once a value of the revision is corrected:
    ``was`` and ``now`` are its lines as entered before and after.

    Each value's ``before`` stays what the order held before the revision (a
    listed change's, else the value it had, which no change means was the
    same); its ``after`` is the value as now entered. A line the revision
    dropped keeps its changes. In `diff_lines`' order.
    """
    listed = {(c.line_no, c.field): c for c in changes}
    old = {line.line_no: line for line in was}
    new = {line.line_no: line for line in now}
    rebased: list[LineChange] = []
    for line_no in sorted({c.line_no for c in changes} | new.keys()):
        if line_no not in new:
            rebased += [c for c in changes if c.line_no == line_no]
            continue
        for field in _COMPARED:
            value, change = getattr(new[line_no], field), listed.get((line_no, field))
            if change is None:
                held = getattr(old[line_no], field)
                if held != value:
                    rebased.append(
                        LineChange(
                            line_no=line_no, field=field, before=_text(held), after=_text(value)
                        )
                    )
            elif not _holds(change.before, field, value):
                rebased.append(
                    LineChange(
                        line_no=line_no, field=field, before=change.before, after=_text(value)
                    )
                )
        change = listed.get((line_no, SCHEDULES_FIELD))
        schedules = _schedules_of(old[line_no], new[line_no])
        if change is not None:
            entered = schedules_text(new[line_no])
            if change.before != entered:
                rebased.append(
                    LineChange(
                        line_no=line_no, field=SCHEDULES_FIELD, before=change.before, after=entered
                    )
                )
        elif schedules is not None and schedules[0] != schedules[1]:
            rebased.append(
                LineChange(
                    line_no=line_no, field=SCHEDULES_FIELD, before=schedules[0], after=schedules[1]
                )
            )
    return tuple(rebased)


def _holds(text: str | None, field: str, value: object) -> bool:
    """Whether ``text`` (a change's side) is ``value``, compared as the
    field's values are (`diff_lines`): ``0.658`` is ``0.6580``."""
    if text is None:
        return False
    return TypeAdapter(PoLine.model_fields[field].annotation).validate_python(text) == value


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
    # The confirmation left and the order waits on the customer's answer;
    # then the customer agreed, in words or by silence (dw_sales ADR 0011).
    CONFIRMATION_SENT = "confirmation_sent"
    CONFIRMED = "confirmed"
    CHANGE_REVIEW = "change_review"
    CLOSED = "closed"


class CloseReason(StrEnum):
    DUPLICATE = "duplicate"
    NOT_AN_ORDER = "not_an_order"
    SUPERSEDED = "superseded"
    CANNOT_SUPPLY = "cannot_supply"


# warn: an acknowledged `missing_noc_esf` lets the confirmation be sent.
# block_confirmation: its presence refuses `confirmation_sent` even when
# acknowledged.
ExportControlMode = Literal["warn", "block_confirmation"]

_S = OrderStatus
# Before the order is in Bravo: what may still be closed, and where a new
# revision restarts the checks.
BEFORE_UPLOAD: Final = frozenset(
    {_S.RECEIVED, _S.CHECKED, _S.IN_REVIEW, _S.CORRECTION_REQUESTED, _S.PREPARED}
)
# The order is in Bravo: a new revision is a change to apply there.
IN_BRAVO: Final = frozenset(
    {
        _S.UPLOADED_TO_BRAVO,
        _S.CROSS_CHECKED,
        _S.CONFIRMATION_SENT,
        _S.CONFIRMED,
        _S.CHANGE_REVIEW,
    }
)
# The confirmation has left (ADR 0011): its stamp stands, and the customer's
# answer, in words or by silence, is what the order waits on until agreed.
CONFIRMATION_LEFT: Final = frozenset({_S.CONFIRMATION_SENT, _S.CONFIRMED})
# Where lines, mappings and dispositions are decided.
_EDITABLE: Final = frozenset({_S.IN_REVIEW, _S.PREPARED, _S.CHANGE_REVIEW})
# Where a change the customer asked by mail is taken (ticket 27): the PIC
# decides the values and the order is not in Bravo yet. In Bravo it is the
# update loop's (dw_sales ADR 0010 decision 3).
_CHANGEABLE: Final = frozenset({_S.IN_REVIEW, _S.PREPARED})
# Where the export-control PIC may acknowledge `missing_noc_esf` without
# moving the case: it blocks only the confirmation (spec decision 9).
_ACKNOWLEDGEABLE: Final = frozenset(
    {_S.IN_REVIEW, _S.PREPARED, _S.UPLOADED_TO_BRAVO, _S.CROSS_CHECKED, _S.CHANGE_REVIEW}
)
# Where each step of the update loop stands (ticket 29). It starts on an order
# whose confirmation has left, whether the customer has agreed to it yet or
# not (ticket 28). Talking with PC and the customer leaves the order as it
# is; once the customer accepts, the change is applied and the order is
# reviewed, entered in Bravo, cross-checked as its rules say, and its
# confirmation sent again, which ends the loop. A move anywhere else (a new
# revision, a return from the cross-check) ends it too.
_LOOP_STATUSES: Final[Mapping[str, frozenset[OrderStatus]]] = MappingProxyType(
    {
        "ask_pc": CONFIRMATION_LEFT,
        "waiting_pc": CONFIRMATION_LEFT,
        "answer_customer": CONFIRMATION_LEFT,
        "waiting_customer": CONFIRMATION_LEFT,
        "bravo_update": frozenset({_S.CHANGE_REVIEW, _S.UPLOADED_TO_BRAVO, _S.CROSS_CHECKED}),
    }
)
# Where each step of the update loop may go next (ticket 29), the one owner:
# the case's methods move the loop only along it (`_loop_with`), and the
# process map draws it (ticket 35). Staying put is a move too where a step
# repeats (PC asked again). The loop begins at `ask_pc` (`loop_change`) and
# ends off this table: the customer keeps the PO as it was, or the order,
# updated in Bravo, is confirmed again.
_LOOP_NEXT: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "ask_pc": frozenset({"waiting_pc"}),
        "waiting_pc": frozenset({"waiting_pc", "answer_customer"}),
        "answer_customer": frozenset({"waiting_customer"}),
        "waiting_customer": frozenset({"ask_pc", "bravo_update"}),
        "bravo_update": frozenset(),
    }
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
        # -> in_review: the customer answered without a corrected PO (they
        # keep it as it is), and Sales decides each finding again.
        _S.CORRECTION_REQUESTED: frozenset({_S.CHECKED, _S.IN_REVIEW, _S.CLOSED}),
        _S.PREPARED: frozenset(
            {_S.PREPARED, _S.UPLOADED_TO_BRAVO, _S.IN_REVIEW, _S.CHECKED, _S.CLOSED}
        ),
        # -> confirmation_sent only when the rules stamped on the case need no
        # cross-check.
        _S.UPLOADED_TO_BRAVO: frozenset(
            {
                _S.UPLOADED_TO_BRAVO,
                _S.CROSS_CHECKED,
                _S.CONFIRMATION_SENT,
                _S.IN_REVIEW,
                _S.CHANGE_REVIEW,
            }
        ),
        _S.CROSS_CHECKED: frozenset({_S.CROSS_CHECKED, _S.CONFIRMATION_SENT, _S.CHANGE_REVIEW}),
        # -> confirmed: the customer agreed (ADR 0011); -> change_review: they
        # declined it, or a revision or an accepted change arrived.
        _S.CONFIRMATION_SENT: frozenset({_S.CONFIRMED, _S.CHANGE_REVIEW}),
        # Back to waiting on the customer: an agreement by silence undone
        # (ticket 82, dw_sales ADR 0011 amendment).
        _S.CONFIRMED: frozenset({_S.CHANGE_REVIEW, _S.CONFIRMATION_SENT}),
        _S.CHANGE_REVIEW: frozenset({_S.CHANGE_REVIEW, _S.UPLOADED_TO_BRAVO}),
        _S.CLOSED: frozenset(),
    }
)


def order_moves() -> Mapping[OrderStatus, frozenset[OrderStatus]]:
    """Every move an order case may make, read-only: `_NEXT` itself, for a
    reader that draws the process (`application.process_settings`)."""
    return _NEXT


def update_loop_moves() -> Mapping[str, frozenset[str]]:
    """Where each step of the update loop may go next, read-only: `_LOOP_NEXT`
    itself, for the reader that draws the process."""
    return _LOOP_NEXT


def update_loop_statuses() -> Mapping[str, frozenset[OrderStatus]]:
    """The statuses an order is in at each step of the update loop, read-only."""
    return _LOOP_STATUSES


def changeable_statuses() -> frozenset[OrderStatus]:
    """Where a customer's change is taken at once and PC is asked before the
    order is in Bravo (tickets 27, 07), read-only."""
    return _CHANGEABLE


def design_wait_statuses() -> frozenset[OrderStatus]:
    """Where an order may wait on Design for a new PRV code (ticket 06): where
    mappings are decided. Outside them `_next` ends every wait, read-only."""
    return _EDITABLE


def quote_wait_statuses() -> frozenset[OrderStatus]:
    """Where an order waits on a quote case opened from it (ticket 09): where
    it was opened, before the self-check that refuses an open one
    (`prepare`), read-only."""
    return _QUOTABLE


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
    # Rows the file marks as other than a firm order, never read (ticket 18).
    forecast_rows: int = 0


# -------------------------------------------------------------------- case --

# Stamps that belong to a step, by the first status that has them.
_PREPARED_ON: Final = frozenset({_S.PREPARED}) | IN_BRAVO
_CROSS_CHECKED_ON: Final = frozenset({_S.CROSS_CHECKED}) | CONFIRMATION_LEFT
MAKER_CHECKER_RULE: Final = "tách nhiệm, WIV-03-012 bước 9"
# Why the customer's answer to the confirmation is not recorded now: their
# change is in the update loop, whose own answer it is.
_ANSWER_IN_THE_LOOP: Final = (
    "khách đang xin thay đổi đơn: câu trả lời của khách ghi ở vòng cập nhật"
)
# The refusal a maker reads, from the domain or from the stored constraint.
MAKER_CHECKER_REFUSAL: Final = (
    f"người đã làm một phần hồ sơ này không tự kiểm chéo được ({MAKER_CHECKER_RULE})"
)
# Where a quote is opened for the PO's lines with no valid quotation (ticket
# 09): while Sales reviews the order, before its self-check.
_QUOTABLE: Final = frozenset({_S.CHECKED, _S.IN_REVIEW})


class QuoteLink(BaseModel):
    """A quote case a person opened from this order ("Mở báo giá", ticket 09):
    a PO came before any quotation for the items of ``lines``. Who opened it,
    and when. The order waits on it while the quote case is open; whether it
    is open is the quote case's own status, read where it matters (`prepare`,
    the line checks), never a copy kept here. Kept once settled: the link is
    the order's history, shown on both cases."""

    model_config = _FROZEN

    quote_case_id: uuid.UUID
    lines: tuple[int, ...] = Field(min_length=1)
    by: ActorId
    at: AwareDatetime

    @model_validator(mode="after")
    def _lines_once(self) -> Self:
        if len(set(self.lines)) != len(self.lines):
            raise ValueError("a quote is opened for a line once")
        return self


class UnappliedDecision(BaseModel):
    """A cross-check decision the platform recorded and DW1's run could not
    apply to the case (ticket 14): the case changed between the decision and
    its apply, say. Said on the order until its cross-check is raised again.

    Ids, the outcome, the version the checker decided on and a reason code;
    the checker's comment stays on the platform's decision record.
    """

    model_config = _FROZEN

    # None only for a run resumed before the platform named the approval.
    approval_id: uuid.UUID | None
    run_id: uuid.UUID
    decided_by: ActorId
    approved: bool
    decided_on: int | None = Field(default=None, ge=1)
    reason_code: str = Field(pattern=r"^[a-z_]{1,40}$")
    at: AwareDatetime


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
    # Step 10: who recorded the confirmation sent (with each line's
    # confirmed dates) and when; kept while the customer's answer is awaited
    # and once they agreed. `confirmation` is what left and its clock.
    confirmed_by: ActorId | None = None
    confirmed_at: AwareDatetime | None = None
    confirmation: ConfirmationSent | None = None
    # The customer agreed to it, as a person recorded (ADR 0011).
    agreement: CustomerAgreement | None = None
    close_reason: CloseReason | None = None
    closed_by: ActorId | None = None
    closed_at: AwareDatetime | None = None
    # The case that replaced this one: the link `closed(superseded)` carries.
    superseded_by_case: uuid.UUID | None = None
    # Whoever prepared the order or recorded its Bravo entry in an earlier
    # round, whose stamp was since cleared (a return from the cross-check, a
    # revision before upload, a reopened self-check) or replaced (a change
    # applied in Bravo). They stay makers of the case (spec decision 7). The
    # store's `makers` column accumulates the same names by trigger, and a
    # stored case is read back with them here.
    earlier_makers: frozenset[ActorId] = frozenset()
    # Only while the order awaits its cross-check: the last decision on it
    # that was not applied. Cleared when it is raised again or the case moves.
    unapplied_decision: UnappliedDecision | None = None
    # What Sales typed for the header values and the total the PO-level
    # `value_uncertain` flagged, one per field (`TOTAL_FIELD` for the total);
    # the document keeps the values as read.
    header_corrections: tuple[ValueCorrection, ...] = ()
    # Sales asked PC for the delivery dates and waits (ticket 07): only where
    # PC's answer is recorded, and cleared once every line asked has it.
    pc_request: PcRequest | None = None
    # Sales asked Design for a new PRV code, line by line (ticket 06): only
    # where mappings are decided, each for a line still without a code.
    design_requests: tuple[DesignRequest, ...] = ()
    # A customer's change on the order once it is in Bravo, from the PIC's
    # confirmation to the order confirmed again (ticket 29); None otherwise.
    update_loop: UpdateLoop | None = None
    # The quote cases opened from this order for lines with no valid
    # quotation, oldest first (ticket 09).
    quote_links: tuple[QuoteLink, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _earlier_makers_are_not_the_current_ones(cls, data: object) -> object:
        """A name stamped in this round is a current maker, not an earlier one.

        One normal form whoever builds the case: the domain clearing a round
        and the store reading back its accumulated `makers` agree on it.
        """
        if not isinstance(data, Mapping) or not data.get("earlier_makers"):
            return data
        current = {str(data.get(stamp)) for stamp in ("prepared_by", "bravo_recorded_by")}
        earlier = [name for name in data["earlier_makers"] if str(name) not in current]
        return {**data, "earlier_makers": frozenset(earlier)}

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
        if self.unapplied_decision is not None and self.status is not _S.UPLOADED_TO_BRAVO:
            raise ValueError("only an order awaiting its cross-check names a decision not applied")
        if self.pc_request is not None:
            if self.status not in _CHANGEABLE:
                raise ValueError(f"a {self.status} case does not wait on PC")
            if not set(self.pc_request.lines) <= line_numbers:
                raise ValueError("PC is asked about a line the case lacks")
        if self.design_requests:
            asked = [request.line_no for request in self.design_requests]
            if len(asked) != len(set(asked)):
                raise ValueError("Design is asked once per line")
            unmapped = {x.line_no for x in self.lines if x.mapping.status is MappingStatus.UNMAPPED}
            if self.status not in _EDITABLE or not set(asked) <= unmapped:
                raise ValueError("Design is asked only about a line without a code, in review")
        if (loop := self.update_loop) is not None:
            if self.status not in _LOOP_STATUSES[loop.step]:
                raise ValueError(f"a {self.status} case is not at {loop.step} of an update")
            if not {x.line_no for x in loop.lines} <= line_numbers:
                raise ValueError("the update names a line the case lacks")
        quoted = [link.quote_case_id for link in self.quote_links]
        if len(quoted) != len(set(quoted)):
            raise ValueError("a quote case is linked to the order once")
        _require_corrections(self.header_corrections, self._header_flagged, "the PO header")
        _keeps_identity(self.header, self.effective_header, "the PO header")
        if self.header_corrections:
            self.effective_document  # noqa: B018 -- validates the typed values
        self._stamps_fit_the_status()
        if self.cross_checked_by is not None and (
            self.cross_checked_by in (self.prepared_by, self.bravo_recorded_by)
            or self.cross_checked_by in self.earlier_makers
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
        require(
            status in CONFIRMATION_LEFT,
            "confirmation",
            self.confirmed_by,
            self.confirmed_at,
            self.confirmation,
        )
        require(status is _S.CONFIRMED, "customer agreement", self.agreement)

    # ------------------------------------------------------------ reading --

    @property
    def awaits_cross_check(self) -> bool:
        """In Bravo and waiting on its cross-check. Only rules that say
        `false` waive it: a case stamped before the rule existed (None) waits,
        the narrow reading (failure-modes #7). `confirm`, `awaiting()` and the
        order list read this, so no two screens disagree about one order."""
        return self.status is _S.UPLOADED_TO_BRAVO and self.cross_check_required is not False

    @property
    def awaits_export_control(self) -> bool:
        """Held on an open `missing_noc_esf` where the export-control PIC may
        acknowledge it (`dispose`'s statuses): their turn, though the status
        is the PIC's (ticket 78). The follow-ups tell them and the case is
        theirs to see while it holds (`visibility.sees_case`)."""
        return self.status in _ACKNOWLEDGEABLE and any(
            f.is_open and f.code is FindingCode.MISSING_NOC_ESF for f in self.findings
        )

    @property
    def awaits_confirmation(self) -> bool:
        """In Bravo, past its cross-check (or with none required), and its
        confirmation not sent yet: where `confirm` may move it."""
        return (
            self.status in (_S.CROSS_CHECKED, _S.UPLOADED_TO_BRAVO) and not self.awaits_cross_check
        )

    @property
    def header(self) -> PoHeader:
        return self.document.header

    def with_value_gates(self, gates: Mapping[tuple[int | None, str], GateRoute]) -> Self:
        """The case with each `model_read` value in ``gates`` stamped with
        what code's gate did with it (ticket 44), by line (None: the PO's
        own) and field, in the document and its lines alike. Nothing
        else changes."""
        if not gates:
            return self

        def stamp(flags: tuple[FlaggedValue, ...], at: int | None) -> tuple[FlaggedValue, ...]:
            return tuple(
                f.model_copy(update={"gate": gates[(at, f.field)]})
                if f.flag is RegionFlag.MODEL_READ and (at, f.field) in gates
                else f
                for f in flags
            )

        document = self.document
        header = document.header.model_copy(update={"flags": stamp(document.header.flags, None)})
        po_lines = tuple(
            line.model_copy(update={"flags": stamp(line.flags, line.line_no)})
            for line in document.lines
        )
        stamped = document.model_copy(update={"header": header, "lines": po_lines})
        lines = tuple(
            line.model_copy(update={"po_line": po_line})
            for line, po_line in zip(self.lines, po_lines, strict=True)
        )
        return self.model_copy(update={"document": stamped, "lines": lines})

    @property
    def effective_header(self) -> PoHeader:
        """The header as it is entered: as read, each corrected value replaced."""
        return _with_values(
            self.header, (c for c in self.header_corrections if c.field != TOTAL_FIELD)
        )

    @property
    def effective_document(self) -> PoDocument:
        """The PO as it is entered: every value as read or as Sales corrected it."""
        return _entered(self.document, self.lines, self.header_corrections)

    def header_correction(self, field: str) -> ValueCorrection | None:
        return next((c for c in self.header_corrections if c.field == field), None)

    def flagged_fields(self, finding: Finding) -> frozenset[str]:
        """The values a `value_uncertain` flagged, which its corrections name:
        its line's, or the header's and the total's. None for another code."""
        if finding.code is not FindingCode.VALUE_UNCERTAIN:
            return frozenset()
        if finding.line_no is None:
            return self._header_flagged
        return self.line(finding.line_no).po_line.flagged

    def correctable_fields(self, finding: Finding) -> frozenset[str]:
        """The flagged values Sales may type (`corrected`): all of them, but
        the dates of a line whose PO prints its schedules, which are asked of
        the customer. What the screen offers reads this too."""
        flagged = self.flagged_fields(finding)
        if finding.line_no is not None and self.line(finding.line_no).po_line.prints_schedules:
            return flagged - {"requested_date"}
        return flagged

    @property
    def _header_flagged(self) -> frozenset[str]:
        total = self.document.total
        read_hidden = total is not None and bool(total.flags)
        return self.header.flagged | (frozenset({TOTAL_FIELD}) if read_hidden else frozenset())

    def _corrections_for(self, finding: Finding) -> tuple[ValueCorrection, ...]:
        if finding.line_no is None:
            return self.header_corrections
        return self.line(finding.line_no).corrections

    def takes_value_note(self, finding: Finding) -> bool:
        """Whether a `value_uncertain` is decided by a free-text
        `corrected_by_sales` (`dispose`): only the PO's one that names a sheet
        nothing reads, once every value it flagged is typed. What the screen
        offers reads this too (`views.order_finding`)."""
        return self._names_unchecked_region(finding) and not self._untyped(finding)

    def _untyped(self, finding: Finding) -> frozenset[str]:
        return self.flagged_fields(finding) - {c.field for c in self._corrections_for(finding)}

    def _names_unchecked_region(self, finding: Finding) -> bool:
        """A PO-level `value_uncertain` also says a sheet nothing reads was
        not checked: no field names it, so no correction resolves it."""
        return (
            finding.code is FindingCode.VALUE_UNCERTAIN
            and finding.line_no is None
            and bool(self.document.unchecked_regions)
        )

    @property
    def attachment_id(self) -> str | None:
        """The PO's file; None for a PO written in the mail."""
        return self.document.attachment_id

    @property
    def blocking_findings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.blocking)

    @property
    def due(self) -> date | None:
        """The order's deadline on the work list (G22): the requested date of
        a line whose lead time is short (`requested_date_short_lt`), as
        entered; the earliest when several are. None when no line's is.

        A line's requested date is its first schedule's, so a split line is
        due on its earliest, which is the one the finding names first."""
        short = {f.line_no for f in self.findings if f.code is FindingCode.REQUESTED_DATE_SHORT_LT}
        days = [
            line.effective.requested_date
            for line in self.lines
            if line.line_no in short and line.effective.requested_date is not None
        ]
        return min(days, default=None)

    @property
    def makers(self) -> frozenset[ActorId]:
        """Everyone the cross-checker must not be (spec decision 7).

        The preparer, whoever recorded the Bravo entry, in this round or an
        earlier one (`earlier_makers`), and whoever typed a value still on the
        case: a corrected value (a finding's, or one field's), or a PRV code
        typed for an unmapped line.
        """
        names: set[ActorId | None] = {self.prepared_by, self.bravo_recorded_by}
        names |= self.earlier_makers
        names |= {
            f.disposition.by for f in self.findings if isinstance(f.disposition, CorrectedBySales)
        }
        names |= {line.mapping.confirmed_by for line in self.lines if line.mapping.hand_entered}
        names |= {c.by for line in self.lines for c in line.corrections}
        names |= {c.by for line in self.lines for c in line.changes}
        names |= {c.by for c in self.header_corrections}
        # PC's dates a person typed are values of the paste sheet (ticket 07).
        names |= {line.pc_answer.by for line in self.lines if line.pc_answer is not None}
        # Who approved the Bravo update file of a customer's change (ticket 29).
        loop = self.update_loop
        if loop is not None and loop.approval is not None:
            names.add(loop.approval.by)
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
            forecast_rows=self.document.forecast_rows,
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
            finding.code is FindingCode.VALUE_UNCERTAIN
            and kind is DispositionKind.CORRECTED_BY_SALES
            and not self.takes_value_note(finding)
        ):
            # A typed value is a field's (`correct_value`); a note is left only
            # for the sheet nothing reads, once every flagged value is typed.
            raise ConflictError(
                "a value_uncertain is corrected field by field",
                details={
                    "case_id": str(self.case_id),
                    "finding": key,
                    "fields": sorted(self._untyped(finding)),
                },
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
        ``recheck``'s item findings, run under this case's rules. Its mapping
        and value findings are not taken: the mapping is this confirmation,
        and the line's values, read from the same cells, keep the findings and
        decisions they already have.
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
        if recheck.line.po_line != line.effective:
            raise DomainError("the line was checked again on other values", details=details)
        rechecked = [f for f in recheck.findings if f.code in ITEM_FINDINGS]
        if any(f.rule_version != self.rules_version for f in rechecked):
            raise ConflictError("the line was checked again under other rules", details=details)
        confirmed = LineMapping(
            status=MappingStatus.CANDIDATE_CONFIRMED,
            prv_code=prv_code,
            candidates=mapping.candidates,
            confirmed_by=actor.user_id,
            confirmed_at=at,
        )
        new_line = OrderLine.model_validate(
            {
                **dict(recheck.line),
                "mapping": confirmed,
                "po_line": line.po_line,
                "corrections": line.corrections,
                "changes": line.changes,
            }
        )
        source = "candidate" if mapping.candidates else "PRV code typed by Sales (item master)"
        kept: list[Finding] = []
        for f in self.findings:
            # The line's item checks are `rechecked`'s; every other finding of
            # the line (its values', a missing date) keeps its decision.
            if f.line_no != line_no or f.code not in MAPPING_FINDINGS | ITEM_FINDINGS:
                kept.append(f)
            elif f.code in MAPPING_FINDINGS:
                corrected = CorrectedBySales(value=prv_code, source=source, by=actor.user_id, at=at)
                kept.append(f.model_copy(update={"disposition": corrected}))
        return self._edited(
            lines=tuple(new_line if x.line_no == line_no else x for x in self.lines),
            findings=_in_line_order((*kept, *rechecked)),
        )

    def undo_applied_mapping(self, line_no: int, *, applied_by: ActorId) -> OrderCase:
        """The PRV code DW applied by itself to a line, undone (dw_sales ADR
        0015, ticket 44): the line is a candidate for a person to confirm
        again, as it was before. Only a code ``applied_by`` (the lane that
        applies) confirmed, after code's gate let it (``gate`` "applied"), on
        a line with that one candidate. Its findings stand: they were checked
        against that same candidate when the case was read, and again when
        it was applied."""
        line = self.line(line_no)
        mapping = line.mapping
        reading = line.basis.description_reading
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if (
            mapping.status is not MappingStatus.CANDIDATE_CONFIRMED
            or mapping.confirmed_by != applied_by
            or mapping.candidates != (mapping.prv_code,)
            or reading is None
            or reading.gate != "applied"
        ):
            raise ConflictError("the line holds no code DW applied by itself", details=details)
        undone = line.model_copy(
            update={
                "mapping": LineMapping(
                    status=MappingStatus.CANDIDATE, candidates=mapping.candidates
                )
            }
        )
        return self._edited(lines=tuple(undone if x.line_no == line_no else x for x in self.lines))

    def reject_candidates(self, line_no: int, recheck: LineCheck) -> OrderCase:
        """Sales says the code a model's reading proposed is not this line's
        ("Không phải mã này", ticket 44): the line's candidates, one or
        several, are rejected together, and the line is `unmapped`, a code
        for Sales to type from the item master (`confirm_mapping`'s
        exception). Only candidates a model's reading proposed
        (``description_reading`` "read") on a line not yet confirmed: a
        convert list's code and DW1's own vocabulary are facts the reading
        did not make, and a confirmed code is not a candidate (one DW
        applied by itself is undone first, `undo_applied_mapping`).

        The line keeps nothing of the reading it rejected: no candidate, no
        reading, no attributes stated by it (``recheck`` is the line checked
        again as unmapped, exactly as without a model), so the picker never
        compares a typed code against attributes the person just refused. The
        reading stays on record as the rejection's labelled case. The line's
        mapping and item findings are ``recheck``'s (`code_unmapped`, open);
        every other finding keeps its decision."""
        line = self.line(line_no)
        mapping = line.mapping
        reading = line.basis.description_reading
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if mapping.status not in (MappingStatus.CANDIDATE, MappingStatus.AMBIGUOUS):
            raise ConflictError("the line holds no candidates to reject", details=details)
        if reading is None or reading.outcome != "read":
            raise ConflictError(
                "only candidates a model's reading proposed are rejected", details=details
            )
        checked = recheck.line
        if (
            checked.line_no != line_no
            or checked.mapping != LineMapping(status=MappingStatus.UNMAPPED)
            or checked.basis.item is not None
            or checked.basis.description_reading is not None
            or checked.basis.stated_attributes is not None
        ):
            raise DomainError("the line was checked again with a mapping", details=details)
        if checked.po_line != line.effective:
            raise DomainError("the line was checked again on other values", details=details)
        raised = [f for f in recheck.findings if f.code in MAPPING_FINDINGS | ITEM_FINDINGS]
        if any(f.rule_version != self.rules_version for f in raised):
            raise ConflictError("the line was checked again under other rules", details=details)
        rejected = _rechecked_line(line, recheck, self.findings)
        kept = [
            f
            for f in self.findings
            if f.line_no != line_no or f.code not in MAPPING_FINDINGS | ITEM_FINDINGS
        ]
        return self._edited(
            lines=tuple(rejected if x.line_no == line_no else x for x in self.lines),
            findings=_in_line_order((*kept, *raised)),
        )

    def corrected(self, key: str, correction: ValueCorrection, actor: Actor) -> Corrected:
        """The case's values with ``correction`` too, for its checks to run on.

        Refused unless ``key`` is a `value_uncertain` that flagged the field,
        the correction is the actor's, and the case is where values are
        decided. The value is validated as the field's type (422 naming the
        field). A line's number, or the PO's number or revision, is confirmed
        as read and never changed (409): another number is another line or
        another PO, which the customer is asked about.
        """
        finding = self.finding(key)
        field = correction.field
        details: dict[str, object] = {"case_id": str(self.case_id), "finding": key, "field": field}
        self._require_editable()
        if finding.code is not FindingCode.VALUE_UNCERTAIN:
            raise ConflictError(f"{finding.code} is not corrected field by field", details=details)
        if correction.by != actor.user_id:
            raise DomainError("a decision is recorded as its actor's", details=details)
        if field not in self.flagged_fields(finding):
            raise DomainError("the finding did not flag this field", details=details)
        if field not in self.correctable_fields(finding):
            # One typed date cannot say which of the printed schedules it is.
            raise ConflictError(
                "the dates of a line with several schedules are asked of the customer",
                details={**details, "rule": "printed_schedules"},
            )
        lines, header_corrections = self.lines, self.header_corrections
        read: BaseModel
        typed: BaseModel
        if finding.line_no is None:
            header_corrections = (*_without(header_corrections, field), correction)
            read = self.header
            typed = _with_values(read, [correction] if field != TOTAL_FIELD else [])
        else:
            line = self.line(finding.line_no)
            corrections = (*_without(line.corrections, field), correction)
            read, typed = line.po_line, _with_values(line.po_line, corrections)
        if field in _IDENTITY_FIELDS and getattr(read, field) != getattr(typed, field):
            raise ConflictError(
                f"a correction confirms the {field} as read: another one is asked of the customer",
                details=details,
            )
        rechecked: frozenset[int] = frozenset()
        remapped = False
        if finding.line_no is not None:
            new_line = OrderLine.model_validate(
                {**dict(line), "corrections": corrections, **_pc_dropped(line, field)}
            )
            lines = tuple(new_line if x.line_no == line.line_no else x for x in lines)
            rechecked = frozenset({line.line_no})
            was, now = line.effective, new_line.effective
            remapped = any(getattr(was, name) != getattr(now, name) for name in _MAPPING_INPUTS)
        entered = _entered(self.document, lines, header_corrections)
        if (
            finding.line_no is None
            and field in _LINE_CHECK_HEADER_INPUTS
            and entered.header != self.effective_header
        ):
            rechecked = frozenset(x.line_no for x in lines)
        return Corrected(finding.line_no, lines, header_corrections, entered, rechecked, remapped)

    def correct_value(
        self, key: str, correction: ValueCorrection, actor: Actor, recheck: Recheck
    ) -> OrderCase:
        """One value a `value_uncertain` flagged, typed by Sales, with the
        checks run again on the corrected values (Đạt, 2026-10-12).

        ``recheck`` is `corrected`'s lines checked again under this case's
        rules, and the PO-level checks run again on the corrected PO. A
        finding whose key and compared values did not change keeps its
        decision; one that changed, or is new, is open. A line whose PRV code
        was computed again (its code or description corrected) has its mapping
        and mapping findings replaced, open; any other line keeps them. The
        finding is resolved (`corrected_by_sales`, by the actor) once every
        field it flagged has a correction, unless it also names a sheet
        nothing reads, which a note decides (`dispose`).
        """
        corrected = self.corrected(key, correction, actor)
        details: dict[str, object] = {"case_id": str(self.case_id), "finding": key}
        taken = self._rechecked(corrected, recheck, details)
        findings = taken.findings
        target = next(f for f in findings if f.key == key)
        typed = (
            corrected.header_corrections
            if target.line_no is None
            else next(x for x in taken.lines if x.line_no == target.line_no).corrections
        )
        if self.flagged_fields(target) <= {c.field for c in typed} and not (
            self._names_unchecked_region(target)
        ):
            resolved = CorrectedBySales(
                value=",".join(sorted(c.field for c in typed)),
                source=_TYPED_PER_FIELD,
                by=actor.user_id,
                at=correction.at,
            )
            findings = tuple(
                f.model_copy(update={"disposition": resolved}) if f.key == key else f
                for f in findings
            )
        return self._edited(**taken._replace(findings=findings).changes())

    def changed(self, line_no: int, change: AppliedChange, actor: Actor) -> Corrected:
        """The case's values with a change the customer asked by mail too, for
        its checks to run on (ticket 27; dw_sales ADR 0010 decision 2).

        Taken only where the PIC decides the order's values before it is in
        Bravo (`in_review`, or `prepared`, which it reopens): once the order
        is in Bravo a change is the update loop's (ADR 0010 decision 3).
        Refused for a line that prints its schedules apart from it (one value
        cannot say which), and unless the change is the actor's. A quantity or
        a date is no input of the line's PRV code, so its mapping stands.
        """
        details: dict[str, object] = {
            "case_id": str(self.case_id),
            "line": line_no,
            "field": change.field,
        }
        if self.status not in _CHANGEABLE:
            raise ConflictError(
                f"a change asked by mail is not taken in {self.status}",
                details={**details, "status": self.status.value, "rule": "change_status"},
            )
        if change.by != actor.user_id:
            raise DomainError("a decision is recorded as its actor's", details=details)
        line = self.line(line_no)
        if line.po_line.prints_schedules:
            raise ConflictError(
                "the line prints its schedules: which one changes is asked of the customer",
                details={**details, "rule": "printed_schedules"},
            )
        new_line = OrderLine.model_validate(
            {
                **dict(line),
                "changes": (*_without(line.changes, change.field), change),
                **_pc_dropped(line, change.field),
            }
        )
        lines = tuple(new_line if x.line_no == line_no else x for x in self.lines)
        entered = _entered(self.document, lines, self.header_corrections)
        return Corrected(
            line_no, lines, self.header_corrections, entered, frozenset({line_no}), False
        )

    def take_change(
        self, line_no: int, change: AppliedChange, actor: Actor, recheck: Recheck
    ) -> OrderCase:
        """A change the customer asked, confirmed by a person, applied with the
        checks run again on the changed values (`changed`), as for a value
        Sales typed: a finding whose compared values did not change keeps its
        decision, one that changed or is new is open (a pulled-in date may
        now be short of the lead time; a quantity no longer the printed
        amount's). The case takes its next version."""
        corrected = self.changed(line_no, change, actor)
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        return self._edited(**self._rechecked(corrected, recheck, details).changes())

    def _rechecked(
        self, corrected: Corrected, recheck: Recheck, details: dict[str, object]
    ) -> _Rechecked:
        """``corrected``'s values with ``recheck``'s results taken: the lines
        checked again, the findings raised again (each keeping its decision
        while its compared values are the same), the history against Bravo
        where it ran again, and a revision's change list rebased."""
        checks = {check.line.line_no: check for check in recheck.lines}
        if checks.keys() != corrected.rechecked:
            raise DomainError("the case was checked again on other lines", details=details)
        if any(
            f.line_no is not None or f.code not in recheck.po_codes for f in recheck.po_findings
        ):
            raise DomainError("the PO was checked again by other checks", details=details)
        history: dict[str, object] = {}
        if recheck.bravo is not None:
            # Only a PO no other DW1 case holds was checked against Bravo alone.
            if self.superseded or self.duplicate_of_case is not None:
                raise DomainError(
                    "the history of a PO another case holds is not checked again", details=details
                )
            history = recheck.bravo._asdict()
        remapped = {corrected.line_no} if corrected.remapped else set()
        raised = [
            f
            for f in (*recheck.po_findings, *(f for c in recheck.lines for f in c.findings))
            if f.line_no is None or f.code not in MAPPING_FINDINGS or f.line_no in remapped
        ]
        if any(f.rule_version != self.rules_version for f in raised):
            raise ConflictError("the case was checked again under other rules", details=details)
        lines: list[OrderLine] = []
        for line in corrected.lines:
            check = checks.get(line.line_no)
            if check is None:
                lines.append(line)
                continue
            if check.line.po_line != line.effective:
                raise DomainError("the line was checked again on other values", details=details)
            if line.line_no in remapped:
                if check.line.mapping.status is MappingStatus.CANDIDATE_CONFIRMED:
                    raise DomainError("a mapping computed again is not confirmed", details=details)
            elif check.line.mapping != line.mapping:
                raise DomainError(
                    "the line was checked again with another mapping", details=details
                )
            lines.append(_rechecked_line(line, check, self.findings))

        def replaced(f: Finding) -> bool:
            if f.line_no is None:
                return f.code in recheck.po_codes
            return f.line_no in checks and (f.code not in MAPPING_FINDINGS or f.line_no in remapped)

        old = {f.key: f for f in self.findings}
        new = [f if f.code in MAPPING_FINDINGS else _carried(f, old.get(f.key)) for f in raised]
        return _Rechecked(
            lines=tuple(lines),
            findings=_in_line_order((*(f for f in self.findings if not replaced(f)), *new)),
            header_corrections=corrected.header_corrections,
            history=history,
            # A revision's change list is what the PIC applies in Bravo: its
            # after is the value as entered, as the upload file's is. A case
            # never revised lists none.
            revision_changes=rebase_changes(
                self.changes,
                [line.effective for line in self.lines],
                [line.effective for line in lines],
            )
            if self.superseded
            else (),
        )

    def request_correction(self) -> OrderCase:
        """in_review -> correction_requested: the customer is asked (step 8)."""
        if not any(f.disposition.kind is DispositionKind.ASK_CUSTOMER for f in self.findings):
            raise ConflictError(
                "no finding is sent back to the customer",
                details={"case_id": str(self.case_id)},
            )
        return self._next(transition(self.status, _S.CORRECTION_REQUESTED))

    def resume_review(self) -> OrderCase:
        """correction_requested -> in_review: the customer answered without a
        corrected PO (ticket 32), and Sales takes the case up again.

        It disposes no finding (spec decision 9): each one sent back to the
        customer stays `ask_customer`, which `prepare` refuses, until Sales
        decides it again, one by one. A corrected PO needs none of this: it
        arrives as a revision and is read afresh.
        """
        if self.status is not _S.CORRECTION_REQUESTED:
            raise ConflictError(
                "only an order awaiting the customer's correction resumes its review",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        return self._next(transition(self.status, _S.IN_REVIEW))

    def prepare(
        self, actor: Actor, at: datetime, *, settled_quotes: frozenset[uuid.UUID] = frozenset()
    ) -> OrderCase:
        """in_review -> prepared: the PIC's self-check is done (step 7).

        Refused while a finding other than `missing_noc_esf` is open, while
        one is sent back to the customer, while a line is not mapped to a
        code Bravo can take, or while a quote case opened from the order is
        open (ticket 09). Each one is named. ``settled_quotes``: the linked
        quote cases the caller read as approved or declined; a link it does
        not name is open, so a caller that reads none refuses (fail closed).
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
        quoting = [str(q) for q in self.quotes_waited_on(settled_quotes)]
        if open_findings or asked or unmapped or quoting:
            raise ConflictError(
                "the self-check is not complete",
                details={
                    "case_id": str(self.case_id),
                    "open_findings": open_findings,
                    "ask_customer": asked,
                    "lines_not_mapped": unmapped,
                    "quotes_open": quoting,
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
            **self._cleared_from_prepared(),
        )

    def decision_not_applied(self, decision: UnappliedDecision) -> OrderCase:
        """uploaded_to_bravo, unchanged: the cross-check decided on it was not
        applied (ticket 14). The case says so until its cross-check is raised
        again; nothing else about it changes."""
        if self.status is not _S.UPLOADED_TO_BRAVO:
            raise ConflictError(
                "only an order awaiting its cross-check records a decision not applied",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        return self._next(self.status, unapplied_decision=decision)

    def resend_cross_check(self, actor: Actor) -> OrderCase:
        """uploaded_to_bravo, unchanged: its cross-check raised again ("Gửi
        kiểm chéo lại"), once the one before was decided and not applied, or
        never raised. By whoever recorded the Bravo entry, or by someone the
        caller verified may do it for them (the head). The makers stay what
        they were: raising it again makes nobody a maker."""
        if self.status is not _S.UPLOADED_TO_BRAVO or self.cross_check_required is False:
            raise ConflictError(
                "only an order awaiting its cross-check has it raised again",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )
        if (
            actor.user_id != self.bravo_recorded_by
            and Capability.RESEND_CROSS_CHECK not in actor.capabilities
        ):
            raise PermissionDeniedError(
                "the cross-check is raised again by whoever recorded the Bravo entry,"
                " or by the head",
                details={"case_id": str(self.case_id), "rule": "resend_cross_check"},
            )
        return self._next(self.status, unapplied_decision=None)

    def reassigned(self) -> OrderCase:
        """The case's next version, nothing in it changed: its assignee, which
        is stamped beside the case and not in it, is about to (ticket 17). A
        closed case is no one's work any more and is refused."""
        if self.status is _S.CLOSED:
            raise ConflictError(
                "a closed case is not reassigned",
                details={"case_id": str(self.case_id), "rule": "case_closed"},
            )
        return self._next(self.status)

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
        if self.status in {_S.CLOSED, _S.RECEIVED, _S.CHECKED} | CONFIRMATION_LEFT:
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

    # ------------------------------------------------------- PC (ticket 07) --

    def pc_lines(self) -> tuple[int, ...]:
        """The lines a request to PC asks about: those PC has not answered,
        or every line once PC answered them all (Sales asks PC to confirm
        again)."""
        waiting = tuple(line.line_no for line in self.lines if line.pc_answer is None)
        return waiting or tuple(line.line_no for line in self.lines)

    def ask_pc(self, actor: Actor, at: datetime) -> OrderCase:
        """Sales asked PC for the delivery dates of `pc_lines` (by mail or
        Teams, from their own account: DW1 sends nothing). The case waits on
        PC from ``at``; asked again, the wait starts again. Only where PC's
        answer can be taken (`_CHANGEABLE`): once the order is in Bravo, PC's
        dates are the update loop's (ticket 29). No value of the case
        changes, so a self-check stands."""
        if self.status not in _CHANGEABLE:
            raise ConflictError(
                f"PC is not asked from DW1 in {self.status}",
                details={
                    "case_id": str(self.case_id),
                    "status": self.status.value,
                    "rule": "pc_status",
                },
            )
        request = PcRequest(lines=self.pc_lines(), by=actor.user_id, at=at)
        return self._next(self.status, pc_request=request)

    def pc_answered(
        self,
        line_no: int,
        deliveries: Sequence[tuple[Decimal, date]],
        actor: Actor,
        at: datetime,
    ) -> Corrected:
        """The case's values with PC's answer for one line too, for its checks
        to run on as a change the customer asked is (`changed`, ticket 27).

        ``deliveries``: each quantity with PC's date, in PC's order. Refused
        where PC's answer is not taken (`_CHANGEABLE`), for a line the case
        lacks, for a line the PO prints split that PC would split otherwise
        (one date per printed schedule; another split is the customer's to
        agree), and for quantities that do not add up to the line's: a split
        that does not add up is a person's to settle with PC, never adjusted
        here.

        A re-confirmation keeps the date PC confirmed first: delivery by
        delivery while PC keeps the line's quantities as they were; split
        anew, every delivery keeps the line's earliest first date, the one PC
        gave the line first. The answer is recorded as PC's agreement on a
        short lead time as well (`record_pc_confirmation`).
        """
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if self.status not in _CHANGEABLE:
            raise ConflictError(
                f"PC's dates are not recorded from DW1 in {self.status}",
                details={**details, "status": self.status.value, "rule": "pc_status"},
            )
        line = self.line(line_no)
        if not deliveries:
            raise DomainError("PC's answer gives the line a date", details=details)
        quantities = tuple(quantity for quantity, _ in deliveries)
        po = line.effective
        if po.prints_schedules:
            if quantities != tuple(s.quantity for s in po.schedules):
                raise ConflictError(
                    "the PO prints the line's schedules: PC confirms one date per schedule",
                    details={**details, "rule": "printed_schedules"},
                )
        elif sum(quantities, Decimal(0)) != po.quantity:
            raise ConflictError(
                "PC's quantities do not add up to the line's: settle it with PC",
                details={**details, "deliveries": len(quantities), "rule": "split_not_summing"},
            )
        answer = reconfirmed(line, deliveries, actor.user_id, at)
        new_line = OrderLine.model_validate(
            {
                **dict(line),
                "pc_answer": answer,
                "pc_confirmed_by": actor.user_id,
                "pc_confirmed_at": at,
            }
        )
        lines = tuple(new_line if x.line_no == line_no else x for x in self.lines)
        entered = _entered(self.document, lines, self.header_corrections)
        return Corrected(
            line_no, lines, self.header_corrections, entered, frozenset({line_no}), False
        )

    def take_pc_answer(
        self,
        line_no: int,
        deliveries: Sequence[tuple[Decimal, date]],
        actor: Actor,
        at: datetime,
        recheck: Recheck,
    ) -> OrderCase:
        """PC's answer for one line, taken with the checks run again on the
        line (`pc_answered`), as a change the customer asked is taken
        (`take_change`): a prepared order reopens its self-check, since its
        paste sheet changes. The wait on PC ends once every line asked has
        its answer (`PcRequest.answered`)."""
        corrected = self.pc_answered(line_no, deliveries, actor, at)
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        taken = self._rechecked(corrected, recheck, details)
        request = self.pc_request
        if request is not None and request.answered(taken.lines):
            request = None
        return self._edited(**taken.changes(), pc_request=request)

    # ------------------------------------------------ Design (ticket 06) --

    def ask_design(self, line_no: int, actor: Actor, at: datetime) -> OrderCase:
        """Sales sent Design the request to create a PRV code for a line no
        item fits (from their own mailbox: DW1 sends nothing). The case waits
        on Design for that line from ``at``; asked again, the wait starts
        again. Only for an `unmapped` line, where mappings are decided
        (`_EDITABLE`). No value of the case changes, so a self-check stands;
        the wait ends when the line's code is confirmed (`_next`)."""
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if self.status not in _EDITABLE:
            raise ConflictError(
                f"Design is not asked from DW1 in {self.status}",
                details={**details, "status": self.status.value, "rule": "design_status"},
            )
        if self.line(line_no).mapping.status is not MappingStatus.UNMAPPED:
            raise ConflictError(
                "only a line no item fits is a code for Design to create",
                details={**details, "rule": "design_line_has_code"},
            )
        request = DesignRequest(line_no=line_no, by=actor.user_id, at=at)
        others = tuple(r for r in self.design_requests if r.line_no != line_no)
        return self._next(self.status, design_requests=(*others, request))

    # ------------------------------------------- the update loop (ticket 29) --

    def loop_target(self, loop_line: LoopLine) -> PoLine:
        """The line as the customer asks it: as entered, each value the loop
        changes replaced. What PC is asked about and answers for."""
        return _with_values(self.line(loop_line.line_no).effective, loop_line.changes)

    def loop_change(self, line_no: int, change: AppliedChange, actor: Actor) -> OrderCase:
        """A change the customer asked, confirmed by the PIC on an order whose
        confirmation has left, agreed yet or not (ADR 0010 decision 3,
        ticket 28): it joins the
        update loop, which waits to be asked of PC, and the order itself does
        not change until the customer accepts PC's answer (`take_update`).

        Refused in any other status: before Bravo a change is taken at once
        (`take_change`); between the Bravo entry and the confirmation the
        PIC sends the confirmation first. Refused for a line printing its
        schedules, for a change of another request while one is in the loop
        (`update_busy`), and once PC has been asked (`update_step`): the
        request's lines are all decided before PC is asked, and for a line
        PC cancelled (`line_cancelled`, ticket 10): nothing of it is
        delivered any more."""
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        if self.status not in CONFIRMATION_LEFT:
            raise ConflictError(
                f"a change asked by mail is not taken in {self.status}",
                details={**details, "status": self.status.value, "rule": "change_status"},
            )
        if change.by != actor.user_id:
            raise DomainError("a decision is recorded as its actor's", details=details)
        _require_not_cancelled(self.line(line_no), details)
        if self.line(line_no).po_line.prints_schedules:
            raise ConflictError(
                "the line prints its schedules: which one changes is asked of the customer",
                details={**details, "rule": "printed_schedules"},
            )
        loop = self.update_loop
        if loop is None:
            added = LoopLine(line_no=line_no, changes=(change,))
            return self._next(
                self.status,
                update_loop=UpdateLoop(
                    request_id=change.request_id, step="ask_pc", since=change.at, lines=(added,)
                ),
            )
        if loop.request_id != change.request_id:
            raise ConflictError(
                "đơn đang trong một vòng cập nhật của yêu cầu khác",
                details={**details, "rule": "update_busy"},
            )
        self._loop("ask_pc")
        held = loop.line(line_no)
        joined = LoopLine(
            line_no=line_no,
            changes=(change,) if held is None else (*_without(held.changes, change.field), change),
        )
        lines = sorted(
            (*(x for x in loop.lines if x.line_no != line_no), joined), key=lambda x: x.line_no
        )
        return self._next(self.status, update_loop=_loop_with(loop, lines=tuple(lines)))

    def loop_ask_pc(self, at: datetime) -> OrderCase:
        """6-DW2: Sales asked PC about the changed lines (from their own
        account: DW1 sends nothing). The case waits on PC from ``at``; asked
        again, the wait starts again and the answers recorded stay."""
        loop = self._loop("ask_pc", "waiting_pc")
        return self._next(self.status, update_loop=_loop_with(loop, step="waiting_pc", since=at))

    def loop_pc_answer(
        self,
        line_no: int,
        deliveries: Sequence[tuple[Decimal, date]],
        actor: Actor,
        at: datetime,
    ) -> OrderCase:
        """PC's answer for one changed line: its deliveries, which add up to
        the quantity asked (or held, when only the date changes); a split that
        does not is refused, never adjusted. With the last line's answer the
        loop is past waiting on PC: code compares PC's dates with the dates
        asked (`_verdict`) and the answer to the customer is drafted. The
        order's own line does not change."""
        loop = self._loop("waiting_pc")
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line_no}
        held = loop.line(line_no)
        if held is None:
            raise ConflictError(
                "PC is not asked about this line", details={**details, "rule": "update_line"}
            )
        if not deliveries:
            raise DomainError("PC's answer gives the line a date", details=details)
        quantities = [quantity for quantity, _ in deliveries]
        if sum(quantities, Decimal(0)) != self.loop_target(held).quantity:
            raise ConflictError(
                "PC's quantities do not add up to the quantity asked: settle it with PC",
                details={**details, "deliveries": len(quantities), "rule": "split_not_summing"},
            )
        answer = PcAnswer(
            deliveries=tuple(
                PcDelivery(quantity=quantity, first_date=day, date=day)
                for quantity, day in deliveries
            ),
            by=actor.user_id,
            at=at,
        )
        answered = LoopLine.model_validate({**dict(held), "pc_answer": answer})
        lines = tuple(answered if x.line_no == line_no else x for x in loop.lines)
        if all(x.pc_answer is not None for x in lines):
            after = _loop_with(
                loop, lines=lines, step="answer_customer", since=at, verdict=self._verdict(lines)
            )
        else:
            after = _loop_with(loop, lines=lines)
        return self._next(self.status, update_loop=after)

    def _verdict(self, lines: Iterable[LoopLine]) -> PcVerdict:
        """6-DW4 when every delivery PC gives is on the date asked (or held,
        when only the quantity changes) of its line, 6-DW3 otherwise: compared
        by code, never read by a model."""
        for loop_line in lines:
            asked = self.loop_target(loop_line).requested_date
            assert loop_line.pc_answer is not None  # every line answered
            if any(d.date != asked for d in loop_line.pc_answer.deliveries):
                return "proposes"
        return "can_do"

    def loop_answer_sent(self, at: datetime) -> OrderCase:
        """6-DW4 or 6-DW3 sent to the customer by a person (DW1 sends
        nothing): the case waits on the customer from ``at``."""
        loop = self._loop("answer_customer")
        return self._next(
            self.status, update_loop=_loop_with(loop, step="waiting_customer", since=at)
        )

    def loop_answered(self, answer: CustomerAnswer, at: datetime) -> OrderCase:
        """The customer's answer as a person recorded it, but acceptance
        (`take_update`, which applies the change): ``keep`` ends the loop and
        leaves the order exactly as it was; ``ask_pc_again`` drops PC's answers
        and waits to ask PC again. Only once the answer was sent: a customer's
        word while PC has not answered is refused (`update_step`)."""
        loop = self._loop("waiting_customer")
        if answer == "keep":
            return self._next(self.status, update_loop=None)
        if answer == "ask_pc_again":
            lines = tuple(x.model_copy(update={"pc_answer": None}) for x in loop.lines)
            return self._next(
                self.status,
                update_loop=_loop_with(loop, lines=lines, step="ask_pc", since=at, verdict=None),
            )
        raise DomainError(
            "the customer's acceptance applies the change",
            details={"case_id": str(self.case_id), "answer": answer},
        )

    def update_accepted(self) -> Corrected:
        """The case's values with the customer's accepted change applied, for
        its checks to run on: each changed line takes the changes (as
        `changed` does) and PC's answer, its first confirmed dates kept
        (`reconfirmed`), and its confirmed dates cleared, to be confirmed
        again."""
        return self._loop_applied(self._loop("waiting_customer"))

    def _loop_applied(self, loop: UpdateLoop) -> Corrected:
        """The case's values with ``loop``'s changes and PC's answers applied
        (`update_accepted`'s docstring): the one owner of what a line in the
        loop becomes, for a customer's change and Proterial's own alike."""
        lines: list[OrderLine] = []
        for line in self.lines:
            held = loop.line(line.line_no)
            if held is None:
                lines.append(line)
                continue
            # Waiting on the customer, or Proterial's own change: answered.
            assert held.pc_answer is not None
            fields = {c.field for c in held.changes}
            pc = held.pc_answer
            lines.append(
                OrderLine.model_validate(
                    {
                        **dict(line),
                        "changes": (
                            *(c for c in line.changes if c.field not in fields),
                            *held.changes,
                        ),
                        "pc_answer": reconfirmed(
                            line,
                            [(d.quantity, d.date) for d in pc.deliveries],
                            pc.by,
                            pc.at,
                        ),
                        "confirmed_delivery_dates": (),
                    }
                )
            )
        numbers = frozenset(x.line_no for x in loop.lines)
        entered = _entered(self.document, lines, self.header_corrections)
        return Corrected(
            min(numbers), tuple(lines), self.header_corrections, entered, numbers, False
        )

    def take_update(self, at: datetime, recheck: Recheck) -> OrderCase:
        """The customer accepted: the change is applied with the checks run
        again on the changed lines (`update_accepted`), and the order goes to
        ``change_review`` for the Bravo update (6.2-SP), its cross-check and
        confirmation cleared as a revision in Bravo clears them. PC answered
        for the values asked, so its answer stands as its agreement on a
        short lead time (as `pc_answered`'s does)."""
        corrected = self.update_accepted()
        loop = self.update_loop
        assert loop is not None  # `update_accepted` required it
        return self._loop_taken(corrected, _loop_with(loop, step="bravo_update", since=at), recheck)

    @property
    def takes_internal_change(self) -> bool:
        """Whether Proterial's own change may be applied now (ticket 10): the
        confirmation has left and no other change is in the update loop. What
        the page offers "Thay đổi nội bộ" by, and `internal_change` refuses by."""
        return self.status in CONFIRMATION_LEFT and self.update_loop is None

    def internal_change(
        self,
        change_id: uuid.UUID,
        reason: InternalReason,
        lines: Mapping[int, Sequence[tuple[Decimal, date]]],
        actor: Actor,
        at: datetime,
    ) -> UpdateLoop:
        """Proterial's own change of a confirmed order (ticket 10, the BA's
        6.1B) as the update loop it starts: per line, the deliveries PC now
        gives it, each a quantity and PC's date, as a person applies them.
        No customer asked it, so the loop begins at its Bravo update (6.2-SP)
        and the order is entered, cross-checked and confirmed again as an
        accepted change is (`take_internal_change`).

        A line's deliveries add up to its quantity (a date moved, a line
        split) or to less (PC cuts it: part of it cancelled, and its quantity
        becomes theirs); never to more, which is no change Proterial makes
        alone (`quantity_raised`). No delivery at all: PC cancels the whole
        line (W07 "cancel all"; `OrderLine.cancelled`), never every line of
        the order (`every_line_cancelled`: that is the order cancelled, no
        change of it). A line the PO prints split keeps its schedules'
        quantities: PC moves their dates only. Refused but on an order whose
        confirmation has left, while another change is in the loop
        (`update_busy`), for a line the order does not have, for a line PC
        cancelled before (`line_cancelled`), and for a line it changes
        nothing on (`no_change`)."""
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if not self.takes_internal_change:
            if self.status in CONFIRMATION_LEFT:
                raise ConflictError(
                    "đơn đang trong một vòng cập nhật khác",
                    details={**details, "rule": "update_busy"},
                )
            raise ConflictError(
                f"Proterial's own change is not taken in {self.status}",
                details={**details, "status": self.status.value, "rule": "change_status"},
            )
        if not lines:
            raise DomainError("an internal change names the lines it changes", details=details)
        if len(lines) > INTERNAL_LINES_MAX:
            raise DomainError(
                "an internal change names too many lines",
                details={**details, "lines": len(lines), "max": INTERNAL_LINES_MAX},
            )
        held = {line.line_no: line for line in self.lines}
        if missing := sorted(set(lines) - held.keys()):
            raise ConflictError(
                "đơn không có dòng này",
                details={**details, "lines": missing, "rule": "no_such_line"},
            )
        loop_lines = [
            self._internal_line(held[no], lines[no], change_id, actor, at) for no in sorted(lines)
        ]
        cancelled = {no for no, line in held.items() if line.cancelled}
        cancelled |= {x.line_no for x in loop_lines if x.pc_answer and not x.pc_answer.deliveries}
        if cancelled == held.keys():
            raise ConflictError(
                "PC huỷ mọi dòng là huỷ cả đơn, không phải thay đổi nội bộ",
                details={**details, "rule": "every_line_cancelled"},
            )
        return UpdateLoop(
            request_id=change_id,
            step="bravo_update",
            since=at,
            lines=tuple(loop_lines),
            reason=reason,
        )

    def _internal_line(
        self,
        line: OrderLine,
        deliveries: Sequence[tuple[Decimal, date]],
        change_id: uuid.UUID,
        actor: Actor,
        at: datetime,
    ) -> LoopLine:
        """One line of `internal_change`, checked as its docstring says."""
        details: dict[str, object] = {"case_id": str(self.case_id), "line": line.line_no}
        if len(deliveries) > PC_DELIVERIES_MAX:
            raise DomainError(
                "PC splits a line into too many deliveries",
                details={**details, "max": PC_DELIVERIES_MAX},
            )
        _require_not_cancelled(line, details)
        quantities = tuple(quantity for quantity, _ in deliveries)
        total = sum(quantities, Decimal(0))
        po = line.effective
        if total > po.quantity:
            raise ConflictError(
                "thay đổi nội bộ không tăng số lượng khách đặt",
                details={**details, "rule": "quantity_raised"},
            )
        if po.prints_schedules and quantities != tuple(s.quantity for s in po.schedules):
            raise ConflictError(
                "dòng in sẵn các đợt giao: PC chỉ dời ngày từng đợt",
                details={**details, "rule": "printed_schedules"},
            )
        if total == po.quantity and tuple(deliveries) == line.confirmed_deliveries():
            raise ConflictError("dòng này không đổi gì", details={**details, "rule": "no_change"})
        cut = (
            ()
            if total in (po.quantity, 0)
            else (
                AppliedChange(
                    field="quantity",
                    value=format(total.normalize(), "f"),
                    request_id=change_id,
                    by=actor.user_id,
                    at=at,
                ),
            )
        )
        answer = PcAnswer(
            deliveries=tuple(
                PcDelivery(quantity=quantity, first_date=day, date=day)
                for quantity, day in deliveries
            ),
            by=actor.user_id,
            at=at,
        )
        return LoopLine(line_no=line.line_no, changes=cut, pc_answer=answer)

    def internal_changed(self, loop: UpdateLoop) -> Corrected:
        """The case's values with Proterial's own change applied, for its
        checks to run on (`_loop_applied`); ``loop`` is `internal_change`'s."""
        return self._loop_applied(loop)

    def take_internal_change(
        self,
        change_id: uuid.UUID,
        reason: InternalReason,
        lines: Mapping[int, Sequence[tuple[Decimal, date]]],
        actor: Actor,
        at: datetime,
        recheck: Recheck,
    ) -> OrderCase:
        """Proterial's own change applied with the changed lines' checks run
        again, as an accepted change is (`take_update`): the order goes to
        ``change_review`` for its Bravo update, then back to its cross-check
        and its confirmation. The one point the case changes."""
        loop = self.internal_change(change_id, reason, lines, actor, at)
        return self._loop_taken(self._loop_applied(loop), loop, recheck)

    def _loop_taken(self, corrected: Corrected, loop: UpdateLoop, recheck: Recheck) -> OrderCase:
        """``corrected`` taken with ``recheck``'s results, the order at its
        Bravo update (``loop``) in ``change_review``, its cross-check and
        confirmation cleared."""
        taken = self._rechecked(corrected, recheck, {"case_id": str(self.case_id)})
        lines = tuple(
            OrderLine.model_validate(
                {**dict(x), "pc_confirmed_by": x.pc_answer.by, "pc_confirmed_at": x.pc_answer.at}
            )
            if loop.line(x.line_no) is not None and x.pc_answer is not None
            else x
            for x in taken.lines
        )
        return self._next(
            transition(self.status, _S.CHANGE_REVIEW),
            **taken._replace(lines=lines).changes(),
            cross_checked_by=None,
            cross_checked_at=None,
            confirmed_by=None,
            confirmed_at=None,
            update_loop=loop,
        )

    def approve_update(
        self, artifact_id: uuid.UUID, sha256: str, rendered_on: int, actor: Actor, at: datetime
    ) -> OrderCase:
        """6.2-SP: the PIC approves the exact Bravo update file, drawn at the
        case's current version, by its id and hash (ADR 0026 as amended). A
        later change to the case drops the approval (`_edited`); the file is
        approved before it is entered, and refused while a finding is open."""
        loop = self._loop("bravo_update")
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if self.status is not _S.CHANGE_REVIEW:
            raise ConflictError(
                "the Bravo update is approved before it is entered",
                details={**details, "status": self.status.value, "rule": "update_step"},
            )
        if loop.approval is not None:
            raise ConflictError(
                "tệp cập nhật Bravo đã được duyệt",
                details={**details, "rule": "bravo_update_approved"},
            )
        if rendered_on != self.case_version:
            raise ConflictError(
                "tài liệu được tạo từ một phiên bản hồ sơ cũ: tạo lại để duyệt bản mới",
                details={**details, "rule": "stale_artifact"},
            )
        self._require_decided()
        approval = BravoUpdateApproval(
            artifact_id=artifact_id,
            sha256=sha256,
            case_version=rendered_on,
            by=actor.user_id,
            at=at,
        )
        return self._next(self.status, update_loop=_loop_with(loop, approval=approval))

    def _loop(self, *steps: UpdateStep) -> UpdateLoop:
        """The update loop, at one of ``steps``; refused otherwise."""
        loop = self.update_loop
        if loop is None or loop.step not in steps:
            raise ConflictError(
                "bước này không phải bước vòng cập nhật đang chờ",
                details={
                    "case_id": str(self.case_id),
                    "step": None if loop is None else loop.step,
                    "expected": list(steps),
                    "rule": "update_step",
                },
            )
        return loop

    def confirm(
        self,
        actor: Actor,
        at: datetime,
        delivery_dates: Mapping[int, Sequence[date]],
        confirmation: ConfirmationSent | None = None,
    ) -> OrderCase:
        """-> confirmation_sent, with the dates Sales confirms for every line
        (step 10): one per delivery, so a line split over several schedules
        gets one per schedule, in their order (ticket 35), and any other line
        one; and what left (``confirmation``: when, from which sent copy, and
        the customer's term of silence, `confirmation_sent`; none named: sent
        at ``at``, never agreed by silence).

        From ``cross_checked``; from ``uploaded_to_bravo`` only when the rules
        stamped on the case need no cross-check. Refused while
        `missing_noc_esf` is open, or present at all under
        ``block_confirmation``, and while a short lead time has no PC date.
        """
        status = transition(self.status, _S.CONFIRMATION_SENT)
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if self.awaits_cross_check:
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
        # A line PC cancelled (ticket 10) is delivered never: no date, named
        # or not.
        delivered = {line.line_no for line in self.lines if not line.cancelled}
        if not delivered <= set(delivery_dates) <= {line.line_no for line in self.lines}:
            raise DomainError("every line gets its confirmed delivery date", details=details)
        if miscounted := [
            line.line_no
            for line in self.lines
            if len(delivery_dates.get(line.line_no, ())) != line.deliveries
        ]:
            raise DomainError(
                "a line gets one confirmed date per delivery schedule",
                details={**details, "lines": miscounted, "rule": "date_per_schedule"},
            )
        lines = tuple(
            OrderLine.model_validate(
                {
                    **dict(line),
                    "confirmed_delivery_dates": tuple(delivery_dates.get(line.line_no, ())),
                }
            )
            for line in self.lines
        )
        return self._next(
            status,
            lines=lines,
            confirmed_by=actor.user_id,
            confirmed_at=at,
            confirmation=confirmation or ConfirmationSent(sent_at=at),
        )

    def confirmation_sent(
        self,
        sent_at: datetime,
        term: ImpliedTerm | None,
        zone: ZoneInfo,
        *,
        message_id: str | None = None,
    ) -> ConfirmationSent:
        """What left, as `confirm` records it: sent at ``sent_at`` (the sent
        copy's time, or when the PIC recorded it), and, where the customer
        has a ``term`` of silence, the instant it counts as agreement, in the
        tenant's ``zone``. No term: never implied (ADR 0011)."""
        return ConfirmationSent(
            sent_at=sent_at,
            message_id=message_id,
            term=term,
            implied_from=(
                None
                if term is None
                else term.implied_from(sent_at, self.effective_header.po_date, zone)
            ),
        )

    def agreed(
        self,
        how: AgreementHow,
        actor: Actor,
        at: datetime,
        *,
        message_id: str | None = None,
        quotes: Sequence[str] = (),
    ) -> OrderCase:
        """confirmation_sent -> confirmed: the customer agreed, as a person
        records it (ADR 0011). ``accepted``: in words, from one of their
        replies when the person recorded it from one. ``implied``: only once
        the customer's term of silence, stamped when the confirmation left,
        has run out at ``at``; never for a customer with no term.

        Refused while a customer's change runs in the update loop: their
        answer there is the loop's (`loop_answered`)."""
        details: dict[str, object] = {"case_id": str(self.case_id), "how": how}
        status = transition(self.status, _S.CONFIRMED)
        if self.update_loop is not None:
            raise ConflictError(_ANSWER_IN_THE_LOOP, details={**details, "rule": "update_running"})
        sent = self.confirmation
        assert sent is not None  # stamped with confirmation_sent
        if how == "implied":
            if sent.implied_from is None:
                raise ConflictError(
                    "khách này không có số ngày im lặng được coi là đồng ý",
                    details={**details, "rule": "no_implied_term"},
                )
            if at < sent.implied_from:
                raise ConflictError(
                    "chưa hết số ngày khách được trả lời",
                    details={**details, "rule": "implied_too_early"},
                )
        agreement = CustomerAgreement(
            how=how, by=actor.user_id, at=at, message_id=message_id, quotes=tuple(quotes)
        )
        return self._next(status, agreement=agreement)

    def implied_undone(self) -> OrderCase:
        """confirmed -> confirmation_sent: an agreement by silence taken back,
        by DW1's own recording or a person's (ticket 82): the order waits on
        the customer again, its confirmation as it left. Only silence: a
        customer's words are not undone here, they are a reply."""
        agreement = self.agreement
        if self.status is not _S.CONFIRMED or agreement is None or agreement.how != "implied":
            raise ConflictError(
                "chỉ hoàn tác được khi khách đang được ghi đồng ý ngầm",
                details={"case_id": str(self.case_id), "rule": "not_implied"},
            )
        status = transition(self.status, _S.CONFIRMATION_SENT)
        return self._next(status, agreement=None)

    def declined(self) -> OrderCase:
        """confirmation_sent -> change_review: the customer did not agree to
        the confirmation (ADR 0011, as a person records it). The order is
        reviewed as a change in Bravo is, its cross-check and confirmation
        cleared; it is then entered, cross-checked as its rules say, and its
        confirmation sent again. Refused while a customer's change runs in
        the update loop, whose answer is its own."""
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if self.status is not _S.CONFIRMATION_SENT:
            raise ConflictError(
                f"a confirmation is not declined in {self.status}",
                details={**details, "status": self.status.value, "rule": "not_awaiting_customer"},
            )
        if self.update_loop is not None:
            raise ConflictError(_ANSWER_IN_THE_LOOP, details={**details, "rule": "update_running"})
        return self._next(
            transition(self.status, _S.CHANGE_REVIEW),
            cross_checked_by=None,
            cross_checked_at=None,
            confirmed_by=None,
            confirmed_at=None,
        )

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
            cleared = self._cleared_from_prepared()
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
            # From the order as it was entered, corrections and all, to the
            # revision as read; the revision starts with no correction.
            changes=diff_lines(self.effective_document.lines, revision.document.lines),
            header_corrections=(),
            # A new revision of the PO replaces what a mail asked to change.
            update_loop=None,
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
        self._require_decided()
        loop = self.update_loop
        if loop is not None and loop.approval is None:
            # A customer's change reaches Bravo only as the file a person
            # approved (ADR 0026 as amended 2026-11-13; ticket 29).
            raise ConflictError(
                "tệp cập nhật Bravo chưa được duyệt",
                details={"case_id": str(self.case_id), "rule": "bravo_update_not_approved"},
            )
        return self._next(
            transition(self.status, _S.UPLOADED_TO_BRAVO),
            bravo_recorded_by=actor.user_id,
            bravo_recorded_at=at,
            earlier_makers=self._retired_makers(),
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

    # ------------------------------------------- a quote for the PO (ticket 09) --

    def quote_lines(self) -> tuple[int, ...]:
        """The lines a quote opened from the order asks about: those whose
        check found no valid quotation (`quotation_missing`), whatever was
        decided on the finding."""
        return tuple(
            sorted(
                {
                    f.line_no
                    for f in self.findings
                    if f.code is FindingCode.QUOTATION_MISSING and f.line_no is not None
                }
            )
        )

    def quotes_waited_on(self, settled: frozenset[uuid.UUID]) -> tuple[uuid.UUID, ...]:
        """The linked quote cases ``settled`` does not name: those the order
        waits on (`QuoteLink`)."""
        return tuple(
            link.quote_case_id for link in self.quote_links if link.quote_case_id not in settled
        )

    def quotes_for(self, line_no: int) -> tuple[uuid.UUID, ...]:
        """The quote cases opened from the order for line ``line_no``."""
        return tuple(link.quote_case_id for link in self.quote_links if line_no in link.lines)

    def open_quote(
        self,
        quote_case_id: uuid.UUID,
        actor: Actor,
        at: datetime,
        *,
        settled_quotes: frozenset[uuid.UUID] = frozenset(),
    ) -> OrderCase:
        """A person opened a quote case for `quote_lines` ("Mở báo giá",
        ticket 09); the order waits on it until it is approved or declined.
        Refused while one opened from the order is still open (opening twice
        opens one), where the order has no line without a valid quotation,
        and outside review. ``settled_quotes`` as `prepare` takes it. No
        value of the case changes."""
        details: dict[str, object] = {"case_id": str(self.case_id)}
        if self.status not in _QUOTABLE:
            raise ConflictError(
                f"a quote is not opened from an order in {self.status}",
                details={**details, "status": self.status.value, "rule": "quote_status"},
            )
        if waiting := self.quotes_waited_on(settled_quotes):
            raise ConflictError(
                "a quote opened from this order is still open",
                details={**details, "quote_case_id": str(waiting[0]), "rule": "quote_open"},
            )
        lines = self.quote_lines()
        if not lines:
            raise ConflictError(
                "every line of the order has a valid quotation",
                details={**details, "rule": "no_quotation_missing"},
            )
        link = QuoteLink(quote_case_id=quote_case_id, lines=lines, by=actor.user_id, at=at)
        return self._next(self.status, quote_links=(*self.quote_links, link))

    def quote_check(self, lines: Iterable[int]) -> Corrected:
        """The case's values as they stand, for ``lines``' checks to run again
        once their quote is approved (ticket 09): nothing is corrected, and
        no code is computed again."""
        rechecked = frozenset(lines) & {line.line_no for line in self.lines}
        if not rechecked:
            raise ConflictError(
                "no line of the order waits on an approved quotation",
                details={"case_id": str(self.case_id), "rule": "no_quoted_line"},
            )
        return Corrected(
            min(rechecked),
            self.lines,
            self.header_corrections,
            self.effective_document,
            rechecked,
            False,
        )

    def take_quote_check(self, corrected: Corrected, recheck: Recheck) -> OrderCase:
        """`quote_check`'s lines with their checks run again, as a change is
        taken (`take_change`): a prepared order reopens its self-check."""
        details: dict[str, object] = {"case_id": str(self.case_id), "rule": "quote_check"}
        return self._edited(**self._rechecked(corrected, recheck, details).changes())

    # ------------------------------------------------------------- helpers --

    def _require_compared(self, entry_compared: bool) -> None:
        if not entry_compared:
            raise DomainError(
                "the Bravo entry is recorded with the statement that it was compared with the PO",
                details={"case_id": str(self.case_id), "field": "bravo_entry_compared"},
            )

    def _require_decided(self) -> None:
        """Every finding decided but `missing_noc_esf`, which blocks only `confirmed`."""
        if open_findings := [
            f.key for f in self.findings if f.is_open and f.code is not FindingCode.MISSING_NOC_ESF
        ]:
            raise ConflictError(
                "the revision's findings are not all decided",
                details={"case_id": str(self.case_id), "open_findings": open_findings},
            )

    def _require_not_a_maker(self, actor: Actor) -> None:
        if actor.user_id in self.makers:
            raise ConflictError(
                MAKER_CHECKER_REFUSAL,
                details={"case_id": str(self.case_id), "rule": "maker_checker"},
            )

    def _edited(self, **changes: object) -> OrderCase:
        """A change to lines, mappings or dispositions, allowed where the PIC decides.

        In ``prepared`` it reopens the self-check: back to ``in_review``,
        the preparation cleared.
        """
        self._require_editable()
        if self.status is _S.PREPARED:
            return self._next(
                transition(self.status, _S.IN_REVIEW), **changes, **self._cleared_from_prepared()
            )
        loop = self.update_loop
        if loop is not None and loop.approval is not None:
            # The approved Bravo update file no longer is the case's: it is
            # approved again from a file drawn on the case as it now is.
            changes.setdefault("update_loop", loop.model_copy(update={"approval": None}))
        return self._next(self.status, **changes)

    def _require_editable(self) -> None:
        if self.status not in _EDITABLE:
            raise ConflictError(
                f"an order case is not edited in {self.status}",
                details={"case_id": str(self.case_id), "status": self.status.value},
            )

    def _retired_makers(self) -> frozenset[ActorId]:
        """The makers so far, as the earlier ones of the next round."""
        current = (self.prepared_by, self.bravo_recorded_by)
        return self.earlier_makers | {name for name in current if name is not None}

    def _cleared_from_prepared(self) -> dict[str, object]:
        """The preparation and the Bravo entry cleared, their makers kept."""
        return {**_CLEARED_FROM_PREPARED, "earlier_makers": self._retired_makers()}

    def _next(self, status: OrderStatus, **changes: object) -> OrderCase:
        if status is not self.status:
            # A case that moves on no longer waits on the decision not applied.
            changes.setdefault("unapplied_decision", None)
        if status not in _CHANGEABLE:
            # Nor on PC, once its answer can no longer be taken here (ticket
            # 07): in Bravo, PC's dates are the update loop's (ticket 29).
            changes.setdefault("pc_request", None)
        # The wait on Design ends with the line's code, a new revision or a
        # case that leaves review (ticket 06).
        lines = cast(Sequence[OrderLine], changes.get("lines", self.lines))
        waiting = _waiting_on_design(self.design_requests, status, lines)
        changes.setdefault("design_requests", waiting)
        if status not in CONFIRMATION_LEFT:
            # What left and the customer's answer belong to that confirmation:
            # a revision, a decline or an accepted change clears them.
            changes.setdefault("confirmation", None)
        if status is not _S.CONFIRMED:
            changes.setdefault("agreement", None)
        loop = self.update_loop
        if loop is not None and (
            status not in _LOOP_STATUSES[loop.step]
            or (status is _S.CONFIRMATION_SENT and self.status not in CONFIRMATION_LEFT)
        ):
            # The update loop ends where its step does not stand: the
            # confirmation sent again, a new revision, a return from the
            # cross-check.
            changes.setdefault("update_loop", None)
        # Validated again: `model_copy(update=...)` would skip the invariants.
        return OrderCase.model_validate(
            {**dict(self), **changes, "status": status, "case_version": self.case_version + 1}
        )


def _waiting_on_design(
    requests: tuple[DesignRequest, ...], status: OrderStatus, lines: Sequence[OrderLine]
) -> tuple[DesignRequest, ...]:
    """The requests to Design a case at ``status`` with ``lines`` still waits
    on: where mappings are decided, for a line still without a code."""
    if status not in _EDITABLE:
        return ()
    unmapped = {x.line_no for x in lines if x.mapping.status is MappingStatus.UNMAPPED}
    return tuple(r for r in requests if r.line_no in unmapped)


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


# The note a `value_uncertain` is resolved with once each value it flagged is
# typed: the values themselves are on the line or the header, per field.
_TYPED_PER_FIELD: Final = "Sales nhập lại từng giá trị bị gắn cờ"


def _without[V: (ValueCorrection, AppliedChange)](values: Iterable[V], field: str) -> tuple[V, ...]:
    return tuple(c for c in values if c.field != field)


def _loop_with(loop: UpdateLoop, **changes: object) -> UpdateLoop:
    """``loop`` with ``changes``, validated again (`model_copy` would skip it);
    a new step only along `_LOOP_NEXT`."""
    step = changes.get("step", loop.step)
    if step != loop.step and step not in _LOOP_NEXT[loop.step]:
        raise ValueError(f"the update loop does not move from {loop.step} to {step}")
    return UpdateLoop.model_validate({**dict(loop), **changes})


def _require_not_cancelled(line: OrderLine, details: Mapping[str, object]) -> None:
    """A line PC cancelled takes no change, Proterial's or the customer's
    (ticket 10): it is delivered never, and reviving it is no change
    either side makes by itself."""
    if line.cancelled:
        raise ConflictError(
            "dòng này đã huỷ", details={**details, "line": line.line_no, "rule": "line_cancelled"}
        )


def _pc_dropped(line: OrderLine, field: str) -> dict[str, object]:
    """PC's answer dropped from ``line`` when ``field`` is one it was given
    for (`_PC_INPUTS`): PC answered for a quantity or a date that is no
    longer the line's, and is asked again (ticket 07)."""
    return {"pc_answer": None} if field in _PC_INPUTS else {}


def _entered(
    document: PoDocument,
    lines: Iterable[OrderLine],
    header_corrections: Sequence[ValueCorrection],
) -> PoDocument:
    """The PO as it is entered: each line's and the header's values as read,
    every corrected one replaced, validated as the document is."""
    total = document.total
    typed_total = [c for c in header_corrections if c.field == TOTAL_FIELD]
    if total is not None and typed_total:
        total = _with_values(total, [typed_total[0].model_copy(update={"field": "amount"})])
    return PoDocument.model_validate(
        {
            **dict(document),
            "header": _with_values(
                document.header, (c for c in header_corrections if c.field != TOTAL_FIELD)
            ),
            "lines": tuple(line.effective for line in lines),
            "total": total,
        }
    )


def _carried(raised: Finding, before: Finding | None) -> Finding:
    """A finding raised again keeps the decision on it while its key and the
    values it compared are the same; otherwise it is open."""
    if before is None or (before.severity, before.expected, before.actual) != (
        raised.severity,
        raised.expected,
        raised.actual,
    ):
        return raised
    return raised.model_copy(update={"disposition": before.disposition})


def _rechecked_line(line: OrderLine, check: LineCheck, findings: Iterable[Finding]) -> OrderLine:
    """``line`` as ``check`` found it on its entered values: the values as read
    and their corrections kept, the basis and suggested date its check's.
    PC's agreement on a short lead time stays while that finding is raised
    again unchanged; the date Sales confirms stays as it was."""
    short = FindingCode.REQUESTED_DATE_SHORT_LT
    was = [f for f in findings if f.code is short and f.line_no == line.line_no]
    now = [f for f in check.findings if f.code is short]
    same = len(was) == len(now) == 1 and (was[0].expected, was[0].actual) == (
        now[0].expected,
        now[0].actual,
    )
    return OrderLine.model_validate(
        {
            **dict(check.line),
            "po_line": line.po_line,
            "corrections": line.corrections,
            "changes": line.changes,
            "confirmed_delivery_dates": line.confirmed_delivery_dates,
            "pc_answer": line.pc_answer,
            "pc_confirmed_by": line.pc_confirmed_by if same else None,
            "pc_confirmed_at": line.pc_confirmed_at if same else None,
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
