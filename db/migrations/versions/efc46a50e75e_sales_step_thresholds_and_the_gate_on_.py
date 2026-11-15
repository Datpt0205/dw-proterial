"""sales step thresholds and the gate on labelled cases and step outcomes

Revision ID: efc46a50e75e
Revises: 4bcfa82060fc
Create Date: 2026-11-15 16:41:00.349038+00:00

Sales ticket 44 (dw_sales ADR 0015, decided 2026-11-16): a reversible step's
result applies itself when its confidence clears a threshold set on the
tenant's labelled cases, so that the error among what applies itself stays
at or below the tenant's target; a share of it is audited blind.

- **`sales.labelled_cases` gains `confidence` and `gate`**: how sure the
  model was of the proposal (a probability from the call's token
  log-probabilities), and what code's gate did with it (`person`, `shadow`,
  `audit`, `applied`; `dw_sales.domain.description_reading.GateRoute`). The
  threshold is set from the first, the audits counted from the second.
  NULL for a case decided before this, or a result no gate saw.
  `ck_labelled_cases_gate` holds a gate other than `person` to a confidence:
  nothing clears a threshold without one. Added on the parent, so every
  partition (the DEFAULT one and each month's) has them.
- **`sales.step_outcomes` gains `gate`**, the same code for the item a step
  handled, on an item code took only (`ck_step_outcomes_gate`): what the
  head's view counts as applied, audited, shadow and sent to a person. A
  code, never a score, as the table holds no value.
- **`sales.step_thresholds`**: one row per workspace, step, prompt and model
  profile (a new version of either starts from no cases), set again by the
  worker's `sales_auto_apply` lane from the labelled cases
  (`dw_sales.domain.autonomy.measure`): the tier and target it was set at,
  the cases it was set from, the threshold (NULL: none certified) and the
  cases it accepts, the blind audits and the wrong among them, whether the
  audits stopped it, and when. Every fixed set is CHECKed, the tier among
  the two that may apply themselves (a step a person approves has no row);
  the counts are held to each other as `StepThreshold` holds them.
  - Tenant AND workspace RLS with the offboarding scope, ENABLEd and FORCEd.
  - `dw_app` SELECTs, INSERTs and UPDATEs (the lane's upsert); DELETE is
    REVOKEd: a threshold is replaced, never removed by the application. The
    rows leave with the tenant's workspaces (`ON DELETE CASCADE`).
  - `updated_at` by `platform.touch_updated_at()`, which yields to a value
    the statement states.
  - The primary key leads with `tenant_id`, `workspace_id`: the gate's one
    read (a step, a prompt, a profile) and the head's list are both carried
    by it; the workspace's own key is indexed for the cascade.
"""

from __future__ import annotations

from alembic import op

revision = "efc46a50e75e"
down_revision = "4bcfa82060fc"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.order_checks.ModelStep`, as `eac4fabdb31a` listed it; held
# to it by `test_sales_step_thresholds.py`.
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
# `GateRoute`.
_GATES = "'person', 'shadow', 'audit', 'applied'"
_VERSION = "'^[a-z][a-z0-9_.-]*@\\d+\\.\\d+\\.\\d+$'"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_LABELLED = (
    "ALTER TABLE sales.labelled_cases"
    " ADD COLUMN confidence double precision,"
    " ADD COLUMN gate text,"
    " ADD CONSTRAINT ck_labelled_cases_confidence CHECK (confidence BETWEEN 0 AND 1),"
    f" ADD CONSTRAINT ck_labelled_cases_gate CHECK (gate IS NULL OR ("
    f"gate IN ({_GATES}) AND (gate = 'person' OR confidence IS NOT NULL)))"
)

_OUTCOMES = (
    "ALTER TABLE sales.step_outcomes"
    " ADD COLUMN gate text,"
    # Written NULL-first: `NULL AND false` is false, and a CHECK refuses it.
    " ADD CONSTRAINT ck_step_outcomes_gate CHECK ("
    f"gate IS NULL OR (gate IN ({_GATES}) AND result = 'accepted'))"
)

_THRESHOLDS = f"""
    CREATE TABLE sales.step_thresholds (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        step text NOT NULL,
        prompt text NOT NULL,
        model_profile text NOT NULL,
        tier text NOT NULL,
        target double precision NOT NULL,
        needed integer NOT NULL,
        cases integer NOT NULL,
        threshold double precision,
        accepted integer NOT NULL,
        errors integer NOT NULL,
        audits integer NOT NULL,
        audit_errors integer NOT NULL,
        stopped boolean NOT NULL,
        computed_at timestamp with time zone NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_step_thresholds PRIMARY KEY (
            tenant_id, workspace_id, step, prompt, model_profile
        ),
        CONSTRAINT fk_step_thresholds_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_step_thresholds_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_step_thresholds_step CHECK (step IN ({_listed(_STEPS)})),
        CONSTRAINT ck_step_thresholds_prompt CHECK (prompt ~ {_VERSION}),
        CONSTRAINT ck_step_thresholds_model_profile CHECK (
            char_length(model_profile) BETWEEN 1 AND 64
        ),
        -- A step a person approves never applies itself, so has no row.
        CONSTRAINT ck_step_thresholds_tier CHECK (tier IN ('applies_itself', 'hand_off')),
        CONSTRAINT ck_step_thresholds_target CHECK (target > 0 AND target <= 1),
        CONSTRAINT ck_step_thresholds_needed CHECK (needed >= 1),
        CONSTRAINT ck_step_thresholds_threshold CHECK (threshold BETWEEN 0 AND 1),
        CONSTRAINT ck_step_thresholds_counts CHECK (
            errors >= 0 AND errors <= accepted AND accepted <= cases
            AND audit_errors >= 0 AND audit_errors <= audits
        ),
        -- A threshold accepts cases, and only a threshold does.
        CONSTRAINT ck_step_thresholds_accepted CHECK ((threshold IS NULL) = (accepted = 0))
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.step_thresholds ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.step_thresholds FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_step_thresholds ON sales.step_thresholds"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # The workspace's own key, for the cascade; the tenant's leads the key.
    "CREATE INDEX ix_step_thresholds_workspace_id ON sales.step_thresholds (workspace_id)",
)

_TRIGGER = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.step_thresholds"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE ON sales.step_thresholds TO dw_app;
            REVOKE DELETE ON sales.step_thresholds FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_LABELLED)
    op.execute(_OUTCOMES)
    op.execute(_THRESHOLDS)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_TRIGGER)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE sales.step_thresholds")
    op.execute(
        "ALTER TABLE sales.step_outcomes DROP CONSTRAINT ck_step_outcomes_gate, DROP COLUMN gate"
    )
    op.execute(
        "ALTER TABLE sales.labelled_cases"
        " DROP CONSTRAINT ck_labelled_cases_gate,"
        " DROP CONSTRAINT ck_labelled_cases_confidence,"
        " DROP COLUMN gate,"
        " DROP COLUMN confidence"
    )
