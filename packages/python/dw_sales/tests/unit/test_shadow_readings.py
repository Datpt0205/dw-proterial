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
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.audit import system_actor
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import PlatformOrderRules
from dw_sales.adapters.reader_client import ClientPoReaders, ClientQuoteForms
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES, DescriptionReader
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.shadow import (
    SHADOW_KEPT_FOR,
    SHADOW_RETENTION_LANE,
    ShadowReadings,
    ShadowRetention,
)
from dw_sales.domain.order_checks import SHADOW_STEPS, ModelAssist, ModelStep, OrderRules
from dw_sales.domain.orders import MappingStatus, OrderCase
from dw_sales.domain.shadow import ShadowReading, item_key
from dw_sales.evals.descriptions import Replayed
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, BETA, NOW, MemoryStore, SampleSet, measured_gate, open_world
from dw_sales.testing.followups import platform_zone

from .test_model_reading import ANSWERS, CATALOG, INBOX, PLATFORM, REPO, RUN, SCOPE, _NoCases

pytestmark = pytest.mark.unit

STEP = ModelStep.DESCRIPTION_ATTRIBUTES
AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def _shadowed(rules: OrderRules, *steps: ModelStep) -> OrderRules:
    return rules.model_copy(
        update={"model_assist": rules.model_assist.model_copy(update={"shadow": steps})}
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
    shadowed = await _case(_intake(model, _shadowed(PLATFORM, STEP), store))
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


async def test_a_step_not_listed_reads_nothing() -> None:
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    await _case(_intake(model, PLATFORM, store))
    assert model.calls == []
    assert _held(store) == {}


class _NoModel:
    async def configured(self, scope: SalesScope, step: ModelStep) -> bool:
        return False


async def test_no_model_configured_reads_nothing_in_shadow() -> None:
    """Fail closed: a step in shadow with no model configured for it reads
    nothing, as off."""
    store, model = MemoryStore(), Replayed(answers=ANSWERS)
    intake = _intake(model, _shadowed(PLATFORM, STEP), store)
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
    case = await _case(_intake(Replayed(answers=ANSWERS), _shadowed(demo, STEP), store))
    assert case.line(1).mapping.status is MappingStatus.CANDIDATE
    assert _held(store) == {}


# --------------------------------------------------------- the tenant list --


def test_only_a_step_with_a_shadow_consumer_may_be_listed_and_once() -> None:
    """Acceptance 4."""
    assist = PLATFORM.model_assist
    assert ModelAssist.model_validate({**assist.model_dump(), "shadow": ["description_attributes"]})
    assert ModelStep.REPLY_INTENT not in SHADOW_STEPS
    with pytest.raises(ValidationError, match="no shadow reading is built for reply_intent"):
        ModelAssist.model_validate({**assist.model_dump(), "shadow": ["reply_intent"]})
    with pytest.raises(ValidationError, match=r"once|at most"):
        ModelAssist.model_validate(
            {**assist.model_dump(), "shadow": ["description_attributes"] * 2}
        )
    assert PLATFORM.model_assist.shadow == ()


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
                "step": ModelStep.REPLY_INTENT,
                "item_key": item_key("M36", "M36-A1", 1, ModelStep.REPLY_INTENT),
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
