"""sales assistant one conversation per case

Revision ID: bfe2d1aeadcd
Revises: efc46a50e75e
Create Date: 2026-11-15 17:30:35.098097+00:00

Ticket 46: the case is the conversation. `sales.assistant_sessions` keeps
being the one owner of a person's conversations (no second table): a row is
either bound to one case or is the person's one general conversation.

- **`case_kind`, `case_id`**: the case the conversation is bound to, both or
  neither (CHECKed; `case_kind` is `CaseKind`'s set). Set by code from the
  case page's route after the caller's read of that case is checked, never
  from a body. No foreign key: an order and a quote live in different
  tables, and the turns' `focus_case_id` has none either; a conversation
  outlives nothing, it is pruned 30 days after its last turn.
- **One per person and case, one general per person**: two partial unique
  indexes, led by what RLS supplies, which are also how a conversation is
  found. Before the general one can be unique, a person's older free
  sessions are deleted (their turns by cascade), keeping each person's most
  recently used: they were working conversations pruned after 30 days
  anyway, and two general conversations cannot be merged turn for turn.
- **`last_read_at`**: when the person last saw it; an answer kept after it
  is the unread mark the case lists show. `dw_app` may UPDATE it and
  `last_turn_at` only; still no DELETE (the prune function's).
- RLS, the prune and the turns are unchanged: the policy already narrows by
  tenant, workspace and user with the offboarding scope on reads.
"""

from __future__ import annotations

from alembic import op

revision = "bfe2d1aeadcd"
down_revision = "efc46a50e75e"
branch_labels = None
depends_on = None

_COLUMNS = """
    ALTER TABLE sales.assistant_sessions
        ADD COLUMN case_kind text,
        ADD COLUMN case_id uuid,
        ADD COLUMN last_read_at timestamp with time zone,
        ADD CONSTRAINT ck_assistant_sessions_case CHECK ((case_kind IS NULL) = (case_id IS NULL)),
        ADD CONSTRAINT ck_assistant_sessions_case_kind CHECK (case_kind IN ('order', 'quote'))
"""

# Each person's most recently used free session is their general conversation.
_ONE_GENERAL = """
    DELETE FROM sales.assistant_sessions AS older
    WHERE older.case_id IS NULL
      AND EXISTS (
        SELECT 1 FROM sales.assistant_sessions AS newer
        WHERE newer.tenant_id = older.tenant_id
          AND newer.workspace_id = older.workspace_id
          AND newer.user_id = older.user_id
          AND newer.case_id IS NULL
          AND (newer.last_turn_at, newer.id) > (older.last_turn_at, older.id)
      )
"""

_INDEXES: tuple[str, ...] = (
    # A person's conversation on a case, found by the case.
    "CREATE UNIQUE INDEX uq_assistant_sessions_one_per_case ON sales.assistant_sessions"
    " (tenant_id, workspace_id, user_id, case_id) WHERE case_id IS NOT NULL",
    # A person's one general conversation.
    "CREATE UNIQUE INDEX uq_assistant_sessions_one_general ON sales.assistant_sessions"
    " (tenant_id, workspace_id, user_id) WHERE case_id IS NULL",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT UPDATE (last_read_at) ON sales.assistant_sessions TO dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_COLUMNS)
    op.execute(_ONE_GENERAL)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_GRANTS)


def downgrade() -> None:
    op.execute("DROP INDEX sales.uq_assistant_sessions_one_general")
    op.execute("DROP INDEX sales.uq_assistant_sessions_one_per_case")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN"
        " REVOKE UPDATE (last_read_at) ON sales.assistant_sessions FROM dw_app;"
        " END IF; END $$"
    )
    op.execute(
        "ALTER TABLE sales.assistant_sessions"
        " DROP COLUMN last_read_at, DROP COLUMN case_id, DROP COLUMN case_kind"
    )
