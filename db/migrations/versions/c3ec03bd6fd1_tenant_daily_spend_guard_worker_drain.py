"""Let the housekeeping sweep see the spend guard across tenants.

Revision ID: c3ec03bd6fd1
Revises: 2b5ff2bceb06
Create Date: 2026-09-22

Same escape hatch `0010_memory_retention_drain` and `0011_knowledge_retention_drain`
already use, for the same reason: aging out rows older than the guard's
housekeeping window needs one DELETE across every tenant, and a sweep scoped
by `app.tenant_id` would first need a list of tenants — itself the
cross-tenant read the scoping exists to prevent. The GUC is set per
transaction by the sweep itself and never by anything reachable from a
request.

This is not a retention *decision* the way audit/memory/knowledge are — the
window is a technical constant (rows are cold within a day or two; nothing
ever asks about a date once it has passed), not a legal term someone has to
choose. It lives in code (`SqlSpendGuardRetention`), not
`configs/policies/retention@1.4.0.yaml`, for that reason.
"""

from __future__ import annotations

from alembic import op

revision = "c3ec03bd6fd1"
down_revision = "2b5ff2bceb06"
branch_labels = None
depends_on = None

_DRAIN = "current_setting('app.worker_drain', true) = 'on'"


def upgrade() -> None:
    op.execute(
        f"CREATE POLICY worker_drain_tenant_daily_spend_guard"
        f" ON platform.tenant_daily_spend_guard"
        f" USING ({_DRAIN}) WITH CHECK ({_DRAIN})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS worker_drain_tenant_daily_spend_guard"
        " ON platform.tenant_daily_spend_guard"
    )
