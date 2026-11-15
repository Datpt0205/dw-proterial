"""DW1's skills against PostgreSQL (ticket 40, migration 80584b911796): a
tenant's version of a skill is a row of `platform.rule_versions`, and what
the database owns about it.

- The key is one the table admits; the row is held by its RLS: another
  tenant's run resolves the platform's skill, never this tenant's.
- The proposer of a version never decides it, whatever writes the row
  (`ck_rule_versions_checker_not_maker`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sales_harness import World
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleVersion
from dw_sales.application.skills import SKILLS_APPROVAL, skill_book, skill_key

pytestmark = pytest.mark.integration

SKILLS = load_dw1_skills(Path(__file__).resolve().parents[5] / "configs" / "skills" / "dw1")
KEY = skill_key("thread-intents")
NOW = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
MAKER, CHECKER = uuid.UUID(int=0x40A), uuid.UUID(int=0x40B)


def _run(scope: SalesScope) -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        actor_id=uuid.UUID(int=0xA1),
        worker_id="sales-dw1",
        worker_version="1.0.0",
        channel="eval",
        plan_id="professional",
        roles=frozenset(),
        scopes=frozenset({"sales.inbox.process"}),
        trace_id="ticket-40",
        autonomy_level="A1",
        approval_policy_version="1.0.0",
    )


async def _opened(work: Any, scope: SalesScope) -> uuid.UUID:
    """The `sales.skills` approval a proposal waits on (a proposed version
    names one, `ck_rule_versions_proposed_has_approval`)."""
    approval_id = uuid.uuid4()
    await work.approvals.add(
        ApprovalRequest(
            id=approval_id,
            tenant_id=TenantId(scope.tenant_id.value),
            workspace_id=WorkspaceId(scope.workspace_id.value),
            approval_type=SKILLS_APPROVAL,
            requested_by=UserId(MAKER),
            reason="ticket 40",
            payload={},
            required_scope="sales.rules.approve",
        )
    )
    return approval_id


def _proposed(version: str, words: str, approval_id: uuid.UUID) -> RuleVersion:
    platform = SKILLS.skills[KEY]
    document = platform.model_copy(update={"policy_version": version, "instructions": words})
    return RuleVersion(
        version_id=uuid.uuid4(),
        key=KEY,
        version=version,
        document=document.model_dump(mode="json"),
        status="proposed",
        proposed_by=MAKER,
        proposed_at=NOW,
        approval_id=approval_id,
    )


def _decided(version: RuleVersion, by: uuid.UUID) -> RuleVersion:
    return RuleVersion.model_validate(
        {**version.model_dump(), "status": "approved", "decided_by": by, "decided_at": NOW}
    )


async def test_an_approved_skill_is_its_tenants_and_never_another_tenants(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> None:
    words = f"ALPHA's own words {uuid.uuid4()}."
    version = f"7.{uuid.uuid4().int % 1000}.0"
    async with uow(world.alpha) as work:
        proposed = _proposed(version, words, await _opened(work, world.alpha))
        await work.rule_versions.add(proposed)
        await work.rule_versions.decide(_decided(proposed, CHECKER), superseding=None)
        await work.commit()
    book = skill_book(SKILLS, SqlRuleVersionLookup(app_sessions))
    alpha = (await book.skill_set(_run(world.alpha))).named("thread-intents")
    assert alpha is not None and (alpha.ref, alpha.body) == (f"{KEY}@{version}", words)
    other = (await book.skill_set(_run(world.beta))).named("thread-intents")
    assert other is not None and other.ref == SKILLS.skills[KEY].ref
    assert other.body != words


async def test_the_proposer_never_decides_their_own_skill_whatever_writes_the_row(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    async with uow(world.beta) as work:
        proposed = _proposed(
            f"8.{uuid.uuid4().int % 1000}.0", "Words.", await _opened(work, world.beta)
        )
        await work.rule_versions.add(proposed)
        await work.commit()
    own = RuleVersion.model_construct(
        **{**proposed.model_dump(), "status": "approved", "decided_by": MAKER, "decided_at": NOW}
    )
    async with uow(world.beta) as work:
        with pytest.raises(ConflictError) as refused:
            await work.rule_versions.decide(own, superseding=None)
    assert refused.value.details["constraint"] == "ck_rule_versions_checker_not_maker"
