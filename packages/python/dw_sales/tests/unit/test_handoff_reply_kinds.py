"""Hand-off and reply kinds become the tenant's skills; code keeps the moves
(ticket 42 family 5, dw_sales ADR 0014).

Which kinds of hand-off to PC or QA, and which kinds of mail to a customer, a
tenant writes are its ``handoffs`` and ``reply-drafts`` skills; what each
kind does is code's closed sets: the fields a hand-off asks for and the team
it goes to, the platform draft a mail is worded as (its gate, facts, check
and recipients). These tests hold: the platform's skills say today's kinds,
a version naming a recipient, a send, a price, an amount, a tool or anything
outside the closed sets is refused when proposed and unused when served, a
tenant's new kind is read with no code, a reading opens no door code would
not, off is exactly as before, and a proposal is replayed by its own step.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.model.skills import Skill
from dw_kernel.errors import DomainError, NotFoundError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.access import SalesScopes
from dw_sales.application.handoff_kinds import (
    HandoffKindExample,
    HandoffKindReplay,
)
from dw_sales.application.handoffs import (
    HANDOFF_KINDS_PROMPT,
    REQUEST_HANDOFF,
    Copied,
    render,
)
from dw_sales.application.handoffs import (
    PROMPT_TOKENS as HANDOFF_PROMPT_TOKENS,
)
from dw_sales.application.order_intake import HANDOFF_KINDS
from dw_sales.application.reply_drafts import (
    PROMPT_TOKENS as REPLY_PROMPT_TOKENS,
)
from dw_sales.application.reply_drafts import (
    REPLY_KINDS_PROMPT,
    ReplyKindExample,
    ReplyKindReplay,
)
from dw_sales.application.skill_replay import SkillReplayer
from dw_sales.application.skills import (
    STEP_SKILLS,
    WORDS_UNREADABLE,
    SkillProposal,
    skill_book,
    skill_key,
)
from dw_sales.domain.dispositions import RoutingReason
from dw_sales.domain.handoff_kinds import HANDOFFS, handoff_kinds_of
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.reply_kinds import REPLY_DRAFTS, REPLY_KINDS, reply_kinds_of
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, GIANG
from dw_sales.evals.handoff_kinds import _through_intake, book_with, read_kind
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.reply_drafts import PO, confirmed, draft, drafting_world, pull_in, sample_for
from dw_sales.evals.reply_kinds import CONTACTS, version_with
from dw_sales.evals.skill_intents import _Following
from dw_sales.evals.thread_agent import Harness, run_for
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SKILLS = REPO / "configs" / "skills" / "dw1"
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
HANDOFF_FIXTURE = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_handoff_kinds.json").read_text("utf-8")
)
REPLY_FIXTURE = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_reply_kinds.json").read_text("utf-8")
)
CERTIFICATE = HANDOFF_FIXTURE["new_kind"]["block"]
SHORT = REPLY_FIXTURE["new_kind"]["block"]
# A tenant's kind that sends a complaint's fields to PC, not QA.
REWORK = """- kind: rework_request
  asks: lot_and_problem
  to: pc
  label: Xin làm lại
  means: the customer asks to rework goods delivered."""
COMPLAINT_ANSWER = {
    "po_no_span": "VLX-PO-2608-0102",
    "lot_no_span": "LOT 2608-152",
    "problem_quote_spans": ["chứng chỉ CoC"],
}
CERT_MAIL = {**HANDOFF_FIXTURE["new_kind"]["mails"][0], "kind": "certificate_request"}


def _platform(name: str) -> str:
    return load_dw1_skills(SKILLS).skills[skill_key(name)].instructions


# ------------------------------------------------------- the platform --


def test_the_platform_hand_offs_are_ticket_33s_kinds_to_the_copys_teams() -> None:
    """One task, measured on the one call's: the platform's kinds are the
    routing reasons ticket 33 pre-fills, each with its own fields, to the
    team the platform's copy writes it to."""
    kinds = handoff_kinds_of(_platform(HANDOFFS))
    copy = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
    assert {k.name for k in kinds.kinds} == set(HANDOFF_KINDS.values())
    for kind in kinds.kinds:
        assert kind.shape == kind.name and kind.label is None
        assert kind.to == copy.handoff_copy.templates[kind.shape].to


def test_the_platform_reply_kinds_are_the_platform_drafts_each_as_itself() -> None:
    kinds = reply_kinds_of(_platform(REPLY_DRAFTS))
    assert [(k.name, k.drafts) for k in kinds.kinds] == [(k, k) for k in REPLY_KINDS]


