"""Which failed searches read as "nothing there" (audit 12).

Only an absent collection is an empty result: a fresh install asked before its
first upload. Every other failure raises, because an empty result reaches a
person as "no evidence" and a broken index must not.

The exceptions are the pinned client's own, shaped as it raised them against a
real Qdrant (unknown collection: `UnexpectedResponse` 404; server down:
`ResponseHandlingException`); `test_qdrant_tenant_filter.py` asks a real one.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import httpx
import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter
from dw_knowledge.ports import TrustedSearchFilter

pytestmark = pytest.mark.unit

_FILTER = TrustedSearchFilter(
    tenant_id=uuid.uuid4(),
    workspace_id=uuid.uuid4(),
    domain="shared",
    allowed_classifications=("internal",),
    acl_principals=("user:x",),
)


def _response(status: int, body: bytes) -> UnexpectedResponse:
    return UnexpectedResponse(
        status_code=status, reason_phrase="", content=body, headers=httpx.Headers()
    )


_MISSING = _response(404, b'{"status":{"error":"Not found: Collection `c` doesn\'t exist!"}}')


class FailingSearch:
    """`query_points` raises what the test set; `collection_exists` answers it."""

    def __init__(self, error: Exception, *, exists: bool | Exception) -> None:
        self._error = error
        self._exists = exists

    async def query_points(self, collection_name: str, **_: Any) -> Any:
        raise self._error

    async def collection_exists(self, collection_name: str) -> bool:
        if isinstance(self._exists, Exception):
            raise self._exists
        return self._exists


async def _search(client: FailingSearch) -> list[Any]:
    adapter = QdrantVectorIndexAdapter(client=cast(AsyncQdrantClient, client), collection="c")
    return list(await adapter.search([0.1, 0.2], _FILTER, top_k=5, text="q"))


async def test_an_absent_collection_is_an_empty_result() -> None:
    assert await _search(FailingSearch(_MISSING, exists=False)) == []


@pytest.mark.parametrize(
    ("error", "exists"),
    [
        # A 404 while the collection exists: a proxy or a wrong base path.
        (_MISSING, True),
        # A 404 Qdrant cannot confirm either.
        (_MISSING, _response(404, b"not found")),
        # Errors whose words say "404" or "not found" but are not one.
        (_response(400, b'{"status":{"error":"Wrong input: field `404` not found"}}'), False),
        (_response(500, b"Service internal error: 404 shards not found"), False),
        (ResponseHandlingException(Exception("not found: 404")), False),
        (TimeoutError("collection not found in time"), False),
    ],
    ids=["404-exists", "404-unconfirmed", "400-says-404", "500-says-404", "down", "timeout"],
)
async def test_every_other_failure_raises(error: Exception, exists: bool | Exception) -> None:
    with pytest.raises(InfrastructureError, match="vector search failed"):
        await _search(FailingSearch(error, exists=exists))
