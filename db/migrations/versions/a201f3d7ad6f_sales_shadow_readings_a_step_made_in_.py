"""sales shadow readings a step made in shadow

Revision ID: a201f3d7ad6f
Revises: 7add0d23936a
Create Date: 2026-11-24 07:53:31.716206+00:00

Sales ticket 67 (dw_sales ADR 0015 decision 4): a model step the tenant lists
in shadow reads while it is not on and passing; what it proposed for an item
is kept here until a person's decision takes it, labelled
(`sales.labelled_cases`, gate ``shadow``), or the retention lane drops it.

- **`sales.shadow_readings`**: one row per step and item
  (`uq_shadow_readings_item`, led by what RLS supplies: the first reading of
  an item stands), the item by reference (message, attachment, line, field:
  never the mail's text), the proposal as JSON, the versions and confidence
  it was read with, and when.
- **Narrowed by tenant and workspace**, the one policy shape every workspace
  table has (`tenant AND (workspace OR app.workspace_scope = 'tenant')`),
  ENABLEd and FORCEd: the offboarding lane exports and purges it like the
  others.
- **Bounded, not append-only**: a reading is deleted when it is labelled and
  past `SHADOW_KEPT_FOR` by the lane, so `dw_app` holds SELECT, INSERT and
  DELETE; UPDATE is REVOKEd (failure-modes #7): a reading is kept as read.
- **Every fixed set and every length CHECKed** with `char_length`, never a
  regex repetition count (failure-modes #4).
- **Indexes**: the item key (unique, what `take` reads), the term's read
  (`read_at` under the scope), and the workspace's key for its cascade.
"""

from __future__ import annotations

from alembic import op

revision = "a201f3d7ad6f"
down_revision = "7add0d23936a"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.domain.order_checks.ModelStep` as it stands; held to it by
# `test_sales_shadow_readings.py`.
_STEPS = (
    "description_attributes",
    "salesorder_skill",
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
    "skill_mail_kinds",
    "skill_document_forms",
    "skill_handoffs",
    "skill_reply_drafts",
    "triage_card",
    "internal_change",
    "case_chat",
)
_IN_STEPS = ", ".join(f"'{s}'" for s in _STEPS)

_TABLE = f"""
    CREATE TABLE sales.shadow_readings (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        step text NOT NULL,
        item_key text NOT NULL,
        message_id text NOT NULL,
        attachment_id text,
        line_no integer,
        field text NOT NULL,
        proposed jsonb NOT NULL,
        prompt text NOT NULL,
        model_profile text,
        rules text,
        confidence double precision,
        read_at timestamp with time zone NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_shadow_readings PRIMARY KEY (id),
        CONSTRAINT fk_shadow_readings_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_shadow_readings_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_shadow_readings_step CHECK (step IN ({_IN_STEPS})),
        CONSTRAINT ck_shadow_readings_item_key CHECK (char_length(item_key) BETWEEN 1 AND 700),
        CONSTRAINT ck_shadow_readings_message_id CHECK (
            char_length(message_id) BETWEEN 1 AND 512
        ),
        CONSTRAINT ck_shadow_readings_attachment_id CHECK (
            attachment_id IS NULL OR char_length(attachment_id) BETWEEN 1 AND 128
        ),
        CONSTRAINT ck_shadow_readings_line_no CHECK (
            line_no IS NULL OR line_no BETWEEN 1 AND 99999
        ),
        CONSTRAINT ck_shadow_readings_field CHECK (char_length(field) BETWEEN 1 AND 40),
        CONSTRAINT ck_shadow_readings_proposed CHECK (
            jsonb_typeof(proposed) <> 'null' AND octet_length(proposed::text) <= 16384
        ),
        CONSTRAINT ck_shadow_readings_prompt CHECK (char_length(prompt) BETWEEN 3 AND 200),
        CONSTRAINT ck_shadow_readings_model_profile CHECK (
            model_profile IS NULL OR char_length(model_profile) BETWEEN 1 AND 64
        ),
        CONSTRAINT ck_shadow_readings_rules CHECK (
            rules IS NULL OR char_length(rules) BETWEEN 3 AND 200
        ),
        CONSTRAINT ck_shadow_readings_confidence CHECK (
            confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
        )
    )
"""

_STATEMENTS: tuple[str, ...] = (
    _TABLE,
    # One reading per step and item: what `take` reads, and the conflict
    # `keep` skips.
    "CREATE UNIQUE INDEX uq_shadow_readings_item"
    " ON sales.shadow_readings (tenant_id, workspace_id, step, item_key)",
    # The retention lane's read: the scope's readings by when they were read.
    "CREATE INDEX ix_shadow_readings_tenant_id_workspace_id_read_at"
    " ON sales.shadow_readings (tenant_id, workspace_id, read_at)",
    "CREATE INDEX ix_shadow_readings_workspace_id ON sales.shadow_readings (workspace_id)",
    "ALTER TABLE sales.shadow_readings ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.shadow_readings FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_shadow_readings ON sales.shadow_readings"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, DELETE ON sales.shadow_readings TO dw_app;
            REVOKE UPDATE ON sales.shadow_readings FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE sales.shadow_readings")
