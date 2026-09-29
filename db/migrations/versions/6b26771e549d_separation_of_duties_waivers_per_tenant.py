"""separation of duties waivers per tenant

Revision ID: 6b26771e549d
Revises: 648e2f7c3edb
Create Date: 2026-09-28

A company too small to staff both sides of a separation-of-duty rule may
waive it, on the record. ISO/IEC 27001:2022 A.5.3 and NIST SP 800-53 AC-5
both allow this where segregation is impractical, provided compensating
controls (a record, review, monitoring) take its place. Đạt asked for exactly
that: a per-tenant exemption, with audit.

- **`platform.sod_rules.waivable`**, false unless a rule's author says
  otherwise. A rule whose author did not mark it waivable is a floor no
  tenant can lower. A context marks its own rules in its own migration.
- **`platform.sod_waivers`**: one row per decision, tenant-wide (tenant_id
  only, like `platform.entitlements` and `platform.policy_overrides`), with a
  mandatory reason, who granted it and when. Revoking closes the row
  (`revoked_at`, `revoked_by`, `revoke_reason`). Rows are never deleted:
  dw_app has no DELETE, so offboarding keeps them with the audit log (its
  purge covers only tables dw_app may delete from). At most one open waiver
  per rule per tenant.
- **`platform.sod_violation(tenant_id, role_keys, permission_set_keys)`**
  replaces the two-argument version. A broken rule is skipped only when it
  is waivable AND that tenant holds an open waiver for it. The tenant is the
  membership row's own, never a session setting. A NULL tenant asks about the
  rules alone. Clearing `waivable` later therefore makes the rule's open
  waivers lift nothing; a migration doing that must first check that no
  membership relies on them, as 2a0ac1ac32e1 does for new rules.
- **Waiver guards** (every writer, the migrator included):
  - insert: only a waivable rule;
  - update: only the closing of an open waiver, leaving what was decided
    unchanged; a closed waiver is history;
  - after closing: refused while any membership of that tenant still breaks
    the rule. Fix the memberships first.
- **Races.** When a waiver is what lets a membership write through,
  `sod_violation` takes it FOR SHARE. A revoke therefore waits for that
  write to commit before its trigger runs (Postgres locks the row first), and
  the trigger's fresh snapshot sees the new membership. A write that arrives
  while a revoke is uncommitted waits too, and then finds the waiver closed.

Waiving is `platform.sod_waivers.write`, granted to org_admin. Reading the
rules and waivers is the existing `platform.roles.read`. The app writes a
`platform.audit_events` row for each grant or revoke in the same transaction.
"""

from __future__ import annotations

from alembic import op

revision = "6b26771e549d"
down_revision = "648e2f7c3edb"
branch_labels = None
depends_on = None

_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)
_WAIVE_SCOPE = "platform.sod_waivers.write"

# The body of the two-argument function b9862fa13a80 created, restored on
# downgrade exactly as it was.
_TWO_ARGUMENT_VIOLATION = """
    CREATE FUNCTION platform.sod_violation(role_keys jsonb, permission_set_keys jsonb)
    RETURNS TABLE (rule_key text, rule_description text)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, platform
    AS $$
        WITH held AS (
            SELECT scope
            FROM platform.roles r,
                 jsonb_array_elements_text(r.scopes) AS scope
            WHERE r.key IN (SELECT jsonb_array_elements_text(role_keys))
            UNION
            SELECT scope
            FROM platform.permission_sets p,
                 jsonb_array_elements_text(p.scopes) AS scope
            WHERE p.key IN (SELECT jsonb_array_elements_text(permission_set_keys))
        )
        SELECT s.key, s.description
        FROM platform.sod_rules s
        WHERE EXISTS (
            SELECT 1 FROM held
            WHERE held.scope IN (SELECT jsonb_array_elements_text(s.left_scopes))
        )
          AND EXISTS (
            SELECT 1 FROM held
            WHERE held.scope IN (SELECT jsonb_array_elements_text(s.right_scopes))
        )
        ORDER BY s.key
        LIMIT 1
    $$
"""


