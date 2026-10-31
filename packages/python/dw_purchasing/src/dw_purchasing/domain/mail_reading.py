"""A model's reading of a PR written in a mail, and what code accepts of it.

dw_sales ADR 0005, applied by DW2 as DW1 applies it to a PO in a mail body
(`dw_sales.domain.po_body_reading`, read for the pattern, not imported): the
model copies span text only; code finds every span in what the model was
shown, parses every value from its span, and decides whether the mail is a
request at all.

**What the model is shown**: the message's newest part (subject first, quoted
history cut by structure, `dw_platform.domain.mail_parts.newest_part`).

**What the model gives** (`ModelPrMail`): spans only. The PR number, the
department, the budget code, the currency and a need-by date for the whole
request as written; for each line, the line as written and inside it the
item code, the description, the quantity, the unit and the line's need-by
date. Never a parsed value, a requester, a supplier or a decision.

**What code checks** (`read_pr_mail`):

1. A PR number found as a whole token run, of a code's shape; else the mail
   is no request DW2 reads (``no_pr_number``).
2. A department found as a whole token run (``no_department``).
3. Every line found as a whole token run, and inside it its description,
   quantity and unit, each found and parsed; an item code and a need-by date
   when the model gives one must be found too. One line that fails refuses
   the whole request (``line_unreadable``): reading part of a request would
   leave out lines nobody knows are missing. The same line twice refuses it.
4. Every other span the model gives must be found, or the request is refused
   (``span_not_found``): a value the mail does not hold is an invented one.
5. The requester is the verified sender (the caller's), never the model's.
   A currency nobody wrote is the tenant's default, a rule.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_purchasing.domain.requests import (
    MAX_LINES,
    PrLine,
    PurchaseRequest,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Span = Annotated[str, Field(min_length=1, max_length=300)]
# The most lines one mail is read with: the answer has to fit the room the
# server leaves after the input. A longer request is a form's job.
MAX_MAIL_LINES: Final = 20


class ModelPrLine(BaseModel):
    """One line as the model reads it: every key required and nullable, so a
    server decoding against the schema writes each one."""

    model_config = _FROZEN

    line_span: Span
    item_code_span: Span | None
    description_span: Span | None
    quantity_span: Span | None
    unit_span: Span | None
    need_by_span: Span | None


class ModelPrMail(BaseModel):
    """What one call returns. No PR number: the mail is no request."""

    model_config = _FROZEN

    pr_no_span: Span | None
    department_span: Span | None
    budget_code_span: Span | None
    currency_span: Span | None
    need_by_span: Span | None
    lines: tuple[ModelPrLine, ...] = Field(max_length=MAX_MAIL_LINES)


@dataclass(frozen=True, slots=True)
class PrMailVerdict:
    """The request, or why there is none (a code: it names no word of the mail)."""

    request: PurchaseRequest | None
    not_read: str | None


def fold(text: str) -> str:
    """How spans and the mail are compared: NFKC, case-folded, runs of
    whitespace as one space. Length-changing, so offsets are not kept."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _occurrences(haystack: str, needle: str) -> list[int]:
    """Where ``needle`` starts as a whole token run: neither end inside a
    word, so ``24`` of ``AWG24`` and ``PR-1`` of ``PR-12`` are not found."""
    found: list[int] = []
    if not needle:
        return found
    start = haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        before = haystack[start - 1] if start > 0 else " "
        after = haystack[end] if end < len(haystack) else " "
        if not before.isalnum() and not after.isalnum():
            found.append(start)
        start = haystack.find(needle, start + 1)
    return found


_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,47}")
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
_GROUPED = re.compile(r"\d{1,3}(?:([.,])\d{3})+")
_DAY_FIRST = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{4}|\d{2}))?(?!\d)")
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_CURRENCIES: Final = {
    "vnd": "VND",
    "đ": "VND",
    "đồng": "VND",
    "vnđ": "VND",
    "usd": "USD",
    "$": "USD",
    "us$": "USD",
    "jpy": "JPY",
    "円": "JPY",
    "yen": "JPY",
    "¥": "JPY",
}


