"""Integration: the examples index on a real Qdrant (Sales ticket 43).

Acceptance 1 at the port: a case one tenant decided is never a neighbour for
another tenant, nor for another workspace of the same tenant, nor for another
step, whatever the text. And the order the reading relies on: the subject's own
cases first, a held-out group never.

Needs only Qdrant (`make infra-up`); no database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from qdrant_client import AsyncQdrantClient
from runtime_harness import runtime_urls

from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter
from dw_knowledge.adapters.qdrant_examples import QdrantExampleIndex
from dw_knowledge.examples import ExampleGateway

pytestmark = pytest.mark.integration

TENANT_A = uuid.UUID(int=0xA0)
WORKSPACE_A = uuid.UUID(int=0xA1)
TENANT_B = uuid.UUID(int=0xB0)
WORKSPACE_B = uuid.UUID(int=0xB1)
STEP = "description_attributes"
DAY = datetime(2026, 11, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Case:
    example_id: uuid.UUID
    step: str
    subject: str | None
    group: str
    decided_at: datetime
    text: str


def case(n: int, text: str, *, subject: str = "C001", group: str | None = None) -> Case:
    return Case(uuid.UUID(int=n), STEP, subject, group or f"po-{n}", DAY + timedelta(hours=n), text)


@pytest.fixture
async def gateway() -> AsyncIterator[ExampleGateway]:
    client = AsyncQdrantClient(url=runtime_urls().qdrant_url, timeout=60)
    collection = f"dw_examples_test_{uuid.uuid4().hex[:8]}"
    index = QdrantExampleIndex(client=client, collection=collection)
    yield ExampleGateway(index=index, embeddings=HashEmbeddingAdapter())
    for name in await index._collections():
        await client.delete_collection(name)
    await client.close()


async def test_another_tenant_never_finds_the_case(gateway: ExampleGateway) -> None:
    text = "2C AWG24 BLK STR 305M REEL"
    await gateway.add([case(1, text)], tenant_id=TENANT_A, workspace_id=WORKSPACE_A)

    own = await gateway.similar(
        [text], tenant_id=TENANT_A, workspace_id=WORKSPACE_A, step=STEP, subject="C001", k=3
    )
    other = await gateway.similar(
        [text], tenant_id=TENANT_B, workspace_id=WORKSPACE_B, step=STEP, subject="C001", k=3
    )
    # The same tenant, another workspace, and another step: three fences.
    workspace = await gateway.similar(
        [text], tenant_id=TENANT_A, workspace_id=WORKSPACE_B, step=STEP, subject=None, k=3
    )
    step = await gateway.similar(
        [text], tenant_id=TENANT_A, workspace_id=WORKSPACE_A, step="po_body", subject=None, k=3
    )
    # Each condition on its own: another tenant naming this workspace's id.
    named = await gateway.similar(
        [text], tenant_id=TENANT_B, workspace_id=WORKSPACE_A, step=STEP, subject=None, k=3
    )
    assert own == [[uuid.UUID(int=1)]]
    assert other == [[]] and workspace == [[]] and step == [[]] and named == [[]]


async def test_the_subjects_cases_come_first_then_the_tenants(gateway: ExampleGateway) -> None:
    await gateway.add(
        [
            case(1, "2C AWG24 BLK STR 305M REEL", subject="C002"),
            case(2, "4C AWG22 GRY TC BRAID", subject="C001"),
            case(3, "7C 1.5SQ BRN STR", subject="C003"),
        ],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )
    [found] = await gateway.similar(
        ["2C AWG24 BLK STR 305M"],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        step=STEP,
        subject="C001",
        k=2,
    )
    # C001's one case first although another customer's reads closer.
    assert found[0] == uuid.UUID(int=2)
    assert found[1] == uuid.UUID(int=1)


async def test_an_excluded_group_is_never_found(gateway: ExampleGateway) -> None:
    text = "2C AWG24 BLK STR 305M REEL"
    await gateway.add(
        [case(1, text, group="po-held-out"), case(2, "4C AWG22 GRY")],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )
    [found] = await gateway.similar(
        [text],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        step=STEP,
        subject="C001",
        k=3,
        exclude_groups=["po-held-out"],
    )
    assert found == [uuid.UUID(int=2)]


async def test_known_cases_are_not_embedded_again_and_retention_drops_old_points(
    gateway: ExampleGateway,
) -> None:
    first = await gateway.add([case(1, "2C AWG24")], tenant_id=TENANT_A, workspace_id=WORKSPACE_A)
    again = await gateway.add(
        [case(1, "2C AWG24"), case(2, "4C AWG22")], tenant_id=TENANT_A, workspace_id=WORKSPACE_A
    )
    # Another tenant's case of the same id is not "known" to this one.
    assert (first, again) == (1, 1)

    await gateway.prune(DAY + timedelta(hours=1, minutes=30))
    [found] = await gateway.similar(
        ["2C AWG24"], tenant_id=TENANT_A, workspace_id=WORKSPACE_A, step=STEP, subject=None, k=3
    )
    assert found == [uuid.UUID(int=2)]

    await gateway.delete_by_tenant(TENANT_A)
    [gone] = await gateway.similar(
        ["4C AWG22"], tenant_id=TENANT_A, workspace_id=WORKSPACE_A, step=STEP, subject=None, k=3
    )
    assert gone == []
