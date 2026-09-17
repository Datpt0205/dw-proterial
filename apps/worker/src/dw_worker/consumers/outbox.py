"""Outbox dispatcher: turn a committed domain event into the effect it announced.

Per tick: claim a batch of undelivered events of the types this process knows how
to handle, run each one's effect, and mark it delivered. Delivery is at-least-once
- the attempt is counted at claim time and the row is marked afterwards - so every
handler wired here has to be idempotent.

**No effect is wired today, deliberately.** Research-on-account-created and
re-score-on-lead-evidence both used to live here, and both were removed rather
than switched off: an event says what happened, never who caused it, so a
SugarCRM import announced 1,666 created accounts exactly as loudly as a
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

from dw_platform.application.ports import OutboxDrainPort
from dw_platform.domain.outbox import OutboxEvent

logger = logging.getLogger("dw_worker.outbox")

EventHandler = Callable[[OutboxEvent], Awaitable[str]]
"""Deliver one event and say in a few words what it did, for the log."""

_ERROR_LIMIT = 500


class UndeliverableEventError(Exception):
    """The event cannot be delivered as written, and retrying will not help."""


async def _deliver(event: OutboxEvent, handler: EventHandler, drain: OutboxDrainPort) -> None:
    try:
        outcome = await handler(event)
    except UndeliverableEventError as exc:
        # A retry cannot fix the event itself, so the reason is recorded and the
        # attempt budget is left to run out rather than being burned in a loop.
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
) -> Callable[[], Awaitable[None]]:
    """Return a consumer that dispatches at most ``batch_size`` events per tick."""
    event_types = sorted(handlers)

    async def consume() -> None:
        events = await drain.claim_batch(
            event_types=event_types, limit=batch_size, max_attempts=max_attempts
        )
        for event in events:
            await _deliver(event, handlers[event.event_type], drain)

    return consume
