-- ---------------------------------------------------------------------------
-- Reference rows the schema itself depends on.
--
-- `platform.entitlements.plan_id` is a foreign key into `platform.plans`, so a
-- plan catalogue is not seed data a demo adds — it is part of the schema being
-- usable at all. Without these rows, granting any tenant any plan fails on the
-- constraint, which is exactly how this was found: every platform integration
-- test died on `Key (plan_id)=(professional) is not present in table "plans"`.
--
-- The same three plans are declared in `dw_platform.application.entitlement`
-- as `DEFAULT_PLANS`, because the service answers "does this plan include that
-- feature" in memory on every request and will not go to the database for it.
-- Two declarations of one fact is a drift risk, and the honest mitigation is
-- that the database is the one that can refuse: the FK means a tenant cannot be
-- granted a plan that is not here, so a code-only plan fails loudly at the first
-- grant rather than quietly at the first entitlement check.
--
-- `ON CONFLICT DO UPDATE` rather than `DO NOTHING`: re-running the baseline
-- against a database that already has these rows should leave them matching
-- this file, not leave whatever was there.
-- ---------------------------------------------------------------------------

INSERT INTO platform.plans (plan_id, name, features, quotas) VALUES
    ('basic',        'Basic',        '["knowledge_search"]',                  '{"runs_per_day": 20}'),
    ('professional', 'Professional', '["knowledge_search"]',                  '{"runs_per_day": 200}'),
    ('enterprise',   'Enterprise',   '["knowledge_search", "audit_export"]',  '{"runs_per_day": 2000}')
ON CONFLICT (plan_id) DO UPDATE
    SET name = EXCLUDED.name,
        features = EXCLUDED.features,
        quotas = EXCLUDED.quotas;


-- ---------------------------------------------------------------------------
-- The role catalogue.
--
-- Same reason as the plans above: `memberships.role_keys` is resolved against
-- this table on every request, so an empty catalogue means every membership
-- grants nothing and every authorization check quietly fails closed. It is the
-- schema working, not demo data.
--
-- Platform scopes only. A bounded context adds its own roles - or its own
-- scopes to these - in the migration that creates it; what ships here is what
-- the platform itself can authorize, and nothing about anybody's business.
--
-- The ladder is deliberate and each rung is a superset of the one below, so
-- "this role can do at least what that one can" is a property the catalogue
-- has rather than a comment somebody has to keep true.
-- ---------------------------------------------------------------------------

INSERT INTO platform.roles (key, name, scopes) VALUES
    ('member', 'Member', '[
        "approvals.read", "directory.read", "integrations.read",
        "knowledge.read", "knowledge.write", "memory.read", "runs.read"
     ]'),
    ('approver', 'Approver', '[
        "approvals.read", "directory.read", "integrations.read",
        "knowledge.read", "knowledge.write", "memory.read", "runs.read",
        "approvals.pending", "approvals.decide"
     ]'),
    ('manager', 'Manager', '[
        "approvals.read", "directory.read", "integrations.read",
        "knowledge.read", "knowledge.write", "memory.read", "runs.read",
        "approvals.pending", "approvals.decide"
     ]'),
    ('director', 'Director', '[
        "approvals.read", "directory.read", "integrations.read",
        "knowledge.read", "knowledge.write", "memory.read", "runs.read",
        "approvals.pending", "approvals.decide", "audit.events"
     ]'),
    -- Read-only on purpose: someone who reviews outcomes without acting on
    -- them, which is a different authority from a manager, not a lesser one.
    ('executive', 'Executive', '[
        "approvals.read", "directory.read", "integrations.read",
        "knowledge.read", "memory.read", "runs.read", "audit.events"
     ]'),
    ('org_admin', 'Organisation admin', '[
        "directory.read", "feedback.inbox",
        "platform.members.read", "platform.members.write",
        "platform.workspaces.write", "platform.roles.read",
        "platform.tenant.settings.write", "platform.usage.read"
     ]'),
    -- One scope, and it is the one the authorization service expands into
    -- everything. Kept separate from org_admin so tenant administration and
    -- platform administration are different grants.
    ('platform_admin', 'Platform admin', '["platform.admin"]')
ON CONFLICT (key) DO UPDATE
    SET name = EXCLUDED.name, scopes = EXCLUDED.scopes;

-- ---------------------------------------------------------------------------
-- Permission sets: a named bundle of extra scopes attached to one membership,
-- for the case a role does not fit - authority to approve without being made a
-- manager, which is what the seed demonstrates.
-- ---------------------------------------------------------------------------

INSERT INTO platform.permission_sets (key, name, scopes) VALUES
    ('approver_boost', 'Approval authority', '["approvals.decide", "approvals.pending"]')
ON CONFLICT (key) DO UPDATE
    SET name = EXCLUDED.name, scopes = EXCLUDED.scopes;
