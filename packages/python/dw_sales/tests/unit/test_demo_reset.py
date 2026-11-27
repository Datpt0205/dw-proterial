"""The demo reset deletes Sales cases, so it refuses every deployed profile,
and touches only the tenants the demo personas sign in to."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from dw_platform.testing.seed_env import sid
from dw_sales.testing import demo_reset

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("profile", ["uat", "production", "staging"])
def test_the_reset_refuses_any_profile_but_local_and_test(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    def must_not_run(url: str) -> None:
        raise AssertionError("the reset ran outside local/test")

    monkeypatch.setenv("DW_API_PROFILE", profile)
    monkeypatch.setenv("DW_DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(demo_reset, "_reset", must_not_run)

    with pytest.raises(SystemExit, match="refusing"):
        demo_reset.main()


def test_the_reset_clears_the_conversations_whose_answers_cite_its_cases() -> None:
    # A kept conversation links to cases the reset deleted (2026-11-26).
    assert demo_reset.tables.assistant_sessions in demo_reset._CLEARED


def test_the_reset_clears_only_the_demo_personas_tenants() -> None:
    assert demo_reset.demo_tenants() == sorted(
        [sid("tenant", "tenant-alpha"), sid("tenant", "tenant-beta")], key=str
    )


class _Recorder:
    """The migrator's connection, recording each statement the reset runs."""

    def __init__(self) -> None:
        self.statements: list[sa.Delete] = []

    async def execute(self, statement: sa.Delete) -> SimpleNamespace:
        self.statements.append(statement)
        return SimpleNamespace(rowcount=0)


class _Engine:
    def __init__(self, conn: _Recorder) -> None:
        self.conn = conn

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[_Recorder]:
        yield self.conn

    async def dispose(self) -> None:
        return None


async def _statements(monkeypatch: pytest.MonkeyPatch) -> list[sa.Delete]:
    conn = _Recorder()
    monkeypatch.setattr(demo_reset, "create_async_engine", lambda *_a, **_k: _Engine(conn))
    await demo_reset.clear_sales_cases("postgresql+asyncpg://unused")
    return conn.statements


def _table(statement: sa.Delete) -> sa.Table:
    assert isinstance(statement.table, sa.Table)
    return statement.table


async def test_the_reset_clears_the_stored_mailbox_so_no_mail_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # With the message log cleared, a stored mail is unread again: 8 test
    # mails of 10-27 were replayed on every reset until 11-28.
    deleted = {_table(statement).name for statement in await _statements(monkeypatch)}

    assert {"mailbox_messages", "mailbox_attachments", "sent_messages", "messages"} <= deleted
    # The drop lane's ledger stays: without it the lane reads the folder's
    # old files back in on its next tick.
    assert "mailbox_files" not in deleted


async def test_every_sales_table_the_reset_clears_is_narrowed_to_the_demo_tenants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenants = demo_reset.demo_tenants()
    sales = [s for s in await _statements(monkeypatch) if _table(s) in demo_reset._CLEARED]

    assert len(sales) == len(demo_reset._CLEARED)
    for statement in sales:
        compiled = statement.compile()
        table = _table(statement).name
        assert f"{table}.tenant_id IN" in str(compiled), table
        assert list(compiled.params.values()) == [tenants], table
