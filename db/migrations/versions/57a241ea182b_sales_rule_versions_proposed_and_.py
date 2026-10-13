"""sales rule versions proposed and approved

Revision ID: 57a241ea182b
Revises: a459e2244a9c
Create Date: 2026-10-13 14:05:00.000000+00:00

Sales ticket 19 (G15). A tenant's own version of a Sales rule arrives at
runtime, proposed by one person and approved by another, never as an edit to
the checkout (`CLAUDE.md`, "Per-tenant artifacts").

- **`sales.rule_versions`**: one row per version of one key a person of the
  tenant proposed, the whole policy document in `document` (validated by the
  key's own schema in `dw_sales.application.rules` before it is written).
  `uq_rule_versions_tenant_id_key_version`: a key's version number is the
  tenant's once. `uq_rule_versions_one_approved` (partial): at most one
  approved version per key, which is the one in force; approving a newer one
  supersedes it in the same transaction.
- **Maker and checker**: `ck_rule_versions_checker_not_maker` refuses a
  decision by the version's proposer, whatever writes the row; the service
  refuses it first (409). `ck_rule_versions_decided`: a proposal names no
  decider, and anything decided names who and when.
- **Tenant data, narrowed by tenant only**: a rule applies to the whole
  tenant, whichever workspace it was proposed in (`workspace_id` records
  which), so `tenant_isolation_rule_versions` reads `app.tenant_id` alone, the
  shape `platform.policy_overrides` has. RLS is enabled and FORCEd, so a
  connection that never scoped itself reads nothing, and offboarding (which
  sets the tenant) exports and purges it with the tenant.
- **Scopes**: `sales.rules.propose` for `sales_pic` and `sales_head`;
  `sales.rules.approve` for `sales_head` only.

Grants: `dw_app` takes every verb, like `po_layouts` (offboarding purges as
the app role); granted explicitly as `621864952a54` does. Downgrade removes
the scopes and the table.
"""

from __future__ import annotations

from alembic import op

revision = "57a241ea182b"
down_revision = "a459e2244a9c"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_KEYS = "('sales_order_rules', 'sales_kpi')"
_STATUSES = "('proposed', 'approved', 'rejected', 'superseded')"
_PROPOSE = "sales.rules.propose"
_APPROVE = "sales.rules.approve"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE sales.rule_versions (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            key text NOT NULL,
            version text NOT NULL,
            document jsonb NOT NULL,
            status text NOT NULL,
            proposed_by uuid NOT NULL,
            proposed_at timestamptz NOT NULL,
            decided_by uuid,
            decided_at timestamptz,
            comment text,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL,
            CONSTRAINT pk_rule_versions PRIMARY KEY (id),
            CONSTRAINT fk_rule_versions_tenant_id_tenants FOREIGN KEY (tenant_id)
                REFERENCES platform.tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_rule_versions_workspace_id_workspaces FOREIGN KEY (workspace_id)
                REFERENCES platform.workspaces (id) ON DELETE CASCADE,
            CONSTRAINT uq_rule_versions_tenant_id_key_version UNIQUE (tenant_id, key, version),
            CONSTRAINT ck_rule_versions_key CHECK (key IN {_KEYS}),
            CONSTRAINT ck_rule_versions_version CHECK (version ~ '^\\d+\\.\\d+\\.\\d+$'),
            CONSTRAINT ck_rule_versions_document CHECK (
                jsonb_typeof(document) = 'object'
                AND document ->> 'policy_id' = key
                AND document ->> 'policy_version' = version
            ),
            CONSTRAINT ck_rule_versions_status CHECK (status IN {_STATUSES}),
            CONSTRAINT ck_rule_versions_decided CHECK (
                (status = 'proposed') = (decided_by IS NULL)
                AND (decided_by IS NULL) = (decided_at IS NULL)
            ),
            CONSTRAINT ck_rule_versions_checker_not_maker CHECK (
                decided_by IS NULL OR decided_by <> proposed_by
            ),
            CONSTRAINT ck_rule_versions_comment CHECK (char_length(comment) <= 500)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rule_versions_one_approved ON sales.rule_versions"
        " (tenant_id, key) WHERE status = 'approved'"
    )
    # The rules list, newest proposed first, led by what RLS supplies.
    op.execute(
        "CREATE INDEX ix_rule_versions_tenant_id_proposed_at ON sales.rule_versions"
        " (tenant_id, proposed_at DESC, id DESC)"
    )
    op.execute("CREATE INDEX ix_rule_versions_workspace_id ON sales.rule_versions (workspace_id)")
    op.execute("ALTER TABLE sales.rule_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.rule_versions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_rule_versions ON sales.rule_versions"
        f" USING {_TENANT} WITH CHECK {_TENANT}"
    )
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.rule_versions"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sales.rule_versions TO dw_app")
    for role, scopes in (("sales_pic", (_PROPOSE,)), ("sales_head", (_PROPOSE, _APPROVE))):
        for scope in scopes:
            op.execute(
                f"UPDATE platform.roles SET scopes = scopes || '[\"{scope}\"]'::jsonb"
                f" WHERE key = '{role}' AND NOT scopes ? '{scope}'"
            )


def downgrade() -> None:
    for scope in (_PROPOSE, _APPROVE):
        op.execute(
            f"UPDATE platform.roles SET scopes = scopes - '{scope}'"
            " WHERE key IN ('sales_pic', 'sales_head')"
        )
    op.execute("DROP TABLE sales.rule_versions")
