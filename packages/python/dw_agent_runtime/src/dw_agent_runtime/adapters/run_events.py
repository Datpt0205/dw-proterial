"""Delivers worker run state changes to whoever is watching, as they happen.

Runs execute in the worker process; the pages that care about them are served
by the API process. Nothing in memory spans the two, so the API used to have
only one way to find out that a run had finished: ask again, and again. That
made every watcher pay a fixed delay for an event that had already happened,
and made an idle system talk to its database forever.

Postgres already spans the two processes and already knows the moment a run's
row commits. ``pg_notify`` from the writer, ``LISTEN`` here, and the delay
becomes the network hop it actually is. No broker, no second store, no new
dependency - and the announcement inherits the write's transaction, so a
watcher is never told about a state that rolled back.

One connection per API process, held for its lifetime, fanning out in memory to
however many watchers that process is serving. The connection is deliberately
NOT taken from the request pool: a listening connection is busy forever, and a
pool that lends one out has lost it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from dw_agent_runtime.adapters.run_store import RUN_STATE_CHANNEL

logger = logging.getLogger(__name__)

# A watcher that stops reading must not be able to stall the listener, and a
# score changes a handful of times a minute at most - a queue this size only
# fills if the consumer is already gone.
_QUEUE_LIMIT = 32

# How long a reconnect waits after the database drops the listening connection.
# Long enough not to hammer a restarting server, short enough that a watcher's
# first missed event is the only one it misses.
_RECONNECT_DELAY_SECONDS = 2.0


@dataclass(frozen=True)
class RunStateEvent:
    """One run changed state. Carries identity, never content."""

    tenant_id: uuid.UUID
    worker_id: str
    run_id: uuid.UUID
    subject_ref: str | None
    status: str

    @classmethod
    def parse(cls, payload: str) -> RunStateEvent | None:
        try:
            raw: Any = json.loads(payload)
            return cls(
                tenant_id=uuid.UUID(raw["tenant"]),
                worker_id=str(raw["worker"]),
                run_id=uuid.UUID(raw["run"]),
                subject_ref=None if raw.get("subject") is None else str(raw["subject"]),
                status=str(raw["status"]),
            )
        except (ValueError, KeyError, TypeError):
            # A payload this process cannot read is a deployment where one side
            # is newer than the other. Dropping it loses liveness, not
            # correctness: every watcher reads its state on connect anyway.
            logger.warning("unreadable run-state announcement discarded")
            return None


@dataclass(eq=False)
class _Watcher:
    tenant_id: uuid.UUID
    worker_id: str
    subject_ref: str
    queue: asyncio.Queue[RunStateEvent] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_LIMIT)
    )

    def wants(self, event: RunStateEvent) -> bool:
        """Tenant first, always. The payload crosses tenants; a watcher must not."""
        return (
            event.tenant_id == self.tenant_id
            and event.worker_id == self.worker_id
            and event.subject_ref == self.subject_ref
        )


class RunStateListener:
    """Owns the LISTEN connection and fans out to in-process watchers."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._watchers: set[_Watcher] = set()
        self._task: asyncio.Task[None] | None = None
        self._connection: asyncpg.Connection[Any] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="run-state-listener")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close()

    @contextlib.asynccontextmanager
    async def watch(
        self, tenant_id: uuid.UUID, *, worker_id: str, subject_ref: str
    ) -> AsyncIterator[AsyncIterator[RunStateEvent]]:
        """Events for one record, for as long as the caller stays inside."""
        watcher = _Watcher(tenant_id=tenant_id, worker_id=worker_id, subject_ref=subject_ref)
        self._watchers.add(watcher)
        try:
            yield _drain(watcher.queue)
        finally:
            self._watchers.discard(watcher)

    # -- internals ---------------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                await self._listen_forever()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncpg.PostgresError) as exc:
                # Losing the connection costs liveness until it is back; every
                # watcher re-reads its state on connect, so nothing is wrong
                # afterwards, only late.
                logger.warning("run-state listener reconnecting: %s", exc)
                await self._close()
                await asyncio.sleep(_RECONNECT_DELAY_SECONDS)

    async def _listen_forever(self) -> None:
        self._connection = await asyncpg.connect(self._dsn)
        await self._connection.add_listener(RUN_STATE_CHANNEL, self._on_notify)
        logger.info("listening for run state on %s", RUN_STATE_CHANNEL)
        # asyncpg delivers on its own reader task; this one only has to notice
        # when the connection dies, which is what makes the loop above retry.
        while not self._connection.is_closed():
            await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
        raise ConnectionError("listening connection closed")

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: str) -> None:
        event = RunStateEvent.parse(payload)
        if event is None:
            return
        for watcher in self._watchers:
            if not watcher.wants(event):
                continue
            try:
                watcher.queue.put_nowait(event)
            except asyncio.QueueFull:
                # The watcher is not reading. Its stream is already over in
                # every way that matters; do not let it block the others.
                logger.warning("dropping run-state event for a watcher that stopped reading")

    async def _close(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(OSError, asyncpg.PostgresError):
                await self._connection.close()
            self._connection = None


async def _drain(queue: asyncio.Queue[RunStateEvent]) -> AsyncIterator[RunStateEvent]:
    while True:
        yield await queue.get()
