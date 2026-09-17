"""Who gets told about a run, and who must not.

The announcement travels on one cluster-wide channel, so every API process
hears every tenant's runs. Routing is therefore a security boundary, not a
convenience: the filter here is the only thing standing between a watcher and
the fact that some other tenant is scoring something.
"""

from __future__ import annotations

import uuid

import pytest

from dw_agent_runtime.adapters.run_events import RunStateEvent, RunStateListener

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()
LEAD = str(uuid.uuid4())
WORKER = "lead_scoring"


def _event(**overrides: object) -> RunStateEvent:
    fields: dict[str, object] = {
        "tenant_id": TENANT,
        "worker_id": WORKER,
        "run_id": uuid.uuid4(),
        "subject_ref": LEAD,
        "status": "completed",
    }
    fields.update(overrides)
    return RunStateEvent(**fields)  # type: ignore[arg-type]


async def test_two_pages_watching_the_same_lead_both_hear_it() -> None:
    """Identity, not value: watchers with identical filters are still two."""
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as first:
        async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as second:
            listener._on_notify(None, 0, "", _payload(_event()))
            assert (await anext(first)).subject_ref == LEAD
            assert (await anext(second)).subject_ref == LEAD


async def test_a_watcher_hears_its_own_lead() -> None:
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as events:
        listener._on_notify(None, 0, "", _payload(_event()))
        assert (await anext(events)).subject_ref == LEAD


async def test_another_tenants_run_never_reaches_a_watcher() -> None:
    """Same worker, same lead id, different tenant. Ids are not secrets and can
    collide across tenants by accident or on purpose."""
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as events:
        listener._on_notify(None, 0, "", _payload(_event(tenant_id=OTHER_TENANT)))
        listener._on_notify(None, 0, "", _payload(_event()))

        # The only event that arrives is the second one.
        assert (await anext(events)).tenant_id == TENANT


async def test_another_lead_never_reaches_a_watcher() -> None:
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as events:
        listener._on_notify(None, 0, "", _payload(_event(subject_ref=str(uuid.uuid4()))))
        listener._on_notify(None, 0, "", _payload(_event()))

        assert (await anext(events)).subject_ref == LEAD


async def test_another_worker_never_reaches_a_watcher() -> None:
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD) as events:
        listener._on_notify(None, 0, "", _payload(_event(worker_id="sales_chat")))
        listener._on_notify(None, 0, "", _payload(_event()))

        assert (await anext(events)).worker_id == WORKER


async def test_a_watcher_that_has_left_stops_being_offered_events() -> None:
    listener = RunStateListener("postgresql://unused")
    async with listener.watch(TENANT, worker_id=WORKER, subject_ref=LEAD):
        pass

    # No watcher left; delivering must not raise.
    listener._on_notify(None, 0, "", _payload(_event()))


def test_an_unreadable_payload_is_discarded_not_raised() -> None:
    """One side newer than the other must not take the listener down with it."""
    assert RunStateEvent.parse("not json") is None
    assert RunStateEvent.parse('{"tenant": "not-a-uuid"}') is None
    assert RunStateEvent.parse('{"worker": "x"}') is None


def _payload(event: RunStateEvent) -> str:
    import json

    return json.dumps(
        {
            "tenant": str(event.tenant_id),
            "worker": event.worker_id,
            "run": str(event.run_id),
            "subject": event.subject_ref,
            "status": event.status,
        }
    )
