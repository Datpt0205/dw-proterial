"""Retrieval evaluation: recall@k, nDCG@k and MRR over documents, and latency.

A query and the documents that should answer it. A search returns chunks, and
several chunks of one document are one answer, so each document counts once, at
its best rank (BEIR's convention). Without that a document split in three filled
three of five places and scored as three answers.

`search` is a callable, so the same labelled set runs in CI's eval smoke against
the in-memory index and against a real Qdrant in an integration test
(`dw_knowledge/tests/integration/test_retrieval_eval_qdrant.py`). A report
passes only against a floor (`RetrievalFloor`); one with no cases does not.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from dw_knowledge.gateway import build_trusted_filter
from dw_knowledge.ports import EmbeddingPort, IndexableChunk, VectorIndexPort
from dw_platform.application.access_context import AccessContext


@dataclass(frozen=True)
class RetrievalCase:
    """One golden query and the document ids that are relevant to it."""

    query: str
    domain: str
    relevant_document_ids: frozenset[UUID]


@dataclass(frozen=True)
class CaseResult:
    query: str
    recall: float
    ndcg: float
    reciprocal_rank: float
    retrieved: tuple[UUID, ...]
    latency_ms: float


@dataclass(frozen=True)
class RetrievalFloor:
    """What a labelled set must reach at `top_k`; below any of it the eval fails."""

    top_k: int
    min_recall: float
    min_ndcg: float
    max_p95_ms: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> RetrievalFloor:
        return cls(
            top_k=int(data["top_k"]),
            min_recall=float(data["min_recall"]),
            min_ndcg=float(data["min_ndcg"]),
            max_p95_ms=float(data["max_p95_ms"]),
        )


@dataclass(frozen=True)
class RetrievalReport:
    cases: tuple[CaseResult, ...]
    top_k: int
    mean_recall: float
    mean_ndcg: float
    mrr: float
    p95_ms: float

    def shortfalls(self, floor: RetrievalFloor) -> list[str]:
        """Each way this report falls short of `floor`; empty when it passes."""
        if not self.cases:
            return ["no cases were run"]
        found = []
        if self.mean_recall < floor.min_recall:
            found.append(f"recall@{self.top_k} {self.mean_recall:.3f} < {floor.min_recall}")
        if self.mean_ndcg < floor.min_ndcg:
            found.append(f"nDCG@{self.top_k} {self.mean_ndcg:.3f} < {floor.min_ndcg}")
        if self.p95_ms > floor.max_p95_ms:
            found.append(f"p95 {self.p95_ms:.1f} ms > {floor.max_p95_ms} ms")
        return found


# A search returns the ranked document id of each chunk it found for a
# (query, domain, top_k); one document may appear more than once.
SearchFn = Callable[[str, str, int], Awaitable[Sequence[UUID]]]


def _distinct(retrieved: Sequence[UUID], top_k: int) -> tuple[UUID, ...]:
    """Each document once, at its first (best) rank, cut to `top_k`."""
    return tuple(dict.fromkeys(retrieved))[:top_k]


def _metrics(
    retrieved: Sequence[UUID], relevant: frozenset[UUID], top_k: int
) -> tuple[float, float, float]:
    """Recall, binary nDCG and reciprocal rank of documents already counted once."""
    if not relevant:
        return (0.0, 0.0, 0.0)
    recall = len(set(retrieved) & relevant) / len(relevant)
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(retrieved, start=1)
        if doc_id in relevant
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), top_k) + 1))
    rr = next(
        (1.0 / rank for rank, doc_id in enumerate(retrieved, start=1) if doc_id in relevant), 0.0
    )
    return (recall, dcg / ideal if ideal else 0.0, rr)


def _p95(values: Sequence[float]) -> float:
    """Nearest-rank 95th percentile: a value that was actually observed."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


