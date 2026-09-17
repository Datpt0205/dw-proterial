"""Integration: feedback with screenshots, under RLS (spec 003 US5).

The attachment rows sit in their own table beside ``feedback``; both are
tenant-confined. What matters here is the join back - the inbox lists each
feedback with its screenshots in one read - and that a screenshot written for
another tenant is invisible by id, which is what makes the download endpoint
safe to key on ids alone.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from pg_harness import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from test_feedback import ALPHA, ALPHA_WS, _member, _sign_in

from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.feedback_dto import attachment_key
from dw_platform.testing.seed_env import seed_test_env

pytestmark = pytest.mark.integration


@pytest.fixture
async def app_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    await seed_test_env(db_urls.migrator)
    engine = create_async_engine(db_urls.app, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrator_engine(db_urls: DatabaseUrls) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_urls.migrator, poolclass=NullPool)
    yield engine
    await engine.dispose()


@dataclass(frozen=True)
class _Written:
    feedback_id: uuid.UUID
    attachment_ids: tuple[uuid.UUID, ...]


async def _submit(engine: AsyncEngine, author: uuid.UUID, *, images: int) -> _Written:
    factory = SqlPlatformUnitOfWorkFactory(async_sessionmaker(engine, expire_on_commit=False))
    feedback_id = uuid.uuid4()
    attachment_ids = tuple(uuid.uuid4() for _ in range(images))
    async with factory(_member(author)) as uow:
        await uow.feedback.add(
            feedback_id=feedback_id,
            tenant_id=ALPHA,
            workspace_id=ALPHA_WS,
            author_id=author,
            category="bug",
            message="Nút Convert biến mất.",
            module="Leads",
            page_path="/sales/leads/123",
            suggestion="Giữ nút ở mọi trạng thái.",
        )
        for attachment_id in attachment_ids:
            await uow.feedback.add_attachment(
                attachment_id=attachment_id,
                feedback_id=feedback_id,
                tenant_id=ALPHA,
                workspace_id=ALPHA_WS,
                object_key=attachment_key(
                    tenant_id=ALPHA,
                    workspace_id=ALPHA_WS,
                    feedback_id=feedback_id,
                    attachment_id=attachment_id,
                ),
                content_type="image/png",
                size_bytes=1234,
            )
        await uow.commit()
    return _Written(feedback_id, attachment_ids)


async def test_the_inbox_lists_a_feedback_with_its_screenshots(app_engine: AsyncEngine) -> None:
    author = await _sign_in(app_engine, "shot@fpt.com", "Screen Shot")
    written = await _submit(app_engine, author, images=2)
    factory = SqlPlatformUnitOfWorkFactory(async_sessionmaker(app_engine, expire_on_commit=False))

    async with factory(_member(author)) as uow:
        items = await uow.feedback.list_recent()
        found = next(item for item in items if item.id == written.feedback_id)
        one = await uow.feedback.get_attachment(written.feedback_id, written.attachment_ids[0])

    assert found.module == "Leads"
    assert found.page_path == "/sales/leads/123"
    assert found.suggestion == "Giữ nút ở mọi trạng thái."
    assert {attachment.id for attachment in found.attachments} == set(written.attachment_ids)
    assert one is not None and one.content_type == "image/png"
    assert str(ALPHA) in one.object_key and str(ALPHA_WS) in one.object_key


async def test_a_screenshot_of_another_tenant_is_invisible_by_id(
    app_engine: AsyncEngine, migrator_engine: AsyncEngine
) -> None:
    author = await _sign_in(app_engine, "isolated@fpt.com", "Isolated")
    theirs_feedback = uuid.uuid4()
    theirs_attachment = uuid.uuid4()
    other_tenant = uuid.uuid4()
    async with async_sessionmaker(migrator_engine, expire_on_commit=False)() as session:
        await session.execute(
            sa.insert(tables.feedback).values(
                id=theirs_feedback,
                tenant_id=other_tenant,
                workspace_id=uuid.uuid4(),
                author_id=author,
                category="bug",
                message="Theirs.",
            )
        )
        await session.execute(
            sa.insert(tables.feedback_attachments).values(
                id=theirs_attachment,
                tenant_id=other_tenant,
                workspace_id=uuid.uuid4(),
                feedback_id=theirs_feedback,
                object_key="feedback/elsewhere",
                content_type="image/png",
                size_bytes=1,
            )
        )
        await session.commit()

    factory = SqlPlatformUnitOfWorkFactory(async_sessionmaker(app_engine, expire_on_commit=False))
    async with factory(_member(author)) as uow:
        hidden = await uow.feedback.get_attachment(theirs_feedback, theirs_attachment)
        listed = await uow.feedback.list_recent()

    assert hidden is None
    assert all(item.id != theirs_feedback for item in listed)


async def test_the_attachment_table_forces_row_level_security(
    migrator_engine: AsyncEngine,
) -> None:
    async with migrator_engine.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE oid = 'platform.feedback_attachments'::regclass"
                )
            )
        ).one()
    assert row.relrowsecurity and row.relforcerowsecurity
