"""sales outbound mails: what Sales asked DW1 to send from their own mailbox

Revision ID: c42ed45c73a2
Revises: 7f94b09d1905
Create Date: 2026-10-29 12:00:00.000000+00:00

Đạt, 2026-10-29: "Gửi cho khách" sends the case's send draft from the
mailbox of the person who pressed, with no Graph API: the worker writes it to
that person's outbox folder, their own Power Automate flow sends it from
their Outlook and writes a receipt back (`dw_sales.application.outbound_mail`).
This table is where each such mail stands.

- **`sales.outbound_mails`**: the case, the artifact (the send draft) and
  who pressed; the mailbox it goes from (the presser's sign-in address,
  resolved by the server); `queued` → `written` → `sent` | `failed`, or
  `stalled` when no receipt came in time; `error` from a fixed set, present
  exactly when it did not go.
- **One active mail per artifact**: a partial unique index, so a second press
  or a retried request sends nothing more; a failed one may be sent again.
- **Status moves, rows stay**: `dw_app` holds SELECT, INSERT, UPDATE; DELETE
  is REVOKEd. Bounded by the cases' send drafts; not partitioned.
- **Tenant AND workspace** on both sides of the policy; foreign keys to the
  tenant and the workspace `ON DELETE CASCADE`, each indexed on its own side.
  The case and the artifact are named, not referenced, like the processing
  jobs: a case is never deleted.
- `updated_at` by `platform.touch_updated_at()`. The case's list leads with
  `tenant_id`, which RLS supplies; the lane's pending scan is a partial index.
"""

from __future__ import annotations

from alembic import op

revision = "c42ed45c73a2"
down_revision = "7f94b09d1905"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_TABLE = """
    CREATE TABLE sales.outbound_mails (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_kind text NOT NULL,
        case_id uuid NOT NULL,
        artifact_id uuid NOT NULL,
        requested_by uuid NOT NULL,
        mailbox text NOT NULL,
        status text NOT NULL,
        queued_at timestamptz NOT NULL,
        settled_at timestamptz,
        error text,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_outbound_mails PRIMARY KEY (id),
        CONSTRAINT fk_outbound_mails_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_outbound_mails_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_outbound_mails_case_kind CHECK (case_kind IN ('order', 'quote')),
        CONSTRAINT ck_outbound_mails_status
            CHECK (status IN ('queued', 'written', 'sent', 'failed', 'stalled')),
        CONSTRAINT ck_outbound_mails_mailbox CHECK (
            mailbox ~ '^[^@[:space:]A-Z]+@[a-z0-9.-]+$' AND char_length(mailbox) <= 254
        ),
        CONSTRAINT ck_outbound_mails_error CHECK (
            (error IS NOT NULL) = (status IN ('failed', 'stalled'))
            AND (error IS NULL OR error IN
                ('not_connected', 'write_failed', 'flow_failed', 'no_receipt', 'gone'))
        ),
        CONSTRAINT ck_outbound_mails_settled
            CHECK ((settled_at IS NULL) = (status IN ('queued', 'written')))
    )
"""

_INDEXES = (
    "CREATE UNIQUE INDEX uq_outbound_mails_active_artifact"
    " ON sales.outbound_mails (tenant_id, workspace_id, artifact_id)"
    " WHERE status IN ('queued', 'written', 'sent')",
    "CREATE INDEX ix_outbound_mails_case"
    " ON sales.outbound_mails (tenant_id, case_id, queued_at)",
    "CREATE INDEX ix_outbound_mails_pending"
    " ON sales.outbound_mails (queued_at) WHERE status IN ('queued', 'written')",
    "CREATE INDEX ix_outbound_mails_workspace_id ON sales.outbound_mails (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON sales.outbound_mails TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE DELETE ON sales.outbound_mails FROM dw_app",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.outbound_mails ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.outbound_mails FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_outbound_mails ON sales.outbound_mails"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_TRIGGER = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.outbound_mails"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
)

# The workspaces with a mail pending, for the lane, which visits each in its
# own scope: definer's rights read across tenants, ids only.
_SCOPES_PENDING = """
    CREATE OR REPLACE FUNCTION sales.outbound_scopes_pending()
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        SELECT DISTINCT m.tenant_id, m.workspace_id
        FROM sales.outbound_mails m
        WHERE m.status IN ('queued', 'written')
        ORDER BY m.tenant_id, m.workspace_id
    $$
"""


def upgrade() -> None:
    for ddl in (_TABLE, *_INDEXES, *_ROW_SECURITY, _TRIGGER, *_GRANTS, _SCOPES_PENDING):
        op.execute(ddl)
    op.execute("REVOKE ALL ON FUNCTION sales.outbound_scopes_pending() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION sales.outbound_scopes_pending() TO dw_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION sales.outbound_scopes_pending()")
    op.execute("DROP TABLE sales.outbound_mails")
