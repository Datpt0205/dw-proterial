"""A Bravo YCBG export, read for Design's results (Sales ticket 16).

`YcbgExportService.upload` keeps the file and writes one outbox event,
`sales.ycbg_export.uploaded`, in the same transaction; this handler hands it
to `YcbgExportReading.read`, which scans the file, has the reader sandbox turn
it into rows, records each Design result on the one case waiting on it, and
stores what became of each YCBG number. Nothing is decided here: the payload
is parsed, the tenancy taken from the envelope.

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

__all__ = ["YcbgExportReadingPort", "YcbgExportUploadedPayload", "build_ycbg_export_handler"]


class YcbgExportUploadedPayload(BaseModel):
    """The body `YcbgExportService.upload` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export_id: uuid.UUID


class YcbgExportReadingPort(Protocol):
    async def read(self, scope: SalesScope, export_id: uuid.UUID) -> str: ...


def build_ycbg_export_handler(reading: YcbgExportReadingPort) -> EventHandler:
    """The handler to wire under `YCBG_EXPORT_UPLOADED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = YcbgExportUploadedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError.unparsable(exc) from None
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await reading.read(scope, payload.export_id)

    return handle
