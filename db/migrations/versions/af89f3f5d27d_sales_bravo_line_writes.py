"""sales bravo line writes

Revision ID: af89f3f5d27d
Revises: adad4d524377
Create Date: 2026-11-21 16:00:00.000000+00:00

Sales ticket 53, ADR 0027: an SO line's change, written into Bravo through
the gateway under the approving PIC's own Bravo user.

- **`sales.bravo_line_writes`**: one row per proposal, keyed by the platform
  approval it waits on (`bravo_write.sales_order`), of the same tenant and
  workspace (`fk_bravo_line_writes_approval_requests`, composite, CASCADE as
  `po_layouts`: an approval leaves only with its tenant's purge). It holds
  the exact command decided on (`command`, the contract's canonical content)
  and its hash, Bravo's value when read beside the new one, and, once the
  worker carried it out, what the gateway answered.
- **One open proposal per line** (`uq_bravo_line_writes_one_open`, partial):
  a second proposal for a line waits for the first to be decided.
- **A settled row says who and when** (`ck_bravo_line_writes_settled`): a
  proposal has no decider and no settle time, anything else has both.
- **Kinds are a fixed set** (`ck_bravo_line_writes_kind`): the two the
  gateway runs today; a new kind is a new revision.
- Tenant data under the one `sales` policy shape (tenant AND (workspace OR
  the offboarding lane's scope)), RLS enabled and FORCEd; `dw_app` holds the
  four verbs, as `po_layouts`.
- **`sales.bravo.write`** joins `sales_pic` and `sales_head`: proposing a
  write and approving it, which writes under the approver's own Bravo user.
  Bravo's own rights decide the rest, at the write.
"""

from __future__ import annotations

from alembic import op

revision = "af89f3f5d27d"
down_revision = "adad4d524377"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"
_STATUSES = (
    "('proposed', 'rejected', 'written', 'written_with_differences', 'refused', 'in_doubt')"
)
_KINDS = "('so.line.set_confirmed_date@1', 'so.line.set_quantity@1')"

_TABLE = f"""
    CREATE TABLE sales.bravo_line_writes (
        approval_id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_id uuid NOT NULL,
        line_no integer NOT NULL,
        so_no text NOT NULL,
        item_code text NOT NULL,
        field text NOT NULL,
        before_value text,
        after_value text NOT NULL,
        kind text NOT NULL,
        command jsonb NOT NULL,
        content_hash text NOT NULL,
        status text NOT NULL,
        check_name text,
        reason text,
        warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
        transport_failures integer NOT NULL DEFAULT 0,
        proposed_by uuid NOT NULL,
        proposed_at timestamp with time zone NOT NULL,
        decided_by uuid,
        settled_at timestamp with time zone,
        created_at timestamp with time zone NOT NULL DEFAULT now(),
        updated_at timestamp with time zone NOT NULL DEFAULT now(),
        CONSTRAINT pk_bravo_line_writes PRIMARY KEY (approval_id),
        CONSTRAINT fk_bravo_line_writes_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_line_writes_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_line_writes_case_id_order_cases FOREIGN KEY (case_id)
            REFERENCES sales.order_cases (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_line_writes_approval_requests
            FOREIGN KEY (tenant_id, workspace_id, approval_id)
            REFERENCES platform.approval_requests (tenant_id, workspace_id, id)
            ON DELETE CASCADE,
        CONSTRAINT uq_bravo_line_writes_approval UNIQUE (tenant_id, workspace_id, approval_id),
        CONSTRAINT ck_bravo_line_writes_line_no CHECK (line_no BETWEEN 1 AND 99999),
        CONSTRAINT ck_bravo_line_writes_so_no CHECK (char_length(so_no) BETWEEN 1 AND 64),
        CONSTRAINT ck_bravo_line_writes_item_code CHECK (char_length(item_code) <= 64),
        CONSTRAINT ck_bravo_line_writes_field CHECK (field IN ('confirmed_date', 'quantity')),
        CONSTRAINT ck_bravo_line_writes_values CHECK (
            char_length(after_value) BETWEEN 1 AND 64
            AND (before_value IS NULL OR char_length(before_value) <= 64)),
        CONSTRAINT ck_bravo_line_writes_kind CHECK (kind IN {_KINDS}),
        CONSTRAINT ck_bravo_line_writes_command CHECK (jsonb_typeof(command) = 'object'),
        CONSTRAINT ck_bravo_line_writes_hash CHECK (
            char_length(content_hash) = 64 AND content_hash ~ '^[0-9a-f]+$'),
        CONSTRAINT ck_bravo_line_writes_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_bravo_line_writes_reason CHECK (
            (reason IS NULL OR char_length(reason) <= 500)
            AND (check_name IS NULL OR char_length(check_name) <= 32)),
        CONSTRAINT ck_bravo_line_writes_warnings CHECK (jsonb_typeof(warnings) = 'array'),
        CONSTRAINT ck_bravo_line_writes_failures CHECK (transport_failures >= 0),
        CONSTRAINT ck_bravo_line_writes_settled CHECK (
            (status = 'proposed') = (decided_by IS NULL)
            AND (status = 'proposed') = (settled_at IS NULL))
    )
"""
_ROW_SECURITY = (
    "ALTER TABLE sales.bravo_line_writes ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.bravo_line_writes FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_bravo_line_writes ON sales.bravo_line_writes"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)
_INDEXES = (
    "CREATE UNIQUE INDEX uq_bravo_line_writes_one_open ON sales.bravo_line_writes"
    " (tenant_id, workspace_id, case_id, line_no) WHERE status = 'proposed'",
    # A case's writes, newest first, led by what row security supplies.
    "CREATE INDEX ix_bravo_line_writes_tenant_id_case_id_proposed_at"
    " ON sales.bravo_line_writes (tenant_id, workspace_id, case_id, proposed_at DESC)",
    "CREATE INDEX ix_bravo_line_writes_case_id ON sales.bravo_line_writes (case_id)",
    "CREATE INDEX ix_bravo_line_writes_workspace_id ON sales.bravo_line_writes (workspace_id)",
)
_GRANT = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON sales.bravo_line_writes TO dw_app;
        END IF;
    END
    $$
"""
_SCOPE_NAME = "sales.bravo.write"
_ROLES = ("sales_pic", "sales_head")


def upgrade() -> None:
    op.execute(_TABLE)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.bravo_line_writes"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    op.execute(_GRANT)
    for role in _ROLES:
        op.execute(
            f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE_NAME}\"]'::jsonb"
            f" WHERE key = '{role}' AND NOT scopes ? '{_SCOPE_NAME}'"
        )


def downgrade() -> None:
    for role in _ROLES:
        op.execute(
            f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE_NAME}' WHERE key = '{role}'"
        )
    op.execute("DROP TABLE sales.bravo_line_writes")
