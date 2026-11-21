"""bravo mirror of read tables

Revision ID: ffd0c95da906
Revises: af89f3f5d27d
Create Date: 2026-11-21 23:30:00.000000+00:00

Sales ticket 50, ADR 0027: Bravo's facts are read through the gateway and
kept in DW's PostgreSQL, so pages read DW's copy and say when Bravo was last
read. If Bravo is down, the copy is stale, never wrong.

- **`bravo.mirror_rows`**: one row per Bravo row of a table the gateway's
  sync serves (its allowlist of tables and columns), keyed by the table and
  Bravo's `Id`; the row's rowversion as read, its columns as JSON, and when
  a full pass stopped seeing it (`gone_at`: Bravo deleted it). Never deleted
  by DW: a row Bravo deleted is marked, and comes back if it reappears.
- **`bravo.mirror_cursors`**: per table, the highest rowversion read (the
  next pass reads what changed after it), when the last full pass and the
  last read finished, and the last error said in words.
- **Tenant only**, as every `bravo` table (Bravo is one per tenant), RLS
  enabled and forced; `dw_app` SELECT, INSERT, UPDATE, DELETE and TRUNCATE
  revoked.
- The ORDER BY the copy is read in (`table_name`, `row_id`) is the primary
  key, led by `tenant_id`.
"""

from __future__ import annotations

from alembic import op

revision = "ffd0c95da906"
down_revision = "af89f3f5d27d"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_TABLES = "('B20LME', 'B20BlackList', 'B20ExportControlList')"
_ROWVERSION = "char_length({col}) = 18 AND {col} ~ '^0x[0-9A-F]+$'"

_ROWS = f"""
    CREATE TABLE bravo.mirror_rows (
        tenant_id uuid NOT NULL,
        table_name text NOT NULL,
        row_id integer NOT NULL,
        row_version text NOT NULL,
        data jsonb NOT NULL,
        read_at timestamptz NOT NULL,
        gone_at timestamptz,
        CONSTRAINT pk_mirror_rows PRIMARY KEY (tenant_id, table_name, row_id),
        CONSTRAINT fk_mirror_rows_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_mirror_rows_table_name CHECK (table_name IN {_TABLES}),
        CONSTRAINT ck_mirror_rows_row_version CHECK ({_ROWVERSION.format(col="row_version")}),
        CONSTRAINT ck_mirror_rows_data CHECK (jsonb_typeof(data) = 'object')
    )
"""
_CURSORS = f"""
    CREATE TABLE bravo.mirror_cursors (
        tenant_id uuid NOT NULL,
        table_name text NOT NULL,
        last_row_version text,
        last_full_at timestamptz,
        last_read_at timestamptz,
        last_error text,
        last_error_at timestamptz,
        CONSTRAINT pk_mirror_cursors PRIMARY KEY (tenant_id, table_name),
        CONSTRAINT fk_mirror_cursors_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_mirror_cursors_table_name CHECK (table_name IN {_TABLES}),
        CONSTRAINT ck_mirror_cursors_row_version CHECK (
            last_row_version IS NULL OR ({_ROWVERSION.format(col="last_row_version")})),
        CONSTRAINT ck_mirror_cursors_error CHECK (
            (last_error IS NULL) = (last_error_at IS NULL)
            AND (last_error IS NULL OR char_length(last_error) BETWEEN 1 AND 300))
    )
"""
# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE bravo.mirror_rows ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.mirror_rows FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_mirror_rows ON bravo.mirror_rows"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
    "ALTER TABLE bravo.mirror_cursors ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.mirror_cursors FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_mirror_cursors ON bravo.mirror_cursors"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
)
_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE ON bravo.mirror_rows TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.mirror_rows FROM dw_app;
            GRANT SELECT, INSERT, UPDATE ON bravo.mirror_cursors TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.mirror_cursors FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    for ddl in (_ROWS, _CURSORS, *_ROW_SECURITY, _GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE bravo.mirror_cursors")
    op.execute("DROP TABLE bravo.mirror_rows")
