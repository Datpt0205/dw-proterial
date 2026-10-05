"""`InboxPort` over the fictional mailbox in `data/inbox.json` and `attachments/`."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict

from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR, attachment_path, read_records
from dw_sales.application.ports import SalesScope
from dw_sales.domain.messages import (
    Attachment,
    AttachmentContent,
    EmailAddress,
    InboundMessage,
    MailAuthentication,
)


class _AttachmentFixture(BaseModel):
    """An attachment as the fixture lists it: no size, no digest.

    Those belong to the bytes and are computed from the file when the inbox
    loads; a digest typed into the fixture would be a second copy that goes
    stale the first time the attachments are regenerated.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attachment_id: str
    name: str
    media_type: str


class _MessageFixture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    sender: EmailAddress
    recipients: tuple[EmailAddress, ...] = ()
    subject: str
    received_at: AwareDatetime
    body_text: str
    attachments: tuple[_AttachmentFixture, ...] = ()
    # Required here although the message model defaults it to "unverified":
    # a fixture states what the mail system concluded, so a scenario never
    # depends on a default nobody wrote down.
    authentication: MailAuthentication


class MockInbox:
    """Implements `InboxPort` for a demo deployment.

    Serves the same fictional mailbox to every scope; a real adapter reads the
    mailbox configured for the scope's tenant and workspace. Attachment bytes
    are held in memory: the fixture set is a few hundred kilobytes.
    """

    def __init__(
        self, messages: Sequence[InboundMessage], contents: dict[tuple[str, str], bytes]
    ) -> None:
        by_id: dict[str, InboundMessage] = {}
        for message in messages:
            if message.message_id in by_id:
                raise ValueError(f"message id {message.message_id!r} appears twice")
            by_id[message.message_id] = message
        for message in by_id.values():
            for attachment in message.attachments:
                data = contents.get((message.message_id, attachment.attachment_id))
                if data is None:
                    raise ValueError(
                        f"message {message.message_id} lists {attachment.attachment_id}"
                        " with no content"
                    )
                # Fails here, not on first read, when the bytes disagree with
                # the description the message carries.
                AttachmentContent(attachment=attachment, data=data)
        self._messages = tuple(sorted(by_id.values(), key=lambda m: m.received_at))
        self._by_id = by_id
        self._contents = dict(contents)

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR, attachments_dir: Path = ATTACHMENTS_DIR) -> MockInbox:
        messages: list[InboundMessage] = []
        contents: dict[tuple[str, str], bytes] = {}
        for fixture in read_records(data_dir / "inbox.json", _MessageFixture):
            attachments: list[Attachment] = []
            for listed in fixture.attachments:
                data = attachment_path(
                    attachments_dir, fixture.message_id, listed.name
                ).read_bytes()
                attachments.append(
                    Attachment(
                        attachment_id=listed.attachment_id,
                        name=listed.name,
                        media_type=listed.media_type,
                        size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                )
                contents[(fixture.message_id, listed.attachment_id)] = data
            messages.append(
                InboundMessage(
                    message_id=fixture.message_id,
                    sender=fixture.sender,
                    recipients=fixture.recipients,
                    subject=fixture.subject,
                    received_at=fixture.received_at,
                    body_text=fixture.body_text,
                    attachments=tuple(attachments),
                    authentication=fixture.authentication,
                )
            )
        return cls(messages, contents)

    async def list_messages(self, scope: SalesScope) -> Sequence[InboundMessage]:
        return self._messages

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        return self._by_id.get(message_id)

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        message = self._by_id.get(message_id)
        attachment = message.attachment(attachment_id) if message is not None else None
        if attachment is None:
            return None
        return AttachmentContent(
            attachment=attachment, data=self._contents[(message_id, attachment_id)]
        )
