"""Tenant offboarding: a provisioning-owned request, a worker-owned execution.

Revision ID: 5d9d89ffc716
Revises: c3ec03bd6fd1
Create Date: 2026-09-22

The provisioning path is deliberately tenant-less: `dw_provisioner` holds
BYPASSRLS and is granted only the platform provisioning tables, so nothing on
that path can read a tenant's business data (see
`provisioning_repo.py`'s docstring). Export and purge need to read and delete
business data across every tenant-scoped table, so they cannot run through
that path — they run as `dw_app`, scoped by the ordinary `app.tenant_id`
mechanism every other tenant-scoped query already uses, for exactly one
tenant at a time.

This table is the handoff between the two: an operator (`dw_provisioner`,
bypasses this table's RLS the same way it bypasses `platform.tenants`') files
a request; a worker lane (`dw_app`, sets `app.tenant_id` to the target tenant
for the duration) claims it, exports, purges, and reports back by updating
its own status. `dw_app` gets no INSERT or DELETE here — only an operator
opens or removes a request; the worker only ever moves one along.

`platform.tenants.status` gains two values (`offboarding`, `offboarded`) and,
since this is the second time that column's valid values were extended, a
CHECK constraint it never had — the set was implicit in `_TENANT_STATUSES` in
Python only, and a row written by anything else was unconstrained.
"""

from __future__ import annotations

from alembic import op

revision = "5d9d89ffc716"
down_revision = "c3ec03bd6fd1"
branch_labels = None
depends_on = None

_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)

_UPGRADE = (
    """
    CREATE TABLE platform.tenant_offboarding_requests (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        status text DEFAULT 'requested'::text NOT NULL,
        requested_by uuid NOT NULL,
        requested_at timestamp with time zone DEFAULT now() NOT NULL,
        export_key text,
        error text,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_tenant_offboarding_requests PRIMARY KEY (id),
        CONSTRAINT ck_tenant_offboarding_requests_status
            CHECK (status IN ('requested', 'exporting', 'purging', 'completed', 'failed')),
        CONSTRAINT fk_tenant_offboarding_requests_tenant_id_tenants
            FOREIGN KEY (tenant_id) REFERENCES platform.tenants (id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX ix_tenant_offboarding_requests_tenant_id"
    " ON platform.tenant_offboarding_requests (tenant_id)",
    # At most one request in flight per tenant — the worker lane claims by
    # status='requested' and a second concurrent request would race it.
    "CREATE UNIQUE INDEX uq_tenant_offboarding_requests_active"
    " ON platform.tenant_offboarding_requests (tenant_id)"
    " WHERE status NOT IN ('completed', 'failed')",
    "ALTER TABLE platform.tenant_offboarding_requests ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.tenant_offboarding_requests FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_tenant_offboarding_requests ON platform.tenant_offboarding_requests"  # noqa: E501
    f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}",
    # dw_provisioner bypasses RLS (like every other provisioning table) but is
    # granted table-by-table, never by ALTER DEFAULT PRIVILEGES — see
    # 0001_platform_grants.sql's second DO block.
    "GRANT SELECT, INSERT, UPDATE ON platform.tenant_offboarding_requests TO dw_provisioner",
    # dw_app inherits SELECT/INSERT/UPDATE/DELETE from ALTER DEFAULT PRIVILEGES
    # (0001_platform_grants.sql); narrow it to what the worker lane actually
    # does — move a request along, never open or remove one.
    "REVOKE INSERT, DELETE ON platform.tenant_offboarding_requests FROM dw_app",
    "ALTER TABLE platform.tenants ADD CONSTRAINT ck_tenants_status"
    " CHECK (status IN ('active', 'locked', 'offboarding', 'offboarded'))",
)

_DOWNGRADE = (
    "ALTER TABLE platform.tenants DROP CONSTRAINT ck_tenants_status",
    "DROP TABLE platform.tenant_offboarding_requests",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
