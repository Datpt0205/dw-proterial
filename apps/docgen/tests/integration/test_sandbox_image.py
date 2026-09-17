"""What the built image actually does — the tests the design rests on.

These run against a running `docgen` container, not against the app in-process:
the properties being proven are properties of the *container* (no route off the
machine, a read-only root, a toolchain that works without a JRE) and an
in-process run would assert none of them.

    docker compose --env-file .env -f infra/compose/docker-compose.yml \
      --profile infra up -d --build docgen docgen-gateway
    uv run pytest -m integration apps/docgen/tests/integration
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator

import httpx
import pytest

pytestmark = pytest.mark.integration

SANDBOX_URL = os.environ.get("DW_DOCGEN_URL", "http://127.0.0.1:8110")
TOKEN = os.environ.get("DW_DOCGEN_TOKEN", "")

# A LibreOffice conversion on a cold container is tens of seconds, and a CI
# runner is slower than a laptop.
SLOW_COMMAND_SECONDS = 180

DIACRITICS = "ế ộ ỹ ằ Đ đ"

GENERATE_DOCX = f"""
from docx import Document

document = Document()
document.add_heading("Bao cao thu nghiem", 0)
document.add_paragraph("Dau tieng Viet: {DIACRITICS}")
document.add_paragraph("So lieu: 1.500.000 VND, tang 12%")
document.save("out.docx")
print("generated")
"""

CONVERT_TO_PDF = "soffice --headless --convert-to pdf --outdir . out.docx"


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    timeout = SLOW_COMMAND_SECONDS + 30
    with httpx.Client(base_url=SANDBOX_URL, headers=headers, timeout=timeout) as connected:
        yield connected


@pytest.fixture
def session(client: httpx.Client) -> Iterator[str]:
    session_id = f"test-{uuid.uuid4().hex[:12]}"
    yield session_id
    client.post(f"/v1/sessions/{session_id}")


def run(
    client: httpx.Client, session: str, command: str, *, timeout: int = 30
) -> dict[str, object]:
    reply = client.post(
        f"/v1/sessions/{session}/execute",
        json={"command": command, "timeout_seconds": timeout},
    )
    reply.raise_for_status()
    return dict(reply.json())


def write(client: httpx.Client, session: str, path: str, body: str) -> None:
    reply = client.post(
        f"/v1/sessions/{session}/files/upload",
        json={"files": [{"path": path, "content_b64": _b64(body.encode())}]},
    )
    reply.raise_for_status()
    assert reply.json()["results"][0]["error"] is None


def generate_and_convert(client: httpx.Client, session: str) -> None:
    write(client, session, "gen.py", GENERATE_DOCX)
    run(client, session, "python3 gen.py")
    run(client, session, CONVERT_TO_PDF, timeout=SLOW_COMMAND_SECONDS)


# ------------------------------------------------------------ containment --


def test_the_sandbox_cannot_open_a_socket(client: httpx.Client, session: str) -> None:
    """The load-bearing control. If this ever passes wrongly nothing else
    matters: an instruction injected through an attachment could send what it
    read."""
    write(
        client,
        session,
        "reach.py",
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=5)\n"
        "    print('CONNECTED')\n"
        "except OSError as exc:\n"
        "    print('BLOCKED', exc)\n",
    )

    result = run(client, session, "python3 reach.py")

    assert "BLOCKED" in str(result["output"])
    assert "CONNECTED" not in str(result["output"])


def test_the_sandbox_cannot_resolve_a_name(client: httpx.Client, session: str) -> None:
    write(
        client,
        session,
        "resolve.py",
        "import socket\n"
        "try:\n"
        "    print('RESOLVED', socket.gethostbyname('example.com'))\n"
        "except OSError as exc:\n"
        "    print('BLOCKED', exc)\n",
    )

    result = run(client, session, "python3 resolve.py")

    assert "RESOLVED" not in str(result["output"])


def test_a_command_that_never_finishes_is_killed(client: httpx.Client, session: str) -> None:
    result = run(client, session, "while true; do :; done", timeout=5)

    assert result["timed_out"] is True
    assert "killed after 5s" in str(result["output"])


def test_a_memory_bomb_dies_inside_the_budget(client: httpx.Client, session: str) -> None:
    write(client, session, "hog.py", "b = bytearray(4 * 1024 * 1024 * 1024)\nprint('ALLOCATED')\n")

    result = run(client, session, "python3 hog.py", timeout=60)

    assert result["exit_code"] != 0
    assert result["timed_out"] is False
    assert "ALLOCATED" not in str(result["output"])


def test_a_fork_bomb_leaves_the_container_usable(client: httpx.Client, session: str) -> None:
    """Answering `/health` is not the property that matters. A fork bomb exits 0
    while its descendants keep running, and those survivors hold the container's
    process budget - the service still replies and every later command fails
    with "Resource temporarily unavailable". So the assertion is that the NEXT
    command works."""
    run(client, session, ":(){ :|:& };:", timeout=8)

    after = run(client, session, "python3 -c \"print('STILL WORKS')\"")

    assert client.get("/health").json()["status"] == "ok"
    assert "STILL WORKS" in str(after["output"]), after["output"]


def test_a_backgrounded_command_does_not_outlive_its_session(
    client: httpx.Client, session: str
) -> None:
    """`cmd &` returns immediately and leaves the child running. Nothing should
    still be alive once the request that started it has been answered."""
    run(client, session, "sleep 300 &")

    alive = run(client, session, "pgrep -c -f 'sleep 300' || echo NONE")

    assert "NONE" in str(alive["output"]), alive["output"]


def test_one_session_cannot_reach_another(client: httpx.Client, session: str) -> None:
    """Both directions: the path check refuses the download, and the shell finds
    nothing because each session is its own directory."""
    other = f"other-{uuid.uuid4().hex[:8]}"
    write(client, other, "secret.txt", "another customer's draft")
    try:
        stolen = client.post(
            f"/v1/sessions/{session}/files/download",
            json={"paths": [f"../{other}/secret.txt"]},
        )
        listed = run(client, session, "ls secret.txt 2>&1 || echo ABSENT")
    finally:
        client.post(f"/v1/sessions/{other}")

    assert stolen.json()["results"][0]["error"] == "invalid_path"
    assert "ABSENT" in str(listed["output"])


def test_the_image_cannot_be_rewritten_by_what_it_runs(client: httpx.Client, session: str) -> None:
    result = run(client, session, "echo x > /app/planted.py 2>&1 || echo REFUSED")

    assert "REFUSED" in str(result["output"])


def test_release_wipes_what_the_session_wrote(client: httpx.Client) -> None:
    session = f"test-{uuid.uuid4().hex[:12]}"
    write(client, session, "draft.docx", "PK")

    client.post(f"/v1/sessions/{session}")
    after = client.post(f"/v1/sessions/{session}/files/download", json={"paths": ["draft.docx"]})

    assert after.json()["results"][0]["error"] == "file_not_found"


# -------------------------------------------------------------- toolchain --


def test_the_toolchain_the_skill_promises_is_present(client: httpx.Client, session: str) -> None:
    result = run(client, session, "brandkit doctor", timeout=SLOW_COMMAND_SECONDS)
    output = str(result["output"])

    assert result["exit_code"] == 0
    for probe in ("python:docx", "python:pptx", "python:openpyxl", "python:lxml", "python:PIL"):
        assert f"{probe}: ok" in output, output
    assert "binary:soffice: ok" in output, output
    assert "binary:pdftoppm: ok" in output, output


def test_a_generated_docx_converts_to_pdf_without_a_jre(client: httpx.Client, session: str) -> None:
    """No JRE is installed on purpose - it is ~180MB for filters this lane does
    not use. If a conversion ever needs one, it fails here rather than shipping
    a blank page."""
    write(client, session, "gen.py", GENERATE_DOCX)

    generated = run(client, session, "python3 gen.py")
    converted = run(
        client,
        session,
        f"{CONVERT_TO_PDF} && test -s out.pdf && echo CONVERTED",
        timeout=SLOW_COMMAND_SECONDS,
    )

    assert generated["exit_code"] == 0
    assert "CONVERTED" in str(converted["output"]), converted["output"]


def test_vietnamese_diacritics_survive_the_pdf(client: httpx.Client, session: str) -> None:
    """The failure this catches is not a missing glyph but a stacked one: `ế`
    rendered as `e` plus two loose marks reads as an ugly font, not as a bug,
    and ships."""
    generate_and_convert(client, session)

    extracted = run(client, session, "pdftotext out.pdf -")

    assert DIACRITICS in str(extracted["output"]), extracted["output"]


def test_a_pdf_page_can_be_rendered_to_an_image(client: httpx.Client, session: str) -> None:
    """The visual-audit loop is a later commit, but it is only possible if the
    renderer works, so the image proves it now."""
    generate_and_convert(client, session)

    rendered = run(client, session, "pdftoppm -jpeg -r 150 -f 1 -l 1 out.pdf page")
    fetched = client.post(f"/v1/sessions/{session}/files/download", json={"paths": ["page-1.jpg"]})

    assert rendered["exit_code"] == 0
    body = fetched.json()["results"][0]
    assert body["error"] is None
    assert base64.b64decode(body["content_b64"]).startswith(b"\xff\xd8\xff")


def test_pandoc_reads_the_text_back_out(client: httpx.Client, session: str) -> None:
    """How the number check sees what the document says rather than what the
    model claims it says."""
    write(client, session, "gen.py", GENERATE_DOCX)
    run(client, session, "python3 gen.py")

    extracted = run(client, session, "pandoc -t plain out.docx")

    assert "1.500.000" in str(extracted["output"])


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")
