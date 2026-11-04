"""DW2's Hỏi đáp sessions on PostgreSQL, as `dw_app` under RLS (migration
63b96e56db85): a session and its turns round-trip for their asker; another
person, another workspace and another tenant read none of it; a turn is
appended, never changed or deleted; the prune drops a session thirty days
after its last turn, with its turns."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_purchasing.adapters.persistence.assistant import SqlAssistantRetention, SqlAssistantStore
from dw_purchasing.domain.assistant import AssistantQuestionKind, CaseRef, Session, Turn
from dw_purchasing.testing.world import caller

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
ASKER, OTHER = uuid.uuid4(), uuid.uuid4()


async def _people(migrator: AsyncEngine) -> None:
    async with migrator.begin() as conn:
        for user in (ASKER, OTHER):
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.users (id, subject, display_name)"
                    " VALUES (:u, :s, 'x') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "s": f"test|{user}"},
            )


def _turn(session: Session, seq: int, at: datetime) -> Turn:
    case = CaseRef(uuid.uuid4(), "PR-2611-004")
    return Turn(
        session_id=session.session_id,
        seq=seq,
        asked_at=at,
        question="PR-2611-004 tới đâu rồi?",
        kind=AssistantQuestionKind.REQUEST_STATUS,
        reference="PR-2611-004",
        answer="PR-2611-004 (Xưởng cắt): Đã nhận.",
        cites=(case,),
        focus=case,
        answered_by="code",
    )


async def test_a_session_is_its_asker_s_alone_and_its_turns_only_appended(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, migrator: AsyncEngine
) -> None:
    await _people(migrator)
    store = SqlAssistantStore(app_sessions)
    me = caller(tenancy.alpha, principal=ASKER)
    session = Session(uuid.uuid4(), ASKER, "PR-2611-004 tới đâu rồi?", NOW, NOW)
    first = _turn(session, 1, NOW)
    await store.append(me, session, first)
    later = _turn(session, 2, NOW + timedelta(minutes=1))
    await store.append(me, session, later)

    assert await store.turns(me, session.session_id) == [first, later]
    (kept,) = await store.sessions(me, limit=10)
    assert kept.last_turn_at == later.asked_at

    for other in (
        caller(tenancy.alpha, principal=OTHER),
        caller(tenancy.alpha_other, principal=ASKER),
        caller(tenancy.beta, principal=ASKER),
    ):
        assert await store.session(other, session.session_id) is None
        assert await store.turns(other, session.session_id) == []
        assert await store.sessions(other, limit=10) == []

    # Appended, never changed: the application role holds no UPDATE of a
    # turn and no DELETE of either table.
    async with app_sessions() as db, db.begin():
        await db.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true),"
                " set_config('app.workspace_id', :w, true), set_config('app.user_id', :u, true)"
            ),
            {"t": str(tenancy.alpha[0]), "w": str(tenancy.alpha[1]), "u": str(ASKER)},
        )
        for statement in (
            "UPDATE purchasing.assistant_turns SET answer = 'x'",
            "DELETE FROM purchasing.assistant_turns",
            "DELETE FROM purchasing.assistant_sessions",
            "UPDATE purchasing.assistant_sessions SET title = 'x'",
        ):
            with pytest.raises(DBAPIError, match="permission denied"):
                async with db.begin_nested():
                    await db.execute(sa.text(statement))
        # A kind outside the catalog is refused by the catalog's CHECK.
        with pytest.raises(DBAPIError, match="ck_assistant_turns_kind"):
            async with db.begin_nested():
                await db.execute(
                    sa.text(
                        "INSERT INTO purchasing.assistant_turns (session_id, seq, tenant_id,"
                        " workspace_id, user_id, asked_at, question, kind, answer, cites,"
                        " answered_by) VALUES (:s, 9, :t, :w, :u, now(), 'q', 'approve', 'a',"
                        " '[]', 'code')"
                    ),
                    {
                        "s": session.session_id,
                        "t": tenancy.alpha[0],
                        "w": tenancy.alpha[1],
                        "u": ASKER,
                    },
                )


async def test_the_prune_drops_a_session_thirty_days_after_its_last_turn(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, migrator: AsyncEngine
) -> None:
    await _people(migrator)
    store = SqlAssistantStore(app_sessions)
    me = caller(tenancy.alpha, principal=ASKER)
    old_at = datetime.now(UTC) - timedelta(days=31)
    fresh_at = datetime.now(UTC) - timedelta(days=29)
    old = Session(uuid.uuid4(), ASKER, "cũ", old_at, old_at)
    fresh = Session(uuid.uuid4(), ASKER, "mới", fresh_at, fresh_at)
    await store.append(me, old, _turn(old, 1, old_at))
    await store.append(me, fresh, _turn(fresh, 1, fresh_at))

    await SqlAssistantRetention(app_sessions).prune()

    assert [s.session_id for s in await store.sessions(me, limit=10)] == [fresh.session_id]
    assert await store.turns(me, old.session_id) == []
