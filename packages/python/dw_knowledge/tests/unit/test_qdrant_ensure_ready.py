"""What `ensure_ready` may and may not do to a collection that already exists.

Three behaviours are load-bearing enough to pin down without infrastructure: it
must never drop a populated collection because a config value disagrees with it,
it must refuse a collection another embedding model filled, and it must
reconcile payload indexes on collections it did not just create.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from qdrant_client import AsyncQdrantClient, models

from dw_kernel.errors import InfrastructureError
from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter

pytestmark = pytest.mark.unit

COLLECTION = "dw_knowledge_test"
MODEL = "text-embedding-3-large"
SERVED = f"{COLLECTION}__text_embedding_3_large__1"


class FakeQdrantClient:
    """Records what the adapter asked for, answers what the test set up.

    `collections` maps a collection to its width; `aliases` maps an alias to
    the collection it names, as Qdrant's `get_aliases` reports them.
    """

    def __init__(
        self, *, collections: dict[str, int] | None = None, aliases: dict[str, str] | None = None
    ) -> None:
        self.collections = dict(collections or {})
        self.aliases = dict(aliases or {})
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.indexed: dict[str, Any] = {}

    async def get_aliases(self) -> Any:
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=alias, collection_name=name)
                for alias, name in self.aliases.items()
            ]
        )

    async def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections or collection_name in self.aliases

    async def get_collection(self, collection_name: str) -> Any:
        size = self.collections[self.aliases.get(collection_name, collection_name)]
        vectors = SimpleNamespace(size=size)
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))

    async def create_collection(self, collection_name: str, **kwargs: Any) -> None:
        self.created.append(collection_name)
        self.collections[collection_name] = kwargs["vectors_config"].size

    async def delete_collection(self, collection_name: str) -> None:
        self.deleted.append(collection_name)

    async def update_collection_aliases(self, *, change_aliases_operations: list[Any]) -> None:
        for operation in change_aliases_operations:
            alias = operation.create_alias
            self.aliases[alias.alias_name] = alias.collection_name

    async def create_payload_index(
        self, collection_name: str, *, field_name: str, field_schema: Any
    ) -> None:
        self.indexed[field_name] = field_schema


def _adapter(client: FakeQdrantClient) -> QdrantVectorIndexAdapter:
    return QdrantVectorIndexAdapter(client=cast(AsyncQdrantClient, client), collection=COLLECTION)


async def test_a_dimension_change_raises_instead_of_dropping_the_collection() -> None:
    """Changing the embedding model must not delete every tenant's vectors.

    The old behaviour recreated the collection whenever the width disagreed. In
    a rolling deploy, one process reading 1024 and another reading 3072 delete
    each other's collection in a loop - and the trigger is a config value, not
    an operator decision.
    """
    client = FakeQdrantClient(collections={SERVED: 1024}, aliases={COLLECTION: SERVED})

    with pytest.raises(InfrastructureError) as raised:
        await _adapter(client).ensure_ready(3072, MODEL)

    assert client.deleted == []
    assert raised.value.details["collection_dimension"] == 1024
    assert raised.value.details["embedding_dimension"] == 3072


async def test_another_models_collection_is_refused_at_the_same_width() -> None:
    """bge-m3 and another 1024-wide model pass a width check and mean nothing
    to each other: searching one's vectors with the other's query is noise
    that fails no check, so the collection's name is."""
    other = f"{COLLECTION}__bge_m3__1"
    client = FakeQdrantClient(collections={other: 3072}, aliases={COLLECTION: other})

    with pytest.raises(InfrastructureError) as raised:
        await _adapter(client).ensure_ready(3072, MODEL)

    assert raised.value.details["served"] == other
    assert client.created == [] and client.deleted == []


async def test_payload_indexes_are_reconciled_on_an_existing_collection() -> None:
    """A key added to the adapter later must still get an index.

    The index calls used to sit after an early return, so they only ever ran on
    a freshly created collection. On a live one the filter stayed unindexed,
    which is a full scan of the tenant's points on every query. The BM25 text
    index is such a later key: Qdrant builds it from the stored chunk text.
    """
    client = FakeQdrantClient(collections={SERVED: 3072}, aliases={COLLECTION: SERVED})

    await _adapter(client).ensure_ready(3072, MODEL)

    assert client.created == []
    assert {"tenant_id", "workspace_id", "account_id", "scope", "is_deleted"} <= set(client.indexed)
    assert client.indexed["tenant_id"].is_tenant is True
    text = client.indexed["content"]
    assert isinstance(text, models.TextIndexParams) and text.scoring is True
    # Measured on 1.20.1: `multilingual` drops digit-only tokens, which are
    # what a PO number is made of.
    assert text.tokenizer == models.TokenizerType.WORD


async def test_a_missing_collection_is_created_under_its_model_and_aliased() -> None:
    client = FakeQdrantClient()

    await _adapter(client).ensure_ready(3072, MODEL)

    assert client.created == [SERVED]
    assert client.aliases == {COLLECTION: SERVED}
    assert "tenant_id" in client.indexed


async def test_a_collection_made_before_aliases_is_still_served_by_width() -> None:
    """A collection holding the alias's own name records no model. It keeps
    being served while its width matches; a rebuild moves it behind an alias."""
    client = FakeQdrantClient(collections={COLLECTION: 3072})

    await _adapter(client).ensure_ready(3072, MODEL)

    assert client.created == [] and client.aliases == {}
    assert "content" in client.indexed
