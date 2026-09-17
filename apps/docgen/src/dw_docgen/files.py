"""Moving bytes in and out of a session, one file at a time, with partial success.

`deepagents` requires batch file operations to report per-file errors rather
than raise, because the model is expected to read the failure and fix it. Errors
use the `FileOperationError` vocabulary the protocol defines, so the backend can
pass them straight through.
"""

from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path

from dw_docgen.models import DownloadResult, UploadFile, UploadResult
from dw_docgen.settings import DocgenSettings
from dw_docgen.workspace import (
    InvalidSessionError,
    PathOutsideSessionError,
    SessionWorkspace,
)

logger = logging.getLogger(__name__)


class BatchTooLargeError(ValueError):
    """The batch exceeded a count or byte budget, so none of it was applied."""


def upload(
    workspace: SessionWorkspace,
    session_id: str,
    files: list[UploadFile],
    settings: DocgenSettings,
) -> list[UploadResult]:
    """Write `files` into the session. Rejects the whole batch if it is oversized."""
    _check_batch_size(len(files), settings)
    decoded = _decode_all(files, settings)

    results: list[UploadResult] = []
    for item, payload in decoded:
        if isinstance(payload, str):
            results.append(UploadResult(path=item.path, error=payload))
            continue
        results.append(_write_one(workspace, session_id, item.path, payload))
    return results


def download(
    workspace: SessionWorkspace,
    session_id: str,
    paths: list[str],
    settings: DocgenSettings,
) -> list[DownloadResult]:
    """Read `paths` out of the session, refusing a batch that exceeds the budget."""
    _check_batch_size(len(paths), settings)
    results: list[DownloadResult] = []
    budget = settings.max_download_bytes
    for raw_path in paths:
        result, spent = _read_one(workspace, session_id, raw_path, budget)
        budget -= spent
        results.append(result)
    return results


def _check_batch_size(count: int, settings: DocgenSettings) -> None:
    if count > settings.max_files_per_batch:
        msg = f"batch of {count} files exceeds the limit of {settings.max_files_per_batch}"
        raise BatchTooLargeError(msg)


def _decode_all(
    files: list[UploadFile], settings: DocgenSettings
) -> list[tuple[UploadFile, bytes | str]]:
    """Decode every payload up front so an oversized batch writes nothing.

    A per-file decode inside the write loop would leave half a template on disk
    when the batch is refused, and half a template is harder to diagnose than
    none.
    """
    decoded: list[tuple[UploadFile, bytes | str]] = []
    total = 0
    for item in files:
        try:
            payload = base64.b64decode(item.content_b64, validate=True)
        except (binascii.Error, ValueError):
            decoded.append((item, "invalid_path"))
            continue
        total += len(payload)
        if total > settings.max_upload_bytes:
            msg = f"upload batch exceeds {settings.max_upload_bytes} bytes"
            raise BatchTooLargeError(msg)
        decoded.append((item, payload))
    return decoded


def _write_one(
    workspace: SessionWorkspace, session_id: str, raw_path: str, payload: bytes
) -> UploadResult:
    try:
        target = workspace.resolve(session_id, raw_path)
    except (InvalidSessionError, PathOutsideSessionError):
        return UploadResult(path=raw_path, error="invalid_path")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    except IsADirectoryError:
        return UploadResult(path=raw_path, error="is_directory")
    except PermissionError:
        return UploadResult(path=raw_path, error="permission_denied")
    except OSError:
        logger.warning("upload to %s failed", raw_path, exc_info=True)
        return UploadResult(path=raw_path, error="permission_denied")
    return UploadResult(path=raw_path)


def _read_one(
    workspace: SessionWorkspace, session_id: str, raw_path: str, budget: int
) -> tuple[DownloadResult, int]:
    """Read one file; returns the result and how much of the budget it spent."""
    try:
        source: Path = workspace.resolve(session_id, raw_path)
    except (InvalidSessionError, PathOutsideSessionError):
        return DownloadResult(path=raw_path, error="invalid_path"), 0
    if source.is_dir():
        return DownloadResult(path=raw_path, error="is_directory"), 0
    try:
        payload = source.read_bytes()
    except FileNotFoundError:
        return DownloadResult(path=raw_path, error="file_not_found"), 0
    except PermissionError:
        return DownloadResult(path=raw_path, error="permission_denied"), 0
    except OSError:
        logger.warning("download of %s failed", raw_path, exc_info=True)
        return DownloadResult(path=raw_path, error="permission_denied"), 0
    if len(payload) > budget:
        return DownloadResult(path=raw_path, error="file_too_large"), 0
    return (
        DownloadResult(path=raw_path, content_b64=base64.b64encode(payload).decode("ascii")),
        len(payload),
    )
