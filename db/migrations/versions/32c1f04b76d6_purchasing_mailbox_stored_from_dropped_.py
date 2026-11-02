"""purchasing mailbox stored from dropped eml files

Revision ID: 32c1f04b76d6
Revises: 191b591d4ef1
Create Date: 2026-11-02 02:04:58.554990+00:00

DW2 reads real mail the way DW1 does (Sales ticket 43): a flow exports each
mail reaching the purchasing mailbox as an `.eml` file into a folder DW2's
host reads; the worker's `purchasing_mail_drop` lane parses each file in the
reader sandbox and stores it here. The folder is a drop box: PostgreSQL is the
mailbox, read by the API and the worker through `SqlPurchasingMailbox` (an
`InboxPort`). The queue is Purchasing's own, not Sales' (ADR 0014 decision 2):
its own tables, lane, audit actor, retention and offboarding.

The three tables are `e544ff20fad6`'s with `2b666371099a`'s refusal folded
in, less `left_out` (DW2 leaves no sender out; a mail from outside the
company goes to a person when it is read):

- **`purchasing.mailbox_messages`**: one row per message, the
  `InboundMessage` whole in `message`; the keys beside it are CHECKed equal
  to the document. `message_id` is the file's sha256 (`eml-<hex>`), so a
  second copy of one file is a primary-key conflict; `internet_message_id`
  with `sender_address` finds one mail exported twice.
- **`purchasing.mailbox_attachments`**: each attachment's bytes, at most
  20 MB. No foreign key to the message, for the reason `e544ff20fad6` gives
  (partitioned both, and `_ensure_one_partition` relocates DEFAULT rows).
- **`purchasing.mailbox_files`**: every file the lane handled, by name:
  `stored`, `duplicate` or `refused` (with the reason code wrote).
- **Tenant AND (workspace OR scope)** on both sides of every policy, the
  DEFAULT partitions policed in their own right.
- **Append-only for the application**: `dw_app` holds SELECT and INSERT;
  UPDATE and DELETE are REVOKEd from every parent and DEFAULT partition (the
  schema's default privileges grant them, and a GRANT takes nothing away),
  and `_ensure_one_partition` withholds them from every month it makes.
- **Range-partitioned by month** (`received_at`, `handled_at`), named by
  `platform.ensure_time_partitions` (the list grown by three; the body is
  `621864952a54`'s).
- **Offboarding**: each table carries a `tenant_isolation_%` policy and a
  `tenant_id`, so `SqlTenantOffboarding` exports it from the catalog; its rows
  leave with the tenant and workspace (`ON DELETE CASCADE`), since `dw_app`
  may not DELETE them.
- **Retention**, the tenant's own term (`purchasing_rules@1.7.0`,
  `retention.mailbox_days`): `purchasing.prune_mailbox_in(tenant, workspace,
  before)`, SECURITY DEFINER, deletes one workspace's mail received before the
  cutoff with its attachments, and the files handled before it; EXECUTE to
  `dw_app` only. `purchasing.retention_scopes()` now names a workspace that
  holds mail and nothing else yet.

Downgrade restores `e544ff20fad6`'s `ensure_time_partitions` and
`191b591d4ef1`'s `retention_scopes`, then drops the function and the tables.
"""

from __future__ import annotations

from alembic import op

revision = "32c1f04b76d6"
down_revision = "191b591d4ef1"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_MESSAGE_ID_CHECK = "message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512"
# A file's name, never a path.
_SOURCE_NAME_CHECK = (
    "char_length(source_name) BETWEEN 1 AND 255"
    " AND strpos(source_name, '/') = 0 AND strpos(source_name, chr(92)) = 0"
)

_MESSAGES = f"""
    CREATE TABLE purchasing.mailbox_messages (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        received_at timestamp with time zone NOT NULL,
        sender_address text NOT NULL,
        internet_message_id text,
        source_name text NOT NULL,
        message jsonb NOT NULL,
        stored_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_mailbox_messages
            PRIMARY KEY (tenant_id, workspace_id, message_id, received_at),
        CONSTRAINT fk_mailbox_messages_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_mailbox_messages_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        -- PostgreSQL's regex bounds a repetition at 255 (RE_DUP_MAX): each
        -- length is its own clause (failure-modes #4).
        CONSTRAINT ck_mailbox_messages_message_id CHECK ({_MESSAGE_ID_CHECK}),
        CONSTRAINT ck_mailbox_messages_sender_address CHECK (
            char_length(sender_address) BETWEEN 3 AND 254
        ),
        CONSTRAINT ck_mailbox_messages_internet_message_id CHECK (
            internet_message_id ~ '^<[!-~]+>$' AND char_length(internet_message_id) <= 996
        ),
        CONSTRAINT ck_mailbox_messages_source_name CHECK ({_SOURCE_NAME_CHECK}),
        -- The keys beside the document are the document's own.
        CONSTRAINT ck_mailbox_messages_message CHECK (
            jsonb_typeof(message) = 'object'
            AND message ->> 'message_id' = message_id
            AND message -> 'sender' ->> 'address' = sender_address
            AND (message ->> 'internet_message_id') IS NOT DISTINCT FROM internet_message_id
        )
    )
    PARTITION BY RANGE (received_at)
"""

