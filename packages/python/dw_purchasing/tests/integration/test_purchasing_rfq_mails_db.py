"""DW2's RFQ mails (migration da6950544c81) on PostgreSQL, as `dw_app`.

One active mail per supplier of a case (a failed one sent again); a mail is
written only while queued and settled once, its audit event beside it;
another tenant or workspace reads none, a connection that never scoped
itself reads nothing; the application never deletes one, and a case taken
by its term takes its mails with it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_purchasing.adapters.persistence.rfq_mails import SqlRfqMails
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.application.rfq_mail import OUTBOUND_LANE, QUEUED, RfqMail
from dw_purchasing.domain.cases import CaseStatus, PrSource, PurchaseCase
from dw_purchasing.domain.requests import PrLine, PurchaseRequest
from dw_purchasing.testing.world import caller

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 3, 7, 0, tzinfo=UTC)


def _scope(pair: tuple[uuid.UUID, uuid.UUID]) -> ContextScope:
    return ContextScope(TenantId(pair[0]), WorkspaceId(pair[1]))


async def _case(
    sessions: async_sessionmaker[AsyncSession], pair: tuple[uuid.UUID, uuid.UUID]
) -> uuid.UUID:
    case = PurchaseCase(
        case_id=uuid.uuid4(),
        case_version=1,
        status=CaseStatus.RECEIVED,
        source=PrSource.FORM,
        request=PurchaseRequest(
            pr_no="PR-2611-031",
            department="Kho",
            requester="Trần Văn Kho",
            currency="VND",
            lines=(PrLine(line_no=1, description="Găng tay", quantity=Decimal(40), unit="đôi"),),
        ),
        received_at=NOW,
        received_by=uuid.UUID(int=0xB0B),
        rules_ref="purchasing_rules@1.0.0",
    )
    store = SqlPurchasingStore(sessions, SqlAuditRepository, SqlApprovalRepository)
    async with store(caller(pair)) as work:
        await work.cases.add(case)
    return case.case_id


def _mail(case_id: uuid.UUID, supplier: str = "NCC-A", *, later: int = 0) -> RfqMail:
    return RfqMail(
        mail_id=uuid.uuid4(),
        case_id=case_id,
        supplier_code=supplier,
        mailbox="buyer@alpha.local",
        recipients=("sales@anphat.vn",),
        subject="Hỏi giá găng tay",
        body="Kính gửi An Phát, ...",
        status="queued",
        queued_by=uuid.uuid4(),
        queued_at=NOW + timedelta(seconds=later),
    )


def _event(pair: tuple[uuid.UUID, uuid.UUID], mail: RfqMail) -> AuditEvent:
    return lane_audit_event(
        lane=OUTBOUND_LANE,
        event_id=uuid.uuid4(),
        tenant_id=TenantId(pair[0]),
        workspace_id=WorkspaceId(pair[1]),
        action=QUEUED,
        resource_type="purchasing_rfq_mail",
        resource_id=str(mail.mail_id),
        occurred_at=NOW,
    )


@pytest.fixture
def mails(app_sessions: async_sessionmaker[AsyncSession]) -> SqlRfqMails:
    return SqlRfqMails(app_sessions, SqlAuditRepository)


async def test_one_active_mail_per_supplier_and_a_failed_one_is_sent_again(
    mails: SqlRfqMails, app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    case_id = await _case(app_sessions, tenancy.alpha)
    first = _mail(case_id)
    await mails.add(first, _event(tenancy.alpha, first))
    with pytest.raises(ConflictError):
        again = _mail(case_id)
        await mails.add(again, _event(tenancy.alpha, again))
    scope = _scope(tenancy.alpha)
    assert await mails.written(scope, first.mail_id, at=NOW)
    assert not await mails.written(scope, first.mail_id, at=NOW)
    assert await mails.settle(
        scope,
        first.mail_id,
        status="failed",
        error="flow_failed",
        at=NOW,
        event=_event(tenancy.alpha, first),
    )
    assert not await mails.settle(
        scope,
        first.mail_id,
        status="sent",
        error=None,
        at=NOW,
        event=_event(tenancy.alpha, first),
    )

    # Pressed after the first failed: listed after it, whatever the ids.
    retry = _mail(case_id, later=1)
    await mails.add(retry, _event(tenancy.alpha, retry))

    assert [m.status for m in await mails.of_case(scope, case_id)] == ["failed", "queued"]
    assert [m.mail_id for m in await mails.pending(scope)] == [retry.mail_id]


async def test_another_tenant_or_workspace_reads_none_and_unscoped_reads_nothing(
    mails: SqlRfqMails,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    tenancy: Tenancy,
) -> None:
    case_id = await _case(app_sessions, tenancy.alpha)
    mail = _mail(case_id)
    await mails.add(mail, _event(tenancy.alpha, mail))

    for other in (tenancy.alpha_other, tenancy.beta):
        assert await mails.get(_scope(other), mail.mail_id) is None
        assert await mails.pending(_scope(other)) == []
        assert not await mails.written(_scope(other), mail.mail_id, at=NOW)
    async with app_sessions() as session:
        assert await session.scalar(sa.text("SELECT count(*) FROM purchasing.rfq_mails")) == 0


async def test_the_application_cannot_delete_a_mail_and_a_case_takes_its_mails(
    mails: SqlRfqMails,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    tenancy: Tenancy,
) -> None:
    case_id = await _case(app_sessions, tenancy.alpha)
    mail = _mail(case_id)
    await mails.add(mail, _event(tenancy.alpha, mail))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_sessions() as session, session.begin():
            await session.execute(sa.text("DELETE FROM purchasing.rfq_mails"))

    async with migrator.begin() as conn:
        await conn.execute(sa.text("DELETE FROM purchasing.cases WHERE id = :c"), {"c": case_id})
        left = await conn.scalar(
            sa.text("SELECT count(*) FROM purchasing.rfq_mails WHERE case_id = :c"), {"c": case_id}
        )
    assert left == 0


@pytest.mark.parametrize(
    ("status", "error", "written", "settled"),
    [
        ("sent", None, True, False),
        ("failed", None, True, True),
        ("queued", None, True, False),
        ("done", None, False, False),
    ],
    ids=["sent_unsettled", "failed_without_why", "queued_written", "status"],
)
async def test_a_status_and_its_times_agree_by_constraint(
    migrator: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    tenancy: Tenancy,
    status: str,
    error: str | None,
    written: bool,
    settled: bool,
) -> None:
    case_id = await _case(app_sessions, tenancy.alpha)
    with pytest.raises(DBAPIError, match="ck_rfq_mails_"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO purchasing.rfq_mails (id, tenant_id, workspace_id, case_id,"
                    " supplier_code, mailbox, recipients, subject, body, status, error,"
                    " queued_by, queued_at, written_at, settled_at) VALUES (:i, :t, :w, :c,"
                    " 'NCC-A', 'buyer@alpha.local', '[\"a@b.vn\"]', 's', 'b', :s, :e, :u, now(),"
                    " CASE WHEN :wr THEN now() END, CASE WHEN :st THEN now() END)"
                ),
                {
                    "i": uuid.uuid4(),
                    "t": tenancy.alpha[0],
                    "w": tenancy.alpha[1],
                    "c": case_id,
                    "s": status,
                    "e": error,
                    "u": uuid.uuid4(),
                    "wr": written,
                    "st": settled,
                },
            )
