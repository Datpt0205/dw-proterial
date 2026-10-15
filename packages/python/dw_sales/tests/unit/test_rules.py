"""A tenant's own Sales rule versions: proposed, decided, resolved (ticket 19);
decided on a `sales.rules` platform approval (ticket 38)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.application.rules import (
    RULES_APPROVAL,
    RuleDecisions,
    RuleKey,
    RuleSettlement,
    RuleVersionView,
    TenantRuleBook,
)
from dw_sales.domain.order_checks import OrderRules
from dw_sales.evals.graders import AN, CALLERS, DIEU, GIANG, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    """The demo sample set: tenant alpha starts with its own order rules
    (seeded as approved, `sales_order_rules@1.5.1`), beta with the platform's."""
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _platform_rules(world: World) -> dict[str, Any]:
    return world.policies.order_rules.model_dump(mode="json", by_alias=True)


def _version(world: World, version: str, **changes: Any) -> dict[str, Any]:
    document = _platform_rules(world)
    document["policy_version"] = version
    document.update(changes)
    return document


async def _approved(world: World, version: str = "9.0.1") -> uuid.UUID:
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, version, cross_check_required=False)
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")
    return proposed.version_id


async def _listed(world: World, version_id: object) -> RuleVersionView:
    listed = await world.services.rules.list(GIANG.context())
    return next(v for v in listed.versions if v.version_id == version_id)


async def test_a_pic_proposes_and_the_head_approves_and_it_applies_to_the_tenant() -> None:
    world = _world()
    before = await world.services.layouts.rules.rules(ALPHA)
    assert before.cross_check_required

    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.0.1", cross_check_required=False)
    )
    assert (proposed.status, proposed.proposed_by, proposed.layer) == (
        "proposed",
        AN.user_id,
        "tenant",
    )
    # Proposed is not in force.
    assert (await world.services.layouts.rules.rules(ALPHA)).version == before.version

    # Proposing opened a platform approval, stamped, the proposer its maker,
    # its payload ids, the key and the version and never the document.
    assert proposed.approval_id is not None
    approval = world.runtime.approvals.rows[proposed.approval_id]
    assert (approval.approval_type, approval.required_scope) == (
        RULES_APPROVAL,
        "sales.rules.approve",
    )
    assert approval.makers == {AN.user_id}
    assert set(approval.payload) == {
        "approval_type",
        "required_scope",
        "version_id",
        "key",
        "version",
        "makers",
    }

    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")
    decided = await _listed(world, proposed.version_id)
    assert (decided.status, decided.decided_by) == ("approved", GIANG.user_id)
    in_force = await world.services.layouts.rules.rules(ALPHA)
    assert in_force.version == "sales_order_rules@9.0.1"
    assert not in_force.cross_check_required
    listed = await world.services.rules.list(GIANG.context())
    assert listed.in_force[RuleKey.ORDER_RULES] == "sales_order_rules@9.0.1"
    assert listed.layers[RuleKey.ORDER_RULES] == "tenant"
    assert listed.layers[RuleKey.KPI] == "platform"
    # Each step is audited, with the key and the version and never the document.
    actions = [e.action for e in world.store.state(ALPHA).audit]
    assert actions[-2:] == ["sales.rules.proposed", "sales.rules.approved"]
    details = world.store.state(ALPHA).audit[-1].details
    assert details == {
        "key": "sales_order_rules",
        "version": "9.0.1",
        "status": "approved",
        "approval_id": str(proposed.approval_id),
    }
    # A redelivery of the decision writes nothing.
    settled = await world.rule_settlement.settle(proposed.approval_id, GIANG.context())
    assert settled == decided
    assert [e.action for e in world.store.state(ALPHA).audit] == actions


async def test_an_override_never_resolves_for_another_tenant() -> None:
    world = _world()
    await _approved(world)

    beta = await world.services.layouts.rules.rules(BETA)
    assert beta.version == world.policies.order_rules.version
    assert beta.cross_check_required
    # Nor does the other tenant see it listed.
    listed = await world.services.rules.list(OUTSIDER.context(BETA))
    assert listed.versions == [] and listed.layers[RuleKey.ORDER_RULES] == "platform"


