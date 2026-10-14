"""Ticket 27: a legacy `.xls`/`.doc` is converted, and a scanned PDF page is
OCRed, inside the reader, with nothing of either taken on trust.

LibreOffice and Tesseract are the reader image's, not this machine's: here
they are stand-ins at their seams (`ConverterPort`, `PageOcrPort`, and the
`run` each tool is started through), so what is tested is everything DW1
decides around them: which files are converted, the command and the profile
that keep macros off, both hashes on every anchor and the converter named, a
scan's words read by the same layout with every value flagged `ocr`, and a
tool that fails making the file unreadable, never failing the run. What the
tools themselves make of the fixtures is the image suite's, owed after the
reboot (`apps/reader/tests/integration/test_reader_image.py`).
"""

from __future__ import annotations

import hashlib
import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader

from dw_kernel.errors import DomainError
from dw_sales.adapters.formats import refusal, sniff
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientSourceView
from dw_sales.adapters.readers.layouts import MOCK_PDF_LAYOUTS
from dw_sales.adapters.readers.legacy import PROFILE, ConversionError, LibreOfficeConverter
from dw_sales.adapters.readers.ocr import (
    LANGUAGES,
    OcrError,
    OcrPage,
    TesseractOcr,
    page_from_tsv,
)
from dw_sales.adapters.readers.operations import InProcessReaderTransport, ReaderTools
from dw_sales.adapters.readers.pdf import PdfPoReader
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.order_checks import check_document
from dw_sales.domain.orders import FindingCode, PoDocument, RegionFlag, Unreadable
from dw_sales.testing.reading_tools import (
    CONVERTER,
    SCAN,
    TRUTH,
    ScriptedConverter,
    TruthOcr,
    compound_file,
    m01_as,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
RULES = load_order_rules(REPO / "configs/policies/sales_order_rules@1.5.0.yaml")
CAPS = RULES.intake
# A legacy workbook as far as DW1 tells one; none is committed (the
# public-repo guard cannot read a binary Office file).
XLS = compound_file("Workbook")
SCANNED = SCAN.read_bytes()


def _content(data: bytes, name: str = "po.bin") -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id="A1",
            name=name,
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


class _Blind:
    def __init__(self, error: bool) -> None:
        self.error = error

    def tool(self) -> str:
        if self.error:
            raise OcrError("the OCR engine is not installed where this file was read")
        return "blind"

    def page(self, pdf: bytes, number: int, size: tuple[float, float]) -> OcrPage:
        return OcrPage(width=size[0], height=size[1], lines=())


# --------------------------------------------------------- what a file is --


def test_a_legacy_workbook_is_told_by_its_directory_not_its_text() -> None:
    assert sniff(XLS) == "xls"
    assert sniff(compound_file("Book")) == "xls"
    assert refusal("po.xls", XLS) is None
    assert refusal("po.xlsx", XLS) == "named .xlsx but its bytes are not one"
    # A compound file whose only mention of "Workbook" is text, not an entry.
    ole = XLS[:8] + b"\x00" * 507 + "Workbook".encode("utf-16-le") + b"\x00" * 600
    assert sniff(ole) == "unsupported"


def test_a_legacy_word_file_is_told_by_its_entry() -> None:
    assert sniff(compound_file("WordDocument")) == "doc"
    assert sniff(compound_file("PowerPoint Document")) == "unsupported"


# ------------------------------------------------------------- converting --


class _Run:
    """`subprocess.run` as LibreOffice would answer it, recorded."""

    def __init__(self, *, writes: bytes | None = b"xlsx", code: int = 0) -> None:
        self.writes, self.code = writes, code
        self.commands: list[list[str]] = []
        self.profiles: list[str] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append(command)
        if "--version" in command:
            return subprocess.CompletedProcess(
                command, 0, b"LibreOffice 7.4.7.2 40(Build:2)\n", b""
            )
        self.profiles.append(_xcu(command))
        out = Path(command[command.index("--outdir") + 1])
        if self.writes is not None:
            (out / f"in.{command[command.index('--convert-to') + 1]}").write_bytes(self.writes)
        return subprocess.CompletedProcess(command, self.code, b"", b"")


def _xcu(command: list[str]) -> str:
    """The profile LibreOffice was started on, read where the command says."""
    source = Path(command[-1])
    return (source.parent / "profile" / "user" / "registrymodifications.xcu").read_text(
        encoding="utf-8"
    )


def test_a_conversion_runs_on_a_fresh_profile_with_macros_off() -> None:
    run = _Run()

    converted = LibreOfficeConverter(run=run).convert(XLS, "xls")

    (convert, version) = run.commands
    assert convert[0] == "soffice" and convert[1].startswith("-env:UserInstallation=file:")
    assert convert[2:8] == [
        "--headless",
        "--norestore",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--convert-to",
    ]
    assert convert[8] == "xlsx"
    # Nothing on the command line lowers macro security or picks a filter option.
    assert not [part for part in convert if "macro" in part.lower() or "infilter" in part.lower()]
    assert run.profiles == [PROFILE]
    assert '"DisableMacrosExecution" oor:op="fuse"><value>true' in PROFILE
    assert version == ["soffice", "--version"]
    assert (converted.kind, converted.tool, converted.data) == (
        "xlsx",
        "LibreOffice 7.4.7.2 40(Build:2)",
        b"xlsx",
    )
    assert converted.sha256 == hashlib.sha256(b"xlsx").hexdigest()


def test_a_doc_becomes_a_pdf() -> None:
    run = _Run(writes=b"%PDF-1.7")

    assert LibreOfficeConverter(run=run).convert(b"doc", "doc").kind == "pdf"
    assert run.commands[0][8] == "pdf"


@pytest.mark.parametrize(
    ("run", "reason"),
    [
        (_Run(code=81), "LibreOffice exited 81"),
        (_Run(writes=None), "LibreOffice made no xlsx of the xls file"),
        (_Run(writes=b""), "LibreOffice made no xlsx of the xls file"),
    ],
)
def test_a_conversion_that_fails_says_why(run: _Run, reason: str) -> None:
    with pytest.raises(ConversionError, match=reason):
        LibreOfficeConverter(run=run).convert(XLS, "xls")


def test_no_libreoffice_and_a_hung_one_are_failures_of_the_conversion() -> None:
    def missing(command: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError(command[0])

    def hung(command: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(ConversionError, match="not installed"):
        LibreOfficeConverter(run=missing).convert(XLS, "xls")
    with pytest.raises(ConversionError, match="longer than 5 s"):
        LibreOfficeConverter(run=hung, seconds=5).convert(XLS, "xls")


# ------------------------------------------------- a converted PO is read --


async def test_an_xls_po_is_read_from_its_copy_and_every_anchor_names_both_hashes() -> None:
    made = m01_as("VLX-PO-2610-0021")
    converter = ScriptedConverter(made)
    readers = ClientPoReaders(InProcessReaderTransport(tools=ReaderTools(converter, ocr=None)))

    read = await readers.read(_content(XLS, "po.xls"), "VLX", CAPS)

    assert isinstance(read, PoDocument)
    assert read.header.po_no == "VLX-PO-2610-0021"
    assert read.attachment_sha256 == hashlib.sha256(XLS).hexdigest()
    assert read.derivation is not None
    assert (read.derivation.method, read.derivation.tool) == ("converted", CONVERTER)
    assert read.derivation.derived_sha256 == hashlib.sha256(made).hexdigest()
    anchors = list(read.anchors())
    assert anchors
    assert {(a.attachment_sha256, a.derived_sha256) for a in anchors} == {
        (read.attachment_sha256, read.derivation.derived_sha256)
    }
    assert converter.asked == ["xls"]


async def test_a_legacy_workbook_has_the_platform_layouts_of_a_workbook() -> None:
    readers = ClientPoReaders(
        InProcessReaderTransport(tools=ReaderTools(ScriptedConverter(), ocr=None))
    )

    assert await readers.has_layout("VLX", "xls")
    assert not await readers.has_layout("VLX", "doc")
    assert await readers.has_layout("BRN", "doc")


async def test_an_anchor_naming_another_copy_is_refused_by_the_po() -> None:
    made = m01_as("VLX-PO-2610-0021")
    readers = ClientPoReaders(
        InProcessReaderTransport(tools=ReaderTools(ScriptedConverter(made), ocr=None))
    )
    read = await readers.read(_content(XLS, "po.xls"), "VLX", CAPS)
    assert isinstance(read, PoDocument) and read.derivation is not None

    with pytest.raises(ValueError, match="points outside"):
        PoDocument.model_validate(
            {
                **read.model_dump(),
                "derivation": {**read.derivation.model_dump(), "derived_sha256": "0" * 64},
            }
        )


async def test_a_conversion_that_fails_is_an_unreadable_file_not_a_failed_run() -> None:
    failing = ReaderTools(ScriptedConverter(error="LibreOffice exited 81"), ocr=None)
    readers = ClientPoReaders(InProcessReaderTransport(tools=failing))

    read = await readers.read(_content(XLS, "po.xls"), "VLX", CAPS)
    buyer = await readers.buyer(_content(XLS, "po.xls"), CAPS)
    source = await readers.label_source(_content(XLS, "po.xls"), CAPS)

    assert read == Unreadable(reason="the xls file could not be converted: LibreOffice exited 81")
    assert buyer is None and source is None


async def test_in_process_with_no_libreoffice_a_legacy_po_is_unreadable_with_the_reason() -> None:
    def missing(command: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError(command[0])

    tools = ReaderTools(LibreOfficeConverter(run=missing), ocr=None)
    read = await ClientPoReaders(InProcessReaderTransport(tools=tools)).read(
        _content(XLS, "po.xls"), "VLX", CAPS
    )

    assert isinstance(read, Unreadable)
    assert read.reason == (
        "the xls file could not be converted: LibreOffice is not installed where this file was read"
    )


async def test_a_legacy_workbook_is_shown_as_its_copy_and_a_failure_is_refused() -> None:
    made = m01_as("VLX-PO-2610-0021")
    shown = ClientSourceView(
        InProcessReaderTransport(tools=ReaderTools(ScriptedConverter(made), ocr=None)), CAPS
    )
    refused = ClientSourceView(
        InProcessReaderTransport(tools=ReaderTools(ScriptedConverter(error="exited 81"), ocr=None)),
        CAPS,
    )

    assert shown.kind(XLS) == "xlsx"
    assert await shown.sheet_names(XLS) == ["PO"]
    grid = await shown.sheet_grid(XLS, "PO")
    assert grid is not None and any(c.text == "VLX-PO-2610-0021" for c in grid.cells)
    with pytest.raises(DomainError):
        await refused.sheet_names(XLS)


# ------------------------------------------------------------------- OCR --


def test_tesseract_words_become_lines_of_cells_in_points() -> None:
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t300\t600\t120\t30\t91\tSố",
            "5\t1\t1\t1\t1\t2\t430\t600\t120\t30\t88\tlượng",
            "5\t1\t1\t1\t1\t3\t900\t600\t60\t30\t95\t3.050",
            "5\t1\t1\t1\t1\t4\t1000\t600\t20\t30\t12\t.",
            "4\t1\t1\t1\t1\t0\t300\t600\t700\t30\t-1\t",
            "5\t1\t1\t1\t2\t1\t300\t300\t90\t30\t90\tSTT",
        ]
    )

    page = page_from_tsv(tsv, (841.89, 595.28))

    first, second = page.lines
    # Top of the page first; a wide gap ends a cell; noise is dropped.
    assert [c.text for c in first] == ["STT"]
    assert [c.text for c in second] == ["Số lượng", "3.050"]
    assert second[0].left == pytest.approx(300 * 72 / 300)
    assert second[0].height == pytest.approx(30 * 72 / 300)


def test_tesseract_is_asked_for_one_page_in_vietnamese_then_english() -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        out = (
            TRUTH.read_text(encoding="utf-8").encode() if "tsv" in command else b"tesseract 5.3.0\n"
        )
        return subprocess.CompletedProcess(command, 0, out, b"")

    ocr = TesseractOcr(run=run)
    page = ocr.page(SCANNED, 2, (841.89, 595.28))

    pdftoppm, tesseract = calls
    assert pdftoppm[0] == "pdftoppm" and pdftoppm[1:7] == ["-r", "300", "-f", "2", "-l", "2"]
    assert tesseract[0] == "tesseract" and tesseract[2:] == [
        "stdout",
        "-l",
        "vie+eng",
        "--psm",
        "6",
        "tsv",
    ]
    assert not page.empty
    assert ocr.tool() == "tesseract 5.3.0 vie+eng"


def test_no_tesseract_is_an_ocr_failure() -> None:
    def missing(command: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError(command[0])

    with pytest.raises(OcrError, match="not installed"):
        TesseractOcr(run=missing).page(SCANNED, 1, (841.89, 595.28))


def test_the_scan_fixture_has_no_text_layer() -> None:
    assert not any(page.extract_text().strip() for page in PdfReader(io.BytesIO(SCANNED)).pages)


def test_a_scanned_po_is_read_by_ocr_with_the_layout_and_every_value_is_flagged() -> None:
    reader = PdfPoReader(MOCK_PDF_LAYOUTS, ocr=TruthOcr())
    text = PdfPoReader(MOCK_PDF_LAYOUTS).read(
        _content((ATTACHMENTS_DIR / "M03_BRN-PO-2609-031.pdf").read_bytes()), "BRN", CAPS
    )

    read = reader.read(_content(SCANNED), "BRN", CAPS)

    assert isinstance(read, PoDocument) and isinstance(text, PoDocument)
    assert read.header.po_no == "BRN-PO-2610-027"
    assert [(line.line_no, line.quantity, line.unit_price) for line in read.lines] == [
        (line.line_no, line.quantity, line.unit_price) for line in text.lines
    ]
    assert read.derivation is not None and read.derivation.method == "ocr"
    assert read.derivation.tool == f"truth {LANGUAGES}" and read.derivation.derived_sha256 is None
    # Every value read from the scan is OCR's, the header, each line, the total.
    assert {f.flag for f in read.header.flags} == {RegionFlag.OCR}
    assert all({f.flag for f in line.flags} == {RegionFlag.OCR} for line in read.lines)
    # Each value keeps its page and a box on it.
    assert all(a.page is not None and a.boxes for a in read.anchors())
    # And none is taken on trust.
    findings = check_document(read, RULES)
    assert FindingCode.VALUE_UNCERTAIN in {f.code for f in findings}


def test_a_scan_whose_labels_lost_their_diacritics_is_read_by_its_layout() -> None:
    """What Tesseract 5.3 with `vie+eng` made of the scan's labels and column
    titles (ticket 27, measured 2026-10-14; CI run 38513561151 refused the scan
    "no line holds the currency"): `Đơn vị tiền tệ` as `Don vị tiền tệ`,
    `ĐVT`, `Đơn giá`, `Thành tiền`, `Ngày giao` as `DVT`, `Don gia`, `Thanh
    tién`, `Ngay giao`. A label is matched without its diacritics on a scanned
    page; what it labels is still flagged `ocr`."""
    misread = {
        "Đơn": "Don",
        "ĐVT": "DVT",
        "giá": "gia",
        "Thành": "Thanh",
        "tiền": "tién",
        "Ngày": "Ngay",
    }

    read = PdfPoReader(MOCK_PDF_LAYOUTS, ocr=TruthOcr(edit=misread)).read(
        _content(SCANNED), "BRN", CAPS
    )

    assert isinstance(read, PoDocument), read
    assert (read.header.currency, read.header.po_date.isoformat()) == ("VND", "2026-09-23")
    assert len(read.lines) == 3
    assert all({f.flag for f in line.flags} == {RegionFlag.OCR} for line in read.lines)


@pytest.mark.parametrize(
    ("ocr", "reason"),
    [
        (_Blind(error=True), "the PDF has no text layer: a scan or an image"),
        (_Blind(error=False), "the PDF has no text layer, and OCR read no text on it"),
        (None, "the PDF has no text layer: a scan or an image"),
    ],
    ids=["no engine", "no word read", "not given one"],
)
def test_a_scan_ocr_cannot_read_is_unreadable_with_why(ocr: Any, reason: str) -> None:
    read = PdfPoReader(MOCK_PDF_LAYOUTS, ocr=ocr).read(_content(SCANNED), "BRN", CAPS)

    assert read == Unreadable(reason=reason)


def test_a_text_pdf_is_never_ocred() -> None:
    m03 = (ATTACHMENTS_DIR / "M03_BRN-PO-2609-031.pdf").read_bytes()

    read = PdfPoReader(MOCK_PDF_LAYOUTS, ocr=_Blind(error=True)).read(_content(m03), "BRN", CAPS)

    assert isinstance(read, PoDocument) and read.derivation is None
    assert RegionFlag.OCR not in {f.flag for f in read.header.flags}


def test_the_scan_fixture_carries_no_date() -> None:
    """Deterministic fixtures: no date in the scan's PDF, so the generator
    makes the same bytes again."""
    info = PdfReader(io.BytesIO(SCANNED)).metadata
    assert info is None or not {k for k in info if k in ("/CreationDate", "/ModDate")}