async def evaluate_retrieval(
    search: SearchFn, cases: Sequence[RetrievalCase], *, top_k: int = 5
) -> RetrievalReport:
    """Run each golden case through ``search``, timing each, and aggregate."""
    results: list[CaseResult] = []
    for case in cases:
        started = time.perf_counter()
        found = await search(case.query, case.domain, top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved = _distinct(found, top_k)
        recall, ndcg, rr = _metrics(retrieved, case.relevant_document_ids, top_k)
        results.append(
            CaseResult(
                query=case.query,
                recall=recall,
                ndcg=ndcg,
                reciprocal_rank=rr,
                retrieved=retrieved,
                latency_ms=latency_ms,
            )
        )
    n = len(results) or 1
    return RetrievalReport(
        cases=tuple(results),
        top_k=top_k,
        mean_recall=sum(r.recall for r in results) / n,
        mean_ndcg=sum(r.ndcg for r in results) / n,
        mrr=sum(r.reciprocal_rank for r in results) / n,
        p95_ms=_p95([r.latency_ms for r in results]),
    )


# ---------------------------------------------------------------- labelled --
# A labelled set names documents by key; their ids are derived from it, so the
# same set gives the same ids on every run and against every index.
_LABELLED = uuid.UUID("5f1d7a52-45c1-4f0e-9a4b-9f8b1a7e2d45")


def labelled_document_id(key: str) -> UUID:
    return uuid.uuid5(_LABELLED, key)


@dataclass(frozen=True)
class LabelledDocument:
    key: str
    tenant_id: UUID
    workspace_id: UUID
    domain: str
    chunks: tuple[str, ...]


@dataclass(frozen=True)
class LabelledSet:
    """Documents, and queries labelled with the documents that answer them.

    Read from an eval fixture (`evals/fixtures/cases/pf_retrieval.json`).
    """

    documents: tuple[LabelledDocument, ...]
    cases: tuple[RetrievalCase, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> LabelledSet:
        tenants = {
            name: (UUID(ids["tenant_id"]), UUID(ids["workspace_id"]))
            for name, ids in data["tenants"].items()
        }
        documents = tuple(
            LabelledDocument(
                key=doc["key"],
                tenant_id=tenants[doc["tenant"]][0],
                workspace_id=tenants[doc["tenant"]][1],
                domain=doc.get("domain", "shared"),
                chunks=tuple(doc["chunks"]),
            )
            for doc in data["documents"]
        )
        cases = tuple(
            RetrievalCase(
                query=query["text"],
                domain=query.get("domain", "shared"),
                relevant_document_ids=frozenset(labelled_document_id(k) for k in query["relevant"]),
            )
            for query in data["queries"]
        )
        return cls(documents=documents, cases=cases)

    async def load_into(
        self,
        index: VectorIndexPort,
        embeddings: EmbeddingPort,
        *,
        tenant_id: UUID | None = None,
    ) -> None:
        """Index every document (or only one tenant's) as the gateway would."""
        for doc in self.documents:
            if tenant_id is not None and doc.tenant_id != tenant_id:
                continue
            document_id = labelled_document_id(doc.key)
            vectors = await embeddings.embed(list(doc.chunks))
            await index.upsert(
                [
                    IndexableChunk(
                        chunk_id=uuid.uuid5(document_id, str(seq)),
                        document_id=document_id,
                        tenant_id=doc.tenant_id,
                        workspace_id=doc.workspace_id,
                        domain=doc.domain,
                        content=text,
                        classification="internal",
                        source_version="1",
                        index_version="eval",
                        provenance_hash="0" * 64,
                        acl_principals=("tenant:*",),
                        vector=tuple(vector),
                        seq=seq,
                    )
                    for seq, (text, vector) in enumerate(zip(doc.chunks, vectors, strict=True))
                ]
            )


def index_search(
    index: VectorIndexPort, embeddings: EmbeddingPort, context: AccessContext
) -> SearchFn:
    """A `SearchFn` over `index` under the filter the gateway builds for `context`.

    Asks for more chunks than documents wanted, as the gateway does for its
    reranker, so a document split in several chunks does not crowd the others
    out before they are counted once.
    """

    async def search(query: str, domain: str, top_k: int) -> list[UUID]:
        [vector] = await embeddings.embed([query])
        hits = await index.search(
            vector, build_trusted_filter(context, domain), top_k * 4, text=query
        )
        return [hit.document_id for hit in hits]

    return search
