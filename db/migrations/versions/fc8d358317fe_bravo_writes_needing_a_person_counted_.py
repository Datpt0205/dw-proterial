"""bravo writes needing a person counted across tenants

Revision ID: fc8d358317fe
Revises: 79418de5ab48
Create Date: 2026-11-26 23:30:43.935340+00:00

Sales ticket 84: the gateway's writes a person has to look at reach the
operator's alerts, from the ledger that owns them (`bravo.write_ledger`,
`2c32bc10b019`), not from a counter of handler calls.

- **`bravo.writes_needing_a_person()`**, SECURITY DEFINER, one bigint: every
  tenant's ledger rows settled `in_doubt` (sent, no answer) or
  `reconcile_failed` (written, and the read-back differs), and rows still
  `claimed` 15 minutes after the claim (the gateway stopped between claim
  and settle, so nobody knows either). A count only: no id, tenant or
  content leaves, so the worker, which holds no tenant scope, may ask it.
  The worker sets `dw_bravo_writes_needing_a_person` from it, and
  `DwBravoWriteNeedsAPerson` fires when it rises.
- EXECUTE for `dw_app` only; PUBLIC's is revoked.
"""

from __future__ import annotations

from alembic import op

revision = "fc8d358317fe"
down_revision = "79418de5ab48"
branch_labels = None
depends_on = None

_FUNCTION = "bravo.writes_needing_a_person()"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION bravo.writes_needing_a_person()
        RETURNS bigint
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, bravo
        AS $$
            SELECT count(*) FROM bravo.write_ledger
             WHERE status IN ('in_doubt', 'reconcile_failed')
                OR (status = 'claimed' AND claimed_at < now() - interval '15 minutes')
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION} FROM PUBLIC")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                GRANT EXECUTE ON FUNCTION {_FUNCTION} TO dw_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {_FUNCTION}")
