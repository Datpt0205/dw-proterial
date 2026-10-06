"""Cross-encoder reranking through a Cohere-style ``POST {base_url}/rerank`` API.

Implements ``RerankPort``. The dialect is the one hosted rerank APIs share
(Cohere, Jina, the FPT Cloud AI Marketplace): ``{"model", "query", "documents",
"top_n"}`` in, ``{"results": [{"index", "relevance_score"}, ...]}`` out. The
model runs at the provider; nothing is hosted here.

Measured against ``https://mkp-api.fptcloud.com/v1`` on 2026-10-06 with
``bge-reranker-v2-m3``: results come back sorted by score, ``document`` is null,
Vietnamese text ranks correctly when sent as UTF-8 JSON, and a body that names
``texts`` instead of ``documents`` is refused with a 400.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from dw_kernel.errors import InfrastructureError
from dw_knowledge.ports import RerankCandidate, RerankResult


@dataclass
class CohereCompatibleRerankAdapter:
    """Implements ``RerankPort`` against a hosted Cohere-dialect rerank endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 10.0

    async def rerank(
        self, query: str, candidates: Sequence[RerankCandidate], top_k: int
    ) -> list[RerankResult]:
        if not candidates or top_k <= 0:
            return []
        payload = {
            "model": self.model,
            "query": query,
            "documents": [c.text for c in candidates],
            "top_n": min(top_k, len(candidates)),
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            ) as client:
                response = await client.post("/rerank", json=payload)
                response.raise_for_status()
                rows = response.json()["results"]
                scored = [(int(row["index"]), float(row["relevance_score"])) for row in rows]
        except httpx.HTTPStatusError as exc:
            # The status says what went wrong; the body is the provider's and
            # may echo the request, so it never enters an error that gets logged.
            raise InfrastructureError(
                "rerank request failed",
                details={
                    "model": self.model,
                    "error": type(exc).__name__,
                    "status": exc.response.status_code,
                },
            ) from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise InfrastructureError(
                "rerank request failed",
                details={"model": self.model, "error": type(exc).__name__},
            ) from exc

        seen: set[int] = set()
        for index, _score in scored:
            # An index we never sent, or one sent twice, would attach a score to
            # the wrong chunk or cite one chunk twice. Neither is recoverable here.
            if not 0 <= index < len(candidates) or index in seen:
                raise InfrastructureError(
                    "rerank response named a document that was not sent",
                    details={"model": self.model, "index": index, "sent": len(candidates)},
                )
            seen.add(index)
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [
            RerankResult(id=candidates[index].id, score=score) for index, score in scored[:top_k]
        ]
