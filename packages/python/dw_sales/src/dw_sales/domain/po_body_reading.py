"""A model's reading of a PO written in the mail body, and what code accepts of it.

AI item 4, dw_sales ADR 0005. A customer who writes the order in the mail
itself, with no file, used to be routed to Sales "it names an order but
carries no document", and the PO was typed by hand. Where a tenant turns it
on (`sales_order_rules.model_assist.po_body_extraction`), a local model reads
it instead, and this module decides what of its reading counts. It is
`domain.rfq_reading`'s rule applied to an order: the model gives span text,
code locates and parses it, and every value is flagged for Sales.

**What the model is shown**: the message's newest part (subject first, quoted
history cut by structure, `mail_parts.newest_part`), NFKC-normalised, so the
offsets an anchor stores are offsets into what the model saw and what the
case keeps (`PoDocument.body`).

**What the model gives** (`ModelPoBody`): span text only. The PO's number,
date, currency and total as written, and for each line the line as written
and, within it, the customer's item code, the description, the quantity, the
unit, the unit price, the amount and the requested date. Never a parsed
value, a customer, an item code of ours or a route.

**What code checks** (`read_po_body`):

1. The PO number is found as a whole token run; without one the mail is no
   PO DW1 reads (``no_po_number``).
2. Every line is found once as a whole token run, and every field span once,
   as a whole token run, inside its line: ``24`` of ``AWG24`` is not a token,
   and a value from another line is not inside this one. A line whose item
   code, quantity, unit or unit price is not found and parsed refuses the
   whole PO: reading part of an order would leave out lines nobody knows are
   missing. The same line twice refuses it too.
3. Every value is parsed from its span (`rfq_reading`'s parsers: numbers as
   customers group them, a numeric date's order and an ambiguous grouping
   such as ``1.250`` only as the mail's own other values settle them, or,
   where the mail says nothing, as the customer's notation record does
   (ticket 37, `notation.settle`: such a value is flagged
   `notation_from_record` too, and one the mail reads otherwise than the
   record is not read), a year guessed from the day the mail arrived). A
   currency nobody wrote is not guessed (``currency_missing``), and neither
   is the one a bare ``$`` means.
4. What the mail does not write is the value it implies, anchored where the
   values it is made from are, as a form that prints no revision reads as
   revision 0 at its PO number (ticket 30): no revision is revision 0, no PO
   date is the day the mail arrived, both at the PO number; no amount is the
   quantity times the unit price, at the unit price; no description is empty,
   at the item code; no requested date is none, at the line, which raises
   `requested_date_missing` as a blank date cell does.
5. Every value is flagged `model_read`, so each is `value_uncertain` and Sales
   confirms it against the mail, field by field.

What remains a model's judgement is which field the words fill (a reel length
read as the quantity, the send date as the required date). That is the
residual risk, and it is why every value is flagged rather than trusted.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from dw_platform.domain.notation import UNSTATED, Notation, notation_of, settle
from dw_sales.domain.anchors import MessageText, SourceAnchor, TextRange
from dw_sales.domain.catalog import PrintedText
from dw_sales.domain.layouts import flagged_everywhere
from dw_sales.domain.orders import (
    FlaggedValue,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoLine,
    PoLineAnchors,
    PrintedTotal,
    RegionFlag,
)
from dw_sales.domain.quotes import MESSAGE_TEXT_REGION
from dw_sales.domain.rfq_reading import (
    normalised,
    parse_currency,
    parse_date,
    parse_price,
    parse_quantity,
    text_digest,
)
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Span = str
_SPAN = Field(min_length=1, max_length=300)
# The most lines one PO in a mail is read with: its answer has to fit the room
# the server leaves after the input (about 2,000 tokens, about 120 a line). A
# longer order is a file's job, and a person's until one is attached.
MAX_LINES: Final = 15


class ModelPoLine(BaseModel):
    """One line as the model reads it: flat, every key required and
    nullable, so a server decoding against the schema writes each one. The
    line comes first, so the model reads it before it splits it."""

    model_config = _FROZEN

    line_span: Span = _SPAN
    customer_item_code_span: Span | None = _SPAN
    description_span: Span | None = _SPAN
    quantity_span: Span | None = _SPAN
    uom_span: Span | None = _SPAN
    unit_price_span: Span | None = _SPAN
    amount_span: Span | None = _SPAN
    requested_date_span: Span | None = _SPAN


class ModelPoBody(BaseModel):
    """What one call returns. No PO number: the mail holds no PO."""

    model_config = _FROZEN

    po_no_span: Span | None = _SPAN
    po_date_span: Span | None = _SPAN
    currency_span: Span | None = _SPAN
    total_span: Span | None = _SPAN
    lines: tuple[ModelPoLine, ...] = Field(max_length=MAX_LINES)


@dataclass(frozen=True, slots=True)
class PoBodyVerdict:
    """What code made of one answer: the PO, or why it is none, and what it
    refused on the way, by reason (counts only: a refusal names no customer
    word)."""

    document: PoDocument | None
    not_read: str | None
    refused: Counter[str]


_PRINTED: TypeAdapter[str] = TypeAdapter(PrintedText)
# `PoLine.uom`'s own shape: one word as written, up to 16 characters.
_UOM_TEXT = re.compile(r"[^\s\x00-\x1f\x7f]{1,16}")


def _printed(span: str) -> str | None:
    try:
        return _PRINTED.validate_python(" ".join(span.split()))
    except ValidationError:
        return None


def _uom(span: str) -> str | None:
    """The unit as written, a trailing full stop dropped (``m.``, ``pcs.``)."""
    text = span.strip().rstrip(".")
    return text if _UOM_TEXT.fullmatch(text) else None


class _Body:
    """The message's text, and where a span is in it."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.sha256 = text_digest(text)
        self.folded = FoldedText(text)

    def anchor(self, start: int, end: int) -> SourceAnchor:
        return SourceAnchor(
            attachment_id=None,
            attachment_sha256=self.sha256,
            chars=TextRange(start=start, end=end),
            quote=self.text[start:end][:500],
        )

    def first(self, span: str) -> tuple[int, int] | None:
        """The first whole-token occurrence: a PO number in the subject and
        the body is one number."""
        found = self.folded.occurrences(normalised(span), bounded=True)
        return found[0] if found else None


