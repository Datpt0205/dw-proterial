"""A ceiling on what one run may spend, enforced rather than declared.

Every model profile has carried `budgets` since the profiles were written, and
until now nothing read it. A limit that is configured and unenforced is worse
than no limit: it reads like a control in review, and the first runaway loop
discovers it was decoration.

The ceiling is a backstop, not a quality lever (ADR-19). A healthy run stops
because its coverage gate is satisfied, far below this. What this catches is the
case the gate cannot: a loop, a retry storm, or a lane whose answer does not
exist being asked for again and again.

Cost is computed from the route's declared price when the provider does not
report one, which is the normal case behind a gateway - the gateway returns
token counts and no money.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from dw_agent_runtime.model.profiles import ModelBudgets, ModelRoute
from dw_kernel.errors import DomainError

logger = logging.getLogger("dw_agent_runtime.budget")

_PER_MILLION = 1_000_000


class BudgetExceededError(DomainError):
    """This run has spent its ceiling and must stop."""


@dataclass
class RunSpend:
    """What one run has spent so far."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


def route_cost(route: ModelRoute, input_tokens: int, output_tokens: int) -> float:
    """What the call cost, from the route's declared price.

    Zero when the route declares no price. That is honest rather than
    convenient: an unpriced route contributes nothing to the cost ceiling, and
    the token ceiling is what protects such a run.
    """
    if route.price_per_million_input is None and route.price_per_million_output is None:
        return 0.0
    inbound = (route.price_per_million_input or 0.0) * input_tokens / _PER_MILLION
    outbound = (route.price_per_million_output or 0.0) * output_tokens / _PER_MILLION
    return inbound + outbound


@dataclass
class RunBudgetLedger:
    """Per-run spend, checked before a call and updated after it.

    In-process and per-gateway: it bounds one run inside one worker, which is
    where a loop actually burns money. A cross-process quota is a different
    control with a different home (the plan's per-tenant quota), and conflating
    them would make neither enforceable.
    """

    spend: dict[uuid.UUID, RunSpend] = field(default_factory=dict)

    def check(self, run_id: uuid.UUID, budgets: ModelBudgets, *, task: str) -> None:
        """Refuse the next call when this run has already spent its ceiling."""
        current = self.spend.get(run_id)
        if current is None:
            return
        if current.input_tokens >= budgets.max_input_tokens_per_run:
            raise BudgetExceededError(
                "run reached its input-token ceiling",
                details={
                    "run_id": str(run_id),
                    "task": task,
                    "input_tokens": str(current.input_tokens),
                    "ceiling": str(budgets.max_input_tokens_per_run),
                    "calls": str(current.calls),
                },
            )
        if current.cost_usd >= budgets.max_cost_usd_per_run:
            raise BudgetExceededError(
                "run reached its cost ceiling",
                details={
                    "run_id": str(run_id),
                    "task": task,
                    "cost_usd": f"{current.cost_usd:.4f}",
                    "ceiling": str(budgets.max_cost_usd_per_run),
                    "calls": str(current.calls),
                },
            )

    def record(
        self, run_id: uuid.UUID, *, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> RunSpend:
        current = self.spend.setdefault(run_id, RunSpend())
        current.input_tokens += input_tokens
        current.output_tokens += output_tokens
        current.cost_usd += cost_usd
        current.calls += 1
        return current

    def forget(self, run_id: uuid.UUID) -> RunSpend | None:
        """Drop a finished run, so a long-lived worker does not accumulate them."""
        return self.spend.pop(run_id, None)
