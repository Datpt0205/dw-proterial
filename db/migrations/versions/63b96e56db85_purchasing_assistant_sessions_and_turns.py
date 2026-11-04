"""purchasing assistant sessions and turns

Revision ID: 63b96e56db85
Revises: 13bff35b038b
Create Date: 2026-11-04

DW2, DW02 function 6: the status assistant's sessions, in DW1's shape
(`e0940c90ce04`, dw_sales ADR 0007) and in DW2's own schema:

- **`purchasing.assistant_sessions`**: one per conversation, a person's own;
  `last_turn_at` the one column the application updates.
- **`purchasing.assistant_turns`**: each question, what it was read as, the
  answer, the cases it rests on (`cites`, `[{case_id, label}]`) and the case
  the conversation is on after it (`focus_*`, both or none). Appended, never
  changed; the foreign key `(tenant_id, workspace_id, user_id, session_id)`
  keeps a turn in its asker's session whatever writes it.
- **Fixed sets CHECKed**, text bounded by `char_length` (failure-modes #4).
- **A person's own, by RLS**: `tenant AND ((workspace AND user) OR scope)` to
  read, `tenant AND workspace AND user` to write.
- **Privileges:** `dw_app` reads and inserts both, UPDATE only of
  `last_turn_at`, no DELETE (REVOKEd). Sessions leave through
  `purchasing.prune_assistant_sessions()` (SECURITY DEFINER, fixed
  `search_path`, no argument): thirty days after their last turn, turns by
  cascade; the worker's `purchasing_assistant_retention` lane calls it.
"""

from __future__ import annotations

from alembic import op

revision = "63b96e56db85"
down_revision = "13bff35b038b"
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

# `dw_purchasing.domain.assistant.AssistantQuestionKind`, held to it by
# `test_purchasing_assistant.py`.
_KINDS = "('request_status', 'my_work', 'late_orders', 'out_of_scope')"

_SESSIONS = """
    CREATE TABLE purchasing.assistant_sessions (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        user_id uuid NOT NULL,
        title text NOT NULL,
        created_at timestamp with time zone NOT NULL,
        last_turn_at timestamp with time zone NOT NULL,
        CONSTRAINT pk_assistant_sessions PRIMARY KEY (id),
        CONSTRAINT uq_assistant_sessions_tenant_id_workspace_id_user_id_id
            UNIQUE (tenant_id, workspace_id, user_id, id),
        CONSTRAINT fk_assistant_sessions_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_assistant_sessions_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_assistant_sessions_user_id_users FOREIGN KEY (user_id)
            REFERENCES platform.users (id) ON DELETE CASCADE,
        CONSTRAINT ck_assistant_sessions_title CHECK (char_length(title) BETWEEN 1 AND 80),
        CONSTRAINT ck_assistant_sessions_last_turn_at CHECK (last_turn_at >= created_at)
    )
"""

