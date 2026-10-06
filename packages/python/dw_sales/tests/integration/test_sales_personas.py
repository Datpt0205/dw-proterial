"""Each demo persona, signed in, holds the scopes the spec's actor table lists
(ticket 11).

Signing in is `SqlMembershipLookup.find_access` as `dw_app`, the call that
builds every request's access context. The expected scopes below are the
spec's table ("Actors, roles and scopes"), written out on purpose: the
catalogue rows come from the sales migration, and a test that read its
expectation from them would agree with any mistake in them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from pg_test_db import DatabaseUrls
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.application.identity import MembershipAccess
from dw_platform.testing.seed_env import seed_test_env, sid
from dw_sales.testing.seed_personas import Persona, seed_sales_personas

pytestmark = pytest.mark.integration

ISSUER = "https://issuer.test/realms/dw"
ALPHA, BETA = "tenant-alpha", "tenant-beta"
_RULE = "sod_sales_price_vs_member_admin"
REPO = Path(__file__).resolve().parents[5]

PIC = frozenset(
    {
        "sales.overview.read",
        "sales.case.read",
        "sales.price.read",
        "sales.inbox.process",
        "sales.order.prepare",
        "sales.order.cross_check",
        "sales.quote.prepare",
        "sales.worker.pause",
    }
)
HEAD = PIC | {"sales.price.other_customers.read", "sales.quote.approve", "sales.worker.resume"}
# (subject, tenant) -> the `sales.*` scopes the spec's actor table gives them.
SPEC: dict[tuple[str, str], frozenset[str]] = {
    ("dev|an.nguyen", ALPHA): PIC | {"sales.compliance.ack"},
    ("dev|dieu.hoang", ALPHA): PIC | {"sales.price.other_customers.read"},
    ("dev|giang.do", ALPHA): HEAD,
    ("dev|khoa.lam", ALPHA): PIC | {"sales.quote.approve"},
    ("dev|ha.vu", ALPHA): frozenset({"sales.overview.read"}),
    ("dev|tam.ngo", ALPHA): frozenset(),
    ("dev|binh.tran", ALPHA): frozenset(),
    ("dev|chi.le", ALPHA): frozenset(),
    ("dev|bao.pham", BETA): PIC,
}

type SignedIn = dict[tuple[str, str], MembershipAccess]


def _sales(scopes: frozenset[str]) -> frozenset[str]:
    return frozenset(scope for scope in scopes if scope.startswith("sales."))


async def _sign_in(
    sessions: async_sessionmaker[AsyncSession], subject: str, tenant: str
) -> MembershipAccess | None:
    return await SqlMembershipLookup(sessions).find_access(
        subject, ISSUER, sid("tenant", tenant), sid("workspace", f"{tenant}:main")
    )


async def _sign_in_all(sessions: async_sessionmaker[AsyncSession]) -> SignedIn:
    signed_in = {}
    for subject, tenant in SPEC:
        access = await _sign_in(sessions, subject, tenant)
        assert access is not None, f"{subject} cannot sign in to {tenant}"
        signed_in[subject, tenant] = access
    return signed_in


@pytest.fixture
async def platform_only(
    sales_db: DatabaseUrls, app_sessions: async_sessionmaker[AsyncSession]
) -> SignedIn:
    """Every persona after the platform seed alone."""
    await seed_test_env(sales_db.migrator)
    return await _sign_in_all(app_sessions)


@pytest.fixture
async def personas(
    platform_only: SignedIn,
    sales_db: DatabaseUrls,
    app_sessions: async_sessionmaker[AsyncSession],
) -> SignedIn:
    """Every persona after the platform seed and then the Sales one."""
    await seed_sales_personas(sales_db.migrator)
    return await _sign_in_all(app_sessions)


@pytest.mark.parametrize(("subject", "tenant"), list(SPEC))
async def test_each_persona_holds_the_spec_scopes_and_nothing_else_changes(
    platform_only: SignedIn, personas: SignedIn, subject: str, tenant: str
) -> None:
    access = personas[subject, tenant]
    assert _sales(access.scopes) == SPEC[subject, tenant]
    # What the platform seed gave (Diệu's approver_boost included) is all
    # still there. The one platform scope the Sales roles add is
    # `approvals.decide` (ac31ff0f2087: the platform asks every decider for it
    # besides the request's stamp), and only to someone who decides a Sales
    # request.
    before = platform_only[subject, tenant].scopes - _sales(platform_only[subject, tenant].scopes)
    after = access.scopes - _sales(access.scopes)
    decides_sales = bool(_sales(access.scopes) & {"sales.order.cross_check", "sales.quote.approve"})
    assert before <= after
    assert after - before <= ({"approvals.decide"} if decides_sales else set())


async def test_the_quote_pic_cannot_approve_whatever_approver_boost_gives_her(
    personas: SignedIn,
) -> None:
    """Spec walk-through: "Diệu approves her own quote: 403". The platform's
    approver_boost stays on her membership and decides platform approvals; it
    grants no Sales approval, hers or anyone's."""
    dieu = personas["dev|dieu.hoang", ALPHA]
    assert "approvals.decide" in dieu.scopes
    assert "sales.quote.approve" not in dieu.scopes
    approvers = {
        subject
        for (subject, _), access in personas.items()
        if "sales.quote.approve" in access.scopes
    }
    assert approvers == {"dev|giang.do", "dev|khoa.lam"}


