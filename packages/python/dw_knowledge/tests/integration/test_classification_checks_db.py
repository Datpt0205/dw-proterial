"""Integration: knowledge's classification columns hold the clearance ladder.

`knowledge.documents`, `knowledge.ingest_jobs` and `knowledge.evidence` held
any text in `classification` (migration 0d8f03566652). Retrieval's clearance
filter matches that column, and memory labels a fact by ranking it, so a
`public` document is one no clearance retrieves and memory can only rank by a
guess (`failure-modes.md` #7).

Written as the migrator on purpose. It bypasses RLS and owns the tables, so
the only thing left between it and a bad row is the constraint under test.

The CHECKs are a second copy of the ladder the code owns
(`dw_knowledge.contracts._CLEARANCE_ALLOWS`, read as `CLASSIFICATIONS`). A copy
that cannot be avoided has to disagree loudly, so the last test reads the
constraints back from the catalog and compares them with the ladder.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from runtime_harness import RuntimeUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from dw_knowledge.contracts import _CLEARANCE_ALLOWS, CLASSIFICATIONS

pytestmark = pytest.mark.integration

TENANT = uuid.UUID(int=0xCF00)
WORKSPACE = uuid.UUID(int=0xCF01)


@pytest.fixture
async def migrator(urls: RuntimeUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(urls.migrator, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _document(conn: AsyncConnection, classification: str) -> uuid.UUID:
    document_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO knowledge.documents"
            " (id, tenant_id, workspace_id, title, source_uri, created_by, classification)"
            " VALUES (:id, :t, :w, 'Bien ban', 'file://bien-ban', :actor, :c)"
        ),
        {
            "id": document_id,
            "t": TENANT,
            "w": WORKSPACE,
            "actor": uuid.uuid4(),
            "c": classification,
        },
    )
    return document_id


async def _ingest_job(conn: AsyncConnection, classification: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO knowledge.ingest_jobs"
            " (id, tenant_id, workspace_id, created_by, title, filename, content_type,"
            "  storage_key, classification)"
            " VALUES (gen_random_uuid(), :t, :w, gen_random_uuid(), 'Bien ban', 'b.txt',"
            "  'text/plain', 'x/y/b.txt', :c)"
        ),
        {"t": TENANT, "w": WORKSPACE, "c": classification},
    )


async def _evidence(conn: AsyncConnection, classification: str) -> None:
    document_id = await _document(conn, "internal")
    await conn.execute(
        text(
            "INSERT INTO knowledge.evidence"
            " (evidence_id, tenant_id, workspace_id, source_document_id, source_version,"
            "  relevance_score, classification, provenance_hash)"
            " VALUES (gen_random_uuid(), :t, :w, :d, '1', 0.5, :c, :h)"
        ),
        {"t": TENANT, "w": WORKSPACE, "d": document_id, "c": classification, "h": "0" * 64},
    )


_WRITERS = {"documents": _document, "ingest_jobs": _ingest_job, "evidence": _evidence}


@pytest.mark.parametrize("table", sorted(_WRITERS))
async def test_a_classification_off_the_ladder_is_refused_by_name(
    migrator: AsyncEngine, table: str
) -> None:
    write = _WRITERS[table]
    # Every rung goes in first, so the refusal below is the column's and not
    # some other constraint this fixture happens to trip.
    async with migrator.begin() as conn:
        for classification in CLASSIFICATIONS:
            await write(conn, classification)

    with pytest.raises(sa.exc.IntegrityError, match=f"ck_{table}_classification"):
        async with migrator.begin() as conn:
            await write(conn, "public")


def _allowed(definition: str) -> set[str]:
    """The literals of `col = ANY (ARRAY['a'::text, ...])` as Postgres prints it."""
    return set(re.findall(r"'([^']*)'::text", definition))


async def test_the_classification_checks_hold_the_clearance_ladder(migrator: AsyncEngine) -> None:
    """A rung added to `_CLEARANCE_ALLOWS` and not to the CHECKs is a document
    the database refuses; one dropped from the ladder and left in the CHECKs is
    a row no clearance reads. Either goes red here."""
    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(c.oid) AS definition"
                    " FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace"
                    " WHERE n.nspname = 'knowledge' AND c.contype = 'c'"
                    "   AND c.conname LIKE '%\\_classification'"
                )
            )
        ).all()
    found = {row.conname: _allowed(row.definition) for row in rows}

    ladder = set(_CLEARANCE_ALLOWS)
    assert set(CLASSIFICATIONS) == ladder
    assert found == {f"ck_{table}_classification": ladder for table in _WRITERS}
