"""The `sales.catalog.imported` handler (Sales ticket 41): the envelope's
tenancy and the payload's snapshot, handed to the parse; nothing else."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.catalog_imports import CATALOG_IMPORTED
from dw_sales.application.ports import SalesScope
from dw_worker.consumers.outbox import UndeliverableEventError
from dw_worker.consumers.sales_catalog import build_catalog_import_handler

pytestmark = pytest.mark.unit


class _Parsing:
    def __init__(self) -> None:
        self.calls: list[tuple[SalesScope, uuid.UUID]] = []

    async def parse(self, scope: SalesScope, snapshot_id: uuid.UUID) -> str:
        self.calls.append((scope, snapshot_id))
        return "import parsed"


def _event(payload: dict[str, object]) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(uuid.uuid4()),
        workspace_id=WorkspaceId(uuid.uuid4()),
        event_type=CATALOG_IMPORTED,
        schema_version="1.0.0",
        aggregate_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        payload=payload,
    )


async def test_the_handler_parses_the_snapshot_in_the_events_own_scope() -> None:
    parsing = _Parsing()
    snapshot_id = uuid.uuid4()
    event = _event({"snapshot_id": str(snapshot_id)})
    assert await build_catalog_import_handler(parsing)(event) == "import parsed"
    assert parsing.calls == [
        (
            SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value)),
            snapshot_id,
        )
    ]


async def test_a_payload_that_names_anything_else_is_undeliverable() -> None:
    parsing = _Parsing()
    with pytest.raises(UndeliverableEventError):
        await build_catalog_import_handler(parsing)(
            _event({"snapshot_id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4())})
        )
    assert parsing.calls == []
