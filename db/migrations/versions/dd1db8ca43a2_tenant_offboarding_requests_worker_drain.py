"""Let the offboarding lane find work before it knows which tenant to scope to.

Revision ID: dd1db8ca43a2
Revises: 5d9d89ffc716
Create Date: 2026-09-22

Every other tenant-scoped table the worker touches gets `app.tenant_id` set
BEFORE the first query, because something already told the worker which
tenant it is handling — the run it is executing, the event it is draining.
This table is different: nothing tells the worker which tenant has a
`status = 'requested'` row until it asks, and asking is itself the
cross-tenant read `app.tenant_id` scoping exists to prevent. Same shape as
`0010_memory_retention_drain`/`c3ec03bd6fd1_tenant_daily_spend_guard_worker_drain`,
same reason.

Once the poll finds a tenant_id, every subsequent step (export, purge,
reporting status back) runs under `app.tenant_id` set to that one tenant, the
ordinary way — never `app.worker_drain` again for the rest of that request's
lifecycle. This policy exists for exactly one query: "which tenant has work
waiting."
"""

from __future__ import annotations

from alembic import op

revision = "dd1db8ca43a2"
down_revision = "5d9d89ffc716"
branch_labels = None
depends_on = None

_DRAIN = "current_setting('app.worker_drain', true) = 'on'"


def upgrade() -> None:
    op.execute(
        "CREATE POLICY worker_drain_tenant_offboarding_requests ON platform.tenant_offboarding_requests"  # noqa: E501
        f" USING ({_DRAIN}) WITH CHECK ({_DRAIN})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS worker_drain_tenant_offboarding_requests"
        " ON platform.tenant_offboarding_requests"
    )
