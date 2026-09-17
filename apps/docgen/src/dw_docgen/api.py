"""HTTP surface: one session, one shell, files in and out.

Four routes, because a `deepagents` sandbox backend needs exactly four things —
run a command, put files in, take files out — plus a release that ends the
session. Every route is scoped to a session id that maps to one directory and
nothing else.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from dw_docgen.files import BatchTooLargeError, download, upload
from dw_docgen.models import (
    DownloadReply,
    DownloadRequest,
    ExecuteReply,
    ExecuteRequest,
    HealthReply,
    UploadReply,
    UploadRequest,
)
from dw_docgen.runner import run_command
from dw_docgen.settings import DocgenSettings
from dw_docgen.workspace import InvalidSessionError, SessionWorkspace

logger = logging.getLogger(__name__)

router = APIRouter()


def _settings(request: Request) -> DocgenSettings:
    settings: DocgenSettings = request.app.state.settings
    return settings


def _workspace(request: Request) -> SessionWorkspace:
    workspace: SessionWorkspace = request.app.state.workspace
    return workspace


def require_token(request: Request) -> None:
    """Reject a caller that does not present the shared secret.

    Skipped entirely when no token is configured: the service is published on no
    network but `dw-sandbox`, whose only other member is the forwarder in front
    of it, so an empty token is a deployment choice rather than an oversight.
    Compared in constant time so a wrong token leaks nothing about the right one.
    """
    expected: str = request.app.state.settings.token
    if not expected:
        return
    header = request.headers.get("authorization", "")
    presented = header.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


Settings = Annotated[DocgenSettings, Depends(_settings)]
Workspace = Annotated[SessionWorkspace, Depends(_workspace)]
Authorized = Depends(require_token)


@router.get("/health")
def health(settings: Settings) -> HealthReply:
    return HealthReply(status="ok", limits_enforced=settings.enforce_limits)


@router.post("/v1/sessions/{session_id}/execute", dependencies=[Authorized])
async def execute(
    session_id: str,
    payload: ExecuteRequest,
    request: Request,
    settings: Settings,
    workspace: Workspace,
) -> ExecuteReply:
    cwd = _session_dir(workspace, session_id)
    timeout = min(
        payload.timeout_seconds or settings.default_timeout_seconds,
        settings.max_timeout_seconds,
    )
    semaphore: asyncio.Semaphore = request.app.state.semaphore
    active: set[str] = request.app.state.active_sessions
    async with semaphore:
        active.add(session_id)
        try:
            result = await asyncio.to_thread(
                run_command,
                payload.command,
                cwd=cwd,
                sink_dir=workspace.scratch_dir,
                settings=settings,
                timeout_seconds=timeout,
            )
        finally:
            active.discard(session_id)
    _sweep(workspace, settings, active)
    return ExecuteReply(
        output=result.output,
        exit_code=result.exit_code,
        truncated=result.truncated,
        timed_out=result.timed_out,
    )


@router.post("/v1/sessions/{session_id}/files/upload", dependencies=[Authorized])
def upload_files(
    session_id: str, payload: UploadRequest, settings: Settings, workspace: Workspace
) -> UploadReply:
    _session_dir(workspace, session_id)
    try:
        return UploadReply(results=upload(workspace, session_id, payload.files, settings))
    except BatchTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc


@router.post("/v1/sessions/{session_id}/files/download", dependencies=[Authorized])
def download_files(
    session_id: str, payload: DownloadRequest, settings: Settings, workspace: Workspace
) -> DownloadReply:
    _session_dir(workspace, session_id)
    try:
        return DownloadReply(results=download(workspace, session_id, payload.paths, settings))
    except BatchTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc


@router.post(
    "/v1/sessions/{session_id}",
    dependencies=[Authorized],
    status_code=status.HTTP_204_NO_CONTENT,
)
def release(session_id: str, workspace: Workspace) -> Response:
    """Delete the session's directory. The chat host calls this when a run ends."""
    try:
        workspace.reset(session_id)
    except InvalidSessionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _session_dir(workspace: SessionWorkspace, session_id: str) -> Path:
    try:
        return workspace.session_dir(session_id)
    except InvalidSessionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _sweep(workspace: SessionWorkspace, settings: DocgenSettings, active: set[str]) -> None:
    """Drop workdirs left behind by runs that never called release.

    Runs after a command rather than on a timer: this service has one caller and
    a low request rate, so a directory listing per command is cheaper than a
    background task that has to be cancelled cleanly on shutdown.
    """
    try:
        swept = workspace.sweep(older_than_seconds=settings.session_ttl_seconds, skip=active)
    except OSError:
        logger.warning("sweep of abandoned sessions failed", exc_info=True)
        return
    if swept:
        logger.info("swept %d abandoned sandbox sessions", len(swept))
