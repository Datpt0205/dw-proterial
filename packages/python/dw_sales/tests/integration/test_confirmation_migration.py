"""Migration 64d50dbc1d00 (ticket 28): an order stored as `confirmed` before
the split was a confirmation SENT, not a customer's agreement, since nothing
recorded one. On a database of its own, stopped at the revision before it:
such a row becomes `confirmation_sent` with its confirmation sent when the PIC
recorded it and no term of silence, its version and `updated_at` unchanged,
its events renamed; and back on downgrade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls, database_urls, recreate_database, run_alembic
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from dw_platform.testing.seed_env import seed_test_env, sid
from dw_sales.domain.orders import ConfirmationSent

pytestmark = pytest.mark.integration

_DB = "dw_test_sales_confirmation_migration"
_BEFORE = "0d1d0e4eb203"
_TENANT = sid("tenant", "tenant-alpha")
_WORKSPACE = sid("workspace", "tenant-alpha:main")
_AN, _DIEU = uuid.UUID(int=0xA1), uuid.UUID(int=0xD1)
_SENT = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)
_TOUCHED = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)


async def _at_the_revision_before() -> DatabaseUrls:
    urls = database_urls(_DB)
    await recreate_database(urls.admin, _DB)
    result = run_alembic(["upgrade", _BEFORE], urls.migrator)
    assert result.returncode == 0, result.stderr
    await seed_test_env(urls.migrator)
    return urls


async def _old_confirmed(urls: DatabaseUrls, status: str = "confirmed") -> uuid.UUID:
    """An order as the code before ticket 28 stored a confirmation, with the
    event that moved it there."""
    case_id = uuid.uuid4()
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.order_cases (id, tenant_id, workspace_id, customer_code,"
                    " po_no, case_version, status, rules_version, catalog_as_of,"
                    " cross_check_required, export_control_mode, prepared_by, prepared_at,"
                    " bravo_so_no, bravo_recorded_by, bravo_recorded_at, bravo_entry_compared,"
                    " cross_checked_by, cross_checked_at, confirmed_by, confirmed_at,"
                    " received_at, updated_at)"
                    " VALUES (:id, :t, :w, 'NRV', :po, 7, :status,"
                    " 'sales_order_rules@1.13.0', :at, true, 'warn', :an, :at, 'SO26-1001',"
                    " :an, :at, true, :dieu, :at, :confirmed_by, :confirmed_at, :at, :touched)"
                ),
                {
                    "id": case_id,
                    "t": _TENANT,
                    "w": _WORKSPACE,
                    "status": status,
                    "po": f"NRV-PO-{case_id.hex[:8]}",
                    "at": _SENT,
                    "an": _AN,
                    "dieu": _DIEU,
                    "confirmed_by": _AN if status == "confirmed" else None,
                    "confirmed_at": _SENT if status == "confirmed" else None,
                    "touched": _TOUCHED,
                },
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.case_events (id, tenant_id, workspace_id, case_kind,"
                    " case_id, case_version, action, from_status, to_status, actor_kind,"
                    " actor_id, occurred_at)"
                    " VALUES (:id, :t, :w, 'order', :case, 7, 'order.confirmed',"
                    " 'cross_checked', :status, 'user', :an, :at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": _TENANT,
                    "w": _WORKSPACE,
                    "case": case_id,
                    "status": status,
                    "an": str(_AN),
                    "at": _SENT,
                },
            )
    finally:
        await engine.dispose()
    return case_id


async def _row(urls: DatabaseUrls, case_id: uuid.UUID) -> sa.Row[tuple[object, ...]]:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.text(
                        "SELECT c.*, e.to_status AS event_to FROM sales.order_cases c"
                        " JOIN sales.case_events e ON e.case_id = c.id WHERE c.id = :id"
                    ),
                    {"id": case_id},
                )
            ).one()
            return row
    finally:
        await engine.dispose()


async def test_a_confirmed_order_was_a_confirmation_sent_and_back_on_downgrade() -> None:
    urls = await _at_the_revision_before()
    case_id = await _old_confirmed(urls)
    untouched = await _old_confirmed(urls, status="cross_checked")

    result = run_alembic(["upgrade", "head"], urls.migrator)
    assert result.returncode == 0, result.stderr

    row = await _row(urls, case_id)
    assert (row.status, row.event_to, row.case_version, row.agreement) == (
        "confirmation_sent",
        "confirmation_sent",
        7,
        None,
    )
    assert row.updated_at == _TOUCHED
    sent = ConfirmationSent.model_validate(row.confirmation)
    assert sent == ConfirmationSent(sent_at=_SENT)
    assert sent.term is None and sent.implied_from is None  # never implied
    other = await _row(urls, untouched)
    assert (other.status, other.confirmation, other.event_to) == (
        "cross_checked",
        None,
        "cross_checked",
    )

    assert run_alembic(["downgrade", _BEFORE], urls.migrator).returncode == 0
    row = await _row(urls, case_id)
    assert (row.status, row.event_to) == ("confirmed", "confirmed")
