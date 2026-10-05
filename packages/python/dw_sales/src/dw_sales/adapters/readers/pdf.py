"""Text PDF POs, read from the text layer with pypdf, every value with its page and boxes.

pypdf's layout mode prints each table row as one text line with cells two or
more spaces apart, so a row is split on runs of spaces and its cells are taken
in the order the customer's `PdfLayout` lists the columns. A header value is the
text after its label and a colon.

**Anchors point at the page, not at extracted text** (ADR 0009). Each value's
anchor is its page plus a box on the rendered page, found from the position
pypdf reports for the text run that printed it, and the words it printed as
the quote. pypdf gives a run's start and font size but no glyph widths, so a
box's width is estimated from the run's length; it marks where to look on the
original, it is not a measurement anyone decides on.

Scans are not read: a PDF with no text layer comes back `Unreadable`, and the
message is routed to Sales. A numbered row-shaped line outside the table (a
wrapped description, a page without the table header) is counted as printed
and not read, which `line_total_mismatch` reports. A refusal names fields and
pages, never a value from the file (spec decision 8).
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import get_args

from pydantic import ValidationError
from pypdf import PdfReader

from dw_sales.domain.anchors import PageBox, SourceAnchor
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import (
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoHeaderField,
    PoLine,
    PoLineAnchors,
    PoLineField,
    PrintedTotal,
    Unreadable,
)

PARSER_VERSION = "pdf_po_reader@1.1.0"
_CELL_GAP = re.compile(r"\s{2,}")
# Average glyph advance as a share of the font size: the width estimate.
_ADVANCE = 0.55


@dataclass(frozen=True)
class PdfLayout:
    """How one customer's PDF PO prints its header, its table and its numbers.

    ``columns``: every column title in print order, each with the line field it
    holds. ``total_label``: the label of the printed total, or None.
    """

    header_labels: Mapping[PoHeaderField, str]
    columns: tuple[tuple[str, PoLineField | None], ...]
    thousands_separator: str
    decimal_separator: str
    # A `datetime.strptime` format, such as ``%d/%m/%Y``.
    date_format: str
    total_label: str | None = None

    def __post_init__(self) -> None:
        if set(self.header_labels) != set(get_args(PoHeaderField)):
            raise ValueError(f"a PDF layout labels every header field {get_args(PoHeaderField)}")
        fields = [f for _, f in self.columns if f is not None]
        if sorted(fields) != sorted(get_args(PoLineField)):
            raise ValueError(
                f"a PDF layout has one column for each line field {get_args(PoLineField)}"
            )
        if self.columns[0][1] != "line_no":
            raise ValueError("the first column holds the line number: it is how a row is told")
        separators = {self.thousands_separator, self.decimal_separator}
        if len(separators) != 2 or any(len(s) != 1 or s.isdigit() for s in separators):
            raise ValueError("thousands and decimal separators are two different characters")


@dataclass(frozen=True)
class _Run:
    """One text run as pypdf drew it: its words, baseline origin and font size."""

    text: str
    x: float
    y: float
    size: float


@dataclass
class _Page:
    number: int
    width: float
    height: float
    lines: list[str]
    # Runs grouped by baseline, top of the page first, each row left to right.
    rows: list[list[_Run]] = field(default_factory=list)
    used: set[int] = field(default_factory=set)

    def box(self, run: _Run) -> PageBox:
        """Where ``run`` sits on the page, in 0-1 of the page from its top-left."""
        x = _fraction(run.x / self.width)
        y = _fraction(1 - (run.y + 0.9 * run.size) / self.height)
        w = len(run.text) * run.size * _ADVANCE / self.width
        h = 1.15 * run.size / self.height
        return PageBox(x=x, y=y, w=_extent(w, x), h=_extent(h, y))

    def find_row(self, cells: Sequence[str]) -> list[_Run] | None:
        """The drawn row whose runs read ``cells``, each row matched once."""
        wanted = [" ".join(cell.split()) for cell in cells]
        for index, row in enumerate(self.rows):
            if index not in self.used and [" ".join(r.text.split()) for r in row] == wanted:
                self.used.add(index)
                return row
        return None


def _fraction(value: float) -> float:
    """A position on the page, kept inside it with room for a box."""
    return min(max(value, 0.0), 0.999)


def _extent(size: float, start: float) -> float:
    """A box's width or height, at least visible and ending on the page."""
    return max(min(size, 1.0 - start - 1e-9), 1e-4)


class PdfPoReader:
    """Reads a text PDF PO with the layout of the customer who sent it."""

    def __init__(self, layouts: Mapping[str, PdfLayout]) -> None:
        self._layouts = dict(layouts)

    def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        layout = self._layouts.get(customer_code)
        if layout is None:
            return Unreadable(reason=f"no PDF PO layout for customer {customer_code}")
        try:
            pages = _pages(document.data, caps)
            return _Pdf(pages, layout, document.attachment).read()
        except _RefusedError as refused:
            return Unreadable(reason=refused.reason, anchor=refused.anchor)


