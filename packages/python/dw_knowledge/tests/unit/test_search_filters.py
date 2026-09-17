"""Business-metadata filters may narrow a search and nothing else.

The whole point of letting a caller pass filters is that a bounded context can
ask for "this account only" without the gateway learning about accounts. The
risk is that the same mechanism becomes a way to name a security field, so
these tests pin both halves: the filters work, and they cannot reach a chunk
the trusted filter would have excluded.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from dw_knowledge.adapters.memory_index import InMemoryVectorIndexAdapter
from dw_knowledge.contracts import SEARCH_FILTER_KEYS, SearchQuery
from dw_knowledge.gateway import IngestDocumentCommand
from dw_knowledge.ingest_jobs import EnqueueIngestCommand
from dw_knowledge.ports import IndexableChunk, TrustedSearchFilter

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()
WS = uuid.uuid4()
ACCOUNT_A = str(uuid.uuid4())
ACCOUNT_B = str(uuid.uuid4())


def _chunk(
    *,
    account_id: str,
    tenant_id: uuid.UUID = TENANT,
    source_type: str = "web_page",
) -> IndexableChunk:
    return IndexableChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        tenant_id=tenant_id,
        workspace_id=WS,
        domain="shared",
        content="Doanh thu 2025 đạt 158.332 tỷ đồng",
        classification="internal",
        source_version="1",
        index_version="v1",
        provenance_hash="0" * 64,
        acl_principals=("tenant:*",),
        vector=(1.0, 0.0, 0.0),
        extra_payload=(("account_id", account_id), ("source_type", source_type)),
    )


def _trusted(tenant_id: uuid.UUID = TENANT) -> TrustedSearchFilter:
    return TrustedSearchFilter(
        tenant_id=tenant_id,
        workspace_id=WS,
        domain="shared",
        allowed_classifications=("internal",),
        acl_principals=("tenant:*",),
    )


# ------------------------------------------------------------------ contract --


def test_unknown_filter_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchQuery(text="doanh thu", filters=(("account_name", "FPT"),))


@pytest.mark.parametrize("key", ["tenant_id", "workspace_id", "acl_principals", "classification"])
def test_security_fields_cannot_be_used_as_filters(key: str) -> None:
    """A caller must not be able to name a field the gateway enforces."""
    assert key not in SEARCH_FILTER_KEYS
    with pytest.raises(ValidationError):
        SearchQuery(text="doanh thu", filters=((key, "anything"),))


@pytest.mark.parametrize("key", ["tenant_id", "acl_principals", "is_deleted"])
def test_ingest_metadata_cannot_name_a_payload_security_field(key: str) -> None:
    """Ingest metadata becomes vector payload, so it needs the same closed list."""
    with pytest.raises(ValidationError):
        IngestDocumentCommand(title="t", content="c", extra=((key, "anything"),))
    with pytest.raises(ValidationError):
        EnqueueIngestCommand(title="t", filename="f.pdf", extra=((key, "anything"),))


# -------------------------------------------------------------------- search --


async def test_filter_narrows_to_one_account() -> None:
    index = InMemoryVectorIndexAdapter()
    await index.upsert([_chunk(account_id=ACCOUNT_A), _chunk(account_id=ACCOUNT_B)])

    unfiltered = await index.search((1.0, 0.0, 0.0), _trusted(), 10)
    filtered = await index.search((1.0, 0.0, 0.0), _trusted(), 10, (("account_id", ACCOUNT_A),))

    assert len(unfiltered) == 2
    assert len(filtered) == 1


async def test_filters_combine_as_and_not_or() -> None:
    index = InMemoryVectorIndexAdapter()
    await index.upsert(
        [
            _chunk(account_id=ACCOUNT_A, source_type="web_page"),
            _chunk(account_id=ACCOUNT_A, source_type="news_article"),
        ]
    )
    hits = await index.search(
        (1.0, 0.0, 0.0),
        _trusted(),
        10,
        (("account_id", ACCOUNT_A), ("source_type", "news_article")),
    )
    assert len(hits) == 1


async def test_filter_cannot_reach_another_tenant() -> None:
    """The failure this guards: a filter that matches, on a chunk you may not see."""
    index = InMemoryVectorIndexAdapter()
    await index.upsert([_chunk(account_id=ACCOUNT_A, tenant_id=OTHER_TENANT)])

    hits = await index.search((1.0, 0.0, 0.0), _trusted(), 10, (("account_id", ACCOUNT_A),))

    assert hits == []


async def test_filtering_never_returns_more_than_not_filtering() -> None:
    index = InMemoryVectorIndexAdapter()
    await index.upsert(
        [
            _chunk(account_id=ACCOUNT_A),
            _chunk(account_id=ACCOUNT_B),
            _chunk(account_id=ACCOUNT_A, tenant_id=OTHER_TENANT),
        ]
    )
    baseline = await index.search((1.0, 0.0, 0.0), _trusted(), 10)
    for key, value in (("account_id", ACCOUNT_A), ("source_type", "web_page")):
        narrowed = await index.search((1.0, 0.0, 0.0), _trusted(), 10, ((key, value),))
        assert len(narrowed) <= len(baseline)
        assert {h.chunk_id for h in narrowed} <= {h.chunk_id for h in baseline}


async def test_chunk_without_metadata_is_excluded_by_a_filter() -> None:
    """Absent metadata must not read as "matches anything"."""
    index = InMemoryVectorIndexAdapter()
    plain = _chunk(account_id=ACCOUNT_A)
    index_chunk = IndexableChunk(**{**plain.__dict__, "extra_payload": ()})
    await index.upsert([index_chunk])

    hits = await index.search((1.0, 0.0, 0.0), _trusted(), 10, (("account_id", ACCOUNT_A),))

    assert hits == []
