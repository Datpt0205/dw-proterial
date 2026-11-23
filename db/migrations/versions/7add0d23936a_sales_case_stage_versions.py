"""sales case stage versions

Revision ID: 7add0d23936a
Revises: 4b3f44f30356
Create Date: 2026-11-23

Sales ticket 61, step 2 (Đạt, 2026-11-23): a case finishes on the stage
versions it was opened with (`dw_sales.application.stages`).

- **`stage_versions jsonb NOT NULL`** on `sales.order_cases` and
  `sales.quote_cases`: `{"<stage>": "<semver>"}`, written by the application
  when the case is opened. No column default: the versions a new case takes
  have one owner (`STAGE_DEFAULTS`), and a default here would be a second.
  Every case open before this revision ran on what is now `write_bravo`
  1.0.0, so that is what they are stamped with. `ck_*_stage_versions`: an
  object.
- **`sales.refuse_stage_versions_change()`**, a BEFORE UPDATE trigger on both
  tables: the stamp never moves, from any role (a past pin must not change
  under the case, as the `updated_at` rule's spirit has it for a decision).
- **`sales.open_cases_by_stage()`**, SECURITY DEFINER: per (stage, version),
  how many cases are still open, across tenants, counts only; start-up
  refuses to drop a handler while it is not zero. An order is open until
  `closed`, a quotation until `declined` or `master_list_recorded`.

Grants: `dw_app` the function; the columns ride on the tables' grants.
Downgrade drops the function, the triggers and the columns.
"""

from __future__ import annotations

from alembic import op

revision = "7add0d23936a"
down_revision = "4b3f44f30356"
branch_labels = None
depends_on = None

_TABLES = ("order_cases", "quote_cases")
_BACKFILL = '{"write_bravo": "1.0.0"}'

_REFUSE = """
    CREATE OR REPLACE FUNCTION sales.refuse_stage_versions_change()
    RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, sales
    AS $$
    BEGIN
        IF NEW.stage_versions IS DISTINCT FROM OLD.stage_versions THEN
            RAISE EXCEPTION 'a case keeps the stage versions it was opened with'
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'ck_' || TG_TABLE_NAME || '_stage_versions_stamped';
        END IF;
        RETURN NEW;
    END
    $$
"""

_OPEN = """
    CREATE OR REPLACE FUNCTION sales.open_cases_by_stage()
    RETURNS TABLE (stage text, version text, open_cases bigint)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        SELECT s.key, s.value, count(*)
        FROM (
            SELECT c.stage_versions FROM sales.order_cases c WHERE c.status <> 'closed'
            UNION ALL
            SELECT q.stage_versions FROM sales.quote_cases q
            WHERE q.status NOT IN ('declined', 'master_list_recorded')
        ) open_cases, jsonb_each_text(open_cases.stage_versions) s
        GROUP BY s.key, s.value
        ORDER BY s.key, s.value
    $$
"""


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE sales.{table} ADD COLUMN stage_versions jsonb")
        op.execute(f"UPDATE sales.{table} SET stage_versions = '{_BACKFILL}'::jsonb")
        op.execute(f"ALTER TABLE sales.{table} ALTER COLUMN stage_versions SET NOT NULL")
        op.execute(
            f"ALTER TABLE sales.{table} ADD CONSTRAINT ck_{table}_stage_versions"
            " CHECK (jsonb_typeof(stage_versions) = 'object')"
        )
    op.execute(_REFUSE)
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER refuse_stage_versions_change BEFORE UPDATE ON sales.{table}"
            " FOR EACH ROW EXECUTE FUNCTION sales.refuse_stage_versions_change()"
        )
    op.execute(_OPEN)
    op.execute("REVOKE ALL ON FUNCTION sales.open_cases_by_stage() FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                GRANT EXECUTE ON FUNCTION sales.open_cases_by_stage() TO dw_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS sales.open_cases_by_stage()")
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS refuse_stage_versions_change ON sales.{table}")
    op.execute("DROP FUNCTION IF EXISTS sales.refuse_stage_versions_change()")
    for table in _TABLES:
        op.execute(f"ALTER TABLE sales.{table} DROP COLUMN stage_versions")
