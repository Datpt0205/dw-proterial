"""sales one path for every Bravo export and sales orders read back

Revision ID: 7c6ad2350566
Revises: acb2a1fbb213
Create Date: 2026-11-16

dw_sales ticket 03. Every Bravo screen Sales exports and uploads comes one
way (ticket 16's): kept until the worker reads it in the reader sandbox, then
handed to the screen's reader. So ticket 16's `sales.ycbg_exports` becomes
`sales.bravo_exports`, with the screen each export is (`ck_bravo_exports_screen`:
ycbg, sales_orders), and its files `sales.bravo_export_files`. The new tables
are created whole (so `verify_invariants.py`, which reads this text, sees
their row security), the rows copied, each outcome's ``ycbg_no`` renamed
``key`` (`bravo_exports.ExportOutcome`), and the old tables dropped.

- **`sales.order_bravo_read_backs`**: an order case's sales order as Bravo
  held it when last read back: the PO, the SO number, the differences found
  against the paste sheet (`ck_order_bravo_read_backs_differences`: an array),
  how many rows were read, the export's sha256, who uploaded it and when,
  and the case version compared against. One row per case, the latest
  replacing the one before (the audit log keeps each read). Its case is
  `sales.order_cases`, ON DELETE CASCADE: a read-back is derived from the
  case and the file, evidence of neither.
- **Row security**: all three narrowed by tenant AND workspace with the
  offboarding scope, ENABLEd and FORCEd.

Grants: `dw_app` every verb on the exports (the worker settles them, an
upload prunes and fails stale ones, offboarding purges) and on the
read-backs (the worker replaces a case's); SELECT, INSERT and DELETE on the
files, UPDATE revoked. Downgrade refuses: a sales-order export or a
read-back has no place in ticket 16's tables.
"""

from __future__ import annotations

from alembic import op

