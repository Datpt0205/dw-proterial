"""Shadow mode shared by every model step (ticket 67, dw_sales ADR 0015
decision 4): a step the tenant lists in shadow reads while it is not on and
passing, keeps what it read, applies and shows nothing; the decision a person
then takes labels it. The first step is `description_attributes`.

`OrderIntake` over the mock mailbox with the scripted model of
`test_model_reading.py`, and the in-memory store of the eval world. The
table, its RLS and grants are `tests/integration/test_sales_shadow_readings.py`'s.
"""

from __future__ import annotations

import dataclasses
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import PlatformOrderRules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES, DescriptionReader
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.routed_mail import HandledRequest
from dw_sales.application.shadow import (
    SHADOW_KEPT_FOR,
    SHADOW_RETENTION_LANE,
    ShadowBudget,
    ShadowReadings,
    ShadowRetention,
    label_reply_move,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import SHADOW_STEPS, ModelStep, OrderRules
from dw_sales.domain.orders import MappingStatus, OrderCase
from dw_sales.domain.reply_intent import ProposedStep
from dw_sales.domain.shadow import NO_STEP, REPLY_MOVES, ShadowReading, item_key
from dw_sales.evals.descriptions import Replayed
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.replies import correction_case
from dw_sales.evals.world import (
    ALPHA,
    BETA,
    NOW,
    MemoryStore,
    SampleSet,
    World,
    measured_gate,
    open_world,
)
from dw_sales.testing.followups import platform_zone

from .test_model_reading import ANSWERS, CATALOG, INBOX, PLATFORM, REPO, RUN, SCOPE, _NoCases

pytestmark = pytest.mark.unit

STEP = ModelStep.DESCRIPTION_ATTRIBUTES
AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def _shadowed(rules: OrderRules, on: bool = True, per_hour: int = 120) -> OrderRules:
    return rules.model_copy(
        update={
            "model_assist": rules.model_assist.model_copy(
                update={"shadow": on, "shadow_calls_per_hour": per_hour}
            )
        }
    )


def _intake(model: Any, rules: OrderRules, store: MemoryStore) -> OrderIntake:
    ids = itertools.count(1)
    gate, _ = measured_gate(REPO, SCOPE)
    return OrderIntake(
        catalog=CATALOG,
        inbox=INBOX,
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        zones=platform_zone(),
        rules=PlatformOrderRules(rules),
        cases=_NoCases(),
        new_case_id=lambda: uuid.UUID(int=next(ids)),
        descriptions=DescriptionReader(model),
        model_steps=gate,
        shadow=ShadowReadings(gate=gate, uow=store, clock=FixedClock(AT)),
    )


async def _case(intake: OrderIntake, message_id: str = "M36") -> OrderCase:
    message = await INBOX.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message, run=RUN)
    assert outcome.case is not None
    return outcome.case


def _held(store: MemoryStore, scope: SalesScope = SCOPE) -> dict[tuple[str, str], ShadowReading]:
    return store.state(scope).shadow_readings


# ------------------------------------------------------------- the reading --


async def test_a_step_off_and_listed_in_shadow_reads_keeps_and_changes_nothing() -> None:
    """Acceptance 1: the case is exactly the case with the step off."""
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    shadowed = await _case(_intake(model, _shadowed(PLATFORM), store))
    off = await _case(_intake(Replayed(answers=ANSWERS), PLATFORM, MemoryStore()))

    assert len(model.calls) == 1
    assert [line.mapping for line in shadowed.lines] == [line.mapping for line in off.lines]
    assert all(line.basis.description_reading is None for line in shadowed.lines)
    assert {f.key for f in shadowed.findings} == {f.key for f in off.findings}
    held = _held(store)
    by_line = {r.line_no: r for r in held.values()}
    # Lines 1 and 3 read to one candidate each; line 2 the model did not
    # understand, so it proposes nothing, as with the step on.
    assert {n: r.proposed for n, r in by_line.items()} == {1: ["HW-1002"], 3: ["CB-2001"]}
    one = by_line[1]
    assert one.item_key == item_key("M36", one.attachment_id, 1, STEP)
    assert (one.prompt, one.model_profile, one.rules, one.read_at) == (
        str(DESCRIPTION_ATTRIBUTES),
        "onprem",
        PLATFORM.version,
        AT,
    )


