"""platform in-app notifications

Revision ID: 855ae928c3fa
Revises: 6b26771e549d
Create Date: 2026-09-28

A message to one person inside the app: "HĐ-2026-007 is waiting for your
approval", with a link to where the work is. Platform-owned because telling a
member something is not any one context's business: every context sends
through the same table.

- **Idempotent per recipient.** `(recipient_user_id, source_key)` is unique.
  A sender names the thing it is telling people about, so a worker that runs
  twice, or a retry, notifies nobody twice.
- **One person's inbox.** RLS narrows reads and updates to the caller's own
  tenant AND to rows addressed to `app.user_id`, which `tenant_session`
  binds from the verified access context. A colleague in the same
  workspace cannot read what was sent to someone else.
- **One door in.** dw_app cannot insert directly. It goes through
  `platform.deliver_notification(...)`, which delivers inside the bound
  tenant (read from `app.tenant_id`, never a parameter), to a workspace of
  that tenant, and only to its members. Others are skipped, not refused, so a
  member removed mid-sweep simply gets nothing. SECURITY DEFINER because
  Postgres applies SELECT policies to the rows of an INSERT ... ON CONFLICT,
  measured here: a sender addressing anyone but itself was refused.
- **Read is the only change.** dw_app may update `read_at` and nothing
  else, and may not delete. Old notifications go through
  `platform.prune_notifications()`, which removes what is older than 90
  days. It takes no argument, so no caller can widen it to recent rows.
- **A link stays inside the app.** `link` is an app-relative path. A CHECK
  refuses anything else (a scheme, `//host`), so a notification cannot carry
  `javascript:` or send someone to another site.
"""

from __future__ import annotations

from alembic import op

revision = "855ae928c3fa"
down_revision = "6b26771e549d"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_RECIPIENT = (
    "(recipient_user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid)"
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform.notifications (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            recipient_user_id uuid NOT NULL,
            source_key text NOT NULL,
            title text NOT NULL,
            body text DEFAULT '' NOT NULL,
            link text,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            read_at timestamp with time zone,
            CONSTRAINT pk_notifications PRIMARY KEY (id),
            CONSTRAINT fk_notifications_tenant_id_tenants FOREIGN KEY (tenant_id)
                REFERENCES platform.tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_notifications_workspace_id_workspaces FOREIGN KEY (workspace_id)
                REFERENCES platform.workspaces (id) ON DELETE CASCADE,
            CONSTRAINT fk_notifications_recipient_user_id_users FOREIGN KEY (recipient_user_id)
                REFERENCES platform.users (id) ON DELETE CASCADE,
            CONSTRAINT uq_notifications_recipient_user_id_source_key
                UNIQUE (recipient_user_id, source_key),
            CONSTRAINT ck_notifications_source_key CHECK (btrim(source_key) <> ''),
            CONSTRAINT ck_notifications_title CHECK (
                btrim(title) <> '' AND char_length(title) <= 200
            ),
            CONSTRAINT ck_notifications_body CHECK (char_length(body) <= 2000),
            CONSTRAINT ck_notifications_link CHECK (
                link IS NULL OR link ~ '^/([A-Za-z0-9_-][A-Za-z0-9/_.?=&-]*)?$'
            )
        )
        """
    )
    # The inbox is read newest first, per person, and RLS supplies the tenant.
    op.execute(
        "CREATE INDEX ix_notifications_tenant_id_recipient_created_at"
        " ON platform.notifications (tenant_id, recipient_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_notifications_workspace_id ON platform.notifications (workspace_id)"
    )
    op.execute("CREATE INDEX ix_notifications_created_at ON platform.notifications (created_at)")
    op.execute("ALTER TABLE platform.notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE platform.notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_notifications_select ON platform.notifications"
        f" FOR SELECT USING ({_TENANT} AND {_RECIPIENT})"
    )
    op.execute(
        "CREATE POLICY tenant_isolation_notifications_update ON platform.notifications"
        f" FOR UPDATE USING ({_TENANT} AND {_RECIPIENT})"
        f" WITH CHECK ({_TENANT} AND {_RECIPIENT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON platform.notifications FROM dw_app;
                GRANT UPDATE (read_at) ON platform.notifications TO dw_app;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION platform.deliver_notification(
            p_workspace_id uuid,
            p_recipients uuid[],
            p_source_key text,
            p_title text,
            p_body text,
            p_link text
        )
        RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
        DECLARE
            v_tenant uuid := NULLIF(current_setting('app.tenant_id', true), '')::uuid;
            v_delivered integer;
        BEGIN
            IF v_tenant IS NULL OR NOT EXISTS (
                SELECT 1 FROM platform.workspaces
                WHERE id = p_workspace_id AND tenant_id = v_tenant
            ) THEN
                RAISE EXCEPTION 'notifications are delivered inside the bound tenant'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            INSERT INTO platform.notifications (
                id, tenant_id, workspace_id, recipient_user_id, source_key, title, body, link
            )
            SELECT gen_random_uuid(), v_tenant, p_workspace_id, r.user_id, p_source_key,
                   p_title, p_body, p_link
            FROM (SELECT DISTINCT unnest(p_recipients) AS user_id) r
            WHERE EXISTS (
                SELECT 1 FROM platform.memberships m
                WHERE m.tenant_id = v_tenant
                  AND m.workspace_id = p_workspace_id
                  AND m.user_id = r.user_id
            )
            ON CONFLICT ON CONSTRAINT uq_notifications_recipient_user_id_source_key DO NOTHING;
            GET DIAGNOSTICS v_delivered = ROW_COUNT;
            RETURN v_delivered;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION platform.deliver_notification(uuid, uuid[], text, text, text, text)"
        " FROM PUBLIC"
    )
    op.execute(
        """
        CREATE FUNCTION platform.prune_notifications()
        RETURNS integer
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, platform
        AS $$
            WITH gone AS (
                DELETE FROM platform.notifications
                WHERE created_at < now() - interval '90 days'
                RETURNING 1
            )
            SELECT count(*)::integer FROM gone
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION platform.prune_notifications() FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                GRANT EXECUTE ON FUNCTION platform.prune_notifications() TO dw_app;
                GRANT EXECUTE ON FUNCTION platform.deliver_notification(
                    uuid, uuid[], text, text, text, text
                ) TO dw_app;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION platform.deliver_notification(uuid, uuid[], text, text, text, text)")
    op.execute("DROP FUNCTION platform.prune_notifications()")
    op.execute("DROP TABLE platform.notifications")
