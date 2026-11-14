"""sales sent messages, thread intents

Revision ID: 7f3def432f82
Revises: 3fcedec4e4f1
Create Date: 2026-11-14 14:37:37.579973+00:00

Sales tickets 25 and 26 (dw_sales ADR 0009 decision 3, ADR 0010 decision 1).

- **`sales.sent_messages`**: a message Sales sent (its sender a member's own
  sign-in address, `dw_sales.application.outgoing`) that DW1 took up. It is
  never a disposition: it opens no case and nothing is routed. The row says
  when DW1 processed it and, where a model read its thread intents, the
  reading (`ReplyReading`, an object or null, `ck_sent_messages_reading`).
  Keyed by the message in its workspace (`pk_sent_messages`), the record's
  idempotency key as a disposition's is. No foreign key to the stored
  mailbox: the mock mailbox of a demo is not stored, as `sales.messages`
  has none either.
- **Row security**: narrowed by tenant AND workspace with the offboarding
  scope, ENABLEd and FORCEd, like `sales.messages`.
- **A reply's reading becomes thread intents.** `sales.messages.case_reply`
  held ticket 32's one kind and its quotes (`reading.kind`,
  `reading.quotes`); a reading now holds a list of intents, each with its
  quotes (`reading.intents`). Each stored reading is rewritten once, its
  kind mapped to the intent that names the same thing (accepts_spec ->
  accepts, rejects_spec and keeps_po_as_is -> rejects, counter_proposal ->
  requests_change, sends_corrected_po -> sends_po, question -> asks,
  unclear -> unclear), with the quotes it stood on; an unavailable reading
  has none.

Grants: `dw_app` SELECT and INSERT on the sent messages; a record is how a
message was processed, never rewritten, so UPDATE and DELETE are revoked (the
sales schema's default privileges would otherwise give them, `89bcd0d49ea6`);
a row leaves only with its tenant or workspace, by cascade.

Downgrade drops the table and rewrites each reading back to one kind: the
first intent's (requests_change -> counter_proposal, rejects ->
keeps_po_as_is on an order and rejects_spec on a quote, an intent ticket 32
did not have -> unclear). A message read as several intents keeps only its
first: the older shape cannot hold more.
"""

from __future__ import annotations

from alembic import op

revision = "7f3def432f82"
down_revision = "3fcedec4e4f1"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_SENT_MESSAGES = """
    CREATE TABLE sales.sent_messages (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        processed_at timestamptz NOT NULL,
        reading jsonb,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_sent_messages PRIMARY KEY (tenant_id, workspace_id, message_id),
        CONSTRAINT fk_sent_messages_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_sent_messages_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_sent_messages_message_id CHECK (message_id ~ '^[!-~]+$'
            AND char_length(message_id) <= 512),
        CONSTRAINT ck_sent_messages_reading CHECK (
            reading IS NULL OR jsonb_typeof(reading) = 'object'
        )
    )
"""

_INDEXES = ("CREATE INDEX ix_sent_messages_workspace_id ON sales.sent_messages (workspace_id)",)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.sent_messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.sent_messages FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_sent_messages ON sales.sent_messages"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_GRANTS = (
    "GRANT SELECT, INSERT ON sales.sent_messages TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON sales.sent_messages FROM dw_app",
)

# A stored reply reading of ticket 32's shape: an object with a `kind` key.
_OLD_READING = (
    "jsonb_typeof(case_reply -> 'reading') = 'object' AND (case_reply -> 'reading') ? 'kind'"
)
_NEW_READING = (
    "jsonb_typeof(case_reply -> 'reading') = 'object' AND (case_reply -> 'reading') ? 'intents'"
)

_TO_INTENTS = f"""
    UPDATE sales.messages SET case_reply = jsonb_set(
        case_reply,
        '{{reading}}',
        ((case_reply -> 'reading') - 'kind' - 'quotes') || jsonb_build_object(
            'intents',
            CASE WHEN case_reply #>> '{{reading,outcome}}' = 'read' THEN jsonb_build_array(
                jsonb_build_object(
                    'intent',
                    CASE case_reply #>> '{{reading,kind}}'
                        WHEN 'accepts_spec' THEN 'accepts'
                        WHEN 'rejects_spec' THEN 'rejects'
                        WHEN 'keeps_po_as_is' THEN 'rejects'
                        WHEN 'counter_proposal' THEN 'requests_change'
                        WHEN 'sends_corrected_po' THEN 'sends_po'
                        WHEN 'question' THEN 'asks'
                        ELSE 'unclear'
                    END,
                    'quotes',
                    COALESCE(case_reply #> '{{reading,quotes}}', '[]'::jsonb)
                )
            ) ELSE '[]'::jsonb END
        )
    )
    WHERE {_OLD_READING}
"""

_TO_KIND = f"""
    UPDATE sales.messages SET case_reply = jsonb_set(
        case_reply,
        '{{reading}}',
        ((case_reply -> 'reading') - 'intents') || jsonb_build_object(
            'kind',
            CASE WHEN case_reply #>> '{{reading,outcome}}' = 'read' THEN to_jsonb(
                CASE case_reply #>> '{{reading,intents,0,intent}}'
                    WHEN 'accepts' THEN 'accepts_spec'
                    WHEN 'rejects' THEN CASE WHEN order_case_id IS NOT NULL
                        THEN 'keeps_po_as_is' ELSE 'rejects_spec' END
                    WHEN 'requests_change' THEN 'counter_proposal'
                    WHEN 'sends_po' THEN 'sends_corrected_po'
                    WHEN 'asks' THEN 'question'
                    ELSE 'unclear'
                END
            ) ELSE 'null'::jsonb END,
            'quotes',
            COALESCE(case_reply #> '{{reading,intents,0,quotes}}', '[]'::jsonb)
        )
    )
    WHERE {_NEW_READING}
"""


def upgrade() -> None:
    for ddl in (_SENT_MESSAGES, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)
    op.execute(_TO_INTENTS)


def downgrade() -> None:
    op.execute(_TO_KIND)
    op.execute("DROP TABLE sales.sent_messages")
