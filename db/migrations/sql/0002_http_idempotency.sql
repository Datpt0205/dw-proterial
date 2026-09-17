-- ---------------------------------------------------------------------------
-- HTTP idempotency keys.
--
-- `Idempotency-Key` has been in the API's CORS allow-list since the first
-- release and nothing enforced it: a client whose POST timed out had no way to
-- retry without risking a second decision, a second membership, a second
-- charge. This table is the enforcement, and it is a published contract, so it
-- arrives before clients integrate rather than after.
--
-- One row per (tenant, key). The primary key IS the concurrency control: two
-- requests presenting the same key race to INSERT this row and exactly one of
-- them wins, which is cheaper and harder to get wrong than an advisory lock
-- (no lock to leak, no connection held for the length of a handler).
--
-- The key is scoped to the tenant, not to the workspace or the user, so two
-- tenants that both send `Idempotency-Key: 1` never collide. `workspace_id` is
-- recorded and compared as part of the fingerprint rather than keyed on, so
-- reusing one key across two workspaces is refused as a conflict instead of
-- replaying one workspace's response into another.
-- ---------------------------------------------------------------------------

CREATE TABLE platform.idempotency_keys (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    workspace_id uuid NOT NULL,
    -- The fingerprint: what request this key was first spent on. A later
    -- request presenting the same key with a different method, path, workspace
    -- or body is a client bug, and answering it with the stored response would
    -- hide the bug behind a plausible reply.
    request_method text NOT NULL,
    request_path text NOT NULL,
    body_hash text NOT NULL,
    -- NULL until the handler returns. A row with a NULL status is a reservation
    -- held by a request that is still in flight.
    response_status integer,
    response_body jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT pk_idempotency_keys PRIMARY KEY (tenant_id, idempotency_key),
    CONSTRAINT fk_idempotency_keys_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES platform.tenants(id) ON DELETE CASCADE,
    -- Both halves of the completion are written together or not at all, so a
    -- reader never has to guess what a status without a body means.
    CONSTRAINT ck_idempotency_keys_completed CHECK (
        (completed_at IS NULL AND response_status IS NULL)
        OR (completed_at IS NOT NULL AND response_status IS NOT NULL)
    )
);


COMMENT ON TABLE platform.idempotency_keys IS
    'Replay cache for mutating HTTP requests that carry an Idempotency-Key header.';


-- Not "when the key was first seen": when the reservation currently in force
-- began. Taking over a reservation abandoned by a dead process re-stamps this,
-- which is what stops a second takeover from firing immediately afterwards.
COMMENT ON COLUMN platform.idempotency_keys.created_at IS
    'When the reservation in force began. Reset when an abandoned one is taken over.';


-- The foreign key needs an index on its own side, and it already has one: the
-- primary key is (tenant_id, idempotency_key) and `tenant_id` leads it, so a
-- tenant delete can find the child rows without scanning. A second index on
-- tenant_id alone would be dead weight on every insert.

-- Retention. Rows here are a replay cache with a finite useful life, not a
-- record anyone audits — the audit trail is `platform.audit_events`. A sweep
-- deletes by age, and this is the index it reads.
CREATE INDEX ix_idempotency_keys_created_at ON platform.idempotency_keys (created_at);


ALTER TABLE platform.idempotency_keys ENABLE ROW LEVEL SECURITY;


ALTER TABLE ONLY platform.idempotency_keys FORCE ROW LEVEL SECURITY;


CREATE POLICY tenant_isolation_idempotency_keys ON platform.idempotency_keys USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


-- No GRANT here on purpose. Migration 0001 ran, as this one does, as
-- `dw_migrator`, and left `ALTER DEFAULT PRIVILEGES IN SCHEMA platform ... TO
-- dw_app` behind — so every table that role creates afterwards is already
-- readable and writable by the application. `test_privileges.py` proves the
-- mechanism in general and `test_http_idempotency.py` proves it for this table
-- in particular. A GRANT written here would be redundant, and would quietly
-- imply the default privileges cannot be relied on.
