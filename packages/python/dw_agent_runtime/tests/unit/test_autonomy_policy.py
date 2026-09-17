"""The autonomy policy matches the product decision in every combination.

The implementation is a ladder. The oracle below is the decision as it was made —
a table, cell by cell. They are deliberately two representations: a test that
restated the ladder would only check the ladder against itself. Agreement across
every combination of level, side effect, idempotency and approval policy is what
says the relation encodes the decision.
"""

from __future__ import annotations

import itertools
from typing import get_args

import pytest

from dw_agent_runtime.autonomy import AutonomyApprovalPolicy, lower_autonomy
from dw_agent_runtime.contracts import ApprovalPolicy, SideEffectLevel, ToolDefinition
from dw_kernel.autonomy import AutonomyLevel

pytestmark = pytest.mark.unit

POLICY = AutonomyApprovalPolicy()

ASK, AUTO, AUTO_IF_IDEMPOTENT = "ask", "auto", "auto_if_idempotent"

# Recorded 2026-09-17, "Cân bằng". Rows: side effect. Columns: A0..A4.
DECISION: dict[str, tuple[str, str, str, str, str]] = {
    "none": (ASK, AUTO, AUTO, AUTO, AUTO),
    "internal": (ASK, ASK, AUTO, AUTO, AUTO),
    "external": (ASK, ASK, ASK, AUTO_IF_IDEMPOTENT, AUTO),
    "critical": (ASK, ASK, ASK, ASK, ASK),
}
LEVELS: tuple[AutonomyLevel, ...] = ("A0", "A1", "A2", "A3", "A4")


def _tool(
    side_effect: SideEffectLevel, *, idempotent: bool, policy: ApprovalPolicy
) -> ToolDefinition:
    return ToolDefinition(
        name="crm.do_thing",
        version="1.0.0",
        description="x",
        input_schema_ref="i",
        output_schema_ref="o",
        required_scopes=frozenset(),
        side_effect_level=side_effect,
        approval_policy=policy,
        timeout_seconds=10,
        max_retries=0,
        idempotent=idempotent,
        data_classification=frozenset({"internal"}),
    )


def _expected(side_effect: str, level: AutonomyLevel, idempotent: bool, policy: str) -> bool:
    if policy == "always":
        return True
    cell = DECISION[side_effect][LEVELS.index(level)]
    if cell == AUTO_IF_IDEMPOTENT:
        return not idempotent
    return cell == ASK


def test_the_side_effect_levels_are_the_ones_the_decision_covers() -> None:
    """If a fifth level were added to the schema, the table would not say what to
    do with it — and the exhaustive test below would silently not cover it."""
    assert set(get_args(SideEffectLevel)) == set(DECISION)
    assert set(get_args(AutonomyLevel)) == set(LEVELS)


@pytest.mark.parametrize(
    ("side_effect", "level", "idempotent", "policy"),
    list(
        itertools.product(
            get_args(SideEffectLevel), LEVELS, (True, False), get_args(ApprovalPolicy)
        )
    ),
)
def test_every_combination_matches_the_decision(
    side_effect: SideEffectLevel, level: AutonomyLevel, idempotent: bool, policy: ApprovalPolicy
) -> None:
    tool = _tool(side_effect, idempotent=idempotent, policy=policy)

    assert POLICY.requires_approval(tool, autonomy=level) is _expected(
        side_effect, level, idempotent, policy
    )


# -------------------------------------------------------------- the floors --


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("idempotent", (True, False))
def test_critical_asks_at_every_level_including_a4(level: AutonomyLevel, idempotent: bool) -> None:
    tool = _tool("critical", idempotent=idempotent, policy="never")

    assert POLICY.requires_approval(tool, autonomy=level) is True


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("side_effect", get_args(SideEffectLevel))
def test_a_tool_declared_always_asks_at_every_level(
    level: AutonomyLevel, side_effect: SideEffectLevel
) -> None:
    """A worker's configuration does not overrule the tool author's own declaration —
    not even for a read, not even at A4."""
    tool = _tool(side_effect, idempotent=True, policy="always")

    assert POLICY.requires_approval(tool, autonomy=level) is True


def test_conditional_is_no_longer_a_silent_never() -> None:
    """It was accepted by the schema and matched by no branch: it behaved as `never`.
    At A2 an external conditional tool must now ask."""
    tool = _tool("external", idempotent=True, policy="conditional")

    assert POLICY.requires_approval(tool, autonomy="A2") is True


def test_an_unresolved_autonomy_fails_closed() -> None:
    """A run that never went through the runner that resolves its level must not be
    treated as trusted. Even a read asks."""
    tool = _tool("none", idempotent=True, policy="never")

    assert POLICY.requires_approval(tool, autonomy=None) is True


def test_a0_is_shadow_mode_and_asks_even_for_a_read() -> None:
    tool = _tool("none", idempotent=True, policy="never")

    assert POLICY.requires_approval(tool, autonomy="A0") is True


# ---------------------------------------------------- the tenant's ceiling --


@pytest.mark.parametrize(("worker", "ceiling"), list(itertools.product(LEVELS, LEVELS)))
def test_a_tenant_can_lower_a_worker_and_never_raise_it(
    worker: AutonomyLevel, ceiling: AutonomyLevel
) -> None:
    effective = lower_autonomy(worker, ceiling)

    assert LEVELS.index(effective) == min(LEVELS.index(worker), LEVELS.index(ceiling))
    assert LEVELS.index(effective) <= LEVELS.index(worker)