def _pages(data: bytes, caps: IntakeCaps) -> list[_Page]:
    if len(data) > caps.max_attachment_bytes:
        raise _RefusedError(f"the file is over the {caps.max_attachment_bytes} bytes read here")
    try:
        pdf = PdfReader(io.BytesIO(data))
        if pdf.is_encrypted:
            raise _RefusedError("the PDF is password-protected")
        if len(pdf.pages) > caps.max_pages:
            raise _RefusedError(f"the PDF has more than the {caps.max_pages} pages read here")
        pages: list[_Page] = []
        for number, page in enumerate(pdf.pages, start=1):
            box = page.mediabox
            left, bottom = float(box.left), float(box.bottom)
            runs: list[_Run] = []

            def visit(
                text: str,
                cm: Sequence[float],
                tm: Sequence[float],
                _font: object,
                size: float,
                runs: list[_Run] = runs,
                left: float = left,
                bottom: float = bottom,
            ) -> None:
                if text.strip():
                    x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4] - left
                    y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5] - bottom
                    runs.append(_Run(text.strip(), x, y, float(size) or 1.0))

            page.extract_text(visitor_text=visit)
            layout_text = page.extract_text(extraction_mode="layout")
            current = _Page(number, float(box.width), float(box.height), layout_text.split("\n"))
            current.rows = _rows(runs)
            pages.append(current)
    except _RefusedError:
        raise
    except Exception as exc:  # any parser failure on a sender's file is "unreadable"
        raise _RefusedError("not a PDF pypdf can read") from exc
    if not any(line.strip() for page in pages for line in page.lines):
        raise _RefusedError("the PDF has no text layer: a scan or an image")
    return pages


def _rows(runs: list[_Run]) -> list[list[_Run]]:
    by_baseline: dict[float, list[_Run]] = {}
    for run in runs:
        by_baseline.setdefault(round(run.y, 1), []).append(run)
    return [sorted(by_baseline[y], key=lambda r: r.x) for y in sorted(by_baseline, reverse=True)]