async def test_a_tenant_that_turns_shadow_off_reads_nothing() -> None:
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    await _case(_intake(model, _shadowed(PLATFORM, on=False), store))
    assert model.calls == []
    assert _held(store) == {}


async def test_past_the_hours_calls_a_step_reads_as_when_it_is_off() -> None:
    """The cap: shadow never takes the model from work that is on."""
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    await _case(_intake(model, _shadowed(PLATFORM, per_hour=0), store))
    assert model.calls == []
    assert _held(store) == {}


class _NoModel:
    async def configured(self, scope: SalesScope, step: ModelStep) -> bool:
        return False


async def test_no_model_configured_reads_nothing_in_shadow() -> None:
    """Fail closed: a step in shadow with no model configured for it reads
    nothing, as off."""
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    intake = _intake(model, _shadowed(PLATFORM), store)
    intake = dataclasses.replace(
        intake, shadow=ShadowReadings(gate=_NoModel(), uow=store, clock=FixedClock(AT))
    )
    await _case(intake)
    assert model.calls == []
    assert _held(store) == {}


async def test_a_step_on_and_passing_runs_as_itself_and_keeps_nothing_in_shadow() -> None:
    """Acceptance 2."""
    from dw_sales.adapters.order_rules import load_tenant_order_rules

    demo = load_tenant_order_rules(DATA_DIR / "policies")
    assert demo is not None and demo.model_assist.description_attributes
    store = MemoryStore()
    case = await _case(_intake(Replayed(answers=ANSWERS), _shadowed(demo), store))
    assert case.line(1).mapping.status is MappingStatus.CANDIDATE
    assert _held(store) == {}


# --------------------------------------------------------- the tenant list --


async def test_shadow_is_on_by_default_and_only_for_a_step_with_a_consumer() -> None:
    """Acceptance 4 as decided 2026-11-24: one switch, on unless a version
    turns it off, capped per hour; a step with no consumer never shadows."""
    assert (PLATFORM.model_assist.shadow, PLATFORM.model_assist.shadow_calls_per_hour) == (
        True,
        120,
    )
    gate, _ = measured_gate(REPO, SCOPE)
    readings = ShadowReadings(gate=gate, uow=MemoryStore(), clock=FixedClock(AT))
    assert ModelStep.REQUEST_HANDOFF not in SHADOW_STEPS
    assert not await readings.shadows(SCOPE, PLATFORM, ModelStep.REQUEST_HANDOFF)
    assert await readings.shadows(SCOPE, PLATFORM, STEP)


def test_the_hour_is_counted_per_tenant_and_starts_again() -> None:
    budget = ShadowBudget()
    one, two = uuid.UUID(int=1), uuid.UUID(int=2)
    assert budget.take(one, 2, AT) and budget.take(one, 2, AT + timedelta(minutes=59))
    assert not budget.take(one, 2, AT + timedelta(minutes=59))
    # Another tenant has its own hour; the next hour starts again.
    assert budget.take(two, 2, AT)
    assert budget.take(one, 2, AT + timedelta(hours=1))
    assert not budget.take(one, 0, AT + timedelta(hours=2))


def test_a_reading_names_its_own_item() -> None:
    values: dict[str, Any] = {
        "reading_id": uuid.uuid4(),
        "step": STEP,
        "item_key": item_key("M36", "M36-A1", 1, STEP),
        "message_id": "M36",
        "attachment_id": "M36-A1",
        "line_no": 1,
        "field": "prv_code",
        "proposed": ["HW-1002"],
        "prompt": "sales.description_attributes@1.2.0",
        "model_profile": "onprem",
        "rules": None,
        "confidence": None,
        "read_at": AT,
    }
    assert ShadowReading.model_validate(values)
    with pytest.raises(ValidationError, match="another item"):
        ShadowReading.model_validate({**values, "line_no": 2})
    with pytest.raises(ValidationError, match="has no shadow reading"):
        ShadowReading.model_validate(
            {
                **values,
                "step": ModelStep.REQUEST_HANDOFF,
                "item_key": item_key("M36", "M36-A1", 1, ModelStep.REQUEST_HANDOFF),
            }
        )


