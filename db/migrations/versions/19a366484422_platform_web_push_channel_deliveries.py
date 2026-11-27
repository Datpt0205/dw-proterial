"""platform web push channel deliveries

Revision ID: 19a366484422
Revises: fe1e1ddf1ea6
Create Date: 2026-11-26 11:29:42.329194+00:00

A notification reaches a person's phone wherever they turned push on, not
only from Sales' follow-ups (Sales ticket 78). The outbox that already carries
a notification out through a linked chat (`platform.channel_deliveries`,
5a25154e0296, ADR 0006) gains a second channel, `web_push`:

- **One door in, as before.** `platform.deliver_notification` queues, in the
  statement that addresses the notification, one `web_push` delivery for each
  recipient the notification was actually inserted for (a repeated
  `source_key` queues nothing) who holds a push subscription in that
  workspace. The subscription is the opt-in, as the chat link is.
- **`p_push`**, default true: a sender that pushes on its own may say no.
  Sales' follow-up lane does (its pushes are batched per tick, ticket 48), so a
  reminder never rings twice. The default keeps every other caller's call as
  it was.
- The worker's `web_push_delivery` lane sends the rows (`dw_worker.consumers.
  web_push_delivery`); retention, expiry of rows no lane sends, and the
  cross-tenant scope read are the outbox's own and need no change.

The signature changes, so the function is dropped and created again with its
EXECUTE grant; downgrade restores the six-argument one exactly.
"""

from __future__ import annotations

from alembic import op

revision = "19a366484422"
down_revision = "fe1e1ddf1ea6"
branch_labels = None
depends_on = None

_HEAD = """
        CREATE FUNCTION platform.deliver_notification(
            p_workspace_id uuid,
            p_recipients uuid[],
            p_source_key text,
            p_title text,
            p_body text,
            p_link text{extra}
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
            WITH delivered AS (
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
                ON CONFLICT ON CONSTRAINT uq_notifications_recipient_user_id_source_key
                    DO NOTHING
                RETURNING recipient_user_id
            ), queued AS (
                INSERT INTO platform.channel_deliveries (
                    id, tenant_id, workspace_id, recipient_user_id, channel, source_key,
                    title, link
                )
                SELECT gen_random_uuid(), v_tenant, p_workspace_id, d.recipient_user_id,
                       e.provider, p_source_key, p_title, p_link
                FROM delivered d
                JOIN platform.external_identities e
                  ON e.user_id = d.recipient_user_id AND e.provider IN ('zalo')
                ON CONFLICT ON CONSTRAINT
                    uq_channel_deliveries_tenant_id_channel_source_key_recipient
                    DO NOTHING
            ){pushed}
            SELECT count(*) INTO v_delivered FROM delivered;
            RETURN v_delivered;
        END
        $$
"""

_PUSHED = """, pushed AS (
                INSERT INTO platform.channel_deliveries (
                    id, tenant_id, workspace_id, recipient_user_id, channel, source_key,
                    title, link
                )
                SELECT gen_random_uuid(), v_tenant, p_workspace_id, d.recipient_user_id,
                       'web_push', p_source_key, p_title, p_link
                FROM delivered d
                WHERE p_push AND EXISTS (
                    SELECT 1 FROM platform.push_subscriptions s
                    WHERE s.tenant_id = v_tenant
                      AND s.workspace_id = p_workspace_id
                      AND s.user_id = d.recipient_user_id
                )
                ON CONFLICT ON CONSTRAINT
                    uq_channel_deliveries_tenant_id_channel_source_key_recipient
                    DO NOTHING
            )"""

_OLD = "platform.deliver_notification(uuid, uuid[], text, text, text, text)"
_NEW = "platform.deliver_notification(uuid, uuid[], text, text, text, text, boolean)"


def _grant(signature: str) -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                GRANT EXECUTE ON FUNCTION {signature} TO dw_app;
            END IF;
        END
        $$
        """
    )


def _channels(values: str) -> None:
    op.execute(
        "ALTER TABLE platform.channel_deliveries DROP CONSTRAINT ck_channel_deliveries_channel"
    )
    op.execute(
        "ALTER TABLE platform.channel_deliveries ADD CONSTRAINT ck_channel_deliveries_channel"
        f" CHECK (channel IN ({values}))"
    )


def upgrade() -> None:
    _channels("'zalo', 'web_push'")
    op.execute(f"DROP FUNCTION {_OLD}")
    op.execute(_HEAD.format(extra=",\n            p_push boolean DEFAULT true", pushed=_PUSHED))
    _grant(_NEW)


def downgrade() -> None:
    op.execute("DELETE FROM platform.channel_deliveries WHERE channel = 'web_push'")
    op.execute(f"DROP FUNCTION {_NEW}")
    op.execute(_HEAD.format(extra="", pushed=""))
    _grant(_OLD)
    _channels("'zalo'")
