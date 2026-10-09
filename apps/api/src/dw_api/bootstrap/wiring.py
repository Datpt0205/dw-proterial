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
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dw_agent_runtime.adapters.langgraph_runner import LangGraphWorkflowRunner
from dw_agent_runtime.adapters.run_events import RunStateListener
from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.approval_codes import ApprovalViewService
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.model.run_policy import load_worker_run_policy
from dw_agent_runtime.registry import GraphRegistry, WorkerRegistry, parse_worker_file
from dw_api.bootstrap.container import ApiContainer
from dw_api.bootstrap.identity import build_token_verifier
from dw_api.bootstrap.paths import (
    COPY_DIR,
    POLICIES_DIR,
    WORKER_RUN_POLICY,
    WORKERS_DIR,
    release_manifest_ref,
)
from dw_api.bootstrap.runtime import build_runtime
from dw_api.bootstrap.storage import (
    build_attachment_storage,
    build_minio_client,
    build_object_storage,
)
from dw_api.bootstrap.telemetry import build_telemetry
from dw_api.health import HealthService, database_probe, qdrant_probe, redis_probe
from dw_api.settings import ApiSettings
from dw_connectors.adapters.zalo_link import ZaloLinking
from dw_kernel.ports import IdGenerator, SystemClock, UtcClock, Uuid7Generator
from dw_knowledge.ports import ObjectStoragePort
from dw_platform.adapters.cache import NullCache, ValkeyCache
from dw_platform.adapters.persistence.admin_console_repo import SqlAdminConsoleRepository
from dw_platform.adapters.persistence.approval_codes import SqlApprovalCodeStore
from dw_platform.adapters.persistence.caching_lookup import CachingMembershipLookup
from dw_platform.adapters.persistence.channel_inbound import SqlChannelUpdateQueue
from dw_platform.adapters.persistence.channel_preferences import SqlChannelPreferences
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.adapters.persistence.hierarchy_repo import SqlHierarchyRepository
from dw_platform.adapters.persistence.idempotency_store import SqlIdempotencyStore
from dw_platform.adapters.persistence.identity_provisioning import SqlIdentityBootstrap
from dw_platform.adapters.persistence.membership_admin import SqlMembershipAdminRepository
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.adapters.persistence.notifications import SqlNotificationRepository
from dw_platform.adapters.persistence.provisioning_repo import SqlProvisioningRepository
from dw_platform.adapters.persistence.scope_holders import SqlScopeHolders
from dw_platform.adapters.persistence.separation_of_duties_repo import (
    SqlSeparationOfDutiesRepository,
)
from dw_platform.adapters.persistence.support_grants import (
    SqlStaffGrants,
    SqlSupportGrantRepository,
)
from dw_platform.adapters.persistence.tenant_members import SqlTenantMembersRepository
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.adapters.persistence.zalo_link_repo import SqlZaloLink
from dw_platform.application.admin_console import AdminConsoleService
from dw_platform.application.approval_codes import ApprovalSubjectVersions, DecisionCodeKey
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.hierarchy import HierarchyService
from dw_platform.application.idempotency import HttpIdempotency
from dw_platform.application.identity import DbAccessContextFactory
from dw_platform.application.membership_admin import (
    GrantMembershipHandler,
    RevokeMembershipHandler,
)
from dw_platform.application.notifications import NotificationService
from dw_platform.application.ports import WorkspaceDirectoryPort
from dw_platform.application.provisioning import ProvisioningService
from dw_platform.application.separation_of_duties import SeparationOfDutiesService
from dw_platform.application.support_access import (
    SupportAccessContextFactory,
    SupportGrantService,
)
from dw_platform.application.tenant_members import TenantMembersService

_LOG = logging.getLogger("dw_api.bootstrap")

_RUN_POLICY = load_worker_run_policy(WORKER_RUN_POLICY)

# Routes open to a support context (ADR 0024), as (method, path template).
# Empty on the platform: a context adds a route here in the same change as
# that route's negative test under a support grant. `test_support_routes.py`
# fails when RequireAccessContextOrSupport appears on any route not listed.
SUPPORT_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset()


