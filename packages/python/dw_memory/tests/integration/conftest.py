"""One migrated database for every memory integration file.

The fixture used to live inside `test_memory_service_db.py`, which was fine
while it had one reader. A second file needing it would otherwise copy the
recreate-and-migrate dance, and two copies of "how a test database is built"
drift the first time the harness changes.
"""

from __future__ import annotations

import asyncio

import pytest
from runtime_harness import TEST_DB, RuntimeUrls, recreate_database, run_migrations, runtime_urls


@pytest.fixture(scope="session")
def urls() -> RuntimeUrls:
    resolved = runtime_urls()
    try:
        asyncio.run(recreate_database(resolved.admin, TEST_DB))
    except Exception as exc:  # pragma: no cover - environment, not logic
        pytest.fail(f"Postgres unreachable — run `make infra-up`. Error: {exc}")
    result = run_migrations(resolved.migrator)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade failed:\n{result.stderr}")
    return resolved
