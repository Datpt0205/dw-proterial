"""sales change requests, a line's confirmed changes

Revision ID: c7d0730fcccd
Revises: 7f3def432f82
Create Date: 2026-11-14 18:17:52.328719+00:00

Sales ticket 27, dw_sales ADR 0010 decisions 2 and 4: a change a customer
asks for in a mail is a change request on the order case, confirmed line by
line (`dw_sales.domain.change_requests`).

- **`sales.change_requests`**: one row per mail and case, the request as the
  domain holds it (`record`, an object: its text, lines, anchors and
  decisions), with the columns a query or a constraint reads beside it: the
  case, its number on the case (the order requests open in, unique), the
  mail, the state, a version a save claims, who opened it and when.
  `open` → `closed` when every line is decided; one opened while another is
  open or queued is `queued` and opens when the one before is closed.
- **One open per case**: a partial unique index, so two requests can never be
  open on one case together (ADR 0010 decision 4: queued, never merged).
  **One request per mail and case**: a unique key.
- **State moves, rows stay**: `dw_app` holds SELECT, INSERT, UPDATE; DELETE is
  REVOKEd (the sales schema's default privileges would otherwise give it). A
  request leaves only with its case, tenant or workspace, by cascade.
  Bounded by the cases; not partitioned.
- **Tenant AND workspace** on both sides of the policy, with the offboarding
  scope; ENABLEd and FORCEd. Foreign keys `ON DELETE CASCADE`, each indexed on
  its own side; the case's list is read by `uq_change_requests_number`,
  which leads with `tenant_id`, as RLS supplies it.
- `updated_at` by `platform.touch_updated_at()`.
- **`sales.order_lines.changes`**: the changes a person confirmed on the line,
  one per field (`AppliedChange`), an array, empty for every line until now.
- **The model step `change_request`** (the changes a reply asks in its own
  words): `ck_model_step_measurements_step` admits it, so a live measurement
  can be attested for it, and `ck_step_outcomes_step` too (the parent carries
  it to every partition), the sets `test_sales_schema.py` and
  `test_sales_step_outcomes.py` hold to `ModelStep`.

Downgrade deletes the rows the old step checks cannot hold, then drops the
column and the table.
"""

from __future__ import annotations

from alembic import op

revision = "c7d0730fcccd"
down_revision = "7f3def432f82"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_TABLE = """
    CREATE TABLE sales.change_requests (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_id uuid NOT NULL,
        number integer NOT NULL,
        message_id text NOT NULL,
        state text NOT NULL,
        version integer NOT NULL,
        opened_by uuid NOT NULL,
        opened_at timestamptz NOT NULL,
        record jsonb NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_change_requests PRIMARY KEY (id),
        CONSTRAINT fk_change_requests_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_change_requests_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_change_requests_case_id_order_cases FOREIGN KEY (case_id)
            REFERENCES sales.order_cases (id) ON DELETE CASCADE,
        CONSTRAINT uq_change_requests_message
            UNIQUE (tenant_id, workspace_id, case_id, message_id),
        CONSTRAINT uq_change_requests_number
            UNIQUE (tenant_id, workspace_id, case_id, number),
        CONSTRAINT ck_change_requests_number CHECK (number >= 1),
        CONSTRAINT ck_change_requests_state CHECK (state IN ('open', 'queued', 'closed')),
        CONSTRAINT ck_change_requests_version CHECK (version >= 1),
        CONSTRAINT ck_change_requests_message_id CHECK (message_id ~ '^[!-~]+$'
            AND char_length(message_id) <= 512),
        CONSTRAINT ck_change_requests_record CHECK (
            jsonb_typeof(record) = 'object'
            AND record ->> 'state' = state
            AND (record ->> 'request_id')::uuid = id
            AND (record ->> 'number')::integer = number
        )
    )
"""

_INDEXES = (
    "CREATE UNIQUE INDEX uq_change_requests_one_open"
    " ON sales.change_requests (tenant_id, workspace_id, case_id) WHERE state = 'open'",
    "CREATE INDEX ix_change_requests_case_id ON sales.change_requests (case_id)",
    "CREATE INDEX ix_change_requests_workspace_id ON sales.change_requests (workspace_id)",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.change_requests ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.change_requests FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_change_requests ON sales.change_requests"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_TRIGGER = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.change_requests"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON sales.change_requests TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE DELETE ON sales.change_requests FROM dw_app",
)

_LINE_CHANGES = (
    "ALTER TABLE sales.order_lines ADD COLUMN changes jsonb DEFAULT '[]'::jsonb NOT NULL",
    "ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_changes"
    " CHECK (jsonb_typeof(changes) = 'array')",
)


# `dw_sales.domain.order_checks.ModelStep`; the platform's table also holds
# Purchasing's steps, which this leaves as they are.
_SALES_STEPS = (
    "description_attributes",
    "message_intent",
    "rfq_extraction",
    "reply_intent",
    "request_handoff",
    "layout_proposal",
    "po_body_extraction",
)
_PURCHASING_STEPS = (
    "purchasing_pr_mail_reading",
    "purchasing_supplier_quote_reading",
    "purchasing_order_confirmation_reading",
)
_NEW_STEP = "change_request"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _steps(sales: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        " ADD CONSTRAINT ck_model_step_measurements_step"
        f" CHECK (step IN ({_listed((*sales, *_PURCHASING_STEPS))}))"
    )
    op.execute(
        "ALTER TABLE sales.step_outcomes"
        " DROP CONSTRAINT ck_step_outcomes_step,"
        f" ADD CONSTRAINT ck_step_outcomes_step CHECK (step IN ({_listed(sales)}))"
    )


def upgrade() -> None:
    for ddl in (_TABLE, *_INDEXES, *_ROW_SECURITY, _TRIGGER, *_GRANTS, *_LINE_CHANGES):
        op.execute(ddl)
    _steps((*_SALES_STEPS, _NEW_STEP))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.model_step_measurements WHERE step = '{_NEW_STEP}'")
    op.execute(f"DELETE FROM sales.step_outcomes WHERE step = '{_NEW_STEP}'")
    _steps(_SALES_STEPS)
    op.execute("ALTER TABLE sales.order_lines DROP COLUMN changes")
    op.execute("DROP TABLE sales.change_requests")
