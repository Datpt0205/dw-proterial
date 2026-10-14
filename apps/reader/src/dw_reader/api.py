"""HTTP surface: one route that reads, and a health check.

`POST /v1/read` takes a `ReaderRequest` (`dw_sales.adapters.reader_wire`) as
its body and answers the reply a one-use reading process wrote
(`dw_reader.reading`). The body is not parsed here: it is measured against
`max_request_bytes` and handed to the reading process as written, so this
process never holds a file's contents in any structure it acts on.

There is no token: the service listens only on a Unix socket in a volume the
api and worker containers mount, and the container has no network, so
nothing else can reach it (`infra/compose/docker-compose.yml`).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from dw_reader.reading import LimitsUnavailableError, read_once
from dw_reader.settings import ReaderSettings

logger = logging.getLogger("dw_reader")

router = APIRouter()


def _settings(request: Request) -> ReaderSettings:
    settings: ReaderSettings = request.app.state.settings
    return settings


Settings = Annotated[ReaderSettings, Depends(_settings)]


@router.get("/health")
def health(request: Request, settings: Settings) -> dict[str, object]:
    """Ready only once a reading process started and answered at startup:
    a broken image fails here, before any file is read as "crashed"."""
    if not request.app.state.ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready")
    return {"status": "ok", "limits_enforced": settings.enforce_limits}


@router.post("/v1/read")
async def read(request: Request, settings: Settings) -> Response:
    body = await _body(request, settings.max_request_bytes)
    semaphore: asyncio.Semaphore = request.app.state.semaphore
    async with semaphore:
        try:
            answer = await asyncio.to_thread(read_once, body, settings)
        except LimitsUnavailableError as unprotected:
            # Fail closed, and loudly: a reader without its limits reads nothing.
            logger.error("refusing to read: %s", unprotected)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="limits unavailable"
            ) from unprotected
    return Response(content=answer, media_type="application/json")


async def _body(request: Request, limit: int) -> bytes:
    """The request body, refused (413) past ``limit`` before it is all read."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="too large")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="too large")
    return bytes(received)