# ------------------------------------------------------- the person's label --


async def _world_with_shadow(code_kept: str, line_no: int = 1) -> tuple[Any, OrderCase]:
    """M36 processed in ALPHA by the world, then its line's reading kept in
    shadow, then Sales confirming ``code_kept`` on it."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _, case = (await world.process_each(AN, ["M36"]))["M36"]
    assert isinstance(case, OrderCase)
    reading = ShadowReading(
        reading_id=uuid.uuid4(),
        step=STEP,
        item_key=item_key(case.message_id, case.document.attachment_id, line_no, STEP),
        message_id=case.message_id,
        attachment_id=case.document.attachment_id,
        line_no=line_no,
        field="prv_code",
        proposed=["HW-1002"],
        prompt=str(DESCRIPTION_ATTRIBUTES),
        model_profile="onprem",
        rules=case.rules_version,
        confidence=0.93,
        read_at=AT,
    )
    async with world.store(ALPHA) as work:
        await work.shadow_readings.keep([reading])
        await work.commit()
    await world.services.order_commands.confirm_mapping(
        AN.context(),
        case.case_id,
        line_no,
        case_version=world.order(case.case_id).case_version,
        prv_code=code_kept,
    )
    return world, case


@pytest.mark.parametrize(("kept", "verdict"), [("HW-1002", "confirmed"), ("HW-1001", "corrected")])
async def test_sales_confirming_a_line_labels_its_shadow_reading_once(
    kept: str, verdict: str
) -> None:
    """Acceptance 3: one labelled case, gated shadow, and the reading gone."""
    world, case = await _world_with_shadow(kept)
    labels = [c for c in world.store.state(ALPHA).labelled_cases if c.step is STEP]
    (label,) = labels
    assert (label.verdict, label.proposed, label.kept, label.gate, label.confidence) == (
        verdict,
        ["HW-1002"],
        [kept],
        "shadow",
        0.93,
    )
    assert (label.case_id, label.line_no, label.decided_by) == (case.case_id, 1, AN.user_id)
    assert world.store.state(ALPHA).shadow_readings == {}


async def test_another_workspace_or_tenant_never_takes_the_reading() -> None:
    """Acceptance 5, in memory: the reading is the scope's own."""
    store = MemoryStore()
    reading = ShadowReading(
        reading_id=uuid.uuid4(),
        step=STEP,
        item_key=item_key("M36", None, 1, STEP),
        message_id="M36",
        attachment_id=None,
        line_no=1,
        field="prv_code",
        proposed=["HW-1002"],
        prompt=str(DESCRIPTION_ATTRIBUTES),
        model_profile="onprem",
        rules=None,
        confidence=None,
        read_at=AT,
    )
    async with store(ALPHA) as work:
        assert await work.shadow_readings.keep([reading, reading]) == 1
        await work.commit()
    async with store(BETA) as work:
        assert await work.shadow_readings.take(STEP, reading.item_key) is None
    async with store(ALPHA) as work:
        assert await work.shadow_readings.take(STEP, reading.item_key) == reading


# ---------------------------------------------------------------- the term --


