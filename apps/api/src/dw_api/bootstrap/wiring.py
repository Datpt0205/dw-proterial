"""The composition root itself: the only place concrete adapters are wired.

Tests build their own container with fake ports; deployed wiring lives here.

Reading order is the dependency order — settings, then the database and the
platform services that need one, then object storage, then the agent runtime
that needs both. Each stage is skipped rather than faked when its infrastructure
is absent, which is why almost every field on ``ApiContainer`` is optional: a
host with no database mounts fewer routers instead of serving routers that fail
on every request.

## Plugging in a bounded context

Nothing in this package names a business context, and it must stay that way.
A context joins in three places and no others:

1. here, at the marked seam below — build its handlers from
   ``container.runtime`` and hang them off your own container extension;
2. ``main.create_app`` — mount its presentation router;
3. ``configs/`` — its worker, graph, prompt, tool, toolset and policy files.

``RuntimeSeam`` is the published object it is wired from, so adding a context is
a call rather than an edit in the middle of this file.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dw_agent_runtime.adapters.run_events import RunStateListener
from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.model.run_policy import load_worker_run_policy
from dw_api.bootstrap.container import ApiContainer
from dw_api.bootstrap.identity import build_token_verifier
from dw_api.bootstrap.paths import WORKER_RUN_POLICY
from dw_api.bootstrap.runtime import build_runtime
from dw_api.bootstrap.storage import (
    build_attachment_storage,
    build_minio_client,
    build_object_storage,
)
from dw_api.bootstrap.telemetry import build_telemetry
from dw_api.health import HealthService, database_probe
from dw_api.settings import ApiSettings
from dw_kernel.ports import SystemClock, Uuid7Generator
from dw_platform.adapters.cache import NullCache, ValkeyCache
from dw_platform.adapters.persistence.admin_console_repo import SqlAdminConsoleRepository
from dw_platform.adapters.persistence.caching_lookup import CachingMembershipLookup
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.adapters.persistence.hierarchy_repo import SqlHierarchyRepository
from dw_platform.adapters.persistence.idempotency_store import SqlIdempotencyStore
from dw_platform.adapters.persistence.identity_provisioning import SqlIdentityBootstrap
from dw_platform.adapters.persistence.membership_admin import SqlMembershipAdminRepository
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.provisioning_repo import SqlProvisioningRepository
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.admin_console import AdminConsoleService
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.hierarchy import HierarchyService
from dw_platform.application.idempotency import HttpIdempotency
from dw_platform.application.identity import DbAccessContextFactory
from dw_platform.application.membership_admin import (
    GrantMembershipHandler,
    RevokeMembershipHandler,
)
from dw_platform.application.provisioning import ProvisioningService

_LOG = logging.getLogger("dw_api.bootstrap")

_RUN_POLICY = load_worker_run_policy(WORKER_RUN_POLICY)


def _asyncpg_dsn(url: str) -> str:
    """SQLAlchemy's URL minus the driver marker asyncpg does not understand."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_container(settings: ApiSettings | None = None) -> ApiContainer:
    settings = settings or ApiSettings()
    settings.validate_for_profile()

    clock = SystemClock()
    # Time-ordered ids (RFC 9562), not random v4. Every primary key in this
    # schema is a UUID, and a random one scatters each insert across the whole
    # B-tree; a v7 key appends to one edge of it. The difference is invisible at
    # demo size and is the difference between a healthy index and a bloated one
    # at real size — and it cannot be fixed later, because the rows already
    # written keep the keys they were given.
    ids = Uuid7Generator()
    authorization = ScopeAuthorizationService()
    entitlement = PlanEntitlementService(DEFAULT_PLANS)
    telemetry = build_telemetry(settings)

    container = ApiContainer(
        settings=settings,
        engine=None,
        health_service=HealthService(probes={"database": database_probe(None)}),
        token_verifier=build_token_verifier(settings),
        access_context_factory=None,
        identity_bootstrap=None,
        uow_factory=None,
        authorization=authorization,
        entitlement=entitlement,
    )
    if not settings.database_url:
        _LOG.warning("no database configured: only stateless routes are mounted")
        return container

    # ---- database + platform services ------------------------------------
    # The library default (pool_size=5, max_overflow=10) serialises past 15
    # concurrent DB-touching requests in an async app. 10/20 gives real
    # headroom and stays well under Postgres' default 100 across all pools.
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    container.engine = engine
    container.health_service = HealthService(probes={"database": database_probe(engine)})

    # Cache the membership lookup (the per-request AccessContext) so a burst
    # from one user hits the database once. No cache URL → straight to the
    # database, unchanged.
    cache = ValkeyCache.from_url(settings.redis_url) if settings.redis_url else NullCache()
    container.cache = cache
    container.access_context_factory = DbAccessContextFactory(
        CachingMembershipLookup(SqlMembershipLookup(session_factory), cache)
    )
    container.identity_bootstrap = SqlIdentityBootstrap(
        session_factory=session_factory,
        default_tenant_id=uuid.UUID(settings.default_tenant_id),
        default_workspace_id=uuid.UUID(settings.default_workspace_id),
        default_role=settings.default_role,
        auto_provision_default_membership=settings.auto_provision_default_membership,
    )
    uow_factory = SqlPlatformUnitOfWorkFactory(session_factory)
    container.uow_factory = uow_factory
    container.idempotency = HttpIdempotency(SqlIdempotencyStore(session_factory), clock)
    container.workspace_directory = SqlWorkspaceDirectory(session_factory)

    membership_repo = SqlMembershipAdminRepository(session_factory)
    container.grant_membership = GrantMembershipHandler(membership_repo, authorization, clock, ids)
    container.revoke_membership = RevokeMembershipHandler(
        membership_repo, authorization, clock, ids
    )
    container.admin_console = AdminConsoleService(
        SqlAdminConsoleRepository(session_factory), authorization, clock, ids
    )
    container.hierarchy = HierarchyService(
        SqlHierarchyRepository(session_factory), authorization, clock, ids
    )

    # ---- provisioning ----------------------------------------------------
    # A second engine as the provisioner role: writes across tenants but holds
    # no grant on any business schema. No URL → /platform is not mounted.
    if settings.provisioner_database_url:
        provisioner_engine = create_async_engine(
            settings.provisioner_database_url, pool_pre_ping=True
        )
        container.provisioner_engine = provisioner_engine
        container.provisioning = ProvisioningService(
            repo=SqlProvisioningRepository(
                async_sessionmaker(provisioner_engine, class_=AsyncSession, expire_on_commit=False)
            ),
            clock=clock,
            ids=ids,
        )

    # ---- runs ------------------------------------------------------------
    run_store = SqlWorkerRunStore(
        session_factory, stale_run_after_seconds=_RUN_POLICY.stale_run_after_seconds
    )
    container.run_store = run_store
    # asyncpg directly: a listening connection never returns to a pool, and
    # SQLAlchemy's URL prefix is not a DSN asyncpg accepts.
    container.run_events = RunStateListener(_asyncpg_dsn(settings.database_url))

    # ---- object storage --------------------------------------------------
    minio = build_minio_client(settings)
    object_storage = build_object_storage(minio, settings)
    container.object_storage = object_storage
    container.feedback_storage = build_attachment_storage(minio, settings)

    if object_storage is None:
        _LOG.warning("no object storage configured: the agent runtime is not wired")
        return container

    # ---- agent runtime ---------------------------------------------------
    wiring = build_runtime(
        settings,
        session_factory=session_factory,
        uow_factory=uow_factory,
        run_store=run_store,
        allowance=entitlement,
        object_storage=object_storage,
        telemetry=telemetry,
        clock=clock,
        ids=ids,
    )
    container.runtime = wiring.seam
    container.runner = wiring.runner
    container.approval_flow = wiring.approval_flow
    container.knowledge_gateway = wiring.knowledge_gateway
    container.ingest_job_store = wiring.ingest_jobs
    container.memory_service = wiring.memory_service
    container.tool_registry = wiring.tool_registry

    # ---- BOUNDED CONTEXTS PLUG IN HERE -----------------------------------
    # Build your context from `container.runtime` (the RuntimeSeam) and attach
    # its handlers, then mount its router in `main.create_app`. Nothing above
    # this line may import a business package.

    return container


def build_engine(url: str, *, pool_pre_ping: bool = True) -> AsyncEngine:
    """Shared engine construction, for processes that need one outside the API."""
    return create_async_engine(url, pool_pre_ping=pool_pre_ping)
