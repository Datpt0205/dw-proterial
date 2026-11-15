"""`PushSenderPort` through `pywebpush` (pinned at 2.5.0), and the VAPID
key's derivations.

Measured before it was depended on (failure-modes #4; 2026-11-15, against a
local endpoint playing the push service): `webpush_async` posts one
``aes128gcm`` record (RFC 8291) that the subscriber's private key decrypts
to the payload, signs it with ``Authorization: vapid t=..., k=...`` whose JWT
carries the ``sub`` given and an ``aud`` it fills from the endpoint, sends
the ``TTL`` header, and raises `WebPushException` whose ``status_code`` is
410 when the service answers 410. A raw 32-byte private key in base64url (43
characters) is accepted as the key.

The VAPID private key comes from the deployment's secrets only
(`DW_WEB_PUSH_VAPID_PRIVATE_KEY`); the public key the browser subscribes with
is derived from it here, so the two cannot disagree.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02, b64urlencode
from pywebpush import WebPushException, webpush_async

from dw_platform.application.web_push import PushGoneError, PushSubscription

logger = logging.getLogger("dw_platform.web_push")

# Apple refuses a VAPID token that lives longer than a day; twelve hours
# keeps clear of every service's bound.
_TOKEN_LIFETIME_SECONDS: Final = 12 * 3600
_GONE: Final = frozenset({404, 410})


class PushServiceError(Exception):
    """A push service refused or failed, for a reason other than gone. Its
    message names the status only: the endpoint is a capability URL."""


def vapid_public_key(private_key: str) -> str:
    """The base64url uncompressed P-256 point the browser subscribes with,
    from the private key. Raises ValueError on a key that is not one."""
    vapid = Vapid02.from_string(private_key=private_key)
    point = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return str(b64urlencode(point))


def new_vapid_private_key() -> str:
    """A fresh raw private key in base64url, for a local `.env` only."""
    vapid = Vapid02()
    vapid.generate_keys()
    raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    return str(b64urlencode(raw))


@dataclass(frozen=True)
class PyWebPushSender:
    private_key: str
    # Who runs the deployment, as the push services ask: ``mailto:`` or an
    # ``https:`` URL. Apple refuses a token without one.
    subject: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        vapid_public_key(self.private_key)  # a key that does not load fails here
        if not self.subject.startswith(("mailto:", "https://")):
            raise ValueError("the VAPID subject is a mailto: or https: URL")

    async def send(self, subscription: PushSubscription, payload: bytes, *, ttl: int) -> None:
        try:
            await webpush_async(
                {
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                payload.decode(),
                vapid_private_key=self.private_key,
                vapid_claims={
                    "sub": self.subject,
                    "exp": int(time.time()) + _TOKEN_LIFETIME_SECONDS,
                },
                ttl=ttl,
                timeout=self.timeout_seconds,
                # Shown at once on a phone that is asleep (RFC 8030 5.3).
                headers={"Urgency": "high"},
            )
        except WebPushException as exc:
            status = exc.status_code
            if status in _GONE:
                raise PushGoneError(f"push service answered {status}") from None
            raise PushServiceError(f"push service answered {status}") from None


def web_push_sender(
    *, enabled: bool, private_key: str, subject: str, deployed: bool
) -> PyWebPushSender | None:
    """The sender a deployment's settings describe, or None where pushes are
    off. On with no key or no subject: a deployed profile refuses to start
    (a switch that is on and does nothing would read as a safeguard,
    failure-modes #1); a local one runs without pushes (`scripts/dev.sh`
    writes a key into `.env` when none is there). A key that does not load
    is refused everywhere."""
    if not enabled:
        return None
    if not private_key or not subject:
        if deployed:
            raise RuntimeError(
                "DW_WEB_PUSH_ENABLED needs DW_WEB_PUSH_VAPID_PRIVATE_KEY and "
                "DW_WEB_PUSH_SUBJECT in a deployed profile"
            )
        logger.warning("web push is on but has no VAPID key or subject: pushes are off")
        return None
    try:
        return PyWebPushSender(private_key, subject)
    except ValueError as exc:
        # The key itself is never in the message.
        raise RuntimeError(f"DW_WEB_PUSH settings do not load: {type(exc).__name__}") from None
