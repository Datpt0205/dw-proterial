"""sales skill replays stored beside a proposed skill version

Revision ID: e1b1e0cadb66
Revises: 137ec1972538
Create Date: 2026-11-15 19:38:24.264449+00:00

Sales ticket 40 (dw_sales ADR 0014 decision 2): a proposed version of a DW1
skill is replayed by the worker on example mails, with it and with the
skills in force, and the head sees the result before deciding
(`dw_sales.application.skill_replay`).

- **`sales.skill_replays`**: one row per replayed version, beside the
  `platform.rule_versions` row it replays (`version_id`, unique, `ON DELETE
  CASCADE`): when, from which examples (`source`, CHECKed), whether every
  reading got an answer (`outcome`, CHECKed), the counts, and the security
  cases the proposal failed, as a JSON array of example ids.
- **Tenant only**, the shape `platform.rule_versions` has: a skill version is
  the tenant's, read for every workspace alike, so its replay is too.
  ENABLEd and FORCEd. `workspace_id` is the workspace whose lane replayed
  it, for the cascade when a workspace leaves.
- **Append-only**: `dw_app` holds SELECT and INSERT; UPDATE and DELETE are
  REVOKEd (failure-modes #7). A replay is a fact about one version.
- **Every count bounded by the messages read**, no default on any value
  (failure-modes #7): a writer states each.
- **Indexes**: the version's own key (unique), the tenant's replays by
  version (what the skills list reads, led by what RLS supplies), the
  workspace's key for its cascade.

Continues from `137ec1972538` (ticket 43's head at the time it was made).
"""

from __future__ import annotations

from alembic import op

revision = "e1b1e0cadb66"
down_revision = "137ec1972538"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"

_TABLE = """
    CREATE TABLE sales.skill_replays (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        version_id uuid NOT NULL,
        replayed_at timestamp with time zone NOT NULL,
        source text NOT NULL,
        outcome text NOT NULL,
        messages integer NOT NULL,
        right_with integer NOT NULL,
        right_without integer NOT NULL,
        unanswered integer NOT NULL,
        security_failed jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_skill_replays PRIMARY KEY (id),
        CONSTRAINT fk_skill_replays_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_skill_replays_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_skill_replays_version_id_rule_versions FOREIGN KEY (version_id)
            REFERENCES platform.rule_versions (id) ON DELETE CASCADE,
        CONSTRAINT ck_skill_replays_source CHECK (source IN ('platform_examples')),
        CONSTRAINT ck_skill_replays_outcome CHECK (outcome IN ('replayed', 'incomplete')),
        CONSTRAINT ck_skill_replays_counts CHECK (
            messages >= 0
            AND right_with BETWEEN 0 AND messages
            AND right_without BETWEEN 0 AND messages
            AND unanswered >= 0
        ),
        CONSTRAINT ck_skill_replays_security_failed CHECK (
            jsonb_typeof(security_failed) = 'array'
            AND octet_length(security_failed::text) <= 8192
        )
    )
"""

_STATEMENTS: tuple[str, ...] = (
    _TABLE,
    # The version's own key: one replay each, and the cascade.
    "CREATE UNIQUE INDEX uq_skill_replays_version_id ON sales.skill_replays (version_id)",
    # The skills list's read: the tenant's replays of the versions it shows.
    "CREATE INDEX ix_skill_replays_tenant_id_version_id"
    " ON sales.skill_replays (tenant_id, version_id)",
    "CREATE INDEX ix_skill_replays_workspace_id ON sales.skill_replays (workspace_id)",
    "ALTER TABLE sales.skill_replays ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.skill_replays FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_skill_replays ON sales.skill_replays"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.skill_replays TO dw_app;
            REVOKE UPDATE, DELETE ON sales.skill_replays FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE sales.skill_replays")