def _enforce_function(call: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION platform.enforce_separation_of_duties()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, platform
        AS $$
        DECLARE
            broken record;
        BEGIN
            SELECT * INTO broken
            FROM {call};
            IF FOUND THEN
                RAISE EXCEPTION 'separation of duties: %', broken.rule_key
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = broken.rule_key,
                          DETAIL = broken.rule_description;
            END IF;
            RETURN NEW;
        END
        $$
        """


def upgrade() -> None:
    op.execute("ALTER TABLE platform.sod_rules ADD COLUMN waivable boolean DEFAULT false NOT NULL")

    op.execute(
        """
        CREATE TABLE platform.sod_waivers (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            rule_key text NOT NULL,
            reason text NOT NULL,
            granted_by uuid NOT NULL,
            granted_at timestamp with time zone DEFAULT now() NOT NULL,
            revoked_at timestamp with time zone,
            revoked_by uuid,
            revoke_reason text,
            CONSTRAINT pk_sod_waivers PRIMARY KEY (id),
            CONSTRAINT fk_sod_waivers_tenant_id_tenants FOREIGN KEY (tenant_id)
                REFERENCES platform.tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_sod_waivers_rule_key_sod_rules FOREIGN KEY (rule_key)
                REFERENCES platform.sod_rules (key) ON DELETE RESTRICT,
            CONSTRAINT ck_sod_waivers_reason CHECK (btrim(reason) <> ''),
            CONSTRAINT ck_sod_waivers_revocation CHECK (
                (revoked_at IS NULL) = (revoked_by IS NULL)
                AND (revoked_at IS NULL) = (revoke_reason IS NULL)
                AND (revoke_reason IS NULL OR btrim(revoke_reason) <> '')
            )
        )
        """
    )
    # Carries the tenant FK and the list's order (newest first); the partial
    # unique index below cannot, being partial.
    op.execute(
        "CREATE INDEX ix_sod_waivers_tenant_id_granted_at"
        " ON platform.sod_waivers (tenant_id, granted_at DESC)"
    )
    op.execute("CREATE INDEX ix_sod_waivers_rule_key ON platform.sod_waivers (rule_key)")
    op.execute(
        "CREATE UNIQUE INDEX uq_sod_waivers_open ON platform.sod_waivers (tenant_id, rule_key)"
        " WHERE revoked_at IS NULL"
    )
    op.execute("ALTER TABLE platform.sod_waivers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.sod_waivers FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_sod_waivers ON platform.sod_waivers"
        f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
    )
    # History: the default privileges handed dw_app DELETE, and a waiver is
    # closed, never removed.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                REVOKE DELETE, TRUNCATE ON platform.sod_waivers FROM dw_app;
            END IF;
        END
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION platform.sod_rule_broken(
            p_rule_key text, p_role_keys jsonb, p_permission_set_keys jsonb
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
            WITH held AS (
                SELECT scope
                FROM platform.roles r,
                     jsonb_array_elements_text(r.scopes) AS scope
                WHERE r.key IN (SELECT jsonb_array_elements_text(p_role_keys))
                UNION
                SELECT scope
                FROM platform.permission_sets p,
                     jsonb_array_elements_text(p.scopes) AS scope
                WHERE p.key IN (SELECT jsonb_array_elements_text(p_permission_set_keys))
            )
            SELECT EXISTS (
                SELECT 1 FROM held, platform.sod_rules s
                WHERE s.key = p_rule_key
                  AND held.scope IN (SELECT jsonb_array_elements_text(s.left_scopes))
            )
               AND EXISTS (
                SELECT 1 FROM held, platform.sod_rules s
                WHERE s.key = p_rule_key
                  AND held.scope IN (SELECT jsonb_array_elements_text(s.right_scopes))
            )
        $$
        """
    )
    op.execute("DROP FUNCTION platform.sod_violation(jsonb, jsonb)")
    op.execute(
        """
        CREATE FUNCTION platform.sod_violation(
            p_tenant_id uuid, p_role_keys jsonb, p_permission_set_keys jsonb
        )
        RETURNS TABLE (rule_key text, rule_description text)
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
        #variable_conflict use_column
        DECLARE
            candidate record;
        BEGIN
            FOR candidate IN
                SELECT s.key, s.description, s.waivable FROM platform.sod_rules s ORDER BY s.key
            LOOP
                CONTINUE WHEN NOT platform.sod_rule_broken(
                    candidate.key, p_role_keys, p_permission_set_keys
                );
                IF candidate.waivable AND p_tenant_id IS NOT NULL THEN
                    -- FOR SHARE: a concurrent revoke of this waiver waits for
                    -- the write relying on it, and then sees that write.
                    PERFORM 1
                    FROM platform.sod_waivers w
                    WHERE w.tenant_id = p_tenant_id
                      AND w.rule_key = candidate.key
                      AND w.revoked_at IS NULL
                    FOR SHARE;
                    CONTINUE WHEN FOUND;
                END IF;
                rule_key := candidate.key;
                rule_description := candidate.description;
                RETURN NEXT;
                RETURN;
            END LOOP;
        END
        $$
        """
    )
    op.execute(
        _enforce_function(
            "platform.sod_violation(NEW.tenant_id, NEW.role_keys, NEW.permission_set_keys)"
        )
    )

    op.execute(
        """
        CREATE FUNCTION platform.guard_sod_waiver()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT EXISTS (
                    SELECT 1 FROM platform.sod_rules WHERE key = NEW.rule_key AND waivable
                ) THEN
                    RAISE EXCEPTION 'rule % cannot be waived', NEW.rule_key
                        USING ERRCODE = 'check_violation',
                              CONSTRAINT = 'ck_sod_waivers_rule_waivable';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.revoked_at IS NOT NULL
               OR NEW.revoked_at IS NULL
               OR (NEW.id, NEW.tenant_id, NEW.rule_key, NEW.reason, NEW.granted_by,
                   NEW.granted_at)
                  IS DISTINCT FROM
                  (OLD.id, OLD.tenant_id, OLD.rule_key, OLD.reason, OLD.granted_by,
                   OLD.granted_at)
            THEN
                RAISE EXCEPTION 'a waiver can only be revoked, once'
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'ck_sod_waivers_revoke_only';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sod_waivers_guard
        BEFORE INSERT OR UPDATE ON platform.sod_waivers
        FOR EACH ROW EXECUTE FUNCTION platform.guard_sod_waiver()
        """
    )
    op.execute(
        """
        CREATE FUNCTION platform.refuse_revoking_a_waiver_in_use()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
        DECLARE
            relying integer;
        BEGIN
            -- The waiver row is locked before a row trigger runs, so a
            -- membership write holding it FOR SHARE has committed by now, and
            -- this query (plpgsql, so a fresh snapshot) sees that write.
            SELECT count(*) INTO relying
            FROM platform.memberships m
            WHERE m.tenant_id = NEW.tenant_id
              AND platform.sod_rule_broken(NEW.rule_key, m.role_keys, m.permission_set_keys);
            IF relying > 0 THEN
                RAISE EXCEPTION 'waiver of % is relied on by % membership(s)',
                    NEW.rule_key, relying
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'ck_sod_waivers_not_in_use',
                          DETAIL = relying::text;
            END IF;
            RETURN NULL;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sod_waivers_not_in_use
        AFTER UPDATE OF revoked_at ON platform.sod_waivers
        FOR EACH ROW
        WHEN (OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL)
        EXECUTE FUNCTION platform.refuse_revoking_a_waiver_in_use()
        """
    )

    op.execute(
        f"""
        UPDATE platform.roles
        SET scopes = scopes || '["{_WAIVE_SCOPE}"]'::jsonb
        WHERE key = 'org_admin' AND NOT scopes ? '{_WAIVE_SCOPE}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - '{_WAIVE_SCOPE}' WHERE key = 'org_admin'"
    )
    op.execute("DROP TABLE platform.sod_waivers")
    op.execute("DROP FUNCTION platform.refuse_revoking_a_waiver_in_use()")
    op.execute("DROP FUNCTION platform.guard_sod_waiver()")
    op.execute("DROP FUNCTION platform.sod_violation(uuid, jsonb, jsonb)")
    op.execute(_TWO_ARGUMENT_VIOLATION)
    op.execute(_enforce_function("platform.sod_violation(NEW.role_keys, NEW.permission_set_keys)"))
    op.execute("DROP FUNCTION platform.sod_rule_broken(text, jsonb, jsonb)")
    op.execute("ALTER TABLE platform.sod_rules DROP COLUMN waivable")
