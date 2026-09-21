import asyncio
from pathlib import Path

import pytest

from dw_worker.consumers import ConsumerRegistry
from dw_worker.health import beat, is_alive
from dw_worker.main import build_registry, run_worker
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit


def test_heartbeat_roundtrip(tmp_path: Path) -> None:
    hb = tmp_path / "heartbeat"
    beat(hb)
    assert is_alive(hb, max_age_seconds=10)
    assert not is_alive(tmp_path / "missing", max_age_seconds=10)


def test_registry_rejects_duplicates_and_blank_names() -> None:
    registry = ConsumerRegistry()

    async def consumer() -> None: ...

    registry.register("outbox", consumer)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("outbox", consumer)
    with pytest.raises(ValueError, match="blank"):
        registry.register("  ", consumer)


async def test_worker_runs_consumers_and_shuts_down(tmp_path: Path) -> None:
    settings = WorkerSettings(
        heartbeat_file=tmp_path / "hb",
        heartbeat_interval_seconds=0.05,
        poll_interval_seconds=0.05,
    )
    registry = ConsumerRegistry()
    calls = 0

    async def counting_consumer() -> None:
        nonlocal calls
        calls += 1

    registry.register("counter", counting_consumer)
    shutdown = asyncio.Event()

    worker_task = asyncio.create_task(run_worker(settings, registry, shutdown))
    await asyncio.sleep(0.3)
    shutdown.set()
    await asyncio.wait_for(worker_task, timeout=2)

    assert calls >= 2, "consumer should run repeatedly"
    assert is_alive(settings.heartbeat_file, max_age_seconds=5)


async def test_failing_consumer_does_not_kill_worker(tmp_path: Path) -> None:
    settings = WorkerSettings(
        heartbeat_file=tmp_path / "hb",
        heartbeat_interval_seconds=0.05,
        poll_interval_seconds=0.05,
    )
    registry = ConsumerRegistry()

    async def broken_consumer() -> None:
        raise RuntimeError("boom")

    registry.register("broken", broken_consumer)
    shutdown = asyncio.Event()
    worker_task = asyncio.create_task(run_worker(settings, registry, shutdown))
    await asyncio.sleep(0.3)
    assert not worker_task.done(), "worker must survive consumer failures"
    shutdown.set()
    await asyncio.wait_for(worker_task, timeout=2)


def bare_settings(**overrides: object) -> WorkerSettings:
    """Settings with every lane's infra explicitly absent.

    Stated rather than defaulted because these fields read plain environment
    variables (``S3_ENDPOINT_URL``, ``LANGFUSE_ENABLED``, …): a developer shell
    with a dev stack exported would otherwise decide what this process wires.
    """
    absent: dict[str, object] = {
        "database_url": None,
        "s3_endpoint_url": None,
        "qdrant_url": None,
        "langfuse_enabled": False,
        "otel_endpoint": None,
    }
    absent.update(overrides)
    return WorkerSettings(**absent)  # type: ignore[arg-type]


def test_a_host_with_no_infrastructure_wires_no_lane() -> None:
    """Every lane is conditional, so the heartbeat-only worker is a real shape."""
    assert set(build_registry(bare_settings()).all()) == set()


def test_only_the_platform_lanes_are_wired() -> None:
    """Four lanes a database alone is enough for, and no more.

    The outbox, and retention twice. Retention joined the platform set the day
    memory got a lifecycle: `memory.items` is a platform table, so the platform
    is what expires it — a context adds its own rules on top rather than owning
    the only ones. Ingest still needs object storage, and the reaper is
    registered only when something above it gave it a queue.

    Two retention lanes and not one because memory and knowledge expire on
    different terms and a pass that failed would otherwise take the other's work
    down with it. They read ONE policy file, which is the part that matters: a
    build where the two halves of a compliance commitment disagreed is the
    failure this split would otherwise invite.

    Naming the whole set is the point: a context's lane arriving in this process
    becomes a visible change rather than a silent one.
    """
    settings = bare_settings(database_url="postgresql+asyncpg://dw:dw@localhost/dw")
    assert set(build_registry(settings).all()) == {
        "outbox",
        "retention",
        "retention_knowledge",
        "partitions",
    }
