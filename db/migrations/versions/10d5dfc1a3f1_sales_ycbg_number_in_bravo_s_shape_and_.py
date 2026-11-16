"""sales ycbg number in Bravo's shape and Design's result read from Bravo

Revision ID: 10d5dfc1a3f1
Revises: 3d139b41fec1
Create Date: 2026-11-16 07:23:56.003913+00:00

dw_sales ticket 16. Bravo numbers a quote request (YCBG) ``RFQ`` + yymmdd +
``-`` + nnn (``RFQ261110-002``, Box 11-10), and Design writes its result on
the YCBG's lines in Bravo: QUOTE or DECLINE, a reason and the BP code, and
the line's status goes CLOSE (Box B16). Until the vendor's API reads a
request back (R13), Sales uploads Bravo's YCBG export and the worker reads
it (`dw_sales.application.ycbg_exports`).

- **`ck_quote_cases_ycbg_no`** now holds the recorded number to Bravo's
  shape, `^RFQ[0-9]{6}-[0-9]{3}$` (repetition counts far below PostgreSQL's
  255, failure-modes #4; tested against the database). **Existing rows that
  do not fit** (numbers typed before ticket 16, the demo's `YCBG-2609-030`)
  are neither rewritten nor allowed to break this migration: no number Bravo
  did not give can be invented, and clearing one would orphan the Design
  reply matched by it. So the constraint is added `NOT VALID` and validated
  at once only when every row fits. Either way every INSERT and UPDATE from
  now on is held to it: a case still holding an old number can be read but
  no longer written (fail closed), so it can match no Bravo result; Sales
  declines it and opens the request again. The count of such rows is
  printed, so the deployment log says whether any were found.
- **`sales.ycbg_exports`**: one row per uploaded YCBG export. Who uploaded it
  and when, the file's name, sha256 and size, its status
  (`ck_ycbg_exports_status`: queued, read, failed), what became of each YCBG
  number in it (`outcomes`) and the rows that could not be read
  (`rejected`), and why it failed (`ck_ycbg_exports_error`: exactly when
  failed). `ix_ycbg_exports_uploaded` carries the list of the latest and the
  prune by age, led by what RLS supplies.
- **`sales.ycbg_export_files`**: an export's bytes until the worker reads
  them (deleted then, or with their export), at most 2 MiB. Never updated.
- **Row security**: both narrowed by tenant AND workspace with the
  offboarding scope, ENABLEd and FORCEd.

Grants: `dw_app` every verb on the exports (the worker settles them, an
upload prunes old ones and fails stale ones, offboarding purges); SELECT,
INSERT and DELETE on the files, and UPDATE revoked, which the sales schema's
default privileges would otherwise give (`89bcd0d49ea6`). Downgrade drops
both tables and restores the document-number CHECK.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "10d5dfc1a3f1"
down_revision = "3d139b41fec1"
branch_labels = None
depends_on = None

# `dw_sales.domain.quotes.YCBG_NO_PATTERN`; `test_ycbg_exports_db.py` holds
# the two together against the database.
_YCBG_NO = "'^RFQ[0-9]{6}-[0-9]{3}$'"
_DOCUMENT_NO = "'^[A-Z0-9][A-Z0-9/-]{1,31}$'"

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.application.ycbg_exports.ExportStatus`; `test_sales_schema.py`
# holds the two together.
_STATUSES = "('queued', 'read', 'failed')"
_MAX_BYTES = 2 * 1024 * 1024

_EXPORTS = f"""
    CREATE TABLE sales.ycbg_exports (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
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
        CONSTRAINT pk_ycbg_exports PRIMARY KEY (id),
        CONSTRAINT fk_ycbg_exports_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_ycbg_exports_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_ycbg_exports_tenant_id_workspace_id_id UNIQUE (tenant_id, workspace_id, id),
        CONSTRAINT ck_ycbg_exports_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_ycbg_exports_file_name CHECK (char_length(file_name) BETWEEN 1 AND 200),
        CONSTRAINT ck_ycbg_exports_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_ycbg_exports_file_size CHECK (file_size BETWEEN 1 AND {_MAX_BYTES}),
        CONSTRAINT ck_ycbg_exports_shapes CHECK (
            jsonb_typeof(outcomes) = 'array' AND jsonb_typeof(rejected) = 'array'
        ),
        -- Only a read export has outcomes to show.
        CONSTRAINT ck_ycbg_exports_outcomes CHECK (
            status = 'read' OR (outcomes = '[]'::jsonb AND rejected = '[]'::jsonb)
        ),
        CONSTRAINT ck_ycbg_exports_error CHECK (
            (status = 'failed') = (error IS NOT NULL) AND char_length(error) <= 500
        )
    )