def parse_quantity(span: str) -> Decimal | None:
    """One number as written: ``1.200`` and ``1,200`` are twelve hundred (a
    group of three after one separator kind), ``2,5`` and ``2.5`` two and a
    half. Two numbers, or none, is no quantity."""
    numbers = _NUMBER.findall(unicodedata.normalize("NFKC", span))
    if len(numbers) != 1:
        return None
    text = numbers[0]
    if (grouped := _GROUPED.fullmatch(text)) is not None:
        text = text.replace(grouped.group(1), "")
    elif re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        text = text.replace(",", ".")
    else:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def parse_date(span: str, *, received_on: date) -> date | None:
    """A date as written: ``2026-11-20``, or day first (``20/11/2026``,
    ``20/11``). A year left out is the first such date on or after the day
    the mail arrived."""
    text = unicodedata.normalize("NFKC", span)
    try:
        if (iso := _ISO.search(text)) is not None:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        if (dmy := _DAY_FIRST.search(text)) is None:
            return None
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), dmy.group(3)
        if year is not None:
            return date(int(year) + (2000 if len(year) == 2 else 0), month, day)
        guess = date(received_on.year, month, day)
        return guess if guess >= received_on else date(received_on.year + 1, month, day)
    except ValueError:
        return None


def parse_currency(span: str) -> str | None:
    return _CURRENCIES.get(fold(span).strip(" .:"))


class _UnreadError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Mail:
    def __init__(self, text: str) -> None:
        self.folded = fold(text)

    def holds(self, span: str | None, *, within: str | None = None) -> bool:
        haystack = within if within is not None else self.folded
        return span is None or bool(_occurrences(haystack, fold(span)))

    def require(self, span: str | None, reason: str, *, within: str | None = None) -> str:
        if span is None or not self.holds(span, within=within):
            raise _UnreadError(reason)
        return " ".join(span.split())


def read_pr_mail(
    text: str,
    answer: ModelPrMail,
    *,
    requester: str,
    received_on: date,
    default_currency: str,
) -> PrMailVerdict:
    """What code accepts of one answer (module docstring). ``text`` is what
    the model was shown; ``requester`` the verified sender's name."""
    mail = _Mail(text)
    try:
        if answer.pr_no_span is None:
            raise _UnreadError("no_pr_number")
        pr_no = mail.require(answer.pr_no_span, "no_pr_number")
        if not _CODE.fullmatch(pr_no):
            raise _UnreadError("no_pr_number")
        department = mail.require(answer.department_span, "no_department")
        for span in (answer.budget_code_span, answer.currency_span, answer.need_by_span):
            if not mail.holds(span):
                raise _UnreadError("span_not_found")
        currency = (
            parse_currency(answer.currency_span) if answer.currency_span else default_currency
        )
        if currency is None:
            raise _UnreadError("currency_unreadable")
        need_by = None
        if answer.need_by_span is not None:
            need_by = parse_date(answer.need_by_span, received_on=received_on)
            if need_by is None:
                raise _UnreadError("need_by_unreadable")
        lines = _lines(mail, answer, received_on)
        request = PurchaseRequest(
            pr_no=pr_no,
            department=department[:80],
            requester=requester[:120],
            budget_code=(
                " ".join(answer.budget_code_span.split()) if answer.budget_code_span else None
            ),
            currency=currency,
            need_by=need_by,
            lines=lines,
        )
    except _UnreadError as unread:
        return PrMailVerdict(None, unread.reason)
    except ValidationError:
        # A value found in the mail that is no value of its kind (a budget
        # code with a space, a line past the limit).
        return PrMailVerdict(None, "value_malformed")
    return PrMailVerdict(request, None)


def _lines(mail: _Mail, answer: ModelPrMail, received_on: date) -> tuple[PrLine, ...]:
    if not answer.lines or len(answer.lines) > MAX_LINES:
        raise _UnreadError("no_lines")
    seen: set[str] = set()
    lines: list[PrLine] = []
    for number, line in enumerate(answer.lines, start=1):
        folded = fold(line.line_span)
        if folded in seen or len(_occurrences(mail.folded, folded)) != 1:
            raise _UnreadError("line_unreadable")
        seen.add(folded)
        description = mail.require(line.description_span, "line_unreadable", within=folded)
        quantity_span = mail.require(line.quantity_span, "line_unreadable", within=folded)
        unit = mail.require(line.unit_span, "line_unreadable", within=folded).rstrip(".")
        if not mail.holds(line.item_code_span, within=folded) or not mail.holds(
            line.need_by_span, within=folded
        ):
            raise _UnreadError("line_unreadable")
        quantity = parse_quantity(quantity_span)
        need_by = (
            parse_date(line.need_by_span, received_on=received_on) if line.need_by_span else None
        )
        if quantity is None or (line.need_by_span is not None and need_by is None):
            raise _UnreadError("line_unreadable")
        item_code = " ".join(line.item_code_span.split()) if line.item_code_span else None
        lines.append(
            PrLine(
                line_no=number,
                item_code=item_code,
                description=description[:300],
                quantity=quantity,
                unit=unit,
                need_by=need_by,
            )
        )
    return tuple(lines)
