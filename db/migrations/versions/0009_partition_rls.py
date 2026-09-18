"""RLS on the partitions, not only on the tables they belong to.

A real cross-tenant read, found by trying it rather than by reading the schema:

    SET ROLE dw_app;                                  -- no app.tenant_id set
    SELECT count(*) FROM platform.audit_events;            -> 0   (RLS holds)
    SELECT count(*) FROM platform.audit_events_default;     -> 1   (it does not)

Enabling RLS on a partitioned table applies its policies to the partitions when
rows are reached THROUGH the parent. A partition addressed by its own name is a
table like any other: it uses its own RLS setting and its own policies, and it
had neither. `dw_app` holds SELECT on it, so any tenant's audit trail and any
tenant's model spend were one table name away.

Two tables, and both are ones an attacker would pick first: `audit_events` is
who-did-what for every customer, and `model_usage_ledger` is what everyone is
spending — which is also what the daily spend cap sums.

The invariant checker missed it because it reads migration TEXT, and a partition
is created by the partitioning DDL rather than by a CREATE TABLE it can see.
Text cannot answer this; the catalog can, and there is now an integration test
that asks it — `test_rls_covers_every_tenant_table`, which walks `pg_class` and
includes partitions.

**A new partition needs this too.** Postgres does not inherit RLS to a partition
created later, so whatever adds one must enable, force and police it. The test
above is what makes forgetting fail loudly instead of silently.

Reversible: disabling RLS and dropping the policies returns the partitions to
what they were, which is also exactly the state this migration exists to end.
"""

from __future__ import annotations

from alembic import op

revision = "7e242f25deaf"
down_revision = "62a9aaba6b16"
branch_labels = None
depends_on = None

# The same predicate the parents carry, in the same null-safe form: an unset GUC
# denies rather than raising, so a connection that never set it reads nothing
# instead of erroring in a way a caller might catch and ignore.
_PREDICATE = (
    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)

_PARTITIONS = (
    ("platform", "audit_events_default"),
    ("platform", "model_usage_ledger_default"),
)


def upgrade() -> None:
    for schema, table in _PARTITIONS:
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")
        # FORCE as well: without it the table's owner reads straight past the
        # policy, and the owner is exactly who runs migrations and maintenance.
        op.execute(f"ALTER TABLE {schema}.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {schema}.{table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for schema, table in _PARTITIONS:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {schema}.{table}")
        op.execute(f"ALTER TABLE {schema}.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {schema}.{table} DISABLE ROW LEVEL SECURITY")
