"""A customer's SalesOrder skill, replayed on all of the customer's worked
pairs before the head decides it (ticket 41, acceptance 3). The pairs are
ticket 38's synthetic ones; the skills are `sales_salesorder_skill.json`'s."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import PromptRef
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.rule_versions import ContextScope, Resolved
from dw_platform.domain.audit import system_actor
from dw_sales.application.access import Gate, SalesScopes
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleKey
from dw_sales.application.salesorder_fill import (
    SalesOrderFiller,
    po_rows,
    prepared_calls,
)
from dw_sales.application.salesorder_learning import LearningRulesPort, WorkedPair
from dw_sales.application.salesorder_pairs import (
    SALESORDER_PAIRS_RETENTION_LANE,
    SalesOrderSkillReplayer,
    WorkedPairRetention,
    WorkedPairs,
)
from dw_sales.application.salesorder_rules import CustomerSalesOrderRules
from dw_sales.application.salesorder_skills import customer_skill
from dw_sales.application.skills import PAIRS_BROKEN, SkillProposal, salesorder_key
from dw_sales.domain.order_checks import Learning
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, GIANG, READER
from dw_sales.evals.rule_drafts import ALPHA_OTHER
from dw_sales.evals.salesorder_rules import Bench, load_cases, pair
from dw_sales.evals.salesorder_skill import gold_answer, kept_pair, load_skill_cases, tools_for
from dw_sales.evals.world import ALPHA, BETA, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
PAIRS = load_cases(REPO)
CASES = load_skill_cases(REPO)
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
HUONG = Caller(uuid.UUID(int=0x62), "Trần Thu Hương", "huong.tran@alpha.local", GIANG.scopes)
# What a skill holds to break a pair, in this test: the scripted model fills
# the delivery date a day off wherever it reads it.
BREAKS = "Move the delivery date one more day."


@dataclass
class _ByPo:
    """The model: each pair's PO filled as its skill says (the gold answer),
    a day off on the delivery date where the skill says ``BREAKS``."""

    answers: Mapping[str, dict[str, Any]]
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        rows = json.loads(inputs["po_rows"])
        answer = json.loads(json.dumps(self.answers[rows[0]["values"]["R1.po_no"]]))
        if BREAKS in inputs["skill"]:
            for row in answer["rows"]:
                for cell in row["cells"]:
                    if cell["column"] == "AF":
                        cell["value"] = "2000-01-01"
        return schema.model_validate(answer)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, HUONG))


async def _bench_with_pairs(*pair_ids: str) -> tuple[Bench, dict[str, dict[str, Any]]]:
    bench = Bench.of(REPO, None, (GIANG,))
    answers = {}
    for pair_id in pair_ids:
        spec = pair(PAIRS, pair_id)
        worked = await kept_pair(bench, spec)
        tools = tools_for(bench, spec["customer"])
        rows = po_rows(worked.document, tools, worked.received_on)
        answers[spec["po_no"]] = gold_answer(
            bench.layout,
            rows,
            prepared_calls(tools, rows),
            CustomerSalesOrderRules.model_validate(spec["gold"]),
            worked.expected,
        )
    return bench, answers


def _replayer(world: World, bench: Bench, answers: Mapping[str, Any]) -> SalesOrderSkillReplayer:
    return SalesOrderSkillReplayer(
        uow=world.store,
        pairs=bench.store,
        replays=world.store.skill_replays,
        book=world.services.skills.book,
        rules=bench.rules(),
        catalog=bench.catalog(),
        filler=SalesOrderFiller(_ByPo(answers)),
        clock=FixedClock(datetime(2026, 11, 16, 9, 0, tzinfo=UTC)),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
    )


async def _propose(world: World, customer: str, words: str, version: str = "1.0.1") -> Any:
    return await world.services.skills.propose(
        AN.context(),
        f"salesorder-{customer.lower()}",
        SkillProposal(
            version=version, description="KHB's PO to the SalesOrder.", instructions=words
        ),
    )


async def test_a_version_every_pair_reproduces_is_approved_and_fills_the_customers_po() -> None:
    world = _world()
    bench, answers = await _bench_with_pairs("SR02")
    proposed = await _propose(world, "KHB", CASES["skills"]["KHB"])
    assert proposed.ref == "sales_skill_salesorder_khb@1.0.1"
    replayer = _replayer(world, bench, answers)
    assert await replayer.tick(ALPHA) == 1
    stored = (await world.store.skill_replays.stored(ALPHA, [proposed.version_id]))[
        proposed.version_id
    ]
    assert (stored.source, stored.outcome, stored.messages, stored.right_with) == (
        "customer_pairs",
        "replayed",
        1,
        1,
    )
    # Replayed once: the next tick finds nothing new.
    assert await replayer.tick(ALPHA) == 0
    await world.decide_skill(HUONG, proposed.version_id, approve=True, comment="Đồng ý")
    scope = ContextScope.of(GIANG.context())
    held = await customer_skill(world.services.skills.book, scope, "KHB")
    assert (held.ref, held.instructions) == (proposed.ref, CASES["skills"]["KHB"])
    # Another customer is still filled with the platform's generic skill, and
    # another tenant never with this one.
    other = await customer_skill(world.services.skills.book, scope, "KHC")
    assert other.ref == "sales_skill_salesorder_khc@1.0.0"
    beta = await customer_skill(
        world.services.skills.book, ContextScope.of(GIANG.context(BETA)), "KHB"
    )
    assert beta.ref == "sales_skill_salesorder_khb@1.0.0"


async def test_a_version_that_breaks_a_pair_cannot_be_approved() -> None:
    """Acceptance 3: one pair off, and the head's approval is refused at the
    decision; rejecting it stays open."""
    world = _world()
    bench, answers = await _bench_with_pairs("SR02")
    proposed = await _propose(world, "KHB", CASES["skills"]["KHB"] + "\n" + BREAKS + "\n")
    await _replayer(world, bench, answers).tick(ALPHA)
    stored = (await world.store.skill_replays.stored(ALPHA, [proposed.version_id]))[
        proposed.version_id
    ]
    # The skill in force (the generic one, here) still reproduces it.
    assert (stored.messages, stored.right_with, stored.right_without) == (1, 0, 1)
    with pytest.raises(ConflictError) as refused:
        await world.decide_skill(HUONG, proposed.version_id, approve=True, comment="Đồng ý")
    assert refused.value.details["rule"] == PAIRS_BROKEN
    await world.decide_skill(HUONG, proposed.version_id, approve=False, comment="Sai ngày")
    (version,) = [
        v
        for v in (await world.store.rule_versions.for_tenant(ALPHA.tenant_id.value).list_all())
        if v.version_id == proposed.version_id
    ]
    assert version.status == "rejected"


async def test_a_version_no_pair_proves_cannot_be_approved() -> None:
    world = _world()
    bench, answers = await _bench_with_pairs("SR02")
    proposed = await _propose(world, "KHC", CASES["skills"]["KHC"])
    await _replayer(world, bench, answers).tick(ALPHA)
    stored = (await world.store.skill_replays.stored(ALPHA, [proposed.version_id]))[
        proposed.version_id
    ]
    assert stored.messages == 0
    with pytest.raises(ConflictError) as refused:
        await world.decide_skill(HUONG, proposed.version_id, approve=True, comment="Đồng ý")
    assert refused.value.details["rule"] == PAIRS_BROKEN


async def test_the_lane_replays_only_customers_salesorder_skills_of_its_tenant() -> None:
    world = _world()
    bench, answers = await _bench_with_pairs("SR02")
    replayer = _replayer(world, bench, answers)
    assert await replayer.tick(BETA) == 0
    assert await replayer.tick(ALPHA) == 0
    assert salesorder_key("KHB") == "sales_skill_salesorder_khb"


# ------------------------------------- a pair withdrawn, or past its term --

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
WITHDRAWN = "sales.salesorder_pair.withdrawn"


def _pairs(bench: Bench) -> WorkedPairs:
    return WorkedPairs(
        bench.store, Gate(ScopeAuthorizationService()), FixedClock(NOW), Uuid4Generator()
    )


async def _keep(bench: Bench, scope: SalesScope, pair_: WorkedPair, **update: Any) -> WorkedPair:
    kept = pair_.model_copy(update={"pair_id": uuid.uuid4(), **update})
    async with bench.store(scope) as work:
        await work.pairs.add(kept)
        await work.commit()
    return kept


async def test_a_withdrawn_pair_is_audited_and_no_longer_replayed() -> None:
    world = _world()
    bench, answers = await _bench_with_pairs("SR02")
    pairs = _pairs(bench)
    (listed,) = await pairs.for_customer(AN.context(), "KHB")
    assert (listed.customer_code, listed.replayed) == ("KHB", True)
    assert listed.rows == len(bench.store.state(ALPHA).pairs[0].expected)

    withdrawn = await pairs.withdraw(AN.context(), listed.pair_id)
    assert withdrawn.pair_id == listed.pair_id
    assert await pairs.for_customer(AN.context(), "KHB") == []
    (event,) = [e for e in bench.store.audit.events if e.action == WITHDRAWN]
    assert (event.actor_id.value, event.resource_id) == (AN.user_id, str(listed.pair_id))
    assert event.details["customer_code"] == "KHB"
    # Ids, a day and a count: never a cell of the PO or of the PIC's file.
    assert set(event.details) == {"customer_code", "example_id", "received_on", "rows", "added_by"}
    # The customer's next version is replayed on the pairs left: none.
    proposed = await _propose(world, "KHB", CASES["skills"]["KHB"])
    await _replayer(world, bench, answers).tick(ALPHA)
    stored = await world.store.skill_replays.stored(ALPHA, [proposed.version_id])
    assert stored[proposed.version_id].messages == 0


async def test_a_pair_is_withdrawn_by_a_proposer_who_reads_prices_in_its_workspace_only() -> None:
    bench, _ = await _bench_with_pairs("SR02")
    pairs = _pairs(bench)
    (listed,) = await pairs.for_customer(AN.context(), "KHB")
    no_prices = replace(AN, scopes=AN.scopes - {SalesScopes.PRICE_READ})
    for caller in (_AN, READER, no_prices):
        with pytest.raises(PermissionDeniedError):
            await pairs.withdraw(caller.context(), listed.pair_id)
        with pytest.raises(PermissionDeniedError):
            await pairs.for_customer(caller.context(), "KHB")
    # Another tenant's proposer, and another workspace of the tenant, find
    # none of it, and withdraw nothing.
    for scope in (BETA, ALPHA_OTHER):
        with pytest.raises(NotFoundError):
            await pairs.withdraw(GIANG.context(scope), listed.pair_id)
        assert await pairs.for_customer(GIANG.context(scope), "KHB") == []
    assert [p.pair_id for p in await pairs.for_customer(AN.context(), "KHB")] == [listed.pair_id]
    assert not [e for e in bench.store.audit.events if e.action == WITHDRAWN]
    # Withdrawn once; a second withdrawal finds nothing.
    await pairs.withdraw(AN.context(), listed.pair_id)
    with pytest.raises(NotFoundError):
        await pairs.withdraw(AN.context(), listed.pair_id)


@dataclass
class _Term:
    """The tenant's rules, with its own term for pairs where ``days`` says."""

    inner: LearningRulesPort
    days: int | None = None

    async def current(self, scope: SalesScope, key: RuleKey) -> Resolved:
        resolved = await self.inner.current(scope, key)
        if key is not RuleKey.ORDER_RULES or self.days is None:
            return resolved
        rules = resolved.policy
        learning = rules.learning.model_copy(update={"salesorder_pairs_kept_days": self.days})
        return Resolved(rules.model_copy(update={"learning": learning}), "tenant")


