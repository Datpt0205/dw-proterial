"""Platform integration harness: its own database."""

from __future__ import annotations

from pg_test_db import REPO_ROOT, DatabaseUrls, database_urls, recreate_database, run_alembic

__all__ = ["REPO_ROOT", "DatabaseUrls", "database_urls", "recreate_database", "run_alembic"]

TEST_DB = "dw_test"


def platform_urls() -> DatabaseUrls:
    return database_urls(TEST_DB)
