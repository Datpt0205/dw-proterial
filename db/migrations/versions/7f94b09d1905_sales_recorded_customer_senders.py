"""sales recorded customer senders: the senders Sales confirmed as a customer's

Revision ID: 7f94b09d1905
Revises: bbf5aa95bf6f
Create Date: 2026-10-29 06:21:49.050998+00:00

Đạt, 2026-10-29 (the AI list, item 5). A mail from an address on no
customer's domain was routed `customer_unknown`, and stayed unknown for every
later mail from it until someone added the domain to the company's Excel.
DW1 now suggests the customer from the mail, Sales confirms, and the address
is kept: the next mail from it finds its customer at once.

- **`sales.recorded_customer_senders`**: one row per (sender address), the
  customer Sales confirmed, who confirmed it and on which message. The
  address, never the domain: a buyer writing from a public mail provider must
  not make every sender there that customer's. Stored lowercase. The first
  confirmation is kept (`ON CONFLICT DO NOTHING`); a customer's own domain in
  the master data answers before it (`SnapshotSalesCatalog`).
- **Appended, never changed**: `dw_app` holds SELECT and INSERT; UPDATE and
  DELETE are REVOKEd (failure-modes #7).
- **Not partitioned, not pruned**: bounded by the customers' buyers.
- **Tenant AND workspace** on both sides of the policy; foreign keys to the
  tenant and the workspace `ON DELETE CASCADE`, each indexed on its own side.
  The message is named, not referenced: the row is evidence of who confirmed
  what.
"""

from __future__ import annotations

from alembic import op

revision = "7f94b09d1905"
down_revision = "bbf5aa95bf6f"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_RECORDED = """
    CREATE TABLE sales.recorded_customer_senders (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        sender_address text NOT NULL,
        customer_code text NOT NULL,
        confirmed_by uuid NOT NULL,
        message_id text NOT NULL,
        recorded_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_recorded_customer_senders
            PRIMARY KEY (tenant_id, workspace_id, sender_address),
        CONSTRAINT fk_recorded_customer_senders_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_recorded_customer_senders_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_recorded_customer_senders_sender_address CHECK (
            sender_address ~ '^[^@[:space:]A-Z]+@[a-z0-9.-]+$'
            AND char_length(sender_address) <= 254
        ),
        CONSTRAINT ck_recorded_customer_senders_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]{1,15}$'),
        CONSTRAINT ck_recorded_customer_senders_message_id
            CHECK (message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512)
    )
"""

_INDEXES = (
    "CREATE INDEX ix_recorded_customer_senders_workspace_id"
    " ON sales.recorded_customer_senders (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT ON sales.recorded_customer_senders TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON sales.recorded_customer_senders FROM dw_app",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.recorded_customer_senders ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.recorded_customer_senders FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_recorded_customer_senders ON sales.recorded_customer_senders"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_RECORDED, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE sales.recorded_customer_senders")
