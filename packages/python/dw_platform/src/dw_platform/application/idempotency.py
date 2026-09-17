"""Replay protection for mutating HTTP requests that carry an idempotency key.

The platform already enforces idempotency for *tools*
(``dw_agent_runtime.executor`` against ``platform.tool_executions``). This is the
HTTP half: the same guarantee for a client of the published API, which until now
could only retry a timed-out POST and hope.

Three outcomes, and the whole point is that they are decided here rather than in
a route:

* the key is unspent — the caller owns it and runs the handler;
* the key was spent on the *same* request — the stored response is returned and
  the handler never runs;
* the key was spent on a *different* request — refused, because answering it
  with the first request's response would hide a client bug behind a plausible
  reply.

What counts as "the same request" is :class:`RequestFingerprint`. It includes
the workspace, not only the method, path and body: one key reused across two
workspaces of a tenant must be a conflict, never a replay of the other
workspace's response into this one.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from dw_kernel.errors import ConflictError, IdempotencyConflictError
from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext

# How long a reservation may stay in flight before another request may take it
# over. A reservation is committed before the handler runs — it has to be, or a
# concurrent request could not see it — so a process killed mid-handler leaves
# one behind, and without a takeover that key would answer 409 forever.
#
# Chosen as a large multiple of the longest a request may legitimately take: the
# API's own upstream timeouts are seconds, so five minutes is far past "still
# working" and still short enough that a client's own retry schedule outlives it.
STALE_RESERVATION = timedelta(minutes=5)


@dataclass(frozen=True)
class RequestFingerprint:
    """What a key was spent on. Compared whole; any difference is a conflict."""

    method: str
    path: str
    workspace_id: uuid.UUID
    body_hash: str

    @classmethod
    def of(
        cls, *, method: str, path: str, workspace_id: uuid.UUID, body: bytes
    ) -> RequestFingerprint:
        return cls(
            method=method.upper(),
            path=path,
            workspace_id=workspace_id,
            # The raw bytes, not a parsed and re-serialised body: hashing what
            # actually arrived is the cheaper claim to defend, and it costs a
            # client nothing, because a retry re-sends what it sent.
            body_hash=hashlib.sha256(body).hexdigest(),
        )


@dataclass(frozen=True)
class StoredResponse:
    """A response worth replaying: the handler produced it and it succeeded."""

    status_code: int
    # ``None`` is a 204, which has no body. Everything else this API returns is
    # a JSON object.
    body: dict[str, object] | None


@dataclass(frozen=True)
class ReservedKey:
    """An existing row: what the key was spent on, and what it produced."""

    fingerprint: RequestFingerprint
    # ``None`` while the request that reserved the key is still running.
    response: StoredResponse | None


class IdempotencyStorePort(Protocol):
    """Persistence for spent keys, tenant-scoped through RLS.

    Every method commits on its own rather than joining the handler's
    transaction. That is deliberate: a reservation the handler's transaction
    could roll back would be invisible to the concurrent request it exists to
    stop, and a completion written inside the handler's transaction would be
    lost in exactly the case the reservation is there to survive.
    """

    async def reserve(
        self, context: AccessContext, *, key: str, fingerprint: RequestFingerprint
    ) -> ReservedKey | None:
        """Claim the key for this request.

        Returns ``None`` when the claim succeeded and the caller now owns the
        key, or the existing row when somebody else already holds it.
        """
        ...

    async def take_over(self, context: AccessContext, *, key: str, older_than: datetime) -> bool:
        """Re-claim a reservation that has been in flight since before ``older_than``.

        Returns whether this caller won it. Never true for a key whose response
        is already stored, so a completed response cannot be overwritten.
        """
        ...

    async def complete(
        self, context: AccessContext, *, key: str, response: StoredResponse
    ) -> None: ...

    async def release(self, context: AccessContext, *, key: str) -> None:
        """Give the key back, so a retry may spend it on a fresh attempt."""
        ...


@dataclass(frozen=True)
class HttpIdempotency:
    """Decides replay, conflict or run. Holds no per-request state."""

    store: IdempotencyStorePort
    clock: UtcClock

    async def claim(
        self, context: AccessContext, *, key: str, fingerprint: RequestFingerprint
    ) -> StoredResponse | None:
        """Claim ``key`` for this request.

        ``None`` means the caller owns the key and must run the handler, then
        call :meth:`complete` or :meth:`release`. A :class:`StoredResponse`
        means the handler must not run: return this instead.
        """
        existing = await self.store.reserve(context, key=key, fingerprint=fingerprint)
        if existing is None:
            return None

        if existing.fingerprint != fingerprint:
            raise IdempotencyConflictError(
                "idempotency key already used for a different request",
                details={
                    "idempotency_key": key,
                    "hint": "use a new key for a new request, or resend the original one",
                },
            )
        if existing.response is not None:
            return existing.response

        # Still in flight. Take the reservation over if it has been abandoned,
        # and otherwise refuse rather than wait: waiting would hold this
        # request's worker and connection for the length of the other request's
        # handler, which is how a client's retry storm becomes the server's
        # outage. The store decides who wins, in one statement.
        if await self.store.take_over(
            context, key=key, older_than=self.clock.now() - STALE_RESERVATION
        ):
            return None
        raise ConflictError(
            "a request with this idempotency key is still in progress",
            details={"idempotency_key": key, "hint": "retry in a few seconds"},
        )

    async def complete(self, context: AccessContext, *, key: str, response: StoredResponse) -> None:
        await self.store.complete(context, key=key, response=response)

    async def release(self, context: AccessContext, *, key: str) -> None:
        await self.store.release(context, key=key)