async def test_readings_past_the_term_are_dropped_in_their_own_scope_and_audited() -> None:
    """Acceptance 6."""
    store = MemoryStore()

    def _read(at: datetime, line_no: int) -> ShadowReading:
        return ShadowReading(
            reading_id=uuid.uuid4(),
            step=STEP,
            item_key=item_key("M36", None, line_no, STEP),
            message_id="M36",
            attachment_id=None,
            line_no=line_no,
            field="prv_code",
            proposed=[],
            prompt=str(DESCRIPTION_ATTRIBUTES),
            model_profile="onprem",
            rules=None,
            confidence=None,
            read_at=at,
        )

    for scope in (ALPHA, BETA):
        async with store(scope) as work:
            await work.shadow_readings.keep(
                [_read(NOW - SHADOW_KEPT_FOR - timedelta(hours=1), 1), _read(NOW, 2)]
            )
            await work.commit()
    lane = ShadowRetention(uow=store, clock=FixedClock(NOW), ids=Uuid4Generator())
    assert await lane.tick(ALPHA) == 1
    assert [r.line_no for r in store.state(ALPHA).shadow_readings.values()] == [2]
    assert len(store.state(BETA).shadow_readings) == 2
    (event,) = [e for e in store.state(ALPHA).audit if e.action == "sales.shadow_readings.pruned"]
    assert event.details == {
        "readings": 1,
        "kept_days": SHADOW_KEPT_FOR.days,
        "actor": f"system:{SHADOW_RETENTION_LANE}",
    }
    assert event.actor_id == system_actor(SHADOW_RETENTION_LANE)


# ------------------------------------------- a reply, labelled by the move --


def test_every_move_a_reply_proposes_is_one_case_move() -> None:
    """`REPLY_MOVES` holds each `ProposedStep` that moves a case once;
    `await_revised_po` moves nothing and labels nothing."""
    moves = list(REPLY_MOVES.values())
    assert len(moves) == len(set(moves))
    assert set(moves) == set(get_args(ProposedStep)) - {"await_revised_po"}


async def _replied(intent: str, *, reply_on: bool = False) -> tuple[World, uuid.UUID]:
    """M04 sent back to the customer, then M42 (the customer's reply) read
    by the one call answering ``intent``, the reply readers off and shadow
    on (or the one call on, with ``reply_on``)."""
    keeps = Recorded(
        raw={"intents": [{"quote_spans": ["Please keep the PO as it is."], "intent": intent}]}
    )
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=keeps, shadow=True)
    current = world.policies.order_rules
    rules = current.model_copy(
        update={
            "policy_version": "1.92.0",
            "model_assist": current.model_assist.model_copy(
                update={
                    "skill_intents": False,
                    "thread_agent": False,
                    "reply_intent": reply_on,
                    "shadow": True,
                }
            ),
        }
    )
    world.store.rule_versions.seed_approved(ALPHA.tenant_id.value, rules)
    case_id = await correction_case(world)
    await world.process_each(AN, ["M42"])
    return world, case_id


def _reply_labels(world: World) -> list[Any]:
    return [c for c in world.store.state(ALPHA).labelled_cases if c.field == "next_step"]