async def test_the_proposer_cannot_approve_their_own_version() -> None:
    world = _world()
    before = await world.services.layouts.rules.rules(ALPHA)
    proposed = await world.services.rules.propose(
        GIANG.context(), RuleKey.ORDER_RULES, _version(world, "9.0.2")
    )
    with pytest.raises(ConflictError) as refused:
        await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Tự duyệt")
    assert refused.value.details["rule"] == "maker_checker"
    assert await world.services.layouts.rules.rules(ALPHA) == before


async def test_a_pic_cannot_approve_and_a_reader_cannot_propose() -> None:
    world = _world()
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.0.3")
    )
    # Without `sales.rules.approve` the stamped approval is not even visible.
    with pytest.raises(NotFoundError):
        await world.decide_rules(DIEU, proposed.version_id, approve=True, comment="Đồng ý")
    with pytest.raises(PermissionDeniedError):
        await world.services.rules.propose(
            READER.context(), RuleKey.ORDER_RULES, _version(world, "9.0.4")
        )
    with pytest.raises(PermissionDeniedError):
        await world.services.rules.list(READER.context())


async def test_a_document_the_keys_schema_refuses_is_refused_by_field() -> None:
    world = _world()
    broken = _version(world, "9.0.5")
    del broken["findings"]
    with pytest.raises(DomainError) as refused:
        await world.services.rules.propose(AN.context(), RuleKey.ORDER_RULES, broken)
    assert refused.value.details["errors"] == ["findings"]
    # Another key's document under this key is refused the same way.
    with pytest.raises(DomainError):
        await world.services.rules.propose(AN.context(), RuleKey.KPI, _version(world, "9.0.6"))


async def test_a_tenant_version_takes_a_number_the_platform_does_not_ship() -> None:
    world = _world()
    with pytest.raises(ConflictError) as refused:
        await world.services.rules.propose(
            AN.context(), RuleKey.ORDER_RULES, _platform_rules(world)
        )
    assert refused.value.details["rule"] == "platform_version_reused"


async def test_a_newer_approval_supersedes_and_a_stamp_still_reads_its_version() -> None:
    world = _world()
    first = await _approved(world, "9.1.0")
    await _approved(world, "9.2.0")

    versions = {
        v.version: v.status for v in (await world.services.rules.list(GIANG.context())).versions
    }
    # The demo tenant's seeded version went first, then 9.1.0.
    assert versions == {"1.5.1": "superseded", "9.1.0": "superseded", "9.2.0": "approved"}
    port = world.services.layouts.rules
    assert (await port.rules(ALPHA)).version == "sales_order_rules@9.2.0"
    # A case stamped under 9.1.0 is rechecked under 9.1.0, not what is in force.
    stamped = await port.rules_at(ALPHA, "sales_order_rules@9.1.0")
    assert stamped is not None and stamped.version == "sales_order_rules@9.1.0"
    # Neither another tenant's version nor one never approved is read by stamp.
    assert await port.rules_at(BETA, "sales_order_rules@9.1.0") is None
    rejected = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.3.0")
    )
    await world.decide_rules(GIANG, rejected.version_id, approve=False, comment="chưa duyệt")
    assert await port.rules_at(ALPHA, "sales_order_rules@9.3.0") is None
    assert first != rejected.version_id


async def test_a_decided_version_is_not_decided_again_and_a_rejection_says_why() -> None:
    world = _world()
    version_id = await _approved(world, "9.4.0")
    with pytest.raises(ConflictError):
        await world.decide_rules(GIANG, version_id, approve=False, comment="x")
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.4.1")
    )
    # `sales.` is strict: a decision says why.
    with pytest.raises(ConflictError):
        await world.decide_rules(GIANG, proposed.version_id, approve=False, comment="")
    assert (await _listed(world, proposed.version_id)).status == "proposed"


async def test_the_rules_list_shows_the_reason_the_decider_gave() -> None:
    """The reason is given on the platform approval (ticket 38); the list
    reads it from the version, where the settlement stamps it, cut to what
    a version holds."""
    world = _world()
    rejected = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.5.0")
    )
    await world.decide_rules(
        GIANG, rejected.version_id, approve=False, comment="  Thiếu ngưỡng giá mới  "
    )
    approved = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, "9.5.1")
    )
    await world.decide_rules(GIANG, approved.version_id, approve=True, comment="x" * 800)

    assert (await _listed(world, rejected.version_id)).comment == "Thiếu ngưỡng giá mới"
    long = (await _listed(world, approved.version_id)).comment
    assert long is not None and len(long) == 500 and long.endswith("…")


