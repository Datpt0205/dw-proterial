"""Rebuild a Qdrant collection from the chunks stored in Postgres.

Documents and chunks in Postgres are the source of truth; vectors are derived.
Re-deriving them is what makes changing the embedding model possible at all.

It is also the restore path: Qdrant holds nothing Postgres cannot rebuild, so a
lost volume, a Qdrant upgrade across minors (a snapshot restores only into the
same or the next minor) and a new embedding model all end here.

QDRANT_COLLECTION names an alias (Sales ticket 45). This builds a NEW collection
named by the embedding model, `<alias>__<model>__<UTC stamp>`, while the alias
keeps serving the old one, then moves the alias in one atomic call. Readers
never see a half-built index and nothing restarts. The old collection is kept
and printed: until it is deleted, moving back is one call.

Run INSIDE the api container, which has the wired gateway and the gateway key:

    docker compose --env-file .env -f infra/compose/docker-compose.yml \
        exec -T api python - < scripts/knowledge_reindex.py

Move the alias back (or onto any build) without rebuilding:

    ... exec -T -e DW_REINDEX_SERVE=<collection> api python - < scripts/knowledge_reindex.py

A deployment from before aliases has a real collection under the alias's name.
The rebuild still runs; moving the alias then refuses, because Qdrant cannot
give an alias the name of a collection. Delete that collection and serve the
build with DW_REINDEX_SERVE.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa


async def main() -> None:
    from dw_api import bootstrap
    from dw_knowledge import tables
    from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter
    from dw_knowledge.ports import IndexableChunk

    container = bootstrap.build_container()
    gateway = container.knowledge_gateway
    assert gateway is not None, "knowledge gateway is not wired"
    live: Any = gateway.vector_index
    if not isinstance(live, QdrantVectorIndexAdapter):
        print("the gateway is not wired to Qdrant; there is nothing to rebuild", file=sys.stderr)
        raise SystemExit(2)

    serve_only = os.environ.get("DW_REINDEX_SERVE", "").strip()
    if serve_only:
        previous = await live.serve(serve_only)
        print(f"{live.collection} now serves {serve_only}; it served {previous}")
        return

    embeddings = gateway.embeddings
    # A new collection every run: writing into the one being served would mix
    # two vector spaces in one place, with no way to tell them apart afterwards.
    started = datetime.now(UTC)
    target = await live.create_build(
        embeddings.dimension, embeddings.model, started.strftime("%Y%m%d%H%M%S")
    )
    index = QdrantVectorIndexAdapter(client=live.client, collection=target)
    print(f"building {target} at dimension {embeddings.dimension}")

    async with gateway.session_factory() as session:
        tenants = (
            (await session.execute(sa.text("select distinct tenant_id from knowledge.documents")))
            .scalars()
            .all()
        )

    total = 0
    for tenant_id in tenants:
        async with gateway.session_factory() as session, session.begin():
            # SET LOCAL semantics: a pooled connection must carry no residue
            # into whoever borrows it next.
            await session.execute(
                sa.text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            documents = (
                await session.execute(
                    sa.select(tables.documents).where(
                        tables.documents.c.is_current,
                        tables.documents.c.status == "active",
                    )
                )
            ).all()
            print(f"tenant {tenant_id}: {len(documents)} documents")

            for document in documents:
                rows = (
                    await session.execute(
                        sa.select(tables.chunks)
                        .where(
                            tables.chunks.c.document_id == document.id,
                            tables.chunks.c.status == "active",
                        )
                        .order_by(tables.chunks.c.seq)
                    )
                ).all()
                if not rows:
                    print(" -", document.title, ": no chunks, skipped")
                    continue

                sections = [
                    str((row._mapping.get("metadata") or {}).get("section_path", "") or "")
                    for row in rows
                ]
                # The breadcrumb is part of what was embedded at ingest time;
                # embedding the bare content here would put these vectors in a
                # subtly different space from every future ingest.
                texts = [
                    f"[{section}]\n{row.content}" if section else row.content
                    for row, section in zip(rows, sections, strict=True)
                ]
                # One call: the adapter splits on the API's own ceilings, which
                # it knows and this script should not have to.
                vectors = await embeddings.embed(texts)

                await index.upsert(
                    [
                        IndexableChunk(
                            chunk_id=row.id,
                            document_id=document.id,
                            tenant_id=document.tenant_id,
                            workspace_id=document.workspace_id,
                            domain=document.domain,
                            content=row.content,
                            classification=document.classification,
                            source_version=document.source_version,
                            # From the row: it records the chunking that produced
                            # these chunks. Re-stamping it with today's constant
                            # would describe them as something they are not.
                            index_version=document.index_version or "v1",
                            provenance_hash=row.provenance_hash,
                            acl_principals=tuple(document.acl_principals or ("tenant:*",)),
                            vector=tuple(vector),
                            section_path=section,
                            seq=row.seq,
                            scope=document.scope,
                            extra_payload=tuple(
                                (key, str(value)) for key, value in (document.extra or {}).items()
                            ),
                        )
                        for row, vector, section in zip(rows, vectors, sections, strict=True)
                    ]
                )
                total += len(rows)
                print(" -", document.title, ":", len(rows), "chunks")

    seconds = (datetime.now(UTC) - started).total_seconds()
    print(f"TOTAL points written to {target}: {total} in {seconds:.0f} s")
    previous = await live.serve(target)
    print(f"{live.collection} now serves {target}; it served {previous}.")
    print("Delete the old collection once the new one has been watched long enough.")


asyncio.run(main())
