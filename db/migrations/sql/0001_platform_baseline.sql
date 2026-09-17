CREATE SCHEMA knowledge;


CREATE SCHEMA memory;


CREATE SCHEMA platform;




CREATE TABLE knowledge.chunks (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_id uuid NOT NULL,
    seq integer NOT NULL,
    content text NOT NULL,
    start_offset integer NOT NULL,
    end_offset integer NOT NULL,
    provenance_hash text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    deleted_at timestamp with time zone
);


ALTER TABLE ONLY knowledge.chunks FORCE ROW LEVEL SECURITY;


CREATE TABLE knowledge.documents (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    title text NOT NULL,
    domain text DEFAULT 'shared'::text NOT NULL,
    source_uri text NOT NULL,
    classification text DEFAULT 'internal'::text NOT NULL,
    source_version text DEFAULT '1'::text NOT NULL,
    index_version text,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    doc_key uuid,
    status text DEFAULT 'active'::text NOT NULL,
    is_current boolean DEFAULT true NOT NULL,
    effective_from timestamp with time zone,
    effective_to timestamp with time zone,
    superseded_by uuid,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    scope text DEFAULT 'tenant'::text NOT NULL,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    identity_key text,
    acl_principals text[] DEFAULT '{tenant:*}'::text[] NOT NULL
);


ALTER TABLE ONLY knowledge.documents FORCE ROW LEVEL SECURITY;


CREATE TABLE knowledge.ingest_jobs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    created_by uuid NOT NULL,
    title text NOT NULL,
    domain text DEFAULT 'shared'::text NOT NULL,
    classification text DEFAULT 'internal'::text NOT NULL,
    source_version text DEFAULT '1'::text NOT NULL,
    scope text DEFAULT 'tenant'::text NOT NULL,
    filename text NOT NULL,
    content_type text NOT NULL,
    storage_key text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    error text,
    document_id uuid,
    chunk_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    identity_key text,
    acl_principals text[] DEFAULT '{tenant:*}'::text[] NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_until timestamp with time zone,
    warnings text[] DEFAULT '{}'::text[] NOT NULL
);


ALTER TABLE ONLY knowledge.ingest_jobs FORCE ROW LEVEL SECURITY;


COMMENT ON COLUMN knowledge.ingest_jobs.warnings IS 'What went wrong with a file that was still indexed. Empty is the normal case.';


