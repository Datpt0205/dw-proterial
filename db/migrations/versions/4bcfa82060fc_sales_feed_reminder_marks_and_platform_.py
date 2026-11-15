"""sales feed reminder marks and platform push subscriptions

Revision ID: 4bcfa82060fc
Revises: eac4fabdb31a
Create Date: 2026-11-15 14:01:06.448113+00:00

Sales tickets 47 and 48: one place for a person's work, with its reminders
marked by that person, and pushed to the phone they turned pushes on from.

- **`platform.push_subscriptions`**: a device a member turned Web Push on
  from, in one workspace (`dw_platform.application.web_push`). The endpoint
  is the browser's push service URL and a capability: UNIQUE across the
  whole table, because a device that signs in as someone else is that
  person's now.
  - **One door in**: `platform.save_push_subscription(endpoint, p256dh,
    auth)`, SECURITY DEFINER with a fixed `search_path`, reads the tenant,
    workspace and user from the bound session (never a parameter), refuses
    a caller who is not a member of that workspace, removes a row anyone
    held for the same endpoint, and inserts or renews the caller's.
    `dw_app` holds no INSERT or UPDATE, so there is no second way in.
  - **A person's own**: `tenant AND ((workspace AND user) OR scope)` to
    read, the offboarding lane's scope as the alternative;
    `tenant AND workspace AND user` to write. The worker's push reads the
    rows of the person it pushes to by binding that person, so a push
    meant for one person reads nobody else's devices.
  - `dw_app` SELECTs and DELETEs (a person turning pushes off; the lane
    removing one the push service says is gone). `updated_at` by
    `platform.touch_updated_at()`: the portal renews a subscription each
    time the app opens, and `platform.prune_push_subscriptions()` (no
    argument, so no caller can widen it) removes those not renewed for 90
    days, from the worker's `push_subscriptions_retention` lane.
- **`sales.reminder_marks`**: what a person did with a follow-up reminder in
  their feed: `done` ("Đã xử lý"), `dismissed` ("Không cần"), `snoozed`
  until a time ("Nhắc lại sau"). One row per notification and person, the
  newest mark winning. Every fixed set is CHECKed: the follow-up is
  `dw_sales.domain.followups.Followup` but the brief and "your turn" (those
  are not reminders the feed lists), the mark its three.
  - **The customer's term is a floor** (ticket 47, acceptance 1):
    `ck_reminder_marks_customer_term` refuses `dismissed` and `snoozed` on
    a reminder whose deadline is the customer's (`CUSTOMER_TERM`:
    `quote_deadline`, `implied_acceptance`), whatever writes it.
  - **Gone with its notification**: the foreign key to
    `platform.notifications` is `ON DELETE CASCADE`, so the inbox's 90-day
    prune takes the marks with it, and what the feed learns from (a
    person's dismissals) spans the same 90 days.
  - Same RLS shape as the subscriptions; `dw_app` SELECTs, INSERTs and
    UPDATEs `mark`, `until` and `marked_at`; DELETE is REVOKEd.
- Foreign keys declare `ON DELETE CASCADE` and are each indexed on their own
  side; the read indexes lead with what RLS supplies.
"""

from __future__ import annotations

from alembic import op

revision = "4bcfa82060fc"
down_revision = "eac4fabdb31a"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_USER = "(user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid)"
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_READ = f"({_TENANT} AND (({_WORKSPACE} AND {_USER}) OR {_WORKSPACE_SCOPE}))"
_WRITE = f"({_TENANT} AND {_WORKSPACE} AND {_USER})"

# `dw_sales.domain.followups.Followup` but `your_turn`, and the customer's
# terms among them (`CUSTOMER_TERM`); held to both by `test_today.py`.
_REMINDERS = (
    "'order_unconfirmed', 'quote_waiting_design', 'quote_deadline', 'waiting_customer',"
    " 'waiting_pc', 'implied_acceptance'"
)
_CUSTOMER_TERM = "'quote_deadline', 'implied_acceptance'"
_B64URL = "'^[A-Za-z0-9_-]+={0,2}$'"

_SUBSCRIPTIONS = f"""
    CREATE TABLE platform.push_subscriptions (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        user_id uuid NOT NULL,
        endpoint text NOT NULL,
        p256dh text NOT NULL,
        auth text NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_push_subscriptions PRIMARY KEY (id),
        CONSTRAINT uq_push_subscriptions_endpoint UNIQUE (endpoint),
        CONSTRAINT fk_push_subscriptions_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_push_subscriptions_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_push_subscriptions_user_id_users FOREIGN KEY (user_id)
            REFERENCES platform.users (id) ON DELETE CASCADE,
        CONSTRAINT ck_push_subscriptions_endpoint CHECK (
            char_length(endpoint) BETWEEN 12 AND 2048 AND endpoint LIKE 'https://%'
        ),
        CONSTRAINT ck_push_subscriptions_p256dh CHECK (
            char_length(p256dh) BETWEEN 80 AND 100 AND p256dh ~ {_B64URL}
        ),
        CONSTRAINT ck_push_subscriptions_auth CHECK (
            char_length(auth) BETWEEN 16 AND 32 AND auth ~ {_B64URL}
        )
    )
"""

