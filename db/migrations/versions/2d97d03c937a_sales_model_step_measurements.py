"""sales model step measurements

Revision ID: 2d97d03c937a
Revises: e8192ed5cc59
Create Date: 2026-10-23 10:00:38.482277+00:00

dw_sales ADR 0005, addendum of 2026-10-23: a tenant turns a model step on
(`sales_order_rules.model_assist.<step>`) only once that step's live eval met
its bar, for the model the tenant's profile routes the step to and the prompt
version the step pins. Until now nothing a running process could read held
that measurement: the bars were constants in the eval modules and the results
gitignored files on whoever ran the live lane.

- **`sales.model_step_measurements`**: one row per live measurement of one
  step, written by `scripts/run_evals.py --live <profile> --attest` as the
  lane `sales_model_attest` (ADR 0011: `recorded_by` reads `system:<lane>`,
  and the audit event is written in the same transaction). The bar the step
  had when it was measured is kept beside the value: a bar raised later does
  not make an old row pass, because the reader holds it to today's bar too.
  `ck_model_step_measurements_passed`: a passing row is at or above its bar.
- **Tenant data, narrowed by tenant only**, the shape `sales.rule_versions`
  has: the switch it backs is in the tenant's rules, which apply in every
  workspace (`workspace_id` records which one the measurement was recorded
  in). RLS is enabled and FORCEd.
- **Append-only**: `dw_app` holds SELECT and INSERT. The schema's default
  privileges hand a new table UPDATE and DELETE, and a GRANT never takes one
  away (failure-modes #7, `89bcd0d49ea6`), so both are REVOKEd here. Offboarding
  purges only what `dw_app` may DELETE; these rows go with the tenant's
  workspaces (`ON DELETE CASCADE`), as `sales.case_events` do.
- **Not partitioned**: a row is written per attested step by a person running
  the live lane (six steps), not per message, so the table stays small; a
  lane that writes per message would partition.

Downgrade drops the table.
"""

from __future__ import annotations

from alembic import op

revision = "2d97d03c937a"
down_revision = "e8192ed5cc59"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
# The model steps (`dw_sales.application.model_readiness.ModelStep`, held to
# this list by `test_sales_schema.py`).
_STEPS = (
    "('description_attributes', 'message_intent', 'rfq_extraction', 'reply_intent',"
    " 'request_handoff', 'layout_proposal')"
)
# One line: `verify_invariants.py` reads the migration's text for it.
_POLICY = "CREATE POLICY tenant_isolation_model_step_measurements ON sales.model_step_measurements"
_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.model_step_measurements TO dw_app;
            REVOKE UPDATE, DELETE ON sales.model_step_measurements FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE sales.model_step_measurements (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            step text NOT NULL,
            model text NOT NULL,
            prompt text NOT NULL,
            metric text NOT NULL,
            value numeric(5, 4) NOT NULL,
            bar numeric(5, 4) NOT NULL,
            passed boolean NOT NULL,
            dataset text NOT NULL,
            measured_at timestamptz NOT NULL,
            recorded_by text NOT NULL,
            created_at timestamptz DEFAULT now() NOT NULL,
            CONSTRAINT pk_model_step_measurements PRIMARY KEY (id),
            CONSTRAINT fk_model_step_measurements_tenant_id_tenants FOREIGN KEY (tenant_id)
                REFERENCES platform.tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_model_step_measurements_workspace_id_workspaces FOREIGN KEY (workspace_id)
                REFERENCES platform.workspaces (id) ON DELETE CASCADE,
            CONSTRAINT ck_model_step_measurements_step CHECK (step IN {_STEPS}),
            CONSTRAINT ck_model_step_measurements_model CHECK (
                char_length(model) BETWEEN 1 AND 200
            ),
            CONSTRAINT ck_model_step_measurements_prompt CHECK (
                prompt ~ '^[a-z0-9_.]+@\\d+\\.\\d+\\.\\d+$'
            ),
            CONSTRAINT ck_model_step_measurements_metric CHECK (
                metric ~ '^[a-z_]+(\\.[a-z_]+)*$'
            ),
            CONSTRAINT ck_model_step_measurements_value CHECK (value BETWEEN 0 AND 1),
            CONSTRAINT ck_model_step_measurements_bar CHECK (bar BETWEEN 0 AND 1),
            CONSTRAINT ck_model_step_measurements_passed CHECK (NOT passed OR value >= bar),
            CONSTRAINT ck_model_step_measurements_dataset CHECK (
                dataset ~ '^[a-z0-9_]+@\\d+\\.\\d+\\.\\d+$'
            ),
            CONSTRAINT ck_model_step_measurements_recorded_by CHECK (
                recorded_by ~ '^system:[a-z][a-z0-9_]*$'
            )
        )
        """
    )
    # The one read: the latest measurement of a step for a model and a prompt,
    # led by what RLS supplies.
    op.execute(
        "CREATE INDEX ix_model_step_measurements_latest ON sales.model_step_measurements"
        " (tenant_id, step, model, prompt, measured_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_model_step_measurements_workspace_id"
        " ON sales.model_step_measurements (workspace_id)"
    )
    op.execute("ALTER TABLE sales.model_step_measurements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.model_step_measurements FORCE ROW LEVEL SECURITY")
    op.execute(f"{_POLICY} USING {_TENANT} WITH CHECK {_TENANT}")
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE sales.model_step_measurements")
