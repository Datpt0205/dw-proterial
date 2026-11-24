"""A customer's SalesOrder skill, replayed on all of the customer's worked
pairs before the head decides it (ticket 41, dw_sales ADR 0013 decision 3 as
amended under ADR 0014).

A worked pair is a PO and the SalesOrder file the PIC made from it
(`salesorder_learning.WorkedPair`), kept whenever an uploaded example is
read. A person proposes a version of a customer's SalesOrder skill as any
skill (`skills.SkillsService`, ``salesorder-<customer code>``); it waits on a
`sales.skills` approval. The worker's `sales_salesorder_skill_replay` lane
then fills every pair's PO twice, with the proposal and with the skill in
force (`salesorder_fill.SalesOrderFiller`, every cell traced), compares each
fill with the PIC's file (`salesorder_fill.check_against`), and stores the
counts beside the proposal (`skills.SkillReplay`, source ``customer_pairs``:
``messages`` the pairs, ``right_with`` and ``right_without`` the pairs each
reproduced). The head may approve the version only where every pair was
reproduced with it (`skills.SkillDecisions`); a version no pair proves
cannot be approved either. It needs the model, so it is queued work: no
request awaits it.

**Never another tenant's or customer's.** The lane reads one scope at a time:
the proposals of that scope's tenant (RLS on `platform.rule_versions`), the
pairs of that workspace and of the version's own customer, the tools bound
to that customer (`SalesOrderTools.bound`), the skill in force through the
tenant's book (never sideways), and the result in that tenant's row.

**As itself.** Every fill is a run of the lane's own (`system_actor`), with
no scope: the fill's tools are code's, called before the turn, and need none.

A replay in which some fill got no usable answer is stored ``incomplete``
with the count, and an incomplete replay is not one the head may approve on.

**A pair leaves two ways** (ticket 41's leftovers), and is then neither
replayed nor listed:

- **withdrawn** by a person who proposes rules and reads prices, as the
  examples' own screen asks (`WorkedPairs.withdraw`): a pair whose PIC's file
  was wrong would fail every replay of the customer's skill for good. Audited
  in that person's name: the pair, its customer, its day and its row count,
  never a cell. A replay already stored beside a waiting version stays what
  it was: it counted the pair, and is read as it was stored.
- **dropped past the tenant's term** (`OrderRules.learning.
  salesorder_pairs_kept_days`) by the worker's
  `sales_salesorder_pairs_retention` lane (`WorkedPairRetention`), hourly, in
  each workspace's own scope, audited as the lane with the count.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import NotFoundError, QuotaExceededError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleStatus, RuleVersion
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import BravoUploadLayout
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.application.rules import RuleKey, rule_work
from dw_sales.application.salesorder_fill import (
    FillSkill,
    SalesOrderFiller,
    SalesOrderTools,
    TracedFill,
    check_against,
    po_rows,
)
from dw_sales.application.salesorder_learning import (
    ExampleUnitOfWorkFactory,
    LearningRulesPort,
    WorkedPair,
)
from dw_sales.application.skills import (
    SALESORDER_PREFIX,
    SkillBook,
    SkillDocument,
    SkillReplay,
    SkillReplayStorePort,
    is_salesorder_key,
    salesorder_key,
)
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.domain.order_checks import OrderRules

__all__ = [
    "PAIRS_REPLAYED",
    "SALESORDER_PAIRS_RETENTION_LANE",
    "SALESORDER_SKILL_REPLAY_LANE",
    "SalesOrderSkillReplayer",
    "WorkedPairRetention",
    "WorkedPairView",
    "WorkedPairs",
    "fill_pair",
    "lane_run",
]

_LOG = logging.getLogger("dw_sales.salesorder_pairs")

SALESORDER_SKILL_REPLAY_LANE: Final = "sales_salesorder_skill_replay"
# The customer's newest pairs a version is replayed on: each costs two fills.
PAIRS_REPLAYED: Final = 20
# How often a pair's fill is asked before it counts as unanswered.
FILL_ATTEMPTS: Final = 2
# The versions a replay is for: those waiting on the head.
_WAITING: Final[tuple[RuleStatus, ...]] = ("proposed",)
SALESORDER_PAIRS_RETENTION_LANE: Final = "sales_salesorder_pairs_retention"
# The customer's newest pairs its screen lists.
PAIRS_LISTED: Final = 50
_PAIR_RESOURCE: Final = "sales_salesorder_pair"


class PairCatalogPort(Protocol):
    """The master data a replay reads (`SalesCatalogPort`'s own methods):
    the workspace's customers, whose skills' proposals it looks for, and a
    customer's record, convert list and items, which its tools are bound to."""

    async def customers(self, scope: SalesScope) -> Snapshot[Sequence[Customer]]: ...

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]: ...

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]: ...

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]: ...


