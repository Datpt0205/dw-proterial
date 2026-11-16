"""DW1's skills (ticket 40, dw_sales ADR 0014): the platform's files, a
tenant's version proposed and decided by another person, resolved for the
run's tenant only."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.domain.audit import lane_audit_event
from dw_sales.adapters.memory_rules import MemoryRuleVersions
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.access import SalesScopes
from dw_sales.application.skills import (
    NOT_REPLAYED,
    SkillDocument,
    SkillProposal,
    SkillReplay,
    skill_book,
    skill_key,
    skill_name,
)
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, GIANG, READER
from dw_sales.evals.thread_agent import run_for
from dw_sales.evals.world import ALPHA, BETA, Caller, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SKILLS = REPO / "configs" / "skills" / "dw1"
NAME = "thread-intents"
# A PIC given the set `sales_rules_editor`, as the rules' own tests do.
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
# A second head, who may decide what Giang proposes.
HUONG = Caller(uuid.UUID(int=0x62), "Trần Thu Hương", "huong.tran@alpha.local", GIANG.scopes)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, HUONG))


def _proposal(version: str, rule: str = "A reply saying 'Noted.' accepts.") -> SkillProposal:
    platform = load_dw1_skills(SKILLS).skills[skill_key(NAME)]
    return SkillProposal(
        version=version,
        description=platform.description,
        instructions=f"{platform.instructions}\n\n{rule}",
    )


def _run(scope: object = ALPHA) -> RunContext:
    return run_for(scope)  # type: ignore[arg-type]


# ------------------------------------------------------- the platform --


def test_the_platform_skills_are_named_by_their_folder_and_versioned() -> None:
    skills = load_dw1_skills(SKILLS)
    assert skills.agent_ref == "dw1@1.1.0" and skills.agent.strip()
    assert {s.ref for s in skills.skills.values()} == {
        "sales_skill_thread_intents@1.0.0",
        "sales_skill_mail_kinds@1.0.0",
        "sales_skill_document_forms@1.0.0",
        "sales_skill_handoffs@1.0.0",
        "sales_skill_reply_drafts@1.0.0",
    }
    assert all(skill_key(s.name) == key for key, s in skills.skills.items())
    assert skill_name(skill_key(NAME)) == NAME


def test_the_platform_skills_carry_no_customer_data() -> None:
    """The repository is public: no customer, item or convert code of the
    sample set appears in DW1's conduct or any skill."""
    text = "".join(p.read_text(encoding="utf-8") for p in sorted(SKILLS.rglob("*.md")))
    customers = read_records(DATA_DIR / "customers.json", Customer)
    items = read_records(DATA_DIR / "items.json", Item)
    convert = read_records(DATA_DIR / "convert_list.json", ConvertEntry)
    leaked = {c.name for c in customers if c.name in text}
    leaked |= {c.code for c in customers if f" {c.code} " in text}
    leaked |= {i.prv_code for i in items if i.prv_code in text}
    leaked |= {e.customer_item_code for e in convert if e.customer_item_code in text}
    assert leaked == set()


def test_the_skill_definitions_are_the_one_call_readings_word_for_word() -> None:
    """The two readings are measured on one task: every intent definition of
    `reply_intent@2.0.0` is in the skill as written."""
    import yaml

    prompt = yaml.safe_load(
        (REPO / "configs" / "prompts" / "sales" / "reply_intent@2.0.0.yaml").read_text("utf-8")
    )["system"]
    start = prompt.index('- "sends_po"')
    end = prompt.index("\nRules:")
    definitions = " ".join(prompt[start:end].split())
    skill = " ".join(load_dw1_skills(SKILLS).skills[skill_key(NAME)].instructions.split())
    assert definitions in skill


# ---------------------------------------------------------- resolution --


async def test_a_tenants_approved_skill_is_its_own_and_never_another_tenants() -> None:
    """Resolution through `TenantOverlay`: the tenant's approved version, else
    the platform's, never sideways."""
    platform = load_dw1_skills(SKILLS)
    own = platform.skills[skill_key(NAME)].model_copy(
        update={"policy_version": "1.1.0", "instructions": "ALPHA's own words."}
    )
    versions = MemoryRuleVersions()
    versions.seed_approved(ALPHA.tenant_id.value, own)
    book = skill_book(platform, versions)
    alpha = (await book.skill_set(_run(ALPHA))).named(NAME)
    beta = (await book.skill_set(_run(BETA))).named(NAME)
    assert alpha is not None and (alpha.ref, alpha.body) == (own.ref, "ALPHA's own words.")
    assert beta is not None and beta.ref == "sales_skill_thread_intents@1.0.0"
    assert beta.body != "ALPHA's own words."
    # The set is the run's: its tenant and workspace, never a request's.
    served = await book.skill_set(_run(BETA))
    assert (served.tenant_id, served.workspace_id) == (
        BETA.tenant_id.value,
        BETA.workspace_id.value,
    )


async def test_a_version_waiting_on_the_head_is_not_served() -> None:
    world = _world()
    await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.1.0"))
    listed = await world.services.skills.list(GIANG.context())
    assert {s.layer for s in listed.skills} == {"platform"}
    assert [(v.ref, v.status) for v in listed.versions] == [
        ("sales_skill_thread_intents@1.1.0", "proposed")
    ]


# ------------------------------------------------------ the decision --


