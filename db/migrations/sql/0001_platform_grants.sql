-- ---------------------------------------------------------------------------
-- Privileges.
--
-- The schema is useless without these: a role that cannot read a table is an
-- application that fails on its first real query, while every health check
-- still passes because a health check does not touch a table. That failure
-- mode is why this file exists separately and is verified by a test.
--
-- Roles are a precondition, not something a migration creates — a migration
-- that created LOGIN roles would have to carry their passwords. The deployment
-- creates `dw_app` (and optionally `dw_provisioner`) first; this grants them
-- what they need and warns, loudly and with the fix in the message, when a role
-- is absent.
--
-- `dw_migrator` needs nothing here: it owns the objects.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
        RAISE WARNING USING
            MESSAGE = 'role dw_app does not exist; the application will have no privileges',
            HINT = 'CREATE ROLE dw_app LOGIN PASSWORD ''...''; then re-run this migration';
        RETURN;
    END IF;

    GRANT USAGE ON SCHEMA platform, knowledge, memory TO dw_app;

    -- Read and write everything by default. The exceptions below are the whole
    -- point: they are what the application must NOT be able to do.
    GRANT SELECT, INSERT, UPDATE, DELETE
        ON ALL TABLES IN SCHEMA platform, knowledge, memory TO dw_app;

    -- The audit log is append-only, enforced by the grant rather than by
    -- convention. Code that "would never" rewrite history cannot, and neither
    -- can anything that reaches the database with the application's credentials.
    REVOKE UPDATE, DELETE ON platform.audit_events FROM dw_app;

    -- Provisioning is a different role's record of a different decision; the
    -- application has no business reading or writing it.
    REVOKE ALL ON platform.provisioning_audit FROM dw_app;

    -- A table added by a later migration inherits these, so "somebody forgot to
    -- write the GRANT" stops being a way to ship a broken release.
    ALTER DEFAULT PRIVILEGES IN SCHEMA platform, knowledge, memory
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_app;
END
$$;

DO $$
BEGIN
    -- Optional. Only a deployment that provisions tenants across the platform
    -- creates this role, and /api/v1/platform is not mounted without it.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_provisioner') THEN
        RAISE NOTICE 'role dw_provisioner absent; skipping its grants';
        RETURN;
    END IF;

    GRANT USAGE ON SCHEMA platform TO dw_provisioner;

    -- Named one by one rather than granted wholesale: this role writes across
    -- every tenant, so what it may touch is a list somebody has to extend on
    -- purpose.
    GRANT SELECT, INSERT, UPDATE, DELETE ON
        platform.tenants,
        platform.workspaces,
        platform.users,
        platform.memberships,
        platform.roles,
        platform.plans,
        platform.entitlements,
        platform.platform_operators,
        platform.provisioning_audit
    TO dw_provisioner;
END
$$;
