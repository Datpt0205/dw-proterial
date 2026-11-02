"""DW2's stored mailbox (migration 32c1f04b76d6) on PostgreSQL, as `dw_app`
wherever isolation is the question.

A dropped mail is stored once, with its audit event as the lane, read back
whole, its attachment kept; another tenant or workspace reads none of it, and
a connection that never scoped itself reads nothing even by partition name;
the application can neither rewrite nor remove it; a month made ahead is
policed; the retention function deletes one workspace's mail before its
cutoff and no one else's; offboarding exports a tenant's mail from every
workspace and its purge takes it away, leaving the other tenant's.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.offboarding import SqlTenantOffboarding
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.domain.messages import Attachment, EmailAddress, InboundMessage
from dw_purchasing.adapters.persistence.mailbox import SqlPurchasingMailbox
from dw_purchasing.adapters.persistence.retention import SqlRetentionStore
from dw_purchasing.application.mail_drop import MAIL_DROP_LANE, MAIL_STORED, MailFile
from dw_purchasing.testing.world import caller

pytestmark = pytest.mark.integration

_XLSX = b"PK\x03\x04 fictional purchase request form"
_TABLES = ("mailbox_messages", "mailbox_attachments", "mailbox_files")


def _scope(pair: tuple[uuid.UUID, uuid.UUID]) -> ContextScope:
    return ContextScope(TenantId(pair[0]), WorkspaceId(pair[1]))


def _mail(
    *,
    sender: str = "an@buyer.example",
    internet_id: str | None = None,
    received: datetime | None = None,
    salt: str | None = None,
) -> MailFile:
    data = (salt or uuid.uuid4().hex).encode()
    attachment = Attachment(
        attachment_id="a1",
        name="PR-2611-031.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size=len(_XLSX),
        sha256=hashlib.sha256(_XLSX).hexdigest(),
    )
    message = InboundMessage(
        message_id="eml-" + hashlib.sha256(data).hexdigest(),
        internet_message_id=internet_id or f"<{uuid.uuid4().hex}@buyer.example>",
        sender=EmailAddress(address=sender),
        subject="Đề nghị mua hàng PR-2611-031",
        received_at=received or datetime.now(UTC).replace(microsecond=0),
        body_text="Xin mua 40 bộ găng tay chống cắt.",
        attachments=(attachment,),
    )
    return MailFile(message=message, contents={"a1": _XLSX})


def _event(scope: ContextScope, mail: MailFile, source: str) -> AuditEvent:
    return lane_audit_event(
        lane=MAIL_DROP_LANE,
        event_id=uuid.uuid4(),
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        action=MAIL_STORED,
        resource_type="purchasing.message",
        resource_id=mail.message.message_id,
        occurred_at=datetime.now(UTC),
        details={"source": source},
    )


@pytest.fixture
def mailbox(app_sessions: async_sessionmaker[AsyncSession]) -> SqlPurchasingMailbox:
    return SqlPurchasingMailbox(app_sessions, SqlAuditRepository)


async def _store(
    mailbox: SqlPurchasingMailbox, pair: tuple[uuid.UUID, uuid.UUID], mail: MailFile, source: str
) -> bool:
    scope = _scope(pair)
    return await mailbox.store(scope, mail, source=source, event=_event(scope, mail, source))


async def _bind(session: AsyncSession, pair: tuple[uuid.UUID, uuid.UUID]) -> None:
    for key, value in (("app.tenant_id", pair[0]), ("app.workspace_id", pair[1])):
        await session.execute(
            sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
        )


# ---------------------------------------------------------------- the rows --


async def test_a_mail_is_stored_once_with_its_attachment_and_read_back_whole(
    mailbox: SqlPurchasingMailbox, migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    mail = _mail()
    scope = _scope(tenancy.alpha)
    event = _event(scope, mail, "20261102-1.eml")

    assert await mailbox.store(scope, mail, source="20261102-1.eml", event=event)

    me = caller(tenancy.alpha)
    assert await mailbox.get_message(me, mail.message.message_id) == mail.message
    assert mail.message in await mailbox.list_messages(me)
    assert "20261102-1.eml" in await mailbox.handled_sources(scope)
    async with migrator.connect() as conn:
        content = await conn.scalar(
            sa.text(
                "SELECT content FROM purchasing.mailbox_attachments"
                " WHERE message_id = :m AND attachment_id = 'a1'"
            ),
            {"m": mail.message.message_id},
        )
        actor = await conn.scalar(
            sa.text("SELECT details->>'actor' FROM platform.audit_events WHERE id = :id"),
            {"id": event.id},
        )
    assert content == _XLSX
    assert actor == f"system:{MAIL_DROP_LANE}"


async def test_a_copy_or_one_mail_exported_twice_is_stored_once_and_audited_once(
    mailbox: SqlPurchasingMailbox, migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    same = "<same@buyer.example>"
    first = _mail(internet_id=same, salt="one")
    assert await _store(mailbox, tenancy.alpha, first, "a.eml")
    # The same file again, under another name.
    assert not await _store(mailbox, tenancy.alpha, _mail(internet_id=same, salt="one"), "b.eml")
    # The same mail in another file: other bytes, same Message-ID and sender.
    assert not await _store(mailbox, tenancy.alpha, _mail(internet_id=same, salt="two"), "c.eml")
    # The same Message-ID from someone else is someone else's mail.
    other = _mail(internet_id=same, sender="other@another.example", salt="three")
    assert await _store(mailbox, tenancy.alpha, other, "d.eml")

    listed = [m.internet_message_id for m in await mailbox.list_messages(caller(tenancy.alpha))]
    assert listed.count(same) == 2
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT source_name, outcome FROM purchasing.mailbox_files"
                " WHERE tenant_id = :t AND source_name IN ('a.eml','b.eml','c.eml','d.eml')"
            ),
            {"t": tenancy.alpha[0]},
        )
        outcomes = {row.source_name: row.outcome for row in rows}
        audited = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events"
                " WHERE tenant_id = :t AND action = :a AND resource_id = :m"
            ),
            {"t": tenancy.alpha[0], "a": MAIL_STORED, "m": first.message.message_id},
        )
    assert outcomes == {
        "a.eml": "stored",
        "b.eml": "duplicate",
        "c.eml": "duplicate",
        "d.eml": "stored",
    }
    assert audited == 1


async def test_a_refused_file_is_recorded_with_its_reason_and_nothing_else(
    mailbox: SqlPurchasingMailbox, migrator: AsyncEngine, tenancy: Tenancy
) -> None:
    scope = _scope(tenancy.alpha)
    await mailbox.refuse(scope, source="bad.eml", reason="the file is over 20 MB")
    assert "bad.eml" in await mailbox.handled_sources(scope)
    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT outcome, reason, message_id FROM purchasing.mailbox_files"
                    " WHERE tenant_id = :t AND source_name = 'bad.eml'"
                ),
                {"t": tenancy.alpha[0]},
            )
        ).one()
    assert tuple(row) == ("refused", "the file is over 20 MB", None)


async def test_the_mailbox_is_read_oldest_first(
    mailbox: SqlPurchasingMailbox, tenancy: Tenancy
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    newer, older = _mail(received=now), _mail(received=now - timedelta(hours=2))
    await _store(mailbox, tenancy.alpha, newer, "n.eml")
    await _store(mailbox, tenancy.alpha, older, "o.eml")
    listed = [m.message_id for m in await mailbox.list_messages(caller(tenancy.alpha))]
    assert listed.index(older.message.message_id) < listed.index(newer.message.message_id)


# --------------------------------------------------------------- isolation --


async def test_another_tenant_or_workspace_reads_none_of_it(
    mailbox: SqlPurchasingMailbox, tenancy: Tenancy
) -> None:
    mail = _mail()
    await _store(mailbox, tenancy.alpha, mail, "iso.eml")
    message_id = mail.message.message_id

    for pair in (tenancy.beta, tenancy.alpha_other):
        them = caller(pair)
        assert all(m.message_id != message_id for m in await mailbox.list_messages(them))
        assert await mailbox.get_message(them, message_id) is None
        assert "iso.eml" not in await mailbox.handled_sources(_scope(pair))


async def test_a_connection_that_never_scopes_itself_reads_nothing_even_by_partition_name(
    mailbox: SqlPurchasingMailbox,
    app_sessions: async_sessionmaker[AsyncSession],
    tenancy: Tenancy,
) -> None:
    await _store(mailbox, tenancy.alpha, _mail(), "unscoped.eml")
    async with app_sessions() as session, session.begin():
        for table in _TABLES:
            for name in (table, f"{table}_default"):
                count = await session.scalar(sa.text(f"SELECT count(*) FROM purchasing.{name}"))
                assert count == 0, name


@pytest.mark.parametrize("table", _TABLES)
async def test_a_row_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, table: str
) -> None:
    values = {
        "mailbox_messages": (
            "(tenant_id, workspace_id, message_id, received_at, sender_address,"
            " source_name, message) VALUES (:t, :w, 'eml-x', now(), 'a@b.example', 'x.eml',"
            """ '{"message_id": "eml-x", "sender": {"address": "a@b.example"}}')"""
        ),
        "mailbox_attachments": (
            "(tenant_id, workspace_id, message_id, received_at, attachment_id, content)"
            " VALUES (:t, :w, 'eml-x', now(), 'a1', '\\x00')"
        ),
        "mailbox_files": (
            "(tenant_id, workspace_id, source_name, outcome, reason)"
            " VALUES (:t, :w, 'x.eml', 'refused', 'no')"
        ),
    }[table]
    async with app_sessions() as session, session.begin():
        await _bind(session, tenancy.alpha)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(f"INSERT INTO purchasing.{table} {values}"),
                {"t": tenancy.beta[0], "w": tenancy.beta[1]},
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE purchasing.mailbox_messages SET source_name = 'x.eml'",
        "DELETE FROM purchasing.mailbox_messages",
        "UPDATE purchasing.mailbox_attachments SET content = '\\x00'",
        "DELETE FROM purchasing.mailbox_attachments",
        "UPDATE purchasing.mailbox_files SET outcome = 'stored'",
        "DELETE FROM purchasing.mailbox_files",
    ],
)
async def test_the_application_can_neither_rewrite_nor_remove_mail(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, statement: str
) -> None:
    async with app_sessions() as session, session.begin():
        await _bind(session, tenancy.alpha)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


async def test_an_outcome_outside_the_lanes_is_refused_by_its_check(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    async with app_sessions() as session, session.begin():
        await _bind(session, tenancy.alpha)
        with pytest.raises(DBAPIError, match="ck_mailbox_files_outcome"):
            await session.execute(
                sa.text(
                    "INSERT INTO purchasing.mailbox_files"
                    " (tenant_id, workspace_id, source_name, outcome, message_id)"
                    " VALUES (:t, :w, 'x.eml', 'left_out', 'eml-x')"
                ),
                {"t": tenancy.alpha[0], "w": tenancy.alpha[1]},
            )


# -------------------------------------------------------------- partitions --


async def test_the_partition_lane_makes_this_months_partitions_policed(
    migrator: AsyncEngine,
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
    async with migrator.connect() as conn:
        for table in _TABLES:
            for name in (f"{table}_{date.today():%Y_%m}", f"{table}_default", table):
                facts = await _facts(conn, name)
                assert facts is not None, name
                assert facts.relrowsecurity and facts.relforcerowsecurity, name
                assert "app.workspace_scope" in facts.qual, name
                assert (facts.can_update, facts.can_delete) == (False, False), name


async def _facts(conn: Any, name: str) -> Any:
    return (
        await conn.execute(
            sa.text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity,"
                " (SELECT pg_get_expr(p.polqual, p.polrelid) FROM pg_policy p"
                "  WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation_' || c.relname)"
                "  AS qual,"
                " has_table_privilege('dw_app', c.oid, 'UPDATE') AS can_update,"
                " has_table_privilege('dw_app', c.oid, 'DELETE') AS can_delete"
                " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'purchasing' AND c.relname = :name"
            ),
            {"name": name},
        )
    ).one_or_none()


# --------------------------------------------------------------- retention --


async def test_retention_deletes_one_workspaces_mail_before_its_cutoff_and_no_one_elses(
    mailbox: SqlPurchasingMailbox,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    tenancy: Tenancy,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    old, new = _mail(received=now - timedelta(days=400)), _mail(received=now)
    theirs = _mail(received=now - timedelta(days=400))
    await _store(mailbox, tenancy.alpha, old, "old.eml")
    await _store(mailbox, tenancy.alpha, new, "new.eml")
    await _store(mailbox, tenancy.alpha_other, theirs, "theirs.eml")
    store = SqlRetentionStore(app_sessions)
    # A workspace holding mail and nothing else is visited.
    assert {tenancy.alpha, tenancy.alpha_other} <= set(await store.scopes())

    kept = await store.prune(
        tenancy.alpha, cases_before=None, outcomes_before=None, mail_before=None
    )
    assert kept.mail == 0
    # Files handled just now stay remembered whatever the cutoff for mail:
    # the cutoff is a year back.
    pruned = await store.prune(
        tenancy.alpha,
        cases_before=None,
        outcomes_before=None,
        mail_before=now - timedelta(days=365),
    )

    assert pruned.mail == 1
    me = caller(tenancy.alpha)
    assert await mailbox.get_message(me, old.message.message_id) is None
    assert await mailbox.get_message(me, new.message.message_id) is not None
    other = caller(tenancy.alpha_other)
    assert await mailbox.get_message(other, theirs.message.message_id) is not None
    async with migrator.connect() as conn:
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM purchasing.mailbox_attachments WHERE message_id = :m"),
            {"m": old.message.message_id},
        )
    assert left == 0
    assert {"old.eml", "new.eml"} <= await mailbox.handled_sources(_scope(tenancy.alpha))


async def test_a_workspace_holding_mail_whose_files_are_forgotten_is_still_visited(
    mailbox: SqlPurchasingMailbox,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    tenancy: Tenancy,
) -> None:
    """A mail dated ahead of when it arrived outlives its file's row (files
    go by when they were handled): its workspace must still be swept."""
    await _store(mailbox, tenancy.alpha_other, _mail(), "ahead.eml")
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text("DELETE FROM purchasing.mailbox_files WHERE workspace_id = :w"),
            {"w": tenancy.alpha_other[1]},
        )
    assert tenancy.alpha_other in set(await SqlRetentionStore(app_sessions).scopes())


# ------------------------------------------------------------- offboarding --


async def test_offboarding_exports_every_workspaces_mail_and_its_purge_takes_it(
    mailbox: SqlPurchasingMailbox,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    tenancy: Tenancy,
) -> None:
    mine, other_ws, theirs = _mail(), _mail(), _mail()
    await _store(mailbox, tenancy.alpha, mine, "mine.eml")
    await _store(mailbox, tenancy.alpha_other, other_ws, "other.eml")
    await _store(mailbox, tenancy.beta, theirs, "theirs.eml")
    offboarding = SqlTenantOffboarding(app_sessions)

    exported = {
        (t.schema, t.table): t.rows for t in await offboarding.export_rows(tenancy.alpha[0])
    }
    for table in _TABLES:
        assert ("purchasing", table) in exported, table
    ids = {row["message_id"] for row in exported[("purchasing", "mailbox_messages")]}
    assert ids == {mine.message.message_id, other_ws.message.message_id}

    await offboarding.purge_rows(tenancy.alpha[0])

    async with migrator.connect() as conn:
        for table in _TABLES:
            left = await conn.scalar(
                sa.text(f"SELECT count(*) FROM purchasing.{table} WHERE tenant_id = :t"),
                {"t": tenancy.alpha[0]},
            )
            assert left == 0, table
    assert await mailbox.get_message(caller(tenancy.beta), theirs.message.message_id) is not None
