"""sales catalog snapshots imported and approved

Revision ID: 511ef1b71dee
Revises: d2b1394c67b1
Create Date: 2026-10-19 04:02:34.725301+00:00

Sales ticket 41 (Đạt, 2026-10-18: Proterial's master data is loaded and
updated by its business users, never hard-coded; real data replaces the mock
list by list). Each import of one list is a versioned snapshot, read in the
worker through the reader sandbox, previewed against the list in force, and
approved by a second person on a run-less platform approval
(`dw_sales.application.catalog_imports`).

- **`sales.catalog_snapshots`**: one row per import of one list
  (`ck_catalog_snapshots_list`: customers, items, convert list, quotations,
  LME; the ERP's orders and open YCBG are never imported). Who imported it,
  when (`as_of`), its `source` (`file` now, `erp` for a later Bravo sync;
  a file import names the file and its sha256, `ck_catalog_snapshots_file`),
  its status, the rows it rejected (`rejected`, a bounded array; the count
  whole), and its decision. At most one approved snapshot per list
  (`uq_catalog_snapshots_one_approved`, the list in force) and one that may
  still change (`uq_catalog_snapshots_one_open`: queued, parsed or
  submitted). A submitted snapshot names its approval, of the same tenant and
  workspace (`fk_catalog_snapshots_approval_requests`, composite, CASCADE as
  `rule_versions`) and the snapshot it was compared with
  (`fk_catalog_snapshots_base`, `SET NULL (base_snapshot_id)` only).
- **Maker and checker**: `ck_catalog_snapshots_checker_not_maker` refuses a
  decision by the importer or the submitter, whatever writes the row; the
  decision guard refuses it first. `ck_catalog_snapshots_submitted` and
  `ck_catalog_snapshots_decided` tie each status to who and when.
- **`sales.catalog_import_files`**: an uploaded file's bytes until the worker
  reads them (deleted then, or with their snapshot), at most 2 MiB.
- **`sales.catalog_rows`**: a parsed snapshot's records, by key, in file
  order. Never updated: a snapshot never changes after its parse, which is
  what lets a reader keep one by id.
- **Row security**: each table is narrowed by tenant AND workspace (a
  workspace's master data is its own, as the mock was bound to one), with
  the offboarding scope, ENABLEd and FORCEd.
- **`ck_approval_requests_sales_catalog_stamped`**: a `sales.catalog`
  approval is stamped `sales.master_data.approve`, or the INSERT fails
  (the shape of `ck_approval_requests_memory_review_stamped`).
- **Scopes**: `sales.master_data.import` for `sales_pic` and `sales_head`;
  `sales.master_data.approve` for `sales_head` only.

Grants: `dw_app` every verb on the snapshots (offboarding purges as the app
role); SELECT, INSERT and DELETE on the files and the rows, which are never
updated. Downgrade removes the scopes, the check and the tables.
"""

from __future__ import annotations

from alembic import op

