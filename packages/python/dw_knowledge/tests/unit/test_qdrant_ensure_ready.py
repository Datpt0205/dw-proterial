"""What `ensure_ready` may and may not do to a collection that already exists.

Two behaviours are load-bearing enough to pin down without infrastructure: it
must never drop a populated collection because a config value disagrees with it,
and it must reconcile payload indexes on collections it did not just create.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from qdrant_client import AsyncQdrantClient

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter

pytestmark = pytest.mark.unit

COLLECTION = "dw_knowledge_test"


class FakeQdrantClient:
    """Records what the adapter asked for, answers what the test set up."""

    def __init__(self, *, exists: bool, size: int | None = None) -> None:
        self._exists = exists
        self._size = size
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.indexed: list[str] = []

    async def collection_exists(self, collection_name: str) -> bool:
        return self._exists

    async def get_collection(self, collection_name: str) -> Any:
        vectors = SimpleNamespace(size=self._size)
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))

    async def create_collection(self, collection_name: str, **_: Any) -> None:
        self.created.append(collection_name)

    async def delete_collection(self, collection_name: str) -> None:
        self.deleted.append(collection_name)

    async def create_payload_index(
        self, collection_name: str, *, field_name: str, field_schema: Any
    ) -> None:
        self.indexed.append(field_name)


def _adapter(client: FakeQdrantClient) -> QdrantVectorIndexAdapter:
    return QdrantVectorIndexAdapter(client=cast(AsyncQdrantClient, client), collection=COLLECTION)


async def test_a_dimension_change_raises_instead_of_dropping_the_collection() -> None:
    """Changing the embedding model must not delete every tenant's vectors.

    The old behaviour recreated the collection whenever the width disagreed. In
    a rolling deploy, one process reading 1024 and another reading 3072 delete
    each other's collection in a loop - and the trigger is a config value, not
    an operator decision.
    """
    client = FakeQdrantClient(exists=True, size=1024)

    with pytest.raises(InfrastructureError) as raised:
        await _adapter(client).ensure_ready(3072)

    assert client.deleted == []
    assert raised.value.details["collection_dimension"] == 1024
    assert raised.value.details["embedding_dimension"] == 3072


async def test_payload_indexes_are_reconciled_on_an_existing_collection() -> None:
    """A key added to the adapter later must still get an index.

    The index calls used to sit after an early return, so they only ever ran on
    a freshly created collection. On a live one the filter stayed unindexed,
    which is a full scan of the tenant's points on every query.
    """
    client = FakeQdrantClient(exists=True, size=3072)

    await _adapter(client).ensure_ready(3072)

    assert client.created == []
    assert {"tenant_id", "workspace_id", "account_id", "is_deleted"} <= set(client.indexed)


async def test_a_missing_collection_is_created_and_then_indexed() -> None:
    client = FakeQdrantClient(exists=False)

    await _adapter(client).ensure_ready(3072)

    assert client.created == [COLLECTION]
    assert "tenant_id" in client.indexed
