"""The demo roster's Purchasing roles are what DW2's persona seed gives, and
every persona is a seeded member of its tenant: the roster is a sign-in
convenience, the seeds own who holds what."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dw_platform.testing import seed_env
from dw_purchasing.testing.seed_personas import PERSONAS, PURCHASING_KEY_PREFIX

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ROSTER: list[dict[str, Any]] = yaml.safe_load(
    (REPO / "configs" / "demo" / "demo_users.yaml").read_text(encoding="utf-8")
)["users"]


def test_the_roster_shows_each_member_s_purchasing_roles_as_seeded() -> None:
    seeded = {p.subject: sorted(p.roles) for p in PERSONAS}
    shown = {
        e["subject"]: sorted(r for r in e["roles"] if r.startswith(PURCHASING_KEY_PREFIX))
        for e in ROSTER
    }
    assert {s: r for s, r in shown.items() if r} == {s: r for s, r in seeded.items() if r}


def test_every_persona_is_a_seeded_member_of_its_tenant() -> None:
    members = {(subject, slug) for subject, _e, _n, slug, _r, _d in seed_env.USERS}
    assert [p.subject for p in PERSONAS if (p.subject, p.tenant_slug) not in members] == []
