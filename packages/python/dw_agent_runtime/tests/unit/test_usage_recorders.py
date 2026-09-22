"""CompositeUsageRecorder: a failing recorder must not take the run down.

`SqlSpendGuardRecorder` is now unconditionally in this list at both
composition roots (Ops hardening Phase 3) — a transient database error there
must not turn into a failed model call the caller is otherwise holding a good
answer for. That contract lived in usage_recorders.py's docstring but had no
test of its own until now.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from dw_agent_runtime.adapters.usage_recorders import CompositeUsageRecorder
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import ModelUsage
from dw_agent_runtime.ports import ModelRequest

pytestmark = pytest.mark.unit

_REQUEST = ModelRequest(task="agent_loop", prompt_id="demo", prompt_version="1.0.0")
_USAGE = ModelUsage(provider="mock", model="mock", input_tokens=1, output_tokens=1, cost_usd=1.0)


def _run_context() -> RunContext:
    return RunContext(
        run_id=uuid.UUID(int=1),
        tenant_id=uuid.UUID(int=2),
        workspace_id=uuid.UUID(int=3),
        actor_id=uuid.UUID(int=4),
        worker_id="demo",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset(),
        trace_id="trace-1",
    )


@dataclass
class _RaisingRecorder:
    async def record(
        self, run_context: RunContext, request: ModelRequest, usage: ModelUsage
    ) -> None:
        raise RuntimeError("database is down")


@dataclass
class _RecordingRecorder:
    calls: list[ModelUsage] = field(default_factory=list)

    async def record(
        self, run_context: RunContext, request: ModelRequest, usage: ModelUsage
    ) -> None:
        self.calls.append(usage)


async def test_a_failing_recorder_does_not_stop_the_others() -> None:
    ok = _RecordingRecorder()
    composite = CompositeUsageRecorder([_RaisingRecorder(), ok])

    await composite.record(_run_context(), _REQUEST, _USAGE)  # must not raise

    assert ok.calls == [_USAGE]


async def test_every_recorder_still_runs_when_one_in_the_middle_fails() -> None:
    """Order in the list must not decide who gets recorded."""
    before = _RecordingRecorder()
    after = _RecordingRecorder()
    composite = CompositeUsageRecorder([before, _RaisingRecorder(), after])

    await composite.record(_run_context(), _REQUEST, _USAGE)

    assert before.calls == [_USAGE]
    assert after.calls == [_USAGE]
