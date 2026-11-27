"""The approval token (ADR 0027 decision 3; ticket 63 check 1): each way a
token fails to prove an approval is refused, by reason."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dw_bravo.approval_token import (
    MAX_TTL,
    ApprovalTokenSigner,
    ApprovalTokenVerifier,
    TokenRefusedError,
    generate_key_pair,
    load_private_key,
    load_public_key,
)
from dw_bravo.contract import BravoTarget, LineRef, SetConfirmedDate, content_hash

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
APPROVAL, TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
COMMAND = SetConfirmedDate(
    line=LineRef(
        so_id=1,
        line_id=2,
        line_rowversion="0x00000000000007D2",
    ),
    confirmed_date=date(2026, 12, 1),
)
KEY = Ed25519PrivateKey.generate()


def _sign(
    key: Ed25519PrivateKey = KEY,
    *,
    kid: str = "k1",
    ttl: timedelta = MAX_TTL,
    target: BravoTarget = "uat",
) -> str:
    return ApprovalTokenSigner(key, kid, ttl).sign(
        approval_id=APPROVAL,
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        command=COMMAND,
        bravo_user_id=2413,
        employee_code="NV001",
        target=target,
        now=NOW,
    )


VERIFIER = ApprovalTokenVerifier({"k1": KEY.public_key()})


def _refused(token: str, *, now: datetime = NOW) -> str:
    with pytest.raises(TokenRefusedError) as refused:
        VERIFIER.verify(token, now=now)
    return refused.value.reason


def test_a_signed_token_carries_what_the_approval_decided() -> None:
    claims = VERIFIER.verify(_sign(), now=NOW + timedelta(minutes=5))

    assert claims.approval_id == APPROVAL
    assert (claims.tenant_id, claims.workspace_id) == (TENANT, WORKSPACE)
    assert claims.kind == "so.line.set_confirmed_date@1"
    assert claims.content_hash == content_hash(COMMAND)
    assert (claims.bravo_user_id, claims.employee_code) == (2413, "NV001")
    assert claims.target == "uat"
    assert VERIFIER.verify(_sign(target="production"), now=NOW).target == "production"


def test_a_payload_changed_after_signing_is_a_bad_signature() -> None:
    body, signature = _sign().split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["bu"] = 1  # another Bravo user
    forged = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    assert _refused(f"{forged.rstrip(b'=').decode()}.{signature}") == "bad_signature"


def test_a_token_signed_with_another_key_under_our_key_id_is_refused() -> None:
    assert _refused(_sign(Ed25519PrivateKey.generate())) == "bad_signature"


def test_an_unknown_key_id_is_refused() -> None:
    assert _refused(_sign(kid="k2")) == "unknown_key"


def test_an_expired_token_is_refused() -> None:
    assert _refused(_sign(ttl=timedelta(minutes=30)), now=NOW + timedelta(minutes=30)) == "expired"


def test_a_token_from_the_future_is_refused() -> None:
    assert _refused(_sign(), now=NOW - timedelta(minutes=5)) == "not_yet_valid"


def test_a_lifetime_past_the_limit_is_refused_even_when_signed() -> None:
    with pytest.raises(ValueError):
        ApprovalTokenSigner(KEY, "k1", MAX_TTL + timedelta(seconds=1))
    signer = ApprovalTokenSigner(KEY, "k1")
    object.__setattr__(signer, "ttl", MAX_TTL + timedelta(hours=1))  # a signer misconfigured

    token = signer.sign(
        approval_id=APPROVAL,
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        command=COMMAND,
        bravo_user_id=2413,
        employee_code="NV001",
        target="uat",
        now=NOW,
    )

    assert _refused(token) == "lifetime_too_long"


@pytest.mark.parametrize("token", ["", "a", "a.b.c", "!!.!!", "e30.AA"], ids=str)
def test_malformed_text_is_refused(token: str) -> None:
    assert _refused(token) in {"malformed", "unknown_key"}


def test_keys_round_trip_through_pem() -> None:
    private_pem, public_pem = generate_key_pair()
    signer_key, verifier_key = load_private_key(private_pem), load_public_key(public_pem)

    token = _sign(signer_key)

    assert ApprovalTokenVerifier({"k1": verifier_key}).verify(token, now=NOW).bravo_user_id == 2413
    with pytest.raises(ValueError):
        load_public_key(private_pem)


def _resigned(change: dict[str, object]) -> str:
    """A token whose payload is changed and signed again with our key: what
    the verifier reads past the signature."""
    body = _sign().split(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload.update(change)
    for name in [k for k, v in change.items() if v is None]:
        del payload[name]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = KEY.sign(b"dw-bravo-approval/1\n" + raw)

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    return f"{b64(raw)}.{b64(signature)}"


@pytest.mark.parametrize(
    "change",
    [{"tgt": None}, {"tgt": "staging"}, {"tgt": ["uat"]}],
    ids=["no_target", "a_target_not_known", "not_a_name"],
)
def test_a_token_without_a_known_target_is_refused(change: dict[str, object]) -> None:
    assert _refused(_resigned(change)) == "malformed"


def test_a_format_1_token_naming_no_target_is_refused() -> None:
    assert _refused(_resigned({"tgt": None, "v": 1})) in {"malformed", "unknown_format"}


def test_the_signer_refuses_a_target_not_known() -> None:
    with pytest.raises(ValueError):
        _sign(target="staging")  # type: ignore[arg-type]
