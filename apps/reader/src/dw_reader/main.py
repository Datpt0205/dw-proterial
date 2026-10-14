"""Composition root for the reader sandbox.

Deliberately small, like docgen's: no database handle, no object-store
client, no credential and no network. What it reads arrives in the request
and what it read leaves in the reply.

At startup one reading process is run on a request that reads no file (the
platform's layouts): an image whose readers cannot start answers 503 on
`/health`, so compose never routes a file to it and no message is routed to
Sales as "the reader failed on this file" because the image was broken.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import ValidationError

from dw_reader.api import router
from dw_reader.reading import LimitsUnavailableError, read_once
from dw_reader.settings import ReaderSettings, get_settings
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest

logger = logging.getLogger("dw_reader")


def self_check(settings: ReaderSettings) -> bool:
    """Whether a reading process starts and answers (module docstring)."""
    probe = ReaderRequest.of(ReaderOp.PO_LAYOUTS).model_dump_json().encode("utf-8")
    try:
        reply = ReaderReply.model_validate_json(read_once(probe, settings))
    except (LimitsUnavailableError, ValidationError):
        logger.exception("the reader's self-check failed")
        return False
    if reply.failure is not None:
        logger.error("the reader's self-check failed: %s", reply.failure)
        return False
    return True


def create_app(settings: ReaderSettings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        Path(resolved.root).mkdir(parents=True, exist_ok=True)
        app.state.settings = resolved
        app.state.semaphore = asyncio.Semaphore(resolved.max_concurrency)
        if not resolved.enforce_limits:
            logger.warning(
                "resource limits are unavailable on this platform, so files are read "
                "uncapped. This build is for tests only - the reader image is Linux."
            )
        app.state.ready = await asyncio.to_thread(self_check, resolved)
        yield

    app = FastAPI(
        title="dw-reader",
        version="0.1.0",
        lifespan=lifespan,
        # Nothing human browses this service.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)
    return app
