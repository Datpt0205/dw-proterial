""" "DW xử lý" as a queue (ticket 25): the routes enqueue, the worker drains.

The real services over the in-memory world (`open_world`), whose store holds
the queue as `sales.processing_jobs` does (one job per message, a claim that
counts attempts, a settlement that names its claim). The SQL half, the
upsert, `FOR UPDATE SKIP LOCKED` and the reaper's function, is tested against
PostgreSQL in `test_sales_store.py` (owed with Docker).
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import system_actor
from dw_sales.application.case_store import Settlement
from dw_sales.application.malware import ScanVerdict
from dw_sales.application.processing import (
    MAX_ATTEMPTS,
    RETRY_AFTER,
    SALES_PROCESSING_LANE,
    ProcessingDrain,
)
from dw_sales.application.views import MessageDispositionView
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, NOW, Directory, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world(**options: object) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, **options)  # type: ignore[arg-type]


def _job(world: World, message_id: str) -> tuple[str, str | None, int]:
    job = world.store.state(ALPHA).jobs[message_id]
    return job.status, job.error, job.attempts


class _Down:
    """A scanner that cannot answer: every file is an outage."""

    async def scan(self, data: bytes) -> ScanVerdict:
        return ScanVerdict.unavailable("connection refused")


# ------------------------------------------------------------------ enqueue --


async def test_pressing_queues_the_message_and_says_who_asked_without_running_it() -> None:
    world = _world()

    job = await world.services.processing.enqueue(AN.context(), "M01")

    assert (job.message_id, job.status, job.attempts, job.error) == ("M01", "queued", 0, None)
    assert world.runtime.runs.rows == {}
    assert world.store.state(ALPHA).messages == {}
    queued = [e for e in world.audit() if e.action == "sales.message.queued"]
    assert [(e.actor_id.value, e.resource_id) for e in queued] == [(AN.user_id, "M01")]
    assert queued[0].details == {"job_id": str(job.job_id)}


async def test_pressing_twice_queues_once() -> None:
    world = _world()

    first = await world.services.processing.enqueue(AN.context(), "M01")
    second = await world.services.processing.enqueue(GIANG.context(), "M01")

    assert second.job_id == first.job_id
    assert world.store.state(ALPHA).jobs["M01"].requested_by == AN.user_id
    assert len([e for e in world.audit() if e.action == "sales.message.queued"]) == 1


async def test_a_caller_without_the_inbox_scope_queues_nothing() -> None:
    world = _world()

    with pytest.raises(PermissionDeniedError):
        await world.services.processing.enqueue(READER.context(), "M01")

    assert world.store.state(ALPHA).jobs == {}


async def test_another_tenant_cannot_queue_alphas_message() -> None:
    """Tenant beta names alpha's message: nothing found, nothing queued in
    either workspace (the mailbox is read in the caller's own scope)."""
    world = _world()

    with pytest.raises(NotFoundError):
        await world.services.processing.enqueue(OUTSIDER.context(BETA), "M01")

    assert world.store.state(ALPHA).jobs == {} and world.store.state(BETA).jobs == {}
    assert await world.services.processing.enqueue_waiting(OUTSIDER.context(BETA)) == []


async def test_an_unknown_message_is_not_found_and_queues_nothing() -> None:
    world = _world()

    with pytest.raises(NotFoundError):
        await world.services.processing.enqueue(AN.context(), "M99")

    assert world.store.state(ALPHA).jobs == {}


async def test_a_message_on_a_case_is_refused_and_a_routed_one_is_queued_again() -> None:
    world = _world()
    await world.process_each(AN, ["M01", "M11"])

    with pytest.raises(ConflictError):
        await world.services.processing.enqueue(AN.context(), "M01")
    again = await world.services.processing.enqueue(AN.context(), "M11")

    assert again.status == "queued"
    assert "M01" not in world.store.state(ALPHA).jobs


async def test_a_paused_dw1_queues_nothing_and_names_who_paused_it() -> None:
    world = _world()
    await world.services.worker.pause(AN.context(), None)

    with pytest.raises(ConflictError) as refused:
        await world.services.processing.enqueue_waiting(GIANG.context())

    assert refused.value.details["rule"] == "worker_paused"
    assert refused.value.details["paused_by"] == str(AN.user_id)
    assert world.store.state(ALPHA).jobs == {}


async def test_all_queues_every_message_without_a_disposition_oldest_first() -> None:
    world = _world()
    await world.process_each(AN, ["M01"])
    mailbox = [m.message_id for m in await world.inbox.list_messages(ALPHA)]

    jobs = await world.services.processing.enqueue_waiting(AN.context())

    assert [j.message_id for j in jobs] == [m for m in mailbox if m != "M01"]
    assert {j.status for j in jobs} == {"queued"}


# -------------------------------------------------------------------- drain --


async def test_the_worker_runs_each_job_as_whoever_asked_and_the_inbox_shows_it() -> None:
    world = _world()
    await world.services.processing.enqueue(AN.context(), "M01")
    shown = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}
    assert shown["M01"].processing is not None and shown["M01"].processing.status == "queued"

    assert await world.drain() == 1

    assert _job(world, "M01") == ("done", None, 1)
    (run,) = world.runtime.runs.rows.values()
    assert (run.context.actor_id, run.input["task"]["message_id"]) == (AN.user_id, "M01")
    # Cut to what processing needs, whatever else the person holds.
    assert run.context.scopes == frozenset({"sales.inbox.process"})
    shown = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}
    assert shown["M01"].disposition.kind == "case_created"
    assert shown["M01"].processing is not None and shown["M01"].processing.status == "done"
    (ran,) = [e for e in world.audit() if e.action == "sales.message.processing_done"]
    assert ran.actor_id == system_actor(SALES_PROCESSING_LANE)
    assert ran.details["requested_by"] == str(AN.user_id)
    assert ran.details["disposition"] == "case_created"


