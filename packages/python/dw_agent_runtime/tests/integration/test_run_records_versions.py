"""A run records every artifact version it ran under — on the row, not the span.

`configs/workers/README.md` says a run records them "so a result can be traced
back to the exact artifacts that produced it". Before migration 0005 that was
true of the OpenTelemetry span and false of `platform.worker_runs`, which held
the worker and graph version and none of the other four. A span is sampled and
expires; a claim about provenance that only a span can answer is not a claim
the system of record supports.

So it is asserted here against real SQL rather than against the store's own
return value: the point is that the columns exist, that the insert fills them,
and that reading a run back gets the same four values the worker was pinned to.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from runtime_harness import RuntimeUrls, make_run_context
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.testing.demo_graph import DEMO_WORKER

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

STALE_AFTER_SECONDS_LOCAL = 3600


@pytest.fixture
async def store(urls: RuntimeUrls) -> AsyncIterator[SqlWorkerRunStore]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlWorkerRunStore(sessions, stale_run_after_seconds=STALE_AFTER_SECONDS_LOCAL)
    finally:
        await engine.dispose()


async def test_a_run_carries_the_versions_its_worker_was_pinned_to(
    store: SqlWorkerRunStore,
) -> None:
    context = make_run_context(thread_id=uuid.uuid4())

    await store.create(context, worker=DEMO_WORKER, input_payload={})
    recorded = await store.get(context, context.run_id)

    assert recorded.graph_version == DEMO_WORKER.graph_version
    assert recorded.prompt_bundle_version == DEMO_WORKER.prompt_bundle_version
    assert recorded.toolset_version == DEMO_WORKER.toolset_version
    assert recorded.policy_version == DEMO_WORKER.policy_version
    assert recorded.memory_policy_version == DEMO_WORKER.memory_policy_version


async def test_the_row_cannot_disagree_with_the_worker(store: SqlWorkerRunStore) -> None:
    """The versions come from one object, so there is no call site to get wrong.

    This is the property `create` was reshaped for: it takes the definition, not
    five strings beside each other. Passing them one by one is how a row comes to
    claim last week's toolset — five arguments are five chances, and an argument
    nobody passes is a NULL nobody notices.
    """
    context = make_run_context(thread_id=uuid.uuid4())
    await store.create(context, worker=DEMO_WORKER, input_payload={})

    recorded = await store.get(context, context.run_id)

    pinned = {
        recorded.worker_version: DEMO_WORKER.worker_version,
        recorded.graph_version: DEMO_WORKER.graph_version,
    }
    assert all(actual == expected for actual, expected in pinned.items())
    # Nothing is left unset: a NULL here means a run that cannot be reproduced.
    assert None not in (
        recorded.prompt_bundle_version,
        recorded.toolset_version,
        recorded.policy_version,
        recorded.memory_policy_version,
    )
