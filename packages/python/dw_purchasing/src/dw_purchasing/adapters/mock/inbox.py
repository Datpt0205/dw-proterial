"""`InboxPort` over the fictional purchasing mailbox in `data/inbox.json`.

Fictional people and suppliers; the company's own domain is the one DW1's
mock uses (`seller.example`). Bound to the one demo scope whose mailbox it
stands in for: every other tenant and workspace sees an empty mailbox. A real
adapter reads the mailbox configured for the caller's tenant and workspace
(the mail drop, once it is the platform's: ADR 0013 decision 3).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from dw_platform.application.access_context import AccessContext
from dw_platform.domain.messages import InboundMessage

DATA_DIR: Final = Path(__file__).resolve().parent / "data"


class MockInbox:
    """Implements `InboxPort` for the demo scope (module docstring)."""

    def __init__(
        self, messages: Sequence[InboundMessage], *, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        by_id = {m.message_id: m for m in messages}
        if len(by_id) != len(messages):
            raise ValueError("a message id appears twice")
        self._messages = sorted(by_id.values(), key=lambda m: (m.received_at, m.message_id))
        self._scope = (tenant_id, workspace_id)

    @classmethod
    def load(cls, *, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> MockInbox:
        records = json.loads((DATA_DIR / "inbox.json").read_text(encoding="utf-8"))
        messages = [InboundMessage.model_validate(record) for record in records]
        return cls(messages, tenant_id=tenant_id, workspace_id=workspace_id)

    def _mine(self, context: AccessContext) -> bool:
        return (context.tenant_id, context.workspace_id) == self._scope

    async def list_messages(self, context: AccessContext) -> Sequence[InboundMessage]:
        return list(self._messages) if self._mine(context) else []

    async def get_message(self, context: AccessContext, message_id: str) -> InboundMessage | None:
        if not self._mine(context):
            return None
        return next((m for m in self._messages if m.message_id == message_id), None)
