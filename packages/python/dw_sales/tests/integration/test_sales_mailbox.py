"""DW1's stored mailbox (ticket 43, migration e544ff20fad6) against a real
database, as `dw_app` wherever isolation is the question.

A mail dropped as an `.eml` file is stored once, with its audit event, read
back through the same model, its attachment held to its description; another
tenant or workspace reads none of it; the application can neither rewrite
nor remove it, on any partition; a month is made ahead policed, and a row
stranded in a DEFAULT partition moves to its month with its attachment. The
lane reads a real folder through the reader, in process.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.adapters.drop_folder import LocalDropFolder
from dw_sales.adapters.persistence.mailbox import SqlMailbox
from dw_sales.adapters.reader_client import ClientMailReader
from dw_sales.adapters.readers.mail import read_mail
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.mail_drop import (
    MAIL_DROP_LANE,
    MailDrop,
    MailFile,
    MailIntake,
)
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.integration

_PDF = b"%PDF-1.4 fictional order"


def _eml(
    *,
    subject: str = "PO 4500012345",
    received: datetime | None = None,
    message_id: str | None = None,
    sender: str = "buyer@velatrix.example",
) -> bytes:
    mail = EmailMessage()
    when = received or datetime.now(UTC).replace(microsecond=0)
    mail["Received"] = f"from mail.example by mx.outlook.com; {when:%a, %d %b %Y %H:%M:%S +0000}"
    mail["Authentication-Results"] = "spf=pass; dkim=pass; dmarc=pass action=none"
    mail["From"] = sender
    mail["To"] = "pic@proterial.example"
    mail["Subject"] = subject
    mail["Message-ID"] = message_id or f"<{uuid.uuid4().hex}@velatrix.example>"
    mail.set_content("Kính gửi Proterial, PO đính kèm.")
    mail.add_attachment(_PDF, maintype="application", subtype="pdf", filename="PO.pdf")
    return mail.as_bytes(policy=SMTP)


def _file(data: bytes) -> MailFile:
    read = read_mail(data)
    return MailFile(
        message=read.message,
        contents={k: base64.b64decode(v) for k, v in read.contents.items()},
    )


def _event(scope: SalesScope, mail: MailFile) -> AuditEvent:
    return lane_audit_event(
        lane=MAIL_DROP_LANE,
        event_id=uuid.uuid4(),
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        action="sales.mail.stored",
        resource_type="sales.message",
        resource_id=mail.message.message_id,
        occurred_at=datetime.now(UTC),
        details={"source": "x.eml"},
    )


@pytest.fixture
def mailbox(app_sessions: async_sessionmaker[AsyncSession]) -> SqlMailbox:
    return SqlMailbox(app_sessions, SqlAuditRepository)


async def _store(mailbox: SqlMailbox, scope: SalesScope, mail: MailFile, source: str) -> bool:
    return await mailbox.store(scope, mail, source=source, event=_event(scope, mail))


# ---------------------------------------------------------------- the rows --


async def test_a_mail_is_stored_once_and_read_back_whole(
    mailbox: SqlMailbox, migrator: AsyncEngine, world: World
) -> None:
    mail = _file(_eml())
    event = _event(world.alpha, mail)

    assert await mailbox.store(world.alpha, mail, source="20261027-1.eml", event=event)

    message = mail.message
    assert await mailbox.get_message(world.alpha, message.message_id) == message
    assert message in await mailbox.list_messages(world.alpha)
    content = await mailbox.read_attachment(world.alpha, message.message_id, "a1")
    assert content is not None and content.data == _PDF
    assert await mailbox.read_attachment(world.alpha, message.message_id, "a9") is None
    assert "20261027-1.eml" in await mailbox.handled_sources(world.alpha)
    async with migrator.connect() as conn:
        actor = await conn.scalar(
            sa.text("SELECT details->>'actor' FROM platform.audit_events WHERE id = :id"),
            {"id": event.id},
        )
    assert actor == f"system:{MAIL_DROP_LANE}"


async def test_a_copy_or_the_same_mail_from_another_mailbox_is_not_stored_again(
    mailbox: SqlMailbox, world: World
) -> None:
    data = _eml(message_id="<same@velatrix.example>")
    assert await _store(mailbox, world.alpha, _file(data), "a.eml")
    # The same file again, under another name.
    assert not await _store(mailbox, world.alpha, _file(data), "b.eml")
    # The same mail exported from a second PIC's mailbox: other bytes, same
    # Message-ID, same sender.
    assert not await _store(
        mailbox, world.alpha, _file(_eml(message_id="<same@velatrix.example>")), "c.eml"
    )
    # The same Message-ID from someone else is someone else's mail.
    assert await _store(
        mailbox,
        world.alpha,
        _file(_eml(message_id="<same@velatrix.example>", sender="other@another.example")),
        "d.eml",
    )
    ids = [m.internet_message_id for m in await mailbox.list_messages(world.alpha)]
    assert ids.count("<same@velatrix.example>") == 2


async def test_the_mailbox_is_read_oldest_first(mailbox: SqlMailbox, world: World) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    newer, older = _file(_eml(received=now)), _file(_eml(received=now - timedelta(hours=2)))
    await _store(mailbox, world.alpha, newer, "n.eml")
    await _store(mailbox, world.alpha, older, "o.eml")
    listed = [m.message_id for m in await mailbox.list_messages(world.alpha)]
    assert listed.index(older.message.message_id) < listed.index(newer.message.message_id)


# --------------------------------------------------------------- isolation --


async def test_another_tenant_or_workspace_reads_none_of_it(
    mailbox: SqlMailbox, world: World
) -> None:
    mail = _file(_eml())
    await _store(mailbox, world.alpha, mail, "iso.eml")
    message_id = mail.message.message_id

    for scope in (world.beta, world.alpha_other):
        assert all(m.message_id != message_id for m in await mailbox.list_messages(scope))
        assert await mailbox.get_message(scope, message_id) is None
        assert await mailbox.read_attachment(scope, message_id, "a1") is None
        assert "iso.eml" not in await mailbox.handled_sources(scope)


async def test_a_connection_that_never_scopes_itself_reads_nothing_even_by_partition_name(
    mailbox: SqlMailbox, sales_app_engine: AsyncEngine, world: World
) -> None:
    await _store(mailbox, world.alpha, _file(_eml()), "unscoped.eml")
    async with sales_app_engine.connect() as conn:
        for table in (
            "sales.mailbox_messages",
            "sales.mailbox_messages_default",
            "sales.mailbox_attachments",
            "sales.mailbox_attachments_default",
        ):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0, table


async def _scoped(session: AsyncSession, scope: SalesScope) -> None:
    for key, value in (
        ("app.tenant_id", scope.tenant_id.value),
        ("app.workspace_id", scope.workspace_id.value),
    ):
        await session.execute(
            sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
        )


async def test_a_mail_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with app_sessions() as session, session.begin():
        await _scoped(session, world.alpha)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.mailbox_attachments (tenant_id, workspace_id,"
                    " message_id, received_at, attachment_id, content)"
                    " VALUES (:t, :w, 'eml-x', now(), 'a1', '\\x00')"
                ),
                {"t": world.beta.tenant_id.value, "w": world.beta.workspace_id.value},
            )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.mailbox_messages SET source_name = 'x.eml'",
        "DELETE FROM sales.mailbox_messages",
        "UPDATE sales.mailbox_attachments SET content = '\\x00'",
        "DELETE FROM sales.mailbox_attachments",
    ],
)
async def test_the_application_can_neither_rewrite_nor_remove_mail(
    app_sessions: async_sessionmaker[AsyncSession], world: World, statement: str
) -> None:
    async with app_sessions() as session, session.begin():
        await _scoped(session, world.alpha)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


async def test_a_document_that_disagrees_with_its_keys_is_refused(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    mail = _file(_eml())
    document = mail.message.model_dump(mode="json")
    async with app_sessions() as session, session.begin():
        await _scoped(session, world.alpha)
        with pytest.raises(DBAPIError, match="ck_mailbox_messages_message"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.mailbox_messages (tenant_id, workspace_id, message_id,"
                    " received_at, sender_address, internet_message_id, source_name, message)"
                    " VALUES (:t, :w, 'eml-other', now(), :s, :i, 'x.eml', CAST(:m AS jsonb))"
                ),
                {
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "s": mail.message.sender.address,
                    "i": mail.message.internet_message_id,
                    "m": json.dumps(document),
                },
            )


# -------------------------------------------------------------- partitions --


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
                " WHERE n.nspname = 'sales' AND c.relname = :name"
            ),
            {"name": name},
        )
    ).one_or_none()


async def test_the_platforms_partition_function_makes_this_months_partitions_policed(
    migrator: AsyncEngine,
) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text("SELECT platform.ensure_time_partitions(1)"))
    async with migrator.connect() as conn:
        for table in ("mailbox_messages", "mailbox_attachments"):
            for name in (f"{table}_{date.today():%Y_%m}", f"{table}_default", table):
                facts = await _facts(conn, name)
                assert facts is not None, name
                assert facts.relrowsecurity and facts.relforcerowsecurity, name
                assert "app.workspace_scope" in facts.qual, name
                assert (facts.can_update, facts.can_delete) == (False, False), name


async def test_a_mail_stranded_in_the_default_partition_moves_with_its_attachment(
    mailbox: SqlMailbox, migrator: AsyncEngine, world: World
) -> None:
    """A month made after its rows arrived: the partition function moves them
    out of DEFAULT, which a key between the two tables would have refused or
    cascaded into deleting the attachment."""
    month = date(2031, 7, 1)
    mail = _file(_eml(received=datetime(2031, 7, 9, 8, 0, tzinfo=UTC)))
    await _store(mailbox, world.alpha, mail, "future.eml")
    async with migrator.begin() as conn:
        for table in ("sales.mailbox_messages", "sales.mailbox_attachments"):
            await conn.execute(
                sa.text("SELECT platform._ensure_one_partition(:t, :m)"),
                {"t": table, "m": month},
            )
    async with migrator.connect() as conn:
        moved = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.mailbox_attachments_2031_07 WHERE message_id = :m"),
            {"m": mail.message.message_id},
        )
    assert moved == 1
    content = await mailbox.read_attachment(world.alpha, mail.message.message_id, "a1")
    assert content is not None and content.data == _PDF


# -------------------------------------------------------------- the lane --


class _Intake:
    def __init__(self, intake: MailIntake) -> None:
        self.value = intake

    async def intake(self, scope: SalesScope) -> MailIntake:
        return self.value


class _Notices:
    def __init__(self) -> None:
        self.told: list[str] = []

    async def refused(self, scope: SalesScope, *, source: str, reason: str) -> None:
        self.told.append(source)

    async def unreachable(self, scope: SalesScope, *, day: date) -> None:
        raise AssertionError("the folder was there")


def _drop(
    folder: Path,
    mailbox: SqlMailbox,
    now: datetime,
    intake: MailIntake | None = None,
    notices: _Notices | None = None,
) -> Callable[[], MailDrop]:
    told = notices or _Notices()
    return lambda: MailDrop(
        LocalDropFolder(folder),
        ClientMailReader(InProcessReaderTransport()),
        mailbox,
        _Intake(intake or MailIntake()),
        told,
        FixedClock(now),
        Uuid4Generator(),
    )


def _settled(folder: Path) -> None:
    old = datetime.now(UTC).timestamp() - 120
    for path in folder.rglob("*"):
        os.utime(path, (old, old))


async def test_the_lane_stores_a_dropped_file_once_across_a_restart(
    mailbox: SqlMailbox, world: World, tmp_path: Path
) -> None:
    (tmp_path / "20261027-0900-a.eml").write_bytes(_eml(subject="RFQ 77"))
    (tmp_path / "ghi-chu.txt").write_text("không phải thư", encoding="utf-8")
    _settled(tmp_path)
    new_drop = _drop(tmp_path, mailbox, datetime.now(UTC))

    first = await new_drop().tick(world.alpha)
    again = await new_drop().tick(world.alpha)

    assert first.stored == ("20261027-0900-a.eml",)
    assert again.stored == again.already_stored == ()
    subjects = [m.subject for m in await mailbox.list_messages(world.alpha)]
    assert subjects.count("RFQ 77") == 1


async def test_a_file_the_reader_refuses_is_recorded_with_its_reason_and_told_once(
    mailbox: SqlMailbox, migrator: AsyncEngine, world: World, tmp_path: Path
) -> None:
    (tmp_path / "20261029-0900-x.eml").write_bytes(b"not a mail at all")
    _settled(tmp_path)
    notices = _Notices()
    new_drop = _drop(tmp_path, mailbox, datetime.now(UTC), notices=notices)

    first = await new_drop().tick(world.alpha)
    again = await new_drop().tick(world.alpha)

    assert [name for name, _ in first.refused] == ["20261029-0900-x.eml"]
    assert again.refused == ()
    assert notices.told == ["20261029-0900-x.eml"]
    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT outcome, reason, message_id FROM sales.mailbox_files"
                    " WHERE tenant_id = :t AND source_name = '20261029-0900-x.eml'"
                ),
                {"t": world.alpha.tenant_id.value},
            )
        ).one()
    assert row.outcome == "refused" and row.reason and row.message_id is None


async def test_each_pics_folder_is_read_and_ignored_domains_are_left_out_for_good(
    mailbox: SqlMailbox, migrator: AsyncEngine, world: World, tmp_path: Path
) -> None:
    """Five PICs, a folder each: the lane reads them all. Mail from an ignored
    domain is not kept, and is not parsed again after a restart; Design's,
    from the same domain, is taken."""
    for pic in ("PIC-An", "PIC-Binh"):
        (tmp_path / pic).mkdir()
    (tmp_path / "PIC-An" / "1-po.eml").write_bytes(_eml(subject="PO từ khách"))
    (tmp_path / "PIC-Binh" / "2-noi-bo.eml").write_bytes(
        _eml(subject="Họp giao ban", sender="hr@vn.proterial.example")
    )
    (tmp_path / "PIC-Binh" / "3-design.eml").write_bytes(
        _eml(subject="Re: YCBG-0042", sender="design@proterial.example")
    )
    _settled(tmp_path)
    intake = MailIntake(
        ignored_domains=("proterial.example",), always_from=frozenset({"design@proterial.example"})
    )
    new_drop = _drop(tmp_path, mailbox, datetime.now(UTC), intake)

    first = await new_drop().tick(world.alpha_other)
    again = await new_drop().tick(world.alpha_other)

    assert first.stored == ("1-po.eml", "3-design.eml")
    assert first.left_out == ("2-noi-bo.eml",)
    assert again == type(again)()
    subjects = {m.subject for m in await mailbox.list_messages(world.alpha_other)}
    assert subjects == {"PO từ khách", "Re: YCBG-0042"}
    async with migrator.connect() as conn:
        kept = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM sales.mailbox_messages"
                " WHERE message ->> 'subject' = 'Họp giao ban'"
            )
        )
    assert kept == 0
