"""sales message cases, finding code files_disagree

Revision ID: 3fcedec4e4f1
Revises: 0e77f2ca8c45
Create Date: 2026-11-14 12:14:16.854171+00:00

Sales tickets 19 and 22: one mail with several POs opens one order case per
PO number, all on the one stored message; and two files of one PO in a mail
are one case whose differences are a finding.

- **`sales.message_cases`**: the further order cases a message is on, after
  the one `sales.messages.order_case_id` names, in the mail's order
  (``position`` 1..49, `MessageDisposition.more_cases`). Written in the
  transaction that records the message's disposition, whose
  (workspace, message_id) key stays the message's idempotency key: a mail
  processed twice is refused whole, so no second set of cases opens. Keyed by
  the message (`fk_message_cases_messages`, the message's unique key, so a
  link is always its own tenant's and workspace's message) and naming a real
  order case (`fk_message_cases_order_case_id_order_cases`), both `ON DELETE
  CASCADE`; a case is named once per message
  (`uq_message_cases_tenant_id_workspace_id_message_id_order_case_id`).
  `ix_message_cases_order_case_id` carries a case's look-up of its messages.
- **Row security**: narrowed by tenant AND workspace with the offboarding
  scope, ENABLEd and FORCEd, like `sales.messages`.
- **A message is one revision per PO number.** `621864952a54` held a message
  to at most one revision (`uq_order_revisions_tenant_id_workspace_id_message_id`);
  a mail with three POs is three revisions of three cases. The key becomes
  the message and the PO number the revision is of
  (`uq_order_revisions_tenant_id_workspace_id_message_id_po_no`), the PO
  number a generated column from the revision's document (`po_no`, never
  written by the application), so the same mail can never be a second
  revision of one PO, in the database and not only in memory.
- **`ck_order_findings_code`** admits `files_disagree` (`test_sales_schema.py`
  holds it to `dw_sales.domain.orders.FindingCode`), as `bc50e4985878` did.

Grants: `dw_app` SELECT and INSERT on the links; a message's cases are a fact
about how it was processed, never rewritten, so UPDATE and DELETE are
revoked (the sales schema's default privileges would otherwise give them,
`89bcd0d49ea6`); a link leaves only with its message or its case, by cascade.

Downgrade drops the table, restores the one-revision-per-message key and
`bc50e4985878`'s list. It fails, with Postgres's own error, while a message
is a revision of several POs or a `files_disagree` is stored: deleting a
case's rows to make a downgrade pass would lose what a mail opened.
"""

from __future__ import annotations

from alembic import op

revision = "3fcedec4e4f1"
down_revision = "0e77f2ca8c45"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_FINDINGS = "sales.order_findings"
_CODE_CHECK = "ck_order_findings_code"
_BEFORE = (
    "code_unmapped",
    "code_ambiguous",
    "price_mismatch",
    "currency_mismatch",
    "uom_mismatch",
    "quotation_missing",
    "lme_band_mismatch",
    "moq_violation",
    "pack_multiple",
    "line_total_mismatch",
    "value_uncertain",
    "customer_unknown",
    "duplicate_po",
    "requested_date_short_lt",
    "missing_noc_esf",
    "revised_po",
    "revision_without_base",
    "customer_temporary",
    "sender_unverified",
    "legacy_encoding",
    "requested_date_missing",
    "reel_length_mismatch",
    "spec_mismatch",
)
_AFTER = (*_BEFORE, "files_disagree")

_MESSAGE_CASES = """
    CREATE TABLE sales.message_cases (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        position integer NOT NULL,
        order_case_id uuid NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_message_cases PRIMARY KEY (tenant_id, workspace_id, message_id, position),
        CONSTRAINT fk_message_cases_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_message_cases_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_message_cases_messages
            FOREIGN KEY (tenant_id, workspace_id, message_id)
            REFERENCES sales.messages (tenant_id, workspace_id, message_id) ON DELETE CASCADE,
        CONSTRAINT fk_message_cases_order_case_id_order_cases FOREIGN KEY (order_case_id)
            REFERENCES sales.order_cases (id) ON DELETE CASCADE,
        CONSTRAINT uq_message_cases_tenant_id_workspace_id_message_id_order_case_id
            UNIQUE (tenant_id, workspace_id, message_id, order_case_id),
        CONSTRAINT ck_message_cases_position CHECK (position BETWEEN 1 AND 49)
    )
"""

_INDEXES = (
    "CREATE INDEX ix_message_cases_order_case_id ON sales.message_cases (order_case_id)",
    "CREATE INDEX ix_message_cases_workspace_id ON sales.message_cases (workspace_id)",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.message_cases ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.message_cases FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_message_cases ON sales.message_cases"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_REVISIONS = "sales.order_revisions"
_ONE_REVISION = "uq_order_revisions_tenant_id_workspace_id_message_id"
_PER_PO = "uq_order_revisions_tenant_id_workspace_id_message_id_po_no"

_GRANTS = (
    "GRANT SELECT, INSERT ON sales.message_cases TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON sales.message_cases FROM dw_app",
)


def _codes(codes: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{code}'" for code in codes)
    op.execute(
        f"ALTER TABLE {_FINDINGS} DROP CONSTRAINT {_CODE_CHECK},"
        f" ADD CONSTRAINT {_CODE_CHECK} CHECK (code IN ({listed}))"
    )


def upgrade() -> None:
    _codes(_AFTER)
    op.execute(
        f"ALTER TABLE {_REVISIONS} ADD COLUMN po_no text"
        " GENERATED ALWAYS AS (document #>> '{header,po_no}') STORED NOT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX {_PER_PO} ON {_REVISIONS}"
        " (tenant_id, workspace_id, message_id, po_no)"
    )
    op.execute(f"DROP INDEX sales.{_ONE_REVISION}")
    for ddl in (_MESSAGE_CASES, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE sales.message_cases")
    op.execute(
        f"CREATE UNIQUE INDEX {_ONE_REVISION} ON {_REVISIONS} (tenant_id, workspace_id, message_id)"
    )
    op.execute(f"DROP INDEX sales.{_PER_PO}")
    op.execute(f"ALTER TABLE {_REVISIONS} DROP COLUMN po_no")
    _codes(_BEFORE)
