"""DW02 function 3 on PostgreSQL, as `dw_app` under RLS: an approved request's
RFQs drafted, suppliers' replies read into offers, a supplier chosen per
line, all on the SQL store; the catalog refuses a sourcing state without what
it must hold."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import NotFoundError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.policy_overrides import SqlPolicyOverrideRepository
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.domain.approval import ApprovalStatus
from dw_purchasing.adapters.assembly import request_settlement
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import Gate
from dw_purchasing.application.approvals import RequestApprovals
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.rules import RuleBook
from dw_purchasing.application.sourcing import SupplierSourcing
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.domain.sourcing import Choice
from dw_purchasing.testing.world import Authz, ScriptedModel, caller

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
FIXTURES = REPO / "evals/fixtures/cases"
INTAKE = json.loads((FIXTURES / "purchasing_pr_intake.json").read_text(encoding="utf-8"))
SOURCING = json.loads((FIXTURES / "purchasing_sourcing.json").read_text(encoding="utf-8"))
HEAD = uuid.UUID(int=0x4EAD)


async def _decide_as_platform(
    sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, approval_id: uuid.UUID
) -> None:
    """The approval row decided, as `ApproveAndResumeService` leaves it (its
    own suite tests that path; this one tests what follows)."""
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenancy.alpha[0])}
        )
        await session.execute(
            sa.text("UPDATE platform.approval_requests SET status = :s WHERE id = :i"),
            {"s": ApprovalStatus.APPROVED.value, "i": approval_id},
        )


async def test_suppliers_are_asked_their_replies_read_and_one_chosen_per_line(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy, migrator: object
) -> None:
    files = PolicyFiles.load(REPO / "configs/policies")
    store = SqlPurchasingStore(app_sessions, SqlAuditRepository, SqlApprovalRepository)
    book = RuleBook(files, SqlPolicyOverrideRepository(app_sessions), files.versions)
    clock, ids = FixedClock(NOW), Uuid4Generator()
    model = ScriptedModel(INTAKE["answers"])
    model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
    }
    inbox = MockInbox.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1])
    master = MockMasterData.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1])
    worker = Worker("purchasing-dw2", "1.0.0")
    intake = PurchaseRequests(store, Gate(Authz()), book, inbox, model, worker, clock, ids)
    approvals = RequestApprovals(store, Gate(Authz()), book, master, clock, ids)
    sourcing = SupplierSourcing(
        store, Gate(Authz()), book, master, inbox, model, worker, clock, ids
    )
    me = caller(tenancy.alpha)

    case_id = (await intake.read_mail(me, "P01")).case_id
    assert case_id is not None
    await approvals.submit(me, case_id, case_version=1)
    sent = await intake.case(me, case_id)
    assert sent.approval is not None
    await _decide_as_platform(app_sessions, tenancy, sent.approval.approval_id)
    await request_settlement(
        app_sessions, SqlAuditRepository, SqlApprovalRepository, clock, ids
    ).settle(sent.approval.approval_id, caller(tenancy.alpha, principal=HEAD))

    await sourcing.draft_rfq(me, case_id, case_version=3)
    for message_id in ("Q01", "Q02", "Q03"):
        version = (await intake.case(me, case_id)).case_version
        await sourcing.read_offer_mail(me, case_id, message_id, case_version=version)
    view = await sourcing.comparison(me, case_id)
    assert [o.supplier_code for o in view.lines[0].offers] == ["KIMURA", "ANPHAT"]
    version = (await intake.case(me, case_id)).case_version
    await sourcing.select(
        me,
        case_id,
        [
            Choice(line_no=1, supplier_code="KIMURA"),
            Choice(line_no=2, supplier_code="BAOHO"),
            Choice(line_no=3, supplier_code="ANPHAT"),
        ],
        case_version=version,
    )
    chosen = await intake.case(me, case_id)
    assert chosen.status is CaseStatus.SUPPLIER_SELECTED and chosen.selection is not None
    assert chosen.selection.total == Decimal(14_200_000)
    # BAOHO's unasked BK-1700 was left out.
    assert {(o.supplier_code, o.line_no) for o in chosen.offers} == {
        ("KIMURA", 1),
        ("ANPHAT", 1),
        ("ANPHAT", 3),
        ("BAOHO", 2),
    }

    # Another workspace sees none of it.
    with pytest.raises(NotFoundError):
        await sourcing.comparison(caller(tenancy.alpha_other), case_id)

    # The catalog refuses a sourcing state without its round or its choice.
    async with store(me) as work:
        session = work.cases._session  # the scoped transaction
        for patch in (
            "body = body - 'selection'",
            "status = 'rfq_drafted'",
            "body = jsonb_set(body, '{rfq}', 'null')",
        ):
            with pytest.raises(sa.exc.DBAPIError, match="ck_cases_sourced"):
                async with session.begin_nested():
                    await session.execute(
                        sa.text(f"UPDATE purchasing.cases SET {patch} WHERE id = :i"),
                        {"i": case_id},
                    )
