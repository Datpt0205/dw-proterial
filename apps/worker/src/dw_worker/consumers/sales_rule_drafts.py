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

The lane of the same name (`RULE_DRAFT_LANE`) is what no request has to come
for: every `INTERVAL_SECONDS` it asks which workspaces have a draft due and
hands each to `RuleDraftSweep.sweep`, which fails a draft its event lost and
drops the old ones, with their files. One workspace's failure costs the
others nothing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.rule_drafts import Swept
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = [
    "INTERVAL_SECONDS",
    "DraftRequestedPayload",
    "RuleDraftSweepPort",
    "RuleDraftingPort",
    "build_rule_draft_handler",
    "build_rule_draft_sweep_consumer",
]

logger = logging.getLogger("dw_worker.sales_rule_drafts")

# Ten minutes: a lost draft is failed within `STALE_AFTER` and this, and a
# tick with nothing due is one read.
INTERVAL_SECONDS = 600.0


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
            raise UndeliverableEventError.unparsable(exc) from None
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await drafting.draft(scope, payload.draft_id)

    return handle


class RuleDraftSweepPort(Protocol):
    """`RuleDraftSweep`: the workspaces with a draft due, and one swept."""

    async def due(self) -> Sequence[SalesScope]: ...

    async def sweep(self, scope: SalesScope) -> Swept: ...


def build_rule_draft_sweep_consumer(sweep: RuleDraftSweepPort) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        for scope in await sweep.due():
            try:
                swept = await sweep.sweep(scope)
            except Exception:
                # Broad on purpose, like the loop's own: the next workspace
                # is still swept.
                logger.exception("sales_rule_drafts: the sweep failed in one workspace")
                continue
            if swept.expired or swept.pruned:
                logger.info(
                    "sales_rule_drafts: %d draft(s) failed as stale, %d dropped",
                    swept.expired,
                    swept.pruned,
                )

    return consume
