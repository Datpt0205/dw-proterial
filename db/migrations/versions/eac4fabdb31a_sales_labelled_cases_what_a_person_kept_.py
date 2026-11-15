"""sales labelled cases what a person kept of a model's proposal

Revision ID: eac4fabdb31a
Revises: 80584b911796
Create Date: 2026-11-15 12:27:11.713533+00:00

Sales ticket 43, part 1 (dw_sales ADR 0015 decision 5): the model's proposal
stored beside what the person kept, the one piece of data the research note
found missing (`docs/research/2026-11-16-less-human-review.md` 2.6).

- **`sales.labelled_cases`**: one row per item a person decided on a model
  step's proposal (`dw_sales.domain.labelled_cases.LabelledCase`), written by
  the step's own service in the transaction of the decision. Not a column on
  `sales.step_outcomes`: that row is written when the step RUNS, holds codes
  and counts and never a value (`ck_step_outcomes_refusals`), and takes no
  UPDATE; the decision comes later, in another transaction, and its point is
  the two values.
- **The input by reference**: the message, case, attachment, line and field;
  never the mail's text. The proposal and the kept value are the step's
  typed answer as text (a code, an ISO date, a number, a layout's mapping),
  at most 16 KB each.
- **The verdict is held to the values**: rejected exactly when nothing was
  kept, confirmed exactly when the kept value is the proposal
  (`ck_labelled_cases_verdict`, jsonb equality), the rule
  `dw_sales.domain.labelled_cases.verdict_of` states; no writer decides on
  its own what a correction is. Every fixed set is CHECKed (`step` held to
  `ModelStep`, `lane`, `verdict`) and every reference to its domain shape.
- **Tenant AND workspace**, the shape every workspace-narrowed table has since
  `0d9e3f85d814`, on both sides, the DEFAULT partition policed in its own
  right.
- **Append-only**: `dw_app` holds SELECT and INSERT; UPDATE and DELETE are
  REVOKEd from the parent and the DEFAULT partition (failure-modes #7), and
  `_ensure_one_partition` withholds them from every month it makes. A second
  decision on one item is a second row; the newest is what the person kept.
- **Range-partitioned by month** on `decided_at`, named last in
  `platform.ensure_time_partitions` (redefined with the list grown by one;
  the body is `621864952a54`'s). Last because the writers insert here after
  the case event and audit rows of the same transaction, so the partition
  lane and a writer take the parents' locks in the same order (the deadlock
  `394419a5ebbd` fixed).
- **Retention**: `sales.drop_expired_labelled_cases(cutoff)`, SECURITY
  DEFINER with a fixed `search_path`, EXECUTE revoked from PUBLIC and
  granted to `dw_app`, drops the months wholly older than ``cutoff``, only
  the names `_ensure_one_partition` makes and never the DEFAULT; NULL drops
  nothing. The cutoff is the term `configs/policies/retention@1.12.0.yaml`
  gives `sales.labelled_cases` (365 days), read by the worker's
  `sales_labelled_cases_retention` lane.
- **Foreign keys to the tenant and the workspace, `ON DELETE CASCADE`**: rows
  leave with an offboarded tenant's workspaces. Each indexed on its own side.
- **Indexes led by what RLS supplies**: a step's cases newest first, and the
  counts per step, `(tenant_id, workspace_id, step, decided_at, id)`; one
  customer's, `(tenant_id, workspace_id, customer_code, step, decided_at,
  id)`.

Downgrade restores `32c1f04b76d6`'s `ensure_time_partitions`, then drops the
function and the table with its partitions.
"""

from __future__ import annotations

from alembic import op

