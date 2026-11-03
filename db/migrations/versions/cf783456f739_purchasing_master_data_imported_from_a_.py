"""purchasing master data imported from a workbook

Revision ID: cf783456f739
Revises: 394419a5ebbd
Create Date: 2026-11-02 08:30:00.000000+00:00

DW2's master data (items, suppliers, quotations on file, prices paid,
budgets) is one document a tenant holds its own version of, key
`purchasing_master_data`, proposed, decided and applied by the platform's
rule-version engine (`dw_purchasing/docs/adr/0001`). Two changes:

- **`ck_rule_versions_key`** admits `purchasing_master_data`.
- **`purchasing.master_imports`**: DW2's own queue of uploaded workbooks
  (ADR 0014 decision 2), what the worker read from each and whether it was
  sent to be decided. A row is `queued` (its bytes kept, nothing read), then
  `parsed` (the lists it holds and the rows refused) or `failed` (why), then
  `submitted` (the version it was proposed as). The bytes go when the file is
  read. Mutable by the application (a queue), RLS on tenant and workspace in
  the one shape, offboarded by the catalog's policy discovery and by the
  tenant's and workspace's cascade; the `purchasing_master_import` lane
  forgets a row after 90 days.

Downgrade drops the table and the key's versions, then narrows the check.
"""

from __future__ import annotations

from alembic import op

revision = "cf783456f739"
down_revision = "394419a5ebbd"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_KEYS = (
    "sales_order_rules",
    "sales_kpi",
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
    "sales_followups",
    "purchasing_rules",
    "purchasing_automation",
)
_KEY = "purchasing_master_data"

_IMPORTS = """
    CREATE TABLE purchasing.master_imports (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        file_name text NOT NULL,
        sha256 text NOT NULL,
        content bytea,
        status text NOT NULL,
        uploaded_by uuid NOT NULL,
        uploaded_at timestamp with time zone NOT NULL,
        read_at timestamp with time zone,
        lists jsonb,
        rejected jsonb DEFAULT '[]'::jsonb NOT NULL,
        rejected_total integer DEFAULT 0 NOT NULL,
        failure text,
        version_ref text,
        submitted_by uuid,
        submitted_at timestamp with time zone,
        CONSTRAINT pk_master_imports PRIMARY KEY (id),
        CONSTRAINT fk_master_imports_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_master_imports_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        -- A file's name, never a path.
        CONSTRAINT ck_master_imports_file_name CHECK (
            char_length(file_name) BETWEEN 1 AND 200
            AND strpos(file_name, '/') = 0 AND strpos(file_name, chr(92)) = 0
        ),
        CONSTRAINT ck_master_imports_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        -- `dw_purchasing.application.master_data`'s statuses.
        CONSTRAINT ck_master_imports_status CHECK (
            status IN ('queued', 'parsed', 'failed', 'submitted')
        ),
        -- The bytes are kept until the file is read, and only until then.
        CONSTRAINT ck_master_imports_content CHECK (
            (status = 'queued') = (content IS NOT NULL)
            AND (content IS NULL OR octet_length(content) BETWEEN 1 AND 20971520)
        ),
        CONSTRAINT ck_master_imports_read_at CHECK ((status = 'queued') = (read_at IS NULL)),
        -- What a file says exists once it was read and said something.
        CONSTRAINT ck_master_imports_lists CHECK (
            (status IN ('parsed', 'submitted')) = (lists IS NOT NULL)
            AND (lists IS NULL OR jsonb_typeof(lists) = 'object')
        ),
        CONSTRAINT ck_master_imports_rejected CHECK (
            jsonb_typeof(rejected) = 'array' AND rejected_total >= jsonb_array_length(rejected)
        ),
        CONSTRAINT ck_master_imports_failure CHECK (
            (status = 'failed') = (failure IS NOT NULL)
            AND (failure IS NULL OR char_length(failure) BETWEEN 1 AND 400)
        ),
        CONSTRAINT ck_master_imports_submitted CHECK (
            (status = 'submitted') = (version_ref IS NOT NULL)
            AND (status = 'submitted') = (submitted_by IS NOT NULL)
            AND (status = 'submitted') = (submitted_at IS NOT NULL)
            AND (version_ref IS NULL OR char_length(version_ref) <= 120)
        )
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE purchasing.master_imports ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.master_imports FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_master_imports ON purchasing.master_imports"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # The page's list, newest first (`SqlMasterImports.recent`).
    "CREATE INDEX ix_master_imports_tenant_id_workspace_id_uploaded_at"
    " ON purchasing.master_imports (tenant_id, workspace_id, uploaded_at DESC, id DESC)",
    # What the lane reads next, oldest first (`SqlMasterImports.queued`).
    "CREATE INDEX ix_master_imports_tenant_id_workspace_id_queued"
    " ON purchasing.master_imports (tenant_id, workspace_id, uploaded_at, id)"
    " WHERE status = 'queued'",
    # The workspace's own key, for the cascade.
    "CREATE INDEX ix_master_imports_workspace_id ON purchasing.master_imports (workspace_id)",
)

# A queue: the application reads, writes, moves and forgets its rows. Every
# verb is granted by name, whatever the schema's defaults say.
_GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON purchasing.master_imports TO dw_app",
)


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _keys(keys: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.rule_versions DROP CONSTRAINT ck_rule_versions_key,"
        f" ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({_listed(keys)}))"
    )


def upgrade() -> None:
    _keys((*_KEYS, _KEY))
    op.execute(_IMPORTS)
    for statement in (*_ROW_SECURITY, *_INDEXES, *_GRANTS):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE purchasing.master_imports")
    op.execute(f"DELETE FROM platform.rule_versions WHERE key = '{_KEY}'")
    _keys(_KEYS)
