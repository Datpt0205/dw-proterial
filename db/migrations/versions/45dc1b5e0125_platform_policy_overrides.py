"""platform.policy_overrides — the tenant-write half of TenantOverlay's own

Revision ID: 45dc1b5e0125
Revises: dd1db8ca43a2
Create Date: 2026-09-24

`dw_kernel.overlay.TenantOverlay`'s own docstring already names "a policy" as
one of five artifact kinds it exists to cover, alongside prompt/tool spec/
toolset/model profile — but only those four have ever been wired, and even
they only ever get the platform layer at runtime: nothing loads a tenant
layer into them in production, and nothing lets a caller write one. This
table is that missing half, for policies specifically — CLAUDE.md's own
"one deployment serves many customers whose processes differ" is not real
until a customer's own value can reach a policy without a code deploy.

Deliberately platform-owned: this mechanism is not business-domain-
specific — `retention_policy`/the
spend-guard quota plans are the two existing "numbers differ per company"
cases in this repo and both currently bypass any override mechanism
entirely (loaded as one flat platform-wide instance); they are candidates
to adopt this same table later, not migrated here.

`content` is JSONB, not typed columns — this table's job is "does a row
exist for (tenant_id, policy_id)", never "is this content valid for that
policy id"; validating a submitted document against its own Pydantic
schema (the Pydantic model a context declares for its own `policy_id`) is
that policy's own bounded context's job, the same
"consumer declares, never re-derived" split this repo already draws
everywhere else. A full-document replacement per `(tenant_id, policy_id)`,
not a field-level merge with the platform default — matches how the other
four `TenantOverlay` artifact kinds already resolve (tenant's own version
whole, or the platform's whole, never blended), not a new merge semantic
invented for this one.

`tenant_id` only, no `workspace_id` — mirrors `platform.entitlements`
(`0001_platform_baseline.sql`), the existing precedent for "one row per
company, not per team": a plan/quota is a company-wide decision in this
platform's model, and an SLA policy is the same shape of decision.

No grants block: `0001_platform_grants.sql`'s `ALTER DEFAULT PRIVILEGES IN
SCHEMA platform` already covers a table the migrator creates later, same
reasoning `2b5ff2bceb06_tenant_daily_spend_guard.py` gives for the same
schema. `updated_at` is trigger-maintained by the existing `platform.
touch_updated_at()`, reused not redefined, same as `po_cases` — a tenant
overwriting their own override is a real edit worth timestamping precisely,
not something the application should have to remember to set by hand.
"""

from __future__ import annotations

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = '45dc1b5e0125'
down_revision = 'dd1db8ca43a2'
branch_labels = None
depends_on = None

_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)

_UPGRADE = (
    """
    CREATE TABLE platform.policy_overrides (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        policy_id text NOT NULL,
        content jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_policy_overrides PRIMARY KEY (id),
        CONSTRAINT uq_policy_overrides_tenant_id_policy_id UNIQUE (tenant_id, policy_id),
        CONSTRAINT fk_policy_overrides_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_policy_overrides_policy_id CHECK (policy_id <> '')
    )
    """,
    # No separate tenant_id index: the UNIQUE(tenant_id, policy_id) constraint
    # above already leads with tenant_id, serving an RLS-filtered lookup by
    # itself without a redundant second index on the same leading column.
    "ALTER TABLE platform.policy_overrides ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.policy_overrides FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_policy_overrides ON platform.policy_overrides"
    f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}",
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON platform.policy_overrides"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()",
)

_DOWNGRADE = ("DROP TABLE platform.policy_overrides",)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
