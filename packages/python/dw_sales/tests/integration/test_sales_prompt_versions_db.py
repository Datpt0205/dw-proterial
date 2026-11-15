"""A tenant's prompt version proposed by the optimiser lane, against
PostgreSQL (ticket 43 part 3, migration 137ec1972538).

The key is one `platform.rule_versions` admits, the proposal waits on its
approval with the lane as its proposer, and nothing is served before the head
decides, to this tenant or another.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel
from sales_harness import World
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import PromptRef
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.examples import DescriptionExample
from dw_sales.application.model_reading import Demonstrations, DescriptionReader
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.application.prompt_optimiser import OPTIMISER_LANE, PromptOptimiser, SecurityCase
from dw_sales.application.prompt_versions import PROMPT_KEY, prompt_book
from dw_sales.domain.catalog import Item
from dw_sales.domain.description_reading import ModelDescriptionLine
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.testing.labelled_examples import MemoryDescriptionExamples

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
ITEMS = read_records(DATA_DIR / "items.json", Item)
GREEN = "Dây điện AWG20 màu xanh lá"
READ = {
    "family_span": "Dây điện",
    "family": "hook_up_wire",
    "gauge_span": "AWG20",
    "colour_span": "màu xanh lá",
    "colour": "green",
}


class _Learner:
    """Reads GREEN once a decided GREEN is shown; leaves every other out."""

    model_profile = "onprem"
    route = "structured_extraction"
    max_input_tokens = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        shown = {e["description"] for e in json.loads(inputs["examples"])}
        nulls = {k: None for k in ModelDescriptionLine.model_fields if k != "line_no"}
        lines = [
            {"line_no": sent["line_no"], **nulls, **READ}
            for sent in json.loads(inputs["lines"])
            if sent["description"] == GREEN and GREEN in shown
        ]
        return schema.model_validate({"lines": lines})


class _Rules:
    def __init__(self) -> None:
        platform = load_sales_policies(
            REPO / "configs" / "policies", REPO / "configs" / "copy"
        ).order_rules
        self.value = platform.model_copy(
            update={
                "learning": platform.learning.model_copy(
                    update={"new_cases_to_retrain": 20, "examples_per_line": 0}
                )
            }
        )

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self.value


class _Open:
    async def allows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        return True


class _Catalog:
    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]:
        return Snapshot(ITEMS, datetime.now(UTC))


class _Directory:
    async def list_members(self, context: AccessContext) -> list[Any]:
        return []


async def test_the_lanes_proposal_is_a_row_waiting_on_the_head_and_served_to_nobody(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    world: World,
) -> None:
    lines = MemoryDescriptionExamples()
    lines.add(
        world.alpha,
        *(
            DescriptionExample(
                label_id=uuid.uuid4(),
                case_id=uuid.uuid4(),
                customer_code="C001",
                decided_at=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(hours=n),
                description=GREEN,
                prv_code="HW-1011",
            )
            for n in range(20)
        ),
    )
    book = prompt_book(SqlRuleVersionLookup(app_sessions))
    optimiser = PromptOptimiser(
        examples=lines,
        reader=DescriptionReader(_Learner(), prompts=book),
        book=book,
        rules=_Rules(),
        gate=_Open(),
        catalog=_Catalog(),
        uow=uow,
        directory=_Directory(),
        security=(SecurityCase(kind="missing_evidence", case_id="m", description="Hàng như cũ"),),
        clock=FixedClock(datetime.now(UTC)),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
    )

    assert (await optimiser.tick(world.alpha)).reason == "proposed"

    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT tenant_id, status, proposed_by, approval_id"
                    " FROM platform.rule_versions WHERE key = :key"
                ),
                {"key": PROMPT_KEY},
            )
        ).all()
    ((tenant, status, proposed_by, approval_id),) = rows
    assert (tenant, status) == (world.alpha.tenant_id.value, "proposed")
    assert proposed_by == system_actor(OPTIMISER_LANE).value and approval_id is not None
    # Waiting on the head: nobody's readings show it yet.
    for scope in (world.alpha, world.beta):
        assert await book.demonstrations(scope) == Demonstrations(None)
