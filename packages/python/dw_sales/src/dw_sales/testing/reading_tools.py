"""Stand-ins for the reader image's tools (ticket 27), for the unit suite and
the evals: LibreOffice and Tesseract are installed in the reader's image, not
where these run.

- `compound_file`: the bytes of a legacy Office file as far as DW1 tells one
  (an OLE compound file whose directory names a workbook or Word stream).
  None is committed: the public-repo guard cannot read a binary Office file.
- `xls_made_in_reader`: a real `.xls`, written by the running reader
  container's own LibreOffice, for the image suite and
  `scripts/measure_reader.py`, which need one and cannot find one committed.
- `ScriptedConverter`: answers a conversion with the bytes it is given, as
  LibreOffice's would be, or with a failure.
- `TruthOcr`: reads the scanned fixture through what a perfect OCR answers
  (`adapters/mock/legacy/*.tsv`, written by `generate_scan`).

What the real tools make of the fixtures is measured on the image (the
reader's integration suite, owed after the WSL reboot).
"""

from __future__ import annotations

import base64
import io
import subprocess
from collections.abc import Sequence
from typing import Final

from openpyxl import load_workbook

from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, LEGACY_DIR
from dw_sales.adapters.readers.legacy import ConversionError, Converted, Legacy
from dw_sales.adapters.readers.ocr import LANGUAGES, OcrPage, page_from_tsv

_OLE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
SCAN: Final = LEGACY_DIR / "scan_BRN-PO-2610-027.pdf"
TRUTH: Final = LEGACY_DIR / "scan_BRN-PO-2610-027.tsv"
CONVERTER: Final = "LibreOffice 7.4.7.2 (scripted)"
LEGACY_PO_NO: Final = "VLX-PO-2610-0021"
# Run in the reader container: M01's workbook on stdin, written out as an
# Excel 97-2003 file by the image's LibreOffice, in a throwaway directory.
_TO_XLS: Final = (
    'cd "$(mktemp -d)" && cat > po.xlsx && HOME=$PWD soffice --headless'
    " --convert-to 'xls:MS Excel 97' po.xlsx >/dev/null 2>&1 && base64 -w0 po.xls"
)


def compound_file(stream: str = "Workbook") -> bytes:
    """A compound file whose directory's second sector names ``stream``:
    what `formats.sniff` tells a legacy file by."""
    name = stream.encode("utf-16-le") + b"\x00\x00"
    entry = name + b"\x00" * (64 - len(name)) + len(name).to_bytes(2, "little")
    return _OLE + b"\x00" * (1024 - len(_OLE)) + entry + b"\x00" * (128 - len(entry))


def m01_as(po_no: str) -> bytes:
    """M01's workbook under ``po_no``: what LibreOffice makes of an `.xls`
    holding M01's sheet, as far as the reader goes."""
    workbook = load_workbook(ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx")
    workbook["PO"]["B4"] = po_no
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def xls_made_in_reader(compose: Sequence[str]) -> bytes:
    """M01 under `LEGACY_PO_NO` as an `.xls`, written by the LibreOffice of
    the reader container ``compose`` (the `docker compose` command and its
    flags) runs."""
    made = subprocess.run(
        [*compose, "exec", "-T", "reader", "bash", "-c", _TO_XLS],
        input=m01_as(LEGACY_PO_NO),
        capture_output=True,
        timeout=180,
        check=False,
    )
    if made.returncode != 0 or not made.stdout:
        stderr = made.stderr.decode("utf-8", errors="replace")[-300:]
        raise RuntimeError(f"the reader's LibreOffice wrote no .xls: {stderr}")
    return base64.b64decode(made.stdout)


class ScriptedConverter:
    """`ConverterPort` answering with ``made``, or failing with ``error``."""

    def __init__(self, made: bytes | None = None, error: str | None = None) -> None:
        self.made, self.error = made, error
        self.asked: list[Legacy] = []

    def convert(self, data: bytes, kind: Legacy) -> Converted:
        self.asked.append(kind)
        if self.error is not None:
            raise ConversionError(self.error)
        if self.made is None:
            raise ConversionError("nothing scripted")
        return Converted(self.made, "xlsx" if kind == "xls" else "pdf", CONVERTER)


class TruthOcr:
    """`PageOcrPort` answering what a perfect OCR of the scan reads; ``edit``
    changes a word as it would be read (an instruction printed on the page)."""

    def __init__(self, edit: dict[str, str] | None = None) -> None:
        self.edit = edit or {}
        self.pages: list[int] = []

    def tool(self) -> str:
        return f"truth {LANGUAGES}"

    def page(self, pdf: bytes, number: int, size: tuple[float, float]) -> OcrPage:
        self.pages.append(number)
        header, *rows = TRUTH.read_text(encoding="utf-8").splitlines()
        on_page = [self._edited(row) for row in rows if row.split("\t")[1] == str(number)]
        return page_from_tsv("\n".join([header, *on_page]), size)

    def _edited(self, row: str) -> str:
        *fields, text = row.split("\t")
        return "\t".join([*fields, self.edit.get(text, text)])
