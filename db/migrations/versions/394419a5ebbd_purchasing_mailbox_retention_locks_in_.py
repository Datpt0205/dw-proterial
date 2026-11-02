"""purchasing mailbox retention locks in the partition lane's order

Revision ID: 394419a5ebbd
Revises: 32c1f04b76d6
Create Date: 2026-11-02 07:39:39.547960+00:00

Measured 2026-11-02 on a worker's first tick: `platform.ensure_time_partitions`
makes a month for `purchasing.mailbox_messages`, then `_attachments`, then
`_files`, in one transaction, each holding its parent's ACCESS EXCLUSIVE lock
to the end; `32c1f04b76d6`'s `purchasing.prune_mailbox_in` deleted
attachments first, then messages. Each held what the other waited for, and
PostgreSQL aborted one ("deadlock detected").

The function now deletes in the lane's order: messages, attachments, files.
The two tables have no foreign key between them (`32c1f04b76d6`), so the
order is free. Its owner, SECURITY DEFINER, search_path and grants are
unchanged (CREATE OR REPLACE keeps the grants). Downgrade restores
`32c1f04b76d6`'s body.
"""

from __future__ import annotations

from alembic import op

revision = "394419a5ebbd"
down_revision = "32c1f04b76d6"
branch_labels = None
depends_on = None

_HEAD = """
    CREATE OR REPLACE FUNCTION purchasing.prune_mailbox_in(
        in_tenant uuid, in_workspace uuid, received_before timestamptz
    ) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, purchasing
    AS $$
    DECLARE
        gone bigint := 0;
    BEGIN
        IF received_before IS NULL THEN
            RETURN 0;
        END IF;
"""

_MESSAGES = """
        DELETE FROM purchasing.mailbox_messages
         WHERE tenant_id = in_tenant AND workspace_id = in_workspace
           AND received_at < received_before;
        GET DIAGNOSTICS gone = ROW_COUNT;
"""

_ATTACHMENTS = """
        DELETE FROM purchasing.mailbox_attachments
         WHERE tenant_id = in_tenant AND workspace_id = in_workspace
           AND received_at < received_before;
"""

_TAIL = """
        -- A file handled before the cutoff was written before it too, so the
        -- lane no longer reads it (`MailDrop`): forgetting its name does not
        -- bring its mail back.
        DELETE FROM purchasing.mailbox_files
         WHERE tenant_id = in_tenant AND workspace_id = in_workspace
           AND handled_at < received_before;
        RETURN gone;
    END
    $$
"""


def upgrade() -> None:
    # The partition lane's order (`ensure_time_partitions`' parents list).
    op.execute(_HEAD + _MESSAGES + _ATTACHMENTS + _TAIL)


def downgrade() -> None:
    op.execute(_HEAD + _ATTACHMENTS + _MESSAGES + _TAIL)
