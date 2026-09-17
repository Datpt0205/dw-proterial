"""Integration fixtures: disposable migrated database on local Postgres.

Requires `make infra-up`. Fails loudly when the database is unreachable —
integration tests never silently skip.
"""

from __future__ import annotations

import asyncio

import pytest
from pg_harness import TEST_DB, DatabaseUrls, platform_urls, recreate_database, run_alembic
from sqlalchemy.exc import InterfaceError, OperationalError


@pytest.fixture(scope="session")
def db_urls() -> DatabaseUrls:
    urls = platform_urls()
    try:
        asyncio.run(recreate_database(urls.admin, TEST_DB))
    except (OSError, OperationalError, InterfaceError) as exc:
        pytest.fail(
            f"Postgres unreachable at {urls.admin!r} — run `make infra-up` first. Error: {exc}"
        )
    result = run_alembic(["upgrade", "head"], urls.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
    return urls
