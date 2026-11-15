"""Web Push to a member's own devices (Sales ticket 48).

A person turns notifications on from their profile; the browser hands the
portal a subscription (an endpoint at the browser's push service and the two
keys the payload is encrypted to, RFC 8291), and the portal stores it here,
for that person in that workspace. A lane that has something to tell them
(Sales' follow-ups) pushes through `WebPushService.push`.

**A channel behind a port** (`CLAUDE.md`, "Channels are reached through a
port"): `PushSenderPort` is the one thing sent, a payload to a subscription;
`dw_platform.adapters.web_push.PyWebPushSender` is the provider (`pywebpush`,
VAPID-signed, aes128gcm), and a fake stands in for it in tests.

**Only to the push services the deployment names.** An endpoint is a URL the
browser chose, so it is an outbound call the server makes on a member's
word. It is stored, and later called, only when it is ``https`` at a host in
the deployment's outbound allow-list (`DW_API_OUTBOUND_ALLOWED_HOSTS`:
Apple's ``web.push.apple.com``, and the others only when someone uses them),
and it still passes the platform's outbound guard
(`dw_kernel.net_guard.ensure_allowed_outbound_url`) when it is called.

**A person's own.** Subscribing and unsubscribing act on the caller's own
rows only (the table's RLS narrows by tenant, workspace and user, and the
one door in, `platform.save_push_subscription`, reads all three from the
bound session). A lane pushes to a person it chose by the platform's own
`holding` (Sales' `ScopeHoldersPort`); what it reads is that person's rows
in that workspace, never anyone else's.

**Gone is deleted.** A push service answering 404 or 410 says the
subscription no longer exists (the app was removed, permission withdrawn):
the row goes at once. A subscription the browser stops renewing goes after
`platform.prune_push_subscriptions()`'s 90 days.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import ConflictError, DomainError
from dw_kernel.net_guard import OutboundUrlError, ensure_allowed_outbound_url
from dw_platform.application.access_context import AccessContext

logger = logging.getLogger("dw_platform.web_push")

# How long a push service keeps a push for a device that is off: a day, then
# the feed holds it anyway.
PUSH_TTL_SECONDS: Final = 24 * 3600
# A push payload is encrypted into one record; the services take about 4 KB.
_PAYLOAD_LIMIT: Final = 3000
_B64URL = r"^[A-Za-z0-9_-]+={0,2}$"


class PushGoneError(Exception):
    """The push service says the subscription no longer exists (404, 410)."""


class SubscriptionKeys(BaseModel):
    """The browser's `PushSubscription.toJSON().keys`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # A P-256 public point, uncompressed: 65 bytes, 87 characters in base64url.
    p256dh: str = Field(min_length=80, max_length=100, pattern=_B64URL)
    # The 16-byte auth secret: 22 characters in base64url.
    auth: str = Field(min_length=16, max_length=32, pattern=_B64URL)


class SubscriptionIn(BaseModel):
    """What the browser hands the portal when a person turns pushes on."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    endpoint: str = Field(min_length=12, max_length=2048)
    keys: SubscriptionKeys


class EndpointIn(BaseModel):
    """A subscription named by its endpoint, to turn it off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint: str = Field(min_length=12, max_length=2048)


class PushKeyView(BaseModel):
    """Whether pushes are on in this deployment, and the VAPID public key the
    browser subscribes with (`applicationServerKey`)."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    public_key: str | None


@dataclass(frozen=True, slots=True)
class PushSubscription:
    id: uuid.UUID
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True, slots=True)
class PushOutcome:
    """How many of a person's devices took a push, and how many subscriptions
    were gone and so removed."""

    reached: int
    removed: int


class PushSenderPort(Protocol):
    """One encrypted push to one subscription. Raises `PushGoneError` when
    the push service says the subscription is gone; any other failure is the
    provider's own exception."""

    async def send(self, subscription: PushSubscription, payload: bytes, *, ttl: int) -> None: ...


class PushSubscriptionStorePort(Protocol):
    async def save(self, context: AccessContext, *, endpoint: str, p256dh: str, auth: str) -> None:
        """The caller's subscription, kept for them in their workspace; one
        already held for this endpoint (by anyone: the device moved on) is
        replaced."""
        ...

    async def remove(self, context: AccessContext, endpoint: str) -> bool:
        """The caller's own subscription at ``endpoint`` deleted; False when
        they hold none there."""
        ...

    async def of_member(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[PushSubscription]:
        """``user_id``'s subscriptions in that workspace, and nobody else's."""
        ...

    async def drop(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> None:
        """One of ``user_id``'s subscriptions removed (the service said gone)."""
        ...


def push_endpoint_allowed(endpoint: str, allowed_hosts: frozenset[str]) -> bool:
    """Whether the server may call ``endpoint``: ``https`` on the default
    port, at a host the deployment allow-lists, with no credentials, and
    passing the platform's outbound guard."""
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:  # an unbalanced IPv6 bracket, a port that is not one
        return False
    if (
        parts.scheme != "https"
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
        or (parts.hostname or "") not in allowed_hosts
    ):
        return False
    try:
        ensure_allowed_outbound_url(endpoint, allowed_hosts=tuple(sorted(allowed_hosts)))
    except OutboundUrlError:
        return False
    return True


@dataclass(frozen=True)
class WebPushService:
    store: PushSubscriptionStorePort
    # None where the deployment has no VAPID key: pushes are off, the
    # profile says so, and nothing is stored or sent.
    sender: PushSenderPort | None
    public_key: str | None
    allowed_hosts: frozenset[str]

    def key(self) -> PushKeyView:
        on = self.sender is not None and self.public_key is not None
        return PushKeyView(enabled=on, public_key=self.public_key if on else None)

    async def subscribe(self, context: AccessContext, subscription: SubscriptionIn) -> None:
        if self.sender is None or self.public_key is None:
            raise ConflictError(
                "thông báo đẩy chưa được bật trên máy chủ này",
                details={"reason": "web_push_off"},
            )
        if not push_endpoint_allowed(subscription.endpoint, self.allowed_hosts):
            raise DomainError(
                "dịch vụ thông báo của trình duyệt này chưa được cho phép",
                details={"reason": "push_host_not_allowed"},
            )
        await self.store.save(
            context,
            endpoint=subscription.endpoint,
            p256dh=subscription.keys.p256dh,
            auth=subscription.keys.auth,
        )

    async def unsubscribe(self, context: AccessContext, endpoint: str) -> None:
        # Nothing held there is already the state asked for.
        await self.store.remove(context, endpoint)

    async def push(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        person: uuid.UUID,
        payload: Mapping[str, object],
    ) -> PushOutcome:
        """``payload`` to each of ``person``'s devices in the workspace. A
        device whose service fails is skipped (the feed holds the item);
        one whose service says gone is removed."""
        if self.sender is None:
            return PushOutcome(0, 0)
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        if len(data) > _PAYLOAD_LIMIT:
            raise ValueError("a push payload is a few words, not a document")
        reached = removed = 0
        for subscription in await self.store.of_member(tenant_id, workspace_id, person):
            if not push_endpoint_allowed(subscription.endpoint, self.allowed_hosts):
                # Its host was allowed once and is not now: not called.
                continue
            try:
                await self.sender.send(subscription, data, ttl=PUSH_TTL_SECONDS)
            except PushGoneError:
                await self.store.drop(tenant_id, workspace_id, person, subscription.id)
                removed += 1
                continue
            except Exception:
                # Logged without the endpoint, which is a capability URL.
                logger.exception("web push: a device's push service refused or failed")
                continue
            reached += 1
        return PushOutcome(reached, removed)
