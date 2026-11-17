"""`sales.salesorder_pairs` and a customer's SalesOrder skill key (migration
711e8b760139, ticket 41) against a real database, as `dw_app` wherever
isolation is the question.

A worked pair is written by the worker in the transaction that settles the
example it was read from, read back under the workspace's RLS only, and never
changed by the application; it is removed only in its own workspace, withdrawn
by a person or dropped past the tenant's term (migration 985e4fa0cd4f). A
customer's SalesOrder skill is a rule version under
``sales_skill_salesorder_<code>``: the key's CHECK admits that family and
nothing else of its shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
    SqlOutboxRepository,
)
from dw_sales.adapters.persistence.catalog import SqlCatalogUnitOfWorkFactory
from dw_sales.application.salesorder_learning import WorkedPair
from dw_sales.application.skills import salesorder_key
from dw_sales.evals.graders import GIANG
from dw_sales.evals.salesorder_rules import Bench, load_cases, pair
from dw_sales.evals.salesorder_skill import kept_pair

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[5]
_CASES = load_cases(_REPO)


@pytest.fixture
def uow(app_sessions: async_sessionmaker[AsyncSession]) -> SqlCatalogUnitOfWorkFactory:
    return SqlCatalogUnitOfWorkFactory(
        app_sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        outbox=SqlOutboxRepository,
    )


async def _a_pair() -> WorkedPair:
    """A pair as the learning keeps it (read in memory, the normal way)."""
    pair_ = await kept_pair(Bench.of(_REPO, None, (GIANG,)), pair(_CASES, "SR02"))
    # No example row behind it in this database: the pair outlives one.
    return pair_.model_copy(
        update={"example_id": None, "added_at": datetime.now(UTC).replace(microsecond=0)}
    )


async def test_a_pair_is_kept_and_read_back_in_its_workspace_only(
    world: World, uow: SqlCatalogUnitOfWorkFactory
) -> None:
    kept = await _a_pair()
    async with uow(world.alpha) as work:
        await work.pairs.add(kept)
        await work.commit()
    async with uow(world.alpha) as work:
        (found,) = await work.pairs.for_customer("KHB", 20)
        assert await work.pairs.for_customer("KHA", 20) == []
    assert found == kept
    # Another workspace of the tenant, and another tenant, read none of it.
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.pairs.for_customer("KHB", 20) == []


async def test_a_pair_is_never_changed_and_an_unscoped_delete_removes_nothing(
    world: World,
    uow: SqlCatalogUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
) -> None:
    kept = await _a_pair()
    async with uow(world.alpha) as work:
        await work.pairs.add(kept)
        await work.commit()
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_sessions() as session, session.begin():
            await session.execute(
                sa.text("UPDATE sales.salesorder_pairs SET customer_code = 'KHA'")
            )
    # DELETE is granted (withdrawal, the term), and RLS leaves a connection
    # that never scoped itself nothing to delete.
    async with app_sessions() as session, session.begin():
        await session.execute(sa.text("DELETE FROM sales.salesorder_pairs"))
    async with migrator.connect() as conn:
        assert (
            await conn.scalar(
                sa.text("SELECT count(*) FROM sales.salesorder_pairs WHERE id = :id"),
                {"id": kept.pair_id},
            )
            == 1
        )


async def test_a_pair_is_withdrawn_and_pruned_in_its_own_workspace_only(
    world: World, uow: SqlCatalogUnitOfWorkFactory
) -> None:
    kept = await _a_pair()
    old = (await _a_pair()).model_copy(
        update={"pair_id": uuid.uuid4(), "added_at": datetime(2025, 1, 2, tzinfo=UTC)}
    )
    for scope, pair_ in ((world.alpha, kept), (world.alpha, old), (world.beta, old)):
        async with uow(scope) as work:
            await work.pairs.add(pair_.model_copy(update={"pair_id": uuid.uuid4()}))
            await work.commit()
    async with uow(world.alpha) as work:
        alphas = list(await work.pairs.for_customer("KHB", 20))
    async with uow(world.beta) as work:
        (betas,) = await work.pairs.for_customer("KHB", 20)
    # Another tenant's, and another workspace of the tenant, withdraw nothing.
    for other in (world.beta, world.alpha_other):
        async with uow(other) as work:
            assert await work.pairs.withdraw(alphas[0].pair_id) is None
            await work.commit()
    async with uow(world.alpha) as work:
        withdrawn = await work.pairs.withdraw(alphas[0].pair_id)
        await work.commit()
    assert withdrawn == alphas[0]
    # Past the term: alpha's old pair is dropped, beta's of the same age kept.
    async with uow(world.alpha) as work:
        assert await work.pairs.prune(datetime(2026, 1, 1, tzinfo=UTC)) == 1
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.pairs.for_customer("KHB", 20) == []
    async with uow(world.beta) as work:
        assert await work.pairs.for_customer("KHB", 20) == [betas]


async def test_a_pair_from_another_workspace_is_refused_by_rls(
    world: World, app_sessions: async_sessionmaker[AsyncSession], uow: SqlCatalogUnitOfWorkFactory
) -> None:
    """Written in alpha's transaction, a row naming beta's tenant is refused
    by the policy's WITH CHECK, whatever the adapter was handed."""
    kept = await _a_pair()
    async with uow(world.alpha) as work:
        await work.pairs.add(kept)
        await work.commit()
    async with uow(world.alpha) as work:
        with pytest.raises(DBAPIError):
            await work.pairs.session.execute(
                sa.text(
                    "INSERT INTO sales.salesorder_pairs (id, tenant_id, workspace_id,"
                    " customer_code, received_on, layout_ref, document, expected, added_by,"
                    " added_at) VALUES (:id, :tenant, :workspace, 'KHB', '2026-11-16', 'x',"
                    " '{}'::jsonb, '[{}]'::jsonb, :id, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": world.beta.tenant_id.value,
                    "workspace": world.beta.workspace_id.value,
                },
            )


