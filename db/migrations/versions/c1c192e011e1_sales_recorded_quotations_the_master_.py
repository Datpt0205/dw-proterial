"""sales recorded quotations: the master-list rows DW1 sent

Revision ID: c1c192e011e1
Revises: 40266fbc98bf
Create Date: 2026-10-29 01:38:36.500919+00:00

WIV-03-023 step 11 (Đạt, 2026-10-29: "2 quy trình trong DW1 đã nối với nhau
chưa"). A quotation Sales sent and confirmed is the valid quotation a later PO
line is checked against. Until this table it was written to the mock catalog
in the memory of the process that served the request: the API held it, the
worker that checks a dropped PO never saw it, and a restart lost it.

- **`sales.recorded_quotations`**: one row per quoted line, keyed by quote
  number and item. The quotation itself is the `quotation` document, as
  `dw_sales.domain.catalog.Quotation` serialises it, so its fields are named
  once; the key columns are CHECKed equal to the document's own.
- **Appended, never changed.** A quotation sent is a fact about the past; a
  second record of the same terms is skipped and different terms under a held
  number are refused (`SqlRecordedQuotations`). `dw_app` holds SELECT and
  INSERT; UPDATE and DELETE are REVOKEd (failure-modes #7).
- **Not partitioned, not pruned:** bounded by the quotations a company sends
  (a few hundred lines a year), like the master list it extends. A row the
  next approved import also holds is shadowed by it on read, not deleted.
- **Tenant AND workspace**, the shape every workspace-narrowed table has, on
  both sides of the policy. Foreign keys to the tenant and the workspace,
  `ON DELETE CASCADE`, each indexed on its own side (the primary key leads
  with `tenant_id`).
"""

from __future__ import annotations

from alembic import op

revision = "c1c192e011e1"
down_revision = "40266fbc98bf"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_RECORDED = """
    CREATE TABLE sales.recorded_quotations (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        quote_no text NOT NULL,
        prv_code text NOT NULL,
        customer_code text NOT NULL,
        quotation jsonb NOT NULL,
        recorded_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_recorded_quotations
            PRIMARY KEY (tenant_id, workspace_id, quote_no, prv_code),
        CONSTRAINT fk_recorded_quotations_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_recorded_quotations_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_recorded_quotations_quote_no
            CHECK (quote_no ~ '^[A-Z0-9][A-Z0-9/-]{1,31}$'),
        CONSTRAINT ck_recorded_quotations_prv_code
            CHECK (prv_code ~ '^[A-Z0-9][A-Z0-9-]{1,31}$'),
        CONSTRAINT ck_recorded_quotations_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]{1,15}$'),
        CONSTRAINT ck_recorded_quotations_quotation CHECK (
            jsonb_typeof(quotation) = 'object'
            AND quotation ->> 'quote_no' = quote_no
            AND quotation ->> 'prv_code' = prv_code
            AND quotation ->> 'customer_code' = customer_code
        )
    )
"""

_INDEXES = (
    "CREATE INDEX ix_recorded_quotations_workspace_id ON sales.recorded_quotations (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT ON sales.recorded_quotations TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON sales.recorded_quotations FROM dw_app",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.recorded_quotations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.recorded_quotations FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_recorded_quotations ON sales.recorded_quotations"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_RECORDED, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE sales.recorded_quotations")
