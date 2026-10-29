"""`sales.po_layouts` (migration e91d0c239874, dw_sales ADR 0006): a layout DW1
learned is stored and read back in force with no approval; the table refuses
a learned row that names an approval or a decider, and a person's row that
names no approval, whatever writes it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence.layouts import SqlLayoutLookup, SqlLayoutStore
from dw_sales.domain.layouts import LayoutMapping, LayoutPrefill, LayoutSample, PoLayout

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 29, 3, tzinfo=UTC)
DW1 = uuid.UUID(int=0xD1)

_MAPPING = LayoutMapping(
    kind="excel",
    po_no="PO No.",
    po_date="PO Date",
    currency="Currency",
    line_no="No.",
    customer_item_code="Part No.",
    description="Description",
    quantity="Qty",
    uom="Unit",
    unit_price="Price",
    amount="Amount",
    requested_date="Delivery",
    total_label="Total",
    thousands_separator=",",
    decimal_separator=".",
    date_format="%d/%m/%Y",
)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


def _learned(version: int = 1) -> PoLayout:
    return PoLayout.learned(
        layout_id=uuid.uuid4(),
        customer_code="NRV",
        version=version,
        mapping=_MAPPING,
        sample=LayoutSample(message_id="M43", attachment_id="M43-A1", attachment_sha256="0" * 64),
        prefill=LayoutPrefill(
            prompt="sales.po_layout_proposal@1.0.0",
            model_profile="onprem",
            route="structured_extraction",
            rules="sales_order_rules@1.7.0",
            outcome="proposed",
            attachment_id="M43-A1",
            mapping=_MAPPING,
        ),
        by=DW1,
        at=AT,
    )


async def test_a_learned_layout_is_stored_and_read_in_force(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    learned = _learned()
    scope = world.alpha
    bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
    async with tenant_session(app_sessions, bound) as session:
        await SqlLayoutStore(session, scope).add(learned)

    lookup = SqlLayoutLookup(app_sessions)
    assert await lookup.approved(scope, "NRV") == [learned]
    assert await lookup.next_version(scope, "NRV", "excel") == 2
    assert await lookup.next_version(scope, "NRV", "pdf") == 1
    # Another workspace or tenant finds nothing of it.
    assert await lookup.approved(world.alpha_other, "NRV") == []
    assert await lookup.approved(world.beta, "NRV") == []


@pytest.mark.parametrize(
    ("origin", "approval", "decided_by", "status"),
    [
        ("model", True, False, "approved"),  # a learned layout opens no approval
        ("model", False, True, "approved"),  # nor is it decided by anyone
        ("model", False, False, "proposed"),  # it is in force from the start
        ("person", False, False, "proposed"),  # a person's waits on an approval
        ("robot", False, False, "approved"),  # origin is one of two
    ],
)
async def test_the_table_refuses_a_row_its_origin_does_not_allow(
    world: World,
    migrator: AsyncEngine,
    origin: str,
    approval: bool,
    decided_by: bool,
    status: str,
) -> None:
    t, w = world.alpha.tenant_id.value, world.alpha.workspace_id.value
    async with migrator.connect() as conn:
        approval_id = None
        if approval:
            approval_id = uuid.uuid4()
            await conn.execute(
                sa.text(
                    "INSERT INTO platform.approval_requests (id, tenant_id, workspace_id,"
                    " approval_type, status, requested_by, reason, payload, created_at,"
                    " required_scope) VALUES (:id, :t, :w, 'sales.layout', 'pending', :by,"
                    " 'r', '{}', now(), 'sales.layout.approve')"
                ),
                {"id": approval_id, "t": t, "w": w, "by": DW1},
            )
        with pytest.raises(IntegrityError, match="ck_po_layouts"):
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.po_layouts (id, tenant_id, workspace_id, customer_code,"
                    " kind, version, status, proposed_by, decided_by, approval_id, origin, body)"
                    " VALUES (:id, :t, :w, 'NRV', 'excel', 1, :status, :by, :decider,"
                    " :approval, :origin, '{}')"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": t,
                    "w": w,
                    "status": status,
                    "by": DW1,
                    "decider": uuid.uuid4() if decided_by else None,
                    "approval": approval_id,
                    "origin": origin,
                },
            )
