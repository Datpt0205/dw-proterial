"""A worked example a customer's SalesOrder rules are learned from (ticket 38).

`SalesOrderExamples.request` keeps the pair and writes one outbox event,
`sales.salesorder_example.requested`, in the same transaction; this handler
hands it to `SalesOrderLearning.learn`, which scans both files, reads the PO
the normal way and the PIC's file in the reader sandbox, asks the model
through the one-call door where the layout alone does not reproduce the
file, verifies and replays the answer, and stores the outcome. Nothing is
decided here: the payload is parsed, the tenancy taken from the envelope.

A scanner or reader that did not answer raises, so the outbox delivers the
event again (bounded by its `max_attempts`); a learning is idempotent, an
example no longer queued is left alone. What no request comes for: an
example whose event was lost stays queued, with its files, until the next
request of its workspace drops the ones older than `KEPT_FOR` never sent.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["ExampleRequestedPayload", "SalesOrderLearningPort", "build_example_handler"]


class ExampleRequestedPayload(BaseModel):
    """The body `SalesOrderExamples.request` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    example_id: uuid.UUID


class SalesOrderLearningPort(Protocol):
    async def learn(self, scope: SalesScope, example_id: uuid.UUID) -> str: ...


def build_example_handler(learning: SalesOrderLearningPort) -> EventHandler:
    """The handler to wire under `EXAMPLE_REQUESTED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = ExampleRequestedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError.unparsable(exc) from None
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await learning.learn(scope, payload.example_id)

    return handle