def test_neither_skill_is_offered_to_the_thread_pick() -> None:
    assert {HANDOFFS, REPLY_DRAFTS} <= STEP_SKILLS


@pytest.mark.parametrize(
    "refused", HANDOFF_FIXTURE["refused_versions"], ids=lambda r: str(r["why"])
)
def test_a_hand_off_version_naming_what_code_holds_is_refused(refused: dict[str, str]) -> None:
    """A recipient, a send, a price, a tool, a field or a team outside the
    closed sets, or a route that takes no hand-off: never a kind."""
    with pytest.raises(ValueError):
        handoff_kinds_of(refused["block"])


@pytest.mark.parametrize("refused", REPLY_FIXTURE["refused_versions"], ids=lambda r: str(r["why"]))
def test_a_reply_version_naming_what_code_holds_is_refused(refused: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        reply_kinds_of(refused["block"])


def test_a_new_kind_needs_a_label_and_a_kind_is_named_once() -> None:
    with pytest.raises(ValueError):
        handoff_kinds_of("- kind: rework\n  asks: lot_and_problem\n  to: pc\n  means: x")
    with pytest.raises(ValueError):
        reply_kinds_of("- kind: short\n  drafts: confirmation_draft\n  means: x")
    with pytest.raises(ValueError):
        handoff_kinds_of(f"{REWORK}\n\n{REWORK}")


async def test_an_unreadable_version_is_refused_when_proposed_and_a_good_one_waits() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    skills = load_dw1_skills(SKILLS).skills
    for name, good, bad in (
        (HANDOFFS, CERTIFICATE, "- kind: x\n  asks: lot_and_problem\n  to: buyer@rival.example"),
        (REPLY_DRAFTS, SHORT, "- kind: x\n  drafts: confirmation_draft\n  price: 1 USD"),
    ):
        base = skills[skill_key(name)]
        proposal = SkillProposal(
            version="1.1.0",
            description=base.description,
            instructions=f"{base.instructions}\n\n{bad}",
        )
        with pytest.raises(DomainError) as refused:
            await world.services.skills.propose(AN.context(), name, proposal)
        assert refused.value.details["rule"] == WORDS_UNREADABLE
        fine = proposal.model_copy(update={"instructions": f"{base.instructions}\n\n{good}"})
        proposed = await world.services.skills.propose(AN.context(), name, fine)
        assert (proposed.ref, proposed.status) == (f"{skill_key(name)}@1.1.0", "proposed")


# ------------------------------------------------------- the hand-offs --


async def test_a_tenants_new_kind_is_pre_filled_through_intake_with_no_code() -> None:
    """Acceptance 2: the mail kinds read a mail as the tenant's kind, routed
    ``other``; its hand-off is the skill's kind, to its team, with every
    value located and resolved by code."""
    book = book_with((ALPHA, "1.1.0", CERTIFICATE))
    handoff = await _through_intake(
        Recorded(raw=COMPLAINT_ANSWER), CERT_MAIL, book, "certificate_request"
    )
    assert handoff is not None and handoff.outcome == "read"
    assert (handoff.skill, handoff.skill_kind, handoff.kind_label, handoff.to) == (
        "sales_skill_handoffs@1.1.0",
        "certificate_request",
        "Xin chứng chỉ chất lượng",
        "qa",
    )
    assert (handoff.kind, handoff.prompt) == ("complaint", str(HANDOFF_KINDS_PROMPT))
    assert handoff.po_no == "VLX-PO-2608-0102" and handoff.lot is not None
    # Another tenant has no such kind: no hand-off, as today.
    beta = await _through_intake(
        Recorded(raw=COMPLAINT_ANSWER), CERT_MAIL, book, "certificate_request", BETA
    )
    assert beta is None


async def test_the_team_is_the_skills_from_the_closed_set_never_the_copys() -> None:
    book = book_with((ALPHA, "1.1.0", REWORK))
    spec = {**CERT_MAIL, "kind": "rework_request"}
    handoff, customer = await read_kind(Recorded(raw=COMPLAINT_ANSWER), spec, book)
    assert handoff is not None and handoff.to == "pc"
    copy = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
    written = render(handoff, copy.handoff_copy, customer_code=customer.code, message_id="M")
    assert copy.handoff_copy.templates["complaint"].to == "qa" and written.to == "pc"


async def test_a_reading_opens_no_door_its_route_does_not() -> None:
    """The reading's kind is honoured only where its route is the reason the
    message was routed for: a mail the mail kinds sent ``other`` but routed
    as a complaint for another reason gets the complaint's hand-off."""
    book = book_with((ALPHA, "1.1.0", CERTIFICATE))
    handoff = await _through_intake(
        Recorded(raw=COMPLAINT_ANSWER),
        CERT_MAIL,
        book,
        "certificate_request",
        reason=RoutingReason.COMPLAINT,
    )
    assert handoff is not None and handoff.skill_kind == "complaint"
    # And a reason with no hand-off of its own gets none from such a reading.
    none = await _through_intake(
        Recorded(raw=COMPLAINT_ANSWER),
        CERT_MAIL,
        book,
        "certificate_request",
        reason=RoutingReason.PORTAL_NOTICE,
    )
    assert none is None


async def test_off_below_bar_down_or_unreadable_is_exactly_ticket_33() -> None:
    answering = Recorded(raw=COMPLAINT_ANSWER)
    book = book_with((ALPHA, "1.1.0", CERTIFICATE))
    spec = {**CERT_MAIL, "kind": "complaint"}
    today = await _through_intake(answering, spec, book, "complaint", skill=False)
    assert today is not None and today.prompt == str(REQUEST_HANDOFF) and today.skill is None
    unreadable = book_with((ALPHA, "1.2.0", "---\n- kind: complaint\n  asks: price\n"))
    for got in (
        await _through_intake(answering, spec, book, "complaint", measured=False),
        await _through_intake(
            answering,
            spec,
            book,
            "complaint",
            skill_model=Recorded(failure=ModelUnavailableError("x")),
        ),
        await _through_intake(answering, spec, unreadable, "complaint"),
    ):
        assert got is not None and got.model_dump() == today.model_dump()
    # A tenant's own kind, the step off: no hand-off at all, as today.
    assert (
        await _through_intake(answering, CERT_MAIL, book, "certificate_request", skill=False)
        is None
    )


async def test_the_hand_off_skill_prompt_is_the_one_its_step_names_and_fits_its_room() -> None:
    from dw_sales.application.model_readiness import BARS

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        HANDOFF_KINDS_PROMPT.prompt_id,
        HANDOFF_KINDS_PROMPT.version,
        {"skill": "", "kind": "", "fields": "", "subject": "", "body": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < HANDOFF_PROMPT_TOKENS
    assert BARS[ModelStep.SKILL_HANDOFFS].prompt == HANDOFF_KINDS_PROMPT
    # Every field set the prompt explains is one a skill may ask for.
    assert all(f"- {asks}:" in rendered.system for asks in ("order_lines", "lot_and_problem"))
    rendered = prompts.render(
        REPLY_KINDS_PROMPT.prompt_id,
        REPLY_KINDS_PROMPT.version,
        {"skill": "", "kind": "", "facts": "", "example": "", "question": ""},
        tenant_id=ALPHA.tenant_id.value,
    )
    assert estimated_tokens(rendered.system + rendered.user) < REPLY_PROMPT_TOKENS
    assert BARS[ModelStep.SKILL_REPLY_DRAFTS].prompt == REPLY_KINDS_PROMPT


# ------------------------------------------------------- the reply kinds --


class _Writing(Recorded):
    """A scripted draft: ``body`` under a subject naming the PO."""

    def __init__(self, body: str) -> None:
        super().__init__(raw={"subject": f"PO {PO}", "body": body})


async def _drafted(
    body: str, kind: str, *versions: Any, skill: bool = True, measured: bool = True
) -> tuple[Any, _Writing]:
    model = _Writing(body)
    with sample_for("en", pull_in()) as sample:
        world = drafting_world(REPO, sample, model, skill=skill, skill_measured=measured)
        for version in versions:
            world.store.rule_versions.seed_approved(ALPHA.tenant_id.value, version)
        case_id = await confirmed(world)
        return await draft(world, case_id, kind), model


async def test_a_tenants_new_reply_kind_is_worded_as_its_draft_to_the_contacts() -> None:
    version = version_with("1.1.0", SHORT)
    view, model = await _drafted("PO NRV-PO-26-0457 confirmed.", "short_confirmation", version)
    assert view.status == "drafted", view
    assert (view.kind, view.drafted_as, view.kind_label, view.skill) == (
        "short_confirmation",
        "confirmation_draft",
        "Xác nhận ngắn",
        "sales_skill_reply_drafts@1.1.0",
    )
    assert view.to == CONTACTS and view.prompt_ref == str(REPLY_KINDS_PROMPT)
    prompt, _, inputs = model.calls[-1]
    assert prompt == REPLY_KINDS_PROMPT and inputs["kind"] == "short_confirmation"
    assert "- kind: short_confirmation" in inputs["skill"]
    assert json.loads(inputs["facts"])["reply"] == "confirmation_draft"
    beside, _ = await _drafted("PO NRV-PO-26-0457 confirmed.", "confirmation_draft", version)
    assert [(o.kind, o.label) for o in beside.others] == [("short_confirmation", "Xác nhận ngắn")]


async def test_a_kind_no_served_version_names_is_not_offered() -> None:
    version = version_with("1.1.0", SHORT)
    with pytest.raises(NotFoundError):
        await _drafted("x", "short_confirmation", version, skill=False)
    with pytest.raises(NotFoundError):
        await _drafted("x", "short_confirmation", version, measured=False)
    with pytest.raises(NotFoundError):
        await _drafted("x", "long_confirmation", version)


async def test_the_check_and_the_gate_are_the_drafts_whatever_the_words() -> None:
    """A skill's kind is held to its draft's check (no amount, no address,
    every figure a fact) and to its draft's question rule."""
    version = version_with("1.1.0", SHORT)
    amount, _ = await _drafted("Line 2: 3600 m, 3600 USD.", "short_confirmation", version)
    address, _ = await _drafted("Copied buyer@rival.example.", "short_confirmation", version)
    figure, _ = await _drafted("Ships on 28/11/2026.", "short_confirmation", version)
    assert (amount.refusal, address.refusal, figure.refusal) == ("amount", "address", "figure")
    asking = version_with(
        "1.2.0",
        "- kind: quick_answer\n  drafts: question_answer\n  label: Trả lời nhanh\n"
        "  means: answer in one line.",
    )
    with pytest.raises(DomainError):
        await _drafted("x", "quick_answer", asking)


# ------------------------------------------------------- the replays --


@dataclass
class _Copying:
    """The hand-off reader's `located`, answering per kind's words."""

    copied: Copied | None
    asked: list[str] = field(default_factory=list)

    async def located(self, part: Any, served: Any, *, run: RunContext) -> Copied | None:
        self.asked.append(served.kind.name)
        return self.copied


def _skill(name: str, words: str = "") -> Skill:
    base = load_dw1_skills(SKILLS).skills[skill_key(name)]
    body = base.instructions.replace("\n\n## Rules", f"\n\n{words}\n\n## Rules", 1)
    return Skill(name=name, description=base.description, body=body, ref=f"{base.policy_id}@9.9.9")


def _mail() -> InboundMessage:
    return InboundMessage(
        message_id="HK-R",
        sender=EmailAddress(address="an.trinh@velatrix.example"),
        subject="CoC",
        received_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
        body_text="Bên em cần chứng chỉ CoC cho lô LOT 2608-152.",
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


async def test_a_hand_off_proposal_is_replayed_by_what_code_locates() -> None:
    example = HandoffKindExample(
        "HK-R", _mail(), "certificate_request", None, "LOT 2608-152", ("chứng chỉ coc",), 0
    )

    class _One:
        def examples(self) -> list[HandoffKindExample]:
            return [example]

    reader = _Copying(Copied(None, "LOT 2608-152", ("bên em cần chứng chỉ coc",), 0))
    replay = HandoffKindReplay(reader, _One())  # type: ignore[arg-type]
    forgotten: list[uuid.UUID] = []
    counts = await replay.counts(
        _skill(HANDOFFS, CERTIFICATE),
        _skill(HANDOFFS),
        new_run=lambda: run_for(ALPHA),
        forget_run=forgotten.append,
    )
    # Right with the proposal; the version in force names no such kind.
    assert counts == (1, 1, 0, 0, ())
    assert reader.asked == ["certificate_request"] and len(forgotten) == 1


async def test_a_reply_proposal_is_replayed_by_its_drafts_check() -> None:
    facts = json.dumps({"reply": "confirmation_draft", "po_no": PO})
    example = ReplyKindExample("RK-R", "confirmation_draft", facts, "", "", PO)

    class _One:
        def examples(self) -> list[ReplyKindExample]:
            return [example]

    keeping = ReplyKindReplay(Recorded(raw={"subject": PO, "body": f"PO {PO}."}), _One())
    counts = await keeping.counts(
        _skill(REPLY_DRAFTS, SHORT),
        _skill(REPLY_DRAFTS),
        new_run=lambda: run_for(ALPHA),
        forget_run=lambda _: None,
    )
    assert counts == (1, 1, 1, 0, ())
    priced = ReplyKindReplay(Recorded(raw={"subject": PO, "body": "0.65 USD"}), _One())
    assert (
        await priced.counts(
            _skill(REPLY_DRAFTS, SHORT),
            _skill(REPLY_DRAFTS),
            new_run=lambda: run_for(ALPHA),
            forget_run=lambda _: None,
        )
    )[1:3] == (0, 0)


async def test_a_step_skill_proposal_waits_unreplayed_where_its_replay_is_not_wired() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    base = load_dw1_skills(SKILLS).skills[skill_key(HANDOFFS)]
    await world.services.skills.propose(
        GIANG.context(),
        HANDOFFS,
        SkillProposal(
            version="1.1.0",
            description=base.description,
            instructions=f"{base.instructions}\n\n{CERTIFICATE}",
        ),
    )
    replayer = _replayer(world)
    assert await replayer.tick(ALPHA) == 0

    @dataclass
    class _Counting:
        asked: list[str] = field(default_factory=list)

        async def counts(self, proposed: Skill, in_force: Skill, **_: Any) -> Any:
            self.asked.append(proposed.ref)
            return 2, 2, 1, 0, ()

    wired = replace(replayer, handoffs=_Counting())
    assert await wired.tick(ALPHA) == 1
    (stored,) = (
        await world.store.skill_replays.stored(ALPHA, [v.version_id for v in await _waiting(world)])
    ).values()
    assert (stored.messages, stored.right_with, stored.right_without) == (2, 2, 1)


async def _waiting(world: World) -> list[Any]:
    from dw_sales.application.rules import rule_work
    from dw_sales.application.skill_replay import _lane_context

    async with rule_work(world.store)(_lane_context(ALPHA)) as work:
        return list(await work.rule_versions.list_all(keys=[skill_key(HANDOFFS)]))


def _replayer(world: World) -> SkillReplayer:
    versions = world.store.rule_versions
    harness = Harness.build(REPO, _Following(marker="x", quote="x"), skills=versions)
    return SkillReplayer(
        uow=world.store,
        replays=world.store.skill_replays,
        agent=harness.agent,
        book=skill_book(load_dw1_skills(SKILLS), versions),
        rules=world.policies,  # type: ignore[arg-type]
        examples=_NoExamples(),
        clock=FixedClock(datetime(2026, 11, 16, 9, 0, tzinfo=UTC)),
        ids=Uuid4Generator(),
        worker_id="sales-dw1",
        worker_version="1.0.0",
        forget_run=lambda _: None,
    )


class _NoExamples:
    def examples(self) -> list[Any]:
        return []


def test_a_disposition_holds_a_hand_off_only_of_its_reason_or_its_reading() -> None:
    from pydantic import ValidationError

    from dw_sales.domain.dispositions import DispositionKind, MessageDisposition
    from dw_sales.domain.handoffs import Handoff

    handoff = Handoff.model_validate(
        {
            "kind": "complaint",
            "prompt": str(HANDOFF_KINDS_PROMPT),
            "model_profile": "onprem",
            "route": "structured_extraction",
            "rules": "sales_order_rules@1.5.2",
            "outcome": "unavailable",
            "skill": "sales_skill_handoffs@1.1.0",
            "skill_kind": "certificate_request",
            "to": "qa",
        }
    )
    routed = {
        "message_id": "M-1",
        "kind": DispositionKind.ROUTED_TO_SALES,
        "reason": RoutingReason.OTHER,
        "owner": "vy@alpha.example",
        "handoff": handoff,
    }
    with pytest.raises(ValidationError):
        MessageDisposition.model_validate(routed)
    reading = {
        "prompt": "sales.mail_kinds@1.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.5.2",
        "outcome": "read",
        "kind": "certificate_request",
        "language": "vi",
        "skill": "sales_skill_mail_kinds@1.1.0",
        "routed_as": "other",
        "kind_label": "Xin chứng chỉ",
    }
    assert MessageDisposition.model_validate({**routed, "reading": reading}).handoff == handoff
