"""The scheduled optimiser of the description reading's prompt (ticket 43
part 3, dw_sales ADR 0015 decision 5).

Acceptance 3: a version worse on any decided line, or failing a security
case of the step's eval, is never proposed. And what holds whatever is
proposed: it waits on the head (the lane never decides, nothing applies
directly), and a tenant's decided lines are never another tenant's
demonstrations.

The model is scripted (`test_examples.Scripted`): it reads a line once a
decided line with the same words is shown, which is what a demonstration is
for; a demonstration marked as poison makes it state an attribute of a line
that states none, which the step's missing-evidence case must catch.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.model_reading import Demonstrations, DescriptionReader
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.application.prompt_optimiser import (
    OPTIMISER_LANE,
    Grade,
    PromptOptimiser,
    SecurityCase,
    better,
    security_cases,
)
from dw_sales.application.prompt_versions import (
    PROMPT_KEY,
    PROMPTS_APPROVAL,
    PromptBook,
    PromptDecisions,
    prompt_book,
)
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.evals.world import ALPHA, BETA, MemoryStore
from dw_sales.testing.labelled_examples import MemoryDescriptionExamples

from .test_examples import (
    BLACK22,
    GREEN,
    ITEMS,
    MISSING,
    READS,
    REPO,
    Scripted,
    decided,
    spans_of,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 20, tzinfo=UTC)
POISON = "Dây điện AWG18 POISON"
SECURITY = security_cases(
    json.loads(
        (REPO / "evals" / "fixtures" / "cases" / "sales_descriptions_security.json").read_text(
            encoding="utf-8"
        )
    )
)
MISSING_ONLY = (SecurityCase(kind="missing_evidence", case_id="miss-vi", description=MISSING),)


def learner(description: str, shown: list[str]) -> dict[str, Any] | None:
    """Reads GREEN once shown it; reads BLACK22 always, but forgets it when
    shown a line marked FORGET; states a family for a line stating nothing
    when shown POISON (a security case's failure)."""
    if description == MISSING:
        if POISON in shown:
            return {"family_span": MISSING, "family": "hook_up_wire"}
        return None
    if description == BLACK22:
        return None if any("FORGET" in s for s in shown) else READS[BLACK22]
    if description == GREEN:
        return READS[GREEN] if GREEN in shown else None
    return None


@dataclass
class _Rules:
    rules_of: OrderRules

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self.rules_of


@dataclass
class _Gate:
    open: bool = True

    async def allows(self, scope: SalesScope, rules: OrderRules, step: ModelStep) -> bool:
        return self.open


@dataclass
class _Catalog:
    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Any]]:
        return Snapshot(ITEMS, NOW)


@dataclass
class _Directory:
    async def list_members(self, context: AccessContext) -> list[Any]:
        return []


@dataclass
class Bench:
    store: MemoryStore = field(default_factory=MemoryStore)
    lines: MemoryDescriptionExamples = field(default_factory=MemoryDescriptionExamples)
    model: Scripted = field(default_factory=lambda: Scripted(learner))

    @property
    def book(self) -> PromptBook:
        return prompt_book(self.store.rule_versions)

    def optimiser(
        self, security: tuple[SecurityCase, ...] = MISSING_ONLY, *, new_cases: int = 20
    ) -> PromptOptimiser:
        platform = load_sales_policies(
            REPO / "configs" / "policies", REPO / "configs" / "copy"
        ).order_rules
        rules = platform.model_copy(
            update={
                "learning": platform.learning.model_copy(
                    # No index here: what is measured is the demonstrations.
                    update={"new_cases_to_retrain": new_cases, "examples_per_line": 0}
                )
            }
        )
        return PromptOptimiser(
            examples=self.lines,
            reader=DescriptionReader(self.model, prompts=self.book),
            book=self.book,
            rules=_Rules(rules),
            gate=_Gate(),
            catalog=_Catalog(),
            uow=self.store,
            directory=_Directory(),
            security=security,
            clock=FixedClock(NOW),
            ids=Uuid4Generator(),
            worker_id="sales-dw1",
            worker_version="1.0.0",
        )

    def decide(self, scope: SalesScope, *extra: tuple[int, str, str]) -> None:
        """Twenty GREEN lines of one customer, each its own order, the newest
        a line of each extra (number, description, code), each its own."""
        self.lines.add(scope, *(decided(n, GREEN, "HW-1011") for n in range(1, 21)))
        for n, description, code in extra:
            self.lines.add(scope, decided(n, description, code, customer=f"C{n:03d}"))

    async def proposals(self, scope: SalesScope) -> list[Any]:
        held = self.store.rule_versions.for_tenant(scope.tenant_id.value)
        return list(await held.list_all(keys=(PROMPT_KEY,)))


# ------------------------------------------------------------ the rule --


def test_better_means_no_line_worse_and_more_right_in_total() -> None:
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    before = {a: Grade.MISSED, b: Grade.RIGHT}
    assert better(before, {a: Grade.RIGHT, b: Grade.RIGHT})
    assert not better(before, {a: Grade.MISSED, b: Grade.RIGHT})  # not more right
    assert not better(before, {a: Grade.RIGHT, b: Grade.LISTED})  # one line worse
    assert not better(before, {a: Grade.RIGHT})  # a line not replayed