def _retention(bench: Bench, days: int | None = None) -> WorkedPairRetention:
    return WorkedPairRetention(
        bench.store, _Term(bench.rules(), days), FixedClock(NOW), Uuid4Generator()
    )


async def test_pairs_past_the_tenants_term_are_dropped_in_their_own_scope_by_the_lane() -> None:
    bench, _ = await _bench_with_pairs("SR02")
    (first,) = bench.store.state(ALPHA).pairs
    recent = await _keep(bench, ALPHA, first, added_at=NOW - timedelta(days=40))
    old = await _keep(bench, ALPHA, first, added_at=NOW - timedelta(days=366))
    beta_old = await _keep(bench, BETA, first, added_at=NOW - timedelta(days=366))
    # A year by default: only the pair older than that.
    assert await _retention(bench).tick(ALPHA) == 1
    assert old not in bench.store.state(ALPHA).pairs
    assert recent in bench.store.state(ALPHA).pairs
    (event,) = [e for e in bench.store.audit.events if e.action == "sales.salesorder_pairs.pruned"]
    assert event.actor_id == system_actor(SALESORDER_PAIRS_RETENTION_LANE)
    assert (event.details["pairs"], event.details["kept_days"]) == (1, 365)
    # Another tenant's pair of the same age waits for its own tenant's tick.
    assert bench.store.state(BETA).pairs == [beta_old]
    # The tenant's own term, shorter: the 40-day-old pair goes too.
    assert await _retention(bench, days=30).tick(ALPHA) == 1
    assert recent not in bench.store.state(ALPHA).pairs
    # Nothing past the term: nothing dropped and nothing audited.
    assert await _retention(bench, days=30).tick(ALPHA) == 0
    assert len([e for e in bench.store.audit.events if e.action.endswith(".pruned")]) == 2


def test_the_term_is_tenant_config_with_a_conservative_default() -> None:
    assert Learning().salesorder_pairs_kept_days == 365
    for days in (29, 1096):
        with pytest.raises(ValueError):
            Learning(salesorder_pairs_kept_days=days)
