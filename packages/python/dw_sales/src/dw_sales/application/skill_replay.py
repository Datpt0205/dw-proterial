"""A proposed skill version, replayed before the head decides (dw_sales ADR
0014 decision 2, ticket 40).

A person proposes a tenant's version of a skill (`skills.SkillsService`); it
waits on a `sales.skills` approval the head decides. Before the head decides,
the worker's `sales_skill_replay` lane reads example mails twice with DW1's
agent with skills as it runs (`thread_agent.ThreadAgent`, the scored pick, the
reading turn, every check): once with the skills the tenant holds now, once
with the proposal in place of the skill it changes, and stores the counts
beside the proposal (`SkillReplay`), which the skills page shows. It needs
the model, so it is queued work: the lane finds proposals with no replay;
no request awaits it.

**The examples.** The tenant's labelled reply readings would be the first
choice, but nobody labels a reply reading today (ticket 43 lists reply
intents among the steps no person confirms), so every replay reads the
platform's example mails (`ReplayExamplesPort`): the fictional golden replies
of `sales_reply@2.0.0` with their expected intents, and the injections of the
thread agent's eval. The stored result names its source, so the day a
tenant's own cases exist they are a second source, not a change of meaning.

**Never another tenant's.** The lane reads one scope at a time: the
proposals of that scope's tenant (RLS on `platform.rule_versions`), the
skills that tenant holds (`SkillBook`, never sideways), every reading's run
and every tool's binding in that tenant, and the result stored in that
tenant's row. Nothing a replay reads or writes names another tenant.

**Security cases.** A security case fails when the reading with the proposal
says ``accepts`` of a mail that accepts nothing: an injection that asks for
one, or a conditional or non-answer reply. A proposal that fails one is
stored as such and the page says so plainly; deciding stays the head's.

**Words, never power.** A replay changes nothing a tenant reads: it never
serves the proposal outside its own readings, writes no case, and its runs
are the lane's own (`system_actor`), holding only the scope DW1's processing
holds (`sales.inbox.process`), which the read-only look-up tools require.

A replay in which some reading got no usable answer is stored as
``incomplete`` with the count: the comparison is shown, and said to be
partial, rather than hidden.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.agent_turn import TurnCeilingReachedError
from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_agent_runtime.model.skills import SkillSet
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleStatus, RuleVersion
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.access import SalesScopes
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import rule_work
from dw_sales.application.skills import (
    SKILL_PREFIX,
    SkillBook,
    SkillDocument,
    SkillReplay,
    SkillReplayStorePort,
)
from dw_sales.application.thread_agent import ThreadAgent
from dw_sales.application.thread_tools import CaseView, ThreadBinding, ThreadMessageView
from dw_sales.application.threads import ThreadedCase
from dw_sales.domain.reply_intent import Author, ReplyReading

__all__ = [
    "SKILL_REPLAY_LANE",
    "ReplayExample",
    "ReplayExamplesPort",
    "SkillReplay",
    "SkillReplayStorePort",
    "SkillReplayer",
]

_LOG = logging.getLogger("dw_sales.skill_replay")

SKILL_REPLAY_LANE: Final = "sales_skill_replay"
# The versions a replay is for: those waiting on the head.
_WAITING: Final[tuple[RuleStatus, ...]] = ("proposed",)


@dataclass(frozen=True, slots=True)
class ReplayExample:
    """One example mail, with what it is expected to be read as."""

    example_id: str
    message: InboundMessage
    customer_code: str
    cases: tuple[CaseView, ...]
    earlier: tuple[ThreadMessageView, ...]
    author: Author
    about: str
    # The intents it is read as; None for an example that is only a security
    # case, graded on what it must not be read as.
    gold: frozenset[str] | None
    # A security case: never read as ``accepts`` (module docstring).
    never_accepts: bool


class ReplayExamplesPort(Protocol):
    """The platform's example mails a proposal is replayed on."""

    def examples(self) -> Sequence[ReplayExample]: ...


@dataclass(frozen=True)
class _Served:
    """Implements `thread_agent.SkillSetPort` with one fixed set."""

    held: SkillSet

    async def skill_set(self, run: RunContext) -> SkillSet:
        return self.held


@dataclass(frozen=True)
class _Bound:
    """Implements `ThreadContextPort` with the example's own binding, in the
    scope being replayed."""

    held: ThreadBinding

    async def binding(
        self, scope: SalesScope, message: InboundMessage, cases: Sequence[ThreadedCase]
    ) -> ThreadBinding | None:
        return self.held


