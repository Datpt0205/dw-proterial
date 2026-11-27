"""A kept worked pair asks for its customer's SalesOrder skill to be drafted
(ticket 66).

`SalesOrderLearning.learn` keeps a pair and writes one outbox event,
`sales.salesorder_pair.added`, in the same transaction; this handler hands
the customer to `SalesOrderSkillDrafter.draft`, which fills the customer's
pairs with the skill in force and, where that does not reproduce them, asks
the model for a draft, checks and replays it, and proposes it for the head.
Nothing is decided here: the payload is parsed, the tenancy taken from the
envelope.

A draft is idempotent where it matters: a version already waiting for the
customer stops it, so an event delivered twice proposes once. A model that
did not answer proposes nothing and is not retried: the customer's next pair
asks again.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_skill_drafts import DraftResult
from dw_sales.domain.catalog import CustomerCode
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["PairAddedPayload", "SkillDraftPort", "build_pair_added_handler"]


class PairAddedPayload(BaseModel):
    """The body `SalesOrderLearning.learn` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_code: CustomerCode
    pair_id: uuid.UUID


class SkillDraftPort(Protocol):
    async def draft(self, scope: SalesScope, customer_code: str) -> DraftResult: ...


def build_pair_added_handler(drafter: SkillDraftPort) -> EventHandler:
    """The handler to wire under `PAIR_ADDED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = PairAddedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError.unparsable(exc) from None
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        result = await drafter.draft(scope, payload.customer_code)
        return f"skill draft {result.outcome}"

    return handle
