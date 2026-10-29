"""sales recorded convert entries: the item codes Sales confirmed

Revision ID: bbf5aa95bf6f
Revises: 71305f72d962
Create Date: 2026-10-29 09:00:00.000000+00:00

Đạt, 2026-10-29 (the AI list, item 3). When Sales confirms which PRV code a
customer's own item code is, the convert list learned nothing: the next PO
with the same code asked Sales again, until someone typed the row into the
company's Excel and imported it. The confirmation is now kept, and a later
PO line with that customer's code maps through it at once.

- **`sales.recorded_convert_entries`**: one row per (customer, customer item
  code), the PRV code Sales confirmed, who confirmed it and on which case.
  The first confirmation is kept; a later one for the same code does not
  replace it (`ON CONFLICT DO NOTHING`), and the company's own list, once an
  import carries the code, answers before it (`SnapshotSalesCatalog`).
- **Appended, never changed**: `dw_app` holds SELECT and INSERT; UPDATE and
  DELETE are REVOKEd (failure-modes #7).
- **Not partitioned, not pruned**: bounded by the customers' item codes, like
  the convert list it extends.
- **Tenant AND workspace** on both sides of the policy; foreign keys to the
  tenant and the workspace `ON DELETE CASCADE`, each indexed on its own side.
  The case is named, not referenced: a case is never deleted, and the row is
  evidence of who confirmed what, not part of the case.
"""

from __future__ import annotations

from alembic import op

revision = "bbf5aa95bf6f"
down_revision = "71305f72d962"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_RECORDED = """
    CREATE TABLE sales.recorded_convert_entries (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        customer_code text NOT NULL,
        customer_item_code text NOT NULL,
        prv_code text NOT NULL,
        confirmed_by uuid NOT NULL,
        case_id uuid NOT NULL,
        recorded_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_recorded_convert_entries
            PRIMARY KEY (tenant_id, workspace_id, customer_code, customer_item_code),
        CONSTRAINT fk_recorded_convert_entries_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_recorded_convert_entries_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_recorded_convert_entries_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]{1,15}$'),
        CONSTRAINT ck_recorded_convert_entries_customer_item_code
            CHECK (customer_item_code ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,47}$'),
        CONSTRAINT ck_recorded_convert_entries_prv_code
            CHECK (prv_code ~ '^[A-Z0-9][A-Z0-9-]{1,31}$')
    )
"""

_INDEXES = (
    "CREATE INDEX ix_recorded_convert_entries_workspace_id"
    " ON sales.recorded_convert_entries (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT ON sales.recorded_convert_entries TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON sales.recorded_convert_entries FROM dw_app",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.recorded_convert_entries ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.recorded_convert_entries FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_recorded_convert_entries ON sales.recorded_convert_entries"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_RECORDED, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE sales.recorded_convert_entries")
