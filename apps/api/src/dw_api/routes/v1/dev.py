"""Dev-only demo endpoints: one-click login + sample data.

Mounted ONLY when auth_mode=dev outside the production profile. The session
endpoint is a convenience token issuer for the seeded roster — authorization
never relies on it: every subsequent request still verifies the token and the
DB membership. The demo-data endpoints require a normal authenticated context.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import InfrastructureError, NotFoundError
from dw_platform.adapters.identity.dev_token import DevTokenVerifier


class DemoUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    display_name: str
    description: str
    roles: tuple[str, ...]
    tenant_id: uuid.UUID
    tenant_name: str
    workspace_id: uuid.UUID


class DevSessionRequest(BaseModel):
    subject: str = Field(min_length=1)


class DevSessionResponse(BaseModel):
    token: str
    subject: str
    display_name: str
    roles: tuple[str, ...]
    tenant_id: uuid.UUID
    tenant_name: str
    workspace_id: uuid.UUID
    expires_at: datetime


def _load_roster(repo_root: Path) -> list[DemoUser]:
    path = repo_root / "configs" / "demo" / "demo_users.yaml"
    if not path.exists():
        raise InfrastructureError("demo roster missing", details={"path": str(path)})
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [DemoUser.model_validate(entry) for entry in raw["users"]]


def build_dev_router(repo_root: Path, dev_secret: str, include_session: bool = True) -> APIRouter:
    router = APIRouter(prefix="/dev", tags=["dev"])

    @router.get("/demo-users", response_model=list[DemoUser])
    async def demo_users() -> list[DemoUser]:
        return _load_roster(repo_root)

    if include_session:

        @router.post("/session", response_model=DevSessionResponse)
        async def create_session(request: DevSessionRequest) -> DevSessionResponse:
            roster = {user.subject: user for user in _load_roster(repo_root)}
            user = roster.get(request.subject)
            if user is None:
                raise NotFoundError("unknown demo subject", details={"subject": request.subject})
            ttl = timedelta(hours=8)
            token = DevTokenVerifier(dev_secret).issue(user.subject, ttl=ttl)
            return DevSessionResponse(
                token=token,
                subject=user.subject,
                display_name=user.display_name,
                roles=user.roles,
                tenant_id=user.tenant_id,
                tenant_name=user.tenant_name,
                workspace_id=user.workspace_id,
                expires_at=datetime.now(tz=UTC) + ttl,
            )

    return router
