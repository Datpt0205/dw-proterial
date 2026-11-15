"""Web Push (Sales ticket 48): which endpoints the server may call, a push
reaching one person's devices alone, a gone subscription removed, and the
`pywebpush` sender run against a local endpoint playing the push service."""

from __future__ import annotations

import base64
import json
import os
import threading
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import http_ece
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from dw_kernel.errors import ConflictError, DomainError
from dw_platform.adapters.web_push import (
    PushServiceError,
    PyWebPushSender,
    new_vapid_private_key,
    vapid_public_key,
    web_push_sender,
)
from dw_platform.application.access_context import AccessContext
from dw_platform.application.web_push import (
    PushGoneError,
    PushSubscription,
    SubscriptionIn,
    WebPushService,
    push_endpoint_allowed,
)

pytestmark = pytest.mark.unit

APPLE = "web.push.apple.com"
HOSTS = frozenset({APPLE})
T_A, T_B = uuid.UUID(int=0xA), uuid.UUID(int=0xB)
W_A, W_B = uuid.UUID(int=0xA1), uuid.UUID(int=0xB1)
AN, BINH = uuid.UUID(int=1), uuid.UUID(int=2)
KEYS = {"p256dh": "B" + "A" * 86, "auth": "A" * 22}


def _context(tenant: uuid.UUID, workspace: uuid.UUID, user: uuid.UUID) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=workspace,
        principal_id=user,
        roles=frozenset(),
        plan_id="business",
    )


def _sub(n: int, host: str = APPLE) -> PushSubscription:
    return PushSubscription(uuid.UUID(int=n), f"https://{host}/3/device/{n}", KEYS["p256dh"], "a")


