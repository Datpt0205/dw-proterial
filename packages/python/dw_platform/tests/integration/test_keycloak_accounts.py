"""`KeycloakLoginAccounts` against a real Keycloak.

The realm is built from `infra/keycloak/dw-realm.json` itself (its
`dw-accounts` client and service account, its user profile, its password
policy), so what runs here is what a fresh deployment imports. A throwaway
realm per module, deleted afterwards.

Reached at ``DW_TEST_KEYCLOAK`` (base URL, e.g. ``http://127.0.0.1:8686``) with
the bootstrap admin in ``KEYCLOAK_ADMIN`` / ``KEYCLOAK_ADMIN_PASSWORD``. CI
sets it, and there the suite fails rather than skips without it.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, NotFoundError
from dw_platform.adapters.identity.keycloak_accounts import TENANT_ATTRIBUTE, KeycloakLoginAccounts

pytestmark = pytest.mark.integration

REALM_FILE = Path(__file__).resolve().parents[5] / "infra" / "keycloak" / "dw-realm.json"
LOGIN_CLIENT = "accounts-test-login"
TENANT_A, TENANT_B = uuid.uuid4(), uuid.uuid4()


@dataclass(frozen=True)
class Realm:
    base: str
    name: str
    secret: str
    admin: httpx.Client

    def accounts(self, secret: str | None = None) -> KeycloakLoginAccounts:
        return KeycloakLoginAccounts(
            base_url=self.base,
            realm=self.name,
            client_id="dw-accounts",
            client_secret=secret or self.secret,
        )

    def sign_in(self, email: str, password: str) -> httpx.Response:
        return httpx.post(
            f"{self.base}/realms/{self.name}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": LOGIN_CLIENT,
                "username": email,
                "password": password,
            },
        )

    def user(self, email: str) -> dict[str, Any]:
        found = self.admin.get(
            f"/admin/realms/{self.name}/users",
            params={"email": email, "exact": "true", "briefRepresentation": "false"},
        ).json()
        assert len(found) == 1, found
        return dict(found[0])


def _realm_from_the_file(name: str, secret: str) -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    realm["realm"] = name
    for client in realm["clients"]:
        if client.get("secret") == "${DW_ACCOUNTS_CLIENT_SECRET}":
            client["secret"] = secret
    # The service account only: the fixed-id sample users exist once per
    # Keycloak, not once per realm.
    realm["users"] = [u for u in realm["users"] if u.get("serviceAccountClientId")]
    # Test scaffolding: a client that signs in by password, to watch what the
    # person meets (temporary password, locked account).
    realm["clients"].append(
        {
            "clientId": LOGIN_CLIENT,
            "publicClient": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": True,
        }
    )
    return realm


@pytest.fixture(scope="module")
def realm() -> Iterator[Realm]:
    base = os.environ.get("DW_TEST_KEYCLOAK", "").rstrip("/")
    if not base:
        if os.environ.get("CI"):
            pytest.fail("DW_TEST_KEYCLOAK is not set: CI runs Keycloak for this suite")
        pytest.skip("DW_TEST_KEYCLOAK is not set")
    try:
        token = httpx.post(
            f"{base}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": os.environ["KEYCLOAK_ADMIN"],
                "password": os.environ["KEYCLOAK_ADMIN_PASSWORD"],
            },
        )
    except httpx.HTTPError as exc:
        pytest.fail(f"Keycloak unreachable at {base!r}: {exc}")
    token.raise_for_status()
    admin = httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        timeout=60,
    )
    name, secret = f"accounts-{uuid.uuid4().hex[:8]}", secrets.token_urlsafe(32)
    created = admin.post("/admin/realms", json=_realm_from_the_file(name, secret))
    assert created.status_code == 201, created.text
    try:
        yield Realm(base=base, name=name, secret=secret, admin=admin)
    finally:
        admin.delete(f"/admin/realms/{name}")
        admin.close()


def _email() -> str:
    return f"p-{uuid.uuid4().hex[:8]}@example.test"


async def test_an_account_starts_with_a_password_the_person_must_change(realm: Realm) -> None:
    email = _email()
    await realm.accounts().create(
        tenant_id=TENANT_A,
        email=email,
        display_name="Phạm Thị Lan",
        temporary_password="Abcd-Efgh-Jkm2",
    )
    stored = realm.user(email)
    assert stored["attributes"][TENANT_ATTRIBUTE] == [str(TENANT_A)]
    assert stored["emailVerified"] is True
    assert (stored["firstName"], stored["lastName"]) == ("Lan", "Phạm Thị")
    assert stored["requiredActions"] == ["UPDATE_PASSWORD"]
    assert realm.sign_in(email, "Abcd-Efgh-Jkm2").json()["error_description"] == (
        "Account is not fully set up"
    )
    listed = await realm.accounts().list(tenant_id=TENANT_A)
    assert {(a.email, a.enabled) for a in listed} >= {(email, True)}


async def test_another_tenant_reaches_nothing(realm: Realm) -> None:
    email = _email()
    accounts = realm.accounts()
    await accounts.create(
        tenant_id=TENANT_A,
        email=email,
        display_name="Trần Văn Bình",
        temporary_password="Abcd-Efgh-Jkm3",
    )
    with pytest.raises(NotFoundError):
        await accounts.set_temporary_password(
            tenant_id=TENANT_B, email=email, temporary_password="Wxyz-Wxyz-Wxy4"
        )
    with pytest.raises(NotFoundError):
        await accounts.set_enabled(tenant_id=TENANT_B, email=email, enabled=False)
    with pytest.raises(NotFoundError):
        await accounts.delete(tenant_id=TENANT_B, email=email)
    assert email not in {a.email for a in await accounts.list(tenant_id=TENANT_B)}
    stored = realm.user(email)
    assert stored["enabled"] is True
    assert realm.sign_in(email, "Abcd-Efgh-Jkm3").json()["error_description"] == (
        "Account is not fully set up"
    )


async def test_an_account_dw_did_not_create_is_out_of_reach(realm: Realm) -> None:
    # An operator's, or one IT made in the console: no tenant attribute.
    email = _email()
    made = realm.admin.post(
        f"/admin/realms/{realm.name}/users",
        json={
            "username": email,
            "email": email,
            "enabled": True,
            "firstName": "A",
            "lastName": "B",
        },
    )
    assert made.status_code == 201
    with pytest.raises(NotFoundError):
        await realm.accounts().set_temporary_password(
            tenant_id=TENANT_A, email=email, temporary_password="Wxyz-Wxyz-Wxy5"
        )


async def test_locking_refuses_sign_in_and_unlocking_restores_it(realm: Realm) -> None:
    email, accounts = _email(), realm.accounts()
    await accounts.create(
        tenant_id=TENANT_A, email=email, display_name="Lê Chi", temporary_password="Abcd-Efgh-Jkm6"
    )
    await accounts.set_enabled(tenant_id=TENANT_A, email=email, enabled=False)
    assert realm.sign_in(email, "Abcd-Efgh-Jkm6").json()["error_description"] == "Account disabled"
    stored = realm.user(email)
    assert stored["attributes"][TENANT_ATTRIBUTE] == [str(TENANT_A)]  # a partial PUT kept it
    assert (email, False) in {(a.email, a.enabled) for a in await accounts.list(tenant_id=TENANT_A)}
    await accounts.set_enabled(tenant_id=TENANT_A, email=email, enabled=True)
    assert realm.sign_in(email, "Abcd-Efgh-Jkm6").json()["error_description"] == (
        "Account is not fully set up"
    )


async def test_a_reset_replaces_the_password(realm: Realm) -> None:
    email, accounts = _email(), realm.accounts()
    await accounts.create(
        tenant_id=TENANT_A, email=email, display_name="Ngô Tâm", temporary_password="Abcd-Efgh-Jkm7"
    )
    await accounts.set_temporary_password(
        tenant_id=TENANT_A, email=email, temporary_password="Pqrs-Tuvw-Xyz8"
    )
    # One wrong try only: two inside a second trip the realm's quick-login
    # check, which then answers "Invalid user credentials" for a minute.
    assert realm.sign_in(email, "Abcd-Efgh-Jkm7").json()["error_description"] == (
        "Invalid user credentials"
    )
    assert realm.sign_in(email, "Pqrs-Tuvw-Xyz8").json()["error_description"] == (
        "Account is not fully set up"
    )


async def test_the_realm_policy_still_refuses_a_short_password(realm: Realm) -> None:
    email, accounts = _email(), realm.accounts()
    await accounts.create(
        tenant_id=TENANT_A, email=email, display_name="Đỗ Hà", temporary_password="Abcd-Efgh-Jkm9"
    )
    with pytest.raises(DomainError) as caught:
        await accounts.set_temporary_password(
            tenant_id=TENANT_A, email=email, temporary_password="short"
        )
    assert caught.value.details["reason_code"] == "login_account_refused"


async def test_a_second_account_for_an_email_is_a_conflict(realm: Realm) -> None:
    email, accounts = _email(), realm.accounts()
    await accounts.create(
        tenant_id=TENANT_A, email=email, display_name="Vũ Minh", temporary_password="Abcd-Efgh-Jkma"
    )
    with pytest.raises(ConflictError) as caught:
        await accounts.create(
            tenant_id=TENANT_B,
            email=email,
            display_name="Vũ Minh",
            temporary_password="Abcd-Efgh-Jkmb",
        )
    assert caught.value.details["reason_code"] == "login_account_exists"
    assert realm.user(email)["attributes"][TENANT_ATTRIBUTE] == [str(TENANT_A)]


async def test_the_person_cannot_change_their_tenant_or_their_email(realm: Realm) -> None:
    # The tenant attribute is what every call checks, and the email is what a
    # first sign-in links by: neither may be the person's own to edit.
    email = _email()
    await realm.accounts().create(
        tenant_id=TENANT_A, email=email, display_name="Hồ Nam", temporary_password="Abcd-Efgh-Jkmc"
    )
    user_id = realm.user(email)["id"]
    realm.admin.put(
        f"/admin/realms/{realm.name}/users/{user_id}/reset-password",
        json={"type": "password", "value": "Perm-Anent-Pw9x", "temporary": False},
    ).raise_for_status()
    token = realm.sign_in(email, "Perm-Anent-Pw9x").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    account = f"{realm.base}/realms/{realm.name}/account/"
    mine = httpx.get(account, headers=headers).json()
    mine["attributes"] = {**(mine.get("attributes") or {}), TENANT_ATTRIBUTE: [str(TENANT_B)]}
    mine["email"] = "someone-else@example.test"
    httpx.post(account, headers=headers, json=mine)
    stored = realm.user(email)
    assert stored["attributes"][TENANT_ATTRIBUTE] == [str(TENANT_A)]
    assert stored["email"] == email
    assert stored["emailVerified"] is True


async def test_a_wrong_secret_is_an_infrastructure_error(realm: Realm) -> None:
    with pytest.raises(InfrastructureError):
        await realm.accounts(secret="not-the-secret").list(tenant_id=TENANT_A)
