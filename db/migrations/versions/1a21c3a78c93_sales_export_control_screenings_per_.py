"""sales export control screenings per customer and step

Revision ID: 1a21c3a78c93
Revises: d90793645086
Create Date: 2026-10-28 06:26:32.387585+00:00

Export control, WIV-03-032 (Sales, 2026-10-28). A person records each step's
result for a customer: the denial-list check, the red-flag answers, the NOC
asked for and received, the ESF approved for a fiscal year. DW1 keeps the
latest per customer and step and decides nothing: the order checks read the
customer's compliance as these results move it.

- **`sales.export_control_screenings`**: one row per (customer, step), the
  latest result. The row is replaced, never appended to: the history is the
  audit trail, written in the same transaction (`sales.export_control.<step>.
  <outcome>`). Bounded by customers times four steps, so neither partitioned
  nor pruned; it goes with its tenant.
- **Outcomes per step** are CHECKed as `dw_sales.domain.export_control.OUTCOMES`
  states them; `test_export_control_store.py` holds the two equal. A fiscal
  year exactly on an ESF, answers exactly on a red flag, a document exactly
  where the domain asks for one (a NOC received, an ESF approved).
- **The document** a result rests on is in object storage under the tenant
  and workspace (`<tenant>/<workspace>/sales/export-control/<customer>/<file>`);
  the row holds its id, hash, type and size.
- **Tenant AND workspace**, the shape every workspace-narrowed table has, on
  both sides of the policy. `dw_app` holds SELECT, INSERT and UPDATE: a result
  is replaced, never deleted; DELETE is REVOKEd (failure-modes #7).
- **Foreign keys to the tenant and the workspace, `ON DELETE CASCADE`**, each
  indexed on its own side (the primary key leads with `tenant_id`).
- **`ck_rule_versions_key`** takes the tenth key, `sales_export_control`: the
  red-flag questions, the ESF's approvers and the NOEC mail are the tenant's
  to replace on /sales/rules (`test_sales_schema.py` holds the list equal to
  `RuleKey`).
"""

from __future__ import annotations

from alembic import op

revision = "1a21c3a78c93"
down_revision = "d90793645086"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.export_control.OUTCOMES`, step by step.
_OUTCOMES = (
    "(step = 'denial_list' AND outcome IN ('clear', 'match'))"
    " OR (step = 'red_flag' AND outcome IN ('clear', 'escalated'))"
    " OR (step = 'noc' AND outcome IN ('requested', 'received'))"
    " OR (step = 'esf' AND outcome = 'approved')"
)
_MAX_BYTES = 10 * 1024 * 1024

_BEFORE = (
    "sales_order_rules",
    "sales_kpi",
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
    "sales_followups",
)
_KEYS = (*_BEFORE, "sales_export_control")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _keys(keys: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.rule_versions
            DROP CONSTRAINT ck_rule_versions_key,
            ADD CONSTRAINT ck_rule_versions_key CHECK (key IN {_in(keys)})
        """
    )

_SCREENINGS = f"""
    CREATE TABLE sales.export_control_screenings (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        customer_code text NOT NULL,
        step text NOT NULL,
        outcome text NOT NULL,
        checked_on date NOT NULL,
        fiscal_year integer,
        answers jsonb DEFAULT '{{}}'::jsonb NOT NULL,
        note text,
        evidence_file_id uuid,
        evidence_sha256 text,
        evidence_content_type text,
        evidence_size integer,
        recorded_by uuid NOT NULL,
        recorded_at timestamptz NOT NULL,
        CONSTRAINT pk_export_control_screenings
            PRIMARY KEY (tenant_id, workspace_id, customer_code, step),
        CONSTRAINT fk_export_control_screenings_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_export_control_screenings_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_export_control_screenings_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]{{1,15}}$'),
        CONSTRAINT ck_export_control_screenings_outcome CHECK ({_OUTCOMES}),
        CONSTRAINT ck_export_control_screenings_fiscal_year CHECK (
            (step = 'esf') = (fiscal_year IS NOT NULL)
            AND (fiscal_year IS NULL OR fiscal_year BETWEEN 2000 AND 2100)
        ),
        CONSTRAINT ck_export_control_screenings_answers CHECK (
            jsonb_typeof(answers) = 'object'
            AND (step = 'red_flag') = (answers <> '{{}}'::jsonb)
        ),
        CONSTRAINT ck_export_control_screenings_note CHECK (char_length(note) <= 500),
        CONSTRAINT ck_export_control_screenings_evidence CHECK (
            num_nonnulls(evidence_file_id, evidence_sha256, evidence_content_type, evidence_size)
                IN (0, 4)
            AND (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{{64}}$')
            AND (evidence_content_type IS NULL
                 OR evidence_content_type IN ('application/pdf', 'image/jpeg', 'image/png'))
            AND (evidence_size IS NULL OR evidence_size BETWEEN 1 AND {_MAX_BYTES})
            AND ((step, outcome) NOT IN (('noc', 'received'), ('esf', 'approved'))
                 OR evidence_file_id IS NOT NULL)
        )
    )
"""

_INDEXES = (
    "CREATE INDEX ix_export_control_screenings_workspace_id"
    " ON sales.export_control_screenings (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON sales.export_control_screenings TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE DELETE ON sales.export_control_screenings FROM dw_app",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.export_control_screenings ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.export_control_screenings FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_export_control_screenings ON sales.export_control_screenings"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_SCREENINGS, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)
    _keys(_KEYS)


def downgrade() -> None:
    op.execute("DELETE FROM sales.rule_versions WHERE key = 'sales_export_control'")
    _keys(_BEFORE)
    op.execute("DROP TABLE sales.export_control_screenings")
