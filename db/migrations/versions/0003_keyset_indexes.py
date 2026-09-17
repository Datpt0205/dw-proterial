"""Indexes for the keyset orderings the list endpoints actually run.

Revision ID: 397e15693ea0
Revises: 894989786cc8
Create Date: 2026-09-17

Cursor pagination replaced ``OFFSET`` in 0002's change, which fixes the page
*after* the first one — but only if an index carries the ordering. Without one
Postgres still reads every matching row and sorts, so page 50 costs what page 1
costs and the plan degrades with the table, which is precisely what keyset
pagination was adopted to stop. ``memory.items`` was the worst of the three: it
carried no index at all beyond its primary key, so every list was a sequential
scan regardless of how it was paged.

Each index below is (RLS predicate, query predicate, sort key) in that order,
matching what the repository issues:

- ``memory.items`` — ``dw_memory.service`` filters ``workspace_id`` and orders
  ``created_at DESC, memory_id DESC``.
- ``knowledge.documents`` — ``dw_knowledge.gateway`` filters ``status`` and
  orders ``created_at DESC, id DESC``. The workspace/scope, classification and
  ACL predicates are an ``OR``/``IN``/``ANY`` and cannot be indexed usefully
  alongside the sort; they are filtered on the rows the index returns.
- ``platform.approval_requests`` — ``list_pending`` filters ``status`` and
  orders ``created_at DESC, id DESC``.

One index here is not a page at all: ``ix_worker_runs_tenant_created`` serves
the per-tenant daily run quota, which counts a date range on the table that
grows fastest in this schema, on the path that starts every run.

``tenant_id`` leads all three because RLS supplies that equality on every
statement; a query never names it, which is exactly why the index must.

The two old indexes are dropped rather than left in place: each is an exact
leading prefix of the index replacing it, so it can answer nothing the new one
cannot, while still costing a write on every insert and update.

DESC matters on both sort columns. A default ASC index can be read backwards,
but only as a whole — and these are composite orderings, so an ASC index would
have to be walked in reverse on one column and forward on the other, which no
scan does.
"""

from __future__ import annotations

from alembic import op

revision = "397e15693ea0"
down_revision = "894989786cc8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_items_page ON memory.items"
        " (tenant_id, workspace_id, created_at DESC, memory_id DESC)"
    )

    op.execute(
        "CREATE INDEX ix_documents_page ON knowledge.documents"
        " (tenant_id, status, created_at DESC, id DESC)"
    )
    op.execute("DROP INDEX knowledge.ix_documents_status")

    op.execute(
        "CREATE INDEX ix_approval_requests_page ON platform.approval_requests"
        " (tenant_id, status, created_at DESC, id DESC)"
    )
    op.execute("DROP INDEX platform.ix_approval_requests_tenant_status")

    # Not a page — the daily run quota counts this range on every run a tenant
    # starts, and worker_runs is the table that grows fastest of any here.
    op.execute(
        "CREATE INDEX ix_worker_runs_tenant_created ON platform.worker_runs (tenant_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX platform.ix_worker_runs_tenant_created")

    op.execute(
        "CREATE INDEX ix_approval_requests_tenant_status ON platform.approval_requests"
        " (tenant_id, status)"
    )
    op.execute("DROP INDEX platform.ix_approval_requests_page")

    op.execute("CREATE INDEX ix_documents_status ON knowledge.documents (tenant_id, status)")
    op.execute("DROP INDEX knowledge.ix_documents_page")

    op.execute("DROP INDEX memory.ix_items_page")