@dataclass(frozen=True, slots=True)
class _Read[T]:
    value: T
    anchor: SourceAnchor


@dataclass
class _Reading:
    """The mail's notation, the customer's record, and what code noted while
    reading with them: refusals by reason, and the fields only the record
    settled (``None`` for the PO's own, else the line's number)."""

    notation: Notation
    record: Notation
    refused: Counter[str] = field(default_factory=Counter)
    by_record: set[tuple[int | None, str]] = field(default_factory=set)

    def parsed[T](
        self, words: str, parse: Callable[[str, Notation], T | None], name: str, line: int | None
    ) -> T | None:
        settled = settle(lambda n: parse(words, n), self.notation, self.record)
        if settled.value is None:
            why = "contradicts_record" if settled.contradicts_record else "unparsed"
            self.refused[f"{name}_{why}"] += 1
        elif settled.by_record:
            self.by_record.add((line, name))
        return settled.value


def read_po_body(
    text: str,
    answer: ModelPoBody,
    received_on: date,
    *,
    parser_version: str,
    record: Notation = UNSTATED,
) -> PoBodyVerdict:
    """What of ``answer`` code accepts of the PO written in ``text`` (module
    docstring, checks 1-5). ``text`` is the message's newest part as
    `mail_parts.newest_part` gives it, NFKC-normalised; ``parser_version``
    the prompt it was read under, stamped on the PO; ``record`` the
    customer's notation record (ticket 37). Never raises on the model's
    answer."""
    body = _Body(text)
    # How this mail writes "1.250" and "05/11": its own other values say,
    # else the customer's record.
    reading = _Reading(notation_of(text), record)
    refused = reading.refused

    def none(reason: str) -> PoBodyVerdict:
        return PoBodyVerdict(None, reason, refused)

    def header[T](
        span: str | None, parse: Callable[[str, Notation], T | None], name: str
    ) -> _Read[T] | None:
        if span is None:
            return None
        place = body.first(span)
        if place is None:
            refused[f"{name}_not_found"] += 1
            return None
        value = reading.parsed(text[place[0] : place[1]], parse, name, None)
        return None if value is None else _Read(value, body.anchor(*place))

    po_no = header(answer.po_no_span, lambda s, _n: _printed(s), "po_no")
    if po_no is None:
        return none("no_po_number")
    currency = header(answer.currency_span, parse_currency, "currency")
    if currency is None:
        return none("currency_missing")
    if not answer.lines:
        return none("no_lines")
    po_date = header(answer.po_date_span, lambda s, n: parse_date(s, received_on, n), "po_date")
    lines: list[PoLine] = []
    starts: set[int] = set()
    for number, raw in enumerate(answer.lines, start=1):
        line = _line(body, raw, number, received_on, reading)
        if line is None:
            return none("line_refused")
        start = line.anchors.line_no.chars
        assert start is not None  # every anchor here is a range of the text
        if start.start in starts:
            refused["line_repeated"] += 1
            return none("line_refused")
        starts.add(start.start)
        lines.append(line)
    total = header(answer.total_span, parse_price, "total")
    document = PoDocument(
        attachment_id=None,
        attachment_sha256=body.sha256,
        parser_version=parser_version,
        header=PoHeader(
            po_no=po_no.value,
            revision=0,
            po_date=po_date.value if po_date is not None else received_on,
            currency=currency.value,
            anchors=PoHeaderAnchors(
                po_no=po_no.anchor,
                revision=po_no.anchor,
                po_date=po_date.anchor if po_date is not None else po_no.anchor,
                currency=currency.anchor,
            ),
        ),
        lines=tuple(lines),
        rows_printed=len(lines),
        regions=(MESSAGE_TEXT_REGION,),
        total=PrintedTotal(amount=total.value, anchor=total.anchor) if total else None,
        body=MessageText(text=text, sha256=body.sha256),
    )
    flagged = flagged_everywhere(document, RegionFlag.MODEL_READ)
    return PoBodyVerdict(_from_record(flagged, reading.by_record), None, refused)