def test_the_security_cases_are_the_step_evals_own() -> None:
    kinds = {case.kind for case in SECURITY}
    assert kinds == {"injection", "missing_evidence", "misleading"}
    assert all(case.code for case in SECURITY if case.kind != "missing_evidence")


# ------------------------------------------------------------ the lane --


async def test_a_better_version_is_proposed_to_the_head_and_never_applied() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    outcome = await bench.optimiser().tick(ALPHA)

    assert outcome.reason == "proposed" and outcome.proposed is not None
    (version,) = await bench.proposals(ALPHA)
    assert version.status == "proposed"
    assert version.proposed_by == system_actor(OPTIMISER_LANE).value
    document = version.document
    assert [d["description"] for d in document["demonstrations"]] == [GREEN]
    # Every replayed line read right but the one whose own order's line is
    # the demonstration, which it is never shown.
    assert document["replay"] == {
        "cases": 20,
        "right_before": 0,
        "right_after": 19,
        "security_cases": 1,
    }
    # Waiting on the head: the readings still run on the platform's.
    assert await bench.book.demonstrations(ALPHA) == Demonstrations(None)
    (request,) = list(bench.store.approvals.rows.values())
    assert (request.approval_type, request.required_scope) == (
        PROMPTS_APPROVAL,
        "sales.rules.approve",
    )
    # The lane never decides what it proposed.
    lane = AccessContext(
        tenant_id=ALPHA.tenant_id.value,
        workspace_id=ALPHA.workspace_id.value,
        principal_id=system_actor(OPTIMISER_LANE).value,
        roles=frozenset(),
        scopes=frozenset({"sales.rules.approve"}),
        plan_id="background",
    )
    with pytest.raises(ConflictError):
        await PromptDecisions(bench.store, bench.book).check(
            request, ProposedDecision(True, "ok", {}, None), lane
        )
    # One proposal at a time: the next tick waits for the head.
    assert (await bench.optimiser().tick(ALPHA)).reason == "proposal_waiting"


async def test_a_demonstration_keeps_the_reading_its_line_was_confirmed_with() -> None:
    """Ticket 43, 2026-11-22: a decided line's reading goes into the version
    with it, so the reading under that version is shown the answer it was."""
    bench = Bench()
    spans = spans_of(GREEN)
    bench.lines.add(
        ALPHA,
        *(decided(n, GREEN, "HW-1011").model_copy(update={"spans": spans}) for n in range(1, 21)),
    )
    outcome = await bench.optimiser().tick(ALPHA)

    assert outcome.reason == "proposed"
    (version,) = await bench.proposals(ALPHA)
    (shown,) = version.document["demonstrations"]
    assert [(s["attribute"], s["span"]) for s in shown["spans"]] == [
        (s.attribute, s.span) for s in spans
    ]


async def test_a_version_worse_on_any_decided_line_is_never_proposed() -> None:
    """Acceptance 3: the FORGET line is the newest of its customer and read
    wrong, so every candidate shows it, and with it BLACK22, read right
    before, is read wrong; nineteen lines better do not buy one worse."""
    bench = Bench()
    bench.decide(ALPHA, (40, BLACK22, "HW-1004"), (41, "Dây FORGET AWG20 xanh lá", "HW-1011"))
    outcome = await bench.optimiser().tick(ALPHA)
    assert outcome.reason == "no_better_candidate"
    assert await bench.proposals(ALPHA) == []


async def test_a_version_failing_a_security_case_is_never_proposed() -> None:
    """Acceptance 3: the POISON line, shown as a demonstration, makes the
    model state a family for a line that states none."""
    bench = Bench()
    bench.decide(ALPHA, (40, POISON, "HW-1008"))
    outcome = await bench.optimiser().tick(ALPHA)
    assert outcome.reason == "no_better_candidate"
    assert await bench.proposals(ALPHA) == []


async def test_another_tenants_lines_are_never_this_tenants_demonstrations() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    bench.lines.add(BETA, *(decided(100 + n, BLACK22, "HW-1004") for n in range(20)))
    await bench.optimiser().tick(ALPHA)
    await bench.optimiser().tick(BETA)
    (alpha,) = await bench.proposals(ALPHA)
    assert {d["description"] for d in alpha.document["demonstrations"]} == {GREEN}
    # BETA's lines read right already: nothing better to propose, and no
    # proposal of ALPHA's is BETA's.
    assert await bench.proposals(BETA) == []
    assert all(run.tenant_id == ALPHA.tenant_id.value for run, _ in bench.model.calls[:21])


async def test_too_few_new_lines_or_no_security_case_proposes_nothing() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    assert (await bench.optimiser(new_cases=50).tick(ALPHA)).reason == "too_few_new_cases"
    assert (await bench.optimiser(security=()).tick(ALPHA)).reason == "no_security_cases"
    assert await bench.proposals(ALPHA) == []


async def test_a_replay_the_model_did_not_answer_proposes_nothing() -> None:
    from dw_agent_runtime.model.interpretation import ModelUnavailableError

    def down(description: str, shown: list[str]) -> dict[str, Any] | None:
        raise ModelUnavailableError("down")

    bench = Bench(model=Scripted(down))
    bench.decide(ALPHA)
    assert (await bench.optimiser().tick(ALPHA)).reason == "model_unanswered"
    assert await bench.proposals(ALPHA) == []
