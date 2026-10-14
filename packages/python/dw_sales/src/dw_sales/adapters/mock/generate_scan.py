"""Ticket 27's scanned PO: a fictional PDF with no text layer, made from the
committed mock M03 with a PO number of its own, and what a perfect OCR of it
reads.

    uv run python -m dw_sales.adapters.mock.generate_scan

- `legacy/scan_BRN-PO-2610-027.pdf`: M03's two pages as images, each line
  drawn where its text layer prints it, in the mock font (Vietnamese
  diacritics), bilevel at 300 dpi, as a fax-like scan.
- `legacy/scan_BRN-PO-2610-027.tsv`: what a perfect OCR of that scan answers,
  in Tesseract's TSV, from where this script drew each word. The unit suite
  and the evals read the scan through it (`dw_sales.testing.reading_tools`);
  the reader image's suite compares Tesseract's own reading against it
  (ticket 27, "Post-reboot checks").

No legacy `.xls`/`.doc` is committed: the public-repo guard cannot read a
binary Office file and counts one a finding (`scripts/check_public_repo.py`).
The image suite makes them in the image from M01 with LibreOffice, and the
unit suite and the evals hand the reader a compound file naming a workbook
stream, with the converter scripted.

Kept out of the mailbox: adding the scan to `data/inbox.json` would change
every count the demo and its walk pin. Deterministic: the same inputs give
the same bytes (no timestamp is written).
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

MOCK = Path(__file__).resolve().parent
FONT = MOCK / "fonts" / "DejaVuSans-LatinVi.ttf"
SCAN = MOCK / "legacy" / "scan_BRN-PO-2610-027.pdf"
TRUTH = MOCK / "legacy" / "scan_BRN-PO-2610-027.tsv"

DPI = 300
MARGIN = 90
TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)
_CELL = re.compile(r"\S+(?: \S+)*")


def scanned_pdf() -> tuple[bytes, str]:
    reader = PdfReader(MOCK / "attachments" / "M03_BRN-PO-2609-031.pdf")
    pages: list[Image.Image] = []
    truth = [TSV_HEADER]
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text(extraction_mode="layout").replace(
            "BRN-PO-2609-031", "BRN-PO-2610-027"
        )
        width = round(float(page.mediabox.width) / 72 * DPI)
        height = round(float(page.mediabox.height) / 72 * DPI)
        image, rows = _drawn(text, width, height, number)
        pages.append(image)
        truth += rows
    buffer = io.BytesIO()
    pages[0].save(
        buffer,
        "PDF",
        resolution=DPI,
        save_all=True,
        append_images=pages[1:],
        creationDate=None,
        modDate=None,
        title=None,
    )
    return buffer.getvalue(), "\n".join(truth) + "\n"


def _drawn(text: str, width: int, height: int, page: int) -> tuple[Image.Image, list[str]]:
    """``text`` drawn line by line, each cell where its column starts; and
    the TSV rows of every word drawn."""
    lines = text.split("\n")
    columns = max(len(line) for line in lines) or 1
    advance = (width - 2 * MARGIN) / columns
    size = max(12, int(advance / 0.62))
    font = ImageFont.truetype(str(FONT), size)
    pitch = (height - 2 * MARGIN) / max(len(lines), 1)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    rows: list[str] = []
    for index, line in enumerate(lines, start=1):
        top = MARGIN + (index - 1) * pitch
        word_no = 0
        for cell in _CELL.finditer(line):
            x = MARGIN + cell.start() * advance
            draw.text((x, top), cell.group(), fill=0, font=font)
            for word in re.finditer(r"\S+", cell.group()):
                word_no += 1
                left = x + draw.textlength(cell.group()[: word.start()], font=font)
                box = draw.textbbox((left, top), word.group(), font=font)
                fields = (
                    5,
                    page,
                    1,
                    1,
                    index,
                    word_no,
                    round(box[0]),
                    round(box[1]),
                    round(box[2] - box[0]),
                    round(box[3] - box[1]),
                    96,
                    word.group(),
                )
                rows.append("\t".join(str(v) for v in fields))
    return image.convert("1", dither=Image.Dither.NONE), rows


def main() -> None:
    pdf, truth = scanned_pdf()
    SCAN.write_bytes(pdf)
    TRUTH.write_text(truth, encoding="utf-8", newline="\n")
    for path in (SCAN, TRUTH):
        print(f"wrote {path.name} ({path.stat().st_size} bytes)", file=sys.stdout)


if __name__ == "__main__":
    main()
