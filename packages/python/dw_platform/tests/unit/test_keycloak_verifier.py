"""``KeycloakTokenVerifier`` against a locally generated RS256 key and JWKS.

The realm is replaced by a key pair made here and a JWK Set served from
``PyJWKClient.fetch_data``, so everything after the HTTP fetch is the real code:
kid matching, signature, algorithm, issuer, audience, expiry and the required
claims. Each refusal is a check a regression could drop, which is why each has
its own token rather than one "bad token" case.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm

from dw_kernel.errors import UnauthenticatedError
from dw_platform.adapters.identity.keycloak import KeycloakTokenVerifier, auth_methods

pytestmark = pytest.mark.unit

ISSUER = "https://sso.example.test/realms/dw"
AUDIENCE = "dw-api"
KID = "realm-key-1"

REALM_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(*keys: tuple[str, rsa.RSAPrivateKey]) -> dict[str, Any]:
    entries = []
    for kid, key in keys:
        jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
        entries.append({**jwk, "kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": entries}


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve the realm's JWK Set; record which URL the client asked for."""
    uris: list[str] = []

    def fetch_data(self: PyJWKClient) -> Any:
        uris.append(self.uri)
        return _jwks((KID, REALM_KEY))

    monkeypatch.setattr(PyJWKClient, "fetch_data", fetch_data)
    return uris


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "kc|an.nguyen",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "email": "an@alpha.local",
        "name": "An Nguyen",
        "amr": ["pwd", "otp"],
        "acr": "2",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _token(
    claims: dict[str, Any],
    *,
    key: rsa.RSAPrivateKey = REALM_KEY,
    algorithm: str = "RS256",
    kid: str = KID,
) -> str:
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid})


def _b64(part: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()


def _verifier() -> KeycloakTokenVerifier:
    return KeycloakTokenVerifier(ISSUER, AUDIENCE)


async def _refused(token: str) -> str:
    with pytest.raises(UnauthenticatedError) as caught:
        await _verifier().verify(token)
    return str(caught.value.details["reason"])


async def test_valid_token_yields_verified_claims(fetched: list[str]) -> None:
    claims = await _verifier().verify(_token(_claims()))

    assert claims.subject == "kc|an.nguyen"
    assert claims.issuer == ISSUER
    assert claims.email == "an@alpha.local"
    assert claims.name == "An Nguyen"
    assert claims.auth_methods == frozenset({"pwd", "otp"})
    assert claims.acr == "2"
    assert fetched == [f"{ISSUER}/protocol/openid-connect/certs"]


async def test_name_falls_back_to_preferred_username(fetched: list[str]) -> None:
    claims = await _verifier().verify(
        _token(_claims(name=None, preferred_username="an.nguyen", acr=None))
    )
    assert claims.name == "an.nguyen"
    assert claims.acr is None


async def test_jwks_url_override_is_what_the_client_fetches(fetched: list[str]) -> None:
    verifier = KeycloakTokenVerifier(
        ISSUER + "/", AUDIENCE, jwks_url="http://keycloak:8080/realms/dw/certs"
    )
    claims = await verifier.verify(_token(_claims()))
    # The trailing slash is not part of the issuer the token is checked against.
    assert claims.issuer == ISSUER
    assert fetched == ["http://keycloak:8080/realms/dw/certs"]


async def test_signature_from_another_key_refused(fetched: list[str]) -> None:
    # Same kid, different private key: only the signature check can tell.
    assert await _refused(_token(_claims(), key=OTHER_KEY)) == "InvalidSignatureError"


async def test_unknown_kid_refused(fetched: list[str]) -> None:
    assert await _refused(_token(_claims(), kid="not-in-the-realm")) == "PyJWKClientError"


async def test_algorithm_other_than_rs256_refused(fetched: list[str]) -> None:
    # A valid signature by the realm key, but under an algorithm the verifier
    # does not accept: the allow-list, not the key, is what refuses it.
    assert await _refused(_token(_claims(), algorithm="RS512")) == "InvalidAlgorithmError"


async def test_hs256_signed_with_the_public_key_refused(fetched: list[str]) -> None:
    # The algorithm-confusion attack: HMAC keyed with the realm's public PEM.
    # Built by hand, as an attacker would: pyjwt itself refuses to sign it.
    public_pem = REALM_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = _b64({"alg": "HS256", "typ": "JWT", "kid": KID})
    payload = _b64(_claims())
    signature = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    token = f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    assert await _refused(token) == "InvalidAlgorithmError"


async def test_wrong_issuer_refused(fetched: list[str]) -> None:
    token = _token(_claims(iss="https://sso.example.test/realms/other"))
    assert await _refused(token) == "InvalidIssuerError"


async def test_wrong_audience_refused(fetched: list[str]) -> None:
    assert await _refused(_token(_claims(aud="another-client"))) == "InvalidAudienceError"


async def test_expired_token_refused(fetched: list[str]) -> None:
    now = int(time.time())
    token = _token(_claims(iat=now - 600, exp=now - 60))
    assert await _refused(token) == "ExpiredSignatureError"


@pytest.mark.parametrize("claim", ["exp", "iss", "sub"])
async def test_missing_required_claim_refused(fetched: list[str], claim: str) -> None:
    assert await _refused(_token(_claims(**{claim: None}))) == "MissingRequiredClaimError"


async def test_garbage_is_unauthenticated_not_a_crash(fetched: list[str]) -> None:
    assert await _refused("not.a.jwt") == "DecodeError"


def test_issuer_must_be_http() -> None:
    with pytest.raises(ValueError, match="http"):
        KeycloakTokenVerifier("sso.example.test/realms/dw")


@pytest.mark.parametrize(
    ("amr", "expected"),
    [
        (["pwd", "otp"], frozenset({"pwd", "otp"})),
        (["pwd", 7, None], frozenset({"pwd"})),
        ("otp", frozenset()),
        ({"otp": True}, frozenset()),
        (None, frozenset()),
    ],
)
def test_auth_methods_reads_only_a_list_of_strings(amr: object, expected: frozenset[str]) -> None:
    # A string is iterable: read as one, "otp" would claim o, t and p.
    assert auth_methods(amr) == expected


async def test_amr_that_is_not_a_list_grants_no_method(fetched: list[str]) -> None:
    claims = await _verifier().verify(_token(_claims(amr="otp")))
    assert claims.auth_methods == frozenset()