async def test_a_person_who_lost_the_scope_since_pressing_processes_nothing() -> None:
    world = _world()
    await world.services.processing.enqueue(AN.context(), "M01")
    gone = replace(AN, scopes=frozenset({"sales.case.read"}))
    drain = ProcessingDrain(
        world.store,
        world.store,
        world.services.dw1,
        Directory((gone,)),
        world.store.clock,
        world.processing.ids,
    )

    await drain.drain_one()

    assert _job(world, "M01") == ("failed", "not_permitted", 1)
    assert world.runtime.runs.rows == {}
    assert world.store.state(ALPHA).messages == {}


async def test_a_stranger_in_the_workspace_processes_nothing() -> None:
    world = _world()
    async with world.store(ALPHA) as work:
        await work.jobs.enqueue("M01", uuid.uuid4(), NOW, uuid.uuid4())
        await work.commit()

    await world.drain()

    assert _job(world, "M01") == ("failed", "not_permitted", 1)
    assert world.runtime.runs.rows == {}


async def test_an_outage_is_retried_later_then_fails_unavailable_recording_nothing() -> None:
    world = _world(scanner=_Down())
    clock = world.store.clock
    await world.services.processing.enqueue(AN.context(), "M01")

    assert await world.drain() == 1
    first = world.store.state(ALPHA).jobs["M01"]
    assert (first.status, first.attempts) == ("queued", 1)
    assert first.available_at == NOW + RETRY_AFTER
    # Not due before its time.
    assert await world.drain() == 0

    for attempt in range(2, MAX_ATTEMPTS + 1):
        clock.advance_to(world.store.state(ALPHA).jobs["M01"].available_at)
        assert await world.drain() == 1
        assert world.store.state(ALPHA).jobs["M01"].attempts == attempt

    assert _job(world, "M01") == ("failed", "unavailable", MAX_ATTEMPTS)
    # Fail closed: nothing about the message was recorded.
    assert world.store.state(ALPHA).messages == {}


async def test_a_job_the_model_could_not_read_yet_fails_to_be_tried_later() -> None:
    world = _world()

    class _NotYet:
        async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
            return MessageDispositionView(kind="not_yet_processed")

    await world.services.processing.enqueue(AN.context(), "M01")
    drain = replace(world.processing, runs=_NotYet())

    await drain.drain_one()

    assert _job(world, "M01") == ("failed", "model_retry", 1)


async def test_a_settlement_whose_claim_was_taken_back_writes_nothing() -> None:
    world = _world()
    await world.services.processing.enqueue(AN.context(), "M01")
    claimed = await world.store.claim()
    assert claimed is not None
    # The reaper put it back and another worker took it: a newer claim.
    taken = await world.store.claim()
    assert taken is None
    state = world.store.state(ALPHA)
    state.jobs["M01"] = replace(state.jobs["M01"], attempts=claimed.job.attempts + 1)

    async with world.store(ALPHA) as work:
        settled = await work.jobs.settle(claimed.job, Settlement.done(), NOW)

    assert settled is False
    assert world.store.state(ALPHA).jobs["M01"].status == "running"


async def test_a_finished_job_queued_again_starts_its_attempts_over() -> None:
    world = _world()
    await world.process_each(AN, ["M11"])
    await world.services.processing.enqueue(AN.context(), "M11")
    await world.drain()
    assert world.store.state(ALPHA).jobs["M11"].status == "done"

    again = await world.services.processing.enqueue(GIANG.context(), "M11")

    assert (again.status, again.attempts) == ("queued", 0)
    assert world.store.state(ALPHA).jobs["M11"].requested_by == GIANG.user_id
