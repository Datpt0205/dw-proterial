"""A model's reading of a request for quotation, and what code accepts of it.

Ticket 29, dw_sales ADR 0005. The fixed-label reader reads one Excel layout;
an RFQ written in the mail body, a PDF or the customer's own spreadsheet is
typed by hand. Where a tenant turns it on
(`sales_order_rules.model_assist.rfq_extraction`), a local model reads it
instead, and this module decides what of its reading counts.

**What the model is shown** (`TextPart`): the message's newest part (subject
first, quoted history cut by structure, `mail_parts.newest_part`) and the
text of each attachment a reader can open (a PDF page's text layer, a sheet's
visible cells), each under an id code chose. Normalised (NFKC) before it is
sent, so the offsets a value is anchored at are offsets into what the model
saw and what the case stores.

**What the model gives** (`ModelRfqReading`): span text only. For each item,
the part it is in, the item's line as written, and within that line the
description, and where stated the customer's code, the quantity, the unit,
the required date and a target price; for the request, its number, the due
date of the quotation and the currency. Never a parsed value, a customer, an
item code of ours or a route.

**What code checks** (`verify_rfq`):

1. The part is one it was sent. The line is found in it once, as a whole
   token run; a line found only in quoted history is not in the part at all,
   and one found twice is refused.
2. Every field span is found exactly once, as a whole token run, inside its
   line: ``24`` of ``AWG24`` is not a token, and a span from another line is
   not inside this one. A span that is not found is dropped, never repaired.
3. Every value is parsed from its span by the parsers below. A quantity is
   taken only in metres (the seller's one unit), from a unit the span or the
   unit span states: ``5 reels`` is no quantity. A date without a year takes
   the one that puts it on or after the day the mail arrived, less a month.
4. The request's own values are found anywhere in the parts, and need not be
   unique: a number in the subject and the body is one number.
5. Every value the model's words gave is flagged `model_read`, and Sales
   confirms it field by field (`value_uncertain`). A target price is kept as
   the customer's statement only (`RequestedItem.stated_target_price`).

What remains a model's judgement is which field the words fill. That is the
residual risk (a reel length read as the quantity, the send date as the
required date), and it is why every value is flagged rather than trusted.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from dw_sales.domain.anchors import SourceAnchor, TextRange
from dw_sales.domain.catalog import Currency, CustomerItemCode, DocumentNo
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Span = str
_SPAN = Field(min_length=1, max_length=300)
# The most items one call may return: its answer has to fit the room the
# server leaves after the input (about 2,000 tokens, about 120 an item).
MAX_ITEMS_PER_CALL: Final = 15
# The most text lines one call is sent, so its items fit the answer's room.
MAX_LINES_PER_CALL: Final = 25


class ModelRfqItem(BaseModel):
    """One requested item as the model reads it: flat, every key required
    and nullable, so a server decoding against the schema writes each one.
    The line comes first, so the model reads it before it splits it."""

    model_config = _FROZEN

    part: str = Field(min_length=1, max_length=80)
    line_span: Span = _SPAN
    description_span: Span = _SPAN
    customer_item_code_span: Span | None = _SPAN
    quantity_span: Span | None = _SPAN
    uom_span: Span | None = _SPAN
    required_date_span: Span | None = _SPAN
    target_price_span: Span | None = _SPAN


class ModelRfqReading(BaseModel):
    """What one call returns."""

    model_config = _FROZEN

    rfq_no_span: Span | None = _SPAN
    quote_due_span: Span | None = _SPAN
    currency_span: Span | None = _SPAN
    items: tuple[ModelRfqItem, ...] = Field(max_length=MAX_ITEMS_PER_CALL)


# ------------------------------------------------------------ the parts --


@dataclass(frozen=True, slots=True)
class TextPart:
    """Text a model is shown, and where its characters are in the original.

    ``attachment_id`` None is the message's newest part. ``cells`` maps a
    sheet's text back to its cells, ``(start, end, "Sheet!B3")``, in offsets
    of the whole sheet's text; ``base`` is where this piece starts in it,
    for a part split to fit a call.
    """

    part_id: str
    text: str
    attachment_id: str | None
    sha256: str
    page: int | None = None
    cells: tuple[tuple[int, int, str], ...] = ()
    base: int = 0

    @property
    def lines(self) -> int:
        return self.text.count("\n") + 1

    def anchor(self, start: int, end: int) -> SourceAnchor | None:
        """Where ``text[start:end]`` is, for the review screen; None when it
        straddles two cells of a sheet, which no value of one field does."""
        quote = self.text[start:end][:500]
        whole = TextRange(start=self.base + start, end=self.base + end)
        if self.attachment_id is None:
            return SourceAnchor(
                attachment_id=None, attachment_sha256=self.sha256, chars=whole, quote=quote
            )
        if self.cells:
            cell = next(
                (ref for s, e, ref in self.cells if s <= whole.start and whole.end <= e), None
            )
            if cell is None:
                return None
            return SourceAnchor(
                attachment_id=self.attachment_id,
                attachment_sha256=self.sha256,
                cell_ref=cell,
                quote=quote,
            )
        return SourceAnchor(
            attachment_id=self.attachment_id,
            attachment_sha256=self.sha256,
            page=self.page,
            chars=whole,
            quote=quote,
        )

    def pieces(self, max_tokens: int, tokens: Callable[[str], int]) -> list[TextPart]:
        """The part as pieces of whole lines, each within ``max_tokens`` and
        `MAX_LINES_PER_CALL`, ids suffixed ``~2``, ``~3`` after the first. A
        single line over the bound stays one piece; the caller refuses it."""
        if tokens(self.text) <= max_tokens and self.lines <= MAX_LINES_PER_CALL:
            return [self]
        pieces: list[TextPart] = []
        start = 0
        lines = self.text.split("\n")
        current: list[str] = []
        for line in lines:
            candidate = [*current, line]
            joined = "\n".join(candidate)
            if current and (tokens(joined) > max_tokens or len(candidate) > MAX_LINES_PER_CALL):
                text = "\n".join(current)
                pieces.append(self._piece(len(pieces), text, start))
                start += len(text) + 1
                current = [line]
            else:
                current = candidate
        pieces.append(self._piece(len(pieces), "\n".join(current), start))
        return pieces

    def _piece(self, index: int, text: str, start: int) -> TextPart:
        part_id = self.part_id if index == 0 else f"{self.part_id}~{index + 1}"
        return replace(self, part_id=part_id, text=text, base=self.base + start)


def normalised(text: str) -> str:
    """What a part's text is, before it is sent or stored: NFKC."""
    return unicodedata.normalize("NFKC", text)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- parsers --
