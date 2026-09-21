"""FastAPI application factory.

Platform routers are mounted unconditionally; the ones that need infrastructure
check their dependency first, so a host without a database serves fewer routes
rather than routes that fail on every call.

Business bounded contexts mount their presentation routers at the marked seam
near the bottom, built from ``container.runtime`` (see
``dw_api.bootstrap.wiring``). Nothing in this module may import a business
package.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import dw_api
from dw_api.bootstrap import ApiContainer, build_container
from dw_api.exception_handlers import register_exception_handlers
from dw_api.middleware.rate_limit import RateLimitMiddleware
from dw_api.middleware.request_id import RequestIdMiddleware
from dw_api.routes.v1.admin_console import router as admin_console_router
from dw_api.routes.v1.admin_members import router as admin_members_router
from dw_api.routes.v1.approvals import router as approvals_router
from dw_api.routes.v1.audit import router as audit_router
from dw_api.routes.v1.auth import router as auth_router
from dw_api.routes.v1.directory import router as directory_router
from dw_api.routes.v1.feedback import router as feedback_router
from dw_api.routes.v1.health import build_health_router
from dw_api.routes.v1.integrations import router as integrations_router
from dw_api.routes.v1.knowledge import router as knowledge_router
from dw_api.routes.v1.me import router as me_router
from dw_api.routes.v1.memory import router as memory_router
from dw_api.routes.v1.platform import router as platform_router
from dw_api.routes.v1.runs import router as runs_router

_LOG = logging.getLogger(__name__)

# Headers the browser client sends. Listed rather than wildcarded because a
# wildcard and credentials cannot both be allowed.
_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Tenant-Id",
    "X-Workspace-Id",
    "Idempotency-Key",
]
_CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
_LOCAL_WEB_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app(container: ApiContainer | None = None) -> FastAPI:
    container = container or build_container()
    settings = container.settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One LISTEN connection for this process, feeding every open stream.
        # Started here because it owns a connection for the app's lifetime, and
        # a composition root that is synchronous cannot open one.
        if container.run_events is not None:
            await container.run_events.start()
        try:
            yield
        finally:
            await container.shutdown()

    # The schema and its Swagger/ReDoc UIs describe every route to anyone who
    # asks; deployed profiles hide them so a scan cannot enumerate the surface.
    # Kept in local/test, where they are the tool developers actually use.
    hide_docs = settings.is_deployed
    app = FastAPI(
        title="Digital Worker Platform API",
        version=dw_api.__version__,
        lifespan=lifespan,
        docs_url=None if hide_docs else "/api/docs",
        redoc_url=None if hide_docs else "/api/redoc",
        openapi_url=None if hide_docs else "/api/openapi.json",
    )
    app.state.container = container

    # Middleware runs in reverse registration order: request-id first, then limit.
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestIdMiddleware)

    # Browser clients are cross-origin; a deployed profile must list origins
    # explicitly, local/test fall back to the dev web origin.
    cors_origins = settings.cors_origins
    if not cors_origins and not settings.is_deployed:
        cors_origins = _LOCAL_WEB_ORIGINS
    if cors_origins:
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=_CORS_METHODS,
            allow_headers=_CORS_HEADERS,
            expose_headers=["X-Request-ID", "Retry-After"],
        )

    register_exception_handlers(app)

    app.include_router(build_health_router(container.health_service), prefix="/api/v1")
    for router in (
        auth_router,
        me_router,
        directory_router,
        admin_members_router,
        admin_console_router,
        approvals_router,
        runs_router,
        audit_router,
        feedback_router,
        knowledge_router,
        memory_router,
        integrations_router,
    ):
        app.include_router(router, prefix="/api/v1")

    # Platform provisioning: mounted only when the provisioner connection is
    # configured, so environments that never provision stay lean.
    if container.provisioning is not None:
        app.include_router(platform_router, prefix="/api/v1")

    # ---- BOUNDED CONTEXT ROUTERS MOUNT HERE ------------------------------
    # Guard each on the dependency it needs, as the platform routers above do:
    # a router that 500s on every call is worse than an absent one.

    # Development helpers, never mounted in a deployed profile. The dev-token
    # issuer stays gated on dev auth mode so it can never become an OIDC bypass.
    if not settings.is_deployed:
        from dw_api.bootstrap import REPO_ROOT
        from dw_api.routes.v1.dev import build_dev_router

        app.include_router(
            build_dev_router(
                REPO_ROOT,
                settings.dev_secret or "",
                include_session=settings.auth_mode == "dev" and bool(settings.dev_secret),
            ),
            prefix="/api/v1",
        )
    return app


app = create_app()