async def test_the_rule_key_admits_a_customers_salesorder_skill_and_nothing_else_of_its_shape(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        check = str(
            await conn.scalar(
                sa.text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_rule_versions_key'"
                )
            )
        )
        admitted = await conn.scalar(
            sa.text(f"SELECT {check.removeprefix('CHECK ')} FROM (SELECT :key AS key) k"),
            {"key": salesorder_key("KHB")},
        )
        refused = [
            await conn.scalar(
                sa.text(f"SELECT {check.removeprefix('CHECK ')} FROM (SELECT :key AS key) k"),
                {"key": key},
            )
            for key in (
                "sales_skill_salesorder_",
                "sales_skill_salesorder_9ab",
                "sales_skill_salesorder_Khb",
                "sales_skill_salesorder_khb_x",
                "sales_skill_salesorderkhb",
            )
        ]
    assert admitted is True
    assert refused == [False] * 5
    # Every key the table held before still is.
    assert "'sales_skill_thread_intents'::text" in check
    assert "'sales_salesorder_rules'::text" in check


async def test_a_replay_on_a_customers_pairs_is_a_source_the_table_takes(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        check = str(
            await conn.scalar(
                sa.text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_skill_replays_source'"
                )
            )
        )
    assert "'customer_pairs'::text" in check and "'platform_examples'::text" in check


async def test_a_pair_with_an_empty_file_is_refused(
    world: World, uow: SqlCatalogUnitOfWorkFactory, migrator: AsyncEngine
) -> None:
    async with migrator.begin() as conn:
        with pytest.raises(IntegrityError, match="ck_salesorder_pairs_expected"):
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.salesorder_pairs (id, tenant_id, workspace_id,"
                    " customer_code, received_on, layout_ref, document, expected, added_by,"
                    " added_at) VALUES (:id, :tenant, :workspace, 'KHB', '2026-11-16', 'x',"
                    " '{}'::jsonb, '[]'::jsonb, :id, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": world.alpha.tenant_id.value,
                    "workspace": world.alpha.workspace_id.value,
                },
            )
