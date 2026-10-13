"""sales po layouts people map and approve

Revision ID: 63242ec52c4b
Revises: a970a6cbac29
Create Date: 2026-10-13 10:30:00.000000+00:00

Sales ticket 30, dw_sales ADR 0005. A customer's PO form no layout reads is
mapped once by a person on the onboarding screen and approved by another; every
later PO of that form is read with the layout by the reader, with no model.

- **`sales.po_layouts`**: one row per layout a person proposed, as the domain
  serialises it (`body`, a `PoLayout`), with the columns constraints and
  lookups need. Tenant data: `tenant_isolation_po_layouts` narrows by tenant
  AND (workspace OR the offboarding lane's tenant scope), the one shape every
  `sales` policy has (`0d9e3f85d814`), so a layout is never read for another
  tenant and offboarding exports and purges it.
- **Maker and checker**: the decision is a platform approval (`sales.layout`,
  dw_sales ADR 0004), opened with the proposal: `approval_id` names it, of
  the same tenant and workspace (`fk_po_layouts_approval_requests`, composite,
  so a layout can never wait on another workspace's approval; CASCADE because
  an approval leaves only with its tenant's purge, which removes both), one
  layout per approval (`uq_po_layouts_approval_id`, which also indexes the
  key). `ck_po_layouts_checker_not_maker` refuses a decision by the person
  who proposed the layout, whatever writes the row; the platform's strict
  rule and the domain refuse it first. A decided layout names who decided it
  (`ck_po_layouts_decided`).
- **One approved layout per form**: `uq_po_layouts_customer_kind_approved` (partial)
  holds at most one approved layout per customer and kind of file in a
  workspace; approving a newer one supersedes the older in the same
  transaction.
- **`sales.messages.layout_prefill`**: what a model pre-filled for a PO no
  layout read (`MessageDisposition.layout_prefill`), only on a message routed
  `attachment_unreadable`. Null for every other message.
- **`sales.layout.approve`** is the head's (`sales_head`): the checker of a
  layout a PIC proposed.

Grants: the schema's default privileges give `dw_app` the table at creation;
granted again explicitly, as `621864952a54` does, for a database whose
defaults were set by another role. Downgrade removes all four.
"""

from __future__ import annotations

from alembic import op

revision = "63242ec52c4b"
down_revision = "a970a6cbac29"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_STATUSES = "('proposed', 'approved', 'rejected', 'superseded')"
_KINDS = "('excel', 'pdf')"
_CUSTOMER_CODE = r"'^[A-Z][A-Z0-9]{1,15}$'"

_TABLE = f"""
    CREATE TABLE sales.po_layouts (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        customer_code text NOT NULL,
        kind text NOT NULL,
        version integer NOT NULL,
        status text NOT NULL,
        proposed_by uuid NOT NULL,
        decided_by uuid,
        approval_id uuid NOT NULL,
        body jsonb NOT NULL,
        created_at timestamp with time zone NOT NULL DEFAULT now(),
        updated_at timestamp with time zone NOT NULL DEFAULT now(),
        CONSTRAINT pk_po_layouts PRIMARY KEY (id),
        CONSTRAINT fk_po_layouts_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_po_layouts_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_po_layouts_approval_requests
            FOREIGN KEY (tenant_id, workspace_id, approval_id)
            REFERENCES platform.approval_requests (tenant_id, workspace_id, id)
            ON DELETE CASCADE,
        CONSTRAINT uq_po_layouts_approval_id UNIQUE (tenant_id, workspace_id, approval_id),
        CONSTRAINT ck_po_layouts_customer_code CHECK (customer_code ~ {_CUSTOMER_CODE}),
        CONSTRAINT ck_po_layouts_kind CHECK (kind IN {_KINDS}),
        CONSTRAINT ck_po_layouts_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_po_layouts_version CHECK (version >= 1),
        CONSTRAINT ck_po_layouts_body CHECK (jsonb_typeof(body) = 'object'),
        CONSTRAINT ck_po_layouts_decided CHECK ((status = 'proposed') = (decided_by IS NULL)),
        CONSTRAINT ck_po_layouts_checker_not_maker CHECK (decided_by IS DISTINCT FROM proposed_by),
        CONSTRAINT uq_po_layouts_customer_kind_version
            UNIQUE (tenant_id, workspace_id, customer_code, kind, version)
    )
"""

_ROW_SECURITY = (
    "ALTER TABLE sales.po_layouts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.po_layouts FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_po_layouts ON sales.po_layouts"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES = (
    # At most one approved layout per form.
    "CREATE UNIQUE INDEX uq_po_layouts_customer_kind_approved"
    " ON sales.po_layouts (tenant_id, workspace_id, customer_code, kind)"
    " WHERE status = 'approved'",
    # The screen's list, newest first, led by what row security supplies.
    "CREATE INDEX ix_po_layouts_tenant_id_workspace_id_created_at"
    " ON sales.po_layouts (tenant_id, workspace_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_po_layouts_workspace_id ON sales.po_layouts (workspace_id)",
)

_GRANT = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON sales.po_layouts TO dw_app;
        END IF;
    END
    $$
"""

_PREFILL = "ck_messages_layout_prefill"
_SCOPE_NAME = "sales.layout.approve"
_ROLE = "sales_head"


def upgrade() -> None:
    op.execute(_TABLE)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.po_layouts"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    op.execute(_GRANT)
    op.execute(
        "ALTER TABLE sales.messages ADD COLUMN layout_prefill jsonb,"
        f" ADD CONSTRAINT {_PREFILL} CHECK ("
        " layout_prefill IS NULL OR (jsonb_typeof(layout_prefill) = 'object'"
        " AND disposition = 'routed_to_sales'"
        " AND routing_reason = 'attachment_unreadable'))"
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE_NAME}\"]'::jsonb"
        f" WHERE key = '{_ROLE}' AND NOT scopes ? '{_SCOPE_NAME}'"
    )


def downgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE_NAME}' WHERE key = '{_ROLE}'")
    op.execute(f"ALTER TABLE sales.messages DROP CONSTRAINT {_PREFILL}, DROP COLUMN layout_prefill")
    op.execute("DROP TABLE sales.po_layouts")