revision = "7c6ad2350566"
down_revision = "acb2a1fbb213"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.application.bravo_exports` (`ExportStatus`, `BravoScreen`);
# `test_sales_schema.py` holds them together.
_STATUSES = "('queued', 'read', 'failed')"
_SCREENS = "('ycbg', 'sales_orders')"
_MAX_BYTES = 2 * 1024 * 1024

_EXPORTS = f"""
    CREATE TABLE sales.bravo_exports (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        screen text NOT NULL,
        status text NOT NULL,
        uploaded_by uuid NOT NULL,
        uploaded_at timestamptz NOT NULL,
        file_name text NOT NULL,
        file_sha256 text NOT NULL,
        file_size integer NOT NULL,
        outcomes jsonb DEFAULT '[]'::jsonb NOT NULL,
        rejected jsonb DEFAULT '[]'::jsonb NOT NULL,
        error text,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_bravo_exports PRIMARY KEY (id),
        CONSTRAINT fk_bravo_exports_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_exports_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_bravo_exports_tenant_id_workspace_id_id UNIQUE (tenant_id, workspace_id, id),
        CONSTRAINT ck_bravo_exports_screen CHECK (screen IN {_SCREENS}),
        CONSTRAINT ck_bravo_exports_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_bravo_exports_file_name CHECK (char_length(file_name) BETWEEN 1 AND 200),
        CONSTRAINT ck_bravo_exports_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_bravo_exports_file_size CHECK (file_size BETWEEN 1 AND {_MAX_BYTES}),
        CONSTRAINT ck_bravo_exports_shapes CHECK (
            jsonb_typeof(outcomes) = 'array' AND jsonb_typeof(rejected) = 'array'
        ),
        -- Only a read export has outcomes to show.
        CONSTRAINT ck_bravo_exports_outcomes CHECK (
            status = 'read' OR (outcomes = '[]'::jsonb AND rejected = '[]'::jsonb)
        ),
        CONSTRAINT ck_bravo_exports_error CHECK (
            (status = 'failed') = (error IS NOT NULL) AND char_length(error) <= 500
        )
    )
"""

_FILES = f"""
    CREATE TABLE sales.bravo_export_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        export_id uuid NOT NULL,
        content bytea NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_bravo_export_files PRIMARY KEY (tenant_id, workspace_id, export_id),
        CONSTRAINT fk_bravo_export_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_export_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_bravo_export_files_bravo_exports
            FOREIGN KEY (tenant_id, workspace_id, export_id)
            REFERENCES sales.bravo_exports (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_bravo_export_files_content
            CHECK (octet_length(content) BETWEEN 1 AND {_MAX_BYTES})
    )
"""

_READ_BACKS = """
    CREATE TABLE sales.order_bravo_read_backs (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_id uuid NOT NULL,
        case_version integer NOT NULL,
        po_no text NOT NULL,
        so_no text NOT NULL,
        differences jsonb NOT NULL,
        rows_read integer NOT NULL,
        file_sha256 text NOT NULL,
        read_by uuid NOT NULL,
        read_at timestamptz NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_order_bravo_read_backs PRIMARY KEY (tenant_id, workspace_id, case_id),
        CONSTRAINT fk_order_bravo_read_backs_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_order_bravo_read_backs_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_order_bravo_read_backs_case_id_order_cases FOREIGN KEY (case_id)
            REFERENCES sales.order_cases (id) ON DELETE CASCADE,
        CONSTRAINT ck_order_bravo_read_backs_case_version CHECK (case_version >= 1),
        CONSTRAINT ck_order_bravo_read_backs_po_no CHECK (char_length(po_no) BETWEEN 1 AND 64),
        CONSTRAINT ck_order_bravo_read_backs_so_no CHECK (char_length(so_no) BETWEEN 1 AND 64),
        CONSTRAINT ck_order_bravo_read_backs_differences
            CHECK (jsonb_typeof(differences) = 'array'),
        CONSTRAINT ck_order_bravo_read_backs_rows_read CHECK (rows_read >= 1),
        CONSTRAINT ck_order_bravo_read_backs_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{64}$')
    )
"""

_INDEXES = (
    # The latest exports of a screen, and the prune by age, led by what RLS
    # supplies.
    "CREATE INDEX ix_bravo_exports_uploaded ON sales.bravo_exports"
    " (tenant_id, workspace_id, screen, uploaded_at)",
    "CREATE INDEX ix_bravo_exports_age ON sales.bravo_exports"
    " (tenant_id, workspace_id, uploaded_at)",
    "CREATE INDEX ix_bravo_exports_workspace_id ON sales.bravo_exports (workspace_id)",
    "CREATE INDEX ix_bravo_export_files_workspace_id ON sales.bravo_export_files (workspace_id)",
    "CREATE INDEX ix_order_bravo_read_backs_case_id ON sales.order_bravo_read_backs (case_id)",
    "CREATE INDEX ix_order_bravo_read_backs_workspace_id"
    " ON sales.order_bravo_read_backs (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.bravo_exports TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.bravo_export_files TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE ON sales.bravo_export_files FROM dw_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.order_bravo_read_backs TO dw_app",
)

# Spelled out per table, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.bravo_exports ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.bravo_exports FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_bravo_exports ON sales.bravo_exports"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.bravo_export_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.bravo_export_files FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_bravo_export_files ON sales.bravo_export_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.order_bravo_read_backs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_bravo_read_backs FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_order_bravo_read_backs ON sales.order_bravo_read_backs"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

# Each outcome's `ycbg_no` is its `key` now; every other field is kept.
_RENAMED_OUTCOMES = """
    COALESCE(
        (SELECT jsonb_agg((o - 'ycbg_no') || jsonb_build_object('key', o -> 'ycbg_no'))
         FROM jsonb_array_elements(e.outcomes) AS o),
        '[]'::jsonb
    )
"""


def upgrade() -> None:
    for ddl in (_EXPORTS, _FILES, _READ_BACKS, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    for table in ("bravo_exports", "order_bravo_read_backs"):
        op.execute(
            f"CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.{table}"
            " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
        )
    for grant in _GRANTS:
        op.execute(grant)
    # The migrator bypasses RLS: every tenant's YCBG exports come across.
    op.execute(
        "INSERT INTO sales.bravo_exports (id, tenant_id, workspace_id, screen, status,"
        " uploaded_by, uploaded_at, file_name, file_sha256, file_size, outcomes, rejected,"
        " error, created_at, updated_at)"
        " SELECT e.id, e.tenant_id, e.workspace_id, 'ycbg', e.status, e.uploaded_by,"
        f" e.uploaded_at, e.file_name, e.file_sha256, e.file_size, {_RENAMED_OUTCOMES},"
        " e.rejected, e.error, e.created_at, e.updated_at FROM sales.ycbg_exports AS e"
    )
    op.execute(
        "INSERT INTO sales.bravo_export_files (tenant_id, workspace_id, export_id, content,"
        " created_at) SELECT tenant_id, workspace_id, export_id, content, created_at"
        " FROM sales.ycbg_export_files"
    )
    op.execute("DROP TABLE sales.ycbg_export_files")
    op.execute("DROP TABLE sales.ycbg_exports")


def downgrade() -> None:
    # One way: a sales-order export or a read-back has no place in ticket 16's
    # tables, and dropping them would lose what a cross-checker read. Restore
    # from a backup taken before upgrading instead.
    raise RuntimeError("7c6ad2350566 is one way: restore the database from before it to go back")
