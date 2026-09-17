"""The domain condition is a fence, and "shared" is one side of it - not a gate.

Both index adapters used to skip the domain condition entirely when the caller
asked for "shared", which is also the default on ``SearchQuery``. The result was
that the least specific query read the most: every domain the tenant owns.

These tests are written against the in-memory adapter because it is the one the
unit suite can run, and its docstring promises the SAME semantics as Qdrant. The
Qdrant side of the same rule is covered in
``tests/integration/test_qdrant_tenant_filter.py``.
"""

from __future__ import annotations

import uuid

import pytest

from dw_knowledge.adapters.memory_index import InMemoryVectorIndexAdapter
from dw_knowledge.contracts import SHARED_DOMAIN
from dw_knowledge.ports import IndexableChunk, TrustedSearchFilter

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
WS = uuid.uuid4()
VECTOR = (1.0, 0.0, 0.0)


def _chunk(domain: str) -> IndexableChunk:
    return IndexableChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        tenant_id=TENANT,
        workspace_id=WS,
        domain=domain,
        content=f"nội dung thuộc {domain}",
        classification="internal",
        source_version="1",
        index_version="v1",
        provenance_hash="0" * 64,
        acl_principals=("tenant:*",),
        vector=VECTOR,
    )


def _filter(domain: str) -> TrustedSearchFilter:
    return TrustedSearchFilter(
        tenant_id=TENANT,
        workspace_id=WS,
        domain=domain,
        allowed_classifications=("internal",),
        acl_principals=("tenant:*",),
    )


async def _domains_visible_to(index: InMemoryVectorIndexAdapter, domain: str) -> set[str]:
    hits = await index.search(VECTOR, _filter(domain), 50)
    return {hit.content.rsplit(" ", 1)[-1] for hit in hits}


async def test_a_shared_search_does_not_read_every_domain() -> None:
    """The regression: "shared" is a domain, not a wildcard.

    A file a user attached to one CRM record lands on its own domain. If the
    default query ignored the domain condition, every lane in the tenant would
    retrieve that file as evidence.
    """
    index = InMemoryVectorIndexAdapter()
    await index.upsert([_chunk(SHARED_DOMAIN), _chunk("crm_attachment"), _chunk("legal")])

    assert await _domains_visible_to(index, SHARED_DOMAIN) == {SHARED_DOMAIN}


async def test_a_named_domain_reads_itself_and_the_shared_pool() -> None:
    index = InMemoryVectorIndexAdapter()
    await index.upsert([_chunk(SHARED_DOMAIN), _chunk("crm_attachment"), _chunk("legal")])

    assert await _domains_visible_to(index, "legal") == {"legal", SHARED_DOMAIN}


async def test_one_domain_never_reads_another() -> None:
    index = InMemoryVectorIndexAdapter()
    await index.upsert([_chunk("crm_attachment"), _chunk("legal")])

    assert await _domains_visible_to(index, "legal") == {"legal"}
    assert await _domains_visible_to(index, "crm_attachment") == {"crm_attachment"}
