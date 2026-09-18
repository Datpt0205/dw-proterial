"""Give a memory the name of the fact it states, so a newer one can close it.

Memory was append-only. Nothing ever wrote `valid_until`, so two memories that
contradict each other about the same customer both stayed valid for ever and
recall returned both, ordered by confidence — the agent believed whichever it
had been most sure of, not the one that was true now. A customer who moved their
signing date twice left three live answers.

`fact_key` is what makes closing the old one decidable without asking a model
whether two sentences disagree. It names WHAT a memory asserts — "contract_date",
"preferred_channel" — so two memories with the same key about the same subject
are, by construction, two answers to one question, and the later one wins.

Nullable, and that is the whole compatibility story: a memory with no key keeps
the old behaviour and accumulates, which is correct for things that genuinely
accumulate (a meeting happened; another meeting also happened). Only a fact that
declares itself an answer to a named question can supersede.

Nothing is deleted, ever. The superseded row keeps its provenance and its place
in the audit trail; only its window closes. History is not rewritten — that is
the difference between forgetting and lying about what was known.

Reversible: the column and both indexes drop. The `valid_until` values written
through it stay, because they are facts about what happened, not schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "62a9aaba6b16"
down_revision = "c490124d690a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("fact_key", sa.Text, nullable=True),
        schema="memory",
    )
    # The supersession lookup: "what is the live answer to this question, for
    # this subject, from this worker". Partial on the live rows because a closed
    # memory is never a supersession candidate, and that is the large majority
    # of the table on any account that has been worked for a while.
    op.create_index(
        "ix_items_live_fact",
        "items",
        ["tenant_id", "workspace_id", "worker_id", "fact_key"],
        unique=False,
        schema="memory",
        postgresql_where=sa.text("fact_key IS NOT NULL AND valid_until IS NULL"),
    )
    # Recall matches `subject_refs ?| array[...]`, which is a containment query
    # on JSONB and cannot use a b-tree. Without this it is a sequential scan of
    # every memory the tenant owns, on every model call.
    op.create_index(
        "ix_items_subject_refs",
        "items",
        ["subject_refs"],
        unique=False,
        schema="memory",
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_items_subject_refs", table_name="items", schema="memory")
    op.drop_index("ix_items_live_fact", table_name="items", schema="memory")
    op.drop_column("items", "fact_key", schema="memory")
