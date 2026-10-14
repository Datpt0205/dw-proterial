"""A decided run-less Sales approval reaches DW1 (Sales tickets 30 and 38).

The handler decides nothing: it parses the run-less decision's payload, takes
the tenancy from the envelope and the decider from the payload, and hands both
to the settlement. A refusal the settlement makes never changes on a retry, so
it is undeliverable rather than retried forever.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, InfrastructureError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.layouts import LAYOUT_DECIDED
from dw_sales.application.rules import RULES_DECIDED
from dw_worker.consumers.outbox import UndeliverableEventError
from dw_worker.consumers.sales_decisions import build_decided_handler

pytestmark = pytest.mark.unit

TENANT, WORKSPACE = uuid.UUID(int=0x51), uuid.UUID(int=0x52)
APPROVAL, DECIDER = uuid.UUID(int=0x53), uuid.UUID(int=0x54)


class _Settlement:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[tuple[uuid.UUID, AccessContext]] = []
        self.failure = failure

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> object:
        self.calls.append((approval_id, decider))
        if self.failure is not None:
            raise self.failure
        return None


def _decided(payload: dict[str, Any] | None = None) -> OutboxEvent:
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        event_type=LAYOUT_DECIDED,
        schema_version="1.0",
        aggregate_id=APPROVAL,
        occurred_at=datetime(2026, 10, 13, tzinfo=UTC),
        payload=payload
        if payload is not None
        else {
            "approval_id": str(APPROVAL),
            "decision_id": str(uuid.uuid4()),
            "outcome": "approved",
            "decided_by": str(DECIDER),
        },
    )


async def test_a_decision_is_settled_in_the_envelopes_tenancy_by_the_decider() -> None:
    settlement = _Settlement()

    handler = build_decided_handler(settlement, applied="layout decision applied")
    assert await handler(_decided()) == "layout decision applied"

    ((approval_id, decider),) = settlement.calls
    assert approval_id == APPROVAL
    assert (decider.tenant_id, decider.workspace_id, decider.principal_id) == (
        TENANT,
        WORKSPACE,
        DECIDER,
    )
    # Authorized where it was decided: the context carries no scope or role.
    assert decider.scopes == frozenset() and decider.roles == frozenset()


async def test_a_payload_naming_a_tenant_is_refused_before_anything_is_settled() -> None:
    body = dict(_decided().payload, tenant_id=str(uuid.uuid4()))
    settlement = _Settlement()

    with pytest.raises(UndeliverableEventError):
        await build_decided_handler(settlement, applied="x")(_decided(body))
    assert settlement.calls == []


async def test_a_refusal_is_undeliverable_and_an_outage_is_retried() -> None:
    refused = _Settlement(ConflictError("mẫu PO không còn chờ quyết định này"))
    with pytest.raises(UndeliverableEventError):
        await build_decided_handler(refused, applied="x")(_decided())

    down = _Settlement(InfrastructureError("database unavailable"))
    with pytest.raises(InfrastructureError):
        await build_decided_handler(down, applied="x")(_decided())


def test_the_worker_hands_every_layout_and_rules_decision_to_its_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wired with a database alone, mailbox or not: an event with no handler
    stays in the outbox, and the layout or the rule version would wait on its
    decision forever."""
    from test_worker import bare_settings

    import dw_worker.main as main

    seen: dict[str, object] = {}

    def capture(drain: object, handlers: dict[str, object], **_: object) -> object:
        seen.update(handlers)

        async def consume() -> None:
            return None

        return consume

    monkeypatch.setattr(main, "build_outbox_consumer", capture)
    main.build_registry(bare_settings(database_url="postgresql+asyncpg://dw:dw@localhost/dw"))

    assert LAYOUT_DECIDED in seen and RULES_DECIDED in seen
