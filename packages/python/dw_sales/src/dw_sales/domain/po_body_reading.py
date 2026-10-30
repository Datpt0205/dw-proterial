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
   customers group them, dates day first, a year guessed from the day the
   mail arrived). A currency nobody wrote is not guessed (``currency_missing``).
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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from dw_sales.domain.anchors import MessageText, SourceAnchor, TextRange
from dw_sales.domain.layouts import flagged_everywhere
from dw_sales.domain.orders import (
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoLine,
    PoLineAnchors,
    PrintedText,
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


# An amount with cents, grouped one way and pointed the other: `2,792.00`,
# `2.792,00`. Only for an amount or a total: a quantity or a price written
# `1.200,5` stays unread (`rfq_reading.parse_number`).
_MONEY = re.compile(r"(\d{1,3}(?:([.,])\d{3})+)([.,])(\d{2})")


def parse_amount(span: str) -> Decimal | None:
    """A printed amount or total: one number, currency words around it."""
    numbers = re.findall(r"\d[\d.,]*\d|\d", normalised(span))
    if len(numbers) == 1:
        money = _MONEY.fullmatch(numbers[0])
        if (
            money is not None
            and money.group(2) != money.group(3)
            and {c for c in money.group(1) if not c.isdigit()} == {money.group(2)}
        ):
            return Decimal(f"{money.group(1).replace(money.group(2), '')}.{money.group(4)}")
    return parse_price(span)


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


def read_po_body(
    text: str, answer: ModelPoBody, received_on: date, *, parser_version: str
) -> PoBodyVerdict:
    """What of ``answer`` code accepts of the PO written in ``text`` (module
    docstring, checks 1-5). ``text`` is the message's newest part as
    `mail_parts.newest_part` gives it, NFKC-normalised; ``parser_version``
    the prompt it was read under, stamped on the PO. Never raises on the
    model's answer."""
    body = _Body(text)
    refused: Counter[str] = Counter()

    def none(reason: str) -> PoBodyVerdict:
        return PoBodyVerdict(None, reason, refused)

    def header[T](span: str | None, parse: Callable[[str], T | None], name: str) -> _Read[T] | None:
        if span is None:
            return None
        place = body.first(span)
        if place is None:
            refused[f"{name}_not_found"] += 1
            return None
        value = parse(text[place[0] : place[1]])
        if value is None:
            refused[f"{name}_unparsed"] += 1
            return None
        return _Read(value, body.anchor(*place))

    po_no = header(answer.po_no_span, _printed, "po_no")
    if po_no is None:
        return none("no_po_number")
    currency = header(answer.currency_span, parse_currency, "currency")
    if currency is None:
        return none("currency_missing")
    if not answer.lines:
        return none("no_lines")
    po_date = header(answer.po_date_span, lambda s: parse_date(s, received_on), "po_date")
    lines: list[PoLine] = []
    starts: set[int] = set()
    for number, raw in enumerate(answer.lines, start=1):
        line = _line(body, raw, number, received_on, refused)
        if line is None:
            return none("line_refused")
        start = line.anchors.line_no.chars
        assert start is not None  # every anchor here is a range of the text
        if start.start in starts:
            refused["line_repeated"] += 1
            return none("line_refused")
        starts.add(start.start)
        lines.append(line)
    total = header(answer.total_span, parse_amount, "total")
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
    return PoBodyVerdict(flagged_everywhere(document, RegionFlag.MODEL_READ), None, refused)


def _line(
    body: _Body, raw: ModelPoLine, number: int, received_on: date, refused: Counter[str]
) -> PoLine | None:
    line = body.folded.locate(normalised(raw.line_span), bounded=True)
    if isinstance(line, str):
        refused[f"line_{line.removeprefix('span_')}"] += 1
        return None

    def read[T](span: str | None, parse: Callable[[str], T | None], name: str) -> _Read[T] | None:
        if span is None:
            return None
        found = body.folded.locate(normalised(span), bounded=True, within=line)
        if isinstance(found, str):
            refused[f"{name}_{found.removeprefix('span_')}"] += 1
            return None
        value = parse(body.text[found[0] : found[1]])
        if value is None:
            refused[f"{name}_unparsed"] += 1
            return None
        return _Read(value, body.anchor(*found))

    line_anchor = body.anchor(*line)
    code = read(raw.customer_item_code_span, _printed, "customer_item_code")
    quantity = read(raw.quantity_span, parse_quantity, "quantity")
    unit_price = read(raw.unit_price_span, parse_price, "unit_price")
    uom = read(raw.uom_span, _uom, "uom")
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
    description = read(raw.description_span, _printed, "description")
    amount = read(raw.amount_span, parse_amount, "amount")
    requested = read(raw.requested_date_span, lambda s: parse_date(s, received_on), "date")
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
