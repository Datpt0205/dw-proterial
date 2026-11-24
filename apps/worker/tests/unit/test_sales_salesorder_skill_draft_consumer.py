"""The `sales.salesorder_pair.added` handler (ticket 66): the envelope's
tenancy and the payload's customer, handed to the drafter; nothing else. A
payload naming anything else, another tenant included, is undeliverable."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_learning import PAIR_ADDED
from dw_sales.application.salesorder_skill_drafts import DraftResult
from dw_worker.consumers.outbox import UndeliverableEventError
from dw_worker.consumers.sales_salesorder_skill_drafts import build_pair_added_handler

pytestmark = pytest.mark.unit


class _Drafter:
    def __init__(self) -> None:
        self.calls: list[tuple[SalesScope, str]] = []

    async def draft(self, scope: SalesScope, customer_code: str) -> DraftResult:
        self.calls.append((scope, customer_code))
        return DraftResult("not_needed", pairs=1, right_before=1)


def _event(payload: dict[str, object]) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(uuid.uuid4()),
        workspace_id=WorkspaceId(uuid.uuid4()),
        event_type=PAIR_ADDED,
        schema_version="1.0.0",
        aggregate_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        payload=payload,
    )


async def test_the_handler_drafts_in_the_events_own_scope() -> None:
    drafter = _Drafter()
    event = _event({"customer_code": "KHA", "pair_id": str(uuid.uuid4())})
    assert await build_pair_added_handler(drafter)(event) == "skill draft not_needed"
    assert drafter.calls == [
        (SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value)), "KHA")
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"customer_code": "kha", "pair_id": str(uuid.uuid4())},
        {"customer_code": "KHA", "pair_id": "not-a-uuid"},
        {"customer_code": "KHA", "pair_id": str(uuid.uuid4()), "tenant_id": "x"},
    ],
)
async def test_a_payload_naming_anything_else_is_undeliverable(payload: dict[str, object]) -> None:
    drafter = _Drafter()
    with pytest.raises(UndeliverableEventError):
        await build_pair_added_handler(drafter)(_event(payload))
    assert drafter.calls == []
