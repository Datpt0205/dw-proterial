"""Sales ticket 53: the key Bravo write approvals are signed with. Unset, no
write can be approved (the stamp refuses); set to anything but an Ed25519
private key, the API does not start."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from dw_api.settings import ApiSettings
from dw_bravo.approval_token import generate_key_pair

pytestmark = pytest.mark.unit


def test_no_key_signs_nothing() -> None:
    assert (
        ApiSettings(profile="test", bravo_approval_signing_key=SecretStr("")).bravo_signer() is None
    )


def test_a_key_from_an_env_file_with_escaped_newlines_signs() -> None:
    private, _ = generate_key_pair()
    escaped = private.strip().replace("\n", "\n")

    signer = ApiSettings(
        profile="test", bravo_approval_signing_key=SecretStr(escaped), bravo_approval_key_id="k2"
    ).bravo_signer()

    assert signer is not None and signer.key_id == "k2"


@pytest.mark.parametrize(
    "pem", ["not a key", "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"]
)
def test_a_key_that_is_not_one_stops_the_start(pem: str) -> None:
    settings = ApiSettings(profile="test", bravo_approval_signing_key=SecretStr(pem))

    with pytest.raises(RuntimeError, match="DW_BRAVO_APPROVAL_SIGNING_KEY"):
        settings.validate_for_profile()