"""

_FILES = f"""
    CREATE TABLE sales.ycbg_export_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        export_id uuid NOT NULL,
        content bytea NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_ycbg_export_files PRIMARY KEY (tenant_id, workspace_id, export_id),
        CONSTRAINT fk_ycbg_export_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_ycbg_export_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_ycbg_export_files_ycbg_exports
            FOREIGN KEY (tenant_id, workspace_id, export_id)
            REFERENCES sales.ycbg_exports (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_ycbg_export_files_content
            CHECK (octet_length(content) BETWEEN 1 AND {_MAX_BYTES})
    )
"""

_INDEXES = (
    # The latest exports, and the prune by age, led by what RLS supplies.
    "CREATE INDEX ix_ycbg_exports_uploaded ON sales.ycbg_exports"
    " (tenant_id, workspace_id, uploaded_at)",
    "CREATE INDEX ix_ycbg_exports_workspace_id ON sales.ycbg_exports (workspace_id)",
    "CREATE INDEX ix_ycbg_export_files_workspace_id ON sales.ycbg_export_files (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.ycbg_exports TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.ycbg_export_files TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE ON sales.ycbg_export_files FROM dw_app",
)

# Spelled out per table, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.ycbg_exports ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.ycbg_exports FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_ycbg_exports ON sales.ycbg_exports"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.ycbg_export_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.ycbg_export_files FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_ycbg_export_files ON sales.ycbg_export_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def _ycbg_number_check() -> None:
    op.execute("ALTER TABLE sales.quote_cases DROP CONSTRAINT ck_quote_cases_ycbg_no")
    op.execute(
        "ALTER TABLE sales.quote_cases ADD CONSTRAINT ck_quote_cases_ycbg_no"
        f" CHECK (ycbg_no ~ {_YCBG_NO}) NOT VALID"
    )
    # The migrator bypasses RLS: this counts every tenant's rows.
    unfit = op.get_bind().scalar(
        sa.text(f"SELECT count(*) FROM sales.quote_cases WHERE NOT (ycbg_no ~ {_YCBG_NO})")
    )
    if unfit:
        print(
            f"ck_quote_cases_ycbg_no left NOT VALID: {unfit} quote case(s) hold a YCBG"
            " number recorded before Bravo's shape; they read, and refuse every write"
        )
    else:
        op.execute("ALTER TABLE sales.quote_cases VALIDATE CONSTRAINT ck_quote_cases_ycbg_no")


def upgrade() -> None:
    _ycbg_number_check()
    for ddl in (_EXPORTS, _FILES, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.ycbg_exports"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for grant in _GRANTS:
        op.execute(grant)


def downgrade() -> None:
    op.execute("DROP TABLE sales.ycbg_export_files")
    op.execute("DROP TABLE sales.ycbg_exports")
    op.execute("ALTER TABLE sales.quote_cases DROP CONSTRAINT ck_quote_cases_ycbg_no")
    op.execute(
        "ALTER TABLE sales.quote_cases ADD CONSTRAINT ck_quote_cases_ycbg_no"
        f" CHECK (ycbg_no ~ {_DOCUMENT_NO})"
    )
