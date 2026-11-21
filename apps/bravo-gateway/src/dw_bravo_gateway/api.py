"""The gateway's HTTP face: typed commands in, results out, nothing else.

Reached only on DW's internal network (compose publishes no port). A write
is authorised by its approval token alone (`pipeline`); the request carries
no tenant, user or role, and the route reads none. There is no free-form
SQL and no route that runs one. Reads (ticket 50) are not served yet.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from dw_bravo.contract import WRITE_KINDS, ContractError, WriteCommand
from dw_bravo_gateway.pipeline import WritePipeline

_TOKEN_LIMIT = 4096


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=64)
    version: int = Field(ge=1, le=9999)
    content: dict[str, Any]


class WriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: _Envelope
    token: str = Field(min_length=1, max_length=_TOKEN_LIMIT)


def parse_command(envelope: _Envelope) -> WriteCommand:
    kind = WRITE_KINDS.get(f"{envelope.kind}@{envelope.version}")
    if kind is None:
        raise HTTPException(422, "not a write the gateway takes")
    try:
        command: WriteCommand = TypeAdapter(kind.command).validate_python(envelope.content)
    except (ValidationError, ContractError):
        raise HTTPException(422, "the command does not satisfy its contract") from None
    return command


def create_app(
    pipeline: WritePipeline, *, max_request_bytes: int = 64 * 1024, docs: bool = False
) -> FastAPI:
    app = FastAPI(
        title="dw-bravo-gateway",
        openapi_url="/openapi.json" if docs else None,
        docs_url=None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def _bounded(request: Request, call_next: Any) -> Any:
        length = request.headers.get("content-length")
        if length is None and request.method == "POST":
            return JSONResponse({"detail": "a length is required"}, status_code=411)
        if length is not None and (not length.isdigit() or int(length) > max_request_bytes):
            return JSONResponse({"detail": "request too large"}, status_code=413)
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/writes")
    async def write(body: WriteRequest) -> dict[str, object]:
        result = await pipeline.execute(parse_command(body.command), body.token)
        return asdict(result)

    @app.post("/v1/writes/preview")
    async def preview(body: WriteRequest) -> dict[str, object]:
        found = await pipeline.preview(parse_command(body.command), body.token)
        return {
            "check": found.check,
            "reason": found.reason,
            "warnings": list(found.warnings),
            "statements": (
                []
                if found.batch is None
                else [{"table": s.table, "sql": s.sql} for s in found.batch.statements]
            ),
        }

    return app
