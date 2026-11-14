"""The `sales.salesorder_example.requested` handler (ticket 38): the
envelope's tenancy and the payload's example, handed to the learning;
nothing else. A payload naming anything else is undeliverable."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_learning import EXAMPLE_REQUESTED
from dw_worker.consumers.outbox import UndeliverableEventError
from dw_worker.consumers.sales_salesorder_examples import build_example_handler

pytestmark = pytest.mark.unit


class _Learning:
    def __init__(self) -> None:
        self.calls: list[tuple[SalesScope, uuid.UUID]] = []

    async def learn(self, scope: SalesScope, example_id: uuid.UUID) -> str:
        self.calls.append((scope, example_id))
        return "example replayed"


def _event(payload: dict[str, object]) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(uuid.uuid4()),
        workspace_id=WorkspaceId(uuid.uuid4()),
        event_type=EXAMPLE_REQUESTED,
        schema_version="1.0.0",
        aggregate_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        payload=payload,
    )


async def test_the_handler_learns_in_the_events_own_scope() -> None:
    learning = _Learning()
    example_id = uuid.uuid4()
    event = _event({"example_id": str(example_id)})
    assert await build_example_handler(learning)(event) == "example replayed"
    assert learning.calls == [
        (
            SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value)),
            example_id,
        )
    ]


@pytest.mark.parametrize(
    "payload",
    [{}, {"example_id": "not-a-uuid"}, {"example_id": str(uuid.uuid4()), "tenant_id": "x"}],
)
async def test_a_payload_naming_anything_else_is_undeliverable(payload: dict[str, object]) -> None:
    learning = _Learning()
    with pytest.raises(UndeliverableEventError):
        await build_example_handler(learning)(_event(payload))
    assert learning.calls == []