# Deterministic, from the span alone, NFKC-normalised. Each refuses what it
# does not read rather than guess.

_METRE_UNIT = r"(?:m|mtrs?|meters?|metres?|mét|met|メートル)"
_QUANTITY = re.compile(rf"(?P<number>[\d.,  ]+?)\s*(?P<unit>{_METRE_UNIT})?", re.IGNORECASE)
_UOM = re.compile(rf"(?:per\s+|/\s*)?{_METRE_UNIT}\.?", re.IGNORECASE)


def parse_number(text: str) -> Decimal | None:
    """A number as a customer writes it: ``1,200``, ``1.200``, ``1 200``
    (thousands), ``1200``, ``0.42``, ``0,42``. A separator followed by exactly
    three digits groups thousands; otherwise it is the decimal point."""
    value = text.strip()
    if not value:
        return None
    grouped = re.fullmatch(r"\d{1,3}(?:([.,  ])\d{3})+", value)
    if grouped is not None:
        separator = grouped.group(1)
        if len({c for c in value if not c.isdigit()}) != 1:
            return None
        return Decimal(value.replace(separator, ""))
    plain = re.fullmatch(r"(\d+)(?:[.,](\d+))?", value)
    if plain is None:
        return None
    whole, fraction = plain.group(1), plain.group(2)
    try:
        return Decimal(whole if fraction is None else f"{whole}.{fraction}")
    except InvalidOperation:
        return None


