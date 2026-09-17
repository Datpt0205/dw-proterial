"""Runtime integration harness: its own database, plus Qdrant and MinIO."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pg_test_db import (
    REPO_ROOT,
    TENANT_A,
    TENANT_B,
    WORKSPACE_A,
    WORKSPACE_B,
    database_urls,
    load_env,
    recreate_database,
    run_migrations,
)

from dw_agent_runtime.contracts import RunContext

__all__ = [
    "REPO_ROOT",
    "TENANT_A",
    "TENANT_B",
    "WORKSPACE_A",
    "WORKSPACE_B",
    "RuntimeUrls",
    "make_run_context",
    "recreate_database",
    "run_migrations",
    "runtime_urls",
]

TEST_DB = "dw_test_runtime"


@dataclass(frozen=True)
class RuntimeUrls:
    admin: str
    migrator: str
    app: str
    qdrant_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str


def runtime_urls() -> RuntimeUrls:
    env = load_env()
    urls = database_urls(TEST_DB)
    return RuntimeUrls(
        admin=urls.admin,
        migrator=urls.migrator,
        app=urls.app,
        qdrant_url=env.get("QDRANT_URL", "http://localhost:6333"),
        minio_endpoint=env.get("S3_ENDPOINT_URL", "http://localhost:9000").split("//")[-1],
        minio_access_key=env.get("MINIO_ROOT_USER", "dw-minio"),
        minio_secret_key=env.get("MINIO_ROOT_PASSWORD", "change-me-minio"),
    )


def make_run_context(
    *,
    tenant: uuid.UUID = TENANT_A,
    workspace: uuid.UUID = WORKSPACE_A,
    run_id: uuid.UUID | None = None,
    thread_id: uuid.UUID | None = None,
    scopes: frozenset[str] = frozenset({"demo.write", "demo.read"}),
) -> RunContext:
    return RunContext(
        run_id=run_id or uuid.uuid4(),
        thread_id=thread_id,
        tenant_id=tenant,
        workspace_id=workspace,
        actor_id=uuid.uuid4(),
        worker_id="demo_approval",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=scopes,
        trace_id=f"trace-{uuid.uuid4().hex[:8]}",
    )
