"""A tenant's purchasing rules through the platform's rule-version engine
(ADR 0013/0014): the configurer proposes, the head decides, the head's own
applies at once; resolved per tenant and stamped on the cases received."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.rules import RULES_APPROVAL
from dw_purchasing.testing.world import ALPHA, BETA, EVERY_SCOPE, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
CONFIGURER = uuid.UUID(int=0xC0F)
HEAD = uuid.UUID(int=0x4EAD)
_CONFIGURES = frozenset({PurchasingScopes.REQUEST_READ.value, PurchasingScopes.RULES_PROPOSE.value})


def _configurer(scope: tuple[uuid.UUID, uuid.UUID] = ALPHA) -> Any:
    return caller(scope, scopes=_CONFIGURES, principal=CONFIGURER)


def _head(scope: tuple[uuid.UUID, uuid.UUID] = ALPHA) -> Any:
    return caller(scope, scopes=EVERY_SCOPE | {"approvals.decide"}, principal=HEAD)


def _document(version: str, *, max_lines: int = 7) -> dict[str, Any]:
    current = PolicyFiles.load(REPO / "configs/policies").current()
    document = current.model_dump(mode="json")
    document["policy_version"] = version
    document["pr_form"]["max_lines"] = max_lines
    return document


def _world() -> World:
    return open_world(REPO, ANSWERS)


async def test_the_configurers_version_waits_for_a_second_person() -> None:
    world = _world()
    version = await world.rules.propose(_configurer(), "purchasing_rules", _document("9.0.0"))
    assert (version.status, version.applied_directly) == ("proposed", False)
    request = world.store.rows(*ALPHA).approvals[version.approval_id or uuid.UUID(int=0)]
    assert request.approval_type == RULES_APPROVAL
    assert request.required_scope == PurchasingScopes.RULES_APPROVE.value
    assert "document" not in request.payload
    # Not in force until decided: the platform's rules still apply.
    assert (await world.service.rules.resolve(_configurer())).pr_form.max_lines == 50


async def test_the_proposer_never_decides_and_the_head_puts_it_in_force() -> None:
    world = _world()
    version = await world.rules.propose(_configurer(), "purchasing_rules", _document("9.0.0"))
    approval_id = version.approval_id or uuid.UUID(int=0)
    request = world.store.rows(*ALPHA).approvals[approval_id]
    with pytest.raises(ConflictError) as refused:
        await world.rule_decisions.check(
            request, ProposedDecision(True, "ok", {}, None), _configurer()
        )
    assert refused.value.details["rule"] == "maker_checker"
    await world.rule_decisions.check(request, ProposedDecision(True, "đồng ý", {}, None), _head())
    world.store.decide(
        approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=world.clock.now(),
        comment="đồng ý",
    )
    settled = await world.rule_settlement.settle(approval_id, _head())
    again = await world.rule_settlement.settle(approval_id, _head())
    assert settled.status == "approved" and again == settled
    assert (await world.service.rules.resolve(_configurer())).pr_form.max_lines == 7
    actions = [e.action for e in world.store.rows(*ALPHA).audit]
    assert actions == ["purchasing.rules.proposed", "purchasing.rules.approved"]


async def test_the_heads_own_version_applies_at_once_and_is_stamped() -> None:
    world = _world()
    version = await world.rules.propose(_head(), "purchasing_rules", _document("9.0.0"))
    assert (version.status, version.applied_directly) == ("approved", True)
    assert world.store.rows(*ALPHA).approvals == {}
    listed = await world.rules.list(_head())
    assert [(k.ref, k.layer) for k in listed.keys] == [("purchasing_rules@9.0.0", "tenant")]
    assert listed.keys[0].platform_ref.startswith("purchasing_rules@1.")
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    case = await world.service.case(caller(), item.case_id)
    assert case.rules_ref == "purchasing_rules@9.0.0"


async def test_a_second_proposal_waits_behind_the_first() -> None:
    world = _world()
    await world.rules.propose(_configurer(), "purchasing_rules", _document("9.0.0"))
    with pytest.raises(ConflictError) as refused:
        await world.rules.propose(_head(), "purchasing_rules", _document("9.0.1"))
    assert refused.value.details["rule"] == "one_open_proposal"


async def test_a_number_the_platform_ships_or_a_document_that_does_not_read_is_refused() -> None:
    world = _world()
    shipped = PolicyFiles.load(REPO / "configs/policies").released[0].version
    with pytest.raises(ConflictError) as reused:
        await world.rules.propose(_head(), "purchasing_rules", _document(shipped))
    assert reused.value.details["rule"] == "platform_version_reused"
    with pytest.raises(DomainError) as invalid:
        await world.rules.propose(_head(), "purchasing_rules", _document("9.0.0", max_lines=0))
    assert invalid.value.details["errors"] == ["pr_form.max_lines"]
    with pytest.raises(DomainError):
        await world.rules.propose(_head(), "purchasing_rules", _document("9.0.0-beta"))


async def test_one_tenants_version_never_reaches_another() -> None:
    world = _world()
    await world.rules.propose(_head(), "purchasing_rules", _document("9.0.0"))
    assert (await world.service.rules.resolve(caller(BETA))).pr_form.max_lines == 50
    listed = await world.rules.list(_head(BETA))
    assert listed.versions == [] and listed.keys[0].layer == "platform"


async def test_without_the_scope_nothing_is_listed_or_proposed() -> None:
    world = _world()
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await world.rules.list(reader)
    with pytest.raises(PermissionDeniedError):
        await world.rules.propose(reader, "purchasing_rules", _document("9.0.0"))
    with pytest.raises(PermissionDeniedError):
        await world.rules.schema(reader, "purchasing_rules")
    assert world.store.versions == {}