@dataclass(frozen=True)
class SalesOrderSkillReplayer:
    """The `sales_salesorder_skill_replay` lane's work for one scope
    (module docstring)."""

    uow: SalesUnitOfWorkFactory
    pairs: ExampleUnitOfWorkFactory
    replays: SkillReplayStorePort
    book: SkillBook
    rules: LearningRulesPort
    catalog: PairCatalogPort
    filler: SalesOrderFiller
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def tick(self, scope: SalesScope) -> int:
        """Replays every waiting version of a customer's SalesOrder skill in
        ``scope``'s tenant that has no replay yet; the number replayed."""
        customers = (await self.catalog.customers(scope)).data
        keys = sorted({salesorder_key(c.code) for c in customers})
        if not keys:
            return 0
        async with rule_work(self.uow)(_lane_context(scope)) as work:
            waiting = await work.rule_versions.list_all(keys=keys, statuses=_WAITING)
        waiting = [v for v in waiting if is_salesorder_key(v.key)]
        if not waiting:
            return 0
        done = await self.replays.stored(scope, [v.version_id for v in waiting])
        replayed = 0
        for version in waiting:
            if version.version_id in done:
                continue
            replay = await self.replay(scope, version)
            if await self.replays.store(scope, replay, self._audit(scope, replay)):
                replayed += 1
                # Ids and counts only: never a cell or the skill's words.
                _LOG.info(
                    "replayed SalesOrder skill version %s for tenant %s: %s/%s pairs with,"
                    " %s/%s without",
                    version.version_id,
                    scope.tenant_id.value,
                    replay.right_with,
                    replay.messages,
                    replay.right_without,
                    replay.messages,
                )
        return replayed

    async def replay(self, scope: SalesScope, version: RuleVersion) -> SkillReplay:
        """``version`` filled on each of its customer's pairs beside the
        customer's skill in force."""
        code = version.key.removeprefix(SALESORDER_PREFIX).upper()
        proposed = SkillDocument.model_validate(dict(version.document))
        in_force = (await self.book.current(scope, version.key)).policy
        assert isinstance(in_force, SkillDocument)
        customer = (await self.catalog.customer_by_code(scope, code)).data
        async with self.pairs(scope) as work:
            pairs = list(await work.pairs.for_customer(code, PAIRS_REPLAYED))
        layout = (await self.rules.current(scope, RuleKey.BRAVO_UPLOAD)).policy
        assert isinstance(layout, BravoUploadLayout)
        right_with = right_without = unanswered = 0
        if customer is not None and pairs:
            tools = SalesOrderTools.bound(
                customer,
                (await self.catalog.convert_list(scope)).data,
                (await self.catalog.items(scope)).data,
            )
            for pair in pairs:
                with_it = await fill_pair(
                    self.filler, layout, tools, pair, _skill(proposed), self._run(scope)
                )
                without = await fill_pair(
                    self.filler, layout, tools, pair, _skill(in_force), self._run(scope)
                )
                unanswered += (with_it is None) + (without is None)
                right_with += _reproduced(layout, with_it, pair)
                right_without += _reproduced(layout, without, pair)
        return SkillReplay(
            version_id=version.version_id,
            replayed_at=self.clock.now(),
            source="customer_pairs",
            outcome="incomplete" if unanswered else "replayed",
            messages=len(pairs) if customer is not None else 0,
            right_with=right_with,
            right_without=right_without,
            unanswered=unanswered,
        )

    def _audit(self, scope: SalesScope, replay: SkillReplay) -> AuditEvent:
        """The lane's own audit row for a stored replay: ids and counts."""
        return lane_audit_event(
            lane=SALESORDER_SKILL_REPLAY_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action="sales.skills.replayed",
            resource_type="sales_skill_version",
            resource_id=str(replay.version_id),
            occurred_at=replay.replayed_at,
            details={
                "source": replay.source,
                "outcome": replay.outcome,
                "pairs": replay.messages,
                "right_with": replay.right_with,
                "right_without": replay.right_without,
            },
        )

    def _run(self, scope: SalesScope) -> RunContext:
        return lane_run(
            SALESORDER_SKILL_REPLAY_LANE,
            scope,
            self.ids.new_uuid(),
            self.worker_id,
            self.worker_version,
        )


