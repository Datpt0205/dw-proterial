"""sales assistant sessions and turns

Revision ID: e0940c90ce04
Revises: cbd4fbacfce2
Create Date: 2026-10-30 07:50:12.104523+00:00

dw_sales ADR 0007: the status assistant answers from live data, in sessions
a person keeps for a while.

- **`sales.assistant_sessions`**: one per conversation, a person's own.
  `last_turn_at` is the one column the application updates (a turn moves
  it); the session is never edited otherwise.
- **`sales.assistant_turns`**: each question, what it was read as, the answer
  and the cases it rests on (`cites`, `[{kind, case_id, label}]`), and the
  case the conversation is on after it (`focus_*`, all three or none).
  Appended, never changed. A turn belongs to its session's person: the
  foreign key is `(tenant_id, workspace_id, user_id, session_id)`, so no row
  can sit in another person's session whatever writes it.
- **Fixed sets are CHECKed** (`kind`: `QuestionKind`; `answered_by`;
  `focus_kind`: `CaseKind`), and every text is bounded by `char_length`, never
  by a regex repetition (failure-modes #4).
- **A person's own, by RLS**, in the shape `test_rls_coverage.py` admits:
  `tenant AND ((workspace AND user) OR scope)` to read, the offboarding lane's
  scope as the alternative; `tenant AND workspace AND user` to write, so the
  scope never writes.
- **Privileges:** `dw_app` reads and inserts both; UPDATE only of
  `last_turn_at`; no DELETE (a GRANT never takes one away, so REVOKEd,
  failure-modes #7). Sessions leave through
  `sales.prune_assistant_sessions()` (SECURITY DEFINER, fixed `search_path`,
  no argument so no caller can widen it): thirty days after their last turn,
  with their turns by cascade. The worker's `sales_assistant_retention` lane
  calls it.
- **Foreign keys** to the tenant, the workspace and the user, `ON DELETE
  CASCADE`, each indexed on its own side; the listing index leads with what
  RLS supplies.
"""

from __future__ import annotations

from alembic import op

revision = "e0940c90ce04"
down_revision = "cbd4fbacfce2"
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

# `dw_sales.domain.assistant.QuestionKind`, held to it by `test_assistant.py`.
_KINDS = "('order_status', 'quote_status', 'my_work', 'overdue', 'out_of_scope')"

_SESSIONS = """
    CREATE TABLE sales.assistant_sessions (
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
    CREATE TABLE sales.assistant_turns (
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
        focus_kind text,
        focus_case_id uuid,
        focus_label text,
        answered_by text NOT NULL,
        CONSTRAINT pk_assistant_turns PRIMARY KEY (session_id, seq),
        CONSTRAINT fk_assistant_turns_session_id_assistant_sessions
            FOREIGN KEY (tenant_id, workspace_id, user_id, session_id)
            REFERENCES sales.assistant_sessions (tenant_id, workspace_id, user_id, id)
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
        CONSTRAINT ck_assistant_turns_focus CHECK (
            (focus_kind IS NULL) = (focus_case_id IS NULL)
            AND (focus_kind IS NULL) = (focus_label IS NULL)
        ),
        CONSTRAINT ck_assistant_turns_focus_kind CHECK (focus_kind IN ('order', 'quote')),
        CONSTRAINT ck_assistant_turns_focus_label CHECK (
            char_length(focus_label) BETWEEN 1 AND 200
        ),
        CONSTRAINT ck_assistant_turns_answered_by CHECK (answered_by IN ('model', 'code'))
    )
"""

# Written out, not generated: `scripts/verify_invariants.py` reads migration text.
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.assistant_sessions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.assistant_sessions FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_assistant_sessions ON sales.assistant_sessions"
    f" USING {_READ} WITH CHECK {_WRITE}",
    "ALTER TABLE sales.assistant_turns ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.assistant_turns FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_assistant_turns ON sales.assistant_turns"
    f" USING {_READ} WITH CHECK {_WRITE}",
)

_INDEXES: tuple[str, ...] = (
    # A person's sessions, the most recently used first (`GET .../sessions`).
    "CREATE INDEX ix_assistant_sessions_tenant_id_user_id_last_turn_at_id"
    " ON sales.assistant_sessions (tenant_id, user_id, last_turn_at DESC, id DESC)",
    "CREATE INDEX ix_assistant_sessions_workspace_id ON sales.assistant_sessions (workspace_id)",
    "CREATE INDEX ix_assistant_sessions_user_id ON sales.assistant_sessions (user_id)",
    # The prune's window.
    "CREATE INDEX ix_assistant_sessions_last_turn_at ON sales.assistant_sessions (last_turn_at)",
    # A session's turns, in order, with what RLS supplies first; it also
    # carries the foreign key to the session, column for column.
    "CREATE INDEX ix_assistant_turns_tenant_id_workspace_id_user_id_session_id_seq"
    " ON sales.assistant_turns (tenant_id, workspace_id, user_id, session_id, seq)",
    "CREATE INDEX ix_assistant_turns_workspace_id ON sales.assistant_turns (workspace_id)",
    "CREATE INDEX ix_assistant_turns_user_id ON sales.assistant_turns (user_id)",
)

_PRUNE = """
CREATE FUNCTION sales.prune_assistant_sessions()
RETURNS integer
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, sales
AS $$
    WITH gone AS (
        DELETE FROM sales.assistant_sessions
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
            GRANT SELECT, INSERT ON sales.assistant_sessions TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON sales.assistant_sessions FROM dw_app;
            GRANT UPDATE (last_turn_at) ON sales.assistant_sessions TO dw_app;
            GRANT SELECT, INSERT ON sales.assistant_turns TO dw_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON sales.assistant_turns FROM dw_app;
            GRANT EXECUTE ON FUNCTION sales.prune_assistant_sessions() TO dw_app;
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
    op.execute("REVOKE ALL ON FUNCTION sales.prune_assistant_sessions() FROM PUBLIC")
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP FUNCTION sales.prune_assistant_sessions()")
    op.execute("DROP TABLE sales.assistant_turns")
    op.execute("DROP TABLE sales.assistant_sessions")