CREATE TABLE memory.items (
    memory_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    worker_id text NOT NULL,
    memory_type text NOT NULL,
    subject_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    content text NOT NULL,
    structured_facts jsonb DEFAULT '{}'::jsonb NOT NULL,
    provenance_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    confidence double precision NOT NULL,
    classification text DEFAULT 'internal'::text NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_until timestamp with time zone,
    retention_policy text DEFAULT 'default'::text NOT NULL,
    memory_schema_version text NOT NULL,
    created_by_run_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ONLY memory.items FORCE ROW LEVEL SECURITY;


CREATE TABLE memory.write_candidates (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    worker_id text NOT NULL,
    memory_type text NOT NULL,
    content text NOT NULL,
    structured_facts jsonb DEFAULT '{}'::jsonb NOT NULL,
    provenance_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    confidence double precision NOT NULL,
    classification text DEFAULT 'internal'::text NOT NULL,
    decision text NOT NULL,
    memory_id uuid,
    created_by_run_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ONLY memory.write_candidates FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.agent_store (
    tenant_id uuid NOT NULL,
    namespace text[] NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ONLY platform.agent_store FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.approval_decisions (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    decided_by uuid NOT NULL,
    outcome text NOT NULL,
    comment text DEFAULT ''::text NOT NULL,
    decided_at timestamp with time zone NOT NULL
);


ALTER TABLE ONLY platform.approval_decisions FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.approval_requests (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    approval_type text NOT NULL,
    requested_by uuid NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    run_id uuid,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL
);


ALTER TABLE ONLY platform.approval_requests FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.audit_events (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    run_id uuid,
    policy_decision text,
    trace_id text,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone NOT NULL
)
PARTITION BY RANGE (occurred_at);


ALTER TABLE ONLY platform.audit_events FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.entitlements (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    plan_id text NOT NULL,
    feature_overrides jsonb DEFAULT '[]'::jsonb NOT NULL
);


ALTER TABLE ONLY platform.entitlements FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.external_identities (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    issuer text NOT NULL,
    subject text NOT NULL,
    provider text DEFAULT 'oidc'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE platform.feedback (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    author_id uuid NOT NULL,
    category text NOT NULL,
    message text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    module text,
    page_path text,
    suggestion text
);


ALTER TABLE ONLY platform.feedback FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.feedback_attachments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    feedback_id uuid NOT NULL,
    object_key text NOT NULL,
    content_type text NOT NULL,
    size_bytes integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ONLY platform.feedback_attachments FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.memberships (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_keys jsonb DEFAULT '[]'::jsonb NOT NULL,
    clearance text DEFAULT 'internal'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    department text DEFAULT 'general'::text NOT NULL,
    manager_user_id uuid,
    permission_set_keys jsonb DEFAULT '[]'::jsonb NOT NULL
);


ALTER TABLE ONLY platform.memberships FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.model_usage_ledger (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    worker_id character varying(64),
    task character varying(128),
    prompt_id character varying(128),
    prompt_version character varying(16),
    provider character varying(32),
    model character varying(64),
    input_tokens bigint,
    output_tokens bigint,
    cost_usd numeric(12,6),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_model_usage_ledger_cost CHECK (((cost_usd IS NULL) OR (cost_usd >= (0)::numeric))),
    CONSTRAINT ck_model_usage_ledger_output_tokens CHECK (((output_tokens IS NULL) OR (output_tokens >= 0))),
    CONSTRAINT ck_model_usage_ledger_tokens CHECK (((input_tokens IS NULL) OR (input_tokens >= 0)))
)
PARTITION BY RANGE (created_at);


ALTER TABLE ONLY platform.model_usage_ledger FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.outbox_events (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    event_type text NOT NULL,
    schema_version text NOT NULL,
    aggregate_id uuid NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    correlation_id uuid,
    causation_id uuid,
    actor_id uuid,
    occurred_at timestamp with time zone NOT NULL,
    processed_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text
);


ALTER TABLE ONLY platform.outbox_events FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.permission_sets (
    key text NOT NULL,
    name text NOT NULL,
    scopes jsonb DEFAULT '[]'::jsonb NOT NULL
);


CREATE TABLE platform.plans (
    plan_id text NOT NULL,
    name text NOT NULL,
    features jsonb DEFAULT '[]'::jsonb NOT NULL,
    quotas jsonb DEFAULT '{}'::jsonb NOT NULL
);


CREATE TABLE platform.platform_operators (
    user_id uuid NOT NULL,
    note text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE platform.provisioning_audit (
    id uuid NOT NULL,
    actor_id uuid NOT NULL,
    action text NOT NULL,
    target_type text NOT NULL,
    target_id text,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE platform.roles (
    key text NOT NULL,
    name text NOT NULL,
    scopes jsonb DEFAULT '[]'::jsonb NOT NULL
);


CREATE TABLE platform.run_checkpoint_writes (
    thread_id uuid NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    task_id text NOT NULL,
    idx integer NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    channel text NOT NULL,
    type text NOT NULL,
    value bytea NOT NULL,
    task_path text DEFAULT ''::text NOT NULL
);


ALTER TABLE ONLY platform.run_checkpoint_writes FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.run_checkpoints (
    thread_id uuid NOT NULL,
    checkpoint_ns text DEFAULT ''::text NOT NULL,
    checkpoint_id text NOT NULL,
    parent_checkpoint_id text,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    type text NOT NULL,
    checkpoint bytea NOT NULL,
    metadata bytea NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE ONLY platform.run_checkpoints FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.tenants (
    id uuid NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    timezone text,
    locale text,
    record_visibility text DEFAULT 'open'::text NOT NULL
);


ALTER TABLE ONLY platform.tenants FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.tool_executions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid,
    tool_name text NOT NULL,
    tool_version text NOT NULL,
    status text NOT NULL,
    idempotency_key text,
    input_hash text NOT NULL,
    output_hash text,
    output jsonb,
    error text,
    attempts integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone
);


ALTER TABLE ONLY platform.tool_executions FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.users (
    id uuid NOT NULL,
    subject text NOT NULL,
    email text,
    display_name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


CREATE TABLE platform.worker_runs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    worker_id text NOT NULL,
    worker_version text NOT NULL,
    graph_version text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    result jsonb,
    error jsonb,
    approval_request_id uuid,
    release_manifest_ref text,
    requested_by uuid NOT NULL,
    trace_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    thread_id uuid NOT NULL,
    actor_roles text[] DEFAULT '{}'::text[] NOT NULL,
    actor_scopes text[] DEFAULT '{}'::text[] NOT NULL,
    actor_plan_id text DEFAULT ''::text NOT NULL,
    actor_clearance text DEFAULT 'internal'::text NOT NULL,
    subject_ref text,
    actor_record_visibility text DEFAULT 'open'::text NOT NULL,
    actor_visible_owners uuid[]
);


ALTER TABLE ONLY platform.worker_runs FORCE ROW LEVEL SECURITY;


CREATE TABLE platform.workspaces (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    archived_at timestamp with time zone
);


ALTER TABLE ONLY platform.workspaces FORCE ROW LEVEL SECURITY;


ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


ALTER TABLE ONLY knowledge.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


ALTER TABLE ONLY knowledge.ingest_jobs
    ADD CONSTRAINT ingest_jobs_pkey PRIMARY KEY (id);


ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT uq_chunks_document_seq UNIQUE (document_id, seq);


ALTER TABLE ONLY memory.items
    ADD CONSTRAINT items_pkey PRIMARY KEY (memory_id);


ALTER TABLE ONLY memory.write_candidates
    ADD CONSTRAINT write_candidates_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.agent_store
    ADD CONSTRAINT agent_store_pkey PRIMARY KEY (tenant_id, namespace, key);


ALTER TABLE ONLY platform.approval_decisions
    ADD CONSTRAINT approval_decisions_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id, occurred_at);


ALTER TABLE ONLY platform.entitlements
    ADD CONSTRAINT entitlements_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.entitlements
    ADD CONSTRAINT entitlements_tenant_id_key UNIQUE (tenant_id);


ALTER TABLE ONLY platform.external_identities
    ADD CONSTRAINT external_identities_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.feedback_attachments
    ADD CONSTRAINT feedback_attachments_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.feedback
    ADD CONSTRAINT feedback_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.model_usage_ledger
    ADD CONSTRAINT pk_model_usage_ledger PRIMARY KEY (id, created_at);


ALTER TABLE ONLY platform.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.permission_sets
    ADD CONSTRAINT permission_sets_pkey PRIMARY KEY (key);


ALTER TABLE ONLY platform.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (plan_id);


ALTER TABLE ONLY platform.platform_operators
    ADD CONSTRAINT platform_operators_pkey PRIMARY KEY (user_id);


ALTER TABLE ONLY platform.provisioning_audit
    ADD CONSTRAINT provisioning_audit_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (key);


ALTER TABLE ONLY platform.run_checkpoint_writes
    ADD CONSTRAINT run_checkpoint_writes_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx);


ALTER TABLE ONLY platform.run_checkpoints
    ADD CONSTRAINT run_checkpoints_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id);


ALTER TABLE ONLY platform.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


ALTER TABLE ONLY platform.tool_executions
    ADD CONSTRAINT tool_executions_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.external_identities
    ADD CONSTRAINT uq_external_identities_issuer_subject UNIQUE (issuer, subject);


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT uq_memberships_scope_user UNIQUE (tenant_id, workspace_id, user_id);


ALTER TABLE ONLY platform.workspaces
    ADD CONSTRAINT uq_workspaces_tenant_slug UNIQUE (tenant_id, slug);


ALTER TABLE ONLY platform.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


ALTER TABLE ONLY platform.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.users
    ADD CONSTRAINT users_subject_key UNIQUE (subject);


ALTER TABLE ONLY platform.worker_runs
    ADD CONSTRAINT worker_runs_pkey PRIMARY KEY (id);


ALTER TABLE ONLY platform.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


CREATE INDEX ix_chunks_document_status ON knowledge.chunks USING btree (document_id, status);


CREATE INDEX ix_documents_doc_key_current ON knowledge.documents USING btree (doc_key, is_current);


CREATE INDEX ix_documents_scope ON knowledge.documents USING btree (scope, status);


CREATE INDEX ix_documents_status ON knowledge.documents USING btree (tenant_id, status);


CREATE INDEX ix_ingest_jobs_claimable ON knowledge.ingest_jobs USING btree (status, available_at) WHERE (status = ANY (ARRAY['queued'::text, 'processing'::text]));


CREATE INDEX ix_ingest_jobs_status ON knowledge.ingest_jobs USING btree (status, created_at);


CREATE INDEX ix_approval_requests_tenant_status ON platform.approval_requests USING btree (tenant_id, status);


CREATE INDEX ix_audit_events_tenant_time ON platform.audit_events USING btree (tenant_id, occurred_at);


CREATE INDEX ix_external_identities_user ON platform.external_identities USING btree (user_id);


CREATE INDEX ix_feedback_attachments_feedback ON platform.feedback_attachments USING btree (feedback_id);


CREATE INDEX ix_feedback_tenant_created ON platform.feedback USING btree (tenant_id, created_at);


CREATE INDEX ix_memberships_manager ON platform.memberships USING btree (tenant_id, manager_user_id);


CREATE INDEX ix_memberships_tenant_user ON platform.memberships USING btree (tenant_id, user_id);


CREATE INDEX ix_model_usage_ledger_created_brin ON ONLY platform.model_usage_ledger USING brin (created_at);


CREATE INDEX ix_model_usage_ledger_run ON ONLY platform.model_usage_ledger USING btree (run_id);


CREATE INDEX ix_model_usage_ledger_tenant_created ON ONLY platform.model_usage_ledger USING btree (tenant_id, created_at);


CREATE INDEX ix_outbox_events_unprocessed ON platform.outbox_events USING btree (occurred_at) WHERE (processed_at IS NULL);


CREATE INDEX ix_provisioning_audit_occurred ON platform.provisioning_audit USING btree (occurred_at);


CREATE INDEX ix_worker_runs_active_by_subject ON platform.worker_runs USING btree (tenant_id, worker_id, subject_ref) WHERE (status = ANY (ARRAY['pending'::text, 'running'::text, 'waiting_approval'::text]));


CREATE INDEX ix_worker_runs_tenant_status ON platform.worker_runs USING btree (tenant_id, status);


CREATE INDEX ix_worker_runs_thread ON platform.worker_runs USING btree (tenant_id, thread_id);


CREATE UNIQUE INDEX uq_tool_executions_idempotency ON platform.tool_executions USING btree (tenant_id, tool_name, idempotency_key) WHERE ((idempotency_key IS NOT NULL) AND (status = 'succeeded'::text));


CREATE UNIQUE INDEX uq_worker_runs_active_thread ON platform.worker_runs USING btree (tenant_id, thread_id) WHERE (status <> ALL (ARRAY['completed'::text, 'failed'::text, 'cancelled'::text]));


ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES knowledge.documents(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.approval_decisions
    ADD CONSTRAINT approval_decisions_request_id_fkey FOREIGN KEY (request_id) REFERENCES platform.approval_requests(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.entitlements
    ADD CONSTRAINT entitlements_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES platform.plans(plan_id) ON DELETE RESTRICT;


ALTER TABLE ONLY platform.entitlements
    ADD CONSTRAINT entitlements_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES platform.tenants(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.external_identities
    ADD CONSTRAINT external_identities_user_id_fkey FOREIGN KEY (user_id) REFERENCES platform.users(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.feedback_attachments
    ADD CONSTRAINT feedback_attachments_feedback_id_fkey FOREIGN KEY (feedback_id) REFERENCES platform.feedback(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT memberships_manager_user_id_fkey FOREIGN KEY (manager_user_id) REFERENCES platform.users(id) ON DELETE SET NULL;


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT memberships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES platform.tenants(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES platform.users(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.memberships
    ADD CONSTRAINT memberships_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES platform.workspaces(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.platform_operators
    ADD CONSTRAINT platform_operators_user_id_fkey FOREIGN KEY (user_id) REFERENCES platform.users(id) ON DELETE CASCADE;


ALTER TABLE ONLY platform.workspaces
    ADD CONSTRAINT workspaces_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES platform.tenants(id) ON DELETE RESTRICT;


ALTER TABLE knowledge.chunks ENABLE ROW LEVEL SECURITY;


ALTER TABLE knowledge.documents ENABLE ROW LEVEL SECURITY;


ALTER TABLE knowledge.ingest_jobs ENABLE ROW LEVEL SECURITY;


CREATE FUNCTION platform.user_has_any_membership(uid uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    AS $$
            SELECT EXISTS (SELECT 1 FROM platform.memberships WHERE user_id = uid);
        $$;

CREATE POLICY knowledge_global_read_documents ON knowledge.documents FOR SELECT USING ((scope = 'global'::text));


CREATE POLICY tenant_isolation_chunks ON knowledge.chunks USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_documents ON knowledge.documents USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_ingest_jobs ON knowledge.ingest_jobs USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY worker_drain_ingest_jobs ON knowledge.ingest_jobs USING ((current_setting('app.worker_drain'::text, true) = 'on'::text)) WITH CHECK ((current_setting('app.worker_drain'::text, true) = 'on'::text));


ALTER TABLE memory.items ENABLE ROW LEVEL SECURITY;


CREATE POLICY tenant_isolation_items ON memory.items USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_write_candidates ON memory.write_candidates USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


ALTER TABLE memory.write_candidates ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.agent_store ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.approval_decisions ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.approval_requests ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.audit_events ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.entitlements ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.feedback ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.feedback_attachments ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.memberships ENABLE ROW LEVEL SECURITY;


CREATE POLICY memberships_self_select ON platform.memberships FOR SELECT USING ((user_id = (NULLIF(current_setting('app.principal_id'::text, true), ''::text))::uuid));


ALTER TABLE platform.model_usage_ledger ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.outbox_events ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.run_checkpoint_writes ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.run_checkpoints ENABLE ROW LEVEL SECURITY;


CREATE POLICY tenant_isolation_agent_store ON platform.agent_store USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_approval_decisions ON platform.approval_decisions USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_approval_requests ON platform.approval_requests USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_audit_events ON platform.audit_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_entitlements ON platform.entitlements USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_feedback ON platform.feedback USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_feedback_attachments ON platform.feedback_attachments USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_memberships ON platform.memberships USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_model_usage_ledger ON platform.model_usage_ledger USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_outbox_events ON platform.outbox_events USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_run_checkpoint_writes ON platform.run_checkpoint_writes USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_run_checkpoints ON platform.run_checkpoints USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_tenants ON platform.tenants USING ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_tool_executions ON platform.tool_executions USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_worker_runs ON platform.worker_runs USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


CREATE POLICY tenant_isolation_workspaces ON platform.workspaces USING ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid));


ALTER TABLE platform.tenants ENABLE ROW LEVEL SECURITY;


CREATE POLICY tenants_self_select ON platform.tenants FOR SELECT USING ((id IN ( SELECT m.tenant_id
   FROM platform.memberships m
  WHERE (m.user_id = (NULLIF(current_setting('app.principal_id'::text, true), ''::text))::uuid))));


ALTER TABLE platform.tool_executions ENABLE ROW LEVEL SECURITY;


CREATE POLICY worker_drain_outbox_events ON platform.outbox_events USING ((current_setting('app.worker_drain'::text, true) = 'on'::text)) WITH CHECK ((current_setting('app.worker_drain'::text, true) = 'on'::text));


ALTER TABLE platform.worker_runs ENABLE ROW LEVEL SECURITY;


ALTER TABLE platform.workspaces ENABLE ROW LEVEL SECURITY;


CREATE POLICY workspaces_self_select ON platform.workspaces FOR SELECT USING ((id IN ( SELECT m.workspace_id
   FROM platform.memberships m
  WHERE (m.user_id = (NULLIF(current_setting('app.principal_id'::text, true), ''::text))::uuid))));

-- ---------------------------------------------------------------------------
-- Every foreign key gets an index on its own side.
--
-- Postgres indexes the referenced side automatically and the referencing side
-- never. Without one, deleting a parent row sequentially scans the child table
-- while holding a lock on it - invisible at demo size, a stall at real size.
-- ---------------------------------------------------------------------------
CREATE INDEX ix_approval_decisions_request ON platform.approval_decisions (request_id);
CREATE INDEX ix_entitlements_plan ON platform.entitlements (plan_id);
CREATE INDEX ix_memberships_user ON platform.memberships (user_id);
CREATE INDEX ix_memberships_workspace ON platform.memberships (workspace_id);
-- `ix_memberships_manager` already exists on (tenant_id, manager_user_id); its
-- leading column is the tenant, so it cannot serve a lookup by manager alone,
-- which is what the foreign key needs.
CREATE INDEX ix_memberships_manager_fk ON platform.memberships (manager_user_id)
    WHERE manager_user_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- updated_at is maintained by the database, not by whoever remembered.
--
-- Three tables carry the column and nothing enforced it, so a value written by
-- anything other than the one code path that set it - a migration, a support
-- fix, a second writer - left a stale timestamp behind. A trigger cannot be
-- forgotten.
-- ---------------------------------------------------------------------------
CREATE FUNCTION platform.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON platform.agent_store
    FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON platform.worker_runs
    FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON knowledge.ingest_jobs
    FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Default partitions.
--
-- Both partitioned tables get one, so a row can never be rejected for landing
-- outside every declared range. Real monthly partitions are created ahead of
-- time by an operator or a scheduled job; rows that miss them are still stored
-- here rather than lost, and can be moved later.
-- ---------------------------------------------------------------------------
CREATE TABLE platform.audit_events_default PARTITION OF platform.audit_events DEFAULT;
CREATE TABLE platform.model_usage_ledger_default
    PARTITION OF platform.model_usage_ledger DEFAULT;