def lane_run(
    lane: str, scope: SalesScope, run_id: UUID, worker_id: str, worker_version: str
) -> RunContext:
    """A model call's own run, as ``lane``, holding no scope: a fill's tools
    are code's, called before the turn, and need none."""
    return RunContext(
        run_id=run_id,
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        actor_id=system_actor(lane).value,
        worker_id=worker_id,
        worker_version=worker_version,
        channel=lane,
        plan_id="background",
        roles=frozenset(),
        scopes=frozenset(),
        trace_id=f"{lane}-{run_id.hex[:12]}",
        autonomy_level="A1",
        approval_policy_version="1.0.0",
    )


async def fill_pair(
    filler: SalesOrderFiller,
    layout: BravoUploadLayout,
    tools: SalesOrderTools,
    pair: WorkedPair,
    skill: FillSkill,
    run: RunContext,
) -> TracedFill | None:
    """The pair's PO filled with ``skill``; None for no usable answer, the
    plan's day spent included: a comparison with a gap proves nothing. A
    fill with no usable answer is asked once more (`FILL_ATTEMPTS`): in the
    first live run on Strata a fill came back malformed (ticket 66), and a
    replay waits on no one."""
    for _ in range(FILL_ATTEMPTS):
        try:
            return await filler.fill(
                layout=layout,
                rows=po_rows(pair.document, tools, pair.received_on),
                tools=tools,
                skill=skill,
                run=run,
            )
        except QuotaExceededError:
            return None
        except ModelUnavailableError:
            continue
    return None


def _skill(document: SkillDocument) -> FillSkill:
    return FillSkill(ref=document.ref, instructions=document.instructions)


def _reproduced(layout: BravoUploadLayout, fill: TracedFill | None, pair: WorkedPair) -> int:
    """1 where the fill came out as the PIC's file, every cell traced."""
    if fill is None:
        return 0
    return int(check_against(layout, fill, pair.expected).reproduced)


