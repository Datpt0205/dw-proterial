"""A run's row records the model profile its worker pins (migration 271bdb87af91).

What is under test is the insert the store builds, captured from a session
that records statements instead of running them: `create` takes the whole
worker, so the profile comes from the definition and no caller can pass a
different one. That the column exists and round-trips is
`tests/integration/test_run_records_versions.py`'s question.
"""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.sql.dml import Insert

from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.testing.demo_graph import DEMO_WORKER

pytestmark = pytest.mark.unit


class _RecordingSession:
    def __init__(self, seen: list[Any]) -> None:
        self._seen = seen

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> _RecordingSession:
        return self

    async def execute(self, statement: Any, params: Any = None) -> None:
        self._seen.append(statement)


def _context() -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        worker_id=DEMO_WORKER.worker_id,
        worker_version=DEMO_WORKER.worker_version,
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset({"demo.read"}),
        trace_id="trace-1",
    )


@pytest.mark.parametrize("profile", ["balanced", "low_cost"])
async def test_the_insert_carries_the_profile_the_worker_pins(profile: str) -> None:
    seen: list[Any] = []
    store = SqlWorkerRunStore(
        lambda: _RecordingSession(seen),  # type: ignore[arg-type]
        stale_run_after_seconds=3600,
    )
    worker = DEMO_WORKER.model_copy(update={"default_model_profile": profile})

    await store.create(_context(), worker=worker, input_payload={})

    (insert,) = [s for s in seen if isinstance(s, Insert)]
    params = insert.compile().params
    assert params["model_profile"] == profile
    assert isinstance(insert.table, sa.Table) and insert.table.name == "worker_runs"
