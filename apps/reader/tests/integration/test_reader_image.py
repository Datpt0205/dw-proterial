"""What the built reader image does (Sales tickets 25 and 27): the properties
the design rests on are the container's (no network, a read-only root, the
limits a reading process starts under, nothing left behind), and the tools are
the image's (LibreOffice, Tesseract), so these run against the running
container, never in process.

    docker compose --env-file .env -f infra/compose/docker-compose.yml \\
      --profile infra up -d --build --wait reader reader-gateway
    DW_TEST_READER=http://127.0.0.1:8120 \\
      uv run pytest -m integration apps/reader/tests/integration

Owed since 2026-10-14: written while Docker's WSL VM was down, run after the
reboot (ticket 25, "Post-reboot checks"). On CI it fails, rather than skips,
without `DW_TEST_READER`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, LEGACY_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import (
    ClientPoReaders,
    ClientSourceView,
    HttpReaderTransport,
)
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.orders import PoDocument, RegionFlag

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
CAPS = load_order_rules(REPO / "configs/policies/sales_order_rules@1.5.0.yaml").intake
READER = os.environ.get("DW_TEST_READER")
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(REPO / ".env"),
    "-f",
    str(REPO / "infra/compose/docker-compose.yml"),
    "--profile",
    "infra",
]


@pytest.fixture(scope="module")
def reader() -> HttpReaderTransport:
    if not READER:
        if os.environ.get("CI"):
            pytest.fail("DW_TEST_READER is not set on CI: the reader image went unchecked")
        pytest.skip("no reader image to check: set DW_TEST_READER (the gateway's URL)")
    return HttpReaderTransport(base_url=READER, timeout_seconds=300)


def _exec(*command: str) -> subprocess.CompletedProcess[str]:
    """``command`` inside the running reader container, as its own user."""
    return subprocess.run(
        [*COMPOSE, "exec", "-T", "reader", *command],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _content(name: str, data: bytes) -> AttachmentContent:
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


def test_the_service_is_ready_with_its_limits_on(reader: HttpReaderTransport) -> None:
    answer = httpx.get(f"{READER}/health", timeout=10)

    assert answer.status_code == 200
    assert answer.json() == {"status": "ok", "limits_enforced": True}


@pytest.mark.parametrize(
    ("name", "customer"),
    [("M01_VLX-PO-2609-0118.xlsx", "VLX"), ("M03_BRN-PO-2609-031.pdf", "BRN")],
)
async def test_a_po_read_in_the_image_is_the_po_read_in_process(
    reader: HttpReaderTransport, name: str, customer: str
) -> None:
    content = _content(name, (ATTACHMENTS_DIR / name).read_bytes())

    sandboxed = await ClientPoReaders(reader).read(content, customer, CAPS)
    in_process = await mock_po_readers().read(content, customer, CAPS)

    assert sandboxed == in_process


async def test_a_request_leaves_nothing_behind(reader: HttpReaderTransport) -> None:
    name = "M01_VLX-PO-2609-0118.xlsx"
    await ClientPoReaders(reader).read(
        _content(name, (ATTACHMENTS_DIR / name).read_bytes()), "VLX", CAPS
    )

    left = _exec("ls", "-A", "/work")

    assert left.returncode == 0, left.stderr
    assert left.stdout.split() == [".service"]


def test_the_container_has_no_network_and_a_read_only_root() -> None:
    interfaces = _exec("ls", "/sys/class/net")
    dial = _exec(
        "python", "-c", "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)"
    )
    write = _exec("touch", "/app/planted")

    assert interfaces.stdout.split() == ["lo"]
    assert dial.returncode != 0
    assert write.returncode != 0


def test_a_reading_process_starts_under_its_limits() -> None:
    """The preamble the service puts before every reading process, applied by
    this image's bash: what `ulimit` then says is the budget."""
    preamble = _exec(
        "python",
        "-c",
        "from dw_docgen.runner import limit_preamble;"
        "from dw_reader.settings import get_settings;"
        "print(limit_preamble(get_settings()))",
    )
    assert preamble.returncode == 0, preamble.stderr

    limits = _exec("bash", "-c", preamble.stdout + "ulimit -t; ulimit -v; ulimit -u; ulimit -c")

    assert limits.stdout.split() == ["150", str(2048 * 1024), "256", "0"]


async def test_libreoffice_converts_the_legacy_po_and_both_hashes_are_on_it(
    reader: HttpReaderTransport,
) -> None:
    data = (LEGACY_DIR / "legacy_VLX-PO-2610-0021.xls").read_bytes()

    started = time.perf_counter()
    read = await ClientPoReaders(reader).read(_content("po.xls", data), "VLX", CAPS)
    seconds = time.perf_counter() - started

    assert isinstance(read, PoDocument), read
    assert read.header.po_no == "VLX-PO-2610-0021"
    assert read.derivation is not None and read.derivation.tool.startswith("LibreOffice")
    assert read.attachment_sha256 == hashlib.sha256(data).hexdigest()
    assert {a.derived_sha256 for a in read.anchors()} == {read.derivation.derived_sha256}
    print(f"\n.xls PO converted and read in {seconds:.1f} s by {read.derivation.tool}")


async def test_tesseract_reads_the_scanned_po_and_nothing_it_read_is_trusted(
    reader: HttpReaderTransport,
) -> None:
    data = (LEGACY_DIR / "scan_BRN-PO-2610-027.pdf").read_bytes()
    text = (ATTACHMENTS_DIR / "M03_BRN-PO-2609-031.pdf").read_bytes()

    started = time.perf_counter()
    read = await ClientPoReaders(reader).read(_content("scan.pdf", data), "BRN", CAPS)
    seconds = time.perf_counter() - started
    truth = await mock_po_readers().read(_content("po.pdf", text), "BRN", CAPS)

    assert isinstance(truth, PoDocument)
    # The measurement this suite owes (acceptance 3): what Tesseract read right.
    print(f"\nscanned PO (2 pages) read in {seconds:.1f} s: {read!r}"[:2000])
    assert isinstance(read, PoDocument), read
    assert read.derivation is not None and read.derivation.method == "ocr"
    assert read.header.po_no == "BRN-PO-2610-027"
    assert [(line.quantity, line.unit_price) for line in read.lines] == [
        (line.quantity, line.unit_price) for line in truth.lines
    ]
    assert all({f.flag for f in line.flags} == {RegionFlag.OCR} for line in read.lines)


async def test_a_bars_only_scan_is_still_unreadable(reader: HttpReaderTransport) -> None:
    name = "M16_BRN-PO-2609-044.pdf"

    read = await ClientPoReaders(reader).read(
        _content(name, (ATTACHMENTS_DIR / name).read_bytes()), "BRN", CAPS
    )

    assert not isinstance(read, PoDocument)


async def test_a_legacy_word_file_is_shown_as_its_pdf(reader: HttpReaderTransport) -> None:
    """A .doc made in the image from a .docx python-docx writes there."""
    made = _exec(
        "bash",
        "-c",
        'cd "$(mktemp -d)" && python -c "from docx import Document; d=Document(); '
        "d.add_paragraph('Số đơn hàng: BRN-PO-2610-030'); d.save('po.docx')\" && "
        "HOME=$PWD soffice --headless --convert-to doc po.docx >/dev/null && base64 -w0 po.doc",
    )
    assert made.returncode == 0, made.stderr
    doc = base64.b64decode(made.stdout)

    page = await ClientSourceView(reader, CAPS).pdf_page(doc, 1)

    assert page is not None and page[0].startswith(b"%PDF-")
