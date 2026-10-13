"""platform audit events support grant index

Revision ID: f1980035d8de
Revises: 0d7fd21052a4
Create Date: 2026-10-12 13:55:49.237424+00:00

`GET /audit/events?support_grant_id=` (support-access ticket 02, step 10)
lists one grant's events: its lifecycle (`support.grant.*`) and every
`support.access` under it, each carrying `details.support_grant_id`. Those rows
are sparse in a trail that grows without bound, so walking
`ix_audit_events_page` and discarding everything else would read the whole
workspace's trail newer than a months-old grant to fill one page. This index is
(RLS predicate, query predicates, sort key), the shape `0003` set and
`ix_audit_events_page` already has, and partial: only rows that carry a grant
id are in it, so it costs nothing on the rest of the trail.

Built on the partitioned parent, so Postgres builds it on every partition and
gives it to each one `ensure_time_partitions` creates later. Locking is the same
as `6d4aed20ccf2`'s: a SHARE lock on the parent and every partition for the
build, acceptable while no deployed environment holds a populated trail; on a
large one, build it per partition concurrently and attach, as that revision
describes.
"""

from __future__ import annotations

from alembic import op

revision = "f1980035d8de"
down_revision = "0d7fd21052a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_audit_events_support_grant ON platform.audit_events"
        " (tenant_id, workspace_id, (details ->> 'support_grant_id'), occurred_at DESC, id DESC)"
        " WHERE (details ->> 'support_grant_id') IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX platform.ix_audit_events_support_grant")
