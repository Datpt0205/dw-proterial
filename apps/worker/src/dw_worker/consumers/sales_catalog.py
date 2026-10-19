"""A master-data upload, read (Sales ticket 41).

`CatalogImportService.upload` keeps the file and writes one outbox event,
`sales.catalog.imported`, in the same transaction; this handler hands it to
`CatalogParsing.parse`, which scans the file, has the reader sandbox turn it
into rows and stores the import's records and rejected rows. Nothing is
decided here: the payload is parsed, the tenancy taken from the envelope.

A scanner or reader that did not answer raises, so the outbox delivers the
event again (bounded by its `max_attempts`); a parse is idempotent, an
import no longer queued is left alone.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["CatalogParsingPort", "ImportedPayload", "build_catalog_import_handler"]


class ImportedPayload(BaseModel):
    """The body `CatalogImportService.upload` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: uuid.UUID


class CatalogParsingPort(Protocol):
    async def parse(self, scope: SalesScope, snapshot_id: uuid.UUID) -> str: ...


def build_catalog_import_handler(parsing: CatalogParsingPort) -> EventHandler:
    """The handler to wire under `CATALOG_IMPORTED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = ImportedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError(f"payload does not parse: {exc}") from exc
        scope = SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value))
        return await parsing.parse(scope, payload.snapshot_id)

    return handle