_TURNS = f"""
    CREATE TABLE purchasing.assistant_turns (
        session_id uuid NOT NULL,
        seq integer NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        user_id uuid NOT NULL,
        asked_at timestamp with time zone NOT NULL,
        question text NOT NULL,
        kind text NOT NULL,
        reference text,
        answer text NOT NULL,
        cites jsonb NOT NULL,
        focus_case_id uuid,
        focus_label text,
        answered_by text NOT NULL,
        CONSTRAINT pk_assistant_turns PRIMARY KEY (session_id, seq),
        CONSTRAINT fk_assistant_turns_session_id_assistant_sessions
            FOREIGN KEY (tenant_id, workspace_id, user_id, session_id)
            REFERENCES purchasing.assistant_sessions (tenant_id, workspace_id, user_id, id)
            ON DELETE CASCADE,
        CONSTRAINT fk_assistant_turns_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_assistant_turns_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_assistant_turns_user_id_users FOREIGN KEY (user_id)
            REFERENCES platform.users (id) ON DELETE CASCADE,
        CONSTRAINT ck_assistant_turns_seq CHECK (seq >= 1),
        CONSTRAINT ck_assistant_turns_question CHECK (char_length(question) BETWEEN 1 AND 500),
        CONSTRAINT ck_assistant_turns_kind CHECK (kind IN {_KINDS}),
        CONSTRAINT ck_assistant_turns_reference CHECK (char_length(reference) BETWEEN 1 AND 64),
        CONSTRAINT ck_assistant_turns_answer CHECK (char_length(answer) BETWEEN 1 AND 4000),
        CONSTRAINT ck_assistant_turns_cites CHECK (jsonb_typeof(cites) = 'array'),
        CONSTRAINT ck_assistant_turns_focus CHECK ((focus_case_id IS NULL) = (focus_label IS NULL)),
        CONSTRAINT ck_assistant_turns_focus_label CHECK (
            char_length(focus_label) BETWEEN 1 AND 200
        ),
        CONSTRAINT ck_assistant_turns_answered_by CHECK (answered_by IN ('model', 'code'))
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE purchasing.assistant_sessions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.assistant_sessions FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_assistant_sessions ON purchasing.assistant_sessions"
    f" USING {_READ} WITH CHECK {_WRITE}",
    "ALTER TABLE purchasing.assistant_turns ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.assistant_turns FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_assistant_turns ON purchasing.assistant_turns"
    f" USING {_READ} WITH CHECK {_WRITE}",
)

_INDEXES: tuple[str, ...] = (
    # A person's sessions, the most recently used first (`GET .../sessions`).
    "CREATE INDEX ix_assistant_sessions_tenant_id_user_id_last_turn_at_id"
    " ON purchasing.assistant_sessions (tenant_id, user_id, last_turn_at DESC, id DESC)",
    "CREATE INDEX ix_assistant_sessions_workspace_id"
    " ON purchasing.assistant_sessions (workspace_id)",
    "CREATE INDEX ix_assistant_sessions_user_id ON purchasing.assistant_sessions (user_id)",
    # The prune's window.
    "CREATE INDEX ix_assistant_sessions_last_turn_at"
    " ON purchasing.assistant_sessions (last_turn_at)",
    # A session's turns, in order, with what RLS supplies first; it also
    # carries the foreign key to the session, column for column.
    "CREATE INDEX ix_assistant_turns_tenant_id_workspace_id_user_id_session_id_seq"
    " ON purchasing.assistant_turns (tenant_id, workspace_id, user_id, session_id, seq)",
    "CREATE INDEX ix_assistant_turns_workspace_id ON purchasing.assistant_turns (workspace_id)",
    "CREATE INDEX ix_assistant_turns_user_id ON purchasing.assistant_turns (user_id)",
)

_PRUNE = """
CREATE FUNCTION purchasing.prune_assistant_sessions()
RETURNS integer
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, purchasing
AS $$
    WITH gone AS (
        DELETE FROM purchasing.assistant_sessions
        WHERE last_turn_at < now() - interval '30 days'
        RETURNING 1
    )
    SELECT count(*)::integer FROM gone
$$
"""

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON purchasing.assistant_sessions TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON purchasing.assistant_sessions FROM dw_app;
            GRANT UPDATE (last_turn_at) ON purchasing.assistant_sessions TO dw_app;
            GRANT SELECT, INSERT ON purchasing.assistant_turns TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON purchasing.assistant_turns FROM dw_app;
            GRANT EXECUTE ON FUNCTION purchasing.prune_assistant_sessions() TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_SESSIONS)
    op.execute(_TURNS)
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_PRUNE)
    op.execute("REVOKE ALL ON FUNCTION purchasing.prune_assistant_sessions() FROM PUBLIC")
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP FUNCTION purchasing.prune_assistant_sessions()")
    op.execute("DROP TABLE purchasing.assistant_turns")
    op.execute("DROP TABLE purchasing.assistant_sessions")
