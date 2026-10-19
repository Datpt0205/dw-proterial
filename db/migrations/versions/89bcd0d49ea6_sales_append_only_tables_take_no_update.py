"""sales append-only tables take no update

Revision ID: 89bcd0d49ea6
Revises: 511ef1b71dee
Create Date: 2026-10-19 09:26:27.021590+00:00

`d2b1394c67b1` (ticket 42) and `511ef1b71dee` (ticket 41) granted `dw_app`
SELECT, INSERT and DELETE on three tables a row of which is never rewritten:
`sales.followup_deliveries`, `sales.catalog_import_files` and
`sales.catalog_rows`. A GRANT adds and never takes away, and the sales
schema's `ALTER DEFAULT PRIVILEGES` had already handed each new table UPDATE,
so the application could rewrite a sent follow-up, an uploaded file's bytes
or an approved snapshot's records (measured 2026-10-19:
`test_privileges.py` and `test_sales_followups_db.py`, the first integration
run since both tickets). The same default is why
`platform.ensure_time_partitions` revokes it from every partition.

Downgrade leaves the revoke in place: handing the application UPDATE back
would reopen the hole this closes, and no code path needs it.
"""

from __future__ import annotations

from alembic import op

revision = "89bcd0d49ea6"
down_revision = "511ef1b71dee"
branch_labels = None
depends_on = None

_REVOKE = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            REVOKE UPDATE ON sales.followup_deliveries FROM dw_app;
            REVOKE UPDATE ON sales.catalog_import_files FROM dw_app;
            REVOKE UPDATE ON sales.catalog_rows FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_REVOKE)


def downgrade() -> None:
    pass
