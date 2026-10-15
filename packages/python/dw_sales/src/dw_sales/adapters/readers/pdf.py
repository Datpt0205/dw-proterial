"""Text PDF POs, read from the text layer with pypdf, every value with its page and boxes.

pypdf's layout mode prints each table row as one text line with cells two or
more spaces apart, so a row is split on runs of spaces and its cells are taken
in the order the customer's `PdfLayout` lists the columns. A header value is the
text after its label and a colon.

**Anchors point at the page, not at extracted text** (ADR 0009-parser-page-output-with-coordinates).
Each value's anchor is its page plus a box on the rendered page, found from the position
pypdf reports for the text run that printed it, and the words it printed as
the quote. pypdf gives a run's start and font size but no glyph widths, so a
box's width is estimated from the run's length; it marks where to look on the
original, it is not a measurement anyone decides on.

**A value drawn in a TCVN3 or VNI font is read and marked** by the font pypdf
reports for its run (`legacy_fonts`), or, when no run matched it, by any such
font on its page: its letters are not what the customer sees, so the checks
raise `legacy_encoding` and nothing is matched on it (ticket 20).

**A line split over several delivery dates** (ticket 21) is read from a
"date: quantity" list in its date cell (``16/11/2026: 3.050; 30/11/2026:
3.050``), each schedule anchored where the cell is printed. A PDF printing
schedules as rows under the line is a layout no customer has sent yet: such a
row is no table row, so it ends the table, and the printed total does not add
up to what was read.

**A row printed with no date** ("date to follow", ticket 34) prints a dash
where the date goes, read as no date at the dash, or is a row one cell short.
A short row is read with the gap at the date's column only when every number
in it then reads as one and the cell after the gap is no date, so a short row
is never read shifted and a printed date is never taken for a blank one: the
line has no requested date, anchored at the row's line number, and the checks
raise `requested_date_missing`. Any other short row is not a table row, as
before.

**A scanned page is read by OCR** where the reader is given an engine
(ticket 27, `readers.ocr`; the reader sandbox gives it Tesseract): a page with
no text layer is rasterised and its words, with their boxes, become the
page's lines and rows, read by the same layout, its labels and column titles
matched without diacritics (OCR loses those first). Every value of a document a
page of which was OCRed is flagged `ocr` (`value_uncertain` until Sales
confirms it, whatever the engine's confidence), and the document says which
engine read it (`Derivation`). A PDF whose pages have no text and no words
the engine could read, or read where there is no engine, comes back
`Unreadable` and the message is routed to Sales; an engine that fails is the
same, never a failed run.

A numbered row-shaped line outside the table (a wrapped description, a page
without the table header) is counted as printed and not read, which
`line_total_mismatch` reports. A refusal names fields and pages, never a value
from the file (spec decision 8).
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

from dw_sales.adapters.readers.ocr import OcrError, OcrPage, PageOcrPort
from dw_sales.adapters.readers.schedules import in_date_order, listed_schedules, no_date
from dw_sales.domain.anchors import PageBox, SourceAnchor
from dw_sales.domain.layouts import LabelCell, flagged_everywhere
from dw_sales.domain.legacy_fonts import LegacyEncoding, legacy_encoding
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps
from dw_sales.domain.orders import (
    DeliverySchedule,
    Derivation,
    LegacyText,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoHeaderField,
    PoLine,
    PoLineAnchors,
    PoLineField,
    PrintedTotal,
    RegionFlag,
    Unreadable,
)
from dw_sales.domain.rfq_reading import parse_currency

PARSER_VERSION = "pdf_po_reader@1.6.0"
# A form need not print its revision: its POs then read as revision 0 (ticket 30).
REQUIRED_HEADER = frozenset({"po_no", "po_date", "currency"})
_CELL_GAP = re.compile(r"\s{2,}")
_WORD = re.compile(r"\S+")
# The tag a PDF puts before an embedded subset's font name: ``ABCDEF+``.
_SUBSET_TAG = re.compile(r"^[A-Z]{6}\+")
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
        if not REQUIRED_HEADER <= set(self.header_labels) <= set(get_args(PoHeaderField)):
            raise ValueError(f"a PDF layout labels the header fields {sorted(REQUIRED_HEADER)}")
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
    """One text run as pypdf drew it: its words, baseline origin and font
    size, and the legacy encoding its font types Vietnamese in, if any."""

    text: str
    x: float
    y: float
    size: float
    legacy: LegacyEncoding | None = None


@dataclass
class _Page:
    number: int
    width: float
    height: float
    lines: list[str]
    # Runs grouped by baseline, top of the page first, each row left to right.
    rows: list[list[_Run]] = field(default_factory=list)
    used: set[int] = field(default_factory=set)
    # Read by OCR: its labels and column titles are matched without their
    # diacritics (`_key`), the marks OCR loses first.
    scanned: bool = False

    @property
    def legacy(self) -> LegacyEncoding | None:
        """A legacy encoding some run on the page is drawn in."""
        return next((run.legacy for row in self.rows for run in row if run.legacy), None)

    def legacy_text(self, name: str, run: _Run | None) -> tuple[LegacyText, ...]:
        """``name``'s value, when the run that drew it is in a TCVN3 or VNI
        font, or no run matched it on a page that has one."""
        encoding = run.legacy if run is not None else self.legacy
        return () if encoding is None else (LegacyText(field=name, encoding=encoding),)

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
    """Reads a PDF PO with the layout of the customer who sent it: its text
    layer, and a scanned page by OCR where ``ocr`` is given (module
    docstring)."""

    def __init__(self, layouts: Mapping[str, PdfLayout], *, ocr: PageOcrPort | None = None) -> None:
        self._layouts = dict(layouts)
        self._ocr = ocr

    def read(
        self, document: AttachmentContent, customer_code: str, caps: IntakeCaps
    ) -> PoDocument | Unreadable:
        layout = self._layouts.get(customer_code)
        if layout is None:
            return Unreadable(reason=f"no PDF PO layout for customer {customer_code}")
        try:
            pages, ocr = _pages(document.data, caps, self._ocr)
            return _ocr_stamped(_Pdf(pages, layout, document.attachment).read(), ocr)
        except _RefusedError as refused:
            return Unreadable(reason=refused.reason, anchor=refused.anchor)

    def has_layout(self, customer_code: str) -> bool:
        """Whether this reader holds the customer's layout."""
        return customer_code in self._layouts

    def read_with(
        self,
        document: AttachmentContent,
        layout: PdfLayout,
        caps: IntakeCaps,
        *,
        layout_ref: str,
    ) -> PoDocument | Unreadable:
        """``document`` read with a tenant's own approved layout (ticket 30),
        the PO stamped with which one."""
        try:
            pages, ocr = _pages(document.data, caps, self._ocr)
            read = _Pdf(pages, layout, document.attachment).read()
        except _RefusedError as refused:
            return Unreadable(reason=refused.reason, anchor=refused.anchor)
        return _ocr_stamped(read, ocr).model_copy(update={"layout_ref": layout_ref})

    def label_cells(self, document: AttachmentContent, caps: IntakeCaps) -> list[LabelCell]:
        """The first page's text a label may be (ticket 30): each line split
        into its cells as the reader splits a table row, and a ``Label: value``
        line as its label alone."""
        try:
            pages, _ = _pages(document.data, caps, self._ocr)
        except _RefusedError:
            return []
        page = pages[0]
        cells: list[LabelCell] = []
        for row, text in enumerate(page.lines, start=1):
            head, colon, _ = text.strip().partition(":")
            single = colon and len(_cells(head)) == 1 and len(head) <= _LABEL_LENGTH
            for column, cell in enumerate([head.strip()] if single else _cells(text), start=1):
                if not cell or len(cell) > _LABEL_LENGTH:
                    continue
                cells.append(
                    LabelCell(
                        ref=f"p{page.number}:{row}:{column}",
                        sheet=f"page {page.number}",
                        row=row,
                        column=column,
                        text=" ".join(cell.split()),
                        labelled=bool(single),
                    )
                )
        return cells

    def form_rows(self, document: AttachmentContent, caps: IntakeCaps) -> list[list[str]]:
        """The first page's lines as a person reads them: a ``Label: value``
        line as its label and its value, any other line as its cells."""
        try:
            pages, _ = _pages(document.data, caps, self._ocr)
        except _RefusedError:
            return []
        rows: list[list[str]] = []
        for text in pages[0].lines:
            head, colon, value = text.strip().partition(":")
            if colon and len(_cells(head)) == 1 and len(head) <= _LABEL_LENGTH:
                rows.append([head.strip(), value.strip()][: 2 if value.strip() else 1])
            elif cells := _cells(text):
                rows.append([" ".join(cell.split())[:200] for cell in cells])
        return rows


