"""sales mailbox messages stored from dropped eml files

Revision ID: e544ff20fad6
Revises: 4bca401bcb3a
Create Date: 2026-10-27 03:49:41.980937+00:00

Sales ticket 43: DW1 reads real mail. A Sales PIC's Power Automate flow
exports each mail as an `.eml` file into a folder DW1's host reads; the
worker's `sales_mail_drop` lane parses each file in the reader sandbox and
stores it here. The folder is a drop box: PostgreSQL is the mailbox, read by
the API and the worker through `SqlMailbox` (an `InboxPort`).

- **`sales.mailbox_messages`**: one row per message, the `InboundMessage`
  whole in `message` (one owner of its fields, the model; the columns beside
  it are the keys the queries need, each CHECKed equal to the document).
  `message_id` is the file's sha256 (`eml-<hex>`) and `received_at` is read
  from the file, so a second copy of one file is a primary-key conflict.
  `internet_message_id` with `sender_address` finds one mail exported from two
  PICs' mailboxes. `source_name` is the file it came from: a name, never a
  path.
- **`sales.mailbox_attachments`**: each attachment's bytes, by message and
  attachment id; what describes them (name, type, size, sha256) is in the
  message's document. At most 20 MB each, the largest mail the lane reads.
  **No foreign key to the message**: both tables are partitioned, and
  `platform._ensure_one_partition` relocates rows stranded in a DEFAULT
  partition by DETACH, INSERT and DELETE, which a key between the two would
  either refuse or cascade into deleting attachments. The lane writes a
  message and its attachments in one transaction, and neither table takes
  an UPDATE or a DELETE from the application.
- **`sales.mailbox_files`**: every file the lane has handled, by name, and
  what became of it: `stored`, `duplicate` (its mail was stored from another
  file) or `left_out` (a sender domain the tenant's order rules ignore,
  `ignored_sender_domains`: nothing of that mail is kept). A restart reads
  these names instead of parsing the folders' whole history again in the
  reader sandbox. A file the reader refused is not recorded: it is tried
  again after a restart.
- **Tenant AND workspace**, the shape every workspace-narrowed table has since
  `0d9e3f85d814`, on both sides of each policy.
- **Append-only**: `dw_app` holds SELECT and INSERT; UPDATE and DELETE are
  REVOKEd from each parent and DEFAULT partition (failure-modes #7), and
  `_ensure_one_partition` withholds them from every month it makes.
- **Range-partitioned by month**, the mail on `received_at` and the files
  on `handled_at`, each with a DEFAULT partition policed in its own right,
  all three named by `platform.ensure_time_partitions` (redefined with the
  list grown by three; the body is `621864952a54`'s).
- **Foreign keys to the tenant and the workspace, `ON DELETE CASCADE`**, as
  `sales.step_outcomes`: an offboarded tenant's mail leaves with it. Each is
  indexed on its own side (the primary key leads with `tenant_id`).
- **Indexes led by what RLS supplies**: the mailbox oldest first,
  `(tenant_id, workspace_id, received_at, message_id)`; one mail by its
  Message-ID and sender.
- **No retention** yet: a case's evidence points into its message's
  attachments, so a term must follow the cases'. Owed (ticket 43).

Downgrade restores `4bca401bcb3a`'s `ensure_time_partitions`, then drops the
three tables with their partitions.
"""

from __future__ import annotations

from alembic import op

revision = "e544ff20fad6"
down_revision = "4bca401bcb3a"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_MESSAGES = """
    CREATE TABLE sales.mailbox_messages (
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
        CONSTRAINT ck_mailbox_messages_message_id CHECK (
            message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
        ),
        CONSTRAINT ck_mailbox_messages_sender_address CHECK (
            char_length(sender_address) BETWEEN 3 AND 254
        ),
        CONSTRAINT ck_mailbox_messages_internet_message_id CHECK (
            internet_message_id ~ '^<[!-~]+>$' AND char_length(internet_message_id) <= 996
        ),
        -- A file's name, never a path.
        CONSTRAINT ck_mailbox_messages_source_name CHECK (
            char_length(source_name) BETWEEN 1 AND 255
            AND strpos(source_name, '/') = 0
            AND strpos(source_name, chr(92)) = 0
        ),
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

_ATTACHMENTS = """
    CREATE TABLE sales.mailbox_attachments (
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
        CONSTRAINT ck_mailbox_attachments_message_id CHECK (
            message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
        ),
        -- `dw_sales.domain.messages.AttachmentId`.
        CONSTRAINT ck_mailbox_attachments_attachment_id CHECK (
            attachment_id ~ '^[A-Za-z0-9._-]{1,128}$'
        ),
        CONSTRAINT ck_mailbox_attachments_content CHECK (octet_length(content) <= 20971520)
    )
    PARTITION BY RANGE (received_at)
