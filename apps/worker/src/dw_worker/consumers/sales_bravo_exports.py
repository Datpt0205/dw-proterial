"""A Bravo screen exported by Sales, read by the worker (Sales tickets 16, 03).

`BravoExportService.upload` keeps the file and writes one outbox event,
`sales.bravo_export.uploaded`, in the same transaction; this handler hands it
to `BravoExportReading.read`, which scans the file, has the reader sandbox
turn it into rows, gives them to the screen's reader (Design's result on a
YCBG, a sales order read back) and stores what became of each document.
Nothing is decided here: the payload is parsed, the tenancy taken from the
envelope.

A scanner or reader that did not answer raises, so the outbox delivers the
event again (bounded by its `max_attempts`); a reading is idempotent, an
export no longer queued is left alone. An export whose event was lost stays
queued, with its file, until the next upload of its workspace fails it.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["BravoExportReadingPort", "BravoExportUploadedPayload", "build_bravo_export_handler"]


class BravoExportUploadedPayload(BaseModel):
    """The body `BravoExportService.upload` writes (and ticket 16's upload
    wrote before it, under its old event type)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export_id: uuid.UUID


class BravoExportReadingPort(Protocol):
    async def read(self, scope: SalesScope, export_id: uuid.UUID) -> str: ...


def build_bravo_export_handler(reading: BravoExportReadingPort) -> EventHandler:
    """The handler to wire under `BRAVO_EXPORT_UPLOADED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = BravoExportUploadedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError.unparsable(exc) from None
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await reading.read(scope, payload.export_id)

    return handle
