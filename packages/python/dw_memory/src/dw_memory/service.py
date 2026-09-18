"""Memory service: candidate → policy decision → (maybe) stored item.

A stored memory is a claim this system will repeat as fact, so what it rests on is
written with it, in one transaction, and checked first:

- the evidence it cites is verified against the chunks it names and recorded in
  `knowledge.evidence`, so `evidence_id` resolves to something;
- `memory.item_evidence` ties the item to that evidence with foreign keys, so the
  citation cannot name a row that was never written;
- the write is audited, because a fact appearing in a customer's system with
  nobody able to say when it was learned is the thing an audit trail is for.

All four writes share the service's transaction. A memory that committed while its
evidence rolled back would be precisely the dangling citation this prevents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import CursorPosition, Page, PageRequest, build_page
from dw_kernel.ports import IdGenerator, UtcClock
from dw_memory import tables
from dw_memory.contracts import MEMORY_SCHEMA_VERSION, MemoryItem, WriteDecision
from dw_memory.policy import MemoryCandidate, MemoryWritePolicy, PolicyOutcome
from dw_memory.ports import EvidenceStorePort
from dw_platform.adapters.persistence.keyset import after_position, newest_first
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")

# One action per outcome, so "what did this worker learn, and what did it decline
# to learn" are both answerable from the trail rather than only the first.
_ACTION = {
    WriteDecision.AUTO_WRITE: "memory.item_written",
    WriteDecision.REVIEW: "memory.write_held_for_review",
    WriteDecision.REJECT: "memory.write_rejected",
}


@dataclass(frozen=True)
class ProposalResult:
    candidate_id: uuid.UUID
    outcome: PolicyOutcome
    item: MemoryItem | None


@dataclass
class MemoryService:
    session_factory: async_sessionmaker[AsyncSession]
    policy: MemoryWritePolicy
    clock: UtcClock
    id_generator: IdGenerator
    # Verifies a citation against the source material before it is written. The
    # policy above decides whether a fact is worth keeping; this decides whether
    # its stated reason is real, which no amount of confidence can substitute for.
    evidence_store: EvidenceStorePort

    async def propose(
        self,
        candidate: MemoryCandidate,
        context: AccessContext,
        *,
        created_by_run_id: uuid.UUID,
    ) -> ProposalResult:
        outcome = self.policy.evaluate(candidate)
        candidate_id = self.id_generator.new_uuid()
        now = self.clock.now()

        item: MemoryItem | None = None
        if outcome.decision is WriteDecision.AUTO_WRITE:
            item = MemoryItem(
                memory_id=self.id_generator.new_uuid(),
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                worker_id=candidate.worker_id,
                memory_type=candidate.memory_type,
                subject_refs=candidate.subject_refs,
                content=candidate.content,
                structured_facts=dict(candidate.structured_facts),
                provenance_refs=candidate.provenance_refs,
                confidence=candidate.confidence,
                classification=candidate.classification,
                valid_from=now,
                retention_policy="default",
                memory_schema_version=MEMORY_SCHEMA_VERSION,
                created_by_run_id=created_by_run_id,
            )

        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(context.tenant_id)})
            await session.execute(
                sa.insert(tables.write_candidates).values(
                    id=candidate_id,
                    tenant_id=context.tenant_id,
                    workspace_id=context.workspace_id,
                    worker_id=candidate.worker_id,
                    memory_type=candidate.memory_type.value,
                    content=candidate.content,
                    structured_facts=dict(candidate.structured_facts),
                    provenance_refs=[
                        ref.model_dump(mode="json") for ref in candidate.provenance_refs
                    ],
                    confidence=candidate.confidence,
                    classification=candidate.classification,
                    decision=outcome.decision.value,
                    memory_id=item.memory_id if item else None,
                    created_by_run_id=created_by_run_id,
                    created_at=now,
                )
            )
            if item is not None:
                # Before the item: a reference that fails verification must not
                # leave a memory behind, and raising here rolls back the candidate
                # row with it.
                await self.evidence_store.record(
                    session,
                    item.provenance_refs,
                    tenant_id=context.tenant_id,
                    workspace_id=context.workspace_id,
                )
                await session.execute(
                    sa.insert(tables.items).values(
                        memory_id=item.memory_id,
                        tenant_id=item.tenant_id,
                        workspace_id=item.workspace_id,
                        worker_id=item.worker_id,
                        memory_type=item.memory_type.value,
                        subject_refs=list(item.subject_refs),
                        content=item.content,
                        structured_facts=dict(item.structured_facts),
                        provenance_refs=[
                            ref.model_dump(mode="json") for ref in item.provenance_refs
                        ],
                        confidence=item.confidence,
                        classification=item.classification,
                        valid_from=item.valid_from,
                        valid_until=item.valid_until,
                        retention_policy=item.retention_policy,
                        memory_schema_version=item.memory_schema_version,
                        created_by_run_id=item.created_by_run_id,
                        created_at=now,
                    )
                )
                await session.execute(
                    sa.insert(tables.item_evidence),
                    [
                        {
                            "memory_id": item.memory_id,
                            "evidence_id": ref.evidence_id,
                            "tenant_id": item.tenant_id,
                        }
                        for ref in item.provenance_refs
                    ],
                )
            await SqlAuditRepository(session).append(
                self._audit_event(
                    context, candidate, outcome, item, candidate_id, created_by_run_id, now
                )
            )
        return ProposalResult(candidate_id=candidate_id, outcome=outcome, item=item)

    def _audit_event(
        self,
        context: AccessContext,
        candidate: MemoryCandidate,
        outcome: PolicyOutcome,
        item: MemoryItem | None,
        candidate_id: uuid.UUID,
        created_by_run_id: uuid.UUID,
        now: datetime,
    ) -> AuditEvent:
        """What was learned, on whose evidence, and under which policy.

        The policy version is recorded because thresholds move: a fact auto-written
        at 0.80 confidence should still read as having been auto-written under the
        rules of the day, not judged against whatever the threshold becomes.
        """
        return AuditEvent(
            id=self.id_generator.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=_ACTION[outcome.decision],
            resource_type="memory_item",
            # The item when there is one, else the candidate that was not stored: a
            # refusal has to be as addressable as a write.
            resource_id=str(item.memory_id) if item is not None else str(candidate_id),
            run_id=created_by_run_id,
            trace_id=None,
            details={
                "worker_id": candidate.worker_id,
                "memory_type": candidate.memory_type.value,
                "confidence": candidate.confidence,
                "classification": candidate.classification,
                "reason": outcome.reason,
                "policy_version": self.policy.policy_version,
                "evidence_count": len(candidate.provenance_refs),
            },
            occurred_at=now.astimezone(UTC),
        )

    async def list_items(self, context: AccessContext, request: PageRequest) -> Page[MemoryItem]:
        """Tenant-scoped long-term memory inventory (newest first, resumable).

        Ordered by ``created_at`` rather than ``valid_from``: the two differ for a
        backdated fact, and only ``created_at`` is monotonic with insertion, which
        is what makes a cursor position stable while the agent keeps writing.
        """
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(context.tenant_id)})
            rows = await session.execute(
                sa.select(tables.items)
                .where(
                    tables.items.c.workspace_id == context.workspace_id,
                    after_position(
                        tables.items.c.created_at, tables.items.c.memory_id, request.after
                    ),
                )
                .order_by(*newest_first(tables.items.c.created_at, tables.items.c.memory_id))
                .limit(request.fetch_limit)
            )
            # Paged on the rows, then mapped: ``created_at`` carries the sort
            # position and is not a field of MemoryItem, so the cursor has to be
            # minted while the row is still in hand.
            page = build_page(
                rows.all(),
                request=request,
                position_of=lambda row: CursorPosition(
                    sort_value=row.created_at, tiebreaker=row.memory_id
                ),
            )
            return page.map_items(
                lambda row: MemoryItem.model_validate(
                    {
                        **dict(row._mapping),
                        "subject_refs": tuple(row.subject_refs),
                        "provenance_refs": tuple(row.provenance_refs),
                    }
                )
            )
