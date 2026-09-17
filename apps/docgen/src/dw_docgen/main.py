"""Composition root for the sandbox service.

Deliberately small. This process holds no database handle, no object-store
client and no credentials of any kind: everything it needs arrives in the
request, and everything it produces leaves in the response. That is the whole
security argument — code the model wrote runs here, so there must be nothing
here worth reaching.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from dw_docgen.api import router
from dw_docgen.settings import DocgenSettings, get_settings
from dw_docgen.workspace import SessionWorkspace

logger = logging.getLogger(__name__)


def create_app(settings: DocgenSettings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        root = Path(resolved.root)
        root.mkdir(parents=True, exist_ok=True)
        app.state.settings = resolved
        workspace = SessionWorkspace(root)
        workspace.scratch_dir.mkdir(parents=True, exist_ok=True)
        app.state.workspace = workspace
        app.state.semaphore = asyncio.Semaphore(resolved.max_concurrency)
        app.state.active_sessions = set()
        if not resolved.enforce_limits:
            logger.warning(
                "resource limits are unavailable on this platform, so commands run "
                "uncapped. This build is for tests only - the sandbox image is Linux."
            )
        yield

    app = FastAPI(
        title="dw-docgen",
        version="0.1.0",
        lifespan=lifespan,
        # No interactive docs and no schema endpoint: nothing human browses this
        # service, and the smaller its surface the less there is to probe.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)
    return app
