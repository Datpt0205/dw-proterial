"""The memory handler: what it refuses, and whose memory a stored fact becomes.

The idempotency itself is proven against a real database in
`dw_memory/tests/integration` — a second delivery has to find the first row, and
only Postgres can say whether it does. What is provable here is everything
around that: which errors are worth retrying, and where tenancy comes from.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_memory.contracts import MemoryType, WriteDecision
from dw_memory.policy import MemoryCandidate, PolicyOutcome
from dw_memory.service import ProposalResult
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_worker.consumers.memory import (
    MEMORY_CANDIDATE_PROPOSED,
    build_memory_handler,
    memory_handlers,
)
from dw_worker.consumers.outbox import UndeliverableEventError

pytestmark = pytest.mark.unit

TENANT = uuid.UUID(int=0xA1)
WORKSPACE = uuid.UUID(int=0xA2)
ACTOR = uuid.UUID(int=0xA3)
RUN = uuid.UUID(int=0xA4)


class _Recorder:
    """Captures the call rather than storing anything."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def propose(
        self,
        candidate: MemoryCandidate,
        context: AccessContext,
        *,
        created_by_run_id: uuid.UUID,
        idempotency_key: uuid.UUID | None = None,
    ) -> ProposalResult:
        self.calls.append(
            {
                "candidate": candidate,
                "tenant_id": context.tenant_id,
                "workspace_id": context.workspace_id,
                "principal_id": context.principal_id,
                "run_id": created_by_run_id,
                "idempotency_key": idempotency_key,
            }
        )
        return ProposalResult(
            candidate_id=uuid.uuid4(),
            outcome=PolicyOutcome(decision=WriteDecision.AUTO_WRITE, reason="ok"),
            item=None,
        )


def _payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": str(RUN),
        "actor_id": str(ACTOR),
        "candidate": {
            "worker_id": "demo",
            "memory_type": MemoryType.COMMITMENT.value,
            "content": "Anh An cam kết gửi hợp đồng.",
            "confidence": 0.9,
            "provenance_refs": [],
        },
    }
    body.update(overrides)
    return body


def _event(
    payload: dict[str, Any] | None = None, *, event_id: uuid.UUID | None = None
) -> OutboxEvent:
    return OutboxEvent(
        id=event_id or uuid.uuid4(),
        tenant_id=TenantId(TENANT),
        workspace_id=WorkspaceId(WORKSPACE),
        event_type=MEMORY_CANDIDATE_PROPOSED,
        schema_version="1.0",
        aggregate_id=RUN,
        occurred_at=datetime(2026, 9, 18, tzinfo=UTC),
        payload=payload if payload is not None else _payload(),
    )


async def test_the_event_id_is_what_makes_a_redelivery_decide_once() -> None:
    """At-least-once delivery plus a non-idempotent write is a duplicate memory
    per retry. The key has to be the event's own id — anything generated per call
    is a fresh key on the second attempt."""
    recorder = _Recorder()
    event = _event()

    await build_memory_handler(recorder)(event)

    assert recorder.calls[0]["idempotency_key"] == event.id


async def test_tenancy_comes_from_the_envelope_not_the_payload() -> None:
    """What produces this event is a model's output one layer up. A payload that
    could name its own tenant would let it choose whose memory a fact becomes."""
    recorder = _Recorder()

    await build_memory_handler(recorder)(_event())

    assert recorder.calls[0]["tenant_id"] == TENANT
    assert recorder.calls[0]["workspace_id"] == WORKSPACE


async def test_a_payload_that_names_a_tenant_is_refused_outright() -> None:
    """Not ignored — refused. A field this build does not know is more likely a
    newer schema than noise, and dropping it silently stores a memory missing
    whatever the sender meant to send."""
    handler = build_memory_handler(_Recorder())

    with pytest.raises(UndeliverableEventError):
        await handler(_event(_payload(tenant_id=str(uuid.uuid4()))))


async def test_a_malformed_payload_is_undeliverable_rather_than_retried() -> None:
    """It cannot become valid by being tried again. Raising the ordinary kind of
    error here would burn the attempt budget in a loop, and the reason would
    never be written down."""
    handler = build_memory_handler(_Recorder())

    with pytest.raises(UndeliverableEventError):
        await handler(_event({"schema_version": "1.0"}))


async def test_a_storage_failure_stays_retryable() -> None:
    """The other half of the same decision: a database that is down IS worth
    trying again, so it must NOT be reported as undeliverable — that would throw
    the memory away."""

    class _Broken(_Recorder):
        async def propose(self, *args: Any, **kwargs: Any) -> ProposalResult:
            raise TimeoutError("database gone")

    handler = build_memory_handler(_Broken())

    with pytest.raises(TimeoutError):
        await handler(_event())


def test_the_worker_wires_this_event_and_only_this_one() -> None:
    """Pins what the composition root turned on. An effect that reacts to an
    ambient record event — "an account was created" — is the shape that bought a
    paid model call per row of a bulk import; this one reacts to an event a run
    emits deliberately when it has something to remember."""
    assert sorted(memory_handlers(_Recorder())) == [MEMORY_CANDIDATE_PROPOSED]
