"""FPT support reads Sales cases, never a price (ticket 22, G20).

dw_sales ADR 0003 §5 on the platform's customer-granted support access
(ADR 0024), end to end with a real grant: the head grants Sales' set on
`/api/v1/support/grants`, the operators list a staff member and assign the
grant (`ProvisioningService`, over the migrator standing in for the
provisioner role), and the staff member signs in with a second factor and
names the grant in `X-DW-Support-Grant`.

- Only the head can issue it: a PIC, the viewer and a member without Sales
  scopes are refused, and tenant IT can only file a request it cannot approve.
- The five reads answer, with every amount marked hidden by the mapper that
  hides it from any caller without `sales.price.read`; the same walk as a PIC
  does find prices, so the search can fail.
- Every other Sales route refuses the support context: each mutation, the
  source view, the evidence and the downloads.
- Each read is on the customer's audit trail, under the grant's id.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BINH, GIANG, HA, SECRET, TAM, Api, Persona, user_id
from sales_flow import order_of
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_sales_api_access import _PARAMS, _sales_routes
from test_sales_api_prices import _decided_world, leaks

from dw_api.dependencies.auth import SUPPORT_GRANT_HEADER
from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.adapters.persistence.provisioning_repo import SqlProvisioningRepository
from dw_platform.application.provisioning import ProvisioningContext, ProvisioningService
from dw_platform.testing.seed_env import sid
from dw_sales.application.access import SUPPORT_SCOPE_SET_KEY

pytestmark = pytest.mark.integration

ALPHA = sid("tenant", "tenant-alpha")
OPERATOR = "dev|chi.le"  # the platform seed's platform operator
HIDDEN = {"hidden": True}

# The five reads open to support, as the routes print them (the composition
# root's `SUPPORT_ALLOWED_ROUTES`, without the prefix the persona adds).
OPENED = {
    ("GET", "/overview"),
    ("GET", "/orders"),
    ("GET", "/orders/{case_id}"),
    ("GET", "/quotes"),
    ("GET", "/quotes/{case_id}"),
}


@pytest.fixture
async def support_enabled(migrator: AsyncEngine) -> AsyncIterator[None]:
    """`support_access` on the demo tenant (ADR 0024: in no plan, by override)."""
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE platform.entitlements"
                " SET feature_overrides = feature_overrides || '[\"support_access\"]'::jsonb"
                " WHERE tenant_id = :t AND NOT feature_overrides ? 'support_access'"
            ),
            {"t": ALPHA},
        )
    yield
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE platform.entitlements"
                " SET feature_overrides = feature_overrides - 'support_access'"
                " WHERE tenant_id = :t"
            ),
            {"t": ALPHA},
        )


async def _grant(persona: Persona) -> httpx.Response:
    """The Sales support set for the whole workspace, as the customer's
    support page posts it."""
    return await persona.client.post(
        "/api/v1/support/grants",
        json={
            "scope_set_key": SUPPORT_SCOPE_SET_KEY,
            "resource_type": "workspace",
            "reason": "DW1 đọc sai một dòng PO (giả lập)",
            "duration_hours": 24,
        },
        headers=persona.headers(str(uuid.uuid4())),
    )


@dataclass
class Staff:
    """An FPT support staff member working under one grant."""

    client: httpx.AsyncClient
    subject: str
    user_id: uuid.UUID
    grant_id: uuid.UUID

    def headers(self) -> dict[str, str]:
        token = DevTokenVerifier(SECRET).issue(self.subject, amr=["pwd", "otp"])
        return {"Authorization": f"Bearer {token}", SUPPORT_GRANT_HEADER: str(self.grant_id)}

    async def get(self, path: str) -> httpx.Response:
        return await self.client.get(f"/api/v1/sales{path}", headers=self.headers())

    async def call(self, method: str, path: str) -> httpx.Response:
        return await self.client.request(
            method,
            f"/api/v1/sales{path}",
            json={"case_version": 1, "assignee": None},
            headers={**self.headers(), "Idempotency-Key": str(uuid.uuid4())},
        )


@pytest.fixture
async def staff(api: Api, migrator: AsyncEngine, support_enabled: None) -> Staff:
    granted = await _grant(api.as_(GIANG))
    assert granted.status_code == 201, granted.text
    assert granted.json()["status"] == "pending_assignment"
    grant_id = uuid.UUID(granted.json()["id"])

    tag = uuid.uuid4().hex[:10]
    subject, email = f"dev|support.{tag}", f"support.{tag}@support.example"
    async with migrator.begin() as conn:
        staff_id = await conn.scalar(
            sa.text(
                "INSERT INTO platform.users (id, subject, email, display_name)"
                " VALUES (gen_random_uuid(), :s, :e, 'Nhân viên hỗ trợ (giả lập)') RETURNING id"
            ),
            {"s": subject, "e": email},
        )
    operators = ProvisioningService(
        repo=SqlProvisioningRepository(async_sessionmaker(migrator, expire_on_commit=False)),
        clock=SystemClock(),
        ids=Uuid7Generator(),
    )
    operator = ProvisioningContext(principal_id=user_id(OPERATOR))
    await operators.add_support_staff(operator, email=email, note=None)
    await operators.assign_support_request(operator, grant_id=grant_id, staff_user_id=staff_id)
    return Staff(api.client, subject, staff_id, grant_id)


# ------------------------------------------------------ who may grant it --


async def test_only_the_head_can_issue_the_sales_support_set(
    api: Api, support_enabled: None
) -> None:
    for subject in (AN, HA, BINH):
        refused = await _grant(api.as_(subject))
        assert refused.status_code == 403, subject

    # Tenant IT files a request (`support.request`) and cannot approve it.
    tam = api.as_(TAM)
    requested = await _grant(tam)
    assert requested.status_code == 201
    assert requested.json()["status"] == "pending_approval"
    grant_id = requested.json()["id"]
    approve = f"/api/v1/support/grants/{grant_id}/approve"
    by_tam = await api.client.post(approve, headers=tam.headers(str(uuid.uuid4())))
    assert by_tam.status_code == 403

    giang = api.as_(GIANG)
    by_head = await api.client.post(approve, headers=giang.headers(str(uuid.uuid4())))
    assert by_head.status_code == 200
    assert by_head.json()["status"] == "pending_assignment"
    granted = await _grant(giang)
    assert granted.status_code == 201
    assert granted.json()["status"] == "pending_assignment"


# ------------------------------------------------------------ the reads --


async def _reads(persona: Persona | Staff, world: dict[str, Any]) -> list[httpx.Response]:
    m04, m10 = world["m04"], world["m10"]
    return [
        await persona.get(path)
        for path in (
            "/overview",
            "/orders",
            f"/orders/{m04['case_id']}",
            "/quotes",
            f"/quotes/{m10['case_id']}",
        )
    ]


async def test_support_reads_the_overview_and_the_cases_without_a_price(
    api: Api, staff: Staff
) -> None:
    world = await _decided_world(api)

    answers = await _reads(staff, world)

    assert [r.status_code for r in answers] == [200] * 5, [r.text for r in answers]
    assert [found for r in answers if (found := leaks(r.json()))] == []
    quote = answers[4].json()
    # The price evidence is not even gathered for a caller without
    # `sales.price.read`; each priced line's amount is marked hidden by the
    # mapper, never zero and never left out.
    assert quote["evidence"] is None
    assert {line["unit_price"] == HIDDEN for line in quote["pricing"]["lines"]} == {True}
    # The same reads as the PIC who may see prices do find them.
    assert any(leaks(r.json()) for r in await _reads(api.as_(AN), world))


async def _every_case(persona: Persona | Staff) -> list[Any]:
    """The two lists and the detail of every case in them."""
    bodies: list[Any] = []
    for kind in ("orders", "quotes"):
        listed = await persona.get(f"/{kind}")
        assert listed.status_code == 200, listed.text
        bodies.append(listed.json())
        for row in listed.json():
            detail = await persona.get(f"/{kind}/{row['case_id']}")
            assert detail.status_code == 200, detail.text
            bodies.append(detail.json())
    return bodies


async def test_every_case_the_inbox_opens_reads_without_a_price(api: Api, staff: Staff) -> None:
    """Support is the first caller holding `sales.case.read` without
    `sales.price.read` (no persona holds that pair), so the mapper's rule is
    walked over every case the mock inbox opens, not only the two decided."""
    await _decided_world(api)
    processed = await api.as_(AN).post("/inbox/process-all")
    assert processed.status_code == 200, processed.text

    bodies = await _every_case(staff)

    assert len(bodies) >= 20  # both lists and the cases in them were read
    assert [found for body in bodies if (found := leaks(body))] == []
    assert any(leaks(body) for body in await _every_case(api.as_(AN)))


async def test_every_other_sales_route_refuses_support(api: Api, staff: Staff) -> None:
    """Each mutation, the source view, the evidence (master data, the
    screening) and the downloads, with a grant that is in force."""
    opened = {(method, path.format(**_PARAMS)) for method, path in OPENED}
    routes = [route for route in _sales_routes() if route not in opened]
    assert len(routes) >= 40

    answered = {}
    for method, path in routes:
        response = await staff.call(method, path)
        reason = response.json().get("details", {}).get("reason_code")
        if (response.status_code, reason) != (403, "support_context_not_allowed"):
            answered[method, path] = response.status_code

    assert answered == {}
    # The grant was in force all along: an opened read still answers.
    assert (await staff.get("/overview")).status_code == 200


# ------------------------------------------------------------ the trail --


async def test_each_support_read_is_on_the_trail_under_the_grant(
    api: Api, staff: Staff, migrator: AsyncEngine
) -> None:
    case = await order_of(api.as_(AN), "M01")

    reads = ["/overview", "/orders", f"/orders/{case['case_id']}", "/quotes"]
    for path in reads:
        assert (await staff.get(path)).status_code == 200, path
    # A refused request reads nothing, and so leaves no access row.
    assert (await staff.get("/inbox")).status_code == 403

    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT actor_id, details FROM platform.audit_events"
                    " WHERE action = 'support.access'"
                    "   AND details->>'support_grant_id' = :g ORDER BY occurred_at, id"
                ),
                {"g": str(staff.grant_id)},
            )
        ).all()
    assert [row.details["route"] for row in rows] == [
        "/api/v1/sales/overview",
        "/api/v1/sales/orders",
        "/api/v1/sales/orders/{case_id}",
        "/api/v1/sales/quotes",
    ]
    assert {row.actor_id for row in rows} == {staff.user_id}
    assert rows[2].details["path_ids"] == {"case_id": case["case_id"]}


async def test_the_head_revokes_and_the_next_read_is_refused(
    api: Api, staff: Staff, migrator: AsyncEngine
) -> None:
    """ADR 0024: a revocation takes effect at the staff member's next request.
    The platform's own test of this runs on fakes; these five reads are the
    first routes a grant opens, so this is the real adapters' reading of it."""
    assert (await staff.get("/orders")).status_code == 200
    giang = api.as_(GIANG)

    revoked = await api.client.post(
        f"/api/v1/support/grants/{staff.grant_id}/revoke", headers=giang.headers(str(uuid.uuid4()))
    )

    assert revoked.status_code == 200, revoked.text
    refused = await staff.get("/orders")
    assert refused.status_code == 403
    assert refused.json()["details"]["reason_code"] == "support_grant_ended"
    async with migrator.connect() as conn:
        reads = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events"
                " WHERE action = 'support.access' AND details->>'support_grant_id' = :g"
            ),
            {"g": str(staff.grant_id)},
        )
    assert reads == 1  # the read before the revocation, and nothing after


# ------------------------------------------------------- the boundaries --


async def test_support_is_no_member_and_the_grant_not_the_headers_names_the_tenant(
    api: Api, staff: Staff
) -> None:
    """Without the grant the staff member is nobody in the customer's tenant;
    with it, another tenant's headers change nothing: the tenant and the
    workspace are the grant's (ADR 0024 SA13)."""
    await order_of(api.as_(AN), "M01")
    token = DevTokenVerifier(SECRET).issue(staff.subject, amr=["pwd", "otp"])
    alpha = {
        "X-Tenant-Id": str(ALPHA),
        "X-Workspace-Id": str(sid("workspace", "tenant-alpha:main")),
    }
    beta = {
        "X-Tenant-Id": str(sid("tenant", "tenant-beta")),
        "X-Workspace-Id": str(sid("workspace", "tenant-beta:main")),
    }

    as_member = await api.client.get(
        "/api/v1/sales/orders", headers={"Authorization": f"Bearer {token}", **alpha}
    )
    under_grant = await api.client.get("/api/v1/sales/orders", headers={**staff.headers(), **beta})

    assert as_member.status_code == 403
    assert under_grant.status_code == 200
    assert under_grant.json() == (await api.as_(AN).get("/orders")).json() != []