def parse_quantity(span: str) -> tuple[Decimal, bool] | None:
    """A quantity, and whether the span itself states metres."""
    match = _QUANTITY.fullmatch(normalised(span).strip())
    if match is None:
        return None
    number = parse_number(match.group("number"))
    if number is None or number <= 0:
        return None
    return number, match.group("unit") is not None


def parse_uom(span: str) -> Literal["m"] | None:
    """Metres, in the spellings customers use; anything else is no unit DW1
    quotes in (``reel``, ``pcs``, ``km`` are not read as metres)."""
    return "m" if _UOM.fullmatch(normalised(span).strip()) else None


def parse_price(span: str) -> Decimal | None:
    """A unit price as the customer states it, currency words around it
    ignored: one number, read by `parse_number`."""
    numbers = re.findall(r"\d[\d.,  ]*\d|\d", normalised(span))
    if len(numbers) != 1:
        return None
    value = parse_number(numbers[0])
    return value if value is not None and value > 0 else None


_CURRENCIES: Final[Mapping[str, Currency]] = {
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "US DOLLAR": "USD",
    "US DOLLARS": "USD",
    "ĐÔ LA MỸ": "USD",
    "VND": "VND",
    "VNĐ": "VND",
    "ĐỒNG": "VND",
    "Đ": "VND",
    "₫": "VND",
    "JPY": "JPY",
    "YEN": "JPY",
    "円": "JPY",
    "日本円": "JPY",
    "¥": "JPY",
}


def parse_currency(span: str) -> Currency | None:
    return _CURRENCIES.get(" ".join(normalised(span).upper().split()))


_MONTHS: Final = {
    name: number
    for number, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}
