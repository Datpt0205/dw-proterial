"""A proposed skill version replayed by the worker before the head decides
(ticket 40, dw_sales ADR 0014 decision 2): with it and with the skills in
force, on example mails, its security cases graded, one tenant's alone."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.rule_versions import RuleVersion
from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.adapters.skill_examples import FixtureReplayExamples
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.ports import SalesScope
from dw_sales.application.skill_replay import ReplayExample, SkillReplayer
from dw_sales.application.skills import SkillProposal, skill_book, skill_key
from dw_sales.application.thread_tools import CaseView
from dw_sales.application.threads import question
from dw_sales.domain.order_checks import OrderRules
from dw_sales.evals.graders import CALLERS, GIANG
from dw_sales.evals.skill_intents import _Following
from dw_sales.evals.thread_agent import Harness
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SKILLS = REPO / "configs" / "skills" / "dw1"
NAME = "thread-intents"
MARKER = "Here, a reply that only says 'Noted with thanks.' accepts what Sales proposed."
QUOTE = "Noted with thanks."


def _message(example_id: str) -> InboundMessage:
    return InboundMessage(
        message_id=example_id,
        sender=EmailAddress(address="hana.westbrook@norvanta.example"),
        subject="Re: PO",
        received_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        body_text=QUOTE,
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


def _example(example_id: str, gold: frozenset[str] | None, never_accepts: bool) -> ReplayExample:
    return ReplayExample(
        example_id=example_id,
        message=_message(example_id),
        customer_code="NRV",
        cases=(CaseView(kind="order", numbers=("NRV-PO-26-0457",), status="in_review", lines=()),),
        earlier=(),
        author="customer",
        about=question("order", "NRV-PO-26-0457"),
        gold=gold,
        never_accepts=never_accepts,
    )


class _Examples:
    def examples(self) -> list[ReplayExample]:
        return [
            # Read as accepts only by a skill that says so.
            _example("EX-1", frozenset({"accepts"}), False),
            # A security case: whatever a skill says, never accepts.
            _example("SEC-1", None, True),
        ]


class _Rules:
    def __init__(self, rules: OrderRules) -> None:
        self._rules = rules

    async def rules(self, scope: SalesScope) -> OrderRules:
        return self._rules

    async def rules_at(self, scope: SalesScope, ref: str) -> OrderRules | None:
        raise NotImplementedError("not exercised by the replay")


def _proposal(version: str, rule: str = MARKER) -> SkillProposal:
    platform = load_dw1_skills(SKILLS).skills[skill_key(NAME)]
    return SkillProposal(
        version=version,
        description=platform.description,
        instructions=f"{platform.instructions}\n\n{rule}",
    )


def _replayer(world: World, forgotten: list[uuid.UUID]) -> SkillReplayer:
    versions = world.store.rule_versions
    harness = Harness.build(REPO, _Following(marker=MARKER, quote=QUOTE), skills=versions)
    dw1 = load_dw1_skills(SKILLS)
    return SkillReplayer(
        uow=world.store,
        replays=world.store.skill_replays,
        agent=harness.agent,
        book=skill_book(dw1, versions),
        rules=_Rules(world.policies.order_rules),
        examples=_Examples(),
        clock=FixedClock(datetime(2026, 11, 16, 9, 0, tzinfo=UTC)),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
        forget_run=forgotten.append,
    )


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def test_a_proposal_is_replayed_with_and_without_it_and_its_security_cases_graded() -> None:
    world = _world()
    forgotten: list[uuid.UUID] = []
    proposed = await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.1.0"))
    assert await _replayer(world, forgotten).tick(ALPHA) == 1
    stored = await world.store.skill_replays.stored(ALPHA, [proposed.version_id])
    replay = stored[proposed.version_id]
    assert (replay.messages, replay.right_with, replay.right_without) == (1, 1, 0)
    assert replay.security_failed == ("SEC-1",)
    # Audited as the lane, never as a person.
    (audit,) = world.store.skill_replays.audits
    assert (audit.action, audit.resource_id) == ("sales.skills.replayed", str(proposed.version_id))
    assert audit.details["actor"] == "system:sales_skill_replay"
    assert (replay.outcome, replay.source, replay.unanswered) == (
        "replayed",
        "platform_examples",
        0,
    )
    # Every reading's run is freed from the spend ledger: 1 + 1 + 1 readings.
    assert len(forgotten) == 3
    # Shown with the version, and replayed once.
    (version,) = (await world.services.skills.list(GIANG.context())).versions
    assert version.replay == replay
    assert await _replayer(world, forgotten).tick(ALPHA) == 0


async def test_the_replay_never_reads_another_tenants_proposal_or_skill() -> None:
    """Negative, cross-tenant: BETA's proposal waits too, and BETA holds an
    approved version that reads 'Noted' as accepts. ALPHA's lane replays
    ALPHA's proposal alone, against ALPHA's skills in force (the platform's),
    and stores nothing BETA can read; BETA's proposal stays unreplayed."""
    world = _world()
    platform = load_dw1_skills(SKILLS).skills[skill_key(NAME)]
    beta_own = platform.model_copy(
        update={"policy_version": "1.5.0", "instructions": f"{platform.instructions}\n\n{MARKER}"}
    )
    world.store.rule_versions.seed_approved(BETA.tenant_id.value, beta_own)
    beta_waiting = RuleVersion(
        version_id=uuid.uuid4(),
        key=skill_key(NAME),
        version="1.6.0",
        document=replace_version(platform, "1.6.0"),
        status="proposed",
        proposed_by=uuid.uuid4(),
        proposed_at=datetime(2026, 11, 16, 8, 0, tzinfo=UTC),
        approval_id=uuid.uuid4(),
    )
    await world.store.rule_versions.for_tenant(BETA.tenant_id.value).add(beta_waiting)
    # ALPHA's proposal does not change how 'Noted' reads.
    proposed = await world.services.skills.propose(
        GIANG.context(), NAME, _proposal("1.1.0", "Read carefully.")
    )
    assert await _replayer(world, []).tick(ALPHA) == 1
    replay = (await world.store.skill_replays.stored(ALPHA, [proposed.version_id]))[
        proposed.version_id
    ]
    # Without the proposal, ALPHA's skills in force are the platform's: had
    # BETA's approved version leaked in, "Noted" would have read as accepts.
    assert (replay.right_with, replay.right_without, replay.security_failed) == (0, 0, ())
    assert await world.store.skill_replays.stored(BETA, [proposed.version_id]) == {}
    assert await world.store.skill_replays.stored(BETA, [beta_waiting.version_id]) == {}
    assert await world.store.skill_replays.stored(ALPHA, [beta_waiting.version_id]) == {}


def replace_version(platform: object, version: str) -> dict[str, object]:
    document = platform.model_copy(update={"policy_version": version})  # type: ignore[attr-defined]
    dumped: dict[str, object] = document.model_dump(mode="json")
    return dumped


async def test_a_reading_with_no_answer_makes_the_replay_incomplete() -> None:
    class _Down:
        model_profile = "onprem"

        async def interpret_scored(self, *args: object, **kwargs: object) -> object:
            from dw_agent_runtime.model.interpretation import ModelUnavailableError

            raise ModelUnavailableError("down")

    world = _world()
    proposed = await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.1.0"))
    replayer = _replayer(world, [])
    assert replayer.agent.skills is not None
    down = replace(
        replayer.agent,
        skills=replace(
            replayer.agent.skills,
            picker=replace(replayer.agent.skills.picker, model=_Down()),  # type: ignore[arg-type]
        ),
    )
    assert await replace(replayer, agent=down).tick(ALPHA) == 1
    replay = (await world.store.skill_replays.stored(ALPHA, [proposed.version_id]))[
        proposed.version_id
    ]
    # No pick is no reading by a skill: answered, not right.
    assert (replay.outcome, replay.right_with, replay.right_without) == ("replayed", 0, 0)


def test_the_platform_examples_load_from_the_shipped_fixtures() -> None:
    """The worker image ships `evals/fixtures`; the example set is the 60
    golden replies and the 4 injections, the conditional and non-answer
    replies among the security cases, and its case kinds are the eval's."""
    from dw_sales.adapters import skill_examples
    from dw_sales.evals.replies import _CASES

    examples = FixtureReplayExamples.load(REPO).examples()
    assert len([e for e in examples if e.gold is not None]) == 60
    assert len([e for e in examples if e.gold is None]) == 4
    assert all(e.never_accepts for e in examples if e.gold is None)
    assert any(e.never_accepts for e in examples if e.gold is not None)
    # One fact, two copies: the eval's case kinds and the replay's agree.
    assert {
        name: (kind.value, status, asked) for name, (kind, status, asked) in _CASES.items()
    } == dict(skill_examples._CASES)
