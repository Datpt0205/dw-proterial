"""A model's reading of a PR written in a mail, and what code accepts of it.

dw_sales ADR 0005, applied by DW2 as DW1 applies it to a PO in a mail body
(`dw_sales.domain.po_body_reading`, read for the pattern, not imported): the
model copies span text only; code finds every span in what the model was
shown, parses every value from its span, and decides whether the mail is a
request at all.

**What the model is shown**: the message's newest part (subject first, quoted
history cut by structure, `dw_platform.domain.mail_parts.newest_part`), and
the text of the one document attached to it when there is one (`ShownFile`:
an Excel form's visible cells, a PDF's text, a scanned page read by OCR, as
the mail drop kept it, `domain.attachments`).

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
6. With a file shown, a value may be in the mail or the file, but every line
   comes from one of them, each found once there: a request is not stitched
   from two places. Where both hold every line (a mail that copies its form),
   the mail's text is read. A reading that takes any value only a scanned
   page holds is `scanned`: OCR misreads a digit without saying so, so a
   person compares it with the paper before DW2 sends it on.
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
    """The request, or why there is none (a code: it names no word of the
    mail). ``from_file``: its lines were read from the attached file;
    ``scanned``: a value it holds was read only on a scanned page."""

    request: PurchaseRequest | None
    not_read: str | None
    from_file: bool = False
    scanned: bool = False


@dataclass(frozen=True, slots=True)
class ShownFile:
    """The text of the file shown beside the mail, exactly as shown, and
    whether any of it was read by OCR."""

    text: str
    scanned: bool


def fold(text: str) -> str:
    """How spans and the mail are compared: NFKC, case-folded, runs of
    whitespace as one space. Length-changing, so offsets are not kept."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def occurrences(haystack: str, needle: str) -> list[int]:
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
    """What the model was shown: the mail's text first, then the file's.
    ``scanned`` records whether a value was taken only from a scanned text."""

    def __init__(self, text: str, file: ShownFile | None = None) -> None:
        shown = [(text, False)] + ([(file.text, file.scanned)] if file is not None else [])
        self.sources = [(fold(t), scanned) for t, scanned in shown]
        self.scanned = False

    def holds(self, span: str | None, *, within: str | None = None) -> bool:
        if span is None:
            return True
        needle = fold(span)
        if within is not None:
            return bool(occurrences(within, needle))
        found = [scanned for haystack, scanned in self.sources if occurrences(haystack, needle)]
        if found and all(found):
            self.scanned = True
        return bool(found)

    def require(self, span: str | None, reason: str, *, within: str | None = None) -> str:
        if span is None or not self.holds(span, within=within):
            raise _UnreadError(reason)
        return " ".join(span.split())

    def lines_source(self, folded_lines: list[str]) -> int:
        """The first text holding every line exactly once, a text with no
        OCR before one with (rule 6); refused when none does."""
        holding = [
            index
            for index, (haystack, _) in enumerate(self.sources)
            if all(len(occurrences(haystack, line)) == 1 for line in folded_lines)
        ]
        if not holding:
            raise _UnreadError("line_unreadable")
        index = min(holding, key=lambda i: self.sources[i][1])
        self.scanned = self.scanned or self.sources[index][1]
        return index


def read_pr_mail(
    text: str,
    answer: ModelPrMail,
    *,
    attachment: ShownFile | None = None,
    requester: str,
    received_on: date,
    default_currency: str,
) -> PrMailVerdict:
    """What code accepts of one answer (module docstring). ``text`` and
    ``attachment`` are what the model was shown; ``requester`` the verified
    sender's name."""
    mail = _Mail(text, attachment)
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
        lines, source = _lines(mail, answer, received_on)
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
    return PrMailVerdict(request, None, from_file=source > 0, scanned=mail.scanned)


def _lines(mail: _Mail, answer: ModelPrMail, received_on: date) -> tuple[tuple[PrLine, ...], int]:
    """The lines, and which text shown they were read from (0: the mail)."""
    if not answer.lines or len(answer.lines) > MAX_LINES:
        raise _UnreadError("no_lines")
    folded_lines = [fold(line.line_span) for line in answer.lines]
    if len(set(folded_lines)) != len(folded_lines):
        raise _UnreadError("line_unreadable")
    source = mail.lines_source(folded_lines)
    lines: list[PrLine] = []
    for number, (line, folded) in enumerate(zip(answer.lines, folded_lines, strict=True), start=1):
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
    return tuple(lines), source


class RequestDraft(BaseModel):
    """What a requester's own words ask for, as code read it from the model's
    spans: the lines, and the request-wide values the words name. No PR
    number, department or requester: those are not the words' to say (code
    numbers the request, the requester is the signed-in person)."""

    model_config = _FROZEN

    lines: tuple[PrLine, ...] = Field(min_length=1, max_length=MAX_MAIL_LINES)
    currency: str
    need_by: date | None = None
    budget_code: str | None = None


@dataclass(frozen=True, slots=True)
class PrWordsVerdict:
    draft: RequestDraft | None
    not_read: str | None


def read_pr_words(
    text: str, answer: ModelPrMail, *, received_on: date, default_currency: str
) -> PrWordsVerdict:
    """What code accepts of a reading of a requester's words ("Tôi cần mua
    …"): every span found as a whole token run, every line whole and parsed,
    as in a mail (`read_pr_mail`); a PR number or department the model gives
    is not read, the words do not decide them."""
    words = _Mail(text)
    try:
        for span in (answer.budget_code_span, answer.currency_span, answer.need_by_span):
            if not words.holds(span):
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
        draft = RequestDraft(
            lines=_lines(words, answer, received_on)[0],
            currency=currency,
            need_by=need_by,
            budget_code=(
                " ".join(answer.budget_code_span.split()) if answer.budget_code_span else None
            ),
        )
    except _UnreadError as unread:
        return PrWordsVerdict(None, unread.reason)
    except ValidationError:
        return PrWordsVerdict(None, "value_malformed")
    return PrWordsVerdict(draft, None)
