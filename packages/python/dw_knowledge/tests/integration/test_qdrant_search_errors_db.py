"""Integration: a real Qdrant's failures, as the search reads them (audit 12).

An absent collection is the one failure that means "nothing there"; a refused
query on a collection that exists raises, whatever its words say.
"""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import AsyncQdrantClient
from runtime_harness import RuntimeUrls

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter
from dw_knowledge.ports import TrustedSearchFilter

pytestmark = pytest.mark.integration

_FILTER = TrustedSearchFilter(
    tenant_id=uuid.uuid4(),
    workspace_id=uuid.uuid4(),
    domain="shared",
    allowed_classifications=("internal",),
    acl_principals=("user:x",),
)


async def test_an_absent_collection_is_empty_and_a_refused_query_raises(
    urls: RuntimeUrls,
) -> None:
    # Creating a collection took ~7 s on a Docker Desktop volume (2026-11-13),
    # past the client's 5 s default; this test is about search, not that.
    qdrant = AsyncQdrantClient(url=urls.qdrant_url, timeout=60)
    present = f"dw_knowledge_test_{uuid.uuid4().hex[:8]}"
    try:
        absent = QdrantVectorIndexAdapter(client=qdrant, collection=f"dw_absent_{present}")
        assert await absent.search([0.1, 0.2, 0.3], _FILTER, top_k=3) == []

        index = QdrantVectorIndexAdapter(client=qdrant, collection=present)
        await index.ensure_ready(3)
        # A vector of the wrong width: Qdrant answers 400, which is a broken
        # caller, not an empty corpus.
        with pytest.raises(InfrastructureError, match="vector search failed"):
            await index.search([0.1, 0.2], _FILTER, top_k=3)
    finally:
        await qdrant.delete_collection(present)
        await qdrant.close()
