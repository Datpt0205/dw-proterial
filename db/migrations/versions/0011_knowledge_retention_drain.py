"""Let the knowledge and citation sweeps see across tenants, and nothing else.

`0010` opened `memory.items` for the same reason and with the same reasoning: a
sweep scoped by `app.tenant_id` would first need a list of tenants, and getting
that list is itself the cross-tenant read the scoping exists to prevent. The GUC
is set per transaction by the sweep and is not reachable from a request.

Three tables, and each earns it separately:

- `knowledge.documents` — the sweep deletes documents somebody marked deleted
  once the grace period is over. `knowledge.chunks` is NOT listed: it follows
  through `ON DELETE CASCADE`, and referential-integrity triggers run with the
  table owner's privileges and row security off, so the cascade does not need a
  policy of its own. `test_knowledge_retention_db.py` proves that rather than
  trusting it.
- `knowledge.evidence` — twice over. The document sweep must ask whether ANY
  evidence still cites a document, and `evidence -> documents` is RESTRICT
  enforced by a trigger that ignores RLS: a `NOT EXISTS` that could only see one
  tenant's evidence would clear a document for deletion that the database then
  refuses. And the citation sweep deletes orphaned evidence here.
- `memory.item_evidence` — what makes an evidence row orphaned is the absence of
  a row here, and that question has to be asked across tenants for the same
  reason.

Reversible: dropping a policy returns the table to tenant-scoped access, which
disables the corresponding sweep rather than letting it silently delete nothing.
That distinction matters — `DELETE` under RLS with no visible rows removes
nothing and reports success, so a disabled sweep looks healthy. The integration
tests are what notice.
"""

from __future__ import annotations

from alembic import op

revision = "15276c3c92fa"
down_revision = "9f6b0469f295"
branch_labels = None
depends_on = None

_DRAIN = "current_setting('app.worker_drain', true) = 'on'"

_TABLES = (
    ("worker_drain_documents", "knowledge.documents"),
    ("worker_drain_evidence", "knowledge.evidence"),
    ("worker_drain_item_evidence", "memory.item_evidence"),
)


def upgrade() -> None:
    for policy, table in _TABLES:
        op.execute(f"CREATE POLICY {policy} ON {table} USING ({_DRAIN}) WITH CHECK ({_DRAIN})")


def downgrade() -> None:
    for policy, table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
