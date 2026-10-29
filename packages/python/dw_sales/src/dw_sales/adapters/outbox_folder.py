"""`OutboxFolderPort` over the share's folders: one folder per mailbox,
named by its address, as each person's Power Automate flow sees it
(`infra/onprem/README.md`, "Sending mail from each PIC's own mailbox", says
how a flow is set up).

    <root>/<mailbox>/outbox/<job>.json          the job the flow sends
    <root>/<mailbox>/outbox/files/<job>/<name>  the files it attaches
    <root>/<mailbox>/receipts/<job>.json        {"status": "sent" | "failed"}
    <root>/<mailbox>/receipts/done/<job>.json   a receipt DW1 has read

A mailbox with no `outbox` folder is not connected: its person's flow is not
set up. Files are written to a temporary name and renamed, the job last, so
a flow that sees a job finds its files. A receipt is read as a small JSON
object and nothing else: anything unreadable counts as failed, never as sent.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from dw_sales.application.outbound_mail import Receipt

logger = logging.getLogger("dw_sales.outbox_folder")

_RECEIPT_MAX_BYTES: Final = 4096
_SAFE_NAME: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_ ()"
)


def _safe(name: str) -> str:
    """A file name the share takes: letters, digits and a few marks."""
    kept = "".join(c if c in _SAFE_NAME else "_" for c in name).strip(" .")
    return kept[:120] or "attachment"


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_bytes(data)
    os.replace(temporary, path)


@dataclass(frozen=True)
class FolderOutbox:
    """Implements `OutboxFolderPort`."""

    root: Path

    def _box(self, mailbox: str) -> Path:
        return self.root / mailbox.lower()

    def connected(self, mailbox: str) -> bool:
        return (self._box(mailbox) / "outbox").is_dir()

    def write(
        self, mailbox: str, name: str, job: bytes, attachments: Sequence[tuple[str, bytes]]
    ) -> None:
        outbox = self._box(mailbox) / "outbox"
        for file_name, data in attachments:
            _atomic(outbox / "files" / name / _safe(file_name), data)
        _atomic(outbox / f"{name}.json", job)

    def receipts(self) -> Sequence[Receipt]:
        found: list[Receipt] = []
        if not self.root.is_dir():
            return found
        for box in sorted(p for p in self.root.iterdir() if p.is_dir()):
            folder = box / "receipts"
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                found.append(Receipt(mailbox=box.name, name=path.stem, status=_status(path)))
        return found

    def forget(self, receipt: Receipt) -> None:
        folder = self._box(receipt.mailbox) / "receipts"
        source = folder / f"{receipt.name}.json"
        if source.exists():
            (folder / "done").mkdir(exist_ok=True)
            os.replace(source, folder / "done" / source.name)


def _status(path: Path) -> Literal["sent", "failed"]:
    """``sent`` only when the receipt says exactly that."""
    try:
        if path.stat().st_size > _RECEIPT_MAX_BYTES:
            return "failed"
        said = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return "failed"
    return "sent" if isinstance(said, dict) and said.get("status") == "sent" else "failed"


@dataclass(frozen=True)
class FakeFlow:
    """A stand-in for the people's Power Automate flows, for tests and the
    local demo only: every job in a connected outbox is "sent" (nothing leaves
    the machine), receipted, and kept under `outbox/sent/` to look at. The
    worker refuses it in a deployed profile."""

    root: Path
    # What the flow answers: "sent", or "failed" to try the failure path.
    answer: str = "sent"

    def run(self) -> int:
        """Each job waiting in every outbox receipted once; how many."""
        handled = 0
        if not self.root.is_dir():
            return handled
        for box in sorted(p for p in self.root.iterdir() if p.is_dir()):
            outbox = box / "outbox"
            if not outbox.is_dir():
                continue
            for job in sorted(outbox.glob("*.json")):
                receipts = box / "receipts"
                receipts.mkdir(exist_ok=True)
                (receipts / job.name).write_text(
                    json.dumps({"status": self.answer}), encoding="utf-8"
                )
                (outbox / "sent").mkdir(exist_ok=True)
                os.replace(job, outbox / "sent" / job.name)
                handled += 1
        return handled
