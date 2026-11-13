"""The Sales mailbox with every attachment scanned and held to its name
before it is returned (ticket 25).

The scan sits at the one door every reader goes through, `InboxPort.read_attachment`:
`ScannedInbox` wraps the mailbox, so the intake, the quotation flow, a PO layout's
preview and the source view all receive bytes that were scanned, and none of them
can ask for bytes that were not. There is no second path to forget. The verdicts
and what each one raises are the platform's (`dw_platform.application.malware`).

**A file locked with a password is handed over locked** (ticket 17): marked
"encrypted: contents not scannable by ClamAV", as a `LockedContent` that
carries the text of the one mail it came with. That text, and nothing kept,
is where the reader sandbox's candidates come from each time the file is
opened (`dw_sales.domain.file_passwords`); the sandbox is the only place it is
opened, and its containment is what stands in for the scan nobody could make.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import Field

from dw_platform.application.malware import (
    AttachmentInfectedError,
    AttachmentRefusedError,
    FormatCheckPort,
    MalwareScanPort,
    ScanUnavailableError,
)
from dw_platform.domain.messages import AttachmentContent, InboundMessage
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.domain.file_passwords import password_candidates


class LockedContent(AttachmentContent):
    """An attachment locked with a password (module docstring): encrypted,
    its contents not scannable by ClamAV, read only in the reader sandbox.
    ``mail_text`` is the body of the message it is attached to, never shown
    and never dumped; the candidates are derived from it per opening."""

    mail_text: str = Field(repr=False, exclude=True)

    def passwords(self) -> tuple[str, ...]:
        """The candidates its mail carries, derived now (`password_candidates`)."""
        return password_candidates(self.mail_text)


@dataclass(frozen=True)
class ScannedInbox:
    """`InboxPort` over ``inner``, every attachment scanned, then checked to
    be what its name says, before it is returned, a locked one as a
    `LockedContent` (module docstring). Listing and reading messages read no
    file."""

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
        if self.formats.encrypted(content.data):
            # The scanner saw the container only: handed over locked, with
            # its own mail's text (module docstring).
            message = await self.inner.get_message(scope, message_id)
            return LockedContent(
                attachment=content.attachment,
                data=content.data,
                mail_text=message.body_text if message is not None else "",
            )
        return content
