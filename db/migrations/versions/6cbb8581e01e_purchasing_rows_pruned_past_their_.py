"""purchasing rows pruned past their retention term

Revision ID: 6cbb8581e01e
Revises: e823f9c57e5a
Create Date: 2026-11-01 09:00:00.000000+00:00

`retention@1.10.0` gives DW2's own tables a term (`tables`): ten years for a
purchase case, one year for what DW2 did with a mail, proposed and waiting on
Proterial's accountant. `dw_app` holds no DELETE on `mail_outcomes` (a
settled mail is a fact), so the worker's `purchasing_retention` lane deletes
through one function:

- **`purchasing.prune_expired(cases_before, outcomes_before)`**, SECURITY
  DEFINER, owned by the migrator (which bypasses RLS: the sweep is every
  tenant's), `search_path` pinned. Deletes the mail outcomes settled before
  their cutoff, then the cases received before theirs (their outcomes go with
  them, `ON DELETE CASCADE`), and returns the two counts. A NULL cutoff
  deletes nothing of that table: a term nobody wrote keeps every row.
  EXECUTE to `dw_app` only.
"""

from __future__ import annotations

from alembic import op

revision = "6cbb8581e01e"
down_revision = "e823f9c57e5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION purchasing.prune_expired(
            cases_before timestamptz, outcomes_before timestamptz
        ) RETURNS TABLE (cases bigint, outcomes bigint)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, purchasing
        AS $$
        DECLARE
            gone_outcomes bigint := 0;
            gone_cases bigint := 0;
        BEGIN
            IF outcomes_before IS NOT NULL THEN
                DELETE FROM purchasing.mail_outcomes WHERE settled_at < outcomes_before;
                GET DIAGNOSTICS gone_outcomes = ROW_COUNT;
            END IF;
            IF cases_before IS NOT NULL THEN
                DELETE FROM purchasing.cases WHERE received_at < cases_before;
                GET DIAGNOSTICS gone_cases = ROW_COUNT;
            END IF;
            RETURN QUERY SELECT gone_cases, gone_outcomes;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION purchasing.prune_expired(timestamptz, timestamptz) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION purchasing.prune_expired(timestamptz, timestamptz) TO dw_app"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION purchasing.prune_expired(timestamptz, timestamptz)")
