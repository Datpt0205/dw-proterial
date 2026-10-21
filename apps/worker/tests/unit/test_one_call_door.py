"""The worker's one-call door: a model call made with no run around it (a
template drafted from an outbox event) is checked against the same plan rule,
on the same gateway and ledger, as the runner's runs (failure-modes #5)."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.model.single_call import SingleCallModelGateway
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_observability.telemetry import NullTelemetry
from dw_worker.composition import build_workflow_runtime
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit


def test_the_one_call_door_checks_the_runners_plan_on_the_runners_gateway() -> None:
    runtime = build_workflow_runtime(
        WorkerSettings(),
        # Never connected to: building the runtime opens no session.
        cast(async_sessionmaker[AsyncSession], object()),
        clock=SystemClock(),
        ids=Uuid4Generator(),
        telemetry=NullTelemetry(),
    )
    door = runtime.one_call
    assert isinstance(door, SingleCallModelGateway)
    assert door.inner is runtime.gateway
    assert door.ledger is runtime.runner.budget
    assert door.allowance.allowance is runtime.runner.allowance
    assert door.allowance.runs is runtime.runner.run_store
    assert door.allowance.spend is runtime.runner.spend_store
