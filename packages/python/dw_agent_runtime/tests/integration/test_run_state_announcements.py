"""Integration: a run's state change reaches another process, as it happens.

This is the whole reason the API can stop asking. The worker writes; the API
listens; Postgres carries the announcement between them. Three properties have
to hold against a real server, and none of them can be checked with a fake:

- the announcement is delivered, and carries enough to route it (tenant, worker,
  the record the run is about, the new status);
- it is bound to the transaction, so a rolled-back write announces nothing;
- both ends agree on the channel name and the payload shape.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import sqlalchemy as sa
from runtime_harness import RuntimeUrls, make_run_context
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.run_store import (
    RUN_STATE_CHANNEL,
    RunStatus,
    SqlWorkerRunStore,
)
from dw_agent_runtime.contracts import RunContext

# The shipped threshold (`configs/policies/worker_runs@1.0.0.yaml`). Stated
# rather than loaded: these tests never age a row, so the number only has
# to be a number.
STALE_AFTER_SECONDS_LOCAL = 3600


pytestmark = [pytest.mark.integration, pytest.mark.anyio]

# Generous: the point is that delivery happens at all, not how fast a loaded
# CI box gets there. A real delivery takes single-digit milliseconds.
_DELIVERY_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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


@pytest.fixture
async def heard(urls: RuntimeUrls) -> AsyncIterator[asyncio.Queue[dict[str, str]]]:
    """A second connection, standing in for the API process."""
    queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    connection = await asyncpg.connect(
        urls.app.replace("postgresql+asyncpg://", "postgresql://", 1)
    )

    def on_notify(_conn: object, _pid: int, _channel: str, payload: str) -> None:
        queue.put_nowait(json.loads(payload))

    await connection.add_listener(RUN_STATE_CHANNEL, on_notify)
    try:
        yield queue
    finally:
        await connection.close()


async def _next(queue: asyncio.Queue[dict[str, str]]) -> dict[str, str]:
    return await asyncio.wait_for(queue.get(), timeout=_DELIVERY_TIMEOUT_SECONDS)


def _about(context: RunContext, subject: str) -> RunContext:
    return context.model_copy(update={"subject_ref": subject})


async def test_starting_a_run_is_announced_to_another_connection(
    store: SqlWorkerRunStore, heard: asyncio.Queue[dict[str, str]]
) -> None:
    subject = str(uuid.uuid4())
    context = _about(make_run_context(), subject)

    await store.create(context, graph_version="1.0.0", input_payload={})

    assert await _next(heard) == {
        "tenant": str(context.tenant_id),
        "worker": context.worker_id,
        "run": str(context.run_id),
        "subject": subject,
        "status": RunStatus.RUNNING.value,
    }


async def test_settling_a_run_is_announced_with_its_new_status(
    store: SqlWorkerRunStore, heard: asyncio.Queue[dict[str, str]]
) -> None:
    """The event the waiting page is actually waiting for."""
    subject = str(uuid.uuid4())
    context = _about(make_run_context(), subject)
    await store.create(context, graph_version="1.0.0", input_payload={})
    await _next(heard)

    await store.set_status(context, context.run_id, status=RunStatus.COMPLETED)

    settled = await _next(heard)
    assert settled["status"] == RunStatus.COMPLETED.value
    assert settled["subject"] == subject


async def test_a_failed_run_is_announced_too(
    store: SqlWorkerRunStore, heard: asyncio.Queue[dict[str, str]]
) -> None:
    """A page told only about success spins for ever over a run that died."""
    context = _about(make_run_context(), str(uuid.uuid4()))
    await store.create(context, graph_version="1.0.0", input_payload={})
    await _next(heard)

    await store.set_status(context, context.run_id, status=RunStatus.FAILED)

    assert (await _next(heard))["status"] == RunStatus.FAILED.value


async def test_a_rolled_back_write_announces_nothing(
    urls: RuntimeUrls, heard: asyncio.Queue[dict[str, str]]
) -> None:
    """Postgres drops a NOTIFY whose transaction never commits. That is what
    makes the announcement safe to send from inside the write."""
    engine = create_async_engine(urls.app, poolclass=NullPool)
    context = _about(make_run_context(), str(uuid.uuid4()))
    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(
                sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(context.tenant_id)},
            )
            await session.execute(
                sa.text("SELECT pg_notify(:channel, :payload)"),
                {"channel": RUN_STATE_CHANNEL, "payload": json.dumps({"run": "rolled-back"})},
            )
            await session.rollback()
    finally:
        await engine.dispose()

    with pytest.raises(TimeoutError):
        await _next(heard)
