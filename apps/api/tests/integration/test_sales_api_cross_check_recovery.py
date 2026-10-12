"""An order whose cross-check decision failed to apply can be cross-checked
again (ticket 14), through the routes and the database.

The decision passes the Sales guard, the platform records it, and the case
version moves before DW1's run applies it (An acknowledges NOC/ESF in that
instant): the run fails and the approval stays decided. The order then says
the decision was not applied and why, the audit names the run, the approval
and the reason, and "Gửi kiểm chéo lại" raises a new approval.

Negatives: raising it again while one is pending (409), by a PIC who made
none of the order (403), and from another tenant's workspace (404).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, BETA, DIEU, GIANG, Api, Persona
from sales_flow import cross_check, cross_checked, open_sources, order, order_of, uploaded
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_agent_runtime.approval_flow import ApprovalDecisionGuard, ProposedDecision
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.application.runs import APPROVAL_PREFIX

pytestmark = pytest.mark.integration

NOC = "missing_noc_esf:-"


async def _dispose(an: Persona, case_id: str, key: str, reason: str) -> None:
    current = await order(an, case_id)
    response = await an.post(
        f"/orders/{case_id}/findings/{key}/disposition",
        {"case_version": current["case_version"], "disposition": "accepted", "reason": reason},
    )
    assert response.status_code == 200, response.text


async def _uploaded_m03(an: Persona) -> dict[str, Any]:
    """M03 prepared and recorded in Bravo by An, NOC/ESF left open."""
    case = await order_of(an, "M03")
    await _dispose(an, case["case_id"], "quotation_missing:2", "Giá theo báo giá gia hạn")
    return await uploaded(an, await order(an, case["case_id"]))


class _BumpAfterCheck:
    """The Sales guard, then An acknowledges NOC/ESF before the run resumes."""

    def __init__(self, inner: ApprovalDecisionGuard, an: Persona, case_id: str) -> None:
        self.inner, self.an, self.case_id = inner, an, case_id

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        await self.inner.check(request, decision, context)
        await _dispose(self.an, self.case_id, NOC, "Khách đã gửi NOC năm nay")


async def _stalled(api: Api) -> dict[str, Any]:
    an, dieu = api.as_(AN), api.as_(DIEU)
    up = await _uploaded_m03(an)
    await open_sources(dieu, up)
    guards = api.approval_flow.decision_guards
    inner = guards[APPROVAL_PREFIX]
    guards[APPROVAL_PREFIX] = _BumpAfterCheck(inner, an, up["case_id"])
    try:
        refused = await cross_check(dieu, up)
    finally:
        guards[APPROVAL_PREFIX] = inner
    # The decision was recorded; its apply was refused, and the decider is told.
    assert refused.status_code == 409, refused.text
    return await order(an, up["case_id"])


async def test_a_failed_apply_is_said_on_the_order_and_its_cross_check_is_raised_again(
    api: Api, migrator: AsyncEngine
) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    stuck = await _stalled(api)

    assert stuck["status"] == "uploaded_to_bravo"
    assert stuck["decision"] is None
    assert stuck["cross_check_stalled"] is True
    unapplied = stuck["unapplied_decision"]
    assert unapplied["reason_code"] == "stale_case_version"
    assert unapplied["decided_by"] == str(dieu.id) and unapplied["approved"] is True

    async with migrator.connect() as conn:
        (row,) = (
            await conn.execute(
                sa.text(
                    "SELECT run_id, details FROM platform.audit_events"
                    " WHERE action = 'sales.order.decision_not_applied' AND resource_id = :id"
                ),
                {"id": stuck["case_id"]},
            )
        ).all()
        (run_status,) = (
            await conn.execute(
                sa.text("SELECT status FROM platform.worker_runs WHERE id = :id"),
                {"id": row.run_id},
            )
        ).one()
        (approval_status,) = (
            await conn.execute(
                sa.text("SELECT status FROM platform.approval_requests WHERE id = :id"),
                {"id": row.details["approval_id"]},
            )
        ).one()
    assert row.details["reason_code"] == "stale_case_version"
    assert row.details["approval_id"] == unapplied["approval_id"]
    assert str(row.run_id) == unapplied["run_id"]
    assert (run_status, approval_status) == ("failed", "approved")
    # Ids and codes only.
    assert set(row.details) <= {
        "case_kind",
        "case_version",
        "from_status",
        "to_status",
        "actor_kind",
        "worker_id",
        "worker_version",
        "reason_code",
        "approval_id",
    }

    # Diệu made none of the order: she may not raise it again (she may decide it).
    refused = await dieu.post(
        f"/orders/{stuck['case_id']}/resend-cross-check",
        {"case_version": stuck["case_version"]},
    )
    assert refused.status_code == 403, refused.text

    resent = await an.post(
        f"/orders/{stuck['case_id']}/resend-cross-check",
        {"case_version": stuck["case_version"]},
    )
    assert resent.status_code == 200, resent.text
    again = await order(an, stuck["case_id"])
    assert again["decision"] is not None
    assert again["decision"]["approval_id"] != unapplied["approval_id"]
    assert (again["cross_check_stalled"], again["unapplied_decision"]) == (False, None)

    # Whoever decided the failed one decides the new one, at the version now.
    done = await cross_checked(dieu, again)
    assert done["status"] == "cross_checked"
    assert done["cross_checked_by"] == str(dieu.id)


@pytest.mark.parametrize(
    "change",
    [
        # A key the domain's record does not have: a comment would travel there.
        """unapplied_decision || '{"comment": "Sai số SO"}'""",
        "unapplied_decision - 'reason_code'",
        """jsonb_set(unapplied_decision, '{reason_code}', '"0.6980 USD"')""",
    ],
)
async def test_the_database_holds_a_decision_not_applied_to_ids_and_codes(
    api: Api, migrator: AsyncEngine, change: str
) -> None:
    stuck = await _stalled(api)

    with pytest.raises(IntegrityError) as refused:
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    f"UPDATE sales.order_cases SET unapplied_decision = {change} WHERE id = :id"
                ),
                {"id": stuck["case_id"]},
            )

    assert "ck_order_cases_unapplied_decision" in str(refused.value)


async def test_the_head_raises_it_again_for_the_recorder(api: Api) -> None:
    giang = api.as_(GIANG)
    stuck = await _stalled(api)

    resent = await giang.post(
        f"/orders/{stuck['case_id']}/resend-cross-check",
        {"case_version": stuck["case_version"]},
    )

    assert resent.status_code == 200, resent.text
    assert (await order(giang, stuck["case_id"]))["decision"] is not None


async def test_raising_it_again_while_one_is_pending_is_refused(api: Api) -> None:
    an = api.as_(AN)
    up = await _uploaded_m03(an)

    refused = await an.post(
        f"/orders/{up['case_id']}/resend-cross-check", {"case_version": up["case_version"]}
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["details"]["rule"] == "cross_check_pending"
    assert (await order(an, up["case_id"]))["decision"] is not None


async def test_another_tenants_workspace_cannot_find_the_order(api: Api) -> None:
    stuck = await _stalled(api)
    # Bảo is a Sales PIC with every PIC scope, in tenant beta.
    bao = api.as_(BAO, BETA)

    refused = await bao.post(
        f"/orders/{stuck['case_id']}/resend-cross-check",
        {"case_version": stuck["case_version"]},
    )

    assert refused.status_code == 404, refused.text
    assert (await order(api.as_(AN), stuck["case_id"]))["cross_check_stalled"] is True


async def test_bravo_entry_on_an_order_in_bravo_withdraws_nothing(api: Api) -> None:
    an = api.as_(AN)
    up = await _uploaded_m03(an)

    refused = await an.post(
        f"/orders/{up['case_id']}/bravo-entry",
        {"case_version": up["case_version"], "entry_compared": True},
    )

    assert refused.status_code == 409, refused.text
    assert (await order(an, up["case_id"]))["decision"] is not None
