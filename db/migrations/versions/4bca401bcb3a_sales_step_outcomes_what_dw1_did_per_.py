"""sales step outcomes what dw1 did per step

Revision ID: 4bca401bcb3a
Revises: 2d97d03c937a
Create Date: 2026-10-23 10:49:38.350239+00:00

Slice 3, "AI activity": what DW1's model steps did, for one case and over
time. Each step stamps WHAT it read on what it produced (a line's
`description_reading`, a message's `model_reading`, `handoff`,
`layout_prefill`, `case_reply`, a quote's `request.reading`); nothing held
WHEN it ran, for HOW LONG, on WHICH model (a stamp names the profile), the
outcome in one queryable shape, or a step that ran and left no stamp (a
request no model reading could extract is routed with no case). The model
usage ledger that once held call times is gone (`aefe7c1f5d9b`); a call's
latency reaches telemetry only.

- **`sales.step_outcomes`**: one row per item a model step handled (a line
  for the description reading, the message otherwise), written by
  `InboxProcessing` in the transaction that writes the message's disposition
  and its case (`dw_sales.domain.activity.StepOutcome`). Ids, codes, counts
  and times only: no value read, no prompt, no model's words; `refusals` is
  reason codes and counts, `ck_step_outcomes_refusals` refuses anything else.
- **Fixed sets are CHECKed**: `step` (`ModelStep`), `result`, `lane`
  (`CaseKind`), held to the domain by `test_sales_step_outcomes.py`; and the
  row's own consistency (an automatic item was accepted with no reason; a
  refused one names its reason; no answer has none; a duration is the
  duration of calls).
- **Tenant AND workspace**, in the shape every workspace-narrowed table has
  since `0d9e3f85d814`: `tenant AND (workspace OR app.workspace_scope =
  'tenant')`, on both sides, so the offboarding lane exports it.
- **Append-only**: `dw_app` holds SELECT and INSERT. The schema's default
  privileges hand a new table UPDATE and DELETE and a GRANT never takes one
  away (failure-modes #7), so both are REVOKEd, from the parent and the
  DEFAULT partition; `platform._ensure_one_partition` withholds them from each
  month it makes because the parent does not hold them.
- **Range-partitioned by month** on `occurred_at`, with a DEFAULT partition
  policed in its own right. `platform.ensure_time_partitions` names the table
  beside the audit and case event logs (redefined here with the list grown by
  one; the rest of its body is `621864952a54`'s), so the worker's
  `partitions` lane creates each month ahead with RLS ENABLEd, FORCEd, the
  parent's policy and the revokes.
- **Retention**: `sales.drop_expired_step_outcomes(cutoff)`, SECURITY DEFINER
  with a fixed `search_path`, EXECUTE revoked from PUBLIC and granted to
  `dw_app`, drops the months wholly older than ``cutoff``, only the names
  `_ensure_one_partition` makes and never the DEFAULT. NULL drops nothing.
  The cutoff is the term `configs/policies/retention@1.9.0.yaml` gives
  `sales.step_outcomes` (365 days), read by the worker's
  `sales_step_outcomes_retention` lane.
- **Foreign keys to the tenant and the workspace, `ON DELETE CASCADE`**, as
  `sales.model_step_measurements`: rows leave with an offboarded tenant's
  workspaces instead of waiting for their month to expire. Each is indexed on
  its own side.
- **Indexes led by what RLS supplies**: one case's entries,
  `(tenant_id, case_id, occurred_at, id)`; a workspace's window,
  `(tenant_id, workspace_id, occurred_at, id)`; the cases one step's rows
  name over a window, the activity page's drill-down into a case list,
  `(tenant_id, workspace_id, step, occurred_at)`.

Downgrade restores `621864952a54`'s `ensure_time_partitions`, then drops the
function and the table with its partitions.
"""

from __future__ import annotations

from alembic import op