class _RefusedError(Exception):
    def __init__(self, reason: str, anchor: SourceAnchor | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.anchor = anchor


class _Pdf:
    def __init__(self, pages: list[_Page], layout: PdfLayout, attachment: Attachment) -> None:
        self._pages = pages
        self._layout = layout
        self._attachment = attachment
        number = re.escape(layout.thousands_separator)
        decimals = re.escape(layout.decimal_separator)
        self._number = re.compile(rf"(?:\d{{1,3}}(?:{number}\d{{3}})+|\d+)(?:{decimals}\d+)?")
        self._titles = [_key(title) for title, _ in layout.columns]
        self._header_values: Mapping[PoHeaderField, Callable[[str], object]] = {
            "po_no": _one_line,
            "revision": _whole_number,
            "po_date": self._day,
            "currency": str.upper,
        }
        self._line_values: Mapping[PoLineField, Callable[[str], object]] = {
            "line_no": _whole_number,
            "customer_item_code": _one_line,
            "description": _one_line,
            "quantity": self._decimal,
            "uom": _one_line,
            "unit_price": self._decimal,
            "amount": self._decimal,
            "requested_date": self._day,
        }

    def read(self) -> PoDocument:
        header = self._header()
        lines: list[PoLine] = []
        regions: list[str] = []
        tabled: set[tuple[int, int]] = set()
        for page in self._pages:
            for index, text in enumerate(page.lines):
                if [_key(cell) for cell in _cells(text)] == self._titles:
                    rows = self._rows(page, index + 1, tabled)
                    if rows and f"page {page.number}" not in regions:
                        regions.append(f"page {page.number}")
                    lines.extend(rows)
        if not lines:
            raise _RefusedError("no page has the PO table")
        # A row-shaped line outside every table is printed and not read.
        outside = sum(
            1
            for page in self._pages
            for index, text in enumerate(page.lines)
            if (page.number, index + 1) not in tabled and self._is_row(text)
        )
        try:
            return PoDocument(
                attachment_id=self._attachment.attachment_id,
                attachment_sha256=self._attachment.sha256,
                parser_version=PARSER_VERSION,
                header=header,
                lines=tuple(lines),
                rows_printed=len(lines) + outside,
                regions=tuple(regions),
                total=self._total(),
            )
        except ValidationError as exc:
            raise _RefusedError(f"the lines do not form one PO: {_first_error(exc)}") from exc

    def _labelled(self, label: str) -> list[tuple[SourceAnchor, str]]:
        """Every ``label: value`` line, with the anchor of what printed it."""
        found: list[tuple[SourceAnchor, str]] = []
        for page in self._pages:
            for text in page.lines:
                value = _labelled(text, label)
                if value is None:
                    continue
                row = page.find_row([text.strip()])
                found.append((self._anchor(page, row[0] if row else None, value), value))
        return found

    def _header(self) -> PoHeader:
        values: dict[str, object] = {}
        anchors: dict[str, SourceAnchor] = {}
        for name, label in self._layout.header_labels.items():
            found = self._labelled(label)
            if not found:
                raise _RefusedError(f"no line holds the {name.replace('_', ' ')}")
            anchor, value = found[0]
            if len({v for _, v in found}) > 1:
                raise _RefusedError(f"the {name.replace('_', ' ')} has two values", found[1][0])
            try:
                values[name] = self._header_values[name](value)
            except ValueError as exc:
                raise _RefusedError(f"{name.replace('_', ' ')} {exc}", anchor) from exc
            anchors[name] = anchor
        try:
            return PoHeader.model_validate({**values, "anchors": PoHeaderAnchors(**anchors)})
        except ValidationError as exc:
            failed = str(exc.errors()[0]["loc"][0])
            raise _RefusedError(f"header: {_first_error(exc)}", anchors.get(failed)) from exc

    def _total(self) -> PrintedTotal | None:
        if self._layout.total_label is None:
            return None
        found = self._labelled(self._layout.total_label)
        if not found:
            return None
        anchor, value = found[-1]
        # The amount, then the currency it is printed in.
        amount = value.split()[0] if value.split() else value
        try:
            return PrintedTotal(amount=self._decimal(amount), anchor=anchor)
        except ValueError as exc:
            raise _RefusedError(f"the total {exc}", anchor) from exc

    def _rows(self, page: _Page, title_line: int, tabled: set[tuple[int, int]]) -> list[PoLine]:
        """The rows under the column titles on ``title_line``, to the first other line."""
        lines: list[PoLine] = []
        for line_number in range(title_line + 1, len(page.lines) + 1):
            text = page.lines[line_number - 1]
            if not self._is_row(text):
                break
            tabled.add((page.number, line_number))
            lines.append(self._row(page, text))
        return lines

    def _row(self, page: _Page, text: str) -> PoLine:
        cells = _cells(text)
        drawn = page.find_row(cells)
        values: dict[str, object] = {}
        anchors: dict[str, SourceAnchor] = {}
        for index, ((_, name), cell) in enumerate(zip(self._layout.columns, cells, strict=True)):
            anchor = self._anchor(page, drawn[index] if drawn else None, cell)
            if name is None:
                continue
            try:
                values[name] = self._line_values[name](cell)
            except ValueError as exc:
                raise _RefusedError(f"{name.replace('_', ' ')} {exc}", anchor) from exc
            anchors[name] = anchor
        try:
            return PoLine.model_validate({**values, "anchors": PoLineAnchors(**anchors)})
        except ValidationError as exc:
            failed = str(exc.errors()[0]["loc"][0])
            raise _RefusedError(f"row: {_first_error(exc)}", anchors.get(failed)) from exc

    def _is_row(self, text: str) -> bool:
        cells = _cells(text)
        return len(cells) == len(self._layout.columns) and cells[0].isdigit()

    def _anchor(self, page: _Page, run: _Run | None, quote: str) -> SourceAnchor:
        """The page and box of the run that printed ``quote``; the quote alone
        when no run matched (the review screen then searches the page)."""
        return SourceAnchor(
            attachment_id=self._attachment.attachment_id,
            attachment_sha256=self._attachment.sha256,
            page=page.number if run is not None else None,
            boxes=(page.box(run),) if run is not None else (),
            quote=" ".join(quote.split())[:500] or None,
        )

    def _decimal(self, text: str) -> Decimal:
        if not self._number.fullmatch(text):
            raise ValueError("is not a number")
        plain = text.replace(self._layout.thousands_separator, "")
        return Decimal(plain.replace(self._layout.decimal_separator, "."))

    def _day(self, text: str) -> date:
        try:
            return datetime.strptime(text, self._layout.date_format).date()
        except ValueError as exc:
            raise ValueError("is not a date in the layout's format") from exc


def _cells(text: str) -> Sequence[str]:
    stripped = text.strip()
    return _CELL_GAP.split(stripped) if stripped else []


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _labelled(text: str, label: str) -> str | None:
    """The value on a ``Label: value`` line, or None when the line is not one."""
    head, colon, value = text.strip().partition(":")
    if not colon or _key(head) != _key(label):
        return None
    return value.strip()


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _whole_number(text: str) -> int:
    if not text.isdigit():
        raise ValueError("is not a whole number")
    return int(text)


def _first_error(exc: ValidationError) -> str:
    error = exc.errors(include_input=False)[0]
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}"
