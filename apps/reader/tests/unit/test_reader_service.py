"""The reader sandbox's service: one request, one throwaway reading process.

Run on the developer's machine without the image's limits (Windows has no
`ulimit`); what the limits do is the image's to show, after the build
(`apps/reader/tests/integration`, owed with Docker). What is tested here is
everything the service decides: the body's cap, the process's answer passed
through, a crash, a timeout and an oversized answer each a reply of their own
kind, nothing left behind, and a health check that fails on a broken reader.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dw_reader import reading
from dw_reader.main import create_app
from dw_reader.settings import ReaderSettings
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_wire import ReaderArgs, ReaderOp, ReaderReply, ReaderRequest
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.domain.orders import PoDocument

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
CAPS = load_order_rules(REPO / "configs/policies/sales_order_rules@1.5.0.yaml").intake
M01 = (ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx").read_bytes()


@pytest.fixture
def settings(tmp_path: Path) -> ReaderSettings:
    return ReaderSettings(root=str(tmp_path / "work"), read_seconds=60, max_request_bytes=1 << 20)


@pytest.fixture
def client(settings: ReaderSettings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _po_request() -> bytes:
    content = AttachmentContent(
        attachment=Attachment(
            attachment_id="A1",
            name="po.xlsx",
            media_type="application/octet-stream",
            size=len(M01),
            sha256=hashlib.sha256(M01).hexdigest(),
        ),
        data=M01,
    )
    request = ReaderRequest.of(
        ReaderOp.PO_READ, content=content, args=ReaderArgs(caps=CAPS, customer_code="VLX")
    )
    return request.model_dump_json().encode("utf-8")


def _python(code: str) -> str:
    """A reading process that runs ``code`` instead of reading."""
    return f'{subprocess.list2cmdline([sys.executable])} -c "{code}"'


def test_a_po_is_read_by_a_reading_process_and_its_answer_comes_back(
    client: TestClient, settings: ReaderSettings
) -> None:
    response = client.post("/v1/read", content=_po_request())

    assert response.status_code == 200
    reply = ReaderReply.model_validate_json(response.content)
    document = reply.value(ReaderOp.PO_READ)
    assert isinstance(document, PoDocument)
    assert document.header.po_no == "VLX-PO-2609-0118"
    # Nothing of the request is left behind: only the service's own directory.
    assert [p.name for p in Path(settings.root).iterdir()] == [".service"]


def test_the_health_check_is_ready_once_a_reading_process_answered(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_a_reader_that_cannot_start_is_not_ready(
    settings: ReaderSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "child_command", lambda: _python("raise SystemExit(3)"))

    with TestClient(create_app(settings)) as broken:
        assert broken.get("/health").status_code == 503


def test_a_body_over_the_cap_is_refused_before_it_is_read(client: TestClient) -> None:
    response = client.post("/v1/read", content=b"x" * ((1 << 20) + 1))

    assert response.status_code == 413


def test_a_reading_process_that_dies_is_a_crash_not_an_error_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "child_command", lambda: _python("raise SystemExit(1)"))

    reply = ReaderReply.model_validate_json(client.post("/v1/read", content=b"{}").content)

    assert reply.failure == "crashed"
    assert reply.detail == "the reading process exited 1"


def test_a_request_the_reading_process_cannot_parse_is_a_crash(client: TestClient) -> None:
    reply = ReaderReply.model_validate_json(client.post("/v1/read", content=b"{}").content)

    assert reply.failure == "crashed"


def test_a_reading_process_past_the_clock_is_killed_and_timed_out(
    settings: ReaderSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reading, "child_command", lambda: _python("import time; time.sleep(30)"))
    slow = settings.model_copy(update={"read_seconds": 1})

    reply = ReaderReply.model_validate_json(reading.read_once(b"{}", slow))

    assert reply.failure == "timed_out"
    assert reply.detail == "reading took longer than 1 s"


def test_an_answer_over_its_cap_is_refused(settings: ReaderSettings) -> None:
    small = settings.model_copy(update={"max_result_bytes": 16})

    reply = ReaderReply.model_validate_json(reading.read_once(_po_request(), small))

    assert reply.failure == "refused"


def test_a_reading_process_that_could_not_set_its_limits_is_an_outage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preamble's own refusal (`LIMITS_UNAVAILABLE_EXIT_CODE`): nothing
    was read, and the caller is told the reader is unavailable, never that
    the file could not be read."""
    monkeypatch.setattr(reading, "child_command", lambda: _python("raise SystemExit(97)"))

    response = client.post("/v1/read", content=b"{}")

    assert response.status_code == 503


def test_a_body_with_no_length_is_cut_off_at_the_cap(client: TestClient) -> None:
    """A chunked body declares no length: it is counted as it arrives."""

    def chunks() -> Iterator[bytes]:
        for _ in range(17):
            yield b"x" * (1 << 16)

    response = client.post("/v1/read", content=chunks())

    assert response.status_code == 413


def test_a_declared_length_over_the_cap_is_refused_before_the_body_is_read(
    client: TestClient,
) -> None:
    response = client.post(
        "/v1/read", content=b"{}", headers={"content-length": str((1 << 20) + 1)}
    )

    assert response.status_code == 413
