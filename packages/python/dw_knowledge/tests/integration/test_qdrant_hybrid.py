"""Integration: hybrid retrieval on a real Qdrant (Sales ticket 45).

The labelled set of the eval smoke (`evals/fixtures/cases/pf_retrieval.json`),
here against Qdrant itself rather than the in-memory index that stands in for it
in CI: the same floor must hold, an exact PO number must be found where dense
search alone ranks it out of the top k (acceptance 1), and another tenant's
documents full of the same codes must neither appear nor move this tenant's
ranking. Also the alias: a rebuild serves a new collection in one move, and a
process embedding with another model refuses the old one.

Only Qdrant is needed: points are written through the adapter, as the gateway
writes them, and searched under the filter the gateway builds.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient, models
from runtime_harness import RuntimeUrls, runtime_urls

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter
from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter
from dw_knowledge.gateway import build_trusted_filter
from dw_knowledge.retrieval_eval import (
    LabelledDocument,
    LabelledSet,
    RetrievalFloor,
    evaluate_retrieval,
    index_search,
    labelled_document_id,
)
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
FIXTURE = json.loads((REPO / "evals/fixtures/cases/pf_retrieval.json").read_text("utf-8"))
FLOOR = RetrievalFloor.from_mapping(
    json.loads((REPO / "evals/expected/pf_retrieval.json").read_text("utf-8"))
)
LABELLED = LabelledSet.from_mapping(FIXTURE)
EMBEDDINGS = HashEmbeddingAdapter()


def _context(tenant: str) -> AccessContext:
    ids = FIXTURE["tenants"][tenant]
    return AccessContext(
        tenant_id=uuid.UUID(ids["tenant_id"]),
        workspace_id=uuid.UUID(ids["workspace_id"]),
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        plan_id="starter",
    )


OWN = _context("own")


@pytest.fixture
def qdrant_url() -> RuntimeUrls:
    return runtime_urls()


@pytest.fixture
async def client(qdrant_url: RuntimeUrls) -> AsyncIterator[AsyncQdrantClient]:
    # Creating a collection and its indexes takes seconds per call on a Docker
    # Desktop volume (measured 2.4-4.7 s on 1.13.4 and 1.20.1 alike).
    built = AsyncQdrantClient(url=qdrant_url.qdrant_url, timeout=60)
    yield built
    await built.close()


@pytest.fixture
async def index(client: AsyncQdrantClient) -> AsyncIterator[QdrantVectorIndexAdapter]:
    alias = f"dw_knowledge_test_{uuid.uuid4().hex[:8]}"
    adapter = QdrantVectorIndexAdapter(client=client, collection=alias)
    await adapter.ensure_ready(EMBEDDINGS.dimension, EMBEDDINGS.model)
    yield adapter
    for found in (await client.get_aliases()).aliases:
        if found.alias_name == alias:
            await client.delete_collection(found.collection_name)
    for name in [c.name for c in (await client.get_collections()).collections]:
        if name.startswith(f"{alias}__"):
            await client.delete_collection(name)


async def test_the_labelled_set_reaches_the_eval_floor_on_qdrant(
    index: QdrantVectorIndexAdapter,
) -> None:
    await LABELLED.load_into(index, EMBEDDINGS)

    report = await evaluate_retrieval(
        index_search(index, EMBEDDINGS, OWN), LABELLED.cases, top_k=FLOOR.top_k
    )

    print(
        f"qdrant hybrid: recall@{report.top_k}={report.mean_recall:.3f} "
        f"ndcg@{report.top_k}={report.mean_ndcg:.3f} mrr={report.mrr:.3f} "
        f"p95={report.p95_ms:.1f}ms"
    )
    assert report.shortfalls(FLOOR) == []


async def test_an_exact_po_number_is_found_where_dense_search_alone_misses_it(
    index: QdrantVectorIndexAdapter, client: AsyncQdrantClient
) -> None:
    """Acceptance 1. The order documents share every word of the question; only
    `PO-2026-0457` names the shipment note that answers it."""
    await LABELLED.load_into(index, EMBEDDINGS, tenant_id=OWN.tenant_id)
    query = "đơn hàng PO-2026-0457 của khách giao ngày nào"
    wanted = labelled_document_id("ship-0457")
    [vector] = await EMBEDDINGS.embed([query])
    k = FLOOR.top_k

    dense = await client.query_points(
        index.collection,
        query=vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value=str(OWN.tenant_id))
                )
            ]
        ),
        limit=k * 4,
        with_payload=True,
    )
    dense_documents = list(
        dict.fromkeys(uuid.UUID(str((p.payload or {})["source_document_id"])) for p in dense.points)
    )[:k]
    hybrid = await index.search(vector, build_trusted_filter(OWN, "shared"), k * 4, text=query)
    hybrid_documents = list(dict.fromkeys(hit.document_id for hit in hybrid))[:k]

    assert wanted not in dense_documents, "the premise: dense alone ranks it out of the top k"
    assert wanted in hybrid_documents


async def test_another_tenants_codes_are_never_retrieved(
    index: QdrantVectorIndexAdapter,
) -> None:
    """The other tenant's documents are worded like this tenant's questions and
    repeat its codes, so each leg would rank them first without its filter."""
    others = {
        labelled_document_id(doc.key)
        for doc in LABELLED.documents
        if doc.tenant_id != OWN.tenant_id
    }
    await LABELLED.load_into(index, EMBEDDINGS)

    for case in LABELLED.cases:
        [vector] = await EMBEDDINGS.embed([case.query])
        hits = await index.search(
            vector, build_trusted_filter(OWN, case.domain), 40, text=case.query
        )
        assert hits and not {hit.document_id for hit in hits} & others


async def test_another_tenants_words_do_not_move_the_ranking(
    index: QdrantVectorIndexAdapter,
) -> None:
    """By default Qdrant's BM25 statistics span the shard (measured on 1.20.1:
    a tenant's score fell from 2.95 to 1.76 when another tenant added 80
    points). Here the other tenant makes `ZQ-11` common: shard-wide, `RT-22`
    would become the rarer code and the two `RT-22` documents would outrank
    the `ZQ-11` one. Scoped to the caller's readable corpus, nothing moves.

    Lengths differ on purpose: Qdrant orders exactly equal scores by where the
    points sit, which any write to the collection can change (measured), and
    that order says nothing about anyone's text.
    """
    other = _context("other")
    own = [
        ("zq", "ZQ-11 khung nhôm"),
        ("rt-a", "RT-22 bản lề inox"),
        ("rt-b", "RT-22 tay nắm cửa nhôm sơn"),
    ]
    flood = [(f"flood-{n}", f"ZQ-11 ZQ-11 hàng mẫu số {n}") for n in range(60)]

    async def write(rows: list[tuple[str, str]], who: AccessContext) -> None:
        documents = tuple(
            LabelledDocument(
                key=key,
                tenant_id=who.tenant_id,
                workspace_id=who.workspace_id,
                domain="shared",
                chunks=(text,),
            )
            for key, text in rows
        )
        await LabelledSet(documents=documents, cases=()).load_into(index, EMBEDDINGS)

    async def ranking() -> list[uuid.UUID]:
        [vector] = await EMBEDDINGS.embed(["ZQ-11 RT-22"])
        hits = await index.search(
            vector, build_trusted_filter(OWN, "shared"), 10, text="ZQ-11 RT-22"
        )
        return [hit.document_id for hit in hits]

    await write(own, OWN)
    alone = await ranking()
    await write(flood, other)
    beside = await ranking()

    assert alone[0] == labelled_document_id("zq")
    assert beside == alone


async def test_a_rebuild_is_served_by_moving_the_alias(
    index: QdrantVectorIndexAdapter, client: AsyncQdrantClient
) -> None:
    """The restore path: Postgres refills a new collection while the old one
    serves, then the alias moves in one call. A process embedding with another
    model refuses what the alias serves rather than searching noise."""
    await LABELLED.load_into(index, EMBEDDINGS, tenant_id=OWN.tenant_id)
    first = f"{index.collection}__hash_64__1"

    build = await index.create_build(EMBEDDINGS.dimension, EMBEDDINGS.model, "2")
    rebuilt = QdrantVectorIndexAdapter(client=client, collection=build)
    only = next(doc for doc in LABELLED.documents if doc.key == "warranty")
    await LabelledSet(documents=(only,), cases=()).load_into(rebuilt, EMBEDDINGS)

    assert await index.serve(build) == first
    [vector] = await EMBEDDINGS.embed(["chính sách bảo hành khung nhôm"])
    hits = await index.search(vector, build_trusted_filter(OWN, "shared"), 20, text="bảo hành")
    assert {hit.document_id for hit in hits} == {labelled_document_id("warranty")}

    other_model = QdrantVectorIndexAdapter(client=client, collection=index.collection)
    with pytest.raises(InfrastructureError, match="different embedding model"):
        await other_model.ensure_ready(EMBEDDINGS.dimension, "bge-m3:567m")