def _lane_context(scope: SalesScope) -> AccessContext:
    """The lane reading ``scope``'s proposals: its own actor, no scope."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SALESORDER_SKILL_REPLAY_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


# ------------------------------------------------ a pair withdrawn or dropped --


class WorkedPairView(BaseModel):
    """A pair as the customer's screen lists it: which PO, when, how many
    rows; never a cell (module docstring)."""

    model_config = ConfigDict(frozen=True)

    pair_id: UUID
    example_id: UUID | None
    customer_code: str
    po_no: str
    received_on: date
    rows: int
    added_by: UUID
    added_at: datetime
    # Among the customer's newest `PAIRS_REPLAYED`: what a replay reads.
    replayed: bool


def _pair_view(pair: WorkedPair, replayed: bool) -> WorkedPairView:
    return WorkedPairView(
        pair_id=pair.pair_id,
        example_id=pair.example_id,
        customer_code=pair.customer_code,
        po_no=str(pair.document.header.po_no),
        received_on=pair.received_on,
        rows=len(pair.expected),
        added_by=pair.added_by,
        added_at=pair.added_at,
        replayed=replayed,
    )


def _pair_details(pair: WorkedPair) -> dict[str, object]:
    """What an audit row says of a pair: ids, its day and row count."""
    return {
        "customer_code": pair.customer_code,
        "example_id": None if pair.example_id is None else str(pair.example_id),
        "received_on": pair.received_on.isoformat(),
        "rows": len(pair.expected),
        "added_by": str(pair.added_by),
    }


@dataclass(frozen=True)
class WorkedPairs:
    """The customer's screen's side: the customer's pairs, and one withdrawn
    (module docstring). Whoever may upload an example: `sales.rules.propose`
    and `sales.price.read`, since a pair is a priced file."""

    uow: ExampleUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator

    async def _require(self, context: AccessContext, pair_id: UUID | None = None) -> None:
        await self.gate.require(
            context,
            SalesScopes.RULES_PROPOSE,
            SalesScopes.PRICE_READ,
            resource_type=_PAIR_RESOURCE,
            resource_id=None if pair_id is None else str(pair_id),
        )

    async def for_customer(
        self, context: AccessContext, customer_code: str
    ) -> list[WorkedPairView]:
        """The customer's newest pairs in the caller's workspace (RLS)."""
        await self._require(context)
        async with self.uow(sales_scope(context)) as work:
            pairs = await work.pairs.for_customer(customer_code, PAIRS_LISTED)
        return [_pair_view(p, i < PAIRS_REPLAYED) for i, p in enumerate(pairs)]

    async def withdraw(self, context: AccessContext, pair_id: UUID) -> WorkedPairView:
        """The pair dropped, with its audit row, in one transaction. Another
        workspace's or tenant's pair, or one already gone, is not found
        alike: RLS leaves it out."""
        await self._require(context, pair_id)
        async with self.uow(sales_scope(context)) as work:
            pair = await work.pairs.withdraw(pair_id)
            if pair is None:
                raise NotFoundError("no such pair", details={"pair_id": str(pair_id)})
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.salesorder_pair.withdrawn",
                    resource_type=_PAIR_RESOURCE,
                    resource_id=str(pair_id),
                    occurred_at=self.clock.now(),
                    details=_pair_details(pair),
                )
            )
            await work.commit()
        return _pair_view(pair, replayed=False)


@dataclass(frozen=True)
class WorkedPairRetention:
    """The `sales_salesorder_pairs_retention` lane's work for one scope: the
    pairs older than the tenant's term dropped (module docstring)."""

    pairs: ExampleUnitOfWorkFactory
    rules: LearningRulesPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: SalesScope) -> int:
        """Drops ``scope``'s pairs past the term; how many."""
        rules = (await self.rules.current(scope, RuleKey.ORDER_RULES)).policy
        assert isinstance(rules, OrderRules)
        days = rules.learning.salesorder_pairs_kept_days
        now = self.clock.now()
        async with self.pairs(scope) as work:
            dropped = await work.pairs.prune(now - timedelta(days=days))
            if dropped:
                await work.audit.append(
                    lane_audit_event(
                        lane=SALESORDER_PAIRS_RETENTION_LANE,
                        event_id=self.ids.new_uuid(),
                        tenant_id=scope.tenant_id,
                        workspace_id=scope.workspace_id,
                        action="sales.salesorder_pairs.pruned",
                        resource_type=_PAIR_RESOURCE,
                        resource_id=str(scope.workspace_id.value),
                        occurred_at=now,
                        details={"pairs": dropped, "kept_days": days},
                    )
                )
            await work.commit()
        return dropped