_LABEL_LENGTH = 80


def _ocr_stamped(document: PoDocument, ocr: str | None) -> PoDocument:
    """``document``, every value flagged `ocr` and the engine named, when a
    page of it was read by ``ocr``; as it was otherwise."""
    if ocr is None:
        return document
    flagged = flagged_everywhere(document, RegionFlag.OCR)
    return flagged.model_copy(update={"derivation": Derivation(method="ocr", tool=ocr)})


def _scanned(number: int, page: OcrPage) -> _Page:
    """A page read by OCR, in the shape a text layer is read in: each line
    its cells two spaces or more apart, each row its cells as runs."""
    lines = ["    ".join(cell.text for cell in line) for line in page.lines]
    rows = [
        [
            # A run's origin is its baseline, from the page's bottom (`box`).
            _Run(cell.text, cell.left, page.height - cell.top - 0.9 * cell.height, cell.height)
            for cell in line
        ]
        for line in page.lines
    ]
    return _Page(number, page.width, page.height, lines, rows, scanned=True)


def _pages(
    data: bytes, caps: IntakeCaps, ocr: PageOcrPort | None = None
) -> tuple[list[_Page], str | None]:
    """The pages, and the OCR engine's name when a page was read by it."""
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
                font: object,
                size: float,
                runs: list[_Run] = runs,
                left: float = left,
                bottom: float = bottom,
            ) -> None:
                if text.strip():
                    x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4] - left
                    y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5] - bottom
                    encoding = legacy_encoding(_base_font(font))
                    runs.append(_Run(text.strip(), x, y, float(size) or 1.0, encoding))

            page.extract_text(visitor_text=visit)
            layout_text = page.extract_text(extraction_mode="layout")
            current = _Page(number, float(box.width), float(box.height), layout_text.split("\n"))
            current.rows = _rows(runs)
            pages.append(current)
    except _RefusedError:
        raise
    except Exception as exc:  # any parser failure on a sender's file is "unreadable"
        raise _RefusedError("not a PDF pypdf can read") from exc
    if ocr is not None and not all(_has_text(page) for page in pages):
        return _with_ocr(data, pages, ocr)
    if not any(_has_text(page) for page in pages):
        raise _RefusedError("the PDF has no text layer: a scan or an image")
    return pages, None


