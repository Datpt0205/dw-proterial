"""`ArtifactWriterPort` over openpyxl, reportlab and the standard email package.

Three rules hold for every file written here:

- **A string is text, never a formula** (G29). openpyxl reads a string that
  starts with ``=`` as a formula; every string cell is set back to type
  ``s``, and one that a spreadsheet would read as a formula once edited
  (``= + - @``, a tab or a carriage return first) also gets Excel's quote
  prefix. A PO description reading ``=HYPERLINK(...)`` stays those characters.
- **The same content writes the same bytes.** The zip entries, the workbook's
  own dates and the PDF's are the content's ``stamped_at``, and a message's
  MIME boundary is derived from its content, so the send draft attaches the
  quotation byte for byte as stored.
- **A draft is a draft.** The ``.eml`` is marked ``X-Unsent: 1``: a mail client
  opens it for the person to read and send; nothing here sends anything.

The quotation PDF is printed here, from the same content as its xlsx, rather
than converted from the xlsx (G38: reportlab stays a runtime dependency of
dw_sales; `apps/docgen` is not involved).
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Final
from xml.sax.saxutils import escape

from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dw_sales.application.artifact_content import EmailDraft, Sheet, Value, Workbook
from dw_sales.domain.messages import EmailAddress

# DejaVu Sans cut down to Latin and Vietnamese, the subset the mock
# attachments are printed with (licence beside it).
LATIN_FONT: Final = Path(__file__).resolve().parent / "mock" / "fonts" / "DejaVuSans-LatinVi.ttf"
# What a spreadsheet reads as the start of a formula once a cell is edited.
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")
_LATIN_FONT: Final = "DW1Latin"
# Adobe's Japanese CID font: no file to ship, and every PDF reader has it.
_JAPANESE_FONT: Final = "HeiseiKakuGo-W5"
_CORE_MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")


class ArtifactFiles:
    """Implements `ArtifactWriterPort`.

    ``latin_font`` is a TrueType font with the Latin and Vietnamese glyphs the
    vi and en documents print (the DejaVu subset the mock attachments use).
    """

    def __init__(self, latin_font: Path = LATIN_FONT) -> None:
        registered = pdfmetrics.getRegisteredFontNames()
        if _LATIN_FONT not in registered:
            pdfmetrics.registerFont(TTFont(_LATIN_FONT, str(latin_font)))
        if _JAPANESE_FONT not in registered:
            pdfmetrics.registerFont(UnicodeCIDFont(_JAPANESE_FONT))

    # ---------------------------------------------------------------- xlsx --

    def workbook(self, book: Workbook) -> bytes:
        workbook = OpenpyxlWorkbook()
        default = workbook.active
        for sheet in book.sheets:
            _fill(workbook.create_sheet(title=sheet.name), sheet)
        if default is not None:
            workbook.remove(default)
        stamped = _naive_utc(book.stamped_at)
        workbook.properties.creator = "DW1"
        workbook.properties.created = stamped
        buffer = io.BytesIO()
        workbook.save(buffer)
        return _repacked(buffer.getvalue(), stamped)

    # ----------------------------------------------------------------- pdf --

    def pdf(self, book: Workbook) -> bytes:
        sheet = book.sheets[0]
        font = _JAPANESE_FONT if book.language == "ja" else _LATIN_FONT
        body = ParagraphStyle("body", fontName=font, fontSize=8, leading=10)
        title = ParagraphStyle("title", fontName=font, fontSize=14, leading=18)
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=sheet.title or sheet.name,
            author="DW1",
            invariant=1,
        )

        def cell(value: Value) -> Paragraph:
            return Paragraph(_markup(_text(value), font), body)

        story: list[object] = []
        if sheet.title:
            story += [Paragraph(_markup(sheet.title, font), title), Spacer(1, 4 * mm)]
        if sheet.heading:
            story += [
                Table([[cell(name), cell(value)] for name, value in sheet.heading]),
                Spacer(1, 4 * mm),
            ]
        if sheet.columns:
            grid = Table(
                [[cell(c) for c in sheet.columns], *([cell(v) for v in row] for row in sheet.rows)],
                repeatRows=1,
            )
            grid.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(grid)
        story += [Paragraph(_markup(note, font), body) for note in sheet.notes]
        document.build(story)  # type: ignore[arg-type]
        return buffer.getvalue()

    # ----------------------------------------------------------------- eml --

    def email(self, draft: EmailDraft) -> bytes:
        message = EmailMessage(policy=policy.SMTP)
        message["From"] = _address(draft.sender)
        message["Reply-To"] = _address(draft.reply_to)
        message["To"] = [_address(recipient) for recipient in draft.to]
        message["Subject"] = draft.subject
        message["Date"] = format_datetime(draft.dated.astimezone(UTC))
        message["X-Unsent"] = "1"
        message.set_content(draft.body, charset="utf-8")
        for attached in draft.attachments:
            maintype, _, subtype = attached.content_type.partition("/")
            message.add_attachment(
                attached.data, maintype=maintype, subtype=subtype, filename=attached.name
            )
        if message.is_multipart():
            seed = hashlib.sha256(draft.body.encode("utf-8"))
            for attached in draft.attachments:
                seed.update(attached.data)
            message.set_boundary(f"dw1-{seed.hexdigest()[:40]}")
        return message.as_bytes()


# ----------------------------------------------------------------- helpers --


def _address(address: EmailAddress) -> Address:
    return Address(display_name=address.display_name, addr_spec=address.address)


def _naive_utc(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def _put(sheet: Worksheet, row: int, col: int, value: Value, *, bold: bool = False) -> None:
    if value is None:
        return
    cell = sheet.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str):
        # openpyxl typed a leading "=" as a formula when assigned: text it is.
        cell.data_type = "s"
        if value.startswith(_FORMULA_START):
            cell.quotePrefix = True
    elif isinstance(value, Decimal):
        # The places the case holds, so 0.6890 prints as 0.6890, not 0.689.
        places = -value.as_tuple().exponent  # type: ignore[operator]
        cell.number_format = "0." + "0" * places if places > 0 else "0"
    elif isinstance(value, date):
        cell.number_format = "yyyy-mm-dd"
    if bold:
        cell.font = Font(bold=True)


def _fill(target: Worksheet, sheet: Sheet) -> None:
    row = 1
    if sheet.title:
        _put(target, row, 1, sheet.title, bold=True)
        row += 2
    for name, value in sheet.heading:
        _put(target, row, 1, name, bold=True)
        _put(target, row, 2, value)
        row += 1
    if sheet.title or sheet.heading:
        row += 1
    if sheet.columns:
        for col, header in enumerate(sheet.columns, start=1):
            _put(target, row, col, header, bold=True)
        row += 1
        for values in sheet.rows:
            for col, value in enumerate(values, start=1):
                _put(target, row, col, value)
            row += 1
    if sheet.notes:
        row += 1
        for note in sheet.notes:
            _put(target, row, 1, note)
            row += 1


def _repacked(data: bytes, stamped: datetime) -> bytes:
    """The workbook's zip with every entry dated ``stamped`` and the core
    properties' modification time set to it, in place of the time of saving."""
    when = max(stamped, datetime(1980, 1, 1))
    date_time = (when.year, when.month, when.day, when.hour, when.minute, when.second)
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                content = _CORE_MODIFIED.sub(rb"\g<1>" + iso + rb"\g<2>", content)
            entry = zipfile.ZipInfo(info.filename, date_time=date_time)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            target.writestr(entry, content)
    return out.getvalue()


def _markup(text: str, font: str) -> str:
    """``text`` as Paragraph markup: escaped, so a customer's ``<`` is a
    character and never a tag, and, under the Japanese font, each run of
    characters it has no glyph for (a Vietnamese name) set in the Latin one."""
    if font != _JAPANESE_FONT:
        return escape(text)
    runs: list[tuple[bool, str]] = []
    for char in text:
        latin = not _in_jis(char)
        if runs and runs[-1][0] == latin:
            runs[-1] = (latin, runs[-1][1] + char)
        else:
            runs.append((latin, char))
    return "".join(
        f'<font name="{_LATIN_FONT}">{escape(run)}</font>' if latin else escape(run)
        for latin, run in runs
    )


def _in_jis(char: str) -> bool:
    try:
        char.encode("shift_jis")
    except UnicodeEncodeError:
        return False
    return True


def _text(value: Value) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
