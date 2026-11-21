"""bravo write ledger and the sales bravo writes key

Revision ID: 2c32bc10b019
Revises: 3187714cd75c
Create Date: 2026-11-21 09:10:48.210471+00:00

The Bravo gateway (ADR 0027, sales ticket 63).

- **Schema `bravo`**: what the gateway keeps in DW's PostgreSQL. Nothing of
  DW's is in Bravo's own database (ADR 0027 decision 2).
- **`bravo.write_ledger`**: one row per approval the gateway acted on, keyed
  by the approval id (the write's idempotency key). Claimed before the
  statements are sent, settled after: `written`, `refused` (Bravo refused it,
  nothing written: a stale row), `in_doubt` (sent, no answer: a person reads
  Bravo before anything else happens), `reconcile_failed` (written, and the
  read-back differs). `settled_at` is set exactly when the row leaves
  `claimed`. Bounded by the PICs' approved writes (6 PICs, ~600 SOs a month),
  kept with its tenant as the record of what DW wrote; neither partitioned
  nor pruned.
- **Tenant AND workspace**, the shape every workspace-narrowed table has, on
  both sides of the policy; the gateway connects as `dw_app` and sets both
  from the verified approval token, per transaction. `dw_app` holds SELECT,
  INSERT and UPDATE; DELETE is REVOKEd (failure-modes #7): a spent approval
  id must stay spent.
- **`ck_rule_versions_key`** and **`ck_rule_drafts_rule_key`** admit
  `sales_bravo_writes`: which write kinds a tenant has switched on, each
  with the UAT run that proved it (`dw_sales.domain.bravo_writes`). Off
  unless a tenant's approved version says otherwise; a version is proposed
  and approved by two people like every Sales rule.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "2c32bc10b019"
down_revision = "3187714cd75c"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_STATUSES = "('claimed', 'written', 'refused', 'in_doubt', 'reconcile_failed')"

_LEDGER = f"""
    CREATE TABLE bravo.write_ledger (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        approval_id uuid NOT NULL,
        kind text NOT NULL,
        content_hash text NOT NULL,
        bravo_user_id integer NOT NULL,
        status text NOT NULL,
        detail jsonb DEFAULT '{{}}'::jsonb NOT NULL,
        claimed_at timestamptz NOT NULL,
        settled_at timestamptz,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_write_ledger PRIMARY KEY (tenant_id, approval_id),
        CONSTRAINT fk_write_ledger_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_write_ledger_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_write_ledger_kind CHECK (
            char_length(kind) <= 64 AND kind ~ '^[a-z][a-z_.]*@[1-9][0-9]*$'
        ),
        CONSTRAINT ck_write_ledger_content_hash CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_write_ledger_bravo_user_id CHECK (bravo_user_id > 0),
        CONSTRAINT ck_write_ledger_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_write_ledger_settled CHECK ((status = 'claimed') = (settled_at IS NULL)),
        CONSTRAINT ck_write_ledger_detail CHECK (
            jsonb_typeof(detail) = 'object' AND pg_column_size(detail) <= 8192
        )
    )
"""

_SCHEMA_FOR_APP = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT USAGE ON SCHEMA bravo TO dw_app;
        END IF;
    END
    $$
"""
_GRANTS_FOR_APP = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE ON bravo.write_ledger TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.write_ledger FROM dw_app;
        END IF;
    END
    $$
"""

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE bravo.write_ledger ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.write_ledger FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_write_ledger ON bravo.write_ledger"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)
_INDEXES = ("CREATE INDEX ix_write_ledger_workspace_id ON bravo.write_ledger (workspace_id)",)
_TRIGGER = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON bravo.write_ledger"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
)

_NEW_KEYS = ("sales_bravo_writes",)
# (table, check, column, the values this revision admits)
_CHECKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("platform.rule_versions", "ck_rule_versions_key", "key", _NEW_KEYS),
    ("sales.rule_drafts", "ck_rule_drafts_rule_key", "rule_key", _NEW_KEYS),
)


def _definition(table: str, check: str) -> str:
    return str(
        op.get_bind().scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
            ),
            {"check": check, "table": table},
        )
    )


def _held(definition: str) -> list[str]:
    """The values a CHECK's list admits, in its order."""
    return re.findall(r"'([a-z_]+)'::text", definition)


def _patterns(definition: str) -> list[str]:
    """The patterns a CHECK admits beside its list (``key ~ '...'``)."""
    return re.findall(r"~ '([^']+)'::text", definition)


def _set(table: str, check: str, column: str, values: list[str], patterns: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    extra = "".join(f" OR {column} ~ '{pattern}'" for pattern in patterns)
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK ({column} IN ({listed}){extra})"
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA bravo")
    op.execute(_SCHEMA_FOR_APP)
    op.execute(_LEDGER)
    for ddl in (*_INDEXES, *_ROW_SECURITY, _TRIGGER):
        op.execute(ddl)
    op.execute(_GRANTS_FOR_APP)
    for table, check, column, new in _CHECKS:
        definition = _definition(table, check)
        held = _held(definition)
        values = [*held, *(v for v in new if v not in held)]
        _set(table, check, column, values, _patterns(definition))


def downgrade() -> None:
    for table, check, column, new in reversed(_CHECKS):
        listed = ", ".join(f"'{value}'" for value in new)
        op.execute(f"DELETE FROM {table} WHERE {column} IN ({listed})")
        definition = _definition(table, check)
        values = [v for v in _held(definition) if v not in new]
        _set(table, check, column, values, _patterns(definition))
    op.execute("DROP TABLE bravo.write_ledger")
    op.execute("DROP SCHEMA bravo")