def _has_text(page: _Page) -> bool:
    return any(line.strip() for line in page.lines)


def _with_ocr(data: bytes, pages: list[_Page], ocr: PageOcrPort) -> tuple[list[_Page], str | None]:
    """Each page with no text layer read by ``ocr``. An engine that cannot
    run reads nothing (the PDF is then as unreadable as without one); one that
    reads no word on a page leaves it empty."""
    try:
        tool = ocr.tool()
        read = [
            page
            if _has_text(page)
            else _scanned(page.number, ocr.page(data, page.number, (page.width, page.height)))
            for page in pages
        ]
    except OcrError:
        if not any(_has_text(page) for page in pages):
            raise _RefusedError("the PDF has no text layer: a scan or an image") from None
        return pages, None
    if not any(_has_text(page) for page in read):
        raise _RefusedError("the PDF has no text layer, and OCR read no text on it")
    return read, tool


def _base_font(font: object) -> str | None:
    """A PDF font's family name: its ``/BaseFont`` without the subset tag."""
    if not isinstance(font, dict):
        return None
    name = str(font.get("/BaseFont", "")).lstrip("/")
    return _SUBSET_TAG.sub("", name) or None


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
        self._header_values: Mapping[PoHeaderField, Callable[[str], object]] = {
            "po_no": _one_line,
            "revision": _whole_number,
            "po_date": self._day,
            "currency": _currency,
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
                if self._is_title_row(page, text):
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

    def _is_title_row(self, page: _Page, text: str) -> bool:
        titles = [_key(title, scanned=page.scanned) for title, _ in self._layout.columns]
        return [_key(cell, scanned=page.scanned) for cell in _cells(text)] == titles

    def _labelled(self, label: str) -> list[tuple[SourceAnchor, str, _Run | None, _Page]]:
        """Every ``label: value`` line, with the anchor of what printed it, the
        run that did when one matched, and its page."""
        found: list[tuple[SourceAnchor, str, _Run | None, _Page]] = []
        for page in self._pages:
            for text in page.lines:
                value = _labelled(text, label, scanned=page.scanned)
                if value is None:
                    continue
                row = page.find_row([text.strip()])
                run = row[0] if row else None
                found.append((self._anchor(page, run, value), value, run, page))
        return found

    def _header(self) -> PoHeader:
        values: dict[str, object] = {}
        anchors: dict[str, SourceAnchor] = {}
        legacy: list[LegacyText] = []
        for name, label in self._layout.header_labels.items():
            found = self._labelled(label)
            if not found:
                raise _RefusedError(f"no line holds the {name.replace('_', ' ')}")
            anchor, value, run, page = found[0]
            if len({v for _, v, _, _ in found}) > 1:
                raise _RefusedError(f"the {name.replace('_', ' ')} has two values", found[1][0])
            try:
                values[name] = self._header_values[name](value)
            except ValueError as exc:
                raise _RefusedError(f"{name.replace('_', ' ')} {exc}", anchor) from exc
            anchors[name] = anchor
            legacy.extend(page.legacy_text(name, run))
        if "revision" not in values:
            values["revision"] = 0
            anchors["revision"] = anchors["po_no"]
        try:
            return PoHeader.model_validate(
                {**values, "anchors": PoHeaderAnchors(**anchors), "legacy": tuple(legacy)}
            )
        except ValidationError as exc:
            failed = str(exc.errors()[0]["loc"][0])
            raise _RefusedError(f"header: {_first_error(exc)}", anchors.get(failed)) from exc

    def _total(self) -> PrintedTotal | None:
        if self._layout.total_label is None:
            return None
        found = self._labelled(self._layout.total_label)
        if not found:
            return None
        anchor, value, run, page = found[-1]
        # The amount, then the currency it is printed in: the words after the
        # number go, a space that groups thousands stays (`1 443.80 USD`).
        amount = _without_trailing_words(value)
        try:
            return PrintedTotal(
                amount=self._decimal(amount),
                anchor=anchor,
                legacy=page.legacy_text("amount", run),
            )
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
        printed = _cells(text)
        drawn = page.find_row(printed)
        runs: list[_Run | None] = list(drawn) if drawn else [None] * len(printed)
        if len(printed) < len(self._layout.columns):
            # A row with its date left blank (`_is_row`): the gap is the date's.
            gap = self._date_column
            printed = [*printed[:gap], "", *printed[gap:]]
            runs = [*runs[:gap], None, *runs[gap:]]
        values: dict[str, object] = {}
        anchors: dict[str, SourceAnchor] = {}
        legacy: list[LegacyText] = []
        schedules: tuple[DeliverySchedule, ...] = ()
        columns = zip(self._layout.columns, printed, runs, strict=True)
        for (_, name), cell, run in columns:
            anchor = self._anchor(page, run, cell) if cell else anchors["line_no"]
            if name is None:
                continue
            try:
                if name == "requested_date" and no_date(cell):
                    values[name] = None
                    anchors[name] = anchor
                    continue
                if name == "requested_date":
                    listed = listed_schedules(cell, anchor, self._day, self._decimal)
                    schedules = in_date_order(listed) if listed is not None else ()
                values[name] = (
                    schedules[0].requested_date if schedules else self._line_values[name](cell)
                )
            except ValueError as exc:
                raise _RefusedError(f"{name.replace('_', ' ')} {exc}", anchor) from exc
            anchors[name] = anchor
            legacy.extend(page.legacy_text(name, run))
        try:
            return PoLine.model_validate(
                {
                    **values,
                    "anchors": PoLineAnchors(**anchors),
                    "legacy": tuple(legacy),
                    "printed_schedules": schedules,
                }
            )
        except ValidationError as exc:
            failed = str(exc.errors()[0]["loc"][0])
            raise _RefusedError(f"row: {_first_error(exc)}", anchors.get(failed)) from exc

    def _is_row(self, text: str) -> bool:
        cells = _cells(text)
        if not cells or not cells[0].isdigit():
            return False
        columns = self._layout.columns
        if len(cells) == len(columns):
            return True
        if len(cells) != len(columns) - 1:
            return False
        # Its date left blank: with the gap at the date's column, every number
        # reads as one, and what follows the gap is no date the gap would hide.
        gap = self._date_column
        placed = [*cells[:gap], "", *cells[gap:]]
        numbers = all(
            self._number.fullmatch(cell) is not None
            for (_, name), cell in zip(columns, placed, strict=True)
            if name in ("quantity", "unit_price", "amount")
        )
        return numbers and (gap == len(cells) or not self._reads_as_dates(cells[gap]))

    @property
    def _date_column(self) -> int:
        return next(
            i for i, (_, name) in enumerate(self._layout.columns) if name == "requested_date"
        )

    def _reads_as_dates(self, text: str) -> bool:
        """A date in the layout's format, or a ``date: quantity`` list that
        starts with one: what a date cell prints."""
        try:
            self._day(text.partition(":")[0].strip())
        except ValueError:
            return False
        return True

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


def _without_trailing_words(text: str) -> str:
    """``1 443.80 USD`` as ``1 443.80``: the words with no digit after the
    last one that has one go. Walked word by word, in time linear in the
    text: the pattern it replaces backtracked quadratically on a long run of
    words (3 s on 16,000 characters of the customer's total line)."""
    words = list(_WORD.finditer(text))
    while len(words) > 1 and not any(c.isdigit() for c in words[-1].group()):
        words.pop()
    return text[: words[-1].end()].strip() if words else ""


def _cells(text: str) -> Sequence[str]:
    stripped = text.strip()
    return _CELL_GAP.split(stripped) if stripped else []


def _key(text: str, *, scanned: bool = False) -> str:
    """``text`` as a label or a column title is compared. On a scanned page,
    also without diacritics: Tesseract read the scan fixture's `Đơn vị tiền
    tệ` as `Don vị tiền tệ` and `Thành tiền` as `Thanh tién` (ticket 27,
    measured), and a label is structure, not a value; every value read there
    is flagged `ocr` whatever it matched."""
    key = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    if not scanned:
        return key
    bare = "".join(c for c in unicodedata.normalize("NFKD", key) if not unicodedata.combining(c))
    return bare.replace("đ", "d")


def _labelled(text: str, label: str, *, scanned: bool = False) -> str | None:
    """The value on a ``Label: value`` line, or None when the line is not one."""
    head, colon, value = text.strip().partition(":")
    if not colon or _key(head, scanned=scanned) != _key(label, scanned=scanned):
        return None
    return value.strip()


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _currency(text: str) -> str:
    """The currency as ISO: a symbol or a word customers write for one
    (`rfq_reading.parse_currency`, the one table of them), else as printed."""
    return parse_currency(text) or text.strip().upper()


def _whole_number(text: str) -> int:
    if not text.isdigit():
        raise ValueError("is not a whole number")
    return int(text)


def _first_error(exc: ValidationError) -> str:
    error = exc.errors(include_input=False)[0]
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}"
