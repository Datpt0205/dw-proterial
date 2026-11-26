"""DW1 learning from what people decided (Sales ticket 43, dw_sales ADR 0015
decision 5): two lanes, each per workspace with Sales cases.

- `sales_examples`: the decided lines indexed for the readings to be shown
  (`dw_sales.application.examples.ExampleIndexLane`), then every point whose
  case has left the store with its month dropped
  (`dw_knowledge.examples.ExampleGateway.prune`, at the labelled cases' term).
- `sales_prompt_optimiser`: a better prompt version proposed to the head
  where enough lines were decided since the last proposal
  (`dw_sales.application.prompt_optimiser.PromptOptimiser`). It only
  proposes; the head decides on the approval.

This module only paces them and keeps one workspace's failure from costing the
others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from dw_sales.application.ports import SalesScope
from dw_sales.application.prompt_optimiser import Outcome
from dw_worker.consumers.scope_failures import raise_if_failed

logger = logging.getLogger("dw_worker.sales_learning")

# Every five minutes: a line decided now is shown to readings within it, and
# a tick with nothing new is one indexed read per workspace.
EXAMPLES_INTERVAL_SECONDS = 300.0
# Daily: the lane proposes only once enough lines were decided since the last
# proposal (the tenant's `learning.new_cases_to_retrain`), and replaying every
# decided line costs model calls, so a quieter workspace waits for its count.
OPTIMISER_INTERVAL_SECONDS = 86_400.0


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


class ExamplesLane(Protocol):
    async def tick(self, scope: SalesScope) -> int: ...


class OptimiserLane(Protocol):
    async def tick(self, scope: SalesScope) -> Outcome: ...


def build_sales_examples_consumer(
    lane: ExamplesLane,
    scopes: ScopesPort,
    prune: Callable[[datetime], Awaitable[None]],
    cutoff: Callable[[], datetime | None],
) -> Callable[[], Awaitable[None]]:
    """``cutoff``: before when a decided line has left the store (None: the
    term is not enforced, and nothing is pruned)."""

    async def consume() -> None:
        failed = 0
        for scope in await scopes.scopes():
            try:
                indexed = await lane.tick(scope)
            except Exception:
                # Broad on purpose: a line not indexed is only not shown yet.
                logger.exception("sales_examples: indexing failed in one workspace")
                failed += 1
                continue
            if indexed:
                logger.info("sales_examples: indexed %d decided line(s)", indexed)
        before = cutoff()
        if before is not None:
            # Raises: a vector outliving its case is the retention failing.
            await prune(before)
        raise_if_failed("sales_examples", failed)

    return consume


def build_sales_prompt_optimiser_consumer(
    lane: OptimiserLane, scopes: ScopesPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        failed = 0
        for scope in await scopes.scopes():
            try:
                outcome = await lane.tick(scope)
            except Exception:
                logger.exception("sales_prompt_optimiser: the tick failed in one workspace")
                failed += 1
                continue
            logger.info(
                "sales_prompt_optimiser: %s",
                outcome.reason,
                extra={"proposed": outcome.proposed},
            )
        raise_if_failed("sales_prompt_optimiser", failed)

    return consume
