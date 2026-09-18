"""Provenance stops being a shape and becomes a chain the database enforces.

Revision ID: c490124d690a
Revises: 5eda1d6108cc
Create Date: 2026-09-18

"Why did the AI conclude that" is the question an enterprise buyer asks first,
and until now the honest answer was that nothing could be traced. A memory item
carried `provenance_refs` — a JSONB array of `EvidenceRef` — and every link in
that chain was broken:

- **The column accepted nothing.** `provenance_refs jsonb DEFAULT '[]' NOT NULL`
  means an empty array satisfies it, and `memory.items` had no CHECK constraint
  at all. Only a dataclass in the service refused empty provenance, and a service
  is not what a second writer, a repair script or a bug goes through.

- **`created_by_run_id` named a run nobody could confirm.** `NOT NULL`, no
  foreign key, across schemas. A memory could claim a run that never existed.

- **`evidence_id` pointed at nothing at all.** It was minted fresh per retrieval
  hit and persisted nowhere but inside that JSONB. There was no `evidence` table.
  Given a stored memory you could read a UUID and had no way to resolve it, so
  the one thing provenance exists for could not be done.

So: `knowledge.evidence` holds the evidence that actually justified a stored
memory — not everything ever retrieved, which is a search log and a different
table — and `memory.item_evidence` ties a memory to it with real foreign keys.
The JSONB stays as the denormalised copy of what the model was shown; the join
is what makes the reference resolvable, and both are written in one transaction.

Deletes are RESTRICT on the way down. A document and a chunk are soft-deleted
here (`deleted_at`), so this blocks nothing anyone does today; what it stops is a
hard delete quietly cutting a stored conclusion loose from its reason.

RLS is declared explicitly on both new tables. Grants are not: `0001_platform_grants`
sets default privileges for these schemas, so a table created by the migrator is
readable by `dw_app` without one — which is the property `test_privileges.py`
pins. RLS has no such default, and a tenant table without it is a cross-tenant
read waiting to happen.
"""

from __future__ import annotations

from alembic import op

revision = "c490124d690a"
down_revision = "5eda1d6108cc"
branch_labels = None
depends_on = None

_TENANT_PREDICATE = (
    "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
)

_UPGRADE = (
    # ---- the evidence a stored memory rests on -----------------------------
    """
    CREATE TABLE knowledge.evidence (
        evidence_id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        source_document_id uuid NOT NULL,
        chunk_id uuid,
        source_version text NOT NULL,
        page integer,
        start_offset integer,
        end_offset integer,
        quote text,
        relevance_score double precision NOT NULL,
        classification text NOT NULL,
        provenance_hash text NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_evidence PRIMARY KEY (evidence_id),
        CONSTRAINT ck_evidence_provenance_hash
            CHECK (provenance_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_evidence_relevance_score
            CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
        CONSTRAINT fk_evidence_source_document_id_documents
            FOREIGN KEY (source_document_id) REFERENCES knowledge.documents (id)
            ON DELETE RESTRICT,
        CONSTRAINT fk_evidence_chunk_id_chunks
            FOREIGN KEY (chunk_id) REFERENCES knowledge.chunks (id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX ix_evidence_source_document_id ON knowledge.evidence (source_document_id)",
    "CREATE INDEX ix_evidence_chunk_id ON knowledge.evidence (chunk_id)",
    "ALTER TABLE knowledge.evidence ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE knowledge.evidence FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_evidence ON knowledge.evidence"
    f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}",
    # ---- which memory rests on which evidence ------------------------------
    """
    CREATE TABLE memory.item_evidence (
        memory_id uuid NOT NULL,
        evidence_id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        CONSTRAINT pk_item_evidence PRIMARY KEY (memory_id, evidence_id),
        CONSTRAINT fk_item_evidence_memory_id_items
            FOREIGN KEY (memory_id) REFERENCES memory.items (memory_id) ON DELETE CASCADE,
        CONSTRAINT fk_item_evidence_evidence_id_evidence
            FOREIGN KEY (evidence_id) REFERENCES knowledge.evidence (evidence_id)
            ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX ix_item_evidence_evidence_id ON memory.item_evidence (evidence_id)",
    "ALTER TABLE memory.item_evidence ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE memory.item_evidence FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_item_evidence ON memory.item_evidence"
    f" USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}",
    # ---- what the item itself must carry ------------------------------------
    "ALTER TABLE memory.items ADD CONSTRAINT ck_items_provenance_refs"
    " CHECK (jsonb_array_length(provenance_refs) > 0)",
    "CREATE INDEX ix_items_created_by_run_id ON memory.items (created_by_run_id)",
    "ALTER TABLE memory.items ADD CONSTRAINT fk_items_created_by_run_id_worker_runs"
    " FOREIGN KEY (created_by_run_id) REFERENCES platform.worker_runs (id) ON DELETE RESTRICT",
)

_DOWNGRADE = (
    "ALTER TABLE memory.items DROP CONSTRAINT fk_items_created_by_run_id_worker_runs",
    "DROP INDEX memory.ix_items_created_by_run_id",
    "ALTER TABLE memory.items DROP CONSTRAINT ck_items_provenance_refs",
    "DROP TABLE memory.item_evidence",
    "DROP TABLE knowledge.evidence",
)


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
