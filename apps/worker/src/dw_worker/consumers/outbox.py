"""Outbox dispatcher: turn a committed domain event into the effect it announced.

Per tick: claim a batch of undelivered events of the types this process knows how
to handle, run each one's effect, and mark it delivered. Delivery is at-least-once
- the attempt is counted at claim time and the row is marked afterwards - so every
handler wired here has to be idempotent.

**No effect is wired today, deliberately.** Research-on-account-created and
re-score-on-lead-evidence both used to live here, and both were removed rather
than switched off: an event says what happened, never who caused it, so a
A bulk import announced 1,666 created records exactly as loudly as a
salesperson typing one name, and each announcement bought a paid search call.
Both effects remain available on demand through their own endpoints, and lead
scoring now starts when someone opens the lead. A setting would have left the
backlog one boolean away from running; deleting the handlers means turning it
back on is a code change, reviewed like one.

An event whose type has no handler is not claimed at all, so the events the CRM
keeps announcing accumulate unread rather than being drained into nothing - a
handler added later finds its history intact instead of a table of rows already
marked delivered. To wire one, pass ``{EVENT_TYPE: handler}`` to
``build_outbox_consumer`` from ``dw_worker.main``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping

from dw_kernel.ports import UtcClock
from dw_observability.metrics import DW_OUTBOX_BACKLOG_SIZE, DW_OUTBOX_OLDEST_PENDING_AGE_SECONDS
from dw_observability.telemetry import TelemetryPort
from dw_platform.application.ports import OutboxDrainPort
from dw_platform.domain.outbox import OutboxEvent

logger = logging.getLogger("dw_worker.outbox")

EventHandler = Callable[[OutboxEvent], Awaitable[str]]
"""Deliver one event and say in a few words what it did, for the log."""

_ERROR_LIMIT = 500


class UndeliverableEventError(Exception):
    """The handler refused the event itself: a payload that does not parse, or a
    refusal of what it asks for — not a failure of the handler or a dependency.

    It changes how the failure is reported (one error line with the reason, no
    traceback), not how it is retried: the event stays undelivered and is
    claimed again until ``max_attempts`` is spent, like any other failure. A
    refusal believed final has turned out not to be — a settlement losing a
    race to another delivery was refused once and found the decision applied
    on the next look (9704778) — so a bounded retry is the safe answer, and a
    handler should still raise this only when a retry is not expected to help.
    """


async def _deliver(event: OutboxEvent, handler: EventHandler, drain: OutboxDrainPort) -> None:
    try:
        outcome = await handler(event)
    except UndeliverableEventError as exc:
        # The reason is the event's, so it is recorded without a traceback. The
        # attempt was counted at claim, so the retries are bounded by
        # `max_attempts` either way; nothing here shortens them.
        logger.error("outbox event %s (%s) is undeliverable: %s", event.id, event.event_type, exc)
        await drain.record_failure(event.id, error=str(exc)[:_ERROR_LIMIT])
        return
    except Exception as exc:
        logger.exception("outbox event %s (%s) failed", event.id, event.event_type)
        await drain.record_failure(event.id, error=f"{type(exc).__name__}: {exc}"[:_ERROR_LIMIT])
        return
    await drain.mark_processed(event.id)
    logger.info("outbox event %s (%s): %s", event.id, event.event_type, outcome)


def build_outbox_consumer(
    drain: OutboxDrainPort,
    handlers: Mapping[str, EventHandler],
    *,
    batch_size: int,
    max_attempts: int,
    telemetry: TelemetryPort,
    clock: UtcClock,
) -> Callable[[], Awaitable[None]]:
    """Return a consumer that dispatches at most ``batch_size`` events per tick.

    Reports backlog size and the oldest pending event's age every tick, for
    the same ``event_types`` this process actually claims — an event type
    nobody handles here is correctly invisible to both, the same as it is to
    ``claim_batch``.
    """
    event_types = sorted(handlers)

    async def consume() -> None:
        events = await drain.claim_batch(
            event_types=event_types, limit=batch_size, max_attempts=max_attempts
        )
        for event in events:
            await _deliver(event, handlers[event.event_type], drain)

        backlog = await drain.backlog(event_types=event_types, max_attempts=max_attempts)
        telemetry.set_gauge(DW_OUTBOX_BACKLOG_SIZE, backlog.pending, {})
        age_seconds = (
            (clock.now() - backlog.oldest_pending_at).total_seconds()
            if backlog.oldest_pending_at is not None
            else 0.0
        )
        telemetry.set_gauge(DW_OUTBOX_OLDEST_PENDING_AGE_SECONDS, age_seconds, {})

    return consume
