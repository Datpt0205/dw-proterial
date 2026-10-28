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


def test_sign_in_and_password_pages_speak_vietnamese(realm: dict[str, object]) -> None:
    # Keycloak 26.7.2 ships messages_vi for the login and account themes
    # (checked in its themes jar, 2026-10-26): the realm only has to ask.
    assert realm["internationalizationEnabled"] is True
    assert realm["defaultLocale"] == "vi"
    # Vietnamese only: with a second locale the login page grows a language
    # switch, which Đạt asked to remove (2026-10-26).
    assert realm["supportedLocales"] == ["vi"]


# The customer's IT signs in to Keycloak's admin console for three things the
# portal does not do: unlock a brute-force lockout, sign a person out of every
# device, ask a person to set up OTP. Membership of `dw-it` gives the console's
# Users and Groups and nothing else (measured on 26.7.2, 2026-10-28: realm
# settings, clients, authentication and identity providers answer 403, and a
# member cannot map a realm-management role to anyone, themselves included).
# The realm is shared by every tenant a deployment serves, so the group is for
# a deployment that serves one customer (on premises): in a shared one a member
# would manage every tenant's logins.
IT_GROUP_ROLES = {"view-users", "manage-users", "query-users", "query-groups"}


def test_the_it_group_manages_logins_and_nothing_else(realm: dict[str, object]) -> None:
    groups = {g["name"]: g for g in realm["groups"]}  # type: ignore[attr-defined]
    it = groups["dw-it"]
    assert set(it.get("clientRoles", {})) == {"realm-management"}
    assert set(it["clientRoles"]["realm-management"]) == IT_GROUP_ROLES
    assert not it.get("realmRoles")