revision = "511ef1b71dee"
down_revision = "d2b1394c67b1"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.master_data.CatalogList` and
# `dw_sales.application.catalog_imports.ImportStatus`; `test_sales_schema.py`
# holds the two together.
_LISTS = "('customers', 'items', 'convert_list', 'quotations', 'lme')"
_STATUSES = (
    "('queued', 'parsed', 'failed', 'submitted', 'approved', 'rejected', 'superseded', 'discarded')"
)
_SUBMITTED = "('submitted', 'approved', 'rejected', 'superseded')"
_DECIDED = "('approved', 'rejected', 'superseded')"
_WITH_ROWS = "('parsed', 'submitted', 'approved', 'rejected', 'superseded')"
_MAX_BYTES = 2 * 1024 * 1024
_IMPORT = "sales.master_data.import"
_APPROVE = "sales.master_data.approve"
_STAMPED = "ck_approval_requests_sales_catalog_stamped"

_SNAPSHOTS = f"""
    CREATE TABLE sales.catalog_snapshots (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        list text NOT NULL,
        status text NOT NULL,
        source text NOT NULL,
        file_name text,
        file_sha256 text,
        file_size integer,
        imported_by uuid NOT NULL,
        imported_at timestamptz NOT NULL,
        as_of timestamptz NOT NULL,
        error text,
        row_count integer DEFAULT 0 NOT NULL,
        rejected_count integer DEFAULT 0 NOT NULL,
        rejected jsonb DEFAULT '[]'::jsonb NOT NULL,
        unknown_headers jsonb DEFAULT '[]'::jsonb NOT NULL,
        submitted_by uuid,
        submitted_at timestamptz,
        approval_id uuid,
        base_snapshot_id uuid,
        decided_by uuid,
        decided_at timestamptz,
        comment text,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_catalog_snapshots PRIMARY KEY (id),
        CONSTRAINT fk_catalog_snapshots_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_catalog_snapshots_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_catalog_snapshots_tenant_id_workspace_id_id
            UNIQUE (tenant_id, workspace_id, id),
        CONSTRAINT fk_catalog_snapshots_approval_requests
            FOREIGN KEY (tenant_id, workspace_id, approval_id)
            REFERENCES platform.approval_requests (tenant_id, workspace_id, id)
            ON DELETE CASCADE,
        CONSTRAINT uq_catalog_snapshots_approval_id
            UNIQUE (tenant_id, workspace_id, approval_id),
        CONSTRAINT fk_catalog_snapshots_base
            FOREIGN KEY (tenant_id, workspace_id, base_snapshot_id)
            REFERENCES sales.catalog_snapshots (tenant_id, workspace_id, id)
            ON DELETE SET NULL (base_snapshot_id),
        CONSTRAINT ck_catalog_snapshots_list CHECK (list IN {_LISTS}),
        CONSTRAINT ck_catalog_snapshots_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_catalog_snapshots_source CHECK (source IN ('file', 'erp')),
        CONSTRAINT ck_catalog_snapshots_file CHECK (
            source <> 'file'
            OR (file_name IS NOT NULL AND file_sha256 IS NOT NULL AND file_size IS NOT NULL)
        ),
        CONSTRAINT ck_catalog_snapshots_file_name CHECK (char_length(file_name) BETWEEN 1 AND 200),
        CONSTRAINT ck_catalog_snapshots_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_catalog_snapshots_file_size CHECK (file_size BETWEEN 1 AND {_MAX_BYTES}),
        CONSTRAINT ck_catalog_snapshots_counts CHECK (row_count >= 0 AND rejected_count >= 0),
        CONSTRAINT ck_catalog_snapshots_rows CHECK (status NOT IN {_WITH_ROWS} OR row_count > 0),
        CONSTRAINT ck_catalog_snapshots_error CHECK (
            (status = 'failed') = (error IS NOT NULL) AND char_length(error) <= 500
        ),
        CONSTRAINT ck_catalog_snapshots_rejected CHECK (
            jsonb_typeof(rejected) = 'array' AND jsonb_typeof(unknown_headers) = 'array'
        ),
        CONSTRAINT ck_catalog_snapshots_submitted CHECK (
            (status IN {_SUBMITTED}) = (
                submitted_by IS NOT NULL AND submitted_at IS NOT NULL AND approval_id IS NOT NULL
            )
        ),
        CONSTRAINT ck_catalog_snapshots_decided CHECK (
            (status IN {_DECIDED}) = (decided_by IS NOT NULL AND decided_at IS NOT NULL)
        ),
        CONSTRAINT ck_catalog_snapshots_checker_not_maker CHECK (
            decided_by IS NULL
            OR (decided_by <> imported_by AND decided_by <> submitted_by)
        ),
        CONSTRAINT ck_catalog_snapshots_comment CHECK (char_length(comment) <= 500)
    )
"""

_FILES = f"""
    CREATE TABLE sales.catalog_import_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        snapshot_id uuid NOT NULL,
        content bytea NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_catalog_import_files PRIMARY KEY (tenant_id, workspace_id, snapshot_id),
        CONSTRAINT fk_catalog_import_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_catalog_import_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_catalog_import_files_catalog_snapshots
            FOREIGN KEY (tenant_id, workspace_id, snapshot_id)
            REFERENCES sales.catalog_snapshots (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_catalog_import_files_content
            CHECK (octet_length(content) BETWEEN 1 AND {_MAX_BYTES})
    )
"""

_ROWS = """
    CREATE TABLE sales.catalog_rows (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        snapshot_id uuid NOT NULL,
        position integer NOT NULL,
        key text NOT NULL,
        record jsonb NOT NULL,
        CONSTRAINT pk_catalog_rows PRIMARY KEY (tenant_id, workspace_id, snapshot_id, position),
        CONSTRAINT uq_catalog_rows_key UNIQUE (tenant_id, workspace_id, snapshot_id, key),
        CONSTRAINT fk_catalog_rows_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_catalog_rows_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_catalog_rows_catalog_snapshots
            FOREIGN KEY (tenant_id, workspace_id, snapshot_id)
            REFERENCES sales.catalog_snapshots (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_catalog_rows_position CHECK (position >= 0),
        CONSTRAINT ck_catalog_rows_key CHECK (char_length(key) BETWEEN 1 AND 200),
        CONSTRAINT ck_catalog_rows_record CHECK (jsonb_typeof(record) = 'object')
    )
"""

_INDEXES = (
    "CREATE UNIQUE INDEX uq_catalog_snapshots_one_approved ON sales.catalog_snapshots"
    " (tenant_id, workspace_id, list) WHERE status = 'approved'",
    "CREATE UNIQUE INDEX uq_catalog_snapshots_one_open ON sales.catalog_snapshots"
    " (tenant_id, workspace_id, list) WHERE status IN ('queued', 'parsed', 'submitted')",
    # A list's history, newest imported first, led by what RLS supplies.
    "CREATE INDEX ix_catalog_snapshots_history ON sales.catalog_snapshots"
    " (tenant_id, workspace_id, list, imported_at DESC, id DESC)",
    "CREATE INDEX ix_catalog_snapshots_workspace_id ON sales.catalog_snapshots (workspace_id)",
    "CREATE INDEX ix_catalog_snapshots_base ON sales.catalog_snapshots"
    " (tenant_id, workspace_id, base_snapshot_id)",
    "CREATE INDEX ix_catalog_import_files_workspace_id"
    " ON sales.catalog_import_files (workspace_id)",
    "CREATE INDEX ix_catalog_rows_workspace_id ON sales.catalog_rows (workspace_id)",
)

_TABLES = ("catalog_snapshots", "catalog_import_files", "catalog_rows")
_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.catalog_snapshots TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.catalog_import_files TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.catalog_rows TO dw_app",
)


# Spelled out per table, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.catalog_snapshots ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.catalog_snapshots FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_catalog_snapshots ON sales.catalog_snapshots"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.catalog_import_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.catalog_import_files FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_catalog_import_files ON sales.catalog_import_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.catalog_rows ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.catalog_rows FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_catalog_rows ON sales.catalog_rows"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_SNAPSHOTS, _FILES, _ROWS, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.catalog_snapshots"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for grant in _GRANTS:
        op.execute(grant)
    op.execute(
        f"""
        ALTER TABLE platform.approval_requests
            ADD CONSTRAINT {_STAMPED} CHECK (
                approval_type <> 'sales.catalog'
                OR coalesce(required_scope = '{_APPROVE}', false)
            )
        """
    )
    for role, scopes in (("sales_pic", (_IMPORT,)), ("sales_head", (_IMPORT, _APPROVE))):
        for scope in scopes:
            op.execute(
                f"UPDATE platform.roles SET scopes = scopes || '[\"{scope}\"]'::jsonb"
                f" WHERE key = '{role}' AND NOT scopes ? '{scope}'"
            )


def downgrade() -> None:
    for scope in (_IMPORT, _APPROVE):
        op.execute(
            f"UPDATE platform.roles SET scopes = scopes - '{scope}'"
            " WHERE key IN ('sales_pic', 'sales_head')"
        )
    op.execute(f"ALTER TABLE platform.approval_requests DROP CONSTRAINT IF EXISTS {_STAMPED}")
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE sales.{table}")