"""

_FILES = """
    CREATE TABLE sales.mailbox_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        source_name text NOT NULL,
        handled_at timestamp with time zone DEFAULT now() NOT NULL,
        outcome text NOT NULL,
        message_id text,
        CONSTRAINT pk_mailbox_files
            PRIMARY KEY (tenant_id, workspace_id, source_name, handled_at),
        CONSTRAINT fk_mailbox_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_mailbox_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_mailbox_files_source_name CHECK (
            char_length(source_name) BETWEEN 1 AND 255
            AND strpos(source_name, '/') = 0
            AND strpos(source_name, chr(92)) = 0
        ),
        -- `dw_sales.application.mail_drop`'s outcomes; a file left out names
        -- no message, since nothing of it is kept.
        CONSTRAINT ck_mailbox_files_outcome CHECK (
            outcome IN ('stored', 'duplicate', 'left_out')
        ),
        CONSTRAINT ck_mailbox_files_message_id CHECK (
            (outcome = 'left_out') = (message_id IS NULL)
            AND (message_id IS NULL OR (
                message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
            ))
        )
    )
    PARTITION BY RANGE (handled_at)
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration
# text. Each DEFAULT partition is policed in its own right (0009).
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.mailbox_messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_messages FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_messages ON sales.mailbox_messages"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.mailbox_messages_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_messages_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_messages_default"
    f" ON sales.mailbox_messages_default USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.mailbox_attachments ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_attachments FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_attachments ON sales.mailbox_attachments"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.mailbox_attachments_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_attachments_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_attachments_default"
    f" ON sales.mailbox_attachments_default USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.mailbox_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_files FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_files ON sales.mailbox_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.mailbox_files_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.mailbox_files_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_mailbox_files_default"
    f" ON sales.mailbox_files_default USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_INDEXES: tuple[str, ...] = (
    # The mailbox oldest first (`SqlMailbox.list_messages`).
    "CREATE INDEX ix_mailbox_messages_tenant_id_workspace_id_received_at"
    " ON sales.mailbox_messages (tenant_id, workspace_id, received_at, message_id)",
    # One mail exported from two mailboxes (`SqlMailbox.store`).
    "CREATE INDEX ix_mailbox_messages_tenant_id_workspace_id_internet_message_id"
    " ON sales.mailbox_messages (tenant_id, workspace_id, internet_message_id, sender_address)"
    " WHERE internet_message_id IS NOT NULL",
    # The workspace's own key, for the cascade.
    "CREATE INDEX ix_mailbox_messages_workspace_id ON sales.mailbox_messages (workspace_id)",
    "CREATE INDEX ix_mailbox_attachments_workspace_id ON sales.mailbox_attachments (workspace_id)",
    "CREATE INDEX ix_mailbox_files_workspace_id ON sales.mailbox_files (workspace_id)",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.mailbox_messages TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_messages FROM dw_app;
            GRANT SELECT, INSERT ON sales.mailbox_messages_default TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_messages_default FROM dw_app;
            GRANT SELECT, INSERT ON sales.mailbox_attachments TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_attachments FROM dw_app;
            GRANT SELECT, INSERT ON sales.mailbox_attachments_default TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_attachments_default FROM dw_app;
            GRANT SELECT, INSERT ON sales.mailbox_files TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_files FROM dw_app;
            GRANT SELECT, INSERT ON sales.mailbox_files_default TO dw_app;
            REVOKE UPDATE, DELETE ON sales.mailbox_files_default FROM dw_app;
        END IF;
    END
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


_PARENTS_BEFORE = "'platform.audit_events', 'sales.case_events', 'sales.step_outcomes'"
_PARENTS = (
    "'platform.audit_events', 'sales.case_events', 'sales.step_outcomes',"
    " 'sales.mailbox_messages', 'sales.mailbox_attachments', 'sales.mailbox_files'"
)


def upgrade() -> None:
    op.execute(_MESSAGES)
    op.execute(
        "CREATE TABLE sales.mailbox_messages_default PARTITION OF sales.mailbox_messages DEFAULT"
    )
    op.execute(_ATTACHMENTS)
    op.execute(
        "CREATE TABLE sales.mailbox_attachments_default"
        " PARTITION OF sales.mailbox_attachments DEFAULT"
    )
    op.execute(_FILES)
    op.execute("CREATE TABLE sales.mailbox_files_default PARTITION OF sales.mailbox_files DEFAULT")
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_GRANTS)
    op.execute(_ensure_time_partitions(_PARENTS))


def downgrade() -> None:
    op.execute(_ensure_time_partitions(_PARENTS_BEFORE))
    # The partitions go with their parent; no CASCADE, so anything else that
    # came to depend on a table stops the downgrade instead.
    op.execute("DROP TABLE sales.mailbox_files")
    op.execute("DROP TABLE sales.mailbox_attachments")
    op.execute("DROP TABLE sales.mailbox_messages")
