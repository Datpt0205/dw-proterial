"""Give an existing realm what sign-in accounts need, from dw-realm.json.

Usage (reads `.env`; in a plain shell run `set -a; source .env; set +a` first):
    uv run python scripts/keycloak_accounts_client.py

Keycloak imports `infra/keycloak/dw-realm.json` once, when the realm is first
created; a realm that already existed has no `dw-accounts` client, and the
members screen then says "chưa bật tạo tài khoản đăng nhập". This applies the
three pieces from the file itself, so the file stays their one owner:

- the `dw-accounts` client, with its secret from
  `DW_API_ACCOUNTS_CLIENT_SECRET` (the value compose hands the API);
- its service account's `realm-management` roles;
- the realm's user profile (only an admin writes `dw_tenant_id` or an email);
- the realm's languages (Vietnamese first), so the first sign-in and the
  password pages a new person meets read in Vietnamese.

Idempotent: a second run updates the secret and re-applies the rest. Prints
what it did, never a secret.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

REALM_FILE = Path(__file__).resolve().parents[1] / "infra" / "keycloak" / "dw-realm.json"
CLIENT_ID = "dw-accounts"
LANGUAGE_KEYS = ("internationalizationEnabled", "supportedLocales", "defaultLocale")
PROFILE_PROVIDER = "org.keycloak.userprofile.UserProfileProvider"


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set (source .env)")
    return value


def main() -> None:
    base = (os.environ.get("DW_API_ACCOUNTS_ADMIN_URL") or _env("NEXT_PUBLIC_KEYCLOAK_URL")).rstrip(
        "/"
    )
    realm = os.environ.get("DW_API_ACCOUNTS_REALM") or _env("NEXT_PUBLIC_KEYCLOAK_REALM")
    secret = _env("DW_API_ACCOUNTS_CLIENT_SECRET")
    if len(secret) < 32:
        sys.exit("DW_API_ACCOUNTS_CLIENT_SECRET must be at least 32 characters")
    spec: dict[str, Any] = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    client_spec = next(c for c in spec["clients"] if c["clientId"] == CLIENT_ID)
    roles = next(
        u["clientRoles"]["realm-management"]
        for u in spec["users"]
        if u.get("serviceAccountClientId") == CLIENT_ID
    )
    profile = spec["components"][PROFILE_PROVIDER][0]["config"]["kc.user.profile.config"][0]

    with httpx.Client(base_url=base, timeout=30) as http:
        token = http.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": _env("KEYCLOAK_ADMIN"),
                "password": _env("KEYCLOAK_ADMIN_PASSWORD"),
            },
        )
        token.raise_for_status()
        http.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
        admin = f"/admin/realms/{realm}"

        body = {**client_spec, "secret": secret}
        found = http.get(f"{admin}/clients", params={"clientId": CLIENT_ID})
        found.raise_for_status()
        if found.json():
            client_uuid = found.json()[0]["id"]
            http.put(f"{admin}/clients/{client_uuid}", json=body).raise_for_status()
            print(f"{CLIENT_ID}: updated")
        else:
            http.post(f"{admin}/clients", json=body).raise_for_status()
            client_uuid = http.get(f"{admin}/clients", params={"clientId": CLIENT_ID}).json()[0][
                "id"
            ]
            print(f"{CLIENT_ID}: created")

        account = http.get(f"{admin}/clients/{client_uuid}/service-account-user")
        account.raise_for_status()
        management = http.get(f"{admin}/clients", params={"clientId": "realm-management"})
        management.raise_for_status()
        management_uuid = management.json()[0]["id"]
        wanted = [
            http.get(f"{admin}/clients/{management_uuid}/roles/{name}").json() for name in roles
        ]
        http.post(
            f"{admin}/users/{account.json()['id']}/role-mappings/clients/{management_uuid}",
            json=wanted,
        ).raise_for_status()
        print(f"{CLIENT_ID}: service account holds {', '.join(roles)}")

        http.put(f"{admin}/users/profile", json=json.loads(profile)).raise_for_status()
        print("user profile: only an admin writes dw_tenant_id or an email")

        http.put(admin, json={key: spec[key] for key in LANGUAGE_KEYS}).raise_for_status()
        print(f"languages: {', '.join(spec['supportedLocales'])}, default {spec['defaultLocale']}")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
