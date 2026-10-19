"""sales followup deliveries and the followups rule key

Revision ID: d2b1394c67b1
Revises: 445f93c2ea2a
Create Date: 2026-10-19 03:57:32.973216+00:00

Sales ticket 42: DW1's follow-ups and morning brief, the worker's
`sales_followups` lane, every timing in the tenant-overridable policy
`sales_followups` (`dw_sales.domain.followups.SalesFollowups`).

- **`ck_rule_versions_key`** takes the ninth key, `sales_followups`, so a
  tenant may hold its own version (`test_sales_schema.py` holds the list equal
  to `RuleKey`). A policy document already names itself by `policy_id` and
  `policy_version`, so `ck_rule_versions_document` is unchanged.
- **`sales.followup_deliveries`**: what the lane delivered, one row per
  (follow-up, stage, subject, since), `uq_followup_deliveries_key`: the
  at-most-once guarantee across restarts, a second worker and the inbox's own
  90 days. ``subject`` is a case id, or the brief's local day; ``since`` when
  the wait began, or the brief's slot. ``followup`` and ``stage`` are closed
  sets (CHECK), held to `Followup`/`Stage` and the brief's names by
  `test_sales_schema.py`; ``recipients`` is a count, never who.
  Bounded: five stages per case at most, and one brief row per workspace per
  working day, which the lane prunes past 35 days in the brief's own
  transaction (`forget_briefs_before`); everything else leaves with its
  workspace or tenant (CASCADE) or offboarding's purge.
- **Workspace RLS**, ENABLEd and FORCEd, the one shape `CLAUDE.md` allows.
- **`sales.followup_scopes()`**, SECURITY DEFINER: the one read that crosses
  tenants, so the lane knows which workspaces have cases to visit; tenant and
  workspace ids only (`sales.processing_scopes_due` is the same shape).

Grants: `dw_app` SELECT, INSERT, DELETE on the table (a record is never
edited, so no UPDATE) and the function; nobody else the function.

Downgrade restores the eight keys; it fails, with Postgres's own "violated
by some row", while a tenant version of `sales_followups` is stored: deleting
a version two people approved to make a downgrade pass would lose it.
"""

from __future__ import annotations

from alembic import op

revision = "d2b1394c67b1"
down_revision = "445f93c2ea2a"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_BEFORE = (
    "sales_order_rules",
    "sales_kpi",
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
)
_KEYS = (*_BEFORE, "sales_followups")
# `dw_sales.domain.followups.Followup` and the brief (`application.followups.BRIEF`).
_FOLLOWUPS = (
    "order_unconfirmed",
    "quote_waiting_design",
    "quote_deadline",
    "waiting_customer",
    "morning_brief",
)
# `dw_sales.domain.followups.Stage` and the brief's (`BRIEF_STAGE`).
_STAGES = ("remind", "escalate", "warn", "brief")


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


_TABLE = f"""
    CREATE TABLE sales.followup_deliveries (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        followup text NOT NULL,
        stage text NOT NULL,
        subject text NOT NULL,
        since timestamp with time zone NOT NULL,
        recipients integer NOT NULL,
        sent_at timestamp with time zone NOT NULL,
        created_at timestamp with time zone NOT NULL DEFAULT now(),
        CONSTRAINT pk_followup_deliveries PRIMARY KEY (id),
        CONSTRAINT fk_followup_deliveries_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_followup_deliveries_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_followup_deliveries_key
            UNIQUE (tenant_id, workspace_id, followup, stage, subject, since),
        CONSTRAINT ck_followup_deliveries_followup CHECK (followup IN {_in(_FOLLOWUPS)}),
        CONSTRAINT ck_followup_deliveries_stage CHECK (stage IN {_in(_STAGES)}),
        CONSTRAINT ck_followup_deliveries_brief CHECK (
            (followup = 'morning_brief') = (stage = 'brief')
        ),
        CONSTRAINT ck_followup_deliveries_subject CHECK (
            subject ~ '^[0-9a-f-]{{10,36}}$'
        ),
        CONSTRAINT ck_followup_deliveries_recipients CHECK (recipients >= 0)
    )
"""

_ROW_SECURITY = (
    "ALTER TABLE sales.followup_deliveries ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.followup_deliveries FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_followup_deliveries ON sales.followup_deliveries"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES = (
    # What `already_sent` asks: the records of these subjects, led by what
    # row security supplies.
    "CREATE INDEX ix_followup_deliveries_subject"
    " ON sales.followup_deliveries (tenant_id, workspace_id, subject)",
    "CREATE INDEX ix_followup_deliveries_workspace_id ON sales.followup_deliveries (workspace_id)",
)

_SCOPES = """
    CREATE OR REPLACE FUNCTION sales.followup_scopes()
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, sales
    AS $$
        SELECT o.tenant_id, o.workspace_id FROM sales.order_cases o
        UNION
        SELECT q.tenant_id, q.workspace_id FROM sales.quote_cases q
        ORDER BY 1, 2
    $$
"""

_GRANT = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, DELETE ON sales.followup_deliveries TO dw_app;
            GRANT EXECUTE ON FUNCTION sales.followup_scopes() TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    _keys(_KEYS)
    op.execute(_TABLE)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_SCOPES)
    op.execute("REVOKE ALL ON FUNCTION sales.followup_scopes() FROM PUBLIC")
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute("DROP FUNCTION sales.followup_scopes()")
    op.execute("DROP TABLE sales.followup_deliveries")
    _keys(_BEFORE)
