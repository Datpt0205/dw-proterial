"""Whether a tool call pauses for a person — decided by the run, not the tool alone.

Until this existed the decision was `ToolDefinition.requires_approval()`, a method
with no arguments: `approval_policy == "always" or side_effect_level == "critical"`.
A function of the tool and nothing else cannot know which worker is calling, for
which tenant, at what level of autonomy — so `WorkerDefinition.autonomy_level`
(A0..A4) was declared, validated, and read by nothing. A worker at A4 paused
exactly as often as one at A0. And `approval_policy: conditional` was accepted by
the schema and matched by no branch, so it behaved as `never`: anyone who wrote it
expecting a gate got none.

The table is a product decision, not an engineering one (recorded 2026-09-17):

                    A0     A1     A2     A3              A4
    none            ask    auto   auto   auto            auto
    internal        ask    ask    auto   auto            auto
    external        ask    ask    ask    auto if idem.   auto
    critical        ask    ask    ask    ask             ask

A0 is shadow mode — the worker proposes everything and does nothing unasked,
reads included — so a new customer can watch it work with nothing at stake.

It is written here as the relation it is rather than as its twenty cells. Each
level unlocks one more rung of a single ladder, and "external but idempotent" is
its own rung below plain "external": safe to repeat, so a smaller step to trust.
With that rung in place A3 needs no special case — it simply reaches one rung
lower than A4.

Two floors hold at every level, A4 included, and no configuration lowers them:

- `side_effect_level: critical` always asks. No level's reach includes it.
- `approval_policy: always` always asks. A worker's configuration does not get
  to overrule what the tool's author declared about their own tool.

`never` and `conditional` both defer to the table here, and for a while that made
them indistinguishable. They are not collapsed — that would break every tool spec
a context writes — so `never` was given the only meaning it can safely carry. A
tool's author cannot lower the tenant's ceiling, so `never` is not an instruction
but a claim: this tool does nothing a person would need to approve. The claim is
checked where a tool is declared (`contracts.approval_policy_disagrees_with_side_effect`),
and a `never` on anything reaching outside is refused rather than quietly read as
`conditional`. Past that gate both values do defer to the table, which is correct:
only the ceiling decides how far a run reaches.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext, ToolDefinition
from dw_kernel.autonomy import AUTONOMY_LEVELS, AutonomyLevel

__all__ = [
    "AUTONOMY_POLICY_VERSION",
    "AutonomyApprovalPolicy",
    "lower_autonomy",
]

# Bumped whenever what any level may do changes. Stamped on each run, so a past
# decision is read under the policy that made it, never re-derived under today's.
AUTONOMY_POLICY_VERSION: Final = "1.0.0"

# The rungs, lowest to highest. "external_idempotent" is not a value a tool spec
# can declare; it is what an idempotent external tool is ranked as.
_RUNG: Final[Mapping[str, int]] = {
    "none": 0,
    "internal": 1,
    "external_idempotent": 2,
    "external": 3,
    "critical": 4,
}

# The highest rung each level runs without asking. -1 is below every rung: A0
# reaches nothing. No level reaches 4, which is what makes `critical` a floor by
# construction and not only by the explicit check below.
_REACH: Final[Mapping[AutonomyLevel, int]] = {
    "A0": -1,
    "A1": _RUNG["none"],
    "A2": _RUNG["internal"],
    "A3": _RUNG["external_idempotent"],
    "A4": _RUNG["external"],
}


def lower_autonomy(first: AutonomyLevel, second: AutonomyLevel) -> AutonomyLevel:
    """The more restrictive of two levels.

    How a tenant's ceiling combines with a worker's declared level: a tenant may
    hold a worker below what it was built for, and never lift it above.
    """
    return first if AUTONOMY_LEVELS.index(first) <= AUTONOMY_LEVELS.index(second) else second


def _rung_of(tool: ToolDefinition) -> int:
    if tool.side_effect_level == "external" and tool.idempotent:
        return _RUNG["external_idempotent"]
    return _RUNG[tool.side_effect_level]


@dataclass(frozen=True)
class AutonomyApprovalPolicy:
    """Decides, per call, whether a tool waits for a person."""

    policy_version: str = AUTONOMY_POLICY_VERSION

    def decide(self, tool: ToolDefinition, run_context: RunContext) -> bool:
        """Whether this call waits for a person, for this run.

        What every gate calls. It reads the level from the run and refuses to
        decide for a run stamped under a policy version this process does not
        have: that run was promised one set of rules, and applying another would
        quietly change what it was allowed after the fact. A version stamp nothing
        checks is decoration — the same failure `model/budget.py` names for a limit
        that is configured and never enforced.
        """
        stamped = run_context.approval_policy_version
        if stamped is not None and stamped != self.policy_version:
            return True
        return self.requires_approval(tool, autonomy=run_context.autonomy_level)

    def requires_approval(self, tool: ToolDefinition, *, autonomy: AutonomyLevel | None) -> bool:
        # The floors, first and unconditionally. `critical` is also out of every
        # level's reach below; checking it here as well means that stays true
        # even if someone one day extends a level's reach.
        if tool.approval_policy == "always" or tool.side_effect_level == "critical":
            return True
        # A run whose autonomy was never resolved has not been through the runner
        # that sets it. Refusing is recoverable; acting on a guess is not.
        if autonomy is None:
            return True
        return _rung_of(tool) > _REACH[autonomy]
