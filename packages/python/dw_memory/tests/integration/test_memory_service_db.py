"""Integration: a stored memory, and the chain that proves where it came from.

Against real Postgres, because every link added in migration 0007 is a database
constraint and none of them can be checked in memory: the CHECK that refuses
empty provenance, the foreign key from a memory to the run that made it, and the
two that tie a memory through `memory.item_evidence` to `knowledge.evidence` and
on to the chunk it quotes.

The fixtures seed a real document, a real chunk and a real run. That is the
change of substance: the previous version of this file invented a document id and
hashed an arbitrary string, which the system now refuses — the citation looked
perfect and referred to nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from runtime_harness import (
    TEST_DB,
    RuntimeUrls,
    recreate_database,
    run_migrations,
    runtime_urls,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_kernel.errors import DomainError
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_knowledge.adapters.evidence_store import SqlEvidenceStore
from dw_knowledge.contracts import EvidenceRef
from dw_memory import tables
from dw_memory.contracts import MemoryType, WriteDecision
from dw_memory.policy import MemoryCandidate, MemoryWritePolicy
from dw_memory.service import MemoryService
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.integration

TENANT = uuid.UUID(int=0xCC00)
WORKSPACE = uuid.UUID(int=0xCC01)
SOURCE_TEXT = b"Anh An noi se gui hop dong truoc thu Sau."


@pytest.fixture(scope="session")
def urls() -> RuntimeUrls:
    resolved = runtime_urls()
    try:
        asyncio.run(recreate_database(resolved.admin, TEST_DB))
    except Exception as exc:
        pytest.fail(f"Postgres unreachable — run `make infra-up`. Error: {exc}")
    result = run_migrations(resolved.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade failed:\n{result.stderr}")
    return resolved


@dataclass(frozen=True)
class Seeded:
    """Real source material and a real run, so a citation can be checked."""

    run_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    provenance_hash: str


@pytest.fixture
async def seeded(urls: RuntimeUrls) -> AsyncIterator[Seeded]:
    """Written as the migrator: RLS is what the service is tested through, not what
    the fixture should have to satisfy to lay down a document."""
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    run_id, document_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    digest = hashlib.sha256(SOURCE_TEXT).hexdigest()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO platform.worker_runs"
                " (id, thread_id, tenant_id, workspace_id, worker_id, worker_version,"
                "  graph_version, requested_by)"
                " VALUES (:id, :id, :t, :w, 'demo', '1.0.0', '1.0.0', :actor)"
            ),
            {"id": run_id, "t": TENANT, "w": WORKSPACE, "actor": uuid.uuid4()},
        )
        await conn.execute(
            text(
                "INSERT INTO knowledge.documents"
                " (id, tenant_id, workspace_id, title, source_uri, created_by)"
                " VALUES (:id, :t, :w, 'Bien ban hop', 'file://bien-ban', :actor)"
            ),
            {"id": document_id, "t": TENANT, "w": WORKSPACE, "actor": uuid.uuid4()},
        )
        await conn.execute(
            text(
                "INSERT INTO knowledge.chunks"
                " (id, tenant_id, workspace_id, document_id, seq, content,"
                "  start_offset, end_offset, provenance_hash)"
                " VALUES (:id, :t, :w, :doc, 0, :content, 0, :end, :hash)"
            ),
            {
                "id": chunk_id,
                "t": TENANT,
                "w": WORKSPACE,
                "doc": document_id,
                "content": SOURCE_TEXT.decode(),
                "end": len(SOURCE_TEXT),
                "hash": digest,
            },
        )
    try:
        yield Seeded(run_id, document_id, chunk_id, digest)
    finally:
        await engine.dispose()


@pytest.fixture
async def service(
    urls: RuntimeUrls,
) -> AsyncIterator[tuple[MemoryService, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield (
        MemoryService(
            session_factory=session_factory,
            policy=MemoryWritePolicy(),
            clock=SystemClock(),
            id_generator=Uuid4Generator(),
            evidence_store=SqlEvidenceStore(clock=SystemClock()),
        ),
        session_factory,
    )
    await engine.dispose()


def make_context() -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        scopes=frozenset({"demo.write"}),
        plan_id="professional",
    )


def evidence_for(seeded: Seeded, **overrides: object) -> EvidenceRef:
    fields: dict[str, object] = {
        "evidence_id": uuid.uuid4(),
        "source_document_id": seeded.document_id,
        "chunk_id": seeded.chunk_id,
        "source_version": "1",
        "relevance_score": 0.95,
        "classification": "internal",
        "provenance_hash": seeded.provenance_hash,
    }
    fields.update(overrides)
    return EvidenceRef(**fields)


def candidate(seeded: Seeded, *, confidence: float = 0.92, **overrides: object) -> MemoryCandidate:
    fields: dict[str, object] = {
        "worker_id": "demo",
        "memory_type": MemoryType.COMMITMENT,
        "content": "Anh An cam kết gửi hợp đồng trước thứ Sáu.",
        "provenance_refs": (evidence_for(seeded),),
        "confidence": confidence,
    }
    fields.update(overrides)
    return MemoryCandidate(**fields)


async def _scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str, **params: object
) -> object:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT)}
        )
        return (await session.execute(text(sql), params)).scalar_one()


# ------------------------------------------------------------- the chain --


async def test_a_stored_memory_traces_back_to_the_document_it_quotes(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """The question Mốc 4 exists for, answered in SQL rather than by inference."""
    memory_service, session_factory = service

    result = await memory_service.propose(
        candidate(seeded), make_context(), created_by_run_id=seeded.run_id
    )

    assert result.outcome.decision is WriteDecision.AUTO_WRITE
    assert result.item is not None
    title = await _scalar(
        session_factory,
        """
        SELECT d.title
        FROM memory.items i
        JOIN memory.item_evidence ie ON ie.memory_id = i.memory_id
        JOIN knowledge.evidence e ON e.evidence_id = ie.evidence_id
        JOIN knowledge.chunks c ON c.id = e.chunk_id
        JOIN knowledge.documents d ON d.id = c.document_id
        WHERE i.memory_id = :memory_id
        """,
        memory_id=result.item.memory_id,
    )
    assert title == "Bien ban hop"


async def test_the_run_that_wrote_a_memory_can_be_confirmed(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    memory_service, session_factory = service

    result = await memory_service.propose(
        candidate(seeded), make_context(), created_by_run_id=seeded.run_id
    )

    assert result.item is not None
    worker = await _scalar(
        session_factory,
        "SELECT r.worker_id FROM memory.items i"
        " JOIN platform.worker_runs r ON r.id = i.created_by_run_id"
        " WHERE i.memory_id = :memory_id",
        memory_id=result.item.memory_id,
    )
    assert worker == "demo"


async def test_a_memory_cannot_name_a_run_that_never_existed(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """`created_by_run_id` was NOT NULL with no foreign key: any UUID passed."""
    memory_service, _ = service

    with pytest.raises(sa.exc.IntegrityError, match="fk_items_created_by_run_id_worker_runs"):
        await memory_service.propose(
            candidate(seeded), make_context(), created_by_run_id=uuid.uuid4()
        )


# -------------------------------------------------- evidence must be real --


async def test_a_fabricated_hash_is_refused_and_nothing_is_written(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """A syntactically perfect citation to material that was never read. It used to
    be stored as the justification for a fact; now it is refused, and the candidate
    row rolls back with it — a refused write leaves no half-record behind."""
    memory_service, session_factory = service
    before = await _scalar(session_factory, "SELECT count(*) FROM memory.write_candidates")

    with pytest.raises(DomainError, match="hash does not match"):
        await memory_service.propose(
            candidate(seeded, provenance_refs=(evidence_for(seeded, provenance_hash="b" * 64),)),
            make_context(),
            created_by_run_id=seeded.run_id,
        )

    assert await _scalar(session_factory, "SELECT count(*) FROM memory.write_candidates") == before


async def test_evidence_citing_a_chunk_nobody_stored_is_refused(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    memory_service, _ = service

    with pytest.raises(DomainError, match="does not have"):
        await memory_service.propose(
            candidate(seeded, provenance_refs=(evidence_for(seeded, chunk_id=uuid.uuid4()),)),
            make_context(),
            created_by_run_id=seeded.run_id,
        )


async def test_evidence_that_cites_one_document_and_quotes_another_is_refused(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """The hash and the chunk agree; the document named does not own that chunk."""
    memory_service, _ = service

    with pytest.raises(DomainError, match="quotes another"):
        await memory_service.propose(
            candidate(
                seeded,
                provenance_refs=(evidence_for(seeded, source_document_id=uuid.uuid4()),),
            ),
            make_context(),
            created_by_run_id=seeded.run_id,
        )


async def test_evidence_with_no_chunk_is_refused_rather_than_stored_unverified(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """`EvidenceRef` allows it. Accepting it would be the loophole: name a real
    document, invent the hash, and nothing could check either."""
    memory_service, _ = service

    with pytest.raises(DomainError, match="must name the chunk"):
        await memory_service.propose(
            candidate(seeded, provenance_refs=(evidence_for(seeded, chunk_id=None),)),
            make_context(),
            created_by_run_id=seeded.run_id,
        )


# ------------------------------------------------------- policy, and audit --


async def test_low_confidence_goes_to_review_without_item(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    memory_service, session_factory = service
    before = await _scalar(session_factory, "SELECT count(*) FROM memory.items")

    result = await memory_service.propose(
        candidate(seeded, confidence=0.6, memory_type=MemoryType.PREFERENCE),
        make_context(),
        created_by_run_id=seeded.run_id,
    )

    assert result.outcome.decision is WriteDecision.REVIEW
    assert result.item is None
    assert await _scalar(session_factory, "SELECT count(*) FROM memory.items") == before


async def test_no_provenance_rejected(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    memory_service, _ = service

    result = await memory_service.propose(
        candidate(seeded, provenance_refs=(), confidence=0.99),
        make_context(),
        created_by_run_id=seeded.run_id,
    )

    assert result.outcome.decision is WriteDecision.REJECT
    assert result.item is None


@pytest.mark.parametrize(
    ("confidence", "action"),
    [
        (0.92, "memory.item_written"),
        (0.6, "memory.write_held_for_review"),
        (0.1, "memory.write_rejected"),
    ],
)
async def test_every_outcome_reaches_the_audit_trail(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]],
    seeded: Seeded,
    confidence: float,
    action: str,
) -> None:
    """A fact appearing in a customer's system with nobody able to say when it was
    learned is what an audit trail is for — and so is one that was refused."""
    memory_service, session_factory = service

    result = await memory_service.propose(
        candidate(seeded, confidence=confidence), make_context(), created_by_run_id=seeded.run_id
    )

    resource = str(result.item.memory_id) if result.item else str(result.candidate_id)
    recorded = await _scalar(
        session_factory,
        "SELECT details->>'policy_version' FROM platform.audit_events"
        " WHERE action = :action AND resource_id = :resource",
        action=action,
        resource=resource,
    )
    assert recorded == "1.0.0"


async def test_the_database_refuses_a_memory_with_empty_provenance(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """The service refuses it first. This is the constraint behind the service, for
    the second writer, the repair script and the bug that does not go through it."""
    _, session_factory = service

    with pytest.raises(sa.exc.IntegrityError, match="ck_items_provenance_refs"):
        async with session_factory() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT)}
            )
            await session.execute(
                sa.insert(tables.items).values(
                    memory_id=uuid.uuid4(),
                    tenant_id=TENANT,
                    workspace_id=WORKSPACE,
                    worker_id="demo",
                    memory_type="semantic",
                    subject_refs=[],
                    content="Không nguồn.",
                    structured_facts={},
                    provenance_refs=[],
                    confidence=0.99,
                    classification="internal",
                    valid_from=sa.func.now(),
                    retention_policy="default",
                    memory_schema_version="1.0.0",
                    created_by_run_id=seeded.run_id,
                    created_at=sa.func.now(),
                )
            )


# ------------------------------------------------------------------ recall --
#
# The read side. `propose` could write since the provenance work and nothing read
# it back, so every stored fact was write-only. These cover the four conditions
# recall narrows by, each with the negative case, because a recall that returns
# too much is a disclosure and looks exactly like one that works.


def a_subject() -> str:
    """A subject nobody else in this file uses.

    The database is created once for the whole module and every test writes into
    it as the same tenant, so a fixed subject string would make each test read
    its neighbours' memories — green alone, wrong together, and wrong in the
    direction that hides a leak. Isolating on the filter under test keeps each
    assertion about its own data.
    """
    return f"account:{uuid.uuid4()}"


async def _remember(
    # `Any`, not `object`: these are forwarded straight into `candidate`, whose
    # own signature types each one. `object` makes mypy reject the `confidence`
    # float it declares, and narrowing here would mean restating that signature.
    service: MemoryService,
    seeded: Seeded,
    *,
    context: AccessContext,
    **overrides: Any,
) -> None:
    result = await service.propose(
        candidate(seeded, **overrides), context, created_by_run_id=seeded.run_id
    )
    assert result.outcome.decision is WriteDecision.AUTO_WRITE, result.outcome.reason


async def test_recall_returns_what_this_worker_learned_about_the_subject(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    found = await svc.recall(
        context, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )

    assert [item.content for item in found] == ["Anh An cam kết gửi hợp đồng trước thứ Sáu."]


async def test_recall_without_a_subject_returns_nothing_rather_than_everything(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """ "No subject" must not read as "every subject" — that is the shape of an
    empty filter that widens instead of narrowing."""
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    assert await svc.recall(context, worker_id="demo", subject_refs=(), now=datetime.now(UTC)) == ()


async def test_recall_does_not_reach_another_tenants_memory(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    svc, _ = service
    subject = a_subject()
    await _remember(svc, seeded, context=make_context(), subject_refs=(subject,))

    intruder = make_context().model_copy(update={"tenant_id": uuid.UUID(int=0xDEAD)})
    found = await svc.recall(
        intruder, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )

    assert found == (), "another tenant's subject must return nothing at all"


async def test_recall_does_not_carry_one_workers_memory_into_another(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """A fact learned under a different prompt and toolset is not this worker's
    premise."""
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    found = await svc.recall(
        context, worker_id="other", subject_refs=(subject,), now=datetime.now(UTC)
    )

    assert found == ()


async def test_recall_will_not_hand_a_run_material_above_its_clearance(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """A memory carries the classification of what it was learned from, so a run
    may only recall what it could have read directly."""
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(subject,),
        classification="confidential",
    )

    at_internal = await svc.recall(
        context, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )
    assert at_internal == (), "internal clearance must not recall a confidential fact"

    cleared = context.model_copy(update={"clearance": "confidential"})
    assert (
        len(
            await svc.recall(
                cleared, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
            )
        )
        == 1
    )


async def test_recall_skips_a_fact_whose_validity_window_has_not_opened(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """`valid_from` is set to now at write, so asking about a moment before the
    write is how a closed window is exercised without waiting for one to close."""
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    earlier = datetime.now(UTC) - timedelta(days=1)
    assert await svc.recall(context, worker_id="demo", subject_refs=(subject,), now=earlier) == ()


async def test_recall_does_not_cross_between_two_teams_of_one_tenant(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """Tenant isolation is not the whole boundary: one company's two sales teams
    share a tenant and must not share what they learned.

    Added because a mutation found it missing — deleting the workspace condition
    from `recall` left every test in this file green, since they all wrote and
    read as the same workspace. A passing cross-tenant test says nothing about
    workspace separation.
    """
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    other_team = context.model_copy(update={"workspace_id": uuid.UUID(int=0xCC02)})
    found = await svc.recall(
        other_team, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )

    assert found == (), "a sibling workspace must not read this team's memory"


# ----------------------------------------------------------- supersession --
#
# Memory used to be append-only: nothing ever wrote `valid_until`, so two facts
# that disagreed both stayed live and recall returned both, ordered by
# confidence. A customer who moved their signing date twice left three live
# answers and the agent believed whichever it had been surest of.


async def test_a_newer_answer_closes_the_older_one_and_recall_returns_one(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(subject,),
        fact_key="contract_date",
        content="Ký ngày 10/10.",
        confidence=0.99,
    )
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(subject,),
        fact_key="contract_date",
        content="Ký ngày 20/10.",
        confidence=0.80,
    )

    live = await svc.recall(
        context, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )

    # The LATER one, not the more confident one — which is the whole point.
    assert [item.content for item in live] == ["Ký ngày 20/10."]


async def test_the_superseded_memory_is_closed_not_deleted(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """ "What did we believe last Tuesday" has to stay answerable, or the system
    cannot explain a decision it already made."""
    svc, session_factory = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,), fact_key="contract_date")
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(subject,),
        fact_key="contract_date",
        content="Ký ngày 20/10.",
    )

    rows = await _scalar(
        session_factory,
        "SELECT count(*) FROM memory.items WHERE subject_refs ? :s",
        s=subject,
    )
    closed = await _scalar(
        session_factory,
        "SELECT count(*) FROM memory.items WHERE subject_refs ? :s AND valid_until IS NOT NULL",
        s=subject,
    )
    assert rows == 2, "both rows are still there"
    assert closed == 1, "exactly the older one is closed"


async def test_a_memory_with_no_fact_key_supersedes_nothing(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """An episode does not replace an episode: a meeting happened, and so did
    another. Only a fact that names the question it answers may close one."""
    svc, _ = service
    context = make_context()
    subject = a_subject()
    await _remember(svc, seeded, context=context, subject_refs=(subject,), content="Họp lần 1.")
    await _remember(svc, seeded, context=context, subject_refs=(subject,), content="Họp lần 2.")

    live = await svc.recall(
        context, worker_id="demo", subject_refs=(subject,), now=datetime.now(UTC)
    )

    assert len(live) == 2


async def test_the_same_question_about_another_customer_is_untouched(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """`fact_key` alone is not identity — every account has a contract date."""
    svc, _ = service
    context = make_context()
    theirs, ours = a_subject(), a_subject()
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(theirs,),
        fact_key="contract_date",
        content="Của khách kia.",
    )
    await _remember(svc, seeded, context=context, subject_refs=(ours,), fact_key="contract_date")

    live = await svc.recall(
        context, worker_id="demo", subject_refs=(theirs,), now=datetime.now(UTC)
    )

    assert [item.content for item in live] == ["Của khách kia."]


async def test_supersession_names_what_it_closed_on_the_audit_trail(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """A fact that silently replaces another leaves a trail that records two
    writes and nothing connecting them."""
    svc, session_factory = service
    context = make_context()
    subject = a_subject()
    first = await svc.propose(
        candidate(seeded, subject_refs=(subject,), fact_key="contract_date"),
        context,
        created_by_run_id=seeded.run_id,
    )
    assert first.item is not None
    await _remember(
        svc,
        seeded,
        context=context,
        subject_refs=(subject,),
        fact_key="contract_date",
        content="Ký ngày 20/10.",
    )

    recorded = await _scalar(
        session_factory,
        """
        SELECT count(*) FROM platform.audit_events
        WHERE action = 'memory.item_written'
          AND details -> 'superseded' ? :closed
          AND details ->> 'fact_key' = 'contract_date'
        """,
        closed=str(first.item.memory_id),
    )
    assert recorded == 1


# ------------------------------------------------------------ idempotency --
#
# The outbox delivers at least once: the attempt is counted at claim time and
# the row marked afterwards, so a process that dies between them delivers again.
# Without a key that is a second identical memory, and with two retries a third.


async def test_the_same_delivery_twice_stores_one_memory(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    svc, session_factory = service
    context = make_context()
    subject = a_subject()
    event_id = uuid.uuid4()

    first = await svc.propose(
        candidate(seeded, subject_refs=(subject,)),
        context,
        created_by_run_id=seeded.run_id,
        idempotency_key=event_id,
    )
    second = await svc.propose(
        candidate(seeded, subject_refs=(subject,)),
        context,
        created_by_run_id=seeded.run_id,
        idempotency_key=event_id,
    )

    assert first.item is not None
    assert second.item is not None
    assert second.item.memory_id == first.item.memory_id, "the redelivery returns the first answer"
    stored = await _scalar(
        session_factory,
        "SELECT count(*) FROM memory.items WHERE subject_refs ? :s",
        s=subject,
    )
    assert stored == 1, "one delivery, one memory, however many times it arrives"


async def test_a_redelivery_does_not_write_a_second_audit_entry(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """An audit trail that records the same fact being learned three times
    because a worker restarted is a trail that has to be explained away."""
    svc, session_factory = service
    context = make_context()
    subject = a_subject()
    event_id = uuid.uuid4()
    for _ in range(3):
        await svc.propose(
            candidate(seeded, subject_refs=(subject,)),
            context,
            created_by_run_id=seeded.run_id,
            idempotency_key=event_id,
        )

    written = await _scalar(
        session_factory,
        """
        SELECT count(*) FROM platform.audit_events a
        JOIN memory.items i ON i.memory_id::text = a.resource_id
        WHERE a.action = 'memory.item_written' AND i.subject_refs ? :s
        """,
        s=subject,
    )
    assert written == 1


async def test_without_a_key_each_call_is_its_own_proposal(
    service: tuple[MemoryService, async_sessionmaker[AsyncSession]], seeded: Seeded
) -> None:
    """The unchanged behaviour, pinned: a caller that means each proposal
    separately must not start collapsing them."""
    svc, session_factory = service
    context = make_context()
    subject = a_subject()

    await _remember(svc, seeded, context=context, subject_refs=(subject,))
    await _remember(svc, seeded, context=context, subject_refs=(subject,))

    stored = await _scalar(
        session_factory,
        "SELECT count(*) FROM memory.items WHERE subject_refs ? :s",
        s=subject,
    )
    assert stored == 2
