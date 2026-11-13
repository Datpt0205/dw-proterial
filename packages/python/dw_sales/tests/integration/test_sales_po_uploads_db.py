""" "Tải PO lên" in the stored mailbox (ticket 18, migration 66c90b900f4a),
against a real database, as `dw_app`.

An upload is stored once with its stamp (who uploaded it, the customer they
chose) and its audit event, and read back through the same model; the same
files again are not stored twice; another tenant or workspace reads none of
it; the stamp cannot be rewritten; and a mail can carry no stamp, nor an
upload go without one: `ck_mailbox_messages_upload` holds the two to the id.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.persistence.mailbox import SqlMailbox
from dw_sales.application.mail_drop import MailFile
from dw_sales.application.order_ports import PoUpload
from dw_sales.application.po_uploads import PO_UPLOADED, UploadedFile, upload_message
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.integration

EXPORT = b"\xff\xfe" + "PO No.\tPart No.\tPO Type\nCVG-PO-1\tCVG-0001\tFirm\n".encode("utf-16-le")
UPLOADER = uuid.UUID(int=0xA1)


def _upload(scope: SalesScope, data: bytes = EXPORT) -> tuple[MailFile, PoUpload, AuditEvent]:
    mail = upload_message(
        [UploadedFile("ORD.csv", data)], "an.nguyen@alpha.local", datetime.now(UTC)
    )
    event = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=TenantId(scope.tenant_id.value),
        workspace_id=WorkspaceId(scope.workspace_id.value),
        actor_id=UserId(UPLOADER),
        action=PO_UPLOADED,
        resource_type="sales_message",
        resource_id=mail.message.message_id,
        occurred_at=datetime.now(UTC),
        details={"customer_code": "CVG", "files": 1},
    )
    return mail, PoUpload(customer_code="CVG", uploaded_by=UPLOADER), event


@pytest.fixture
def mailbox(app_sessions: async_sessionmaker[AsyncSession]) -> SqlMailbox:
    return SqlMailbox(app_sessions, SqlAuditRepository)


async def test_an_upload_is_stored_once_with_its_stamp_and_audit(
    mailbox: SqlMailbox, migrator: AsyncEngine, world: World
) -> None:
    mail, upload, event = _upload(world.alpha)

    assert await mailbox.store_upload(world.alpha, mail, upload, event=event)
    message_id = mail.message.message_id
    assert await mailbox.upload_of(world.alpha, message_id) == upload
    assert await mailbox.get_message(world.alpha, message_id) == mail.message
    content = await mailbox.read_attachment(world.alpha, message_id, "A1")
    assert content is not None and content.data == EXPORT

    # The same file again, later: the same id, nothing written.
    again, _, second = _upload(world.alpha)
    assert not await mailbox.store_upload(world.alpha, again, upload, event=second)
    async with migrator.connect() as conn:
        rows = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.mailbox_messages WHERE message_id = :m"),
            {"m": message_id},
        )
        audited = await conn.scalar(
            sa.text("SELECT count(*) FROM platform.audit_events WHERE resource_id = :m"),
            {"m": message_id},
        )
    assert (rows, audited) == (1, 1)


async def test_a_mail_has_no_upload_stamp(mailbox: SqlMailbox, world: World) -> None:
    assert await mailbox.upload_of(world.alpha, "eml-" + "0" * 64) is None


async def test_another_tenant_or_workspace_reads_none_of_it(
    mailbox: SqlMailbox, world: World
) -> None:
    mail, upload, event = _upload(world.alpha, EXPORT + "x".encode("utf-16-le"))
    await mailbox.store_upload(world.alpha, mail, upload, event=event)
    message_id = mail.message.message_id
    for scope in (world.beta, world.alpha_other):
        assert await mailbox.upload_of(scope, message_id) is None
        assert await mailbox.get_message(scope, message_id) is None


async def _scoped(session: AsyncSession, scope: SalesScope) -> None:
    for key, value in (
        ("app.tenant_id", scope.tenant_id.value),
        ("app.workspace_id", scope.workspace_id.value),
    ):
        await session.execute(
            sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
        )


async def test_the_stamp_cannot_be_rewritten(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with app_sessions() as session, session.begin():
        await _scoped(session, world.alpha)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text("UPDATE sales.mailbox_messages SET uploaded_for = 'VLX'"))


@pytest.mark.parametrize(
    ("message_id", "uploaded_by", "uploaded_for"),
    [
        # A mail claiming an upload's stamp.
        ("eml-forged", str(UPLOADER), "CVG"),
        # An upload's id with no stamp.
        ("upload-unstamped", None, None),
        # Half a stamp.
        ("upload-half", str(UPLOADER), None),
        # A customer code no master data has the shape of.
        ("upload-bad-code", str(UPLOADER), "cvg; drop"),
    ],
)
async def test_a_stamp_goes_with_an_upload_id_only(
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    message_id: str,
    uploaded_by: str | None,
    uploaded_for: str | None,
) -> None:
    mail, _, _ = _upload(world.alpha)
    document = mail.message.model_dump(mode="json")
    document["message_id"] = message_id
    async with app_sessions() as session, session.begin():
        await _scoped(session, world.alpha)
        with pytest.raises(DBAPIError, match="ck_mailbox_messages_upload"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.mailbox_messages (tenant_id, workspace_id, message_id,"
                    " received_at, sender_address, source_name, message, uploaded_by,"
                    " uploaded_for) VALUES (:t, :w, :id, now(), :s, 'ORD.csv',"
                    " CAST(:m AS jsonb), CAST(:by AS uuid), :for)"
                ),
                {
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "id": message_id,
                    "s": document["sender"]["address"],
                    "m": json.dumps(document),
                    "by": uploaded_by,
                    "for": uploaded_for,
                },
            )
