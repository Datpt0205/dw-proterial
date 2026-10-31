"""The share's outbox folders (sales' outbound mail, lifted by docs/adr/0013):
a job is written with its files first, a receipt counts as sent only when it
says exactly that, and a sender's file name cannot leave the job's folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dw_platform.adapters.outbox_folder import FakeFlow, FolderOutbox
from dw_platform.application.outbox_folder import Receipt

pytestmark = pytest.mark.unit

BOX = "Pic@Example.com"


def _connected(root: Path) -> FolderOutbox:
    (root / BOX.lower() / "outbox").mkdir(parents=True)
    return FolderOutbox(root)


def test_a_mailbox_without_an_outbox_folder_is_not_connected(tmp_path: Path) -> None:
    assert not FolderOutbox(tmp_path).connected(BOX)
    assert _connected(tmp_path).connected(BOX)


def test_the_job_and_its_files_are_written_and_a_name_cannot_climb_out(tmp_path: Path) -> None:
    outbox = _connected(tmp_path)
    outbox.write(BOX, "job-1", b"{}", [("../../evil.exe", b"x"), ("báo giá.pdf", b"y")])

    folder = tmp_path / BOX.lower() / "outbox"
    assert (folder / "job-1.json").read_bytes() == b"{}"
    written = sorted(p.name for p in (folder / "files" / "job-1").iterdir())
    assert written == ["_.._evil.exe", "b_o gi_.pdf"]
    assert not list(folder.rglob("*.part"))


@pytest.mark.parametrize(
    ("content", "status"),
    [
        (json.dumps({"status": "sent"}), "sent"),
        (json.dumps({"status": "failed"}), "failed"),
        (json.dumps({"status": "SENT"}), "failed"),
        (json.dumps(["sent"]), "failed"),
        ("not json", "failed"),
        (json.dumps({"status": "sent", "pad": "x" * 5000}), "failed"),
    ],
)
def test_a_receipt_is_sent_only_when_it_says_exactly_that(
    tmp_path: Path, content: str, status: str
) -> None:
    receipts = tmp_path / "box" / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "job-1.json").write_text(content, encoding="utf-8")

    assert FolderOutbox(tmp_path).receipts() == [Receipt("box", "job-1", status)]  # type: ignore[arg-type]


def test_a_read_receipt_is_moved_aside_and_not_read_again(tmp_path: Path) -> None:
    outbox = _connected(tmp_path)
    outbox.write(BOX, "job-1", b"{}", [])
    assert FakeFlow(tmp_path).run() == 1

    (receipt,) = outbox.receipts()
    assert receipt == Receipt(BOX.lower(), "job-1", "sent")
    outbox.forget(receipt)
    assert outbox.receipts() == []
