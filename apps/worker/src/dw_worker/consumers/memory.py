"""Remembering happens after the answer, not during it.

A run that stops to decide what is worth keeping is a run the person is waiting
on. So a workflow announces a candidate on the outbox when its turn is over and
this handler stores it on the worker — the foreground path pays nothing, and a
memory that fails to store fails where a retry is cheap instead of in front of a
customer.

**At-least-once is the whole design problem.** The outbox counts an attempt at
claim time and marks the row afterwards, so a process that dies between those
two points delivers the same event again. Without a key, that is a second
identical memory; with two retries, a third. The event's own id is passed as the
idempotency key, which makes the candidate row's primary key deterministic — the
second delivery finds the first decision and returns it.

**A malformed payload is not retried.** It cannot become valid by being tried
again, so it raises `UndeliverableEventError` and the reason is recorded rather
than burning the attempt budget in a loop. That distinction is the one thing a
handler must get right here: a database that is down IS worth retrying, and
raising the wrong kind of error for it would throw the memory away.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_memory.policy import MemoryCandidate
from dw_memory.service import ProposalResult
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = [
    "MEMORY_CANDIDATE_PROPOSED",
    "MemoryCandidatePayload",
    "build_memory_handler",
    "memory_handlers",
]

MEMORY_CANDIDATE_PROPOSED = "memory.candidate_proposed"
"""What a workflow announces when a turn produced something worth keeping."""

# `AccessContext` requires a plan and this path reads none, so rather than
# borrow a real one — which a later entitlement check would honour — the
# context carries a plan the catalog does not contain. `has_feature` answers
# False for it and `runs_per_day` answers 0, so anything that starts reading
# the plan here refuses rather than grants.
_NO_PLAN = "background"


class MemoryProposePort(Protocol):
    """`MemoryService.propose`, stated by its consumer."""

    async def propose(
        self,
        candidate: MemoryCandidate,
        context: AccessContext,
        *,
        created_by_run_id: uuid.UUID,
        idempotency_key: uuid.UUID | None = None,
    ) -> ProposalResult: ...


class MemoryCandidatePayload(BaseModel):
    """The event body, validated before anything reaches the database.

    `extra="forbid"`: an event carrying a field this build does not know is more
    likely a newer schema than a harmless extra, and silently dropping it would
    store a memory that is missing whatever the sender thought it was sending.

    Deliberately NOT carrying tenant or workspace: those come off the event's own
    envelope, which the emitting transaction wrote. A payload that could name its
    own tenant would let whatever produced the event choose whose memory it
    becomes — and what produces it is a model's output, one layer up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    run_id: uuid.UUID
    actor_id: uuid.UUID
    candidate: MemoryCandidate


def _access_for(event: OutboxEvent, payload: MemoryCandidatePayload) -> AccessContext:
    """Tenancy from the envelope, identity from the payload's actor.

    The run's own scopes are not replayed: this is a background write of a fact
    the run already produced, not a chance to act as that user again. Memory has
    no scope gate of its own — the policy and the evidence check are what decide
    whether it is written.
    """
    return AccessContext(
        # `.value`: the envelope carries the typed ids, `AccessContext` the plain
        # ones. Passing the wrapper raised at validation rather than silently
        # becoming something else, which is the behaviour to want here.
        tenant_id=event.tenant_id.value,
        workspace_id=event.workspace_id.value,
        principal_id=payload.actor_id,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id=_NO_PLAN,
    )


def build_memory_handler(service: MemoryProposePort) -> EventHandler:
    """The handler to wire under `MEMORY_CANDIDATE_PROPOSED`."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = MemoryCandidatePayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError(f"payload does not parse: {exc}") from exc
        result = await service.propose(
            payload.candidate,
            _access_for(event, payload),
            created_by_run_id=payload.run_id,
            # The event id, so a redelivery decides once. See the module docstring.
            idempotency_key=event.id,
        )
        return f"memory candidate {result.outcome.decision.value}"

    return handle


def memory_handlers(service: MemoryProposePort) -> dict[str, EventHandler]:
    """Ready to merge into the outbox consumer's handler map."""
    return {MEMORY_CANDIDATE_PROPOSED: build_memory_handler(service)}
