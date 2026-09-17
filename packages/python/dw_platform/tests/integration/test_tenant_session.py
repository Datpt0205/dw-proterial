"""A failure while opening a tenant session must not cost the connection."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pg_harness import DatabaseUrls
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dw_platform.adapters.persistence import tenant_session as tenant_session_module
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session

TENANT = uuid.UUID(int=0xA00)

# One connection and no overflow: a leaked connection makes the next acquisition
# block until the pool times out, which is what this asserts against.
_SINGLE_CONNECTION = {"pool_size": 1, "max_overflow": 0, "pool_timeout": 5}


@pytest.mark.asyncio
async def test_a_failed_bind_releases_the_connection(
    db_urls: DatabaseUrls, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(db_urls.app, **_SINGLE_CONNECTION)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fail_after_checkout(session: AsyncSession, _: TenantScope) -> None:
        """Fail the way a real bind fails: the connection is already checked out.

        Raising before any statement would leave the pool untouched, because
        ``session.begin()`` acquires nothing until the first execute.
        """
        await session.execute(text("SELECT * FROM table_that_does_not_exist"))

    monkeypatch.setattr(tenant_session_module, "bind_tenant", fail_after_checkout)
    try:
        with pytest.raises(ProgrammingError):
            async with tenant_session(factory, TenantScope(TENANT)):
                pytest.fail("the body must not run when the bind fails")
        monkeypatch.undo()

        async with tenant_session(factory, TenantScope(TENANT)) as session:
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_failing_body_releases_the_connection(db_urls: DatabaseUrls) -> None:
    engine = create_async_engine(db_urls.app, **_SINGLE_CONNECTION)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        with pytest.raises(ProgrammingError):
            async with tenant_session(factory, TenantScope(TENANT)) as session:
                await session.execute(text("SELECT * FROM table_that_does_not_exist"))

        async with tenant_session(factory, TenantScope(TENANT)) as session:
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_scope_reaches_the_database_and_is_transaction_local(
    db_urls: DatabaseUrls,
) -> None:
    engine = create_async_engine(db_urls.app, **_SINGLE_CONNECTION)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    workspace = uuid.UUID(int=0xA01)

    try:
        async with tenant_session(factory, TenantScope(TENANT, workspace)) as session:
            bound = (
                await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
            ).scalar()
            assert bound == str(TENANT)

        # Same pooled connection, new transaction: the previous scope is gone.
        async with factory() as session, session.begin():
            leaked = (
                await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
            ).scalar()
            assert leaked in (None, "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_absent_workspace_binds_empty_rather_than_the_previous_one(
    db_urls: DatabaseUrls,
) -> None:
    engine = create_async_engine(db_urls.app, **_SINGLE_CONNECTION)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with tenant_session(factory, TenantScope(TENANT, uuid.UUID(int=0xA01))):
            pass
        async with tenant_session(factory, TenantScope(TENANT)) as session:
            workspace = (
                await session.execute(text("SELECT current_setting('app.workspace_id', true)"))
            ).scalar()
            assert workspace == ""
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_pool_survives_repeated_failures(db_urls: DatabaseUrls) -> None:
    engine = create_async_engine(db_urls.app, **_SINGLE_CONNECTION)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        for _ in range(5):
            with pytest.raises(ProgrammingError):
                async with tenant_session(factory, TenantScope(TENANT)) as session:
                    await session.execute(text("SELECT * FROM table_that_does_not_exist"))

        async with asyncio.timeout(10):
            async with tenant_session(factory, TenantScope(TENANT)) as session:
                assert (await session.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()