@dataclass
class Store:
    """`PushSubscriptionStorePort` keyed as the table's RLS keys it."""

    held: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], list[PushSubscription]] = field(
        default_factory=dict
    )
    saved: list[tuple[AccessContext, str]] = field(default_factory=list)

    async def save(self, context: AccessContext, *, endpoint: str, p256dh: str, auth: str) -> None:
        self.saved.append((context, endpoint))

    async def remove(self, context: AccessContext, endpoint: str) -> bool:
        raise NotImplementedError("not exercised by these tests")

    async def of_member(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Sequence[PushSubscription]:
        return list(self.held.get((tenant_id, workspace_id, user_id), []))

    async def drop(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> None:
        key = (tenant_id, workspace_id, user_id)
        self.held[key] = [s for s in self.held.get(key, []) if s.id != subscription_id]


@dataclass
class Sender:
    sent: list[tuple[str, bytes]] = field(default_factory=list)
    gone: frozenset[str] = frozenset()
    broken: frozenset[str] = frozenset()

    async def send(self, subscription: PushSubscription, payload: bytes, *, ttl: int) -> None:
        if subscription.endpoint in self.gone:
            raise PushGoneError("410")
        if subscription.endpoint in self.broken:
            raise PushServiceError("500")
        self.sent.append((subscription.endpoint, payload))


def _service(store: Store, sender: Sender | None) -> WebPushService:
    return WebPushService(store, sender, "PUBLIC" if sender else None, HOSTS)


# ------------------------------------------------------------- endpoints --


@pytest.mark.parametrize(
    ("endpoint", "allowed"),
    [
        (f"https://{APPLE}/3/device/abc", True),
        (f"https://{APPLE}:443/3/device/abc", True),
        (f"http://{APPLE}/3/device/abc", False),
        (f"https://{APPLE}:8443/3/device/abc", False),
        (f"https://user:pw@{APPLE}/3/device/abc", False),
        ("https://fcm.googleapis.com/fcm/send/abc", False),
        ("https://127.0.0.1/push", False),
        (f"https://{APPLE}.evil.example/x", False),
        ("https://[::1", False),
    ],
)
def test_only_an_allow_listed_push_service_is_called(endpoint: str, allowed: bool) -> None:
    assert push_endpoint_allowed(endpoint, HOSTS) is allowed


async def test_a_subscription_at_an_unlisted_host_is_refused() -> None:
    store = Store()
    body = SubscriptionIn.model_validate({"endpoint": "https://push.example.net/x", "keys": KEYS})
    with pytest.raises(DomainError):
        await _service(store, Sender()).subscribe(_context(T_A, W_A, AN), body)
    assert store.saved == []


async def test_nothing_is_stored_while_pushes_are_off() -> None:
    store = Store()
    body = SubscriptionIn.model_validate({"endpoint": f"https://{APPLE}/3/device/x", "keys": KEYS})
    service = _service(store, None)
    assert service.key().enabled is False and service.key().public_key is None
    with pytest.raises(ConflictError):
        await service.subscribe(_context(T_A, W_A, AN), body)
    assert store.saved == []


# ------------------------------------------------------------------ push --


async def test_a_push_reaches_that_persons_devices_and_nobody_elses() -> None:
    """Acceptance 3: An's two devices in tenant A; Bình's in the same
    workspace and An's own in another tenant receive nothing."""
    store = Store(
        held={
            (T_A, W_A, AN): [_sub(1), _sub(2)],
            (T_A, W_A, BINH): [_sub(3)],
            (T_B, W_B, AN): [_sub(4)],
            (T_A, W_B, AN): [_sub(5)],
        }
    )
    sender = Sender()
    outcome = await _service(store, sender).push(T_A, W_A, AN, {"title": "Đến lượt bạn"})
    assert outcome.reached == 2 and outcome.removed == 0
    assert [endpoint for endpoint, _ in sender.sent] == [_sub(1).endpoint, _sub(2).endpoint]
    assert json.loads(sender.sent[0][1]) == {"title": "Đến lượt bạn"}


async def test_a_gone_subscription_is_removed_and_a_failing_one_kept() -> None:
    store = Store(held={(T_A, W_A, AN): [_sub(1), _sub(2), _sub(3)]})
    sender = Sender(gone=frozenset({_sub(1).endpoint}), broken=frozenset({_sub(2).endpoint}))
    outcome = await _service(store, sender).push(T_A, W_A, AN, {"title": "x"})
    assert (outcome.reached, outcome.removed) == (1, 1)
    assert [s.id for s in store.held[(T_A, W_A, AN)]] == [_sub(2).id, _sub(3).id]


async def test_a_host_no_longer_listed_is_not_called() -> None:
    store = Store(held={(T_A, W_A, AN): [_sub(1, host="push.example.net")]})
    sender = Sender()
    assert (await _service(store, sender).push(T_A, W_A, AN, {"t": 1})).reached == 0
    assert sender.sent == []


async def test_a_payload_is_a_few_words_not_a_document() -> None:
    store = Store(held={(T_A, W_A, AN): [_sub(1)]})
    with pytest.raises(ValueError):
        await _service(store, Sender()).push(T_A, W_A, AN, {"body": "x" * 4000})


# ------------------------------------------------- the sender, measured --


class _Recorder(BaseHTTPRequestHandler):
    seen: ClassVar[list[tuple[str, dict[str, str], bytes]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        code = 410 if self.path.endswith("gone") else 500 if self.path.endswith("down") else 201
        self.send_response(code)
        self.end_headers()

    def log_message(self, *_: object) -> None:
        return None


@pytest.fixture
def push_service() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


async def test_the_sender_encrypts_to_the_device_and_signs_with_vapid(push_service: str) -> None:
    """Run, not assumed (failure-modes #4): the record decrypts with the
    device's key to the payload (RFC 8291 aes128gcm), and the VAPID token
    names the subject and the push service."""
    device = ec.generate_private_key(ec.SECP256R1())
    public = device.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = os.urandom(16)
    key = new_vapid_private_key()
    sender = PyWebPushSender(key, "mailto:ops@example.invalid")
    subscription = PushSubscription(
        uuid.uuid4(), f"{push_service}/push/device", _b64(public), _b64(auth)
    )
    payload = json.dumps({"title": "Đến lượt bạn"}, ensure_ascii=False).encode()
    await sender.send(subscription, payload, ttl=3600)
    _, headers, body = _Recorder.seen[-1]
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["ttl"] == "3600"
    clear = http_ece.decrypt(body, private_key=device, auth_secret=auth, version="aes128gcm")
    assert clear == payload
    token = headers["authorization"].split("t=")[1].split(",")[0]
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert claims["sub"] == "mailto:ops@example.invalid"
    assert claims["aud"] == push_service
    assert vapid_public_key(key) in headers["authorization"]

    with pytest.raises(PushGoneError):
        await sender.send(
            PushSubscription(uuid.uuid4(), f"{push_service}/push/gone", _b64(public), _b64(auth)),
            payload,
            ttl=60,
        )
    with pytest.raises(PushServiceError) as failed:
        await sender.send(
            PushSubscription(uuid.uuid4(), f"{push_service}/push/down", _b64(public), _b64(auth)),
            payload,
            ttl=60,
        )
    assert "push/down" not in str(failed.value)


# --------------------------------------------------------- the settings --


def test_a_deployed_profile_with_pushes_on_refuses_to_start_without_a_key() -> None:
    with pytest.raises(RuntimeError, match="DW_WEB_PUSH_VAPID_PRIVATE_KEY"):
        web_push_sender(enabled=True, private_key="", subject="mailto:a@b.c", deployed=True)
    with pytest.raises(RuntimeError, match="DW_WEB_PUSH_SUBJECT"):
        web_push_sender(
            enabled=True, private_key=new_vapid_private_key(), subject="", deployed=True
        )
    # Local runs without pushes; off is off anywhere.
    assert web_push_sender(enabled=True, private_key="", subject="", deployed=False) is None
    assert web_push_sender(enabled=False, private_key="", subject="", deployed=True) is None


def test_a_key_that_does_not_load_is_refused_without_being_printed() -> None:
    with pytest.raises(RuntimeError) as refused:
        web_push_sender(
            enabled=True, private_key="not-a-key-at-all", subject="mailto:a@b.c", deployed=False
        )
    assert "not-a-key-at-all" not in str(refused.value)
    with pytest.raises(ValueError, match="subject"):
        PyWebPushSender(new_vapid_private_key(), "ops@example.invalid")