revision = "eac4fabdb31a"
down_revision = "80584b911796"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.order_checks.ModelStep`, as `80584b911796` left it; held
# to it by `test_sales_labelled_cases.py`.
_STEPS = (
    "description_attributes",
    "message_intent",
    "rfq_extraction",
    "reply_intent",
    "request_handoff",
    "layout_proposal",
    "po_body_extraction",
    "change_request",
    "thread_agent",
    "reply_draft",
    "skill_intents",
)
_VERSION = "'^[a-z][a-z0-9_.-]*@\\d+\\.\\d+\\.\\d+$'"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_TABLE = f"""
    CREATE TABLE sales.labelled_cases (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        decided_at timestamp with time zone NOT NULL,
        step text NOT NULL,
        lane text NOT NULL,
        case_id uuid,
        customer_code text,
        message_id text NOT NULL,
        attachment_id text,
        line_no integer,
        field text NOT NULL,
        proposed jsonb NOT NULL,
        kept jsonb,
        verdict text NOT NULL,
        prompt text NOT NULL,
        model_profile text,
        rules text,
        decided_by uuid NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_labelled_cases PRIMARY KEY (id, decided_at),
        CONSTRAINT fk_labelled_cases_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_labelled_cases_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_labelled_cases_step CHECK (step IN ({_listed(_STEPS)})),
        CONSTRAINT ck_labelled_cases_lane CHECK (lane IN ('order', 'quote')),
        CONSTRAINT ck_labelled_cases_customer_code CHECK (
            customer_code ~ '^[A-Z][A-Z0-9]{{1,15}}$'
        ),
        -- PostgreSQL's regex bounds a repetition at 255 (RE_DUP_MAX): the
        -- length is its own clause, `LabelledCase.message_id`'s 512.
        CONSTRAINT ck_labelled_cases_message_id CHECK (
            message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
        ),
        CONSTRAINT ck_labelled_cases_attachment_id CHECK (
            attachment_id ~ '^[A-Za-z0-9._-]{{1,128}}$'
        ),
        CONSTRAINT ck_labelled_cases_line_no CHECK (line_no BETWEEN 1 AND 99999),
        CONSTRAINT ck_labelled_cases_field CHECK (field ~ '^[a-z_]{{1,40}}$'),
        -- The step's typed answer and the value kept, never a document.
        CONSTRAINT ck_labelled_cases_values CHECK (
            jsonb_typeof(proposed) <> 'null'
            AND octet_length(proposed::text) <= 16384
            AND (kept IS NULL OR octet_length(kept::text) <= 16384)
        ),
        -- `verdict_of`: nothing kept is rejected, the proposal kept is
        -- confirmed, any other value is corrected.
        CONSTRAINT ck_labelled_cases_verdict CHECK (
            verdict IN ('confirmed', 'corrected', 'rejected')
            AND (verdict = 'rejected') = (kept IS NULL)
            AND (kept IS NULL OR (verdict = 'confirmed') = (kept = proposed))
        ),
        CONSTRAINT ck_labelled_cases_prompt CHECK (prompt ~ {_VERSION}),
        CONSTRAINT ck_labelled_cases_model_profile CHECK (
            char_length(model_profile) BETWEEN 1 AND 64
        ),
        CONSTRAINT ck_labelled_cases_rules CHECK (rules ~ {_VERSION})
    )
    PARTITION BY RANGE (decided_at)
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration
# text. The DEFAULT partition is policed in its own right (0009).
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.labelled_cases ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.labelled_cases FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_labelled_cases ON sales.labelled_cases"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.labelled_cases_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.labelled_cases_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_labelled_cases_default ON sales.labelled_cases_default"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # A step's cases, newest first, and the counts per step
    # (`SqlLabelledCaseReader.latest`, `.counts`).
    "CREATE INDEX ix_labelled_cases_tenant_id_workspace_id_step_decided_at_id"
    " ON sales.labelled_cases (tenant_id, workspace_id, step, decided_at, id)",
    # One customer's cases of a step, newest first.
    "CREATE INDEX ix_labelled_cases_tenant_id_workspace_id_customer_code_step"
    " ON sales.labelled_cases (tenant_id, workspace_id, customer_code, step, decided_at, id)",
    # The workspace's own key, for the cascade.
    "CREATE INDEX ix_labelled_cases_workspace_id ON sales.labelled_cases (workspace_id)",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.labelled_cases TO dw_app;
            REVOKE UPDATE, DELETE ON sales.labelled_cases FROM dw_app;
            GRANT SELECT, INSERT ON sales.labelled_cases_default TO dw_app;
            REVOKE UPDATE, DELETE ON sales.labelled_cases_default FROM dw_app;
            GRANT EXECUTE ON FUNCTION sales.drop_expired_labelled_cases(timestamptz) TO dw_app;
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


# `32c1f04b76d6`'s list.
_PARENTS_BEFORE = (
    "'platform.audit_events', 'sales.case_events', 'sales.step_outcomes',"
    " 'sales.mailbox_messages', 'sales.mailbox_attachments', 'sales.mailbox_files',"
    " 'purchasing.mailbox_messages', 'purchasing.mailbox_attachments',"
    " 'purchasing.mailbox_files'"
)
_PARENTS = _PARENTS_BEFORE + ", 'sales.labelled_cases'"

# Drops the months of `sales.labelled_cases` whose whole range ends at or
# before ``cutoff``: `4bca401bcb3a`'s `drop_expired_step_outcomes` for this
# table. Only the names `_ensure_one_partition` makes are touched, never the
# DEFAULT partition or one a person added by hand.
_DROP_EXPIRED = """
CREATE FUNCTION sales.drop_expired_labelled_cases(cutoff timestamptz)
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
        WHERE n.nspname = 'sales' AND parent.relname = 'labelled_cases'
        ORDER BY child.relname
    LOOP
        CONTINUE WHEN found.part !~ '^labelled_cases_\\d{4}_\\d{2}$';
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
    op.execute(
        "CREATE TABLE sales.labelled_cases_default PARTITION OF sales.labelled_cases DEFAULT"
    )
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_DROP_EXPIRED)
    op.execute(
        "REVOKE EXECUTE ON FUNCTION sales.drop_expired_labelled_cases(timestamptz) FROM PUBLIC"
    )
    op.execute(_GRANTS)
    op.execute(_ensure_time_partitions(_PARENTS))


def downgrade() -> None:
    op.execute(_ensure_time_partitions(_PARENTS_BEFORE))
    op.execute("DROP FUNCTION sales.drop_expired_labelled_cases(timestamptz)")
    # The partitions go with their parent; no CASCADE, so anything else that
    # came to depend on the table stops the downgrade instead.
    op.execute("DROP TABLE sales.labelled_cases")