_MARKS = f"""
    CREATE TABLE sales.reminder_marks (
        notification_id uuid NOT NULL,
        user_id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        followup text NOT NULL,
        mark text NOT NULL,
        until timestamp with time zone,
        marked_at timestamp with time zone NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_reminder_marks PRIMARY KEY (notification_id, user_id),
        CONSTRAINT fk_reminder_marks_notification_id_notifications FOREIGN KEY (notification_id)
            REFERENCES platform.notifications (id) ON DELETE CASCADE,
        CONSTRAINT fk_reminder_marks_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_reminder_marks_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_reminder_marks_user_id_users FOREIGN KEY (user_id)
            REFERENCES platform.users (id) ON DELETE CASCADE,
        CONSTRAINT ck_reminder_marks_followup CHECK (followup IN ({_REMINDERS})),
        CONSTRAINT ck_reminder_marks_mark CHECK (mark IN ('done', 'dismissed', 'snoozed')),
        CONSTRAINT ck_reminder_marks_until CHECK ((mark = 'snoozed') = (until IS NOT NULL)),
        CONSTRAINT ck_reminder_marks_customer_term CHECK (
            followup NOT IN ({_CUSTOMER_TERM}) OR mark = 'done'
        )
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE platform.push_subscriptions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.push_subscriptions FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_push_subscriptions ON platform.push_subscriptions"
    f" USING {_READ} WITH CHECK {_WRITE}",
    "ALTER TABLE sales.reminder_marks ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.reminder_marks FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_reminder_marks ON sales.reminder_marks"
    f" USING {_READ} WITH CHECK {_WRITE}",
)

_INDEXES: tuple[str, ...] = (
    # A person's devices in a workspace (the push, the person's own list).
    "CREATE INDEX ix_push_subscriptions_tenant_id_workspace_id_user_id"
    " ON platform.push_subscriptions (tenant_id, workspace_id, user_id)",
    "CREATE INDEX ix_push_subscriptions_workspace_id ON platform.push_subscriptions (workspace_id)",
    "CREATE INDEX ix_push_subscriptions_user_id ON platform.push_subscriptions (user_id)",
    # The prune's window.
    "CREATE INDEX ix_push_subscriptions_updated_at ON platform.push_subscriptions (updated_at)",
    # A person's marks, by follow-up (the feed's read and its dismissal
    # counts).
    "CREATE INDEX ix_reminder_marks_tenant_id_workspace_id_user_id_followup"
    " ON sales.reminder_marks (tenant_id, workspace_id, user_id, followup)",
    "CREATE INDEX ix_reminder_marks_notification_id ON sales.reminder_marks (notification_id)",
    "CREATE INDEX ix_reminder_marks_workspace_id ON sales.reminder_marks (workspace_id)",
    "CREATE INDEX ix_reminder_marks_user_id ON sales.reminder_marks (user_id)",
)

_TRIGGERS: tuple[str, ...] = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON platform.push_subscriptions"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()",
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.reminder_marks"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()",
)

_SAVE = """
CREATE FUNCTION platform.save_push_subscription(p_endpoint text, p_p256dh text, p_auth text)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, platform
AS $$
DECLARE
    v_tenant uuid := NULLIF(current_setting('app.tenant_id', true), '')::uuid;
    v_workspace uuid := NULLIF(current_setting('app.workspace_id', true), '')::uuid;
    v_user uuid := NULLIF(current_setting('app.user_id', true), '')::uuid;
BEGIN
    IF v_tenant IS NULL OR v_workspace IS NULL OR v_user IS NULL OR NOT EXISTS (
        SELECT 1 FROM platform.memberships m
        WHERE m.tenant_id = v_tenant AND m.workspace_id = v_workspace AND m.user_id = v_user
    ) THEN
        RAISE EXCEPTION 'a push subscription is a member''s own, in the bound workspace'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- The device moved on: whoever held this endpoint before holds it no more.
    DELETE FROM platform.push_subscriptions
    WHERE endpoint = p_endpoint
      AND (tenant_id, workspace_id, user_id) IS DISTINCT FROM (v_tenant, v_workspace, v_user);
    INSERT INTO platform.push_subscriptions (
        id, tenant_id, workspace_id, user_id, endpoint, p256dh, auth
    )
    VALUES (gen_random_uuid(), v_tenant, v_workspace, v_user, p_endpoint, p_p256dh, p_auth)
    ON CONFLICT ON CONSTRAINT uq_push_subscriptions_endpoint
        DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth;
END
$$
"""

_PRUNE = """
CREATE FUNCTION platform.prune_push_subscriptions()
RETURNS integer
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, platform
AS $$
    WITH gone AS (
        DELETE FROM platform.push_subscriptions
        WHERE updated_at < now() - interval '90 days'
        RETURNING 1
    )
    SELECT count(*)::integer FROM gone
$$
"""

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, DELETE ON platform.push_subscriptions TO dw_app;
            REVOKE INSERT, UPDATE, TRUNCATE ON platform.push_subscriptions FROM dw_app;
            GRANT EXECUTE ON FUNCTION platform.save_push_subscription(text, text, text) TO dw_app;
            GRANT EXECUTE ON FUNCTION platform.prune_push_subscriptions() TO dw_app;
            GRANT SELECT, INSERT ON sales.reminder_marks TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON sales.reminder_marks FROM dw_app;
            GRANT UPDATE (mark, until, marked_at) ON sales.reminder_marks TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_SUBSCRIPTIONS)
    op.execute(_MARKS)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    for statement in _TRIGGERS:
        op.execute(statement)
    op.execute(_SAVE)
    op.execute(_PRUNE)
    op.execute(
        "REVOKE ALL ON FUNCTION platform.save_push_subscription(text, text, text) FROM PUBLIC"
    )
    op.execute("REVOKE ALL ON FUNCTION platform.prune_push_subscriptions() FROM PUBLIC")
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP FUNCTION platform.prune_push_subscriptions()")
    op.execute("DROP FUNCTION platform.save_push_subscription(text, text, text)")
    op.execute("DROP TABLE sales.reminder_marks")
    op.execute("DROP TABLE platform.push_subscriptions")