def _asyncpg_dsn(url: str) -> str:
    """SQLAlchemy's URL minus the driver marker asyncpg does not understand."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_container(settings: ApiSettings | None = None) -> ApiContainer:
    container = _build_container(settings)
    # Every context has registered its support scope sets by now (the seam
    # below); nothing may add one while the process serves requests.
    container.support_catalog.freeze()
    return container


def _build_container(settings: ApiSettings | None) -> ApiContainer:
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

    # Built ahead of the database gate below: neither depends on Postgres, and
    # readiness must report both regardless of whether a database is
    # configured at all.
    cache = ValkeyCache.from_url(settings.redis_url) if settings.redis_url else NullCache()
    qdrant_client = (
        AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        if settings.qdrant_url
        else None
    )

    def _health_service(engine: AsyncEngine | None) -> HealthService:
        return HealthService(
            probes={
                "database": database_probe(engine),
                "redis": redis_probe(cache.client if isinstance(cache, ValkeyCache) else None),
                "qdrant": qdrant_probe(qdrant_client),
            }
        )

    container = ApiContainer(
        settings=settings,
        engine=None,
        health_service=_health_service(None),
        token_verifier=build_token_verifier(settings),
        access_context_factory=None,
        identity_bootstrap=None,
        uow_factory=None,
        authorization=authorization,
        entitlement=entitlement,
        cache=cache,
        qdrant_client=qdrant_client,
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
    container.health_service = _health_service(engine)

    # Cache the membership lookup (the per-request AccessContext) so a burst
    # from one user hits the database once. No cache URL → straight to the
    # database, unchanged.
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
    container.tenant_members = TenantMembersService(
        SqlTenantMembersRepository(session_factory), authorization, clock, ids
    )
    container.admin_console = AdminConsoleService(
        SqlAdminConsoleRepository(session_factory), authorization, clock, ids
    )
    container.hierarchy = HierarchyService(
        SqlHierarchyRepository(session_factory), authorization, clock, ids
    )
    container.separation_of_duties = SeparationOfDutiesService(
        SqlSeparationOfDutiesRepository(session_factory), authorization, clock, ids
    )
    container.notifications = NotificationService(SqlNotificationRepository(session_factory))
    container.support_grants = SupportGrantService(
        repo=SqlSupportGrantRepository(session_factory),
        member_scopes=SqlScopeHolders(session_factory),
        catalog=container.support_catalog,
        clock=clock,
        ids=ids,
    )
    staff_grants = SqlStaffGrants(session_factory)
    container.support_access = SupportAccessContextFactory(
        grants=staff_grants,
        member_scopes=SqlScopeHolders(session_factory),
        clock=clock,
        ids=ids,
    )
    container.support_access_audit = staff_grants
    container.staff_grants = staff_grants
    container.support_allowed_routes = SUPPORT_ALLOWED_ROUTES
    # The user's own Zalo link, on the request pool (`dw_app`), which holds the
    # identity-plane grants it needs; never the provisioner engine.
    if settings.zalo_link_enabled:
        container.zalo_linking = ZaloLinking(
            store=SqlZaloLink(session_factory),
            link_secret=settings.zalo_link_secret.get_secret_value(),
            clock=clock,
            bot_link=settings.zalo_bot_link,
        )
        container.channel_preferences = SqlChannelPreferences(session_factory)
    # The hosted way updates arrive (ADR 0008): queued here, handled by the
    # worker's drain through the same entry the poll lane uses.
    if settings.zalo_webhook_enabled:
        container.zalo_webhook_inbox = SqlChannelUpdateQueue(session_factory)

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
    # The portal half of a decision on Zalo (ADR 0007, channels Z5): the view
    # receipt and the single-use code. A context registers who answers for its
    # approval types' subject version on `approval_subjects` at the seam below
    # (`approval_subjects.register(prefix, port)`); a type nobody answers for
    # is decided on the web only.
    approval_subjects = ApprovalSubjectVersions()
    code_secret = settings.approval_code_secret.get_secret_value()
    container.approval_views = ApprovalViewService(
        uow_factory=uow_factory,
        approval_flow=wiring.approval_flow,
        store=SqlApprovalCodeStore(session_factory),
        subjects=approval_subjects,
        chats=SqlZaloLink(session_factory),
        key=DecisionCodeKey(code_secret.encode()) if code_secret else None,
        clock=clock,
        ids=ids,
    )
    container.knowledge_gateway = wiring.knowledge_gateway
    container.ingest_job_store = wiring.ingest_jobs
    container.memory_service = wiring.memory_service
    container.tool_registry = wiring.tool_registry

    # ---- BOUNDED CONTEXTS PLUG IN HERE -----------------------------------
    # Sales: built from the seam, never from a global. `container.runtime`
    # carries the session factory, clock, ids, registries and gateways; anything
    # this context needs beyond them is its own adapter (`build_sales` below).
    assert container.workspace_directory is not None  # wired with the database
    container.sales = build_sales(
        settings,
        session_factory=wiring.seam.session_factory,
        clock=wiring.seam.clock,
        ids=wiring.seam.ids,
        authorization=authorization,
        directory=container.workspace_directory,
        holders=SqlScopeHolders(session_factory),
        notifications=SqlNotificationRepository(session_factory),
        artifact_bytes=object_storage,
        release_manifest_ref=release_manifest_ref(),
        runtime=SalesRuntime(
            graphs=wiring.seam.graphs,
            workers=wiring.seam.workers,
            runner=wiring.runner,
            approval_flow=wiring.approval_flow,
        ),
    )

    # Build your context from `container.runtime` (the RuntimeSeam) and attach
    # its handlers, then mount its router in `main.create_app`. Nothing above
    # this line may import a business package. A context offering support
    # access registers here too: `container.support_catalog.register(...)`
    # and `.register_resource(...)` (ADR 0024).

    return container


@dataclass(frozen=True)
class SalesRuntime:
    """The runtime pieces DW1 plugs into: where its graph and worker are
    registered, what starts its runs, and the approvals its runs pause on."""

    graphs: GraphRegistry
    workers: WorkerRegistry
    runner: LangGraphWorkflowRunner
    approval_flow: ApproveAndResumeService


def build_sales(
    settings: ApiSettings,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    clock: UtcClock,
    ids: IdGenerator,
    authorization: ScopeAuthorizationService,
    directory: WorkspaceDirectoryPort,
    holders: SqlScopeHolders,
    notifications: SqlNotificationRepository,
    artifact_bytes: ObjectStoragePort,
    release_manifest_ref: str | None,
    runtime: SalesRuntime,
) -> object:
    """The Sales context's mount, part of the seam above.

    DW1's master data and mailbox are fictional mocks bound to one demo
    (tenant, workspace) (`ApiSettings.sales_demo_scope`); every other scope
    reads them empty. In a deployed profile without that pair nothing is
    wired, and the Sales routes answer that no data source is configured.

    DW1 runs on the runtime (dw_sales ADR 0004): its graph and worker
    (`configs/workers/sales.yaml`) are registered here, every `sales.`
    approval is made strict and checked by the context before it is recorded
    (`dw_sales.workflows.graph.register`), and "DW xử lý", a submitted
    quotation and a recorded Bravo entry each start a run.
    """
    from dw_kernel.ids import TenantId, WorkspaceId
    from dw_platform.adapters.persistence.repositories import SqlAuditRepository
    from dw_sales.adapters.artifact_files import ArtifactFiles
    from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
    from dw_sales.adapters.order_rules import PlatformOrderRules
    from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
    from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
    from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
    from dw_sales.adapters.policy_files import load_sales_policies
    from dw_sales.adapters.readers import mock_po_readers
    from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
    from dw_sales.adapters.runtime import RuntimeDw1Runs
    from dw_sales.adapters.source_view import FileSourceView
    from dw_sales.application.order_intake import OrderIntake
    from dw_sales.application.ports import SalesScope
    from dw_sales.application.quotation import QuotationService
    from dw_sales.application.services import assemble
    from dw_sales.presentation.routes import SalesMount
    from dw_sales.workflows.graph import register

    demo = settings.sales_demo_scope()
    if demo is None:
        _LOG.warning("sales: no data source configured; /api/v1/sales answers 503")
        return SalesMount(services=None)
    scope = SalesScope(TenantId(demo[0]), WorkspaceId(demo[1]))
    catalog = MockSalesCatalog.load(scope)
    inbox = MockInbox.load(scope)
    policies = load_sales_policies(POLICIES_DIR, COPY_DIR)
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=SqlQuoteCaseLookup(session_factory),
        ledger=catalog,
        rules=policies.quote_rules,
        pricing=policies.pricing,
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(policies.order_rules),
        cases=SqlOrderCaseLookup(session_factory),
        new_case_id=ids.new_uuid,
    )
    worker_file = WORKERS_DIR / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    runs = RuntimeDw1Runs(
        runtime.runner,
        runtime.approval_flow,
        ids,
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
    )
    assembly = assemble(
        uow=SqlSalesUnitOfWorkFactory(session_factory, audit=SqlAuditRepository),
        authorization=authorization,
        clock=clock,
        ids=ids,
        catalog=catalog,
        inbox=inbox,
        intake=intake,
        quotation=quotation,
        files=FileSourceView(policies.order_rules.intake),
        kpi=policies.kpi,
        directory=directory,
        holders=holders,
        notifications=notifications,
        artifact_bytes=artifact_bytes,
        artifact_writer=ArtifactFiles(),
        artifact_copy=policies.artifact_copy,
        release_manifest_ref=release_manifest_ref,
        runs=runs,
        pending=runs,
    )
    register(
        graphs=runtime.graphs,
        workers=runtime.workers,
        approvals=runtime.approval_flow,
        steps=assembly.decisions,
        worker_file=worker_file,
    )
    return SalesMount(services=assembly.services)


def build_engine(url: str, *, pool_pre_ping: bool = True) -> AsyncEngine:
    """Shared engine construction, for processes that need one outside the API."""
    return create_async_engine(url, pool_pre_ping=pool_pre_ping)