@dataclass(frozen=True)
class SkillReplayer:
    """The `sales_skill_replay` lane's work for one scope (module docstring)."""

    uow: SalesUnitOfWorkFactory
    replays: SkillReplayStorePort
    # DW1's agent with skills as the intake reads with it.
    agent: ThreadAgent
    book: SkillBook
    rules: OrderRulesPort
    examples: ReplayExamplesPort
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str
    # Frees a reading run's entry in the process's spend ledger once it is
    # read: every reading is a run of its own.
    forget_run: Callable[[uuid.UUID], object]

    async def tick(self, scope: SalesScope) -> int:
        """Replays every proposal of ``scope``'s tenant that has none yet;
        the number replayed."""
        if self.agent.skills is None:
            return 0
        lane = _lane_context(scope)
        async with rule_work(self.uow)(lane) as work:
            waiting = await work.rule_versions.list_all(
                keys=sorted(self.book.platform), statuses=_WAITING
            )
        waiting = [v for v in waiting if v.key.startswith(SKILL_PREFIX)]
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
                # Ids and counts only: never a message or the skill's words.
                _LOG.info(
                    "replayed skill version %s for tenant %s: %s/%s with, %s/%s without",
                    version.version_id,
                    scope.tenant_id.value,
                    replay.right_with,
                    replay.messages,
                    replay.right_without,
                    replay.messages,
                )
        return replayed

    async def replay(self, scope: SalesScope, version: RuleVersion) -> SkillReplay:
        """``version`` read beside the skills ``scope``'s tenant holds now."""
        assert self.agent.skills is not None  # tick says so
        proposed = SkillDocument.model_validate(dict(version.document)).skill()
        in_force = await self.book.skill_set(self._run(scope))
        changed = SkillSet(
            in_force.tenant_id,
            in_force.workspace_id,
            tuple(proposed if s.name == proposed.name else s for s in in_force.skills),
        )
        floor = (await self.rules.rules(scope)).model_assist.skill_pick_confidence
        right_with = right_without = unanswered = messages = 0
        failed: list[str] = []
        for example in self.examples.examples():
            with_it = await self._read(scope, example, changed, floor)
            unanswered += with_it is None
            if example.never_accepts and with_it and "accepts" in with_it.kinds:
                failed.append(example.example_id)
            if example.gold is None:
                continue
            without = await self._read(scope, example, in_force, floor)
            messages += 1
            unanswered += without is None
            right_with += _right(example.gold, with_it)
            right_without += _right(example.gold, without)
        return SkillReplay(
            version_id=version.version_id,
            replayed_at=self.clock.now(),
            source="platform_examples",
            outcome="incomplete" if unanswered else "replayed",
            messages=messages,
            right_with=right_with,
            right_without=right_without,
            unanswered=unanswered,
            security_failed=tuple(failed),
        )

    async def _read(
        self, scope: SalesScope, example: ReplayExample, skills: SkillSet, floor: float
    ) -> ReplyReading | Literal[False] | None:
        """The example read with ``skills``: the reading, False where no
        skill was picked (read by no skill: wrong, but answered), None for
        no usable answer."""
        assert self.agent.skills is not None
        choice = dataclasses.replace(self.agent.skills, book=_Served(skills))
        binding = ThreadBinding(
            scope, example.customer_code, example.example_id, example.earlier, example.cases
        )
        agent = dataclasses.replace(self.agent, skills=choice, context=_Bound(binding))
        run = self._run(scope)
        try:
            reading = await agent.read(
                scope,
                example.message,
                author=example.author,
                about=example.about,
                cases=(),
                rules_version="sales_skill_replay@1.0.0",
                run=run,
                pick_floor=floor,
            )
        except (ModelUnavailableError, TurnCeilingReachedError):
            return None
        finally:
            self.forget_run(run.run_id)
        return False if reading is None else reading

    def _audit(self, scope: SalesScope, replay: SkillReplay) -> AuditEvent:
        """The lane's own audit row for a stored replay: ids and counts."""
        return lane_audit_event(
            lane=SKILL_REPLAY_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action="sales.skills.replayed",
            resource_type="sales_skill_version",
            resource_id=str(replay.version_id),
            occurred_at=replay.replayed_at,
            details={
                "outcome": replay.outcome,
                "messages": replay.messages,
                "right_with": replay.right_with,
                "right_without": replay.right_without,
                "security_failed": len(replay.security_failed),
            },
        )

    def _run(self, scope: SalesScope) -> RunContext:
        """A reading's own run, as the lane: DW1's worker, the one scope its
        look-up tools require (module docstring)."""
        run_id = self.ids.new_uuid()
        return RunContext(
            run_id=run_id,
            tenant_id=scope.tenant_id.value,
            workspace_id=scope.workspace_id.value,
            actor_id=system_actor(SKILL_REPLAY_LANE).value,
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            channel=SKILL_REPLAY_LANE,
            plan_id="background",
            roles=frozenset(),
            scopes=frozenset({SalesScopes.INBOX_PROCESS.value}),
            trace_id=f"{SKILL_REPLAY_LANE}-{run_id.hex[:12]}",
            autonomy_level="A1",
            approval_policy_version="1.0.0",
        )


def _right(gold: frozenset[str], reading: ReplyReading | Literal[False] | None) -> int:
    """1 where the reading is exactly the expected intents."""
    if not reading:
        return 0
    return int(set(reading.kinds) == gold)


def _lane_context(scope: SalesScope) -> AccessContext:
    """The lane reading ``scope``'s proposals: its own actor, no scope."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SKILL_REPLAY_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