async def test_the_kpi_policy_resolves_per_tenant_for_the_overview() -> None:
    world = _world()
    document = world.policies.kpi.model_dump(mode="json", by_alias=True)
    document["policy_version"] = "9.0.0"
    document["quotation_target_days"] = 3
    proposed = await world.services.rules.propose(AN.context(), RuleKey.KPI, document)
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")

    alpha = await world.services.overview.overview(GIANG.context())
    assert alpha.kpi_policy == "sales_kpi@9.0.0"
    assert alpha.quotation_time.target_seconds == 3 * 86400.0
    beta = await world.services.overview.overview(OUTSIDER.context(BETA))
    assert beta.kpi_policy == world.policies.kpi.version


# ------------------------------------------- quote rules and copy (36) --

_SIX = (
    RuleKey.QUOTE_RULES,
    RuleKey.PRICING,
    RuleKey.EMAILS,
    RuleKey.DOCUMENTS,
    RuleKey.BRAVO_UPLOAD,
    RuleKey.HANDOFFS,
)


def _bumped(world: World, key: RuleKey, version: str) -> dict[str, Any]:
    """The platform's document of ``key`` under a tenant's number: a policy
    names it ``policy_version``, a copy file ``version``."""
    document = dict(world.services.rules.book.platform[key].model_dump(mode="json", by_alias=True))
    document["policy_version" if "policy_version" in document else "version"] = version
    return document


@pytest.mark.parametrize("key", _SIX, ids=[k.value for k in _SIX])
async def test_each_key_is_proposed_approved_and_in_force_for_its_tenant_only(
    key: RuleKey,
) -> None:
    world = _world()
    rules = world.services.rules
    proposed = await rules.propose(AN.context(), key, _bumped(world, key, "9.0.1"))
    assert proposed.ref == f"{key.value}@9.0.1"
    with pytest.raises(ConflictError) as reused:
        await rules.propose(
            AN.context(), key, _bumped(world, key, rules.book.platform[key].ref.partition("@")[2])
        )
    assert reused.value.details["rule"] == "platform_version_reused"

    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")

    alpha = await rules.list(GIANG.context())
    assert (alpha.in_force[key], alpha.layers[key]) == (f"{key.value}@9.0.1", "tenant")
    resolved = await rules.book.current(ALPHA, key)
    assert resolved.policy.ref == f"{key.value}@9.0.1"
    beta = await rules.list(OUTSIDER.context(BETA))
    assert beta.layers[key] == "platform" and beta.versions == []
    assert (await rules.book.current(BETA, key)).policy.ref == rules.book.platform[key].ref
    assert await rules.book.at(BETA, key, f"{key.value}@9.0.1") is None


async def test_another_keys_document_is_no_version_of_a_copy_key() -> None:
    world = _world()
    with pytest.raises(DomainError):
        await world.services.rules.propose(
            AN.context(), RuleKey.EMAILS, _bumped(world, RuleKey.DOCUMENTS, "9.0.1")
        )


# ------------------------------------------- the decision guard (ticket 38) --


def _decision(approve: bool = True) -> ProposedDecision:
    return ProposedDecision(approve=approve, comment="Đồng ý", reasons={}, subject_version=None)


async def _opened(world: World, version: str) -> tuple[RuleVersionView, ApprovalRequest]:
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.ORDER_RULES, _version(world, version)
    )
    assert proposed.approval_id is not None
    return proposed, world.runtime.approvals.rows[proposed.approval_id]


async def test_the_guard_refuses_an_approval_no_proposal_opened_or_stamped_otherwise() -> None:
    world = _world()
    guard = RuleDecisions(world.store, world.services.rules.book)
    _, request = await _opened(world, "9.6.0")

    for forged in (
        replace(request, approval_type="sales.layout"),
        replace(request, payload={**request.payload, "version_id": "not-a-uuid"}),
    ):
        with pytest.raises(ConflictError):
            await guard.check(forged, _decision(), GIANG.context())
    with pytest.raises(PermissionDeniedError):
        await guard.check(
            replace(request, required_scope="sales.quote.approve"), _decision(), GIANG.context()
        )
    # The proposer, asked directly: the platform's strict rule refuses them
    # first, and this is the line behind it.
    with pytest.raises(ConflictError) as maker:
        await guard.check(request, _decision(), AN.context())
    assert maker.value.details["rule"] == "maker_checker"
    # The approval as opened passes.
    await guard.check(request, _decision(), GIANG.context())


