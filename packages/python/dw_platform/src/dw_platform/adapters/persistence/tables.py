"""SQLAlchemy Core table definitions for the platform schema.

Imperative (non-ORM) mapping keeps the domain free of SQLAlchemy; repositories
translate rows <-> domain objects explicitly. Mirrors the Alembic migration —
change both together.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from dw_kernel.naming import NAMING_CONVENTION

metadata = sa.MetaData(schema="platform", naming_convention=NAMING_CONVENTION)

tenants = sa.Table(
    "tenants",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("slug", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("record_visibility", sa.Text, nullable=False, server_default="open"),
    sa.Column("timezone", sa.Text, nullable=True),
    sa.Column("locale", sa.Text, nullable=True),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
)

workspaces = sa.Table(
    "workspaces",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
    sa.Column("slug", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_slug"),
)

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("subject", sa.Text, nullable=False, unique=True),
    sa.Column("email", sa.Text, nullable=True, unique=True),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
)

roles = sa.Table(
    "roles",
    metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
)

# Additive scope bundles (ADR-001 Phase 3): a versioned catalog, like roles, that
# an admin attaches to a membership on top of its role. Global config, no RLS.
permission_sets = sa.Table(
    "permission_sets",
    metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
)

# Maps a verified (issuer, subject) — e.g. a Keycloak sub or a dev token subject —
# to a platform user. Identity plane (like users): not tenant-scoped, no RLS.
# One platform user may have several external identities (dev + Keycloak).
external_identities = sa.Table(
    "external_identities",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("issuer", sa.Text, nullable=False),
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("provider", sa.Text, nullable=False, server_default="oidc"),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("issuer", "subject", name="uq_external_identities_issuer_subject"),
)

plans = sa.Table(
    "plans",
    metadata,
    sa.Column("plan_id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("features", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("quotas", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
)

memberships = sa.Table(
    "memberships",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
    sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("role_keys", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("permission_set_keys", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("clearance", sa.Text, nullable=False, server_default="internal"),
    sa.Column("department", sa.Text, nullable=False, server_default="general"),
    sa.Column(
        "manager_user_id",
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.UniqueConstraint("tenant_id", "workspace_id", "user_id", name="uq_memberships_scope_user"),
)

entitlements = sa.Table(
    "entitlements",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, unique=True
    ),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id"), nullable=False),
    sa.Column("feature_overrides", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
)

approval_requests = sa.Table(
    "approval_requests",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("approval_type", sa.Text, nullable=False),
    sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
    sa.Column("reason", sa.Text, nullable=False, server_default=""),
    sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("run_id", UUID(as_uuid=True), nullable=True),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
    ),
    sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
)

approval_decisions = sa.Table(
    "approval_decisions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column(
        "request_id", UUID(as_uuid=True), sa.ForeignKey("approval_requests.id"), nullable=False
    ),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("decided_by", UUID(as_uuid=True), nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("comment", sa.Text, nullable=False, server_default=""),
    sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("resource_type", sa.Text, nullable=False),
    sa.Column("resource_id", sa.Text, nullable=False),
    sa.Column("run_id", UUID(as_uuid=True), nullable=True),
    sa.Column("policy_decision", sa.Text, nullable=True),
    sa.Column("trace_id", sa.Text, nullable=True),
    sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
)

feedback = sa.Table(
    "feedback",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("author_id", UUID(as_uuid=True), nullable=False),
    sa.Column("category", sa.Text, nullable=False),
    sa.Column("message", sa.Text, nullable=False),
    # Spec 003 US5: which part of the app, sent from which page, and what the
    # person would do about it. Nullable because rows predate the columns.
    sa.Column("module", sa.Text, nullable=True),
    sa.Column("page_path", sa.Text, nullable=True),
    sa.Column("suggestion", sa.Text, nullable=True),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

feedback_attachments = sa.Table(
    "feedback_attachments",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column(
        "feedback_id",
        UUID(as_uuid=True),
        sa.ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("object_key", sa.Text, nullable=False),
    sa.Column("content_type", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.Integer, nullable=False),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

outbox_events = sa.Table(
    "outbox_events",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("schema_version", sa.Text, nullable=False),
    sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("correlation_id", UUID(as_uuid=True), nullable=True),
    sa.Column("causation_id", UUID(as_uuid=True), nullable=True),
    sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
    sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_error", sa.Text, nullable=True),
)

# Replay cache for mutating HTTP requests that carry an `Idempotency-Key`
# header. The primary key is (tenant_id, idempotency_key), so the key string is
# the client's to choose within its own tenant and two tenants never collide —
# and inserting the row is itself the mutual exclusion between two concurrent
# requests presenting the same key.
idempotency_keys = sa.Table(
    "idempotency_keys",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
    sa.Column("idempotency_key", sa.Text, primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("request_method", sa.Text, nullable=False),
    sa.Column("request_path", sa.Text, nullable=False),
    sa.Column("body_hash", sa.Text, nullable=False),
    # Both NULL while the first request is in flight; both set when it returned.
    sa.Column("response_status", sa.Integer, nullable=True),
    sa.Column("response_body", JSONB, nullable=True),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
)

# Platform Operator allowlist: who may provision tenants (ADR-002). Global —
# no tenant_id, no RLS. Deliberately outside the tenant plane.
platform_operators = sa.Table(
    "platform_operators",
    metadata,
    sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("note", sa.Text, nullable=True),
    sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# Audit trail for provisioning actions. Global (a "create tenant" has no tenant
# to belong to yet), so it is separate from tenant-scoped audit_events.
provisioning_audit = sa.Table(
    "provisioning_audit",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("target_type", sa.Text, nullable=False),
    sa.Column("target_id", sa.Text, nullable=True),
    sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column(
        "occurred_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
)

# Tables whose rows belong to exactly one tenant → RLS enabled + forced.
TENANT_SCOPED_TABLES = (
    "workspaces",
    "memberships",
    "entitlements",
    "approval_requests",
    "approval_decisions",
    "audit_events",
    "outbox_events",
    "idempotency_keys",
)
