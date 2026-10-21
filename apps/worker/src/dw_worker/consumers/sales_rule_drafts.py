"""A company's template, drafted into a rule version ("Tạo từ tệp mẫu").

`RuleDraftService.request` keeps the file and writes one outbox event,
`sales.rule_draft.requested`, in the same transaction; this handler hands it
to `RuleDrafting.draft`, which scans the file, has the reader sandbox open
its sheets, asks the model through the one-call door and stores the draft.
Nothing is decided here: the payload is parsed, the tenancy taken from the
envelope.

A scanner or reader that did not answer raises, so the outbox delivers the
event again (bounded by its `max_attempts`); a draft is idempotent, one no
longer queued is left alone.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["DraftRequestedPayload", "RuleDraftingPort", "build_rule_draft_handler"]


class DraftRequestedPayload(BaseModel):
    """The body `RuleDraftService.request` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: uuid.UUID


class RuleDraftingPort(Protocol):
    async def draft(self, scope: SalesScope, draft_id: uuid.UUID) -> str: ...


def build_rule_draft_handler(drafting: RuleDraftingPort) -> EventHandler:
    """The handler to wire under `RULE_DRAFT_REQUESTED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = DraftRequestedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError(f"payload does not parse: {exc}") from exc
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await drafting.draft(scope, payload.draft_id)

    return handle
