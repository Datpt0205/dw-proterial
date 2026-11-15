"""The one Query API call a hybrid search makes, pinned without a server.

What must hold whatever Qdrant does with it: every prefetch carries the whole
trusted filter (a leg without it would rank every tenant's points, and the
fusion could only filter what it was handed), the BM25 statistics are scoped to
what the trusted filter admits and to no business narrowing, and the fusion is
reciprocal rank at the measured k. `test_qdrant_hybrid.py` asks a real Qdrant.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from qdrant_client import AsyncQdrantClient, models

from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter
from dw_knowledge.hybrid import RRF_K
from dw_knowledge.ports import TrustedSearchFilter

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()
DOCUMENT = uuid.uuid4()
_FILTER = TrustedSearchFilter(
    tenant_id=TENANT,
    workspace_id=WORKSPACE,
    domain="sales",
    allowed_classifications=("internal",),
    acl_principals=("user:x", "tenant:*"),
)


class CapturingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def query_points(self, collection_name: str, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])


async def _query(**narrowing: Any) -> dict[str, Any]:
    client = CapturingClient()
    adapter = QdrantVectorIndexAdapter(client=cast(AsyncQdrantClient, client), collection="c")
    await adapter.search([0.1, 0.2], _FILTER, 8, text="PO-2026-0457", **narrowing)
    [call] = client.calls
    return call


def _tenant_conditions(flt: models.Filter) -> set[tuple[str, str]]:
    """(key, value) of every MatchValue condition inside the filter's `should`."""
    found: set[tuple[str, str]] = set()
    for clause in flt.should or []:
        conditions = clause.must if isinstance(clause, models.Filter) else [clause]
        for condition in conditions or []:
            if isinstance(condition, models.FieldCondition) and isinstance(
                condition.match, models.MatchValue
            ):
                found.add((condition.key, str(condition.match.value)))
    return found


async def test_every_prefetch_carries_the_trusted_filter() -> None:
    call = await _query()
    dense, lexical = call["prefetch"]
    for leg in (dense, lexical):
        assert leg.filter == call["query_filter"]
        assert {("tenant_id", str(TENANT)), ("workspace_id", str(WORKSPACE))} <= (
            _tenant_conditions(leg.filter)
        )
    assert isinstance(lexical.query, models.TextQuery) and lexical.using == "content"
    assert lexical.query.text == "PO-2026-0457"
    assert call["query"] == models.RrfQuery(rrf=models.Rrf(k=RRF_K))


async def test_bm25_statistics_are_the_callers_own_readable_corpus() -> None:
    """Scoped to the trusted filter, so another tenant's words weigh nothing,
    and not to the business narrowing, so asking about one document does not
    make every word in it rare."""
    call = await _query(extra_filters=(("account_id", "acc-1"),), document_ids=(DOCUMENT,))
    _, lexical = call["prefetch"]
    corpus = lexical.params.idf.corpus
    assert corpus.should == call["query_filter"].should
    assert corpus.must_not == call["query_filter"].must_not
    narrowed_keys = {c.key for c in call["query_filter"].must}
    corpus_keys = {c.key for c in corpus.must}
    assert {"account_id", "source_document_id"} <= narrowed_keys
    assert corpus_keys == narrowed_keys - {"account_id", "source_document_id"}
    assert {"classification", "acl_principals", "domain"} <= corpus_keys