_ISO = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_DAY_FIRST = re.compile(r"(\d{1,2})[-/.](\d{1,2})(?:[-/.](\d{2}|\d{4}))?")
_JA = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")
_VI = re.compile(r"(?:ngày\s*)?(\d{1,2})\s*tháng\s*(\d{1,2})(?:\s*năm\s*(\d{4}))?")
_EN_DAY_MONTH = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?,?(?:\s+(\d{4}))?")
_EN_MONTH_DAY = re.compile(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?")
_DATE_PREFIX = re.compile(r"^(?:ngày|by|before|on|trước)\s+", re.IGNORECASE)


def parse_date(span: str, received_on: date) -> date | None:
    """A date as a customer writes it: ``2026-11-15``, ``15/11/2026``,
    ``15/11``, ``15 Nov 2026``, ``Nov 15``, ``2026年11月15日``, ``11月15日``,
    ``15 tháng 11``. Day first where the order is not stated (Vietnam's
    custom, and the customers' own forms); the other order when only it
    makes a date. Without a year, the one that puts it on or after the day
    the mail arrived less a month."""
    text = _DATE_PREFIX.sub("", " ".join(normalised(span).lower().split()))
    found: tuple[int | None, int, int] | None = None
    if match := _ISO.fullmatch(text):
        found = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    elif match := _JA.fullmatch(text):
        year = match.group(1)
        found = (int(year) if year else None, int(match.group(2)), int(match.group(3)))
    elif match := _VI.fullmatch(text):
        year = match.group(3)
        found = (int(year) if year else None, int(match.group(2)), int(match.group(1)))
    elif match := _DAY_FIRST.fullmatch(text):
        first, second = int(match.group(1)), int(match.group(2))
        year_text = match.group(3)
        century = 2000 if year_text is not None and len(year_text) == 2 else 0
        year_given = None if year_text is None else int(year_text) + century
        day, month = (first, second) if second <= 12 else (second, first)
        found = (year_given, month, day)
    elif match := _EN_DAY_MONTH.fullmatch(text):
        named = _MONTHS.get(match.group(2))
        if named is not None:
            year = match.group(3)
            found = (int(year) if year else None, named, int(match.group(1)))
    elif match := _EN_MONTH_DAY.fullmatch(text):
        named = _MONTHS.get(match.group(1))
        if named is not None:
            year = match.group(3)
            found = (int(year) if year else None, named, int(match.group(2)))
    if found is None:
        return None
    year, month, day = found
    try:
        if year is not None:
            return date(year, month, day)
        guess = date(received_on.year, month, day)
        if guess < received_on - timedelta(days=31):
            guess = date(received_on.year + 1, month, day)
        return guess
    except ValueError:
        return None


_DOCUMENT_NO: TypeAdapter[str] = TypeAdapter(DocumentNo)
_ITEM_CODE: TypeAdapter[str] = TypeAdapter(CustomerItemCode)


def parse_document_no(span: str) -> str | None:
    text = normalised(span).strip().upper()
    try:
        return _DOCUMENT_NO.validate_python(text)
    except ValidationError:
        return None


def parse_item_code(span: str) -> str | None:
    text = normalised(span).strip()
    try:
        return _ITEM_CODE.validate_python(text)
    except ValidationError:
        return None


# ---------------------------------------------------------- verification --


@dataclass(frozen=True, slots=True)
class Read[T]:
    """A value code parsed from a located span, and where it is."""

    value: T
    anchor: SourceAnchor
    attachment_id: str | None


@dataclass(frozen=True, slots=True)
class VerifiedItem:
    """One item code accepted: the line's place, and each value read."""

    line: Read[str]
    description: Read[str]
    customer_item_code: Read[str] | None
    quantity: Read[Decimal] | None
    uom: Read[str] | None
    needed_by: Read[date] | None
    stated_target_price: Read[Decimal] | None


@dataclass
class VerifiedRfq:
    """What code accepted of one or more answers, and what it refused, by
    reason (counts only: a refusal names no customer word)."""

    items: list[VerifiedItem] = field(default_factory=list)
    rfq_no: Read[str] | None = None
    quote_due: Read[date] | None = None
    currency: Read[Currency] | None = None
    refused: Counter[str] = field(default_factory=Counter)


_Located = tuple[TextPart, int, int]


class _Parts:
    def __init__(self, parts: Sequence[TextPart]) -> None:
        self.parts = {part.part_id: part for part in parts}
        self._texts = {part.part_id: FoldedText(part.text) for part in parts}

    def text(self, part_id: str) -> FoldedText:
        return self._texts[part_id]

    def anywhere(self, span: str) -> _Located | None:
        """The first whole-token occurrence of ``span`` in any part."""
        for part_id, part in self.parts.items():
            found = self._texts[part_id].occurrences(normalised(span), bounded=True)
            if found:
                return part, found[0][0], found[0][1]
        return None


def verify_rfq(
    parts: Sequence[TextPart],
    answer: ModelRfqReading,
    received_on: date,
    into: VerifiedRfq | None = None,
) -> VerifiedRfq:
    """What of ``answer`` code accepts (module docstring, checks 1-5), added
    to ``into`` (the verdict of an earlier call of the same request). Never
    raises on the model's answer."""
    verdict = into if into is not None else VerifiedRfq()
    held = _Parts(parts)
    seen_lines = {
        (i.line.anchor.attachment_id, i.line.anchor.quote, _start(i)) for i in verdict.items
    }
    for raw in answer.items:
        item = _item(held, raw, received_on, verdict.refused)
        if item is None:
            continue
        key = (item.line.anchor.attachment_id, item.line.anchor.quote, _start(item))
        if key in seen_lines:
            verdict.refused["line_repeated"] += 1
            continue
        seen_lines.add(key)
        verdict.items.append(item)
    if verdict.rfq_no is None and answer.rfq_no_span:
        verdict.rfq_no = _header(
            held, answer.rfq_no_span, parse_document_no, verdict.refused, "rfq_no"
        )
    if verdict.quote_due is None and answer.quote_due_span:
        verdict.quote_due = _header(
            held,
            answer.quote_due_span,
            lambda span: parse_date(span, received_on),
            verdict.refused,
            "quote_due",
        )
    if verdict.currency is None and answer.currency_span:
        verdict.currency = _header(
            held, answer.currency_span, parse_currency, verdict.refused, "currency"
        )
    return verdict


def _start(item: VerifiedItem) -> int:
    chars = item.line.anchor.chars
    return chars.start if chars is not None else -1


def _header[T](
    held: _Parts,
    span: str,
    parse: Callable[[str], T | None],
    refused: Counter[str],
    name: str,
) -> Read[T] | None:
    located = held.anywhere(span)
    if located is None:
        refused[f"{name}_not_found"] += 1
        return None
    part, start, end = located
    value = parse(part.text[start:end])
    anchor = part.anchor(start, end)
    if value is None or anchor is None:
        refused[f"{name}_unparsed"] += 1
        return None
    return Read(value, anchor, part.attachment_id)


def _item(
    held: _Parts, raw: ModelRfqItem, received_on: date, refused: Counter[str]
) -> VerifiedItem | None:
    part = held.parts.get(raw.part)
    if part is None:
        refused["part_unknown"] += 1
        return None
    text = held.text(raw.part)
    line = text.locate(normalised(raw.line_span), bounded=True)
    if isinstance(line, str):
        refused[f"line_{line.removeprefix('span_')}"] += 1
        return None
    line_anchor = part.anchor(*line) if part.cells == () else _line_anchor(part, *line)
    if line_anchor is None:
        refused["line_unanchored"] += 1
        return None

    def within(span: str | None, name: str) -> tuple[int, int] | None:
        if span is None:
            return None
        found = text.locate(normalised(span), bounded=True, within=line)
        if isinstance(found, str):
            refused[f"{name}_{found.removeprefix('span_')}"] += 1
            return None
        return found

    def read[T](
        place: tuple[int, int] | None, parse: Callable[[str], T | None], name: str
    ) -> Read[T] | None:
        if place is None:
            return None
        value = parse(part.text[place[0] : place[1]])
        anchor = part.anchor(*place)
        if value is None or anchor is None:
            refused[f"{name}_unparsed"] += 1
            return None
        return Read(value, anchor, part.attachment_id)

    description = read(within(raw.description_span, "description"), _description, "description")
    if description is None:
        return None
    quantity_place = within(raw.quantity_span, "quantity")
    quantity_read: Read[tuple[Decimal, bool]] | None = read(
        quantity_place, parse_quantity, "quantity"
    )
    uom = read(within(raw.uom_span, "uom"), parse_uom, "uom")
    quantity: Read[Decimal] | None = None
    if quantity_read is not None:
        number, states_metres = quantity_read.value
        if uom is None and states_metres:
            uom = Read("m", quantity_read.anchor, part.attachment_id)
        if uom is None:
            # A number with no unit, or one DW1 does not quote in, is no
            # quantity: `5 reels` is not 5 m. Sales asks (`rfq_incomplete`).
            refused["quantity_unit_unknown"] += 1
        else:
            quantity = Read(number, quantity_read.anchor, part.attachment_id)
    return VerifiedItem(
        line=Read(part.text[line[0] : line[1]], line_anchor, part.attachment_id),
        description=description,
        customer_item_code=read(
            within(raw.customer_item_code_span, "customer_item_code"),
            parse_item_code,
            "customer_item_code",
        ),
        quantity=quantity,
        uom=uom,
        needed_by=read(
            within(raw.required_date_span, "needed_by"),
            lambda span: parse_date(span, received_on),
            "needed_by",
        ),
        stated_target_price=read(
            within(raw.target_price_span, "target_price"), parse_price, "target_price"
        ),
    )


def _line_anchor(part: TextPart, start: int, end: int) -> SourceAnchor | None:
    """A sheet row's place: the cell its line starts in."""
    first = part.anchor(start, min(end, start + 1))
    if first is None:
        return None
    return first.model_copy(update={"quote": part.text[start:end][:500]})


def _description(span: str) -> str | None:
    text = " ".join(span.split())
    return text if 1 <= len(text) <= 500 else None
