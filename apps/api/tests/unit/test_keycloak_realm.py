"""The realm a fresh deployment imports (infra/keycloak/dw-realm.json).

The host overlay counts on Keycloak's brute-force detection, and the API
verifies an access token by its signature alone: a person locked out or
signed out keeps whatever token they hold until it expires. So the realm
ships with lockout on, a password floor, and a short access token the web
refreshes (`updateToken`), while the sign-in (the refresh token, which the
session banner reads) lasts a working day.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REALM = Path(__file__).resolve().parents[4] / "infra" / "keycloak" / "dw-realm.json"


@pytest.fixture(scope="module")
def realm() -> dict[str, object]:
    return json.loads(REALM.read_text(encoding="utf-8"))


def test_repeated_wrong_passwords_lock_the_account(realm: dict[str, object]) -> None:
    assert realm["bruteForceProtected"] is True
    assert 0 < int(str(realm["failureFactor"])) <= 10


def test_an_access_token_outlives_a_sign_out_by_minutes_not_a_shift(
    realm: dict[str, object],
) -> None:
    assert int(str(realm["accessTokenLifespan"])) <= 900
    # The sign-in itself still covers a shift.
    assert int(str(realm["ssoSessionIdleTimeout"])) >= 8 * 3600


def test_a_password_has_a_floor(realm: dict[str, object]) -> None:
    assert "length(10)" in str(realm["passwordPolicy"])