async def test_it_administers_members_and_holds_no_sales_scope(personas: SignedIn) -> None:
    tam = personas["dev|tam.ngo", ALPHA]
    assert "platform.members.write" in tam.scopes
    assert _sales(tam.scopes) == frozenset()


async def test_the_other_tenants_pic_is_no_member_of_alpha(
    personas: SignedIn, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    assert await _sign_in(app_sessions, "dev|bao.pham", ALPHA) is None


async def test_each_persona_signs_in_with_the_roles_the_roster_shows(
    personas: SignedIn,
) -> None:
    roster = yaml.safe_load(
        (REPO / "configs" / "demo" / "demo_users.yaml").read_text(encoding="utf-8")
    )["users"]
    shown = {entry["subject"]: frozenset(entry["roles"]) for entry in roster}
    signed_in = {subject: access.roles for (subject, _), access in personas.items()}
    assert signed_in == {subject: shown[subject] for subject in signed_in}


async def test_no_walk_through_step_needs_platform_admin(
    personas: SignedIn, migrator: AsyncEngine
) -> None:
    """Every Sales scope the catalogue declares is held by some persona who is
    not a platform admin, so each step can be shown without one."""
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT scopes FROM platform.roles"
                " UNION ALL SELECT scopes FROM platform.permission_sets"
            )
        )
        declared = frozenset(s for (scopes,) in rows for s in scopes if s.startswith("sales."))
    held = frozenset(
        scope
        for access in personas.values()
        if "platform_admin" not in access.roles
        for scope in _sales(access.scopes)
    )
    assert declared
    assert held == declared
    assert not [
        s for (s, _), a in personas.items() if "platform_admin" in a.roles and _sales(a.scopes)
    ]


async def test_reseeding_writes_nothing(personas: SignedIn, sales_db: DatabaseUrls) -> None:
    assert await seed_sales_personas(sales_db.migrator) == 0


async def test_the_full_seed_rerun_leaves_every_persona_as_it_was(
    personas: SignedIn,
    sales_db: DatabaseUrls,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_test_env(sales_db.migrator)
    await seed_sales_personas(sales_db.migrator)
    assert await _sign_in_all(app_sessions) == personas


async def test_the_seed_cannot_give_it_a_price_scope(
    personas: SignedIn,
    sales_db: DatabaseUrls,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The separation-of-duty trigger judges the seed's own writes."""
    with pytest.raises(IntegrityError) as refused:
        await seed_sales_personas(
            sales_db.migrator, [Persona("dev|tam.ngo", ALPHA, ("sales_pic",))]
        )
    cause = getattr(refused.value.orig, "__cause__", None)
    assert getattr(cause, "constraint_name", None) == _RULE
    assert await _sign_in(app_sessions, "dev|tam.ngo", ALPHA) == personas["dev|tam.ngo", ALPHA]


async def test_a_persona_without_a_membership_fails_loudly(
    platform_only: SignedIn, sales_db: DatabaseUrls
) -> None:
    with pytest.raises(LookupError, match="run the platform seed first"):
        await seed_sales_personas(
            sales_db.migrator, [Persona("dev|bao.pham", ALPHA, ("sales_pic",))]
        )
