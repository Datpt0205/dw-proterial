"""purchasing rows pruned per tenant term

Revision ID: 191b591d4ef1
Revises: fcc0e57d0817
Create Date: 2026-11-01 10:06:02.526064+00:00

How long DW2 keeps rows is each tenant's own rule now
(`purchasing_rules@1.6.0`, `retention`), not one platform term
(`retention@1.10.0`'s `tables`, dropped in 1.11.0). So the sweep is per
workspace:

- **`purchasing.retention_scopes()`**, SECURITY DEFINER: every (tenant,
  workspace) holding a case or a mail outcome, ids only, the one read across
  tenants the lane makes.
- **`purchasing.prune_expired_in(tenant, workspace, cases_before,
  outcomes_before)`**, SECURITY DEFINER: that workspace's mail outcomes
  settled before their cutoff, then its cases received before theirs (their
  outcomes go with them, `ON DELETE CASCADE`); the two counts. A NULL cutoff
  deletes nothing of its table.
- **`purchasing.prune_expired(cutoffs)`** is dropped: one term for every
  tenant is what this replaces, and nothing calls it.

EXECUTE to `dw_app` only, revoked from PUBLIC; `dw_app` still holds no
DELETE on `mail_outcomes`.
"""

from __future__ import annotations

from alembic import op

revision = "191b591d4ef1"
down_revision = "fcc0e57d0817"
branch_labels = None
depends_on = None

_SCOPES = "purchasing.retention_scopes()"
_PRUNE = "purchasing.prune_expired_in(uuid, uuid, timestamptz, timestamptz)"
_OLD = "purchasing.prune_expired(timestamptz, timestamptz)"


def _grant(function: str) -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO dw_app")


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION purchasing.retention_scopes()
        RETURNS TABLE (tenant_id uuid, workspace_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, purchasing
        AS $$
            SELECT c.tenant_id, c.workspace_id FROM purchasing.cases c
            UNION
            SELECT o.tenant_id, o.workspace_id FROM purchasing.mail_outcomes o
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION purchasing.prune_expired_in(
            in_tenant uuid, in_workspace uuid,
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
                DELETE FROM purchasing.mail_outcomes
                 WHERE tenant_id = in_tenant AND workspace_id = in_workspace
                   AND settled_at < outcomes_before;
                GET DIAGNOSTICS gone_outcomes = ROW_COUNT;
            END IF;
            IF cases_before IS NOT NULL THEN
                DELETE FROM purchasing.cases
                 WHERE tenant_id = in_tenant AND workspace_id = in_workspace
                   AND received_at < cases_before;
                GET DIAGNOSTICS gone_cases = ROW_COUNT;
            END IF;
            RETURN QUERY SELECT gone_cases, gone_outcomes;
        END
        $$
        """
    )
    _grant(_SCOPES)
    _grant(_PRUNE)
    op.execute(f"DROP FUNCTION {_OLD}")


def downgrade() -> None:
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
    _grant(_OLD)
    op.execute(f"DROP FUNCTION {_PRUNE}")
    op.execute(f"DROP FUNCTION {_SCOPES}")
