"""The head's page of DW1's prompt versions through the API, against
PostgreSQL (ticket 43).

The optimiser lane proposes (here: the lane's own engine call, as
`PromptOptimiser.tick` makes it); the head reads each version beside the one
in force on `GET /sales/prompts` and decides it on `/approvals`; the worker
carries the decision out (`_carry_out` does here what the worker does), and
only then does a reading of this tenant show the version's lines.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, BETA, GIANG, TAM, Api
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleVersionEngine
from dw_platform.domain.audit import system_actor
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.assembly import build_prompt_settlement
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.model_reading import Demonstrations
from dw_sales.application.ports import SalesScope
from dw_sales.application.prompt_optimiser import OPTIMISER_LANE
from dw_sales.application.prompt_versions import (
    PROMPT_KEY,
    PROMPTS_DECIDED,
    REGISTRY,
    prompt_book,
)
from dw_sales.application.rules import ProposerNames, rule_work

pytestmark = pytest.mark.integration


def _scope(tenant: str) -> SalesScope:
    return SalesScope(
        TenantId(sid("tenant", tenant)), WorkspaceId(sid("workspace", f"{tenant}:main"))
    )


ALPHA_SCOPE = _scope("tenant-alpha")
BETA_SCOPE = _scope(BETA)
CASE = uuid.uuid4()
LABEL = uuid.uuid4()
GREEN = {
    "description": "Dây điện AWG20 màu xanh lá",
    "prv_code": "HW-1011",
    "label_id": str(LABEL),
    "case_id": str(CASE),
    "customer_code": "C001",
}


class _NoNames:
    async def list_members(self, context: AccessContext) -> list[Any]:
        return []


def _lane(scope: SalesScope) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(OPTIMISER_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


async def _propose(api: Api, scope: SalesScope, version: str) -> str:
    """The lane's proposal, as `PromptOptimiser.tick` writes it: the
    approval it waits on."""
    uow = SqlSalesUnitOfWorkFactory(
        api.sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
    )
    engine = RuleVersionEngine(
        REGISTRY,
        rule_work(uow),
        prompt_book(SqlRuleVersionLookup(api.sessions)),
        SystemClock(),
        Uuid4Generator(),
        ProposerNames(_NoNames()),
    )
    document = {
        "schema_version": "1.0",
        "policy_id": PROMPT_KEY,
        "policy_version": version,
        "demonstrations": [GREEN],
        "replay": {"cases": 20, "right_before": 0, "right_after": 19, "security_cases": 9},
    }
    proposed = await engine.propose(_lane(scope), PROMPT_KEY, document, applies_directly=False)
    assert proposed.approval_id is not None
    return str(proposed.approval_id)


async def _carry_out(api: Api, migrator: AsyncEngine, approval_id: str) -> str:
    """What the worker does with the decision's outbox event."""
    async with migrator.connect() as conn:
        event = (
            await conn.execute(
                sa.text(
                    "SELECT tenant_id, workspace_id, payload FROM platform.outbox_events"
                    " WHERE event_type = :type AND aggregate_id = :id"
                ),
                {"type": PROMPTS_DECIDED, "id": approval_id},
            )
        ).one()
    settlement = build_prompt_settlement(
        session_factory=api.sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        clock=SystemClock(),
        ids=Uuid4Generator(),
    )
    decider = AccessContext(
        tenant_id=event.tenant_id,
        workspace_id=event.workspace_id,
        principal_id=uuid.UUID(event.payload["decided_by"]),
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
    return (await settlement.settle(uuid.UUID(approval_id), decider)).status


@pytest.fixture
async def prompts_api(api: Api, migrator: AsyncEngine) -> AsyncIterator[Api]:
    """No other test's readings run under a version these tests approve."""
    try:
        yield api
    finally:
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM platform.rule_versions WHERE key = :key"), {"key": PROMPT_KEY}
            )


async def test_the_head_reads_a_proposal_and_it_is_served_only_once_approved(
    prompts_api: Api, migrator: AsyncEngine
) -> None:
    api = prompts_api
    giang = api.as_(GIANG)
    book = prompt_book(SqlRuleVersionLookup(api.sessions))
    alpha_approval = await _propose(api, ALPHA_SCOPE, "1.3.0")
    await _propose(api, BETA_SCOPE, "1.3.0")

    listed = await giang.get("/prompts")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert (body["in_force"], body["layer"], body["demonstrations"]) == (
        "sales_prompt_description_attributes@1.2.0",
        "platform",
        [],
    )
    # Beta's proposal is beta's: alpha's head lists alpha's one only.
    (version,) = body["versions"]
    assert (version["status"], version["approval_id"]) == ("proposed", alpha_approval)
    assert version["replay"]["right_after"] == 19
    assert version["demonstrations"] == [GREEN]
    # Waiting on the head: no reading of either tenant shows it.
    for scope in (ALPHA_SCOPE, BETA_SCOPE):
        assert await book.demonstrations(scope) == Demonstrations(None)

    # Another tenant's member cannot even see alpha's approval.
    decision = {"approve": True, "comment": "Đồng ý"}
    assert (await api.as_(BAO, BETA).decide(alpha_approval, decision)).status_code == 404

    key = str(uuid.uuid4())
    approved = await giang.decide(alpha_approval, decision, key=key)
    assert approved.status_code == 200, approved.text
    replayed = await giang.decide(alpha_approval, decision, key=key)
    assert (replayed.status_code, replayed.json()) == (200, approved.json())
    # Recorded, not carried out: still the platform's.
    assert await book.demonstrations(ALPHA_SCOPE) == Demonstrations(None)
    assert await _carry_out(api, migrator, alpha_approval) == "approved"
    assert await _carry_out(api, migrator, alpha_approval) == "approved"  # redelivered

    served = await book.demonstrations(ALPHA_SCOPE)
    assert served.version == "1.3.0"
    assert [(d.description, d.prv_code) for d in served.shown] == [
        (GREEN["description"], GREEN["prv_code"])
    ]
    assert await book.demonstrations(BETA_SCOPE) == Demonstrations(None)
    body = (await giang.get("/prompts")).json()
    assert (body["in_force"], body["layer"]) == (
        "sales_prompt_description_attributes@1.3.0",
        "tenant",
    )
    assert body["versions"][0]["decided_by"] is not None

    # A rejected one changes nothing served.
    second = await _propose(api, ALPHA_SCOPE, "1.4.0")
    rejected = await giang.decide(second, {"approve": False, "comment": "Chưa đủ"})
    assert rejected.status_code == 200, rejected.text
    assert await _carry_out(api, migrator, second) == "rejected"
    assert (await book.demonstrations(ALPHA_SCOPE)).version == "1.3.0"

    async with migrator.connect() as conn:
        actions = set(
            (
                await conn.execute(
                    sa.text(
                        "SELECT action FROM platform.audit_events"
                        " WHERE tenant_id = :tenant AND action LIKE 'sales.prompts.%'"
                    ),
                    {"tenant": ALPHA_SCOPE.tenant_id.value},
                )
            ).scalars()
        )
    assert {"sales.prompts.proposed", "sales.prompts.approved", "sales.prompts.rejected"} <= actions


async def test_a_caller_without_the_heads_scope_reads_no_version(prompts_api: Api) -> None:
    """A PIC, and tenant IT who proposes rules, are refused: the lines carry
    customers' words, and deciding them is the head's."""
    await _propose(prompts_api, ALPHA_SCOPE, "1.3.0")

    for subject in (AN, TAM):
        refused = await prompts_api.as_(subject).get("/prompts")
        assert refused.status_code == 403, subject
        assert "Dây điện" not in refused.text
