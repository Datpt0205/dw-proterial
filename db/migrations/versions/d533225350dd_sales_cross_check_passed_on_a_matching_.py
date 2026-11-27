"""sales cross check passed on a matching read back

Revision ID: d533225350dd
Revises: 5895c4d8683e
Create Date: 2026-11-27 04:43:51.790806+00:00

Sales ticket 81 (dw_sales ADR 0016, Proposed): an order whose sales order DW
reads back from Bravo through the gateway, holding exactly the paste sheet,
with nothing a person decided or typed, may pass its cross-check by DW, at
the tenant's hand-off error and audit share; off unless the order rules say
`cross_check_on_match`.

- **`sales.order_cases`** gains the rule's stamp, `cross_check_on_match`
  (NULL, as on every case checked before, reads as off;
  `ck_order_cases_cross_check_on_match`: on only where a cross-check is
  required), and `cross_checked_on_read_back`, the gateway answer's sha256 a
  cross-check DW passed rests on (`ck_order_cases_cross_checked_on_read_back`:
  64 lowercase hex characters, bounded by `char_length`, never `{64}`, which
  PostgreSQL's regex engine refuses at run time past 255 (failure-modes #4);
  and only beside its checker).
- **`sales.order_bravo_read_backs.source`**: `export` (a file a person
  uploaded) or `gateway` (Bravo itself). Every row already stored reads
  `export`: the narrow reading, so a read-back from before never passes a
  cross-check until the order is read again.
- **`sales.order_cross_check_routes`**: what the cross-check lane did with
  one case version it read back, at most once (the key), and what a person
  then decided: `route` (code's gate: `person`, `shadow`, `audit`,
  `applied`), the `exceptions` that kept it a person's (codes only; an empty
  array is an eligible order), `basis` (what the comparison was, so a new one
  is measured from none), and `outcome` once decided: `kept` or `returned` by
  the cross-checker, `undone` for a pass taken back. Its counts are the
  measure (`OutcomeTally`). Written once and decided once: `dw_app` holds
  SELECT, INSERT and UPDATE (the outcome), DELETE REVOKEd (the schema's
  default privileges hand it, and a GRANT never takes it away,
  failure-modes #7). Not partitioned and with no retention lane of its own:
  one row per order version, at most, and it leaves with its order case
  (`ON DELETE CASCADE`), whose own retention it follows.
- Tenant AND workspace on both sides, in the shape every workspace-narrowed
  table has (`0d9e3f85d814`), so the offboarding lane exports it; ENABLEd and
  FORCEd. Foreign keys to the tenant, the workspace and the case, `ON DELETE
  CASCADE`, each indexed on its own side; the measure reads
  `(tenant_id, workspace_id, basis)`. `updated_at` by the platform trigger.

Downgrade drops the table and the columns.
"""

from __future__ import annotations

from alembic import op

revision = "d533225350dd"
down_revision = "5895c4d8683e"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_HEX = "'^[0-9a-f]+$'"

_CASE_COLUMNS = (
    "ALTER TABLE sales.order_cases ADD COLUMN cross_check_on_match boolean",
    "ALTER TABLE sales.order_cases ADD COLUMN cross_checked_on_read_back text",
    "ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_cross_check_on_match"
    " CHECK (cross_check_on_match IS NOT TRUE OR cross_check_required IS TRUE)",
    "ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_cross_checked_on_read_back"
    " CHECK (cross_checked_on_read_back IS NULL OR (char_length(cross_checked_on_read_back) = 64"
    f" AND cross_checked_on_read_back ~ {_HEX} AND cross_checked_by IS NOT NULL))",
    "ALTER TABLE sales.order_bravo_read_backs ADD COLUMN source text NOT NULL DEFAULT 'export'",
    "ALTER TABLE sales.order_bravo_read_backs ADD CONSTRAINT ck_order_bravo_read_backs_source"
    " CHECK (source IN ('export', 'gateway'))",
)

_ROUTES = """
    CREATE TABLE sales.order_cross_check_routes (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_id uuid NOT NULL,
        case_version integer NOT NULL,
        basis text NOT NULL,
        route text NOT NULL,
        exceptions jsonb NOT NULL,
        outcome text,
        routed_at timestamptz NOT NULL,
        decided_at timestamptz,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_order_cross_check_routes
            PRIMARY KEY (tenant_id, workspace_id, case_id, case_version),
        CONSTRAINT fk_order_cross_check_routes_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_order_cross_check_routes_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_order_cross_check_routes_case_id_order_cases FOREIGN KEY (case_id)
            REFERENCES sales.order_cases (id) ON DELETE CASCADE,
        CONSTRAINT ck_order_cross_check_routes_case_version CHECK (case_version >= 1),
        CONSTRAINT ck_order_cross_check_routes_basis
            CHECK (char_length(basis) BETWEEN 1 AND 64),
        CONSTRAINT ck_order_cross_check_routes_route
            CHECK (route IN ('person', 'shadow', 'audit', 'applied')),
        CONSTRAINT ck_order_cross_check_routes_exceptions
            CHECK (jsonb_typeof(exceptions) = 'array'),
        CONSTRAINT ck_order_cross_check_routes_eligible
            CHECK (route = 'person' OR exceptions = '[]'::jsonb),
        CONSTRAINT ck_order_cross_check_routes_outcome
            CHECK (outcome IN ('kept', 'returned', 'undone')),
        CONSTRAINT ck_order_cross_check_routes_decided
            CHECK ((outcome IS NULL) = (decided_at IS NULL)),
        CONSTRAINT ck_order_cross_check_routes_undone
            CHECK (outcome IS DISTINCT FROM 'undone' OR route = 'applied')
    )
"""

_INDEXES = (
    "CREATE INDEX ix_order_cross_check_routes_case_id ON sales.order_cross_check_routes (case_id)",
    "CREATE INDEX ix_order_cross_check_routes_workspace_id"
    " ON sales.order_cross_check_routes (workspace_id)",
    "CREATE INDEX ix_order_cross_check_routes_basis"
    " ON sales.order_cross_check_routes (tenant_id, workspace_id, basis)",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.order_cross_check_routes ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_cross_check_routes FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_order_cross_check_routes ON sales.order_cross_check_routes"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON sales.order_cross_check_routes TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE DELETE ON sales.order_cross_check_routes FROM dw_app",
)


def upgrade() -> None:
    for ddl in (*_CASE_COLUMNS, _ROUTES, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.order_cross_check_routes"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for grant in _GRANTS:
        op.execute(grant)


def downgrade() -> None:
    op.execute("DROP TABLE sales.order_cross_check_routes")
    op.execute("ALTER TABLE sales.order_bravo_read_backs DROP COLUMN source")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN cross_checked_on_read_back")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN cross_check_on_match")
