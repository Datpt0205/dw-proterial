"""A decided Bravo write reaches its settlement with the token the decision
signed (Sales ticket 53); the handler decides nothing itself."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.bravo_line_writes import BRAVO_WRITE_DECIDED
from dw_worker.consumers.bravo_writes import build_bravo_write_handler
from dw_worker.consumers.outbox import UndeliverableEventError

pytestmark = pytest.mark.unit

TENANT, WORKSPACE = uuid.UUID(int=0x61), uuid.UUID(int=0x62)
APPROVAL, DECIDER = uuid.UUID(int=0x63), uuid.UUID(int=0x64)


class _Settlement:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[tuple[uuid.UUID, AccessContext, str | None]] = []
        self.failure = failure

    async def settle(
        self, approval_id: uuid.UUID, decider: AccessContext, token: str | None
    ) -> object:
        self.calls.append((approval_id, decider, token))
        if self.failure is not None:
            raise self.failure
        return "written"


def _event(**over: Any) -> OutboxEvent:
    payload: dict[str, Any] = {
        "approval_id": str(APPROVAL),
        "decision_id": str(uuid.uuid4()),
        "outcome": "approved",
        "decided_by": str(DECIDER),
        "stamp": {"token": "a.b"},
    }
    payload.update(over)
    return OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        event_type=BRAVO_WRITE_DECIDED,
        schema_version="1.0",
        aggregate_id=APPROVAL,
        occurred_at=datetime(2026, 11, 21, tzinfo=UTC),
        payload={k: v for k, v in payload.items() if v is not None},
    )


async def test_the_token_and_the_decider_reach_the_settlement() -> None:
    settlement = _Settlement()

    said = await build_bravo_write_handler(settlement)(_event())

    [(approval, decider, token)] = settlement.calls
    assert (approval, decider.principal_id, decider.tenant_id, token) == (
        APPROVAL,
        DECIDER,
        TENANT,
        "a.b",
    )
    assert decider.scopes == frozenset() and said == "bravo write written"


async def test_a_rejection_carries_no_token() -> None:
    settlement = _Settlement()

    await build_bravo_write_handler(settlement)(_event(outcome="rejected", stamp=None))

    assert settlement.calls[0][2] is None


@pytest.mark.parametrize(
    "over",
    [{"stamp": {"token": "a.b", "bravo_user_id": 1}}, {"decided_by": "nobody"}, {"extra": 1}],
    ids=["stamp_with_more", "bad_decider", "unknown_key"],
)
async def test_a_payload_outside_the_shape_is_undeliverable(over: dict[str, Any]) -> None:
    settlement = _Settlement()

    with pytest.raises(UndeliverableEventError):
        await build_bravo_write_handler(settlement)(_event(**over))
    assert settlement.calls == []


async def test_a_refusal_is_undeliverable_and_a_gateway_failure_is_retried() -> None:
    with pytest.raises(UndeliverableEventError):
        await build_bravo_write_handler(_Settlement(ConflictError("settled")))(_event())
    with pytest.raises(OSError):
        await build_bravo_write_handler(_Settlement(OSError("gateway down")))(_event())
