"""The demo roster (`configs/demo/demo_users.yaml`) is what the seeds create
(ticket 11).

The roster is a sign-in convenience the dev router reads; the seeds own who
exists and what they hold: platform rows in `dw_platform.testing.seed_env`,
the Sales keys in `dw_sales.testing.seed_personas`. Each answer here is
derived from those two tables, never restated, so a roster that drifts from
them fails.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.testing import seed_env
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.application.ports import SalesScope
from dw_sales.testing.seed_personas import PERSONAS, SALES_KEY_PREFIX, Persona

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ROSTER: list[dict[str, Any]] = yaml.safe_load(
    (REPO / "configs" / "demo" / "demo_users.yaml").read_text(encoding="utf-8")
)["users"]
SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))


@dataclass(frozen=True)
class Seeded:
    """One seeded member, as both seeds leave their membership."""

    email: str
    display_name: str
    tenant_slug: str
    roles: list[str]
    permission_sets: list[str]


def _seeded() -> dict[str, Seeded]:
    sets = {(s, slug): keys for s, keys, slug in seed_env.PERMISSION_SET_ASSIGNMENTS}
    personas = {persona.subject: persona for persona in PERSONAS}
    seeded = {}
    for subject, email, name, slug, roles, _department in seed_env.USERS:
        permission_sets = sets.get((subject, slug), [])
        persona = personas.get(subject)
        if persona is not None:
            roles, permission_sets = persona.keys_on(roles, permission_sets)
        seeded[subject] = Seeded(email, name, slug, list(roles), list(permission_sets))
    return seeded


SEEDED = _seeded()
TENANT_NAMES = {tenant["slug"]: tenant["name"] for tenant in seed_env.TENANTS}


def test_every_roster_user_is_seeded_with_the_same_name_roles_and_tenant() -> None:
    drift: list[tuple[str, object]] = []
    for entry in ROSTER:
        seeded = SEEDED.get(entry["subject"])
        if seeded is None:
            drift.append((entry["subject"], "not seeded"))
            continue
        expected = {
            "display_name": seeded.display_name,
            "roles": sorted(seeded.roles),
            "tenant_id": str(seed_env.sid("tenant", seeded.tenant_slug)),
            "tenant_name": TENANT_NAMES[seeded.tenant_slug],
            "workspace_id": str(seed_env.sid("workspace", f"{seeded.tenant_slug}:main")),
        }
        actual = {
            **{key: str(entry[key]) for key in expected if key != "roles"},
            "roles": sorted(entry["roles"]),
        }
        if actual != expected:
            drift.append((entry["subject"], {"roster": actual, "seed": expected}))
    assert drift == []


def test_the_roster_names_each_subject_once() -> None:
    subjects = [entry["subject"] for entry in ROSTER]
    assert len(subjects) == len(set(subjects))


def test_every_persona_is_a_seeded_member_of_its_tenant_and_on_the_roster() -> None:
    on_roster = {entry["subject"] for entry in ROSTER}
    misplaced = [
        persona.subject
        for persona in PERSONAS
        if persona.subject not in SEEDED
        or SEEDED[persona.subject].tenant_slug != persona.tenant_slug
        or persona.subject not in on_roster
    ]
    assert misplaced == []


def test_a_persona_sets_only_the_keys_this_context_owns() -> None:
    foreign = {
        persona.subject: key
        for persona in PERSONAS
        for key in (*persona.roles, *persona.permission_sets)
        if not key.startswith(SALES_KEY_PREFIX)
    }
    assert foreign == {}


def test_applying_a_persona_keeps_platform_keys_and_replaces_its_own() -> None:
    """Diệu keeps the platform's `approver_boost`; a Sales key nobody listed
    for her (handed out by hand) is gone after the seed."""
    persona = Persona("dev|x", "tenant-alpha", ("sales_pic",), ("sales_price_evidence",))
    assert persona.keys_on(["member", "sales_head"], ["approver_boost"]) == (
        ["member", "sales_pic"],
        ["approver_boost", "sales_price_evidence"],
    )
    assert Persona("dev|y", "tenant-alpha").keys_on(["org_admin", "sales_pic"], []) == (
        ["org_admin"],
        [],
    )


def test_no_one_holding_a_sales_key_is_a_platform_admin() -> None:
    """A walk-through as platform_admin passes every check, so it would hide
    the ones that are missing (spec, "Actors, roles and scopes")."""
    both = [
        subject
        for subject, seeded in SEEDED.items()
        if "platform_admin" in seeded.roles
        and any(k.startswith(SALES_KEY_PREFIX) for k in (*seeded.roles, *seeded.permission_sets))
    ]
    assert both == []


async def test_every_customers_sales_pic_is_a_seeded_sales_pic() -> None:
    """A case's `assigned_to` is the customer's PIC, so it must resolve to a
    persona who can work the case (ticket 04)."""
    customers = (await MockSalesCatalog.load(SCOPE).customers(SCOPE)).data
    pics = {c.sales_pic for c in customers if c.sales_pic is not None}
    sales_pics = {
        seeded.email
        for seeded in SEEDED.values()
        if seeded.tenant_slug == "tenant-alpha" and "sales_pic" in seeded.roles
    }
    assert pics
    assert pics <= sales_pics