@pytest.mark.parametrize(
    ("intent", "proposed", "verdict"),
    [("rejects", "resume_review", "confirmed"), ("asks", NO_STEP, "corrected")],
)
async def test_the_pics_move_after_a_reply_labels_what_the_reader_read_in_shadow(
    intent: str, proposed: str, verdict: str
) -> None:
    world, case_id = await _replied(intent)
    # Nothing of it shows on the case: the reply carries no reading.
    (reply,) = (await world.services.orders.get(AN.context(), case_id)).replies
    assert (reply.outcome, reply.proposal) == (None, None)
    (held,) = world.store.state(ALPHA).shadow_readings.values()
    assert (held.step, held.case_id, held.proposed) == (ModelStep.REPLY_INTENT, case_id, proposed)

    await world.services.order_commands.resume_review(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    (label,) = _reply_labels(world)
    assert (label.step, label.verdict, label.proposed, label.kept, label.gate) == (
        ModelStep.REPLY_INTENT,
        verdict,
        proposed,
        "resume_review",
        "shadow",
    )
    assert (label.case_id, label.message_id, label.decided_by) == (case_id, "M42", AN.user_id)
    assert world.store.state(ALPHA).shadow_readings == {}


async def test_a_reader_on_and_passing_reads_as_itself_and_keeps_nothing_in_shadow() -> None:
    world, case_id = await _replied("rejects", reply_on=True)
    (reply,) = (await world.services.orders.get(AN.context(), case_id)).replies
    assert reply.outcome == "read"
    assert world.store.state(ALPHA).shadow_readings == {}


async def test_a_lanes_move_or_a_move_no_reply_proposes_labels_nothing() -> None:
    world, case_id = await _replied("rejects")
    lane = AccessContext(
        tenant_id=ALPHA.tenant_id.value,
        workspace_id=ALPHA.workspace_id.value,
        principal_id=uuid.uuid4(),
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
    async with world.store(ALPHA) as work:
        for context, before, after in (
            (lane, "correction_requested", "in_review"),
            (AN.context(), "in_review", "prepared"),
        ):
            await label_reply_move(
                work,
                context,
                Uuid4Generator(),
                case_kind=CaseKind.ORDER,
                case_id=case_id,
                customer_code="KMH",
                from_status=before,
                to_status=after,
                at=AT,
            )
        await work.commit()
    assert _reply_labels(world) == []
    assert len(world.store.state(ALPHA).shadow_readings) == 1


# ---------------------------------------- a mail's kind, labelled on handled --


async def _unread_mail(kind: str, *, shadow: bool = True) -> World:
    """M11 (a customer asking to move a delivery) with every mail-reading
    step off and shadow on: it goes to a person, read in shadow as ``kind``."""
    scripted = Recorded(raw={"language": "en", "referenced_number_spans": [], "kind": kind})
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=scripted, shadow=True)
    current = world.policies.order_rules
    off = {"message_intent": False, "skill_mail_kinds": False, "triage_card": False}
    rules = current.model_copy(
        update={
            "policy_version": "1.93.0",
            "model_assist": current.model_assist.model_copy(update={**off, "shadow": shadow}),
        }
    )
    world.store.rule_versions.seed_approved(ALPHA.tenant_id.value, rules)
    seen = await world.process_each(AN, ["M11"])
    disposition, _ = seen["M11"]
    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "other")
    return world


def _kind_labels(world: World) -> list[Any]:
    return [c for c in world.store.state(ALPHA).labelled_cases if c.field == "kind"]


@pytest.mark.parametrize(
    ("picked", "verdict"), [("delivery_change", "confirmed"), ("complaint", "corrected")]
)
async def test_the_kind_picked_as_a_mail_is_marked_handled_labels_its_shadow_reading(
    picked: str, verdict: str
) -> None:
    world = await _unread_mail("delivery_change")
    (held,) = world.store.state(ALPHA).shadow_readings.values()
    assert (held.step, held.proposed) == (ModelStep.MESSAGE_INTENT, "delivery_change")

    await world.services.routed_mail.handle(GIANG.context(), "M11", None, picked)

    (label,) = _kind_labels(world)
    assert (label.step, label.verdict, label.proposed, label.kept, label.gate) == (
        ModelStep.MESSAGE_INTENT,
        verdict,
        "delivery_change",
        picked,
        "shadow",
    )
    assert world.store.state(ALPHA).shadow_readings == {}


async def test_marked_handled_with_no_kind_labels_nothing_and_keeps_the_reading() -> None:
    world = await _unread_mail("delivery_change")
    await world.services.routed_mail.handle(GIANG.context(), "M11", None)
    assert _kind_labels(world) == []
    assert len(world.store.state(ALPHA).shadow_readings) == 1


def test_a_kind_outside_the_platforms_is_refused_at_the_door() -> None:
    assert HandledRequest.model_validate({"kind": "complaint"}).kind == "complaint"
    with pytest.raises(ValidationError):
        HandledRequest.model_validate({"kind": "anything"})


async def test_with_shadow_off_a_mail_to_a_person_is_not_read() -> None:
    world = await _unread_mail("delivery_change", shadow=False)
    assert world.store.state(ALPHA).shadow_readings == {}
