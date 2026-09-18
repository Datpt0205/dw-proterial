"""Let the retention sweep see memory across tenants, and nothing else.

Retention has to delete expired rows for every tenant. A sweep scoped by
`app.tenant_id` would first need a list of tenants, and getting that list is
itself the cross-tenant read the scoping exists to prevent.

The same escape hatch the outbox and ingest drains already use: a policy that
admits a transaction which has set `app.worker_drain = 'on'`. It is narrow in
the way that matters — the GUC is set per transaction by the sweep itself and
never by anything reachable from a request, so it cannot be turned on by a
caller, a model, or a header.

`memory.items` only. The sweep deletes memories; `memory.item_evidence` follows
through its cascade, and `knowledge.evidence` rows stay because the same chunk
may be cited by a memory that is not expiring.

Reversible: dropping the policy returns memory to tenant-scoped access only,
which also disables the sweep rather than letting it silently delete nothing —
`DELETE` under RLS with no visible rows removes nothing and reports success, so
the sweep would look healthy and do no work. `test_retention_db.py` is what
notices.
"""

from __future__ import annotations

from alembic import op

revision = "9f6b0469f295"
down_revision = "7e242f25deaf"
branch_labels = None
depends_on = None

_DRAIN = "current_setting('app.worker_drain', true) = 'on'"


def upgrade() -> None:
    op.execute(
        f"CREATE POLICY worker_drain_items ON memory.items "
        f"USING ({_DRAIN}) WITH CHECK ({_DRAIN})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS worker_drain_items ON memory.items")
