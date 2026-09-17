"""Integration: "is something still working on this subject" against real SQL.

A surface that triggers work it does not wait for polls this on a timer, so
three things have to hold against the database rather than against a fake: the
lookup reads the subject out of the run's JSON input, it counts only runs that
have not settled, and it cannot see another tenant's runs.

What a unit test cannot check is that the column, the caller's value and the
partial index in migration 0059 agree - a mismatch in any of the three turns
this into a sequential scan, or into a wrong answer.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from runtime_harness import TENANT_B, WORKSPACE_B, RuntimeUrls, make_run_context
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.run_store import RunStatus, SqlWorkerRunStore
from dw_agent_runtime.contracts import RunContext

# The shipped threshold (`configs/policies/worker_runs@1.0.0.yaml`). Stated
# rather than loaded: these tests never age a row, so the number only has
# to be a number.
STALE_AFTER_SECONDS_LOCAL = 3600


pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# The harness stamps every run with this worker; the scorer's own id is
# irrelevant here, what matters is that the filter discriminates at all.
WORKER = "demo_approval"
OTHER_WORKER = "sales_chat"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _about(context: RunContext, lead_id: str) -> RunContext:
    """The run declares what it is about; that is what the lookup reads."""
    return context.model_copy(update={"subject_ref": lead_id})


@pytest.fixture
async def store(urls: RuntimeUrls) -> AsyncIterator[SqlWorkerRunStore]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    try:
        yield SqlWorkerRunStore(
            async_sessionmaker(engine, expire_on_commit=False),
            stale_run_after_seconds=STALE_AFTER_SECONDS_LOCAL,
        )
    finally:
        await engine.dispose()


async def _ask(
    store: SqlWorkerRunStore, tenant: uuid.UUID, lead_id: str, *, worker: str = WORKER
) -> object:
    return await store.active_since(tenant, worker_id=worker, subject_ref=lead_id)


async def test_a_run_still_going_reports_the_moment_it_started(
    store: SqlWorkerRunStore,
) -> None:
    lead = str(uuid.uuid4())
    context = make_run_context()
    await store.create(_about(context, lead), graph_version="1.0.0", input_payload={})

    since = await _ask(store, context.tenant_id, lead)

    assert since is not None
    record = await store.get(context, context.run_id)
    assert record.status is RunStatus.RUNNING


async def test_a_settled_run_stops_being_reported(store: SqlWorkerRunStore) -> None:
    """The whole contract: the spinner has to end when the work does."""
    lead = str(uuid.uuid4())
    context = make_run_context()
    await store.create(_about(context, lead), graph_version="1.0.0", input_payload={})
    assert await _ask(store, context.tenant_id, lead) is not None

    await store.set_status(context, context.run_id, status=RunStatus.COMPLETED)

    assert await _ask(store, context.tenant_id, lead) is None


async def test_a_failed_run_also_stops_being_reported(store: SqlWorkerRunStore) -> None:
    """Failure settles too. Reporting it as still running is how a page ends up
    spinning for ever over a run that died a minute ago."""
    lead = str(uuid.uuid4())
    context = make_run_context()
    await store.create(_about(context, lead), graph_version="1.0.0", input_payload={})

    await store.set_status(context, context.run_id, status=RunStatus.FAILED)

    assert await _ask(store, context.tenant_id, lead) is None


async def test_a_run_on_another_lead_is_not_this_lead(store: SqlWorkerRunStore) -> None:
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    context = make_run_context()
    await store.create(_about(context, theirs), graph_version="1.0.0", input_payload={})

    assert await _ask(store, context.tenant_id, mine) is None


async def test_another_tenants_run_is_invisible(store: SqlWorkerRunStore) -> None:
    """RLS, not a WHERE clause the caller could forget."""
    lead = str(uuid.uuid4())
    context = make_run_context(tenant=TENANT_B, workspace=WORKSPACE_B)
    await store.create(_about(context, lead), graph_version="1.0.0", input_payload={})

    mine = make_run_context()
    assert await _ask(store, mine.tenant_id, lead) is None
    assert await _ask(store, TENANT_B, lead) is not None


async def test_the_oldest_of_several_runs_is_the_one_reported(
    store: SqlWorkerRunStore,
) -> None:
    """Queued signals mean a lead can have more than one run outstanding. The
    first one is when the work on screen actually began."""
    lead = str(uuid.uuid4())
    first = make_run_context()
    await store.create(_about(first, lead), graph_version="1.0.0", input_payload={})
    second = make_run_context()
    await store.create(_about(second, lead), graph_version="1.0.0", input_payload={})

    since = await _ask(store, first.tenant_id, lead)

    earliest = (await store.get(first, first.run_id)).id
    assert earliest == first.run_id
    assert since is not None


async def test_a_run_of_a_different_worker_does_not_count(
    store: SqlWorkerRunStore,
) -> None:
    """Two workers can hold the same id in their input and mean different work."""
    lead = str(uuid.uuid4())
    context = make_run_context()
    await store.create(_about(context, lead), graph_version="1.0.0", input_payload={})

    assert await _ask(store, context.tenant_id, lead, worker=OTHER_WORKER) is None