async def test_the_guard_refuses_a_version_no_longer_waiting_and_a_number_released_since() -> None:
    world = _world()
    proposed, request = await _opened(world, "9.7.0")
    await world.decide_rules(GIANG, proposed.version_id, approve=False, comment="Chưa")
    guard = RuleDecisions(world.store, world.services.rules.book)
    with pytest.raises(ConflictError) as stale:
        await guard.check(request, _decision(), GIANG.context())
    assert stale.value.details["rule"] == "decision_stale"

    proposed, request = await _opened(world, "9.8.0")
    book = world.services.rules.book
    later = OrderRules.model_validate(_version(world, "9.8.0"))
    released = TenantRuleBook(book.platform, book.stored, {**book.released, later.ref: later})
    with pytest.raises(ConflictError) as reused:
        await RuleDecisions(world.store, released).check(request, _decision(), GIANG.context())
    assert reused.value.details["rule"] == "platform_version_reused"
    # Rejecting it is still allowed: nothing is stamped with a rejected number.
    await RuleDecisions(world.store, released).check(request, _decision(False), GIANG.context())


async def test_a_pending_approval_is_not_settled_and_a_rejection_is_recorded() -> None:
    world = _world()
    proposed, request = await _opened(world, "9.9.0")
    with pytest.raises(ConflictError):
        await world.rule_settlement.settle(request.id, GIANG.context())

    await world.decide_rules(GIANG, proposed.version_id, approve=False, comment="Chưa đủ")

    rejected = await _listed(world, proposed.version_id)
    assert (rejected.status, rejected.decided_by) == ("rejected", GIANG.user_id)
    assert world.store.state(ALPHA).audit[-1].action == "sales.rules.rejected"
    assert await world.services.layouts.rules.rules_at(ALPHA, proposed.ref) is None


async def test_another_tenant_neither_decides_nor_carries_out_a_rules_approval() -> None:
    world = _world()
    proposed, request = await _opened(world, "9.9.1")

    with pytest.raises(NotFoundError):
        await world.runtime.approval_flow.decide(
            approval_id=request.id,
            approve=True,
            comment="Đồng ý",
            context=GIANG.context(BETA),
            authorization=ScopeAuthorizationService(),
        )
    with pytest.raises(NotFoundError):
        await world.rule_settlement.settle(request.id, GIANG.context(BETA))
    assert (await _listed(world, proposed.version_id)).status == "proposed"


class _LosesTheRace:
    """The memory store, except that the first unit of work reads the
    version as it stood before another delivery decided it: what the seed
    met in CI run 38545009082 while the worker carried out the same event."""

    def __init__(self, store: Any, stale: RuleVersionView) -> None:
        self.store, self.stale, self.first = store, stale, True

    def __call__(self, scope: Any) -> Any:
        work = self.store(scope)
        if self.first:
            self.first = False
            versions, stale = work.rule_versions, self.stale

            class _Stale:
                async def get(self, version_id: uuid.UUID) -> Any:
                    found = await versions.get(version_id)
                    return found.model_copy(
                        update={"status": stale.status, "decided_by": None, "decided_at": None}
                    )

                def __getattr__(self, name: str) -> Any:
                    return getattr(versions, name)

            work.rule_versions = _Stale()
        return work


async def test_a_delivery_that_loses_the_race_to_another_finds_the_decision_applied() -> None:
    world = _world()
    proposed, request = await _opened(world, "9.9.2")
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")
    applied = await _listed(world, proposed.version_id)
    audited = len(world.store.state(ALPHA).audit)

    racing = RuleSettlement(
        _LosesTheRace(world.store, proposed),
        world.services.rules.book,
        world.rule_settlement.clock,
        world.rule_settlement.ids,
    )
    settled = await racing.settle(request.id, GIANG.context())

    assert settled == applied
    assert len(world.store.state(ALPHA).audit) == audited
