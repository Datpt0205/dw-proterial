"""The examples index's gateway and its in-memory adapter (Sales ticket 43).

The same fences the Qdrant test holds (`tests/integration/test_qdrant_examples.py`),
on the adapter the evals and unit tests run on, plus what only the gateway
decides: the scope a point is stamped with is the caller's, never the
example's; a search past its time budget raises (the reading then goes on
without examples); nothing is embedded twice.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter
from dw_knowledge.adapters.memory_examples import InMemoryExampleIndex
from dw_knowledge.examples import ExampleGateway

pytestmark = pytest.mark.unit

TENANT_A, WORKSPACE_A = uuid.UUID(int=0xA0), uuid.UUID(int=0xA1)
TENANT_B, WORKSPACE_B = uuid.UUID(int=0xB0), uuid.UUID(int=0xB1)
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


def gateway() -> tuple[ExampleGateway, InMemoryExampleIndex]:
    index = InMemoryExampleIndex()
    return ExampleGateway(index=index, embeddings=HashEmbeddingAdapter()), index


async def test_a_tenants_case_is_never_another_tenants_or_workspaces_or_steps() -> None:
    examples, _ = gateway()
    text = "2C AWG24 BLK STR 305M REEL"
    await examples.add([case(1, text)], tenant_id=TENANT_A, workspace_id=WORKSPACE_A)

    async def found(tenant: uuid.UUID, workspace: uuid.UUID, step: str = STEP) -> list[uuid.UUID]:
        [ids] = await examples.similar(
            [text], tenant_id=tenant, workspace_id=workspace, step=step, subject=None, k=3
        )
        return ids

    assert await found(TENANT_A, WORKSPACE_A) == [uuid.UUID(int=1)]
    assert await found(TENANT_B, WORKSPACE_B) == []
    # Each condition on its own: another tenant naming this workspace's id.
    assert await found(TENANT_B, WORKSPACE_A) == []
    assert await found(TENANT_A, WORKSPACE_B) == []
    assert await found(TENANT_A, WORKSPACE_A, "po_body_extraction") == []


async def test_a_point_carries_the_callers_scope_whatever_the_example_says() -> None:
    examples, index = gateway()
    await examples.add([case(1, "4C AWG22")], tenant_id=TENANT_B, workspace_id=WORKSPACE_B)
    point = index.points[uuid.UUID(int=1)]
    assert (point.tenant_id, point.workspace_id) == (TENANT_B, WORKSPACE_B)


async def test_the_subjects_cases_come_first_and_a_held_out_group_never() -> None:
    examples, _ = gateway()
    await examples.add(
        [
            case(1, "2C AWG24 BLK STR 305M REEL", subject="C002"),
            case(2, "4C AWG22 GRY TC BRAID", subject="C001"),
            case(3, "2C AWG24 BLK STR 305M REEL", subject="C001", group="po-held-out"),
        ],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
    )
    [found] = await examples.similar(
        ["2C AWG24 BLK STR 305M"],
        tenant_id=TENANT_A,
        workspace_id=WORKSPACE_A,
        step=STEP,
        subject="C001",
        k=2,
        exclude_groups=["po-held-out"],
    )
    assert found == [uuid.UUID(int=2), uuid.UUID(int=1)]


@dataclass
class _Counting:
    inner: HashEmbeddingAdapter = field(default_factory=HashEmbeddingAdapter)
    texts: list[str] = field(default_factory=list)

    @property
    def dimension(self) -> int:
        return self.inner.dimension

    @property
    def model(self) -> str:
        return self.inner.model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts += texts
        return await self.inner.embed(texts)


async def test_a_case_indexed_already_is_not_embedded_again() -> None:
    counting = _Counting()
    examples = ExampleGateway(index=InMemoryExampleIndex(), embeddings=counting)
    await examples.add([case(1, "2C AWG24")], tenant_id=TENANT_A, workspace_id=WORKSPACE_A)
    added = await examples.add(
        [case(1, "2C AWG24"), case(2, "4C AWG22")], tenant_id=TENANT_A, workspace_id=WORKSPACE_A
    )
    assert added == 1 and counting.texts == ["2C AWG24", "4C AWG22"]


@dataclass
class _Slow:
    @property
    def dimension(self) -> int:
        return 64

    @property
    def model(self) -> str:
        return "slow"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        await asyncio.sleep(5)
        return [[1.0] * 64 for _ in texts]


async def test_a_search_past_its_budget_raises_rather_than_waiting() -> None:
    examples = ExampleGateway(
        index=InMemoryExampleIndex(), embeddings=_Slow(), timeout_seconds=0.05
    )
    with pytest.raises(TimeoutError):
        await examples.similar(
            ["2C"], tenant_id=TENANT_A, workspace_id=WORKSPACE_A, step=STEP, subject=None, k=3
        )


async def test_retention_and_offboarding_drop_points() -> None:
    examples, index = gateway()
    await examples.add(
        [case(1, "2C AWG24"), case(2, "4C AWG22")], tenant_id=TENANT_A, workspace_id=WORKSPACE_A
    )
    await examples.add([case(3, "7C 1.5SQ")], tenant_id=TENANT_B, workspace_id=WORKSPACE_B)
    await examples.prune(DAY + timedelta(hours=1, minutes=30))
    assert set(index.points) == {uuid.UUID(int=2), uuid.UUID(int=3)}
    await examples.delete_by_tenant(TENANT_A)
    assert set(index.points) == {uuid.UUID(int=3)}
