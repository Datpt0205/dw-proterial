"""Tenant daily spend guard — narrow by design, not the ledger that got pulled.

Revision ID: 2b5ff2bceb06
Revises: aefe7c1f5d9b
Create Date: 2026-09-22

`platform.model_usage_ledger` was dropped in `aefe7c1f5d9b` because it was
built on a false premise: "evidence for invoicing," when this repo invoices
nobody and `cost_usd` is what the platform pays a model provider, not
something billed to a tenant. That commit left a real gap, stated plainly in
its own message: `runs_per_day` still bounds how many runs a tenant starts,
the per-run ceiling still bounds one loop, but a day of expensive runs has no
ceiling at all.

This table is the mechanism only — no admin route, no usage-stats service, no
UI. One row per `(tenant_id, spend_date)`, a running total, not a per-call
event log: there is nothing here for anyone to read as billing evidence,
which is what made the last one look like something it never was.

No GRANT here: `0001_platform_grants.sql`'s `ALTER DEFAULT PRIVILEGES IN
SCHEMA platform ... GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_app`
already covers a table the migrator creates later — DELETE included on
purpose, because the retention sweep that ages this table out runs as
`dw_app`, the same way memory and knowledge retention already do.
"""

from __future__ import annotations

from alembic import op

revision = "2b5ff2bceb06"
down_revision = "aefe7c1f5d9b"
branch_labels = None
depends_on = None

_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)

_UPGRADE = (
    """
    CREATE TABLE platform.tenant_daily_spend_guard (
        tenant_id uuid NOT NULL,
        spend_date date NOT NULL,
        spend_usd numeric(12, 4) DEFAULT 0 NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_tenant_daily_spend_guard PRIMARY KEY (tenant_id, spend_date),
        CONSTRAINT ck_tenant_daily_spend_guard_spend_usd CHECK (spend_usd >= 0)
    )
    """,
    "ALTER TABLE platform.tenant_daily_spend_guard ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.tenant_daily_spend_guard FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_tenant_daily_spend_guard ON platform.tenant_daily_spend_guard"
    f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}",
)

_DOWNGRADE = ("DROP TABLE platform.tenant_daily_spend_guard",)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
