"""`sales.step_thresholds` and the gate columns (migration efc46a50e75e,
ticket 44) against a real database, as `dw_app` wherever isolation is the
question.

Each step's threshold is written by the lane with its audit rows in one
transaction, replaced on the next measure, read under tenant AND workspace
RLS only, never removed by the application, and held by its CHECKs to the
shape `StepThreshold` has. A labelled case keeps its confidence and gate,
read back per step and versions for the measure; a step row keeps its gate.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.domain.audit import lane_audit_event
from dw_sales.adapters.persistence.activity import SqlStepActivityReader
from dw_sales.adapters.persistence.labelled_cases import SqlLabelledCaseReader
from dw_sales.adapters.persistence.step_thresholds import SqlStepThresholds
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.autonomy import AUTO_APPLY_LANE
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.autonomy import LabelledScore, StepThreshold, Tier
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
_PROMPT = "sales.description_attributes@1.0.0"
_STEP = ModelStep.DESCRIPTION_ATTRIBUTES


def _threshold(score: float | None = 0.93, **changes: Any) -> StepThreshold:
    values: dict[str, Any] = {
        "step": _STEP,
        "prompt": _PROMPT,
        "model_profile": "onprem",
        "tier": Tier.APPLIES_ITSELF,
        "target": 0.05,
        "needed": 59,
        "cases": 90,
        "threshold": score,
        "accepted": 0 if score is None else 70,
        "errors": 0,
        "audits": 4,
        "audit_errors": 1,
        "stopped": False,
        "computed_at": _AT,
    }
    return StepThreshold.model_validate(values | changes)


def _audit(scope: SalesScope) -> Any:
    return lane_audit_event(
        lane=AUTO_APPLY_LANE,
        event_id=uuid.uuid4(),
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        action="sales.autonomy.threshold_set",
        resource_type="sales_step_threshold",
        resource_id=f"{_STEP.value}:{_PROMPT}",
        occurred_at=_AT,
        details={"step": _STEP.value},
    )


def _store(app_sessions: async_sessionmaker[AsyncSession]) -> SqlStepThresholds:
    return SqlStepThresholds(app_sessions, SqlAuditRepository)


async def test_the_step_check_holds_exactly_the_domains_steps(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
                " WHERE c.conname = 'ck_step_thresholds_step'"
            )
        )
    assert set(re.findall(r"'([a-z_]+)'::text", str(definition))) == {s.value for s in ModelStep}


async def test_a_threshold_is_stored_with_its_audit_replaced_and_read_back(
    app_sessions: async_sessionmaker[AsyncSession], migrator: AsyncEngine, world: World
) -> None:
    store = _store(app_sessions)
    assert await store.threshold(world.alpha, _STEP, _PROMPT, "onprem") is None
    first = _threshold(None, audits=0, audit_errors=0)
    await store.save(world.alpha, [first], [_audit(world.alpha)])
    assert await store.threshold(world.alpha, _STEP, _PROMPT, "onprem") == first

    later = _threshold(0.93, computed_at=_AT + timedelta(hours=1))
    await store.save(world.alpha, [later], [])

    assert await store.threshold(world.alpha, _STEP, _PROMPT, "onprem") == later
    assert await store.thresholds(world.alpha) == [later]
    # Another prompt version is its own row, starting from none.
    assert (
        await store.threshold(world.alpha, _STEP, "sales.description_attributes@1.1.0", "onprem")
        is None
    )
    async with migrator.connect() as conn:
        rows = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events WHERE tenant_id = :t"
                " AND action = 'sales.autonomy.threshold_set'"
            ),
            {"t": world.alpha.tenant_id.value},
        )
    assert rows == 1


async def test_another_tenant_or_workspace_reads_none_and_an_unscoped_connection_nothing(
    app_sessions: async_sessionmaker[AsyncSession], sales_app_engine: AsyncEngine, world: World
) -> None:
    store = _store(app_sessions)
    await store.save(world.alpha, [_threshold()], [])

    for scope in (world.beta, world.alpha_other):
        assert await store.thresholds(scope) == []
        assert await store.threshold(scope, _STEP, _PROMPT, "onprem") is None
    async with sales_app_engine.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM sales.step_thresholds")) == 0


async def _bound(session: AsyncSession, scope: SalesScope) -> None:
    for key, value in (
        ("app.tenant_id", scope.tenant_id.value),
        ("app.workspace_id", scope.workspace_id.value),
    ):
        await session.execute(
            sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
        )


_INSERT = (
    "INSERT INTO sales.step_thresholds (tenant_id, workspace_id, step, prompt, model_profile,"
    " tier, target, needed, cases, threshold, accepted, errors, audits, audit_errors, stopped,"
    " computed_at) VALUES (:t, :w, 'description_attributes', 'sales.x@1.0.0', 'onprem',"
    " :tier, 0.05, 59, 90, :threshold, :accepted, 0, 0, 0, false, now())"
)


async def test_a_row_written_for_another_tenant_is_refused_by_the_policy(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    async with app_sessions() as session, session.begin():
        await _bound(session, world.alpha)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                sa.text(_INSERT),
                {
                    "t": world.beta.tenant_id.value,
                    "w": world.beta.workspace_id.value,
                    "tier": "applies_itself",
                    "threshold": 0.9,
                    "accepted": 70,
                },
            )


async def test_the_application_never_removes_a_threshold(
    app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    await _store(app_sessions).save(world.alpha, [_threshold()], [])
    async with app_sessions() as session, session.begin():
        await _bound(session, world.alpha)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text("DELETE FROM sales.step_thresholds"))


@pytest.mark.parametrize(
    ("tier", "threshold", "accepted", "admitted"),
    [
        ("applies_itself", 0.9, 70, True),
        ("hand_off", None, 0, True),
        # A step a person approves has no threshold.
        ("person_approves", 0.9, 70, False),
        # A threshold accepts cases, and only a threshold does.
        ("applies_itself", None, 70, False),
        ("applies_itself", 0.9, 0, False),
        ("applies_itself", 1.5, 70, False),
    ],
)
async def test_the_checks_hold_a_row_to_the_domains_shape(
    migrator: AsyncEngine,
    world: World,
    tier: str,
    threshold: float | None,
    accepted: int,
    admitted: bool,
) -> None:
    values = {
        "t": world.alpha.tenant_id.value,
        "w": world.alpha.workspace_id.value,
        "tier": tier,
        "threshold": threshold,
        "accepted": accepted,
    }
    async with migrator.connect() as conn:
        transaction = await conn.begin()
        try:
            if admitted:
                await conn.execute(sa.text(_INSERT), values)
            else:
                with pytest.raises(IntegrityError):
                    await conn.execute(sa.text(_INSERT), values)
        finally:
            await transaction.rollback()


# ------------------------------------------------------ the gate columns --


def _label(**changes: Any) -> LabelledCase:
    values: dict[str, Any] = {
        "label_id": uuid.uuid4(),
        "decided_at": _AT,
        "step": _STEP,
        "lane": CaseKind.ORDER,
        "case_id": uuid.uuid4(),
        "customer_code": "KMH",
        "message_id": "M05",
        "attachment_id": "M05-A1",
        "line_no": 2,
        "field": "prv_code",
        "proposed": ["CB-2005"],
        "kept": ["CB-2005"],
        "prompt": _PROMPT,
        "model_profile": "onprem",
        "rules": "sales_order_rules@1.5.2",
        "decided_by": uuid.UUID(int=0xA1),
        "confidence": 0.97,
        "gate": "audit",
    }
    return LabelledCase.model_validate(values | changes)


async def test_a_labelled_cases_confidence_and_gate_are_kept_and_read_for_the_measure(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    gated = _label()
    undone = _label(kept=None, gate="applied", confidence=0.99)
    before = _label(confidence=None, gate=None)
    async with uow(world.alpha) as work:
        await work.labelled_cases.append([gated, undone, before])
        await work.commit()
    reader = SqlLabelledCaseReader(app_sessions)

    assert {
        c.label_id: (c.confidence, c.gate) for c in await reader.latest(world.alpha, _STEP)
    } == {
        gated.label_id: (0.97, "audit"),
        undone.label_id: (0.99, "applied"),
        before.label_id: (None, None),
    }
    found = await reader.gated(world.alpha)
    assert sorted(found[(_STEP, _PROMPT, "onprem")], key=lambda s: s.gate) == [
        LabelledScore(confidence=0.99, verdict="rejected", gate="applied"),
        LabelledScore(confidence=0.97, verdict="confirmed", gate="audit"),
    ]
    for scope in (world.beta, world.alpha_other):
        assert await reader.gated(scope) == {}


async def test_a_gate_past_the_person_needs_a_confidence(
    migrator: AsyncEngine, world: World
) -> None:
    insert = (
        "INSERT INTO sales.labelled_cases (id, tenant_id, workspace_id, decided_at, step, lane,"
        " message_id, field, proposed, kept, verdict, prompt, decided_by, confidence, gate)"
        " VALUES (:id, :t, :w, now(), 'description_attributes', 'order', 'M05', 'prv_code',"
        " '[\"CB-2005\"]', '[\"CB-2005\"]', 'confirmed', :p, :by, :c, :g)"
    )
    for confidence, gate, admitted in (
        (None, "person", True),
        (0.9, "applied", True),
        (None, "applied", False),
        (None, "audit", False),
        (0.9, "maybe", False),
        (1.2, "person", False),
    ):
        async with migrator.connect() as conn:
            transaction = await conn.begin()
            values = {
                "id": uuid.uuid4(),
                "t": world.alpha.tenant_id.value,
                "w": world.alpha.workspace_id.value,
                "p": _PROMPT,
                "by": uuid.UUID(int=0xA1),
                "c": confidence,
                "g": gate,
            }
            try:
                if admitted:
                    await conn.execute(sa.text(insert), values)
                else:
                    with pytest.raises(IntegrityError):
                        await conn.execute(sa.text(insert), values)
            finally:
                await transaction.rollback()


async def test_a_step_rows_gate_is_kept(
    uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession], world: World
) -> None:
    row = StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=_AT,
        message_id="M05",
        lane=CaseKind.ORDER,
        case_id=uuid.uuid4(),
        line_no=2,
        step=_STEP,
        result="accepted",
        automatic=True,
        reason_code=None,
        refusals={},
        prompt=_PROMPT,
        model_profile="onprem",
        model=None,
        calls=0,
        duration_ms=None,
        gate="applied",
    )
    async with uow(world.alpha) as work:
        await work.step_activity.append([row])
        await work.commit()
    read = await SqlStepActivityReader(app_sessions).between(
        world.alpha, _AT - timedelta(minutes=1), _AT + timedelta(minutes=1), None
    )
    assert [r.gate for r in read if r.outcome_id == row.outcome_id] == ["applied"]
