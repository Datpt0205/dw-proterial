"""Unit: the three answers an idempotency key can get, and the two edges.

A fake store, no database. What matters here is the decision — replay, conflict,
or run — because that is what a route inherits and what a client's retry policy
is written against.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from dw_kernel.errors import ConflictError, IdempotencyConflictError
from dw_kernel.ports import FixedClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.idempotency import (
    STALE_RESERVATION,
    HttpIdempotency,
    RequestFingerprint,
    ReservedKey,
    StoredResponse,
)

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()
OTHER_WORKSPACE = uuid.uuid4()
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
KEY = "retry-me-once"

CONTEXT = AccessContext(
    tenant_id=TENANT,
    workspace_id=WORKSPACE,
    principal_id=uuid.uuid4(),
    roles=frozenset({"org_admin"}),
    plan_id="professional",
)


def fingerprint(
    *, body: bytes = b'{"approve":true}', workspace: uuid.UUID = WORKSPACE
) -> RequestFingerprint:
    return RequestFingerprint.of(
        method="post",
        path="/api/v1/approvals/1/decisions",
        workspace_id=workspace,
        body=body,
    )


class FakeStore:
    """One key's worth of state, plus a count of how often it was claimed."""

    def __init__(self, existing: ReservedKey | None = None, *, takeover_wins: bool = False) -> None:
        self.existing = existing
        self.takeover_wins = takeover_wins
        self.completed: StoredResponse | None = None
        self.released = False
        self.take_over_calls: list[datetime] = []

    async def reserve(
        self, context: AccessContext, *, key: str, fingerprint: RequestFingerprint
    ) -> ReservedKey | None:
        return self.existing

    async def take_over(self, context: AccessContext, *, key: str, older_than: datetime) -> bool:
        self.take_over_calls.append(older_than)
        return self.takeover_wins

    async def complete(self, context: AccessContext, *, key: str, response: StoredResponse) -> None:
        self.completed = response

    async def release(self, context: AccessContext, *, key: str) -> None:
        self.released = True


def build(store: FakeStore) -> HttpIdempotency:
    return HttpIdempotency(store=store, clock=FixedClock(NOW))


async def test_an_unspent_key_lets_the_handler_run() -> None:
    idempotency = build(FakeStore(existing=None))

    assert await idempotency.claim(CONTEXT, key=KEY, fingerprint=fingerprint()) is None


async def test_the_same_request_twice_replays_the_stored_response() -> None:
    stored = StoredResponse(status_code=200, body={"status": "approved"})
    idempotency = build(FakeStore(ReservedKey(fingerprint=fingerprint(), response=stored)))

    assert await idempotency.claim(CONTEXT, key=KEY, fingerprint=fingerprint()) == stored


async def test_a_different_body_under_the_same_key_is_refused() -> None:
    """The client reused a key for a new request. Answering it would hide that."""
    first = ReservedKey(
        fingerprint=fingerprint(body=b'{"approve":true}'),
        response=StoredResponse(status_code=200, body={"status": "approved"}),
    )
    idempotency = build(FakeStore(first))

    with pytest.raises(IdempotencyConflictError):
        await idempotency.claim(
            CONTEXT, key=KEY, fingerprint=fingerprint(body=b'{"approve":false}')
        )


async def test_the_same_key_in_another_workspace_is_refused() -> None:
    """A key is tenant-scoped, so this is a conflict — never a cross-workspace replay."""
    first = ReservedKey(
        fingerprint=fingerprint(workspace=OTHER_WORKSPACE),
        response=StoredResponse(status_code=200, body={"status": "approved"}),
    )
    idempotency = build(FakeStore(first))

    with pytest.raises(IdempotencyConflictError):
        await idempotency.claim(CONTEXT, key=KEY, fingerprint=fingerprint(workspace=WORKSPACE))


async def test_a_request_still_in_flight_is_refused_rather_than_run_again() -> None:
    """The second of two concurrent retries must not reach the handler."""
    store = FakeStore(ReservedKey(fingerprint=fingerprint(), response=None), takeover_wins=False)

    with pytest.raises(ConflictError) as excinfo:
        await build(store).claim(CONTEXT, key=KEY, fingerprint=fingerprint())

    assert excinfo.value.code.value == "conflict"
    assert store.completed is None


async def test_an_abandoned_reservation_is_taken_over() -> None:
    """A process killed mid-handler must not brick the key forever."""
    store = FakeStore(ReservedKey(fingerprint=fingerprint(), response=None), takeover_wins=True)

    assert await build(store).claim(CONTEXT, key=KEY, fingerprint=fingerprint()) is None
    assert store.take_over_calls == [NOW - STALE_RESERVATION]


async def test_a_takeover_cutoff_is_in_the_past() -> None:
    """Guards the sign of the subtraction: a future cutoff would steal live keys."""
    store = FakeStore(ReservedKey(fingerprint=fingerprint(), response=None), takeover_wins=True)
    await build(store).claim(CONTEXT, key=KEY, fingerprint=fingerprint())

    assert store.take_over_calls[0] < NOW
    assert NOW - store.take_over_calls[0] >= timedelta(minutes=1)


async def test_completing_stores_what_the_handler_returned() -> None:
    store = FakeStore()
    response = StoredResponse(status_code=201, body={"user_id": "u-1"})

    await build(store).complete(CONTEXT, key=KEY, response=response)

    assert store.completed == response


async def test_releasing_gives_the_key_back() -> None:
    store = FakeStore()

    await build(store).release(CONTEXT, key=KEY)

    assert store.released is True


def test_the_fingerprint_normalises_the_method_but_not_the_body() -> None:
    """Method case is HTTP's business. Body bytes are compared as they arrived."""
    assert fingerprint().method == "POST"
    assert fingerprint(body=b'{"a":1,"b":2}') != fingerprint(body=b'{"b":2,"a":1}')
