"""sales policies read the offboarding workspace scope

Revision ID: 0d9e3f85d814
Revises: eb9885f7ae07
Create Date: 2026-10-06 15:09:12.000000+00:00

Every `sales` policy narrows by tenant AND workspace (`621864952a54`). The
platform's offboarding lane now reads every workspace of one tenant by setting
`app.workspace_scope = 'tenant'` for its transaction, instead of binding each
workspace in turn, and CLAUDE.md gives a workspace-narrowed table one policy
shape for that, on both sides:

    tenant AND (workspace OR current_setting('app.workspace_scope') = 'tenant')

Without it the lane exports no sales row and deletes none, and the purge of
`platform.workspaces` then CASCADEs them away unexported.
`test_rls_coverage.py` fails a workspace-narrowed table with no policy reading
the scope, and a policy reading it outside that shape.

The policies are found in the catalog, not listed: the case event log's monthly
partitions carry their own copy of the parent's policy, and the partitions made
so far are not named in any migration. A partition made after this revision
copies the parent's policy as it then reads (`platform._ensure_one_partition`),
so it is born in the new shape.
"""

from __future__ import annotations

from alembic import op

revision = "0d9e3f85d814"
down_revision = "eb9885f7ae07"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"

_NARROW = f"({_TENANT} AND {_WORKSPACE})"
_WIDENED = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"


def _set_every_sales_policy(expression: str) -> str:
    # Every policy in `sales` that narrows by workspace. The expression is a
    # constant of this file; the names come from the catalog and are quoted.
    # It sits inside a string literal of the format() call, so its quotes
    # are doubled there.
    literal = expression.replace("'", "''")
    return f"""
DO $do$
DECLARE
    pol record;
BEGIN
    FOR pol IN
        SELECT p.polname, c.relname
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'sales'
          AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.workspace_id%'
    LOOP
        EXECUTE format(
            'ALTER POLICY %I ON sales.%I USING {literal} WITH CHECK {literal}',
            pol.polname, pol.relname
        );
    END LOOP;
END;
$do$
"""


def upgrade() -> None:
    op.execute(_set_every_sales_policy(_WIDENED))


def downgrade() -> None:
    op.execute(_set_every_sales_policy(_NARROW))