# What a field read is called where it is flagged: the line's ``date`` is
# its ``requested_date``, the PO's ``total`` the total's ``amount``.
_FLAGGED_AS: Final = {"date": "requested_date", "total": "amount"}


def _from_record(document: PoDocument, by_record: set[tuple[int | None, str]]) -> PoDocument:
    """``document`` with each value only the customer's record settled
    flagged `notation_from_record` beside `model_read` (ticket 37)."""
    if not by_record:
        return document

    def flags(existing: tuple[FlaggedValue, ...], line: int | None, total: bool) -> list[Any]:
        names = {
            _FLAGGED_AS.get(name, name)
            for at, name in by_record
            if at == line and (name == "total") == total
        }
        added = [FlaggedValue(field=n, flag=RegionFlag.NOTATION_FROM_RECORD) for n in sorted(names)]
        return [*existing, *added]

    dumped = document.model_dump()
    dumped["header"]["flags"] = flags(document.header.flags, None, False)
    dumped["lines"] = [
        {**line.model_dump(), "flags": flags(line.flags, line.line_no, False)}
        for line in document.lines
    ]
    if document.total is not None:
        dumped["total"]["flags"] = flags(document.total.flags, None, True)
    return PoDocument.model_validate(dumped)


def _line(
    body: _Body,
    raw: ModelPoLine,
    number: int,
    received_on: date,
    reading: _Reading,
) -> PoLine | None:
    refused = reading.refused
    line = body.folded.locate(normalised(raw.line_span), bounded=True)
    if isinstance(line, str):
        refused[f"line_{line.removeprefix('span_')}"] += 1
        return None

    def read[T](
        span: str | None, parse: Callable[[str, Notation], T | None], name: str
    ) -> _Read[T] | None:
        if span is None:
            return None
        found = body.folded.locate(normalised(span), bounded=True, within=line)
        if isinstance(found, str):
            refused[f"{name}_{found.removeprefix('span_')}"] += 1
            return None
        value = reading.parsed(body.text[found[0] : found[1]], parse, name, number)
        return None if value is None else _Read(value, body.anchor(*found))

    line_anchor = body.anchor(*line)
    code = read(raw.customer_item_code_span, lambda s, _n: _printed(s), "customer_item_code")
    quantity = read(raw.quantity_span, parse_quantity, "quantity")
    unit_price = read(raw.unit_price_span, parse_price, "unit_price")
    uom = read(raw.uom_span, lambda s, _n: _uom(s), "uom")
    if code is None or quantity is None or unit_price is None:
        refused["line_incomplete"] += 1
        return None
    number_read, states_metres = quantity.value
    if uom is None and states_metres:
        uom = _Read("m", quantity.anchor)
    if uom is None:
        # A number with no unit is no quantity: `5` of what is the customer's
        # to say, never DW1's to assume.
        refused["uom_missing"] += 1
        return None
    description = read(raw.description_span, lambda s, _n: _printed(s), "description")
    amount = read(raw.amount_span, parse_price, "amount")
    requested = read(raw.requested_date_span, lambda s, n: parse_date(s, received_on, n), "date")
    return PoLine(
        line_no=number,
        customer_item_code=code.value,
        description=description.value if description else "",
        quantity=number_read,
        uom=uom.value,
        unit_price=unit_price.value,
        amount=amount.value if amount else number_read * unit_price.value,
        requested_date=requested.value if requested else None,
        anchors=PoLineAnchors(
            line_no=line_anchor,
            customer_item_code=code.anchor,
            description=description.anchor if description else code.anchor,
            quantity=quantity.anchor,
            uom=uom.anchor,
            unit_price=unit_price.anchor,
            amount=amount.anchor if amount else unit_price.anchor,
            requested_date=requested.anchor if requested else line_anchor,
        ),
    )
