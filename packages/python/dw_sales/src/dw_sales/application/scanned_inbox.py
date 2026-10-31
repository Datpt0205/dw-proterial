"""The Sales mailbox with every attachment scanned and held to its name
before it is returned (ticket 25).

The scan sits at the one door every reader goes through, `InboxPort.read_attachment`:
`ScannedInbox` wraps the mailbox, so the intake, the quotation flow, a PO layout's
preview and the source view all receive bytes that were scanned, and none of them
can ask for bytes that were not. There is no second path to forget. The verdicts
and what each one raises are the platform's (`dw_platform.application.malware`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dw_platform.application.malware import (
    AttachmentInfectedError,
    AttachmentRefusedError,
    FormatCheckPort,
    MalwareScanPort,
    ScanUnavailableError,
)
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.domain.messages import AttachmentContent, InboundMessage


@dataclass(frozen=True)
class ScannedInbox:
    """`InboxPort` over ``inner``, every attachment scanned, then checked to
    be what its name says, before it is returned (module docstring). Listing
    and reading messages read no file."""

    inner: InboxPort
    scanner: MalwareScanPort
    formats: FormatCheckPort

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]:
        return await self.inner.list_messages(scope)

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        return await self.inner.get_message(scope, message_id)

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        content = await self.inner.read_attachment(scope, message_id, attachment_id)
        if content is None:
            return None
        verdict = await self.scanner.scan(content.data)
        match verdict.outcome:
            case "clean":
                pass
            case "infected":
                raise AttachmentInfectedError(
                    message_id, attachment_id, verdict.signature or "unknown"
                )
            case _:
                raise ScanUnavailableError(message_id, attachment_id, verdict.reason or "no answer")
        # Scanned clean; then what it is, by its bytes, against its name.
        if (reason := self.formats.refusal(content.attachment.name, content.data)) is not None:
            raise AttachmentRefusedError(message_id, attachment_id, reason)
        return content
