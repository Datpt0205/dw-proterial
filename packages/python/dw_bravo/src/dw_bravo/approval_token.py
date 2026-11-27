"""The approval token: what the Bravo gateway trusts, and nothing else.

ADR 0027 decision 3, ticket 63 check 1. A PIC approves the exact content of
a write on the portal or in the case chat; the approval decision signs a
token carrying the approval id, the tenant and workspace, the write kind, the
content's hash (`dw_bravo.contract.content_hash`), the Bravo user the
decision resolved, the Bravo target the proposal was read from (format 2,
sales ticket 85), and an expiry. The gateway verifies it before anything
else and takes every one of those values from it, never from the request.

Ed25519, not a shared secret: the approval path holds the private key, the
gateway only the public one, so whatever reads the gateway's configuration
can verify a token and cannot mint one. Not a JWT either: the format has one
algorithm and no header to choose another with, so there is no algorithm to
confuse. A key id lets a key be rotated with both keys accepted meanwhile.

    token = base64url(payload) "." base64url(signature)
    signature = Ed25519(_DOMAIN + payload)
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from dw_bravo.contract import BRAVO_TARGETS, WRITE_KINDS, BravoTarget, content_hash

# Signed with the payload, so a signature made for anything else under the
# same key never verifies as an approval.
_DOMAIN: Final = b"dw-bravo-approval/1\n"
# 2 since ticket 85 added the target: a format-1 token, which names none, is
# refused, never read as either Bravo.
FORMAT_VERSION: Final = 2
# The longest an approval may wait for its write. Past it the PIC approves
# again: what they approved may no longer be what Bravo holds.
MAX_TTL: Final = timedelta(hours=2)
DEFAULT_TTL: Final = timedelta(minutes=30)
# Clocks of the signer and the gateway may differ by this much.
CLOCK_SKEW: Final = timedelta(seconds=60)
_CLAIMS: Final = frozenset(
    {"v", "kid", "aid", "tid", "wid", "kind", "hash", "bu", "ec", "tgt", "iat", "exp"}
)


class TokenRefusedError(Exception):
    """The token does not prove an approval of this write; nothing is written."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ApprovalClaims:
    approval_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    kind: str  # `kind@version`, a key of `WRITE_KINDS`
    content_hash: str
    bravo_user_id: int
    employee_code: str
    # The Bravo the proposal was read from: the gateway writes only there.
    target: BravoTarget
    issued_at: datetime
    expires_at: datetime
    key_id: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not text or any(c not in _B64_ALPHABET for c in text):
        raise TokenRefusedError("malformed")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise TokenRefusedError("malformed") from None


_B64_ALPHABET: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def load_private_key(pem: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("the approval signing key must be an Ed25519 private key")
    return key


def load_public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("ascii"))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("the approval verifying key must be an Ed25519 public key")
    return key


@dataclass(frozen=True)
class ApprovalTokenSigner:
    """Held by the approval decision only (ADR 0027 decision 3)."""

    key: Ed25519PrivateKey
    key_id: str
    ttl: timedelta = DEFAULT_TTL

    def __post_init__(self) -> None:
        if not timedelta(0) < self.ttl <= MAX_TTL:
            raise ValueError(f"a token lives more than 0 and at most {MAX_TTL}")

    def sign(
        self,
        *,
        approval_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        command: object,
        bravo_user_id: int,
        employee_code: str,
        target: BravoTarget,
        now: datetime,
    ) -> str:
        kind = f"{type(command).kind}@{type(command).version}"  # type: ignore[attr-defined]
        if kind not in WRITE_KINDS:
            raise ValueError(f"{kind} is not a write the gateway takes")
        if target not in BRAVO_TARGETS:
            raise ValueError(f"{target} is not a Bravo target")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        payload = {
            "v": FORMAT_VERSION,
            "kid": self.key_id,
            "aid": str(approval_id),
            "tid": str(tenant_id),
            "wid": str(workspace_id),
            "kind": kind,
            "hash": content_hash(command),
            "bu": bravo_user_id,
            "ec": employee_code,
            "tgt": target,
            "iat": int(now.timestamp()),
            "exp": int((now + self.ttl).timestamp()),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"{_b64(body)}.{_b64(self.key.sign(_DOMAIN + body))}"


@dataclass(frozen=True)
class ApprovalTokenVerifier:
    """Held by the gateway: public keys by key id, nothing that can sign."""

    keys: Mapping[str, Ed25519PublicKey]

    def verify(self, token: str, *, now: datetime) -> ApprovalClaims:
        parts = token.split(".")
        if len(parts) != 2:
            raise TokenRefusedError("malformed")
        body, signature = _unb64(parts[0]), _unb64(parts[1])
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TokenRefusedError("malformed") from None
        if not isinstance(payload, dict) or set(payload) != _CLAIMS:
            raise TokenRefusedError("malformed")
        key = self.keys.get(payload["kid"]) if isinstance(payload["kid"], str) else None
        if key is None:
            raise TokenRefusedError("unknown_key")
        try:
            key.verify(signature, _DOMAIN + body)
        except InvalidSignature:
            raise TokenRefusedError("bad_signature") from None
        # Signed by our key from here on; still read as data, never trusted
        # to be well formed.
        claims = _claims(payload)
        if claims.expires_at - claims.issued_at > MAX_TTL:
            raise TokenRefusedError("lifetime_too_long")
        if claims.issued_at > now + CLOCK_SKEW:
            raise TokenRefusedError("not_yet_valid")
        if now >= claims.expires_at:
            raise TokenRefusedError("expired")
        return claims


def _claims(payload: Mapping[str, object]) -> ApprovalClaims:
    try:
        iat, exp, bu = payload["iat"], payload["exp"], payload["bu"]
        if payload["v"] != FORMAT_VERSION:
            raise TokenRefusedError("unknown_format")
        if not (type(iat) is int and type(exp) is int and type(bu) is int and bu > 0):
            raise TokenRefusedError("malformed")
        kind, digest, code, target = payload["kind"], payload["hash"], payload["ec"], payload["tgt"]
        if not (isinstance(kind, str) and isinstance(digest, str) and isinstance(code, str)):
            raise TokenRefusedError("malformed")
        if kind not in WRITE_KINDS or len(digest) != 64 or not code:
            raise TokenRefusedError("malformed")
        if target not in BRAVO_TARGETS:
            raise TokenRefusedError("malformed")
        return ApprovalClaims(
            approval_id=uuid.UUID(str(payload["aid"])),
            tenant_id=uuid.UUID(str(payload["tid"])),
            workspace_id=uuid.UUID(str(payload["wid"])),
            kind=kind,
            content_hash=digest,
            bravo_user_id=bu,
            employee_code=code,
            target=target,
            issued_at=datetime.fromtimestamp(iat, UTC),
            expires_at=datetime.fromtimestamp(exp, UTC),
            key_id=str(payload["kid"]),
        )
    except ValueError:
        raise TokenRefusedError("malformed") from None


def generate_key_pair() -> tuple[str, str]:
    """A new key pair as PEM (private, public), for an operator's secret store."""
    private = Ed25519PrivateKey.generate()
    return (
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii"),
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii"),
    )


if __name__ == "__main__":  # pragma: no cover - an operator's one-off
    private_pem, public_pem = generate_key_pair()
    print(private_pem + public_pem, end="")
