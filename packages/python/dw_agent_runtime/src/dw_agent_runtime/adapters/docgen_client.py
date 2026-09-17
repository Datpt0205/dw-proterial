"""The HTTP client for the docgen sandbox service.

Separate from the agent's backend because two callers need it and only one of
them is an agent. The backend scopes every call to the run's conversation; the
template plane runs `brandkit extract` in a session of its own, at upload time,
with no run to belong to.

Errors are raised, not returned. The per-file partial-success contract that
`deepagents` requires is a property of the BACKEND, not of the transport, and
translating a dead connection into fifty "file_not_found" rows would be a lie
about what happened.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Final

import httpx

from dw_kernel.errors import InfrastructureError

# The service's own ceiling is 300s; the HTTP call has to outlive the command it
# is waiting on or every long conversion reads as a network failure.
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 360.0


@dataclass(frozen=True)
class SandboxCommand:
    output: str
    exit_code: int | None
    truncated: bool
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class FileResult:
    """One entry of a batch, carrying the service's own error vocabulary."""

    path: str
    content: bytes | None = None
    error: str | None = None


class DocgenClient:
    """One docgen service, addressed by session id."""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient,
        token: str = "",
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = request_timeout_seconds

    @property
    def base_url(self) -> str:
        return self._base_url

    async def execute(
        self, session: str, command: str, *, timeout: int | None = None
    ) -> SandboxCommand:
        payload: dict[str, Any] = {"command": command}
        if timeout is not None:
            payload["timeout_seconds"] = timeout
        body = await self._post(f"/v1/sessions/{session}/execute", payload)
        return SandboxCommand(
            output=str(body.get("output", "")),
            exit_code=body.get("exit_code"),
            truncated=bool(body.get("truncated", False)),
            timed_out=bool(body.get("timed_out", False)),
        )

    async def upload(self, session: str, files: list[tuple[str, bytes]]) -> list[FileResult]:
        payload = {
            "files": [
                {"path": path, "content_b64": base64.b64encode(content).decode("ascii")}
                for path, content in files
            ]
        }
        body = await self._post(f"/v1/sessions/{session}/files/upload", payload)
        return [
            FileResult(path=str(item["path"]), error=_error_of(item)) for item in _results(body)
        ]

    async def download(self, session: str, paths: list[str]) -> list[FileResult]:
        body = await self._post(f"/v1/sessions/{session}/files/download", {"paths": paths})
        return [
            FileResult(
                path=str(item["path"]),
                content=_decoded(item.get("content_b64")),
                error=_error_of(item),
            )
            for item in _results(body)
        ]

    async def release(self, session: str) -> None:
        """Delete the session's directory. Idempotent."""
        await self._post(f"/v1/sessions/{session}", None)

    async def _post(self, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self._base_url}{path}",
                json=payload if payload is not None else {},
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise InfrastructureError(
                f"the document sandbox at {self._base_url} did not answer ({exc}); "
                "check that the docgen container is running"
            ) from exc
        return _body(response, self._base_url)


def _decoded(encoded: object) -> bytes | None:
    return base64.b64decode(str(encoded)) if encoded else None


def _error_of(item: dict[str, Any]) -> str | None:
    error = item.get("error")
    return None if error is None else str(error)


def _results(body: dict[str, Any]) -> list[dict[str, Any]]:
    results = body.get("results", [])
    if not isinstance(results, list):
        raise InfrastructureError("the document sandbox returned a reply with no results list")
    return [item for item in results if isinstance(item, dict)]


def _body(response: httpx.Response, base_url: str) -> dict[str, Any]:
    if response.status_code >= httpx.codes.BAD_REQUEST:
        raise InfrastructureError(
            f"the document sandbox at {base_url} refused the request "
            f"({response.status_code}): {response.text[:200]}"
        )
    if not response.content:
        return {}
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise InfrastructureError("the document sandbox returned a reply that is not an object")
    return parsed