async def test_the_proposer_cannot_approve_their_own_skill() -> None:
    """Acceptance 3: the head's own proposal waits on an approval like
    anyone's, and the head who proposed it cannot decide it."""
    world = _world()
    proposed = await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.1.0"))
    assert (proposed.status, proposed.decided_by) == ("proposed", None)
    assert proposed.approval_id is not None
    with pytest.raises(ConflictError) as refused:
        await world.decide_skill(GIANG, proposed.version_id, approve=True, comment="Tự duyệt")
    assert refused.value.details["rule"] == "maker_checker"
    listed = await world.services.skills.list(GIANG.context())
    assert {s.layer for s in listed.skills} == {"platform"}


async def _replayed(world: World, version_id: uuid.UUID) -> SkillReplay:
    """The worker's replay of ``version_id``, stored as its lane stores one."""
    replay = SkillReplay(
        version_id=version_id,
        replayed_at=datetime(2026, 11, 16, 9, 0, tzinfo=UTC),
        source="platform_examples",
        outcome="replayed",
        messages=60,
        right_with=50,
        right_without=48,
        unanswered=0,
        security_failed=("RP31",),
    )
    audit = lane_audit_event(
        lane="sales_skill_replay",
        event_id=uuid.uuid4(),
        tenant_id=ALPHA.tenant_id,
        workspace_id=ALPHA.workspace_id,
        action="sales.skills.replayed",
        resource_type="sales_skill_version",
        resource_id=str(version_id),
        occurred_at=replay.replayed_at,
    )
    assert await world.store.skill_replays.store(ALPHA, replay, audit)
    return replay


async def test_the_head_approves_only_a_replayed_version_and_sees_its_replay() -> None:
    """ADR 0014 decision 2: the head sees the replay before deciding. Until
    the worker has stored it, an approval is refused at the decision (not
    only hidden on the page); a rejection is not."""
    world = _world()
    proposed = await world.services.skills.propose(AN.context(), NAME, _proposal("1.1.0"))
    with pytest.raises(ConflictError) as refused:
        await world.decide_skill(HUONG, proposed.version_id, approve=True, comment="Đồng ý")
    assert refused.value.details["rule"] == NOT_REPLAYED
    (waiting,) = (await world.services.skills.list(GIANG.context())).versions
    assert (waiting.status, waiting.replay) == ("proposed", None)
    replay = await _replayed(world, proposed.version_id)
    (waiting,) = (await world.services.skills.list(GIANG.context())).versions
    assert waiting.replay == replay
    # Another tenant sees nothing of it.
    assert await world.store.skill_replays.stored(BETA, [proposed.version_id]) == {}


async def test_a_version_not_replayed_can_still_be_rejected() -> None:
    world = _world()
    proposed = await world.services.skills.propose(AN.context(), NAME, _proposal("1.1.0"))
    await world.decide_skill(HUONG, proposed.version_id, approve=False, comment="Không")
    (version,) = (await world.services.skills.list(GIANG.context())).versions
    assert version.status == "rejected"


async def test_another_head_approves_and_the_tenants_reading_uses_it() -> None:
    world = _world()
    proposed = await world.services.skills.propose(AN.context(), NAME, _proposal("1.1.0"))
    await _replayed(world, proposed.version_id)
    await world.decide_skill(HUONG, proposed.version_id, approve=True, comment="Đồng ý")
    listed = await world.services.skills.list(GIANG.context())
    assert [(s.ref, s.layer) for s in listed.skills if s.layer == "tenant"] == [
        ("sales_skill_thread_intents@1.1.0", "tenant"),
    ]
    assert {s.layer for s in listed.skills if s.name != NAME} == {"platform"}
    assert listed.skills[-1].instructions.endswith("A reply saying 'Noted.' accepts.")
    assert {v.status for v in listed.versions} == {"approved"}


async def test_a_pic_without_the_editor_set_or_a_reader_proposes_nothing() -> None:
    world = _world()
    for caller in (_AN, READER):
        with pytest.raises(PermissionDeniedError):
            await world.services.skills.propose(caller.context(), NAME, _proposal("1.1.0"))
        with pytest.raises(PermissionDeniedError):
            await world.services.skills.list(caller.context())


async def test_a_skill_the_platform_does_not_ship_or_its_own_number_is_refused() -> None:
    world = _world()
    with pytest.raises(NotFoundError):
        await world.services.skills.propose(GIANG.context(), "send-mail", _proposal("1.1.0"))
    with pytest.raises(ConflictError):
        await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.0.0"))


async def test_one_proposal_waits_per_skill() -> None:
    world = _world()
    await world.services.skills.propose(GIANG.context(), NAME, _proposal("1.1.0"))
    with pytest.raises(ConflictError) as refused:
        await world.services.skills.propose(AN.context(), NAME, _proposal("1.2.0"))
    assert refused.value.details["rule"] == "one_open_proposal"


def test_a_skill_is_words_held_to_their_length() -> None:
    with pytest.raises(ValueError):
        SkillProposal(version="1.1.0", description="x" * 1025, instructions="y")
    with pytest.raises(ValueError):
        SkillProposal(version="1.1.0", description="x", instructions="y" * 12_001)
    with pytest.raises(ValueError):
        SkillDocument(
            policy_id="sales_order_rules",
            policy_version="1.1.0",
            description="x",
            instructions="y",
        )


def test_a_proposal_names_no_tool_scope_or_recipient() -> None:
    """A version is a description and instructions, nothing else."""
    with pytest.raises(ValueError):
        SkillProposal.model_validate(
            {"version": "1.1.0", "description": "x", "instructions": "y", "tools": ["send"]}
        )
