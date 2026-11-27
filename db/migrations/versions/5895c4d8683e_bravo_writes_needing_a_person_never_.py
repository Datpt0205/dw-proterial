"""bravo writes needing a person never falls when a stale claim settles

Revision ID: 5895c4d8683e
Revises: fc8d358317fe
Create Date: 2026-11-27 01:44:00.945277+00:00

Sales ticket 84, from its review. `DwBravoWriteNeedsAPerson` fires when
`bravo.writes_needing_a_person()` rises, and Prometheus reads a rise as the
newest sample above the oldest in its window. `fc8d358317fe` counted a row
still `claimed` 15 minutes on, and the gateway's settle has no age limit: a
write that hung on Bravo and then settled `written` left the count. That
drop, landing in the same sample as a new `in_doubt` row, cancelled it, and
the new one reached nobody.

A row that was ever 15 minutes claimed is counted for good: still claimed, or
settled more than 15 minutes after its claim. It was told as needing a person
when it went stale, so it stays told. The count then falls only when a
tenant's ledger is deleted with the tenant.

`CREATE OR REPLACE` keeps the function's owner and its grants: EXECUTE for
`dw_app` only (`test_bravo_ledger_health_db.py` asserts it).
"""

from __future__ import annotations

from alembic import op

revision = "5895c4d8683e"
down_revision = "fc8d358317fe"
branch_labels = None
depends_on = None

_STALE = "interval '15 minutes'"


def _replace(stale_settled: bool) -> str:
    settled_late = (
        f"\n                OR settled_at > claimed_at + {_STALE}" if stale_settled else ""
    )
    return f"""
        CREATE OR REPLACE FUNCTION bravo.writes_needing_a_person()
        RETURNS bigint
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, bravo
        AS $$
            SELECT count(*) FROM bravo.write_ledger
             WHERE status IN ('in_doubt', 'reconcile_failed')
                OR (status = 'claimed' AND claimed_at < now() - {_STALE}){settled_late}
        $$
        """


def upgrade() -> None:
    op.execute(_replace(stale_settled=True))


def downgrade() -> None:
    op.execute(_replace(stale_settled=False))
