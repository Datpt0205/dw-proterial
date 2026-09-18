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

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.pagination import CursorPosition, Page, PageRequest, build_page
from dw_kernel.ports import IdGenerator, UtcClock
from dw_knowledge.contracts import classifications_for_clearance
from dw_memory import tables
from dw_memory.contracts import MEMORY_SCHEMA_VERSION, MemoryItem, WriteDecision
from dw_memory.policy import MemoryCandidate, MemoryWritePolicy, PolicyOutcome
from dw_memory.ports import EvidenceStorePort
from dw_memory.ranking import MemoryRankerPort, rank_by
from dw_platform.adapters.persistence.keyset import after_position, newest_first
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent

logger = logging.getLogger("dw_memory.service")

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")

# How many recalled facts may reach one model call. A ceiling, not a tuning
# knob: recall runs on every step, and an unbounded list would grow the prompt
# with the agent's own output until compaction fought it.
DEFAULT_RECALL_LIMIT = 12

# How many live memories a ranker may reorder. Wider than the cap so the
# ranker has something to choose from, bounded so one account with years of
# history does not load its whole past to pick twelve rows.
RANKING_POOL = 100

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
    # Orders what recall found when there is more of it than fits. Optional, and
    # it can only ever change the ORDER — see `dw_memory.ranking`.
    ranker: MemoryRankerPort | None = None

    async def propose(
        self,
        candidate: MemoryCandidate,
        context: AccessContext,
        *,
        created_by_run_id: uuid.UUID,
        idempotency_key: uuid.UUID | None = None,
    ) -> ProposalResult:
        """Decide on a candidate and, if it passes, store it with its evidence.

        `idempotency_key` is for callers that may be asked twice — the outbox
        delivers at least once, so its handler will be. Passing the event's id
        makes the candidate row's primary key deterministic, and the second
        delivery finds it already there and returns what was decided the first
        time instead of writing a second memory. Without a key the behaviour is
        unchanged: a fresh id every call, which is right for a caller that means
        each proposal to be its own.
        """
        outcome = self.policy.evaluate(candidate)
        candidate_id = idempotency_key or self.id_generator.new_uuid()
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
                fact_key=candidate.fact_key,
            )

        # Bound before the branch: a REVIEW or REJECT stores no item and closes
        # nothing, but the audit event is written either way and reads this.
        superseded: tuple[uuid.UUID, ...] = ()
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(context.tenant_id)})
            if idempotency_key is not None:
                seen = await self._already_decided(session, idempotency_key)
                if seen is not None:
                    return seen
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
                        fact_key=item.fact_key,
                        created_at=now,
                    )
                )
                superseded = await self._close_superseded(session, item, now=now)
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
                    context,
                    candidate,
                    outcome,
                    item,
                    candidate_id,
                    created_by_run_id,
                    now,
                    superseded=superseded,
                )
            )
        return ProposalResult(candidate_id=candidate_id, outcome=outcome, item=item)

    async def _already_decided(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> ProposalResult | None:
        """What was decided for this candidate id, if it has been seen before.

        A read inside the caller's transaction, deliberately: checking on one
        connection and writing on another leaves the window where two deliveries
        both find nothing. The candidate table's primary key is the backstop if
        two workers race past this check at the same instant — one of them gets a
        unique violation and the delivery is retried, which is the correct
        outcome for at-least-once.
        """
        row = (
            await session.execute(
                sa.select(
                    tables.write_candidates.c.decision,
                    tables.write_candidates.c.memory_id,
                ).where(tables.write_candidates.c.id == candidate_id)
            )
        ).first()
        if row is None:
            return None
        item: MemoryItem | None = None
        if row.memory_id is not None:
            stored = (
                await session.execute(
                    sa.select(tables.items).where(tables.items.c.memory_id == row.memory_id)
                )
            ).first()
            if stored is not None:
                item = MemoryItem.model_validate(
                    {
                        **dict(stored._mapping),
                        "subject_refs": tuple(stored.subject_refs),
                        "provenance_refs": tuple(stored.provenance_refs),
                    }
                )
        decision = WriteDecision(row.decision)
        return ProposalResult(
            candidate_id=candidate_id,
            # The reason is not stored on the candidate row, and inventing one
            # here would put words in the first decision's mouth. The decision
            # itself is what a caller acts on.
            outcome=PolicyOutcome(decision=decision, reason="already decided"),
            item=item,
        )

    async def _close_superseded(
        self, session: AsyncSession, item: MemoryItem, *, now: datetime
    ) -> tuple[uuid.UUID, ...]:
        """Close the live memories this one answers over, and say which.

        Two memories sharing a `fact_key` AND a subject are two answers to one
        question; the later one is the answer now. Closing is `valid_until = now`
        — the row, its provenance and its audit entry all stay, so "what did we
        believe last Tuesday" is still answerable. Deleting would make the system
        unable to explain a decision it had already made.

        In the caller's transaction, deliberately: a memory superseded by one
        whose evidence then failed verification would leave the customer with no
        live answer at all.

        A memory with no key supersedes nothing. That is the compatibility story
        and also the correct default — an episode does not replace an episode.
        """
        if item.fact_key is None or not item.subject_refs:
            return ()
        closed = await session.execute(
            sa.update(tables.items)
            .where(
                tables.items.c.workspace_id == item.workspace_id,
                tables.items.c.worker_id == item.worker_id,
                tables.items.c.fact_key == item.fact_key,
                tables.items.c.memory_id != item.memory_id,
                tables.items.c.valid_until.is_(None),
                tables.items.c.subject_refs.op("?|")(
                    sa.literal(list(item.subject_refs), sa.ARRAY(sa.Text))
                ),
            )
            .values(valid_until=now)
            .returning(tables.items.c.memory_id)
        )
        return tuple(row.memory_id for row in closed.all())

    def _audit_event(
        self,
        context: AccessContext,
        candidate: MemoryCandidate,
        outcome: PolicyOutcome,
        item: MemoryItem | None,
        candidate_id: uuid.UUID,
        created_by_run_id: uuid.UUID,
        now: datetime,
        *,
        superseded: tuple[uuid.UUID, ...] = (),
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
                # Which memories this one closed, and under what name. A fact
                # that silently replaces another is the same trail problem as a
                # setting that changes without saying what changed: the row is
                # still there, but nothing connects it to what replaced it.
                "fact_key": candidate.fact_key,
                "superseded": [str(memory_id) for memory_id in superseded],
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

    async def recall(
        self,
        context: AccessContext,
        *,
        worker_id: str,
        subject_refs: Sequence[str],
        now: datetime,
        limit: int = DEFAULT_RECALL_LIMIT,
        query: str | None = None,
    ) -> tuple[MemoryItem, ...]:
        """What this worker already knows about these subjects, for this caller.

        The read side of memory. `propose` has been able to write since the
        provenance work; nothing read it back, which made every stored fact
        write-only — the shape this repository keeps producing, and the reason
        `list_items` (an inventory screen) is not the same thing as recall.

        Four conditions, and each one is a boundary rather than a preference:

        - **tenant**: the GUC is set from the verified context and RLS enforces
          it, the same as every other read here;
        - **workspace**: a tenant's two teams do not share what they learned;
        - **worker**: a fact another worker wrote was learned under a different
          prompt and toolset, and carrying it over is how one worker's mistake
          becomes another's premise;
        - **clearance**: a memory carries the classification of the material it
          was learned from, so a run may only recall what it could have read
          directly — resolved through `classifications_for_clearance`, the same
          ladder retrieval uses, never a second table.

        Plus validity: a fact whose window has closed is history, not memory.

        Ordered by confidence then recency, because what reaches the model is
        capped and the cap should drop the least-supported claim rather than an
        arbitrary one. An empty `subject_refs` recalls nothing: a run that is
        about no particular record has no basis to pull one record's facts in,
        and "no subject" must not read as "every subject".
        """
        # A shortcut, not the enforcement: `?|` against an empty array matches
        # no row either, so the behaviour holds without this line. It is here to
        # skip a round trip that can only return nothing.
        if not subject_refs:
            return ()
        allowed = classifications_for_clearance(context.clearance)
        async with self.session_factory() as session, session.begin():
            await session.execute(_SET_TENANT, {"tenant_id": str(context.tenant_id)})
            rows = await session.execute(
                sa.select(tables.items)
                .where(
                    tables.items.c.workspace_id == context.workspace_id,
                    tables.items.c.worker_id == worker_id,
                    tables.items.c.classification.in_(allowed),
                    # JSONB `?|`: the stored subject list overlaps the asked-for
                    # one. Done in SQL rather than by filtering in Python, so the
                    # limit below applies to matching rows and not to whatever
                    # the first page happened to hold.
                    #
                    # The right operand is typed `text[]` explicitly. Left to
                    # infer, SQLAlchemy binds a Python list as JSONB and Postgres
                    # answers `operator does not exist: jsonb ?| jsonb` — which
                    # only a real database says, and is the reason this is tested
                    # against one.
                    tables.items.c.subject_refs.op("?|")(
                        sa.literal(list(subject_refs), sa.ARRAY(sa.Text))
                    ),
                    tables.items.c.valid_from <= now,
                    sa.or_(
                        tables.items.c.valid_until.is_(None),
                        tables.items.c.valid_until > now,
                    ),
                )
                .order_by(
                    tables.items.c.confidence.desc(),
                    tables.items.c.created_at.desc(),
                    tables.items.c.memory_id.desc(),
                )
                # Read wider than the cap only when something will reorder them;
                # otherwise the first `limit` by confidence IS the answer and
                # fetching more is work nobody reads.
                .limit(RANKING_POOL if self._ranks(query) else limit)
            )
            found = [
                MemoryItem.model_validate(
                    {
                        **dict(row._mapping),
                        "subject_refs": tuple(row.subject_refs),
                        "provenance_refs": tuple(row.provenance_refs),
                    }
                )
                for row in rows.all()
            ]
        return tuple(await self._ordered(found, query, context, worker_id))[:limit]

    def _ranks(self, query: str | None) -> bool:
        return self.ranker is not None and bool(query)

    async def _ordered(
        self,
        found: list[MemoryItem],
        query: str | None,
        context: AccessContext,
        worker_id: str,
    ) -> list[MemoryItem]:
        """Similarity order when a ranker can give one, the query's order otherwise.

        Outside the transaction: the rows are already in hand, and holding a
        database connection open across a call to another service is how a slow
        dependency becomes a connection-pool outage.

        Fails open to the existing order, deliberately. A ranker that is down
        leaves an agent reading its memories confidence-first, which is what
        every run did before this existed — not an agent with no memory, and
        certainly not a failed run.
        """
        if self.ranker is None or not query or not found:
            return found
        try:
            order = await self.ranker.nearest(
                query,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                worker_id=worker_id,
                limit=len(found),
            )
        except Exception:
            logger.warning(
                "memory ranker failed; falling back to confidence order",
                extra={"worker_id": worker_id},
                exc_info=True,
            )
            return found
        return rank_by(order, [(item.memory_id, item) for item in found])
