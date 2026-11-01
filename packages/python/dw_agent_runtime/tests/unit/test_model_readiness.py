"""The readiness check every context's model steps are held to (ADR
0013/0014): a registry of its own here, not Sales'."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import pytest

from dw_agent_runtime.model.interpretation import PromptRef
from dw_agent_runtime.model.readiness import (
    Attestation,
    MeasuredScope,
    ModelMeasurement,
    ReadinessCheck,
    StepBar,
    refusal,
)
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.domain.audit import AuditEvent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 1, 8, tzinfo=UTC)


class Step(StrEnum):
    READ = "pr_reading"


BARS: Mapping[Step, StepBar] = {
    Step.READ: StepBar(0.9, "all.right", PromptRef("ctx.pr_reading", "1.0.0"), "ctx_pr", "g")
}


@dataclass(frozen=True)
class Scope:
    tenant_id: TenantId
    workspace_id: WorkspaceId


A = Scope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
B = Scope(TenantId(uuid.UUID(int=3)), WorkspaceId(uuid.UUID(int=4)))


@dataclass
class Log:
    rows: list[tuple[uuid.UUID, ModelMeasurement]] = field(default_factory=list)
    events: list[AuditEvent] = field(default_factory=list)
    unreadable: bool = False

    async def latest(
        self, scope: MeasuredScope, step: str, *, model: str, prompt: str
    ) -> ModelMeasurement | None:
        if self.unreadable:
            raise ConnectionError("down")
        found = [
            m
            for t, m in self.rows
            if t == scope.tenant_id.value
            and m.step == step
            and (m.model, m.prompt) == (model, prompt)
        ]
        return max(found, key=lambda m: m.measured_at, default=None)

    async def record(
        self, scope: MeasuredScope, measurement: ModelMeasurement, event: AuditEvent
    ) -> None:
        self.rows.append((scope.tenant_id.value, measurement))
        self.events.append(event)


class _Model:
    def model_for(self, tenant_id: uuid.UUID) -> str:
        return "qwen3.5:9b"


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


def _attest(log: Log) -> Attestation:
    return Attestation(
        log,
        _Clock(),
        _Ids(),
        BARS,
        lane="ctx_model_attest",
        action="ctx.model_step.measured",
        resource_type="ctx_model_step_measurement",
    )


async def test_a_step_never_measured_is_not_ready_and_says_so() -> None:
    readiness = await ReadinessCheck(BARS, Log(), _Model()).check(A, Step.READ)
    assert (readiness.ready, readiness.reason) == (False, "not_measured")
    assert "chưa đo" in str(refusal([readiness]))


async def test_a_pass_at_the_bar_on_the_model_and_prompt_in_use_is_ready() -> None:
    log = Log()
    measured = await _attest(log).attest(
        A, Step.READ, model="qwen3.5:9b", value=0.93, held=True, dataset="ctx_pr@1.0.0"
    )
    assert measured.passed and measured.recorded_by == "system:ctx_model_attest"
    assert log.events[0].action == "ctx.model_step.measured"
    readiness = await ReadinessCheck(BARS, log, _Model()).check(A, Step.READ)
    assert readiness.ready and readiness.step is Step.READ


@pytest.mark.parametrize(
    ("value", "held", "model"),
    [(0.89, True, "qwen3.5:9b"), (0.95, False, "qwen3.5:9b"), (0.95, True, "other")],
    ids=["below-the-bar", "the-run-failed", "another-model"],
)
async def test_anything_short_of_a_pass_on_the_model_in_use_is_not_ready(
    value: float, held: bool, model: str
) -> None:
    log = Log()
    await _attest(log).attest(
        A, Step.READ, model=model, value=value, held=held, dataset="ctx_pr@1.0.0"
    )
    readiness = await ReadinessCheck(BARS, log, _Model()).check(A, Step.READ)
    assert not readiness.ready


async def test_another_tenants_pass_and_an_unreadable_store_are_not_ready() -> None:
    log = Log()
    await _attest(log).attest(
        B, Step.READ, model="qwen3.5:9b", value=0.99, held=True, dataset="ctx_pr@1.0.0"
    )
    assert not (await ReadinessCheck(BARS, log, _Model()).check(A, Step.READ)).ready
    log.unreadable = True
    readiness = await ReadinessCheck(BARS, log, _Model()).check(B, Step.READ)
    assert (readiness.ready, readiness.reason) == (False, "unreadable")


@pytest.mark.parametrize(
    "bar",
    [
        StepBar(0.95, "all.right", PromptRef("ctx.pr_reading", "1.0.0"), "ctx_pr", "g"),
        StepBar(0.9, "vi.right", PromptRef("ctx.pr_reading", "1.0.0"), "ctx_pr", "g"),
    ],
    ids=["the-bar-raised-since", "another-metric-since"],
)
async def test_a_pass_recorded_under_an_older_bar_is_not_todays(bar: StepBar) -> None:
    log = Log()
    await _attest(log).attest(
        A, Step.READ, model="qwen3.5:9b", value=0.93, held=True, dataset="ctx_pr@1.0.0"
    )
    readiness = await ReadinessCheck({Step.READ: bar}, log, _Model()).check(A, Step.READ)
    assert (readiness.ready, readiness.reason) == (False, "failed")
