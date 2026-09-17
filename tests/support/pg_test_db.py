"""Postgres bring-up shared by every integration and e2e suite.

Each suite owns a database so they never fight, but the credentials, the DSNs,
the drop/create and the alembic invocation are the same everywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TENANT_A = uuid.UUID(int=0xA00)
WORKSPACE_A = uuid.UUID(int=0xA01)
TENANT_B = uuid.UUID(int=0xB00)
WORKSPACE_B = uuid.UUID(int=0xB01)


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    values.update(
        {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("DW_", "POSTGRES", "MINIO", "QDRANT", "S3_"))
        }
    )
    return values


@dataclass(frozen=True)
class DatabaseUrls:
    admin: str
    migrator: str
    app: str


def database_urls(test_db: str) -> DatabaseUrls:
    env = load_env()
    host = env.get("DW_TEST_DB_HOST", "localhost")
    port = env.get("DW_TEST_DB_PORT", "5432")
    admin_user = env.get("POSTGRES_USER", "dw_admin")
    admin_password = env.get("POSTGRES_PASSWORD", "change-me-admin")
    migrator_password = env.get("DW_DB_MIGRATOR_PASSWORD", "change-me-migrator")
    app_password = env.get("DW_DB_APP_PASSWORD", "change-me-app")
    return DatabaseUrls(
        admin=f"postgresql+asyncpg://{admin_user}:{admin_password}@{host}:{port}/postgres",
        migrator=f"postgresql+asyncpg://dw_migrator:{migrator_password}@{host}:{port}/{test_db}",
        app=f"postgresql+asyncpg://dw_app:{app_password}@{host}:{port}/{test_db}",
    )


async def recreate_database(admin_url: str, test_db: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {test_db} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {test_db} OWNER dw_migrator"))
    finally:
        await engine.dispose()


def run_alembic(command: list[str], database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPO_ROOT / "db" / "alembic.ini"), *command],
        env={**os.environ, "DW_DATABASE_URL": database_url},
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_migrations(database_url: str) -> subprocess.CompletedProcess[str]:
    return run_alembic(["upgrade", "head"], database_url)
