"""HTTP surface. Authorization belongs where the mutation is."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from dw_purchasing.application.handlers import HandlePurchasing
from dw_purchasing.domain.entities import PurchasingRequest


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=200)


def build_router(handler: HandlePurchasing) -> APIRouter:
    """Injected, never resolved from a global: the app owns the wiring.

    The router is built here, per call. A module-level one would collect a
    route on every call, and a second app would be served by the first app's
    handler.
    """
    router = APIRouter(prefix="/api/v1/purchasing", tags=["purchasing"])

    @router.post("/requests")
    async def create(body: _Body) -> dict[str, str]:
        # Tenancy comes from the verified access context in a real context, never
        # from the body. Fixed here so the generated slice cannot look like a
        # place where a client supplies its own tenant.
        request = PurchasingRequest(
            request_id=uuid.uuid4(), tenant_id=uuid.UUID(int=0), subject=body.subject
        )
        return {"summary": await handler(request)}

    return router
