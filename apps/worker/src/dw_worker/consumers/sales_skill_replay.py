"""The replay of proposed DW1 skill versions (Sales ticket 40, dw_sales ADR
0014 decision 2), per workspace with Sales cases.

Each tick replays every proposal of the workspace's tenant that has no
replay yet (`dw_sales.application.skill_replay.SkillReplayer`): example mails
read with the proposal and with the skills in force, the counts stored
beside the proposal for the head. It only reads and stores a replay; the head
decides on the approval. A tenant with several workspaces is replayed once:
the first workspace's lane stores it, the next finds it stored.

This module only paces it and keeps one workspace's failure from costing the
others their tick.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from dw_sales.application.ports import SalesScope
from dw_worker.consumers.scope_failures import raise_if_failed

logger = logging.getLogger("dw_worker.sales_skill_replay")

# Every five minutes: a person who proposed a skill sees its replay soon, and
# a tick with no proposal waiting is one short read per workspace.
INTERVAL_SECONDS = 300.0


class ScopesPort(Protocol):
    """Every workspace with a Sales case (`SqlFollowupScopes.scopes`)."""

    async def scopes(self) -> Sequence[SalesScope]: ...


class ReplayLane(Protocol):
    async def tick(self, scope: SalesScope) -> int: ...


def build_sales_skill_replay_consumer(
    lane: ReplayLane, scopes: ScopesPort
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        failed = 0
        for scope in await scopes.scopes():
            try:
                replayed = await lane.tick(scope)
            except Exception:
                # Broad on purpose: a proposal not replayed waits for the next
                # tick, and the head cannot approve it meanwhile.
                logger.exception("sales_skill_replay: the tick failed in one workspace")
                failed += 1
                continue
            if replayed:
                logger.info("sales_skill_replay: replayed %d proposal(s)", replayed)
        raise_if_failed("sales_skill_replay", failed)

    return consume