_ATTACHMENTS = f"""
    CREATE TABLE purchasing.mailbox_attachments (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        received_at timestamp with time zone NOT NULL,
        attachment_id text NOT NULL,
        content bytea NOT NULL,
        stored_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_mailbox_attachments
            PRIMARY KEY (tenant_id, workspace_id, message_id, received_at, attachment_id),
        CONSTRAINT fk_mailbox_attachments_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_mailbox_attachments_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_mailbox_attachments_message_id CHECK ({_MESSAGE_ID_CHECK}),
        -- `dw_platform.domain.messages.AttachmentId`.
        CONSTRAINT ck_mailbox_attachments_attachment_id CHECK (
            attachment_id ~ '^[A-Za-z0-9._-]{{1,128}}$'
        ),
        CONSTRAINT ck_mailbox_attachments_content CHECK (octet_length(content) <= 20971520)
    )
    PARTITION BY RANGE (received_at)
"""

_FILES = f"""
    CREATE TABLE purchasing.mailbox_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        source_name text NOT NULL,
        handled_at timestamp with time zone DEFAULT now() NOT NULL,
        outcome text NOT NULL,
        message_id text,
        reason text,
        CONSTRAINT pk_mailbox_files
            PRIMARY KEY (tenant_id, workspace_id, source_name, handled_at),
        CONSTRAINT fk_mailbox_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_mailbox_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_mailbox_files_source_name CHECK ({_SOURCE_NAME_CHECK}),
        -- `dw_purchasing.application.mail_drop`'s outcomes.
        CONSTRAINT ck_mailbox_files_outcome CHECK (
            outcome IN ('stored', 'duplicate', 'refused')
        ),
        -- A refused file names no message and says why; a stored or
        -- duplicate one names its message and gives no reason.
        CONSTRAINT ck_mailbox_files_message_id CHECK (
            (outcome = 'refused') = (message_id IS NULL)
            AND (message_id IS NULL OR ({_MESSAGE_ID_CHECK}))
        ),
        CONSTRAINT ck_mailbox_files_reason CHECK (
            (outcome = 'refused') = (reason IS NOT NULL)
            AND (reason IS NULL OR char_length(reason) BETWEEN 1 AND 300)
        )
    )
    PARTITION BY RANGE (handled_at)
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration
# text. Each DEFAULT partition is policed in its own right (0009).
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE purchasing.mailbox_messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_messages FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_messages ON purchasing.mailbox_messages"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mailbox_messages_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_messages_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_messages_default"
    f" ON purchasing.mailbox_messages_default USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mailbox_attachments ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_attachments FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_attachments ON purchasing.mailbox_attachments"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mailbox_attachments_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_attachments_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_attachments_default"
    f" ON purchasing.mailbox_attachments_default USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mailbox_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_files FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_files ON purchasing.mailbox_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mailbox_files_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mailbox_files_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_files_default"
    f" ON purchasing.mailbox_files_default USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # The mailbox oldest first (`SqlPurchasingMailbox.list_messages`).
    "CREATE INDEX ix_mailbox_messages_tenant_id_workspace_id_received_at"
    " ON purchasing.mailbox_messages (tenant_id, workspace_id, received_at, message_id)",
    # One mail exported twice (`SqlPurchasingMailbox.store`).
    "CREATE INDEX ix_mailbox_messages_tenant_id_workspace_id_internet_message_id"
    " ON purchasing.mailbox_messages (tenant_id, workspace_id, internet_message_id, sender_address)"
    " WHERE internet_message_id IS NOT NULL",
    # The workspace's own key, for the cascade.
    "CREATE INDEX ix_mailbox_messages_workspace_id ON purchasing.mailbox_messages (workspace_id)",
    "CREATE INDEX ix_mailbox_attachments_workspace_id"
    " ON purchasing.mailbox_attachments (workspace_id)",
    "CREATE INDEX ix_mailbox_files_workspace_id ON purchasing.mailbox_files (workspace_id)",
)

# The schema's default privileges gave every verb (2d0c58dc3806); a GRANT
# never takes one away, so the withheld verbs are REVOKEd by name.
_GRANTS: tuple[str, ...] = tuple(
    statement
    for table in (
        "mailbox_messages",
        "mailbox_messages_default",
        "mailbox_attachments",
        "mailbox_attachments_default",
        "mailbox_files",
        "mailbox_files_default",
    )
    for statement in (
        f"GRANT SELECT, INSERT ON purchasing.{table} TO dw_app",
        f"REVOKE UPDATE, DELETE ON purchasing.{table} FROM dw_app",
    )
)

_PRUNE = "purchasing.prune_mailbox_in(uuid, uuid, timestamptz)"

_PRUNE_MAILBOX = """
    CREATE FUNCTION purchasing.prune_mailbox_in(
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
        DELETE FROM purchasing.mailbox_attachments
         WHERE tenant_id = in_tenant AND workspace_id = in_workspace
           AND received_at < received_before;
        DELETE FROM purchasing.mailbox_messages
         WHERE tenant_id = in_tenant AND workspace_id = in_workspace
           AND received_at < received_before;
        GET DIAGNOSTICS gone = ROW_COUNT;
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

_SCOPES_BEFORE = """
    CREATE OR REPLACE FUNCTION purchasing.retention_scopes()
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, purchasing
    AS $$
        SELECT c.tenant_id, c.workspace_id FROM purchasing.cases c
        UNION
        SELECT o.tenant_id, o.workspace_id FROM purchasing.mail_outcomes o
    $$
"""

_SCOPES_WITH_MAIL = """
    CREATE OR REPLACE FUNCTION purchasing.retention_scopes()
    RETURNS TABLE (tenant_id uuid, workspace_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, purchasing
    AS $$
        SELECT c.tenant_id, c.workspace_id FROM purchasing.cases c
        UNION
        SELECT o.tenant_id, o.workspace_id FROM purchasing.mail_outcomes o
        UNION
        SELECT m.tenant_id, m.workspace_id FROM purchasing.mailbox_messages m
        UNION
        SELECT f.tenant_id, f.workspace_id FROM purchasing.mailbox_files f
    $$
"""


def _ensure_time_partitions(parents: str) -> str:
    """`621864952a54`'s body, with the parents it names."""
    return f"""
CREATE OR REPLACE FUNCTION platform.ensure_time_partitions(months_ahead integer)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    parent text;
    step integer;
    made text;
    first_month constant date := date_trunc('month', now())::date;
BEGIN
    IF months_ahead IS NULL OR months_ahead < 1 OR months_ahead > 24 THEN
        RAISE EXCEPTION 'months_ahead must be between 1 and 24, got %', months_ahead;
    END IF;
    -- The parents are a constant: no caller-supplied string names a table.
    FOREACH parent IN ARRAY ARRAY[{parents}] LOOP
        FOR step IN 0..months_ahead LOOP
            made := platform._ensure_one_partition(
                parent, (first_month + (step || ' month')::interval)::date
            );
            IF made IS NOT NULL THEN
                RETURN NEXT made;
            END IF;
        END LOOP;
    END LOOP;
END;
$fn$
"""


_PARENTS_BEFORE = (
    "'platform.audit_events', 'sales.case_events', 'sales.step_outcomes',"
    " 'sales.mailbox_messages', 'sales.mailbox_attachments', 'sales.mailbox_files'"
)
_PARENTS = (
    _PARENTS_BEFORE + ", 'purchasing.mailbox_messages', 'purchasing.mailbox_attachments',"
    " 'purchasing.mailbox_files'"
)


def upgrade() -> None:
    op.execute(_MESSAGES)
    op.execute(
        "CREATE TABLE purchasing.mailbox_messages_default"
        " PARTITION OF purchasing.mailbox_messages DEFAULT"
    )
    op.execute(_ATTACHMENTS)
    op.execute(
        "CREATE TABLE purchasing.mailbox_attachments_default"
        " PARTITION OF purchasing.mailbox_attachments DEFAULT"
    )
    op.execute(_FILES)
    op.execute(
        "CREATE TABLE purchasing.mailbox_files_default"
        " PARTITION OF purchasing.mailbox_files DEFAULT"
    )
    for statement in (*_ROW_SECURITY, *_INDEXES, *_GRANTS):
        op.execute(statement)
    op.execute(_PRUNE_MAILBOX)
    op.execute(f"REVOKE ALL ON FUNCTION {_PRUNE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_PRUNE} TO dw_app")
    op.execute(_SCOPES_WITH_MAIL)
    op.execute(_ensure_time_partitions(_PARENTS))


def downgrade() -> None:
    op.execute(_ensure_time_partitions(_PARENTS_BEFORE))
    op.execute(_SCOPES_BEFORE)
    op.execute(f"DROP FUNCTION {_PRUNE}")
    # The partitions go with their parent; no CASCADE, so anything else that
    # came to depend on a table stops the downgrade instead.
    op.execute("DROP TABLE purchasing.mailbox_files")
    op.execute("DROP TABLE purchasing.mailbox_attachments")
    op.execute("DROP TABLE purchasing.mailbox_messages")
