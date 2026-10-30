"""The status assistant's sessions (migration e0940c90ce04, dw_sales ADR 0007)
against a real database, as `dw_app`: a person's own under RLS, a turn only in
its person's session, appended, and gone thirty days after the last turn."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.persistence.assistant import SqlAssistantRetention, SqlAssistantStoreFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.assistant import CaseRef, QuestionKind, Session, Turn
from dw_sales.domain.dispositions import CaseKind

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
CASE = uuid.UUID(int=0xC0)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


async def _person(migrator: AsyncEngine) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO platform.users (id, subject, display_name)"
                " VALUES (:u, :s, 'Người dùng (giả lập)')"
            ),
            {"u": user_id, "s": f"dev|assistant.{user_id.hex[:8]}"},
        )
    return user_id


def _context(scope: SalesScope, user: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=user,
        roles=frozenset(),
        plan_id="business",
    )


def _session(user: uuid.UUID, at: datetime = T0) -> Session:
    return Session(uuid.uuid4(), user, "PO NRV-PO-26-0457?", at, at)


def _turn(session: Session, seq: int = 1, at: datetime = T0) -> Turn:
    ref = CaseRef(CaseKind.ORDER, CASE, "PO NRV-PO-26-0457")
    return Turn(
        session_id=session.session_id,
        seq=seq,
        asked_at=at,
        question="PO NRV-PO-26-0457 tới đâu rồi?",
        kind=QuestionKind.ORDER_STATUS,
        reference="NRV-PO-26-0457",
        answer="PO NRV-PO-26-0457 (rev 0) của khách NRV: Chờ PIC tự kiểm.",
        cites=(ref,),
        focus=ref,
        answered_by="code",
    )


async def test_a_session_is_kept_whole_and_read_back_by_its_person_alone(
    world: World, migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    an, binh, other = await _person(migrator), await _person(migrator), await _person(migrator)
    stores = SqlAssistantStoreFactory(app_sessions)
    session = _session(an)
    async with stores(_context(world.alpha, an)) as store:
        await store.open(session)
        await store.add(_turn(session))
    async with stores(_context(world.alpha, an)) as store:
        assert (await store.session(session.session_id)) is not None
        (turn,) = await store.turns(session.session_id)
        assert turn.focus == CaseRef(CaseKind.ORDER, CASE, "PO NRV-PO-26-0457")
        assert turn.cites == (turn.focus,) and turn.kind is QuestionKind.ORDER_STATUS
    # Another person of the same workspace, another workspace, another tenant.
    for scope, user in ((world.alpha, binh), (world.alpha_other, an), (world.beta, other)):
        async with stores(_context(scope, user)) as store:
            assert await store.session(session.session_id) is None
            assert await store.turns(session.session_id) == []
            assert await store.sessions(10) == []


async def test_the_policy_alone_keeps_another_persons_rows_out(
    world: World, migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Asked with no WHERE at all, as `dw_app`: RLS is the gate, not the store's
    filter."""
    an, binh = await _person(migrator), await _person(migrator)
    session = _session(an)
    async with SqlAssistantStoreFactory(app_sessions)(_context(world.alpha, an)) as store:
        await store.open(session)
        await store.add(_turn(session))
    scope = world.alpha
    async with tenant_session(
        app_sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value, binh)
    ) as db:
        for table in ("assistant_sessions", "assistant_turns"):
            count = (await db.execute(sa.text(f"SELECT count(*) FROM sales.{table}"))).scalar()
            assert count == 0, table
    async with tenant_session(
        app_sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value, None)
    ) as db:
        assert (
            await db.execute(sa.text("SELECT count(*) FROM sales.assistant_turns"))
        ).scalar() == 0


async def test_a_turn_never_lands_in_another_persons_session(
    world: World, migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    an, binh = await _person(migrator), await _person(migrator)
    stores = SqlAssistantStoreFactory(app_sessions)
    session = _session(an)
    async with stores(_context(world.alpha, an)) as store:
        await store.open(session)
    with pytest.raises(DBAPIError):
        async with stores(_context(world.alpha, binh)) as store:
            await store.add(_turn(session))


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM sales.assistant_turns",
        "UPDATE sales.assistant_turns SET answer = 'đã sửa'",
        "DELETE FROM sales.assistant_sessions",
        "UPDATE sales.assistant_sessions SET title = 'đã sửa'",
    ],
)
async def test_a_turn_is_never_rewritten_and_a_session_only_moves_its_last_use(
    world: World,
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    statement: str,
) -> None:
    an = await _person(migrator)
    session = _session(an)
    context = _context(world.alpha, an)
    async with SqlAssistantStoreFactory(app_sessions)(context) as store:
        await store.open(session)
        await store.add(_turn(session))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(app_sessions, TenantScope.from_access_context(context)) as db:
            await db.execute(sa.text(statement))


async def test_a_session_goes_thirty_days_after_its_last_turn_with_its_turns(
    world: World, migrator: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    an = await _person(migrator)
    stores = SqlAssistantStoreFactory(app_sessions)
    now = datetime.now(UTC)
    old, recent = _session(an, now - timedelta(days=31)), _session(an, now - timedelta(days=29))
    async with stores(_context(world.alpha, an)) as store:
        for session in (old, recent):
            await store.open(session)
            await store.add(_turn(session, at=session.last_turn_at))
    await SqlAssistantRetention(app_sessions).prune()
    async with stores(_context(world.alpha, an)) as store:
        assert [s.session_id for s in await store.sessions(10)] == [recent.session_id]
        assert await store.turns(old.session_id) == []
    async with migrator.connect() as conn:
        left = await conn.execute(
            sa.text("SELECT count(*) FROM sales.assistant_turns WHERE session_id = :s"),
            {"s": old.session_id},
        )
        assert left.scalar() == 0
