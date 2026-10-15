"""platform sod rule change rechecks memberships

Revision ID: d82a60870baf
Revises: 2e0354b50d10
Create Date: 2026-10-15 03:40:12.000000+00:00

Separation of duties is checked when a membership is written (b9862fa13a80)
and when a role or permission set it holds changes its scopes (f381f1694395).
It was not checked when the rule itself changed: a migration could add a scope
to `left_scopes` or `right_scopes`, add a rule, or clear `waivable`, and every
membership that then held both sides broke the rule silently. Each rule a
context added so far carried its own hand-written check (68305ebe4a83);
6b26771e549d asks the same of a migration clearing `waivable`. This makes both
the database's.

An AFTER INSERT trigger, and an AFTER UPDATE trigger on `key`, `left_scopes`,
`right_scopes` and `waivable` when one of them actually changes, on
`platform.sod_rules`. Either refuses the write while any membership breaks the
rule as it now reads, unless the rule is waivable and the membership's own
tenant holds an open, confirmed waiver of it (what `sod_violation` honours).
It names the rule and lists up to 20 membership ids in DETAIL
(`ck_sod_rules_memberships`), the shape of `ck_roles_sod_memberships`: the
migration fails, and its author fixes the memberships or the rule first.

Only this rule is asked about (`sod_rule_broken`), not the first rule a
membership breaks: a membership already holding both sides of ANOTHER rule
under an old unconfirmed waiver (f381f1694395 left those as they were) must
not block an unrelated rule's change. Changing `description` alone is never
checked. `dw_app` holds no write on the table (b9862fa13a80), so only a
migration reaches this today.
"""

from __future__ import annotations

from alembic import op

revision = "d82a60870baf"
down_revision = "2e0354b50d10"
branch_labels = None
depends_on = None

_REFUSE = """
    CREATE OR REPLACE FUNCTION platform.refuse_rule_change_breaking_memberships()
    RETURNS trigger
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, platform
    AS $$
    DECLARE
        broken integer;
        listed text;
    BEGIN
        -- AFTER: the catalogue already reads the new rule, so `sod_rule_broken`
        -- answers for the rule as it will be.
        WITH holders AS (
            SELECT m.id
            FROM platform.memberships m
            WHERE platform.sod_rule_broken(NEW.key, m.role_keys, m.permission_set_keys)
              AND NOT (
                  NEW.waivable AND EXISTS (
                      SELECT 1 FROM platform.sod_waivers w
                      WHERE w.tenant_id = m.tenant_id
                        AND w.rule_key = NEW.key
                        AND w.revoked_at IS NULL
                        AND w.confirmed_at IS NOT NULL
                  )
              )
        )
        SELECT count(*), string_agg(id::text, ', ' ORDER BY id) FILTER (WHERE rn <= 20)
        INTO broken, listed
        FROM (SELECT h.id, row_number() OVER (ORDER BY h.id) AS rn FROM holders h) ranked;
        IF broken > 0 THEN
            RAISE EXCEPTION 'rule % as written would be broken by % membership(s)',
                NEW.key, broken
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'ck_sod_rules_memberships',
                      DETAIL = listed;
        END IF;
        RETURN NULL;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_REFUSE)
    # Idempotent, as f381f1694395 is: a product carrying the same triggers
    # lands on this state instead of failing.
    op.execute("DROP TRIGGER IF EXISTS trg_sod_rules_memberships_insert ON platform.sod_rules")
    op.execute(
        """
        CREATE TRIGGER trg_sod_rules_memberships_insert
        AFTER INSERT ON platform.sod_rules
        FOR EACH ROW
        EXECUTE FUNCTION platform.refuse_rule_change_breaking_memberships()
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_sod_rules_memberships_update ON platform.sod_rules")
    op.execute(
        """
        CREATE TRIGGER trg_sod_rules_memberships_update
        AFTER UPDATE OF key, left_scopes, right_scopes, waivable ON platform.sod_rules
        FOR EACH ROW
        WHEN (
            (OLD.key, OLD.left_scopes, OLD.right_scopes, OLD.waivable)
            IS DISTINCT FROM (NEW.key, NEW.left_scopes, NEW.right_scopes, NEW.waivable)
        )
        EXECUTE FUNCTION platform.refuse_rule_change_breaking_memberships()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sod_rules_memberships_update ON platform.sod_rules")
    op.execute("DROP TRIGGER IF EXISTS trg_sod_rules_memberships_insert ON platform.sod_rules")
    op.execute("DROP FUNCTION IF EXISTS platform.refuse_rule_change_breaking_memberships()")
