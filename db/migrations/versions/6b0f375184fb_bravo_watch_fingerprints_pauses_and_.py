"""bravo watch fingerprints pauses and baselines

Revision ID: 6b0f375184fb
Revises: 2c32bc10b019
Create Date: 2026-11-21 11:30:00.000000+00:00

The Bravo change watch (ADR 0027 decision 4, sales ticket 65).

- **`bravo.watch_fingerprints`**: what the gateway measured, stored only when
  it differs from the last one of its environment, so the history is also
  the answer to "how often does Bravo change". Append-only (UPDATE and
  DELETE revoked). Bounded by Bravo's own change rate (script 06 §11 counts
  a few dozen objects changed a year), so neither partitioned nor pruned; it
  goes with its tenant.
- **`bravo.watch_pauses`**: the write kinds paused now, one row per kind,
  with the reasons and the fingerprint that paused it. Written by the
  `bravo_watch` lane; removed only when a person accepts a baseline, the
  service checking `sales.bravo.watch.accept` where it is written. The
  gateway reads it before each write.
- **`bravo.watch_baselines`**: each accepted baseline, append-only, naming
  the person (`accepted_by`, never null: no baseline accepts itself) and
  their reason. The latest per environment is the baseline; with none,
  every kind stays paused (fail closed).
- **`bravo.watch_reads`**: when each environment was last read whole, one
  row per tenant and environment, so "could not check since" survives a
  worker restart.
- **Scopes** `sales.bravo.watch.read` (told of a change, sees the state) and
  `sales.bravo.watch.accept` (accepts a new baseline) join the role
  `sales_head`; an admin grants them to anyone else through a permission set.
- **Tenant only**, the shape `platform.rule_versions` has: one Bravo per
  tenant, whatever the workspace. RLS enabled and forced; the foreign keys
  to a fingerprint are `ON DELETE RESTRICT` (a pause and a baseline name
  the evidence they rest on), each indexed on its own side.
"""

from __future__ import annotations

from alembic import op

revision = "6b0f375184fb"
down_revision = "2c32bc10b019"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_ENVIRONMENT = "environment IN ('uat', 'production')"

_FINGERPRINTS = f"""
    CREATE TABLE bravo.watch_fingerprints (
        tenant_id uuid NOT NULL,
        id uuid NOT NULL,
        environment text NOT NULL,
        taken_at timestamptz NOT NULL,
        digest text NOT NULL,
        components jsonb NOT NULL,
        CONSTRAINT pk_watch_fingerprints PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_watch_fingerprints_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_watch_fingerprints_environment CHECK ({_ENVIRONMENT}),
        CONSTRAINT ck_watch_fingerprints_digest CHECK (digest ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_watch_fingerprints_components CHECK (
            jsonb_typeof(components) = 'array' AND pg_column_size(components) <= 4194304
        )
    )
"""
_PAUSES = """
    CREATE TABLE bravo.watch_pauses (
        tenant_id uuid NOT NULL,
        kind text NOT NULL,
        reasons jsonb NOT NULL,
        fingerprint_id uuid,
        paused_at timestamptz NOT NULL,
        CONSTRAINT pk_watch_pauses PRIMARY KEY (tenant_id, kind),
        CONSTRAINT fk_watch_pauses_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_watch_pauses_fingerprint FOREIGN KEY (tenant_id, fingerprint_id)
            REFERENCES bravo.watch_fingerprints (tenant_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_watch_pauses_kind CHECK (
            char_length(kind) <= 64 AND kind ~ '^[a-z][a-z_.]*@[1-9][0-9]*$'
        ),
        CONSTRAINT ck_watch_pauses_reasons CHECK (
            jsonb_typeof(reasons) = 'array' AND jsonb_array_length(reasons) > 0
        )
    )
"""
_BASELINES = f"""
    CREATE TABLE bravo.watch_baselines (
        tenant_id uuid NOT NULL,
        id uuid NOT NULL,
        environment text NOT NULL,
        fingerprint_id uuid NOT NULL,
        accepted_by uuid NOT NULL,
        accepted_at timestamptz NOT NULL,
        reason text NOT NULL,
        CONSTRAINT pk_watch_baselines PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_watch_baselines_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_watch_baselines_fingerprint FOREIGN KEY (tenant_id, fingerprint_id)
            REFERENCES bravo.watch_fingerprints (tenant_id, id) ON DELETE RESTRICT,
        CONSTRAINT ck_watch_baselines_environment CHECK ({_ENVIRONMENT}),
        CONSTRAINT ck_watch_baselines_reason CHECK (char_length(btrim(reason)) BETWEEN 1 AND 500)
    )
"""
_READS = f"""
    CREATE TABLE bravo.watch_reads (
        tenant_id uuid NOT NULL,
        environment text NOT NULL,
        read_at timestamptz NOT NULL,
        CONSTRAINT pk_watch_reads PRIMARY KEY (tenant_id, environment),
        CONSTRAINT fk_watch_reads_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_watch_reads_environment CHECK ({_ENVIRONMENT})
    )
"""
_SCOPES = ("sales.bravo.watch.read", "sales.bravo.watch.accept")
_INDEXES = (
    "CREATE INDEX ix_watch_fingerprints_environment_taken_at"
    " ON bravo.watch_fingerprints (tenant_id, environment, taken_at)",
    "CREATE INDEX ix_watch_pauses_fingerprint ON bravo.watch_pauses (tenant_id, fingerprint_id)",
    "CREATE INDEX ix_watch_baselines_fingerprint"
    " ON bravo.watch_baselines (tenant_id, fingerprint_id)",
    "CREATE INDEX ix_watch_baselines_environment_accepted_at"
    " ON bravo.watch_baselines (tenant_id, environment, accepted_at)",
)
# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE bravo.watch_fingerprints ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.watch_fingerprints FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_watch_fingerprints ON bravo.watch_fingerprints"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
    "ALTER TABLE bravo.watch_pauses ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.watch_pauses FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_watch_pauses ON bravo.watch_pauses"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
    "ALTER TABLE bravo.watch_reads ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.watch_reads FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_watch_reads ON bravo.watch_reads"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
    "ALTER TABLE bravo.watch_baselines ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.watch_baselines FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_watch_baselines ON bravo.watch_baselines"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
)
_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON bravo.watch_fingerprints TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON bravo.watch_fingerprints FROM dw_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON bravo.watch_pauses TO dw_app;
            REVOKE TRUNCATE ON bravo.watch_pauses FROM dw_app;
            GRANT SELECT, INSERT, UPDATE ON bravo.watch_reads TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.watch_reads FROM dw_app;
            GRANT SELECT, INSERT ON bravo.watch_baselines TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON bravo.watch_baselines FROM dw_app;
        END IF;
    END
    $$
"""


def _roles(change: str) -> None:
    scopes = "', '".join(_SCOPES)
    op.execute(
        f"UPDATE platform.roles SET scopes = {change} WHERE key = 'sales_head'".replace(
            "<SCOPES>", f"'{scopes}'"
        )
    )


def upgrade() -> None:
    for ddl in (_FINGERPRINTS, _PAUSES, _BASELINES, _READS, *_INDEXES, *_ROW_SECURITY, _GRANTS):
        op.execute(ddl)
    _roles("scopes || jsonb_build_array(<SCOPES>)")


def downgrade() -> None:
    _roles("scopes - ARRAY[<SCOPES>]")
    op.execute("DROP TABLE bravo.watch_reads")
    op.execute("DROP TABLE bravo.watch_baselines")
    op.execute("DROP TABLE bravo.watch_pauses")
    op.execute("DROP TABLE bravo.watch_fingerprints")
