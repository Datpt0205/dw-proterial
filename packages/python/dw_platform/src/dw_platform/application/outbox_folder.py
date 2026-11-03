"""Sending from a person's own mailbox through a shared folder: the port
(sales' outbound mail, lifted by docs/adr/0013 so any context can hand a mail
to the flow that sends it as the person who pressed).

The share holds one folder per mailbox; each person's Power Automate flow sends
what is written there and writes a receipt back (`dw_platform.adapters.outbox_folder`).
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class Receipt:
    """What a flow wrote back for one job."""

    mailbox: str
    name: str
    status: Literal["sent", "failed"]


def flow_job(
    *,
    job_id: str,
    mailbox: str,
    to: Sequence[str],
    cc: Sequence[str],
    subject: str,
    body_text: str,
    attachments: Sequence[str],
) -> bytes:
    """The job a person's flow reads (`infra/onprem/README.md`, "Sending mail
    from each PIC's own mailbox"): one flow serves every context, so its
    fields have this one owner. The body is text, sent as HTML for Outlook."""
    job = {
        "job": job_id,
        "from": mailbox,
        "to": ";".join(to),
        "cc": ";".join(cc),
        "subject": subject,
        "body_html": html.escape(body_text).replace("\n", "<br>"),
        "attachments": list(attachments),
    }
    return json.dumps(job, ensure_ascii=False, indent=1).encode("utf-8")


class OutboxFolderPort(Protocol):
    """The share's outbox folders, one per mailbox (`dw_platform.adapters.outbox_folder`)."""

    def connected(self, mailbox: str) -> bool:
        """Whether ``mailbox`` has an outbox folder: its flow is set up."""
        ...

    def write(
        self, mailbox: str, name: str, job: bytes, attachments: Sequence[tuple[str, bytes]]
    ) -> None:
        """The job and its files, the job last: a flow sees it complete."""
        ...

    def receipts(self) -> Sequence[Receipt]: ...

    def forget(self, receipt: Receipt) -> None:
        """Move a handled receipt aside: it is not read again."""
        ...
