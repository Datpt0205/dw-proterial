"""Web push delivery: in-app notifications out to the devices a person turned
push on from (Sales ticket 78; ADR 0006-provider-neutral-channel-delivery-outbox).

``platform.deliver_notification`` queues a ``web_push`` row in
``platform.channel_deliveries`` for every recipient holding a push
subscription in the workspace (migration 19a366484422), in the transaction
that addresses the notification. This lane sends them, claiming one row at a
time exactly as the chat lane does (`channel_delivery`), the row locked while
it is sent:

1. the recipient must still belong to the workspace, or the row is
   ``cancelled`` (``recipient_not_member``);
2. the push goes to each of their devices in that workspace
   (`WebPushService.push`): a device whose service says gone is removed there;
3. no device took it (none left, or every one failed): ``failed``
   (``no_device_reached``), the inbox still holds the item;
4. the push service itself raised: one attempt more after a delay that
   doubles, ``failed`` (``attempts_exhausted``) at ``MAX_ATTEMPTS``;
5. one device or more took it: ``sent``.

What leaves is the notification's title, the place it happened and its link,
under one tag, so several pushes replace each other on the lock screen rather
than pile up (`apps/web/public/sw.js`); never its body.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Final, Protocol

from dw_observability.metrics import DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL
from dw_observability.telemetry import TelemetryPort
from dw_worker.consumers.channel_delivery import (
    BATCH_PER_SCOPE,
    EXHAUSTED,
    MAX_ATTEMPTS,
    ChannelOutboxPort,
    ClaimedDelivery,
    DeliveryScopeRef,
    backoff,
)
from dw_worker.consumers.scope_failures import raise_if_failed

logger = logging.getLogger("dw_worker.web_push_delivery")

CHANNEL: Final = "web_push"
# One tag for every inbox push: the newest replaces the one before it.
TAG: Final = "dw-inbox"


class PushResultRef(Protocol):
    @property
    def reached(self) -> int: ...


class PushPort(Protocol):
    """`dw_platform.application.web_push.WebPushService.push`."""

    async def push(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        person: uuid.UUID,
        payload: Mapping[str, object],
    ) -> PushResultRef: ...


def payload(claim: ClaimedDelivery) -> dict[str, object]:
    """The five fields the service worker reads (`sw.js`), nothing else."""
    return {
        "title": claim.title,
        "body": f"{claim.tenant_name} · {claim.workspace_name}",
        "url": claim.link or "/",
        "count": 1,
        "tag": TAG,
    }


async def _deliver(claim: ClaimedDelivery, scope: DeliveryScopeRef, push: PushPort) -> str | None:
    """Settles the row; answers the reason when it ended ``failed``."""
    if not await claim.recipient_may_receive():
        await claim.mark_cancelled("recipient_not_member")
        return None
    try:
        result = await push.push(
            scope.tenant_id, scope.workspace_id, claim.recipient_user_id, payload(claim)
        )
    except Exception as exc:
        made = claim.attempts + 1
        error = type(exc).__name__  # an endpoint is a capability URL: never logged
        if made >= MAX_ATTEMPTS:
            await claim.mark_failed(EXHAUSTED, error)
            return EXHAUSTED
        await claim.retry_later(error, backoff(made))
        return None
    if result.reached == 0:
        await claim.mark_failed("no_device_reached", "no device took the push")
        return "no_device_reached"
    await claim.mark_sent(CHANNEL, CHANNEL)
    return None


def build_web_push_delivery_consumer(
    outbox: ChannelOutboxPort,
    push: PushPort,
    *,
    telemetry: TelemetryPort,
    batch_per_scope: int = BATCH_PER_SCOPE,
) -> Callable[[], Awaitable[None]]:
    exhausted = {"channel": CHANNEL}
    telemetry.add_metric(DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL, 0, exhausted)

    async def consume() -> None:
        failed = 0
        for scope in await outbox.due_scopes(CHANNEL):
            try:
                for _ in range(batch_per_scope):
                    async with outbox.claim_next(CHANNEL, scope) as claim:
                        if claim is None:
                            break
                        reason = await _deliver(claim, scope, push)
                    # After the block: only a settlement that committed counts.
                    if reason == EXHAUSTED:
                        telemetry.add_metric(DW_CHANNEL_DELIVERY_EXHAUSTED_TOTAL, 1, exhausted)
            except Exception:
                logger.exception("web push delivery: a scope failed; the next tick retries")
                failed += 1
        raise_if_failed("web_push_delivery", failed)

    return consume
