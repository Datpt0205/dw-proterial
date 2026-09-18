"""Worker main loop: runs registered consumers and keeps the heartbeat fresh.

The loop is the whole of this module's job. Each consumer is an ``async``
callable that does one tick of work and returns; the loop decides how often to
call it, catches what it raises, and stops every one of them on a single
shutdown event. A consumer that sleeps inside itself would be a consumer the
shutdown event cannot wake, so cadence is declared on the registry instead.

## Plugging in a bounded context

``build_registry`` wires only the platform lanes. A context adds its own at the
marked seam: build its components from settings, then
``registry.register("<name>", consumer, interval_seconds=...)``. If it owns job
queues, append a ``ReapTarget`` for each so abandoned rows are settled here
rather than in a second sweeper; if it has retention rules, satisfy
``RetentionPrunePort``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_knowledge.adapters.evidence_store import SqlEvidenceStore
from dw_memory.policy import MemoryWritePolicy
from dw_memory.service import MemoryService
from dw_observability.otel import build_telemetry
from dw_observability.telemetry import TelemetryPort
from dw_platform.adapters.persistence.outbox_drain import SqlOutboxDrain
from dw_worker.composition import build_ingest_components
from dw_worker.consumers import ConsumerRegistry
from dw_worker.consumers.ingest import build_ingest_consumer
from dw_worker.consumers.memory import memory_handlers
from dw_worker.consumers.outbox import EventHandler, build_outbox_consumer
from dw_worker.consumers.reaper import INTERVAL_SECONDS as REAP_INTERVAL_SECONDS
from dw_worker.consumers.reaper import ReapTarget, build_reaper_consumer
from dw_worker.consumers.retention import INTERVAL_SECONDS as RETENTION_INTERVAL_SECONDS
from dw_worker.consumers.retention import RetentionPrunePort, build_retention_consumer
from dw_worker.health import beat
from dw_worker.settings import WorkerSettings

logger = logging.getLogger("dw_worker")


def _build_worker_telemetry(settings: WorkerSettings) -> TelemetryPort:
    return build_telemetry(
        service_name="dw-worker",
        langfuse_enabled=settings.langfuse_enabled,
        langfuse_host=settings.langfuse_host,
        langfuse_public_key=settings.langfuse_public_key,
        langfuse_secret_key=settings.langfuse_secret_key,
        otel_endpoint=settings.otel_endpoint,
    )


def build_registry(settings: WorkerSettings) -> ConsumerRegistry:
    """Wire the lanes this process hosts, skipping any whose infra is absent."""
    registry = ConsumerRegistry()
    clock = SystemClock()
    # Uuid7: a memory id that sorts by when it was learned makes the
    # keyset page over `created_at` stable without a second column.
    ids = Uuid7Generator()
    _ = _build_worker_telemetry(settings)

    # Every queue this process wired, with the window its jobs deserve. A queue
    # this host did not wire stays absent rather than being reaped with a
    # guessed window: the rows still exist and another process owns them, and
    # two reapers disagreeing about what counts as stale is worse than one that
    # is silent.
    reap_targets: list[ReapTarget] = []
    # What this deployment considers expired. ``None`` means nothing is pruned,
    # which is the correct default: deleting rows on a schedule nobody asked for
    # is not a safe guess.
    retention: RetentionPrunePort | None = None

    if settings.database_url:
        # ---- transactional outbox ----------------------------------------
        # Handlers are keyed by event type. A context registers its own here;
        # an event with no handler is left in the table rather than dropped, so
        # adding the handler later drains the backlog.
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        # Remembering runs here rather than on the request that produced the
        # fact: a run that stops to decide what is worth keeping is a run someone
        # is waiting on. The handler is idempotent because the outbox delivers at
        # least once — see `dw_worker.consumers.memory`.
        handlers: dict[str, EventHandler] = dict(
            memory_handlers(
                MemoryService(
                    session_factory=sessions,
                    policy=MemoryWritePolicy(),
                    clock=clock,
                    id_generator=ids,
                    evidence_store=SqlEvidenceStore(clock=clock),
                )
            )
        )
        registry.register(
            "outbox",
            build_outbox_consumer(
                SqlOutboxDrain(sessions, clock),
                handlers,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
            ),
        )

    # ---- knowledge ingestion ---------------------------------------------
    # Needs a database and object storage both; without either, files are
    # staged by nobody and this lane would spin on an empty queue.
    ingest = build_ingest_components(settings)
    if ingest is not None:
        registry.register(
            "ingest",
            build_ingest_consumer(ingest, batch_size=settings.ingest_batch_size),
        )

    # ---- BOUNDED CONTEXT LANES REGISTER HERE -----------------------------
    # build_<context>_components(settings) → registry.register(...), and append
    # a ReapTarget per job queue the context owns.

    # ---- periodic repair --------------------------------------------------
    # Registered last because both sweeps act on what everything above created,
    # and both are skipped when there is nothing for them to act on.
    if reap_targets:
        registry.register(
            "reaper",
            build_reaper_consumer(reap_targets, clock),
            interval_seconds=REAP_INTERVAL_SECONDS,
        )
    if retention is not None:
        registry.register(
            "retention",
            build_retention_consumer(retention),
            interval_seconds=RETENTION_INTERVAL_SECONDS,
        )
    return registry


async def run_worker(
    settings: WorkerSettings,
    registry: ConsumerRegistry,
    shutdown_event: asyncio.Event,
) -> None:
    logger.info("worker starting, consumers=%s", sorted(registry.all()))

    async def heartbeat_loop() -> None:
        while not shutdown_event.is_set():
            beat(settings.heartbeat_file)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=settings.heartbeat_interval_seconds
                )

    async def consumer_loop(name: str) -> None:
        consumer = registry.all()[name]
        interval = registry.interval_for(name, settings.poll_interval_seconds)
        while not shutdown_event.is_set():
            try:
                await consumer()
            except Exception:
                # Broad on purpose: one lane's bad tick must not take the
                # process down and stop every other lane with it.
                logger.exception("consumer %s failed; backing off", name)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=interval)

    tasks = [asyncio.create_task(heartbeat_loop(), name="heartbeat")]
    tasks.extend(
        asyncio.create_task(consumer_loop(name), name=f"consumer:{name}") for name in registry.all()
    )
    await shutdown_event.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("worker stopped cleanly")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = WorkerSettings()
    settings.validate_for_profile()
    registry = build_registry(settings)
    shutdown_event = asyncio.Event()

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):  # Windows lacks add_signal_handler
                loop.add_signal_handler(sig, shutdown_event.set)
        await run_worker(settings, registry, shutdown_event)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
