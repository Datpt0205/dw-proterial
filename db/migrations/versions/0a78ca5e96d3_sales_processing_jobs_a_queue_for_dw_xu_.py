"""sales processing jobs a queue for DW xu ly

Revision ID: 0a78ca5e96d3
Revises: 26a5276840ba
Create Date: 2026-10-14 03:09:57.736001+00:00

Sales ticket 25 (decided by Đạt 2026-10-14: "DW xử lý" becomes asynchronous).
The button, "DW xử lý tất cả" and DW1's mailbox lane (ticket 16) enqueue a
message here; the worker's `sales_processing` lane drains it, reading every
file through the reader sandbox, and settles the row.

- **`sales.processing_jobs`**: one row per message per workspace
  (`uq_processing_jobs_message`, the (workspace, message_id) idempotency
  key): enqueueing a message already queued or running returns that row, and
  enqueueing a finished one puts the same row back in the queue. The table is
  bounded by the mailbox, like `sales.messages`, and leaves with its
  workspace or tenant (CASCADE) or through offboarding's purge.
- **Order**: due jobs run oldest `available_at` first, then by `seq`, the
  order they were queued in, so "DW xử lý tất cả" runs the mailbox oldest
  first as it did in one run (an original PO before its revision).
- **States** `queued | running | done | failed`, each with what it needs:
  a running row has its claim time (`ck_processing_jobs_claimed`), a failed
  one its reason from a fixed set (`ck_processing_jobs_error`,
  `ck_processing_jobs_error_code`), so an unknown reason is refused, not
  stored.
- **Workspace RLS**, ENABLEd and FORCEd, the one shape `CLAUDE.md` allows.
- **`sales.processing_scopes_due()`**, SECURITY DEFINER: the one read that
  crosses tenants, so the lane knows whom to visit; tenant and workspace ids
  only. The claim then runs under that scope's RLS, `FOR UPDATE SKIP LOCKED`
  (`platform.channel_delivery_scopes_due` is the same shape).
- **`sales.reap_processing_jobs(older_than, max_attempts)`**, SECURITY
  DEFINER: the worker's reaper returns a row a dead worker left running to
  the queue, or fails it (`abandoned`) once its attempts are spent. It touches
  nothing but rows running since before `older_than`, and returns their ids.
- **`updated_at`** by `platform.touch_updated_at()`.

Grants: `dw_app` the table and both functions, nobody else the functions.
"""

from __future__ import annotations

from alembic import op

revision = "0a78ca5e96d3"
down_revision = "26a5276840ba"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_STATUSES = "('queued', 'running', 'done', 'failed')"
# `dw_sales.application.processing.JobError`; `test_sales_schema.py` holds the two together.
_ERRORS = (
    "('quota', 'not_permitted', 'paused', 'conflict', 'not_found', 'unavailable',"
    " 'model_retry', 'abandoned', 'error')"
)
_MESSAGE_ID = r"'^[!-~]{1,512}$'"

_TABLE = f"""
    CREATE TABLE sales.processing_jobs (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        -- The order jobs queued at one instant are run in: the mailbox's.
        seq bigint GENERATED ALWAYS AS IDENTITY,
        status text NOT NULL,
        requested_by uuid NOT NULL,
        requested_at timestamp with time zone NOT NULL,
        attempts integer NOT NULL DEFAULT 0,
        failures integer NOT NULL DEFAULT 0,
        available_at timestamp with time zone NOT NULL,
        claimed_at timestamp with time zone,
        error text,
        created_at timestamp with time zone NOT NULL DEFAULT now(),
        updated_at timestamp with time zone NOT NULL DEFAULT now(),
        CONSTRAINT pk_processing_jobs PRIMARY KEY (id),
        CONSTRAINT fk_processing_jobs_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_processing_jobs_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_processing_jobs_message UNIQUE (tenant_id, workspace_id, message_id),
        CONSTRAINT ck_processing_jobs_message_id CHECK (message_id ~ {_MESSAGE_ID}),
        CONSTRAINT ck_processing_jobs_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_processing_jobs_attempts CHECK (attempts >= 0),
        CONSTRAINT ck_processing_jobs_failures CHECK (failures >= 0),
        CONSTRAINT ck_processing_jobs_claimed CHECK ((status = 'running') = (claimed_at IS NOT NULL)),
        CONSTRAINT ck_processing_jobs_error CHECK ((status = 'failed') = (error IS NOT NULL)),
        CONSTRAINT ck_processing_jobs_error_code CHECK (error IS NULL OR error IN {_ERRORS})
    )
"""

_ROW_SECURITY = (
    "ALTER TABLE sales.processing_jobs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.processing_jobs FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_processing_jobs ON sales.processing_jobs"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES = (
    # The queue: what the drain claims in a scope, oldest due first, and the
    # scopes with anything due, led by what row security supplies.
    "CREATE INDEX ix_processing_jobs_queued"
    " ON sales.processing_jobs (tenant_id, workspace_id, available_at, seq)"
    " WHERE status = 'queued'",
    # What the reaper looks for: rows running since before its window.
    "CREATE INDEX ix_processing_jobs_running"
    " ON sales.processing_jobs (claimed_at) WHERE status = 'running'",
    "CREATE INDEX ix_processing_jobs_workspace_id ON sales.processing_jobs (workspace_id)",
)

_SCOPES_DUE = """
    CREATE OR REPLACE FUNCTION sales.processing_scopes_due()
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        SELECT DISTINCT j.tenant_id, j.workspace_id
        FROM sales.processing_jobs j
        WHERE j.status = 'queued'
          AND j.available_at <= now()
        ORDER BY j.tenant_id, j.workspace_id
    $$
"""

_REAP = """
    CREATE OR REPLACE FUNCTION sales.reap_processing_jobs(
        p_older_than timestamp with time zone, p_max_attempts integer
    )
    RETURNS TABLE (id uuid)
    LANGUAGE sql
    VOLATILE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        UPDATE sales.processing_jobs j
        SET status = CASE WHEN j.attempts >= p_max_attempts THEN 'failed' ELSE 'queued' END,
            error = CASE WHEN j.attempts >= p_max_attempts THEN 'abandoned' END,
            failures = CASE WHEN j.attempts >= p_max_attempts
                            THEN j.failures + 1 ELSE j.failures END,
            claimed_at = NULL,
            available_at = now()
        WHERE j.status = 'running'
          AND j.claimed_at < p_older_than
        RETURNING j.id
    $$
"""

_FUNCTIONS = (
    "sales.processing_scopes_due()",
    "sales.reap_processing_jobs(timestamp with time zone, integer)",
)

_GRANT = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON sales.processing_jobs TO dw_app;
            GRANT EXECUTE ON FUNCTION sales.processing_scopes_due() TO dw_app;
            GRANT EXECUTE ON FUNCTION
                sales.reap_processing_jobs(timestamp with time zone, integer) TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_TABLE)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.processing_jobs"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    op.execute(_SCOPES_DUE)
    op.execute(_REAP)
    for function in _FUNCTIONS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute("DROP FUNCTION sales.reap_processing_jobs(timestamp with time zone, integer)")
    op.execute("DROP FUNCTION sales.processing_scopes_due()")
    op.execute("DROP TABLE sales.processing_jobs")
