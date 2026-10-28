"""Give every seeded dev user a Keycloak login, for a local browser run.

Usage (reads `.env`; in a plain shell run `set -a; source .env; set +a` first):
    uv run python scripts/keycloak_dev_users.py

For each user in the dev database that has an email, it creates the Keycloak
account in the app's realm if there is none with that email, then sets it
enabled, email-verified, and gives it the password in `DW_DEV_USER_PASSWORD`
(from `.env`, never committed). A user who belongs to one tenant gets that
tenant's `dw_tenant_id`, as an account made from Thành viên → Thêm người does,
so the demo's IT can reset and lock it there; a user of several tenants gets
none (the members page then refuses, as it would anyone else's account).
The app links a Keycloak identity to the seeded user by email
(`identity_provisioning.py`), so a login lands on that user with the roles the
seed gave it.

The users are read from the database, not listed here: the seed owns who
exists; this only makes them able to sign in. Refuses outside the `local`
profile.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.adapters.identity.keycloak_accounts import TENANT_ATTRIBUTE


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set (source .env)")
    return value


async def _seeded_users(database_url: str) -> list[tuple[str, str, str | None]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT u.email, u.display_name,"
                        " (SELECT CASE WHEN count(DISTINCT m.tenant_id) = 1"
                        "  THEN min(m.tenant_id::text) END"
                        "  FROM platform.memberships m WHERE m.user_id = u.id) AS tenant_id"
                        " FROM platform.users u WHERE u.email IS NOT NULL ORDER BY u.email"
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    return [(row.email, row.display_name, row.tenant_id) for row in rows]


def _names(display_name: str) -> dict[str, str]:
    # Vietnamese order: family name first, given name last.
    *family, given = display_name.split()
    return {"firstName": given, "lastName": " ".join(family) or given}


def main() -> None:
    if os.environ.get("DW_API_PROFILE", "local") != "local":
        sys.exit("refusing: dev accounts with a shared password are for the local profile only")
    base = _env("NEXT_PUBLIC_KEYCLOAK_URL").rstrip("/")
    realm = _env("NEXT_PUBLIC_KEYCLOAK_REALM")
    password = _env("DW_DEV_USER_PASSWORD")
    users = asyncio.run(_seeded_users(_env("DW_DATABASE_URL")))
    if not users:
        sys.exit("no seeded users; seed the dev database first")

    with httpx.Client(base_url=base, timeout=30) as client:
        token = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": _env("KEYCLOAK_ADMIN"),
                "password": _env("KEYCLOAK_ADMIN_PASSWORD"),
            },
        )
        token.raise_for_status()
        client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
        admin = f"/admin/realms/{realm}/users"

        for email, display_name, tenant_id in users:
            found = client.get(admin, params={"email": email, "exact": "true"})
            found.raise_for_status()
            # A PUT replaces the whole attribute map: keep what is there.
            attributes = dict(found.json()[0].get("attributes") or {}) if found.json() else {}
            attributes.pop(TENANT_ATTRIBUTE, None)
            if tenant_id:
                attributes[TENANT_ATTRIBUTE] = [tenant_id]
            profile = {
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "attributes": attributes,
                **_names(display_name),
            }
            if found.json():
                user_id = found.json()[0]["id"]
                client.put(f"{admin}/{user_id}", json=profile).raise_for_status()
                action = "updated"
            else:
                created = client.post(admin, json={"username": email.split("@", 1)[0], **profile})
                created.raise_for_status()
                user_id = created.headers["Location"].rsplit("/", 1)[-1]
                action = "created"
            client.put(
                f"{admin}/{user_id}/reset-password",
                json={"type": "password", "value": password, "temporary": False},
            ).raise_for_status()
            print(f"{email}: {action}, password set")

        _it_group(client, realm, asyncio.run(_org_admins(_env("DW_DATABASE_URL"))))


REALM_FILE = Path(__file__).resolve().parents[1] / "infra" / "keycloak" / "dw-realm.json"
IT_GROUP = "dw-it"


async def _org_admins(database_url: str) -> list[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                sa.text(
                    "SELECT DISTINCT u.email FROM platform.users u"
                    " JOIN platform.memberships m ON m.user_id = u.id"
                    " WHERE m.role_keys ? 'org_admin' AND u.email IS NOT NULL"
                )
            )
            return [row.email for row in rows]
    finally:
        await engine.dispose()


def _it_group(client: httpx.Client, realm: str, emails: list[str]) -> None:
    """The customer's IT group, as the realm file defines it, on a realm imported
    before it existed (an import never updates a realm), with the dev org
    admins in it: signed in to the admin console they see Users and nothing else."""
    spec = next(
        g
        for g in json.loads(REALM_FILE.read_text(encoding="utf-8"))["groups"]
        if g["name"] == IT_GROUP
    )
    admin = f"/admin/realms/{realm}"
    found = client.get(f"{admin}/groups", params={"search": IT_GROUP, "exact": "true"})
    found.raise_for_status()
    if found.json():
        group_id = found.json()[0]["id"]
    else:
        client.post(
            f"{admin}/groups", json={"name": IT_GROUP, "description": spec["description"]}
        ).raise_for_status()
        group_id = client.get(
            f"{admin}/groups", params={"search": IT_GROUP, "exact": "true"}
        ).json()[0]["id"]
    for client_id, role_names in spec["clientRoles"].items():
        owner = client.get(f"{admin}/clients", params={"clientId": client_id}).json()[0]["id"]
        roles = [client.get(f"{admin}/clients/{owner}/roles/{n}").json() for n in role_names]
        client.post(
            f"{admin}/groups/{group_id}/role-mappings/clients/{owner}", json=roles
        ).raise_for_status()
    for email in emails:
        user = client.get(f"{admin}/users", params={"email": email, "exact": "true"}).json()
        if user:
            client.put(f"{admin}/users/{user[0]['id']}/groups/{group_id}").raise_for_status()
            print(f"{email}: in {IT_GROUP}")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