revision = "4bca401bcb3a"
down_revision = "2d97d03c937a"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.order_checks.ModelStep`, held to it by
# `test_sales_step_outcomes.py`.
_STEPS = (
    "('description_attributes', 'message_intent', 'rfq_extraction', 'reply_intent',"
    " 'request_handoff', 'layout_proposal')"
)
_CODE = "'^[a-z_]{1,40}$'"

_TABLE = f"""
    CREATE TABLE sales.step_outcomes (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        occurred_at timestamp with time zone NOT NULL,
        message_id text NOT NULL,
        lane text,
        case_id uuid,
        line_no integer,
        step text NOT NULL,
        result text NOT NULL,
        automatic boolean NOT NULL,
        reason_code text,
        refusals jsonb NOT NULL,
        prompt text NOT NULL,
        model_profile text NOT NULL,
        model text,
        calls integer NOT NULL,
        duration_ms integer,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_step_outcomes PRIMARY KEY (id, occurred_at),
        CONSTRAINT fk_step_outcomes_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_step_outcomes_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        -- PostgreSQL's regex bounds a repetition at 255 (RE_DUP_MAX): the
        -- length is its own clause, `StepOutcome.message_id`'s 512.
        CONSTRAINT ck_step_outcomes_message_id CHECK (
            message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
        ),
        CONSTRAINT ck_step_outcomes_lane CHECK (lane IN ('order', 'quote')),
        CONSTRAINT ck_step_outcomes_case CHECK (case_id IS NULL OR lane IS NOT NULL),
        CONSTRAINT ck_step_outcomes_line_no CHECK (line_no BETWEEN 1 AND 99999),
        CONSTRAINT ck_step_outcomes_step CHECK (step IN {_STEPS}),
        CONSTRAINT ck_step_outcomes_result CHECK (
            result IN ('accepted', 'refused', 'unavailable')
        ),
        CONSTRAINT ck_step_outcomes_reason_code CHECK (reason_code ~ {_CODE}),
        -- An automatic item was accepted, with no reason; a refused one names
        -- why; one with no answer went to a person, with no reason.
        CONSTRAINT ck_step_outcomes_outcome CHECK (
            (NOT automatic OR (result = 'accepted' AND reason_code IS NULL))
            AND (result <> 'refused' OR reason_code IS NOT NULL)
            AND (result <> 'unavailable' OR (NOT automatic AND reason_code IS NULL))
        ),
        -- Reason codes and counts, nothing else: no place for a value.
        CONSTRAINT ck_step_outcomes_refusals CHECK (
            jsonb_typeof(refusals) = 'object'
            AND NOT jsonb_path_exists(
                refusals,
                '$.keyvalue() ? (!(@.key like_regex "^[a-z_]{{1,40}}$")
                    || @.value.type() != "number" || @.value < 1)'
            )
        ),
        CONSTRAINT ck_step_outcomes_prompt CHECK (
            prompt ~ '^[a-z][a-z0-9_.]*@\\d+\\.\\d+\\.\\d+$'
        ),
        CONSTRAINT ck_step_outcomes_model_profile CHECK (
            char_length(model_profile) BETWEEN 1 AND 64
        ),
        CONSTRAINT ck_step_outcomes_model CHECK (char_length(model) BETWEEN 1 AND 200),
        CONSTRAINT ck_step_outcomes_calls CHECK (calls BETWEEN 0 AND 1000),
        CONSTRAINT ck_step_outcomes_duration CHECK (
            (calls = 0) = (duration_ms IS NULL) AND (duration_ms IS NULL OR duration_ms >= 0)
        )
    )
    PARTITION BY RANGE (occurred_at)
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration
# text. The DEFAULT partition is policed in its own right (0009).
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.step_outcomes ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.step_outcomes FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_step_outcomes ON sales.step_outcomes"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.step_outcomes_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.step_outcomes_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_step_outcomes_default ON sales.step_outcomes_default"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # One case's entries, oldest first (`GET .../{case_id}/activity`).
    "CREATE INDEX ix_step_outcomes_tenant_id_case_id_occurred_at_id"
    " ON sales.step_outcomes (tenant_id, case_id, occurred_at, id)",
    # A workspace's window (`GET /sales/activity`), and the process page's week.
    "CREATE INDEX ix_step_outcomes_tenant_id_workspace_id_occurred_at_id"
    " ON sales.step_outcomes (tenant_id, workspace_id, occurred_at, id)",
    # The cases one step's rows name over a window (a case list narrowed by
    # the activity page's filter, `SqlStepActivityReader.cases`).
    "CREATE INDEX ix_step_outcomes_tenant_id_workspace_id_step_occurred_at"
    " ON sales.step_outcomes (tenant_id, workspace_id, step, occurred_at)",
    # The workspace's own key, for the cascade.
    "CREATE INDEX ix_step_outcomes_workspace_id ON sales.step_outcomes (workspace_id)",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.step_outcomes TO dw_app;
            REVOKE UPDATE, DELETE ON sales.step_outcomes FROM dw_app;
            GRANT SELECT, INSERT ON sales.step_outcomes_default TO dw_app;
            REVOKE UPDATE, DELETE ON sales.step_outcomes_default FROM dw_app;
            GRANT EXECUTE ON FUNCTION sales.drop_expired_step_outcomes(timestamptz) TO dw_app;
        END IF;
    END
    $$
"""


def _ensure_time_partitions(parents: str) -> str:
    """`621864952a54`'s body, with the parents it names."""
    return f"""
CREATE OR REPLACE FUNCTION platform.ensure_time_partitions(months_ahead integer)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    parent text;
    step integer;
    made text;
    first_month constant date := date_trunc('month', now())::date;
BEGIN
    IF months_ahead IS NULL OR months_ahead < 1 OR months_ahead > 24 THEN
        RAISE EXCEPTION 'months_ahead must be between 1 and 24, got %', months_ahead;
    END IF;
    -- The parents are a constant: no caller-supplied string names a table.
    FOREACH parent IN ARRAY ARRAY[{parents}] LOOP
        FOR step IN 0..months_ahead LOOP
            made := platform._ensure_one_partition(
                parent, (first_month + (step || ' month')::interval)::date
            );
            IF made IS NOT NULL THEN
                RETURN NEXT made;
            END IF;
        END LOOP;
    END LOOP;
END;
$fn$
"""


_PARENTS_BEFORE = "'platform.audit_events', 'sales.case_events'"
_PARENTS = "'platform.audit_events', 'sales.case_events', 'sales.step_outcomes'"

# Drops the months of `sales.step_outcomes` whose whole range ends at or
# before ``cutoff``. The table is a constant; only the names
# `_ensure_one_partition` makes are touched, never the DEFAULT partition or
# one a person added by hand.
_DROP_EXPIRED = """
CREATE FUNCTION sales.drop_expired_step_outcomes(cutoff timestamptz)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    found record;
    range_end timestamptz;
BEGIN
    -- NULL: no term, or a term not enforced. Nothing is dropped.
    IF cutoff IS NULL THEN
        RETURN;
    END IF;
    FOR found IN
        SELECT child.relname AS part
        FROM pg_inherits i
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE n.nspname = 'sales' AND parent.relname = 'step_outcomes'
        ORDER BY child.relname
    LOOP
        CONTINUE WHEN found.part !~ '^step_outcomes_\\d{4}_\\d{2}$';
        range_end := to_date(right(found.part, 7), 'YYYY_MM') + interval '1 month';
        IF range_end <= cutoff THEN
            EXECUTE format('DROP TABLE sales.%I', found.part);
            RETURN NEXT found.part;
        END IF;
    END LOOP;
END;
$fn$
"""


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute("CREATE TABLE sales.step_outcomes_default PARTITION OF sales.step_outcomes DEFAULT")
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_DROP_EXPIRED)
    op.execute(
        "REVOKE EXECUTE ON FUNCTION sales.drop_expired_step_outcomes(timestamptz) FROM PUBLIC"
    )
    op.execute(_GRANTS)
    op.execute(_ensure_time_partitions(_PARENTS))


def downgrade() -> None:
    op.execute(_ensure_time_partitions(_PARENTS_BEFORE))
    op.execute("DROP FUNCTION sales.drop_expired_step_outcomes(timestamptz)")
    # The partitions go with their parent; no CASCADE, so anything else that
    # came to depend on the table stops the downgrade instead.
    op.execute("DROP TABLE sales.step_outcomes")
