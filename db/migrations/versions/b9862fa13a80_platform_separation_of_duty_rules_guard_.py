"""platform separation of duty rules guard memberships

Revision ID: b9862fa13a80
Revises: 45dc1b5e0125
Create Date: 2026-09-28

Static separation of duties (NIST RBAC's SSD; NIST SP 800-53 AC-5): some
pairs of authority must never meet in one person's membership, such as
ordering goods and confirming their payment. Until now that was a comment in a
role catalogue. This makes it a rule the database enforces.

- **`platform.sod_rules`** is a platform-wide catalogue, like `platform.roles`:
  a rule is violated when one membership holds any scope of `left_scopes` AND
  any scope of `right_scopes`. Rules are written in terms of scopes, not role
  keys, so a permission set (`memberships.permission_set_keys`) cannot carry a
  forbidden scope past a check that only looked at roles. A bounded context
  adds its rules in its own migrations, the same way it adds its roles.
- **`platform.sod_violation(role_keys, permission_set_keys)`** returns the
  first rule a combination breaks, or nothing. It is SECURITY DEFINER with a
  pinned search_path, so every role that writes memberships (`dw_app`,
  `dw_provisioner`, `dw_migrator`) is judged by the same reading of the
  catalogue whatever it may itself select.
- **A trigger on `platform.memberships`**, on INSERT and on any UPDATE of
  `role_keys` or `permission_set_keys`, refuses a violating row with SQLSTATE
  23514 and the rule's key as the constraint name.
  - Seven code paths write memberships (admin grants, permission sets,
    provisioning, first login, the hierarchy, seed, a script). One trigger
    covers all of them, including an upsert's update half, and there is no
    second copy of the rule to drift.
  - The application maps the error to a 409.

`dw_app` may read the rules but not write them. The application enforcing a
rule must not be able to delete it. Its broad write grant on the other
catalogue tables (`platform.roles`, `platform.permission_sets`) predates this
change and is recorded as a separate decision.

`platform_admin` holds the break-glass scope `platform.admin`, which no rule
names. Rules constrain ordinary authority, not the emergency role.
"""

from __future__ import annotations

from alembic import op

revision = "b9862fa13a80"
down_revision = "45dc1b5e0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.sod_rules (
            key text NOT NULL,
            description text NOT NULL,
            left_scopes jsonb NOT NULL,
            right_scopes jsonb NOT NULL,
            CONSTRAINT pk_sod_rules PRIMARY KEY (key),
            CONSTRAINT ck_sod_rules_key CHECK (key ~ '^sod_[a-z0-9_]+$'),
            CONSTRAINT ck_sod_rules_left_scopes CHECK (
                jsonb_typeof(left_scopes) = 'array' AND jsonb_array_length(left_scopes) > 0
            ),
            CONSTRAINT ck_sod_rules_right_scopes CHECK (
                jsonb_typeof(right_scopes) = 'array' AND jsonb_array_length(right_scopes) > 0
            )
        )
        """
    )
    # Read, never rewrite: the default privileges handed dw_app all four.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                REVOKE INSERT, UPDATE, DELETE ON platform.sod_rules FROM dw_app;
                GRANT SELECT ON platform.sod_rules TO dw_app;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
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
    )
    op.execute(
        """
        CREATE FUNCTION platform.enforce_separation_of_duties()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, platform
        AS $$
        DECLARE
            broken record;
        BEGIN
            SELECT * INTO broken
            FROM platform.sod_violation(NEW.role_keys, NEW.permission_set_keys);
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
    )
    op.execute(
        """
        CREATE TRIGGER trg_memberships_separation_of_duties
        BEFORE INSERT OR UPDATE OF role_keys, permission_set_keys ON platform.memberships
        FOR EACH ROW EXECUTE FUNCTION platform.enforce_separation_of_duties()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_memberships_separation_of_duties ON platform.memberships")
    op.execute("DROP FUNCTION platform.enforce_separation_of_duties()")
    op.execute("DROP FUNCTION platform.sod_violation(jsonb, jsonb)")
    op.execute("DROP TABLE platform.sod_rules")
