"""The `sales.rule_draft.requested` handler ("Tạo từ tệp mẫu"): the
envelope's tenancy and the payload's draft, handed to the drafting; nothing
else. And the sweep lane: every workspace due is swept, one failing costs the
others nothing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.ports import SalesScope
from dw_sales.application.rule_drafts import RULE_DRAFT_REQUESTED, Swept
from dw_worker.consumers.outbox import UndeliverableEventError
from dw_worker.consumers.sales_rule_drafts import (
    build_rule_draft_handler,
    build_rule_draft_sweep_consumer,
)

pytestmark = pytest.mark.unit


class _Drafting:
    def __init__(self) -> None:
        self.calls: list[tuple[SalesScope, uuid.UUID]] = []

    async def draft(self, scope: SalesScope, draft_id: uuid.UUID) -> str:
        self.calls.append((scope, draft_id))
        return "draft ready"


def _event(payload: dict[str, object]) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(uuid.uuid4()),
        workspace_id=WorkspaceId(uuid.uuid4()),
        event_type=RULE_DRAFT_REQUESTED,
        schema_version="1.0.0",
        aggregate_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        payload=payload,
    )


async def test_the_handler_drafts_in_the_events_own_scope() -> None:
    drafting = _Drafting()
    draft_id = uuid.uuid4()
    event = _event({"draft_id": str(draft_id)})
    assert await build_rule_draft_handler(drafting)(event) == "draft ready"
    assert drafting.calls == [
        (
            SalesScope(TenantId(event.tenant_id.value), WorkspaceId(event.workspace_id.value)),
            draft_id,
        )
    ]


async def test_a_payload_that_names_anything_else_is_undeliverable() -> None:
    drafting = _Drafting()
    with pytest.raises(UndeliverableEventError):
        await build_rule_draft_handler(drafting)(
            _event({"draft_id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4())})
        )
    assert drafting.calls == []


def _scope() -> SalesScope:
    return SalesScope(TenantId(uuid.uuid4()), WorkspaceId(uuid.uuid4()))


class _Sweep:
    def __init__(self, scopes: list[SalesScope], failing: SalesScope) -> None:
        self.scopes, self.failing = scopes, failing
        self.swept: list[SalesScope] = []

    async def due(self) -> list[SalesScope]:
        return self.scopes

    async def sweep(self, scope: SalesScope) -> Swept:
        if scope == self.failing:
            raise RuntimeError("one workspace's database row is broken")
        self.swept.append(scope)
        return Swept(expired=1, pruned=0)


async def test_the_sweep_lane_sweeps_every_workspace_due_past_one_that_fails() -> None:
    first, broken, last = _scope(), _scope(), _scope()
    sweep = _Sweep([first, broken, last], failing=broken)
    await build_rule_draft_sweep_consumer(sweep)()
    assert sweep.swept == [first, last]
