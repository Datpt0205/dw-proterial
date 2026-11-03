"""purchasing rfq mails sent from the buyer's mailbox

Revision ID: da6950544c81
Revises: cf783456f739
Create Date: 2026-11-03 02:00:00.000000+00:00

DW2's queue of RFQs a buyer sent from their own mailbox
(`dw_purchasing.application.rfq_mail`, ADR 0014: the context's own queue):
`purchasing.rfq_mails`, one row per press, `queued` until the
`purchasing_outbound` lane writes it into the buyer's outbox folder
(`written`), then `sent`, `failed` or `stalled`.

- **One active mail per supplier of a case**: a unique index over
  (case, supplier) while queued, written or sent; a failed or stalled one
  may be sent again.
- **Goes with its case** (`ON DELETE CASCADE`): a case pruned by its term
  takes its mails; the application never deletes one (DELETE revoked).
- **Tenant AND (workspace OR scope)** on both sides; offboarded by the
  catalog's policy discovery and the tenant's and workspace's cascade.
"""

from __future__ import annotations

from alembic import op

revision = "da6950544c81"
down_revision = "cf783456f739"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_MAILS = """
    CREATE TABLE purchasing.rfq_mails (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_id uuid NOT NULL,
        supplier_code text NOT NULL,
        mailbox text NOT NULL,
        recipients jsonb NOT NULL,
        subject text NOT NULL,
        body text NOT NULL,
        status text NOT NULL,
        error text,
        queued_by uuid NOT NULL,
        queued_at timestamp with time zone NOT NULL,
        written_at timestamp with time zone,
        settled_at timestamp with time zone,
        CONSTRAINT pk_rfq_mails PRIMARY KEY (id),
        CONSTRAINT fk_rfq_mails_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_rfq_mails_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_rfq_mails_case_id_cases FOREIGN KEY (case_id)
            REFERENCES purchasing.cases (id) ON DELETE CASCADE,
        -- `dw_purchasing.domain.requests.Code`.
        CONSTRAINT ck_rfq_mails_supplier_code CHECK (
            supplier_code ~ '^[A-Za-z0-9][A-Za-z0-9._/-]*$' AND char_length(supplier_code) <= 48
        ),
        CONSTRAINT ck_rfq_mails_mailbox CHECK (
            char_length(mailbox) BETWEEN 3 AND 254 AND mailbox = lower(mailbox)
        ),
        CONSTRAINT ck_rfq_mails_recipients CHECK (
            jsonb_typeof(recipients) = 'array' AND jsonb_array_length(recipients) BETWEEN 1 AND 20
        ),
        CONSTRAINT ck_rfq_mails_subject CHECK (char_length(subject) BETWEEN 1 AND 300),
        CONSTRAINT ck_rfq_mails_body CHECK (char_length(body) BETWEEN 1 AND 8000),
        -- `dw_purchasing.application.rfq_mail`'s statuses and why one failed.
        CONSTRAINT ck_rfq_mails_status CHECK (
            status IN ('queued', 'written', 'sent', 'failed', 'stalled')
        ),
        CONSTRAINT ck_rfq_mails_error CHECK (
            (status IN ('failed', 'stalled')) = (error IS NOT NULL)
            AND (error IS NULL OR error IN ('not_connected', 'flow_failed', 'no_receipt'))
        ),
        -- Written once it left the queue, unless it failed before (no
        -- folder). `IS NOT DISTINCT FROM`: a NULL error must not pass.
        CONSTRAINT ck_rfq_mails_written_at CHECK (
            (status = 'queued') = (written_at IS NULL)
            OR error IS NOT DISTINCT FROM 'not_connected'
        ),
        CONSTRAINT ck_rfq_mails_settled_at CHECK (
            (status IN ('sent', 'failed', 'stalled')) = (settled_at IS NOT NULL)
        )
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE purchasing.rfq_mails ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.rfq_mails FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_rfq_mails ON purchasing.rfq_mails"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # One active mail per supplier of a case (`SqlRfqMails.add`).
    "CREATE UNIQUE INDEX uq_rfq_mails_case_id_supplier_code_active"
    " ON purchasing.rfq_mails (case_id, supplier_code)"
    " WHERE status IN ('queued', 'written', 'sent')",
    # A case's mails (`SqlRfqMails.of_case`), and the case's own key.
    "CREATE INDEX ix_rfq_mails_tenant_id_case_id"
    " ON purchasing.rfq_mails (tenant_id, case_id, queued_at)",
    "CREATE INDEX ix_rfq_mails_case_id ON purchasing.rfq_mails (case_id)",
    # What the lane takes next (`SqlRfqMails.pending`).
    "CREATE INDEX ix_rfq_mails_tenant_id_workspace_id_pending"
    " ON purchasing.rfq_mails (tenant_id, workspace_id, queued_at)"
    " WHERE status IN ('queued', 'written')",
    "CREATE INDEX ix_rfq_mails_workspace_id ON purchasing.rfq_mails (workspace_id)",
)

# The schema's default privileges gave every verb (2d0c58dc3806); a GRANT
# never takes one away, so the withheld verb is REVOKEd by name.
_GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON purchasing.rfq_mails TO dw_app",
    "REVOKE DELETE ON purchasing.rfq_mails FROM dw_app",
)


def upgrade() -> None:
    op.execute(_MAILS)
    for statement in (*_ROW_SECURITY, *_INDEXES, *_GRANTS):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE purchasing.rfq_mails")
